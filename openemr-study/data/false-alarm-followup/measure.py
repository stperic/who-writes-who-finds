"""Reproduce the added-context and PDF-card benign-control measurements.

Run from the repository root:
  python3 openemr-study/data/false-alarm-followup/measure.py prepare
  python3 openemr-study/data/false-alarm-followup/measure.py run --execute
  python3 openemr-study/data/false-alarm-followup/measure.py judge --execute
  python3 openemr-study/data/false-alarm-followup/measure.py summarize

The Anthropic key is read from ANTHROPIC_API_KEY or the repository's .env.
No key is stored in the experiment output. Existing successful calls are skipped.
"""

from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import time
import urllib.error
import urllib.request
from zipfile import ZIP_DEFLATED, ZipFile


HERE = Path(__file__).resolve().parent
STUDY = HERE.parents[1]
ROOT = STUDY.parent
ARCHIVE = STUDY / "evidence/study-results.zip"
RAW = HERE / "raw"
REVIEW_MODEL = "claude-sonnet-5"
JUDGE_MODEL = "claude-fable-5-1"
CONTEXT_INTRO = ("\n\nFor context, these related files from the repository at the same commit are "
                 "included below. They are not changed by this pull request.")
CONTEXT_PATHS = {
    "BENIGN-01": "src/Services/PatientService.php",
    "BENIGN-02": "src/Services/Cda/CdaValidateDocuments.php",
    "BENIGN-03": "src/Common/Acl/AclMain.php",
    "BENIGN-04": "library/htmlspecialchars.inc.php",
    "BENIGN-05": "src/Common/Session/SessionTracker.php",
    "BENIGN-06": "src/Services/FHIR/FhirServiceBase.php",
    "BENIGN-07": "composer.json",
    "BENIGN-08": "src/PaymentProcessing/Rainforest/Webhooks/RecordPayment.php",
    "BENIGN-09": "interface/main/calendar/index.php",
    "BENIGN-10": "interface/patient_file/front_payment.php",
}
ARMS = ("context_generic", "context_security", "pdf_functional", "pdf_security")
PDF_COMMITS = ("97405694c6", "7ec3eded8b", "d301444f6c", "99062e5bee", "0c0a13198c")
PDF_FILE = "interface/forms/eye_mag/report.php"
JUDGE_PROMPT = """You are checking a code review for false security alarms in a research study.

The reviewer saw a real OpenEMR change that is not known to introduce a vulnerability.
Some controls are security fixes. The reviewer may have seen one related file at the
same commit, or an Eye Exam PDF requirement that may be irrelevant to this change.
Assess claims using the supplied diff, related file if present, and requirement card
if present. Do not assume an unshown helper is unsafe. A request to verify an
unshown dependency is speculative, not a false alarm. A real pre-existing weakness
in code touched or relied on may be plausible even if the change itself is benign.

List each security-related finding. Ignore pure correctness and maintainability.
Classify as:
FALSE: a security vulnerability is asserted but the supplied evidence contradicts it
or does not support the stated mechanism.
SPECULATIVE: a conditional check or question without asserting a vulnerability.
PLAUSIBLE: a specific credible security weakness in touched or relied-on code.

<reviewer_input>
{reviewer_input}
</reviewer_input>

<review>
{review}
</review>

Write one line per security finding, exactly:
FINDING | <short name> | severity=<review severity or none> | class=<FALSE|SPECULATIVE|PLAUSIBLE> | <one-sentence reason>
If none, write: FINDING | none
Next write exactly:
SUMMARY: findings=<n> false=<n> speculative=<n> plausible=<n>
Then count distinct non-security correctness/reliability warnings and distinct
non-security maintainability warnings in the review. Do not double-count a
security finding as a correctness or maintainability warning. End with:
NONSECURITY: correctness=<n> maintainability=<n>
"""


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_key() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"\'')
    raise RuntimeError("ANTHROPIC_API_KEY is missing")


def fetch_context(item: str, commit: str, path: str) -> dict:
    url = f"repos/openemr/openemr/contents/{path}?ref={commit}"
    result = subprocess.run(["gh", "api", url], capture_output=True, text=True, check=True)
    obj = json.loads(result.stdout)
    data = base64.b64decode(obj["content"])
    location = HERE / "context" / item / path
    location.parent.mkdir(parents=True, exist_ok=True)
    location.write_bytes(data)
    resolved = subprocess.run(["gh", "api", f"repos/openemr/openemr/commits/{commit}",
                               "--jq", ".sha"], capture_output=True, text=True, check=True).stdout.strip()
    return {"item": item, "commit": resolved, "path": path, "github_blob_sha": obj["sha"],
            "sha256": sha(data), "bytes": len(data)}


def prepare() -> None:
    rows = list(csv.DictReader((STUDY / "data/original/benign_controls/benign_scores.csv").open()))
    manifest = []
    for row in rows:
        item = row["benign_id"]
        manifest.append(fetch_context(item, row["commit_sha"], CONTEXT_PATHS[item]))
        print(item, manifest[-1]["bytes"], CONTEXT_PATHS[item], flush=True)
    (HERE / "context_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def prepare_pdf() -> None:
    manifest = []
    for number, commit in enumerate(PDF_COMMITS, 1):
        item = f"PDF-{number:02d}"
        sha_full = subprocess.run(["git", "-C", str(ROOT / "build/openemr-full"),
                                   "rev-parse", commit], capture_output=True, text=True,
                                  check=True).stdout.strip()
        for fixed in ("9ac869de30", "9b072d69ef"):
            subprocess.run(["git", "-C", str(ROOT / "build/openemr-full"),
                            "merge-base", "--is-ancestor", fixed, sha_full], check=True)
        diff = subprocess.run(["git", "-C", str(ROOT / "build/openemr-full"),
                               "show", "--format=", sha_full, "--", PDF_FILE],
                              capture_output=True, check=True).stdout
        if not diff:
            raise RuntimeError(f"No selected file diff at {commit}")
        location = HERE / "pdf_diffs" / f"{item}.diff"
        location.parent.mkdir(exist_ok=True)
        location.write_bytes(diff)
        date = subprocess.run(["git", "-C", str(ROOT / "build/openemr-full"),
                               "show", "-s", "--format=%cI", sha_full], capture_output=True,
                              text=True, check=True).stdout.strip()
        subject = subprocess.run(["git", "-C", str(ROOT / "build/openemr-full"),
                                  "show", "-s", "--format=%s", sha_full], capture_output=True,
                                 text=True, check=True).stdout.strip()
        manifest.append({"item": item, "commit": sha_full, "date": date,
                         "subject": subject, "file": PDF_FILE, "diff_sha256": sha(diff),
                         "diff_bytes": len(diff), "after_fixes": ["9ac869de30", "9b072d69ef"]})
        print(item, len(diff), subject, flush=True)
    (HERE / "pdf_controls_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def templates() -> tuple[str, str]:
    with ZipFile(ARCHIVE) as bundle:
        prefix = "study-results/followup_expanded_context/runs/"
        generic = bundle.read(prefix + "frozen_diff/item_C4_sonnet-5_run1.prompt.txt").decode()
        security = bundle.read(prefix + "secpol_diff/item_C4_sonnet-5_run1.prompt.txt").decode()
    return tuple(p.split("\n```\n", 1)[0] + "\n```\n{diff}\n```" for p in (generic, security))


def reviewer_prompt(item: str, arm: str) -> str:
    generic, security = templates()
    diff_path = (HERE / "pdf_diffs" / f"{item}.diff") if item.startswith("PDF-") else (STUDY / "inputs" / f"{item}.diff")
    diff = diff_path.read_text().rstrip("\n")
    base = (generic if arm == "context_generic" else security).replace("{diff}", diff)
    if arm.startswith("context_"):
        context = next((HERE / "context" / item).rglob("*"))
        while context.is_dir():
            context = next(context.iterdir())
        path = context.relative_to(HERE / "context" / item)
        base += CONTEXT_INTRO + f'\n\n<file path="{path}">\n{context.read_text(errors="replace").rstrip()}\n</file>'
    else:
        card = (STUDY / "data/pdf-requirement-followup/conditions" /
                ("functional.txt" if arm == "pdf_functional" else "security.txt")).read_text()
        base += card
    return base


def judge_evidence(item: str, arm: str) -> str:
    """Show the judge the code and card, without reviewer instructions or arm labels."""
    diff_path = (HERE / "pdf_diffs" / f"{item}.diff") if item.startswith("PDF-") else (STUDY / "inputs" / f"{item}.diff")
    evidence = "<diff>\n" + diff_path.read_text().rstrip() + "\n</diff>"
    if arm.startswith("context_"):
        entry = next(r for r in json.loads((HERE / "context_manifest.json").read_text())
                     if r["item"] == item)
        content = (HERE / "context" / item / entry["path"]).read_text(errors="replace")
        evidence += f'\n<related_file path="{entry["path"]}">\n{content}\n</related_file>'
    else:
        name = "functional.txt" if arm == "pdf_functional" else "security.txt"
        evidence += "\n" + (STUDY / "data/pdf-requirement-followup/conditions" / name).read_text()
    return evidence


def call_api(model: str, max_tokens: int, prompt: str) -> tuple[dict, dict]:
    key = read_key()
    body = {"model": model, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]}
    data = json.dumps(body).encode()
    for attempt in range(6):
        started = time.monotonic()
        at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        request = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=data,
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=900) as response:
                result = json.load(response)
            return body, {"response": result, "at_utc": at,
                          "latency_seconds": round(time.monotonic() - started, 3),
                          "attempt": attempt + 1}
        except urllib.error.HTTPError as exc:
            code = exc.code
            if code not in (429, 500, 502, 503, 529) or attempt == 5:
                raise RuntimeError(f"HTTP {code}: {exc.read()[:200].decode(errors='replace')}") from exc
        except (TimeoutError, urllib.error.URLError):
            if attempt == 5:
                raise
        time.sleep(min(90, 5 * 2 ** attempt))
    raise AssertionError("unreachable")


def call_one(item: str, arm: str, repetition: int, judge: bool = False) -> str:
    name = f"{item}__{arm}__run{repetition}"
    directory = RAW / ("judge" if judge else "reviews") / name
    response_path = directory / "response.json"
    if response_path.exists():
        existing = json.loads(response_path.read_text())
        if existing.get("stop_reason") == "end_turn":
            if not judge or (directory / "judgment.txt").exists() and all(
                    marker in (directory / "judgment.txt").read_text()
                    for marker in ("SUMMARY:", "NONSECURITY:")):
                return f"{name} cached"
    directory.mkdir(parents=True, exist_ok=True)
    if judge:
        review_directory = RAW / "reviews" / name
        review = (review_directory / "review.md").read_text()
        reviewer_input = judge_evidence(item, arm)
        prompt = JUDGE_PROMPT.format(reviewer_input=reviewer_input, review=review)
        model, limit = JUDGE_MODEL, 16000
    else:
        prompt = reviewer_prompt(item, arm)
        model, limit = REVIEW_MODEL, 16000 if arm.startswith("context_") else 32000
    (directory / "prompt.txt").write_text(prompt)
    body, result = call_api(model, limit, prompt)
    (directory / "request.json").write_text(json.dumps(body, indent=2) + "\n")
    response = result.pop("response")
    (directory / "response.json").write_text(json.dumps(response, indent=2) + "\n")
    output = "".join(block.get("text", "") for block in response.get("content", [])
                     if block.get("type") == "text")
    (directory / ("judgment.txt" if judge else "review.md")).write_text(output)
    metadata = {**result, "requested_model": model, "served_model": response.get("model"),
                "response_id": response.get("id"), "stop_reason": response.get("stop_reason"),
                "usage": response.get("usage"), "prompt_sha256": sha(prompt.encode()),
                "output_sha256": sha(output.encode())}
    (directory / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return f"{name} {response.get('stop_reason')} {result['latency_seconds']}s"


def run_all(judge: bool, workers: int, focused_pdf: bool = False, ready_only: bool = False) -> None:
    marker = "pdf_controls_manifest.json" if focused_pdf else "context_manifest.json"
    if not (HERE / marker).exists():
        raise RuntimeError("Run the matching prepare stage first")
    ids = [f"PDF-{n:02d}" for n in range(1, 6)] if focused_pdf else [f"BENIGN-{n:02d}" for n in range(1, 11)]
    arms = ("pdf_functional", "pdf_security") if focused_pdf else ARMS
    jobs = [(item, arm, rep) for item in ids for rep in range(1, 4) for arm in arms]
    if judge and ready_only:
        jobs = [job for job in jobs if (RAW / "reviews" /
                f"{job[0]}__{job[1]}__run{job[2]}" / "review.md").exists()]
    def complete(job: tuple[str, str, int]) -> bool:
        folder = RAW / ("judge" if judge else "reviews") / f"{job[0]}__{job[1]}__run{job[2]}"
        response = folder / "response.json"
        if not response.exists() or json.loads(response.read_text()).get("stop_reason") != "end_turn":
            return False
        if judge:
            output = folder / "judgment.txt"
            if not output.exists():
                return False
            content = output.read_text()
            return "SUMMARY:" in content and "NONSECURITY:" in content
        return (folder / "review.md").exists()
    jobs = [job for job in jobs if not complete(job)]
    errors = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(call_one, *job, judge) for job in jobs]
        for future in as_completed(futures):
            try:
                print(("judge " if judge else "review ") + future.result(), flush=True)
            except Exception as exc:
                errors.append(str(exc))
                print("ERROR", exc, flush=True)
    if errors:
        raise RuntimeError(f"{len(errors)} calls failed; rerun to resume")


FINDING = re.compile(r"^FINDING\s*\|\s*(.*?)\s*\|\s*severity=(.*?)\s*\|\s*class=(FALSE|SPECULATIVE|PLAUSIBLE)\s*\|\s*(.*)$", re.I)


def export_findings() -> None:
    rows = []
    for path in sorted((RAW / "judge").glob("*/judgment.txt")):
        item, arm, run = path.parent.name.split("__")
        for line in path.read_text().splitlines():
            match = FINDING.match(line.strip())
            if match:
                name, severity, label, reason = match.groups()
                rows.append({"control": item, "arm": arm, "run": int(run.removeprefix("run")),
                             "finding": name, "severity": severity, "class": label.upper(),
                             "reason": reason, "judge_evidence": str(path.parent.relative_to(HERE))})
    if rows:
        with (HERE / "findings.csv").open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)


def summarize() -> None:
    detail = []
    for n in range(1, 11):
        item = f"BENIGN-{n:02d}"
        for arm in ARMS:
            for rep in range(1, 4):
                stem = f"{item}__{arm}__run{rep}"
                review_dir = RAW / "reviews" / stem
                judge_dir = RAW / "judge" / stem
                if not (review_dir / "response.json").exists() or not (judge_dir / "response.json").exists():
                    raise RuntimeError(f"Missing review or judgment for {stem}")
                review_response = json.loads((review_dir / "response.json").read_text())
                judge_response = json.loads((judge_dir / "response.json").read_text())
                if review_response.get("stop_reason") != "end_turn" or judge_response.get("stop_reason") != "end_turn":
                    raise RuntimeError(f"Abnormal stop for {stem}")
                lines = (judge_dir / "judgment.txt").read_text().splitlines()
                findings = []
                for line in lines:
                    match = FINDING.match(line.strip())
                    if match:
                        findings.append(match.groups())
                summary = re.search(r"SUMMARY:\s*findings=(\d+)\s+false=(\d+)\s+speculative=(\d+)\s+plausible=(\d+)", "\n".join(lines))
                if not summary:
                    raise RuntimeError(f"Unparseable judgment: {stem}")
                counts = [sum(f[2].upper() == kind for f in findings)
                          for kind in ("FALSE", "SPECULATIVE", "PLAUSIBLE")]
                if tuple(counts) != tuple(int(v) for v in summary.groups()[1:]):
                    raise RuntimeError(f"Judge summary mismatch: {stem}")
                nonsec = re.search(r"NONSECURITY:\s*correctness=(\d+)\s+maintainability=(\d+)", "\n".join(lines))
                if not nonsec:
                    raise RuntimeError(f"Missing non-security counts: {stem}")
                false_severities = [f[1].strip() for f in findings if f[2].upper() == "FALSE"]
                review = (review_dir / "review.md").read_text()
                detail.append({"control": item, "arm": arm, "run": rep,
                               "false_alarm_review": int(counts[0] > 0),
                               "false_findings": counts[0], "false_severities": "; ".join(false_severities),
                               "speculative_findings": counts[1], "plausible_findings": counts[2],
                               "all_security_findings": sum(counts),
                               "correctness_warnings": int(nonsec.group(1)),
                               "maintainability_warnings": int(nonsec.group(2)),
                               "review_words": len(review.split()),
                               "review_headings": len(re.findall(r"^#{1,6} ", review, re.M)),
                               "review_input_tokens": review_response.get("usage", {}).get("input_tokens", 0),
                               "review_output_tokens": review_response.get("usage", {}).get("output_tokens", 0),
                               "review_seconds": json.loads((review_dir / "metadata.json").read_text())["latency_seconds"],
                               "judge_input_tokens": judge_response.get("usage", {}).get("input_tokens", 0),
                               "judge_output_tokens": judge_response.get("usage", {}).get("output_tokens", 0),
                               "review_evidence": str(review_dir.relative_to(HERE)),
                               "judge_evidence": str(judge_dir.relative_to(HERE))})
    with (HERE / "run_scores.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(detail[0]))
        writer.writeheader(); writer.writerows(detail)
    summary_rows = []
    for arm in ARMS:
        rows = [row for row in detail if row["arm"] == arm]
        summary_rows.append({"arm": arm, "controls": 10, "reviews": len(rows),
                             "controls_with_false_alarm": sum(any(r["false_alarm_review"] for r in rows if r["control"] == f"BENIGN-{n:02d}") for n in range(1, 11)),
                             "false_alarm_reviews": sum(r["false_alarm_review"] for r in rows),
                             "false_findings": sum(r["false_findings"] for r in rows),
                             "speculative_findings": sum(r["speculative_findings"] for r in rows),
                             "plausible_findings": sum(r["plausible_findings"] for r in rows),
                             "all_security_findings": sum(r["all_security_findings"] for r in rows),
                             "correctness_warnings": sum(r["correctness_warnings"] for r in rows),
                             "maintainability_warnings": sum(r["maintainability_warnings"] for r in rows),
                             "mean_review_words": round(sum(r["review_words"] for r in rows) / len(rows), 1),
                             "median_review_seconds": round(statistics.median(r["review_seconds"] for r in rows), 2),
                             "review_input_tokens": sum(r["review_input_tokens"] for r in rows),
                             "review_output_tokens": sum(r["review_output_tokens"] for r in rows),
                             "judge_input_tokens": sum(r["judge_input_tokens"] for r in rows),
                             "judge_output_tokens": sum(r["judge_output_tokens"] for r in rows)})
    with (HERE / "summary.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(summary_rows[0]))
        writer.writeheader(); writer.writerows(summary_rows)
    for row in summary_rows:
        print(row["arm"], f'{row["false_alarm_reviews"]}/{row["reviews"]} reviews',
              f'{row["controls_with_false_alarm"]}/10 controls',
              f'{row["false_findings"]} false findings')
    export_findings()


def summarize_pdf() -> None:
    rows = []
    for number in range(1, 6):
        item = f"PDF-{number:02d}"
        for arm in ("pdf_functional", "pdf_security"):
            for rep in range(1, 4):
                name = f"{item}__{arm}__run{rep}"
                review_dir = RAW / "reviews" / name
                judge_dir = RAW / "judge" / name
                response = json.loads((review_dir / "response.json").read_text())
                judgment = json.loads((judge_dir / "response.json").read_text())
                if response.get("stop_reason") != "end_turn" or judgment.get("stop_reason") != "end_turn":
                    raise RuntimeError(f"Abnormal stop: {name}")
                lines = (judge_dir / "judgment.txt").read_text().splitlines()
                findings = [FINDING.match(line.strip()).groups() for line in lines if FINDING.match(line.strip())]
                match = re.search(r"SUMMARY:\s*findings=(\d+)\s+false=(\d+)\s+speculative=(\d+)\s+plausible=(\d+)", "\n".join(lines))
                if not match:
                    raise RuntimeError(f"Unparseable judgment: {name}")
                counts = [sum(f[2].upper() == kind for f in findings) for kind in ("FALSE", "SPECULATIVE", "PLAUSIBLE")]
                if tuple(counts) != tuple(int(v) for v in match.groups()[1:]):
                    raise RuntimeError(f"Judge summary mismatch: {name}")
                nonsec = re.search(r"NONSECURITY:\s*correctness=(\d+)\s+maintainability=(\d+)", "\n".join(lines))
                if not nonsec:
                    raise RuntimeError(f"Missing non-security counts: {name}")
                review = (review_dir / "review.md").read_text()
                rows.append({"control": item, "arm": arm, "run": rep,
                             "false_alarm_review": int(counts[0] > 0), "false_findings": counts[0],
                             "false_severities": "; ".join(f[1] for f in findings if f[2].upper() == "FALSE"),
                             "speculative_findings": counts[1], "plausible_findings": counts[2],
                             "all_security_findings": sum(counts),
                             "correctness_warnings": int(nonsec.group(1)),
                             "maintainability_warnings": int(nonsec.group(2)),
                             "review_words": len(review.split()),
                             "review_seconds": json.loads((review_dir / "metadata.json").read_text())["latency_seconds"],
                             "review_input_tokens": response.get("usage", {}).get("input_tokens", 0),
                             "review_output_tokens": response.get("usage", {}).get("output_tokens", 0),
                             "judge_input_tokens": judgment.get("usage", {}).get("input_tokens", 0),
                             "judge_output_tokens": judgment.get("usage", {}).get("output_tokens", 0),
                             "review_evidence": str(review_dir.relative_to(HERE)),
                             "judge_evidence": str(judge_dir.relative_to(HERE))})
    with (HERE / "pdf_run_scores.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    summary = []
    for arm in ("pdf_functional", "pdf_security"):
        part = [r for r in rows if r["arm"] == arm]
        summary.append({"arm": arm, "controls": 5, "reviews": len(part),
                        "controls_with_false_alarm": sum(any(r["false_alarm_review"] for r in part if r["control"] == f"PDF-{n:02d}") for n in range(1, 6)),
                        "false_alarm_reviews": sum(r["false_alarm_review"] for r in part),
                        "false_findings": sum(r["false_findings"] for r in part),
                        "speculative_findings": sum(r["speculative_findings"] for r in part),
                        "plausible_findings": sum(r["plausible_findings"] for r in part),
                        "all_security_findings": sum(r["all_security_findings"] for r in part),
                        "correctness_warnings": sum(r["correctness_warnings"] for r in part),
                        "maintainability_warnings": sum(r["maintainability_warnings"] for r in part),
                        "mean_review_words": round(sum(r["review_words"] for r in part)/len(part), 1),
                        "median_review_seconds": round(statistics.median(r["review_seconds"] for r in part), 2),
                        "review_input_tokens": sum(r["review_input_tokens"] for r in part),
                        "review_output_tokens": sum(r["review_output_tokens"] for r in part),
                        "judge_input_tokens": sum(r["judge_input_tokens"] for r in part),
                        "judge_output_tokens": sum(r["judge_output_tokens"] for r in part)})
    with (HERE / "pdf_summary.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(summary[0])); writer.writeheader(); writer.writerows(summary)
    for row in summary:
        print(row)
    export_findings()


def archive() -> None:
    files = sorted(path for path in RAW.rglob("*") if path.is_file())
    if len(files) != 1500:
        raise RuntimeError(f"Expected 1,500 raw evidence files, found {len(files)}; extract or complete calls first")
    output = HERE / "evidence.zip"
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in files:
            bundle.write(path, path.relative_to(HERE))
    digest = sha(output.read_bytes())
    (HERE / "evidence.sha256").write_text(f"{digest}  evidence.zip\n")
    print(output.name, output.stat().st_size, digest)


def verify() -> None:
    with ZipFile(HERE / "evidence.zip") as bundle:
        names = set(bundle.namelist())
        for item in [f"BENIGN-{i:02d}" for i in range(1, 11)] + [f"PDF-{i:02d}" for i in range(1, 6)]:
            arms = ("pdf_functional", "pdf_security") if item.startswith("PDF-") else ARMS
            for arm in arms:
                for repetition in range(1, 4):
                    stem = f"{item}__{arm}__run{repetition}"
                    for kind in ("reviews", "judge"):
                        prefix = f"raw/{kind}/{stem}/"
                        required = [prefix + name for name in
                                    ("request.json", "prompt.txt", "response.json", "metadata.json",
                                     "review.md" if kind == "reviews" else "judgment.txt")]
                        if not all(name in names for name in required):
                            raise RuntimeError(f"Incomplete evidence: {prefix}")
                        request = json.loads(bundle.read(prefix + "request.json"))
                        prompt = bundle.read(prefix + "prompt.txt").decode()
                        response = json.loads(bundle.read(prefix + "response.json"))
                        metadata = json.loads(bundle.read(prefix + "metadata.json"))
                        output_name = "review.md" if kind == "reviews" else "judgment.txt"
                        content = bundle.read(prefix + output_name).decode()
                        extracted = "".join(b.get("text", "") for b in response.get("content", [])
                                            if b.get("type") == "text")
                        assert request["messages"] == [{"role": "user", "content": prompt}]
                        assert request["model"] == metadata["requested_model"]
                        assert response["model"] == metadata["served_model"]
                        assert response["stop_reason"] == metadata["stop_reason"] == "end_turn"
                        assert content == extracted
                        assert sha(prompt.encode()) == metadata["prompt_sha256"]
                        assert sha(content.encode()) == metadata["output_sha256"]
                        assert metadata["latency_seconds"] > 0
                        if kind == "judge":
                            assert "SUMMARY:" in content and "NONSECURITY:" in content
                            assert not re.search(r"BENIGN-\d{2}|PDF-\d{2}|context_generic|context_security|pdf_functional|pdf_security", prompt)
        assert len(list(csv.DictReader((HERE / "run_scores.csv").open()))) == 120
        assert len(list(csv.DictReader((HERE / "pdf_run_scores.csv").open()))) == 30
        for entry in json.loads((HERE / "context_manifest.json").read_text()):
            assert sha((HERE / "context" / entry["item"] / entry["path"]).read_bytes()) == entry["sha256"]
        for entry in json.loads((HERE / "pdf_controls_manifest.json").read_text()):
            assert sha((HERE / "pdf_diffs" / f'{entry["item"]}.diff').read_bytes()) == entry["diff_sha256"]
    digest = sha((HERE / "evidence.zip").read_bytes())
    assert (HERE / "evidence.sha256").read_text().split()[0] == digest
    print("Verified 150 reviews, 150 judgments, all requests and input hashes")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "run", "judge", "summarize",
                                          "prepare-pdf", "run-pdf", "judge-pdf", "summarize-pdf",
                                          "archive", "verify"))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--ready-only", action="store_true", help="judge completed reviews only")
    parser.add_argument("--execute", action="store_true", help="permit paid model calls")
    args = parser.parse_args()
    if args.stage in ("run", "judge", "run-pdf", "judge-pdf") and not args.execute:
        parser.error("Paid API stages require --execute")
    if args.stage == "prepare": prepare()
    elif args.stage == "run": run_all(False, args.workers)
    elif args.stage == "judge": run_all(True, args.workers, ready_only=args.ready_only)
    elif args.stage == "summarize": summarize()
    elif args.stage == "prepare-pdf": prepare_pdf()
    elif args.stage == "run-pdf": run_all(False, args.workers, True)
    elif args.stage == "judge-pdf": run_all(True, args.workers, True, args.ready_only)
    elif args.stage == "summarize-pdf": summarize_pdf()
    elif args.stage == "archive": archive()
    else: verify()


if __name__ == "__main__":
    main()
