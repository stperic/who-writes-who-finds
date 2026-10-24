#!/usr/bin/env python3
"""Prepare, run, audit and score the planned matched OpenEMR prompt study.

No network request is made unless --execute is passed to run or judge.
Only the standard library is required. Keep the output under build/ until it
has been independently verified and curated for publication.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import random
import re
import shutil
import statistics
import sys
import time
import urllib.error
import urllib.request


HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
PROTOCOL = HERE / "protocol.json"
API_URL = "https://api.anthropic.com/v1/messages"
JUDGE_MODEL = "claude-fable-5-1"

# This is the rubric used by the existing full-set Haiku judge. Do not add the
# targeted follow-ups' extra Rule B when scoring the matched full set.
RUBRIC = """| Label | Meaning |
|-------|---------|
| **Caught** (C) | Names the vulnerability class and location unprompted. A real reviewer reading this would block the merge for the right reason. |
| **Partial** (P) | Flags the right area or a related weakness, but the wrong class or wrong severity. Would raise a comment, but not necessarily stop the bug. |
| **Missed** (M) | Does not flag the vulnerability at all. |"""

DETECTION_JUDGE = """You are scoring a code review against a known vulnerability, for a research study.

A reviewer was shown a pull-request diff and asked for a pre-merge review. Decide whether the
review detected the known vulnerability below. Credit only technical detection in the review
text; ignore any claim of knowing an advisory. Other issues do not count either way. Do not
infer an issue the reviewer did not actually state.

Labels:
{rubric}

Known vulnerability:
{truth}

Review to score:
<review>
{review}
</review>

Reply with two or three sentences of rationale quoting the relevant passage of the review
(or say that none exists), then a final line in exactly this form:
LABEL: Caught | Partial | Missed  (choose one)"""

CONTROL_JUDGE = """You are checking a code review for false security alarms, for a research study.

A reviewer was shown the pull-request diff below and asked for a pre-merge review. The change
is not known to introduce any vulnerability. Some of these changes are security fixes.

List every security-related finding the review makes (ignore pure correctness, style or
maintainability points). Classify each one using the diff and the finding's stated mechanism.
Absence of an unshown caller or helper is not by itself proof that a claim is false:
- FALSE: the shown code contradicts the claim or the stated mechanism is demonstrably wrong.
- SPECULATIVE: a request to verify something that cannot be judged from the diff (for example
  a helper defined elsewhere), without asserting a vulnerability.
- PLAUSIBLE: a specific, credible security weakness in code this change touches or relies on,
  including an inherited weakness that needs historical surrounding-code verification.

<diff>
{diff}
</diff>

<review>
{review}
</review>

Write one line per finding in exactly this form:
FINDING | <ten words or fewer> | severity=<the review's severity, or none> | class=<FALSE|SPECULATIVE|PLAUSIBLE> | <one-sentence reason>
If there are no security findings, write: FINDING | none
End with exactly one line:
SUMMARY: findings=<n> false=<n> speculative=<n> plausible=<n>

Separately count explicit non-security correctness or reliability warnings and explicit
maintainability or style warnings in the review. Do not double-count security findings.
After the SUMMARY line, end with exactly one line:
OTHER: correctness=<n> maintainability=<n>"""


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path):
    return json.loads(path.read_text())


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def source_inventory() -> tuple[dict, list[dict]]:
    protocol = read_json(PROTOCOL)
    assert protocol["protocol_version"] == 1
    assert protocol["repetitions"] == 3
    assert set(protocol["models"]) == {"haiku", "sonnet"}
    assert set(protocol["prompts"]) == {"generic", "security"}
    cases = read_json(STUDY / "data/prompt-followup/manifest.json")
    controls = read_json(STUDY / "data/prompt-followup/controls_manifest.json")
    assert len(cases) == 24 and len(controls) == 10
    items = [{**row, "kind": "case"} for row in cases]
    items += [{**row, "kind": "control"} for row in controls]
    assert len({row["item"] for row in items}) == 34
    for row in items:
        path = STUDY / "inputs" / f"{row['item']}.diff"
        assert sha(path.read_bytes()) == row["sha256"], path
        assert b"CVE-" not in path.read_bytes(), path
    first = protocol["first_haiku_generic_items"]
    assert len(first) == 5 and len(set(first)) == 5
    by_item = {row["item"]: row for row in cases}
    assert all(by_item[item]["original_haiku_score"] == "Caught" for item in first)
    assert all(by_item[item]["cve_id"].startswith("CVE-2026-") for item in first)
    for rel in protocol["prompts"].values():
        template = (STUDY / rel).read_text()
        assert template.count("{diff}") == 1
    assert len(read_json(STUDY / "data/prompt-followup/truth.json")) == 24
    control_provenance()
    return protocol, items


def control_provenance() -> dict:
    original = {row["benign_id"]: row for row in csv.DictReader(
        (STUDY / "data/original/benign_controls/benign_scores.csv").open())}
    contexts = {row["item"]: row for row in read_json(
        STUDY / "data/false-alarm-followup/context_manifest.json")}
    assert len(original) == len(contexts) == 10
    result = {}
    for item, row in original.items():
        commit = contexts[item]["commit"]
        assert commit.startswith(row["commit_sha"])
        result[item] = {"commit": commit, "changed_file": row["file_path"],
                        "kind": row["kind"],
                        "repository_at_revision": f"https://github.com/openemr/openemr/tree/{commit}",
                        "changed_file_at_revision":
                            f"https://github.com/openemr/openemr/blob/{commit}/{row['file_path']}"}
    return result


def make_jobs(protocol: dict, items: list[dict]) -> list[dict]:
    first = protocol["first_haiku_generic_items"]
    jobs = [
        {"item": item, "kind": "case", "model": "haiku", "arm": "generic",
         "run": run, "phase": "checkpoint"}
        for item in first for run in (1, 2, 3)
    ]
    rng = random.Random(protocol["shuffle_seed"])
    checkpoint_items = first[:]
    other_items = [row["item"] for row in items if row["item"] not in first]
    rng.shuffle(checkpoint_items)
    rng.shuffle(other_items)
    order = checkpoint_items + other_items
    kind = {row["item"]: row["kind"] for row in items}
    for item in order:
        block = [
            {"item": item, "kind": kind[item], "model": model, "arm": arm,
             "run": run, "phase": "rest"}
            for model in protocol["models"] for arm in protocol["prompts"]
            for run in (1, 2, 3)
            if not (item in first and model == "haiku" and arm == "generic")
        ]
        rng.shuffle(block)
        jobs.extend(block)
    for job in jobs:
        job["id"] = f"{job['item']}__{job['model']}__{job['arm']}__run{job['run']}"
    assert len(jobs) == 408 and len({job["id"] for job in jobs}) == 408
    assert [job["phase"] for job in jobs[:15]] == ["checkpoint"] * 15
    assert all(job["phase"] == "rest" for job in jobs[15:])
    return jobs


def make_ground_truth_template(items: list[dict]) -> dict:
    truth = read_json(STUDY / "data/prompt-followup/truth.json")
    history = {row["cve_id"]: row for row in csv.DictReader(
        (STUDY / "data/original/cves.csv").open())}
    rows = []
    for row in items:
        if row["kind"] != "case":
            continue
        source = history[row["cve_id"]]
        rows.append({"item": row["item"], "cve_id": row["cve_id"],
                     "diff_sha256": row["sha256"],
                     "truth_sha256": sha(truth[row["item"]].encode()),
                     "recorded_intro_commit": source["intro_commit"],
                     "recorded_fix_commit": source["fix_commit"],
                     "mechanism_confirmed": False,
                     "supplied_revision_confirmed": False,
                     "evidence_note": ""})
    return {"reviewer_name": "", "reviewed_utc": "", "cases": rows}


def validate_ground_truth_signoff(out: Path, freeze: bool) -> str:
    expected = read_json(out / "snapshot/ground_truth_signoff_template.json")
    path = out / "ground_truth_signoff.json"
    if not path.is_file():
        raise ValueError(f"Independent ground-truth signoff required before paid review calls: {path}")
    actual = read_json(path)
    if not actual.get("reviewer_name", "").strip() or not actual.get("reviewed_utc", "").strip():
        raise ValueError("Ground-truth signoff needs an identified reviewer and UTC date")
    reviewed_at = datetime.fromisoformat(actual["reviewed_utc"])
    if reviewed_at.tzinfo is None:
        raise ValueError("Ground-truth signoff date needs a UTC offset")
    if len(actual.get("cases", [])) != 24:
        raise ValueError("Ground-truth signoff must cover all 24 cases")
    identity = ("item", "cve_id", "diff_sha256", "truth_sha256",
                "recorded_intro_commit", "recorded_fix_commit")
    for wanted, observed in zip(expected["cases"], actual["cases"]):
        if any(observed.get(field) != wanted[field] for field in identity):
            raise ValueError(f"Ground-truth signoff case or hash changed: {wanted['item']}")
        if (observed.get("mechanism_confirmed") is not True
                or observed.get("supplied_revision_confirmed") is not True
                or not observed.get("evidence_note", "").strip()):
            raise ValueError(f"Ground-truth signoff incomplete: {wanted['item']}")
    digest = sha(path.read_bytes())
    hash_path = out / "ground_truth_signoff.sha256"
    if hash_path.exists() and hash_path.read_text().strip() != digest:
        raise ValueError("Ground-truth signoff changed after the first paid call")
    if freeze and not hash_path.exists():
        hash_path.write_text(digest + "\n")
    return digest


def prepare(out: Path) -> None:
    protocol, items = source_inventory()
    if out.exists() and any(out.iterdir()):
        raise ValueError(f"Output directory already contains files: {out}")
    snapshot = out / "snapshot"
    snapshot.mkdir(parents=True, exist_ok=True)
    shutil.copy2(HERE / "README.md", snapshot / "README.md")
    shutil.copy2(PROTOCOL, snapshot / "protocol.json")
    shutil.copy2(Path(__file__), snapshot / "study.py")
    for arm, source in protocol["prompts"].items():
        shutil.copy2(STUDY / source, snapshot / f"{arm}.txt")
    shutil.copy2(STUDY / "data/prompt-followup/truth.json", snapshot / "truth.json")
    shutil.copy2(STUDY / "data/original/rubric.md", snapshot / "rubric.md")
    write_json(snapshot / "inventory.json", items)
    write_json(snapshot / "control_provenance.json", control_provenance())
    write_json(snapshot / "ground_truth_signoff_template.json", make_ground_truth_template(items))
    (snapshot / "inputs").mkdir()
    for row in items:
        shutil.copy2(STUDY / "inputs" / f"{row['item']}.diff",
                     snapshot / "inputs" / f"{row['item']}.diff")
    jobs = make_jobs(protocol, items)
    request_dir = out / "review_requests"
    request_dir.mkdir()
    for job in jobs:
        diff = (snapshot / "inputs" / f"{job['item']}.diff").read_text().rstrip("\n")
        template = (snapshot / f"{job['arm']}.txt").read_text()
        prompt = template.replace("{diff}", diff)
        assert "CVE-" not in prompt and "{diff}" not in prompt
        request = {"model": protocol["models"][job["model"]],
                   "max_tokens": protocol["review_max_tokens"],
                   "messages": [{"role": "user", "content": prompt}]}
        write_json(request_dir / f"{job['id']}.json", request)
    write_json(out / "jobs.json", jobs)
    checksums = {}
    for path in sorted(snapshot.rglob("*")) + sorted(request_dir.glob("*.json")) + [out / "jobs.json"]:
        if path.is_file():
            checksums[str(path.relative_to(out))] = sha(path.read_bytes())
    write_json(out / "lock.json", {"created_utc": utc_now(),
                                    "protocol": "matched two-prompt core",
                                    "expected_review_calls": 408,
                                    "expected_judge_calls": 408,
                                    "file_sha256": checksums})
    print(f"Prepared {out}: 24 cases, 10 controls, 15 checkpoint calls, 393 later calls")


def load_prepared(out: Path) -> tuple[dict, list[dict]]:
    lock = read_json(out / "lock.json")
    for rel, expected in lock["file_sha256"].items():
        path = out / rel
        if not path.is_file() or sha(path.read_bytes()) != expected:
            raise ValueError(f"Frozen input changed or is missing: {path}")
    if sha(Path(__file__).read_bytes()) != lock["file_sha256"]["snapshot/study.py"]:
        raise ValueError("Runner changed after prepare; start a new output directory")
    protocol = read_json(out / "snapshot/protocol.json")
    jobs = read_json(out / "jobs.json")
    assert len(jobs) == lock["expected_review_calls"] == 408
    return protocol, jobs


def result_paths(out: Path, kind: str, job_id: str) -> tuple[Path, Path]:
    folder = out / kind / job_id
    return folder, folder / "result.json"


def response_text(response: dict) -> str:
    return "".join(part.get("text", "") for part in response.get("content", [])
                   if part.get("type") == "text")


def parsed_judgment(item_kind: str, text: str) -> dict | None:
    lines = [line.strip().strip("` ").strip("* ").strip() for line in text.splitlines()
             if line.strip() and line.strip() != "```"]
    if item_kind == "case":
        label_lines = [line for line in lines if line.startswith("LABEL:")]
        if len(label_lines) != 1 or lines[-1] != label_lines[0]:
            return None
        match = re.fullmatch(r"LABEL:\s*(Caught|Partial|Missed)", lines[-1])
        return {"label": match.group(1)} if match else None
    summaries = [re.fullmatch(r"SUMMARY:\s*findings=(\d+)\s+false=(\d+)\s+speculative=(\d+)\s+plausible=(\d+)", line)
                 for line in lines if line.startswith("SUMMARY:")]
    others = [re.fullmatch(r"OTHER:\s*correctness=(\d+)\s+maintainability=(\d+)", line)
              for line in lines if line.startswith("OTHER:")]
    if len(summaries) != 1 or len(others) != 1 or not summaries[0] or not others[0]:
        return None
    finding_lines = [line for line in lines if line.startswith("FINDING |")
                     and line != "FINDING | none"]
    none_lines = [line for line in lines if line == "FINDING | none"]
    if (finding_lines and none_lines) or len(none_lines) > 1:
        return None
    values = dict(zip(("findings", "false", "speculative", "plausible"),
                      (int(x) for x in summaries[0].groups())))
    values.update(zip(("correctness", "maintainability"),
                      (int(x) for x in others[0].groups())))
    parsed_lines = [re.fullmatch(r"FINDING\s*\|\s*([^|]+)\|\s*severity=([^|]+)\|\s*class=(FALSE|SPECULATIVE|PLAUSIBLE)\s*\|\s*(.+)", line)
                    for line in finding_lines]
    if any(match is None for match in parsed_lines):
        return None
    classes = Counter(match.group(3) for match in parsed_lines)
    values["false_severities"] = [match.group(2).strip() for match in parsed_lines
                                  if match.group(3) == "FALSE"]
    if (values["findings"] != len(finding_lines)
            or values["false"] != classes["FALSE"]
            or values["speculative"] != classes["SPECULATIVE"]
            or values["plausible"] != classes["PLAUSIBLE"]
            or len(values["false_severities"]) != values["false"]
            or (values["findings"] == 0 and len(none_lines) != 1)):
        return None
    return values


def check_result(out: Path, kind: str, job: dict, protocol: dict) -> dict | None:
    folder, result_file = result_paths(out, kind, job["id"])
    if not result_file.exists():
        return None
    result = read_json(result_file)
    attempt = result["attempt"]
    body = folder / f"attempt-{attempt:03}.body"
    meta = folder / f"attempt-{attempt:03}.meta.json"
    raw = body.read_bytes()
    response = json.loads(raw)
    data = read_json(meta)
    expected = (protocol["models"][job["model"]] if kind == "reviews" else JUDGE_MODEL)
    if data["status"] != "ok" or response.get("model") != expected:
        raise ValueError(f"Invalid served model or result: {kind}/{job['id']}")
    if response.get("stop_reason") != "end_turn" or not response_text(response).strip():
        raise ValueError(f"Incomplete response: {kind}/{job['id']}")
    if sha(raw) != data["response_sha256"] or response.get("id") != data["response_id"]:
        raise ValueError(f"Response hash or ID changed: {kind}/{job['id']}")
    usage = response.get("usage", {})
    if ("cache_creation_input_tokens" not in usage or "cache_read_input_tokens" not in usage
            or usage["cache_creation_input_tokens"] != 0 or usage["cache_read_input_tokens"] != 0):
        raise ValueError(f"Cache counters missing or nonzero: {kind}/{job['id']}")
    if kind == "judgments" and parsed_judgment(job["kind"], response_text(response)) is None:
        raise ValueError(f"Unparseable judgment: {job['id']}")
    return {"response": response, "meta": data, "text": response_text(response),
            "parsed": parsed_judgment(job["kind"], response_text(response)) if kind == "judgments" else None}


def api_call(out: Path, kind: str, job: dict, request_path: Path, protocol: dict,
             key: str) -> None:
    folder, result_file = result_paths(out, kind, job["id"])
    folder.mkdir(parents=True, exist_ok=True)
    request_bytes = request_path.read_bytes()
    request = json.loads(request_bytes)
    assert set(request) == {"model", "max_tokens", "messages"}
    assert len(request["messages"]) == 1 and request["messages"][0]["role"] == "user"
    previous = [int(match.group(1)) for path in folder.glob("attempt-*")
                if (match := re.fullmatch(r"attempt-(\d+)\.(?:body|meta\.json)", path.name))]
    attempt = max(previous, default=0) + 1
    body_path = folder / f"attempt-{attempt:03}.body"
    meta_path = folder / f"attempt-{attempt:03}.meta.json"
    started = utc_now()
    clock = time.monotonic()
    status = "error"
    http_status = None
    error = None
    response = None
    raw = b""
    req = urllib.request.Request(API_URL, data=request_bytes,
        headers={"x-api-key": key, "anthropic-version": protocol["api_version"],
                 "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=900) as reply:
            http_status = reply.status
            raw = reply.read()
        response = json.loads(raw)
        expected = request["model"]
        usage = response.get("usage", {})
        valid = (response.get("model") == expected and response.get("stop_reason") == "end_turn"
                 and bool(response_text(response).strip())
                 and usage.get("cache_creation_input_tokens") == 0
                 and usage.get("cache_read_input_tokens") == 0)
        if kind == "judgments":
            valid = valid and parsed_judgment(job["kind"], response_text(response)) is not None
        status = "ok" if valid else "invalid_response"
    except urllib.error.HTTPError as exc:
        http_status = exc.code
        raw = exc.read()
        error = str(exc)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        error = str(exc)
    with body_path.open("xb") as file:
        file.write(raw)
    meta = {"job_id": job["id"], "kind": kind, "attempt": attempt, "status": status,
            "http_status": http_status, "started_utc": started,
            "latency_seconds": round(time.monotonic() - clock, 3),
            "api_version": protocol["api_version"],
            "request_sha256": sha(request_bytes), "response_sha256": sha(raw),
            "response_id": response.get("id") if response else None,
            "requested_model": request["model"],
            "served_model": response.get("model") if response else None,
            "stop_reason": response.get("stop_reason") if response else None,
            "usage": response.get("usage") if response else None,
            "error": error}
    with meta_path.open("x") as file:
        file.write(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    if status != "ok":
        raise RuntimeError(f"{kind}/{job['id']} attempt {attempt}: {status}; details saved")
    write_json(result_file, {"attempt": attempt, "response_id": response["id"]})
    print(f"{kind} {job['id']} ok {meta['latency_seconds']}s", flush=True)


def run_reviews(out: Path, phase: str, execute: bool) -> None:
    protocol, jobs = load_prepared(out)
    if phase == "rest":
        first = [job for job in jobs if job["phase"] == "checkpoint"]
        if not all(check_result(out, "reviews", job, protocol) and
                   check_result(out, "judgments", job, protocol) for job in first):
            raise ValueError("Complete and provisionally score all 15 checkpoint reviews first")
        checkpoint_report(out, protocol, first)
    pending = [job for job in jobs if job["phase"] == phase
               and check_result(out, "reviews", job, protocol) is None]
    print(f"{phase}: {len(pending)} review calls pending")
    if not execute:
        return
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ValueError("Set ANTHROPIC_API_KEY in the environment")
    validate_ground_truth_signoff(out, freeze=True)
    for job in pending:
        api_call(out, "reviews", job, out / "review_requests" / f"{job['id']}.json",
                 protocol, key)


def judge(out: Path, phase: str, execute: bool) -> None:
    protocol, jobs = load_prepared(out)
    targets = [job for job in jobs if job["phase"] == phase]
    reviews = {job["id"]: check_result(out, "reviews", job, protocol) for job in targets}
    if any(value is None for value in reviews.values()):
        raise ValueError(f"All {len(targets)} {phase} reviews must be complete before judging")
    if phase == "rest" and not all(check_result(out, "judgments", job, protocol)
                                   for job in jobs if job["phase"] == "checkpoint"):
        raise ValueError("Score all 15 checkpoint reviews before judging the rest")
    truth = read_json(out / "snapshot/truth.json")
    request_dir = out / "judge_requests"
    request_dir.mkdir(exist_ok=True)
    for job in targets:
        path = request_dir / f"{job['id']}.json"
        diff = (out / "snapshot/inputs" / f"{job['item']}.diff").read_text().rstrip("\n")
        review = reviews[job["id"]]["text"].strip()
        prompt = (DETECTION_JUDGE.format(rubric=RUBRIC, truth=truth[job["item"]], review=review)
                  if job["kind"] == "case" else CONTROL_JUDGE.format(diff=diff, review=review))
        request = {"model": JUDGE_MODEL, "max_tokens": protocol["judge_max_tokens"],
                   "messages": [{"role": "user", "content": prompt}]}
        proposed = (json.dumps(request, indent=2, ensure_ascii=False) + "\n").encode()
        if path.exists():
            if path.read_bytes() != proposed:
                raise ValueError(f"Judge request changed: {path}")
        else:
            path.write_bytes(proposed)
    pending = [job for job in targets if check_result(out, "judgments", job, protocol) is None]
    print(f"{phase}: {len(pending)} judge calls pending")
    if execute:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError("Set ANTHROPIC_API_KEY in the environment")
        for job in pending:
            api_call(out, "judgments", job, request_dir / f"{job['id']}.json", protocol, key)
    if phase == "checkpoint" and all(check_result(out, "judgments", job, protocol)
                                     for job in targets):
        checkpoint_report(out, protocol, targets)


def checkpoint_report(out: Path, protocol: dict, targets: list[dict]) -> None:
    inventory = {row["item"]: row for row in read_json(out / "snapshot/inventory.json")}
    rows = []
    for item in protocol["first_haiku_generic_items"]:
        chosen = sorted((job for job in targets if job["item"] == item), key=lambda job: job["run"])
        labels = [check_result(out, "judgments", job, protocol)["parsed"]["label"]
                  for job in chosen]
        rows.append({"item": item, "cve_id": inventory[item]["cve_id"],
                     "run_labels": labels, "case_score": majority(labels)})
    result = {"status": "provisional model-judged checkpoint; continue regardless of scores",
              "created_utc": utc_now(), "caught": sum(row["case_score"] == "Caught" for row in rows),
              "denominator": 5, "cases": rows}
    path = out / "checkpoint_summary.json"
    if path.exists():
        previous = read_json(path)
        previous.pop("created_utc", None)
        comparison = dict(result)
        comparison.pop("created_utc", None)
        if previous != comparison:
            raise ValueError("Checkpoint score changed after being recorded")
    else:
        write_json(path, result)
    print(f"Checkpoint provisionally Caught {result['caught']}/5; "
          f"continue with frozen protocol regardless of this score")


def verify(out: Path, complete: bool) -> None:
    protocol, jobs = load_prepared(out)
    if complete:
        if not (out / "ground_truth_signoff.sha256").is_file():
            raise ValueError("Frozen ground-truth signoff hash is missing")
        validate_ground_truth_signoff(out, freeze=False)
    totals = {}
    response_ids = set()
    for kind in ("reviews", "judgments"):
        found = 0
        for job in jobs:
            item = check_result(out, kind, job, protocol)
            if item:
                found += 1
                response_id = item["response"]["id"]
                if response_id in response_ids:
                    raise ValueError(f"Duplicate response ID: {response_id}")
                response_ids.add(response_id)
                req = out / ("review_requests" if kind == "reviews" else "judge_requests") / f"{job['id']}.json"
                meta = item["meta"]
                if sha(req.read_bytes()) != meta["request_sha256"]:
                    raise ValueError(f"Request changed: {req}")
        totals[kind] = found
        if complete and found != 408:
            raise ValueError(f"Only {found}/408 {kind} complete")
    print(f"Verified frozen plan and {totals['reviews']}/408 reviews, "
          f"{totals['judgments']}/408 judgments; completed calls have zero cache tokens")


def packet(out: Path) -> None:
    verify(out, complete=True)
    protocol, jobs = load_prepared(out)
    truth = read_json(out / "snapshot/truth.json")
    controls = read_json(out / "snapshot/control_provenance.json")
    rng = random.Random(protocol["shuffle_seed"] + 1)
    shuffled = jobs[:]
    rng.shuffle(shuffled)
    blind = out / "packet/blind"
    private = out / "packet/private"
    blind.mkdir(parents=True, exist_ok=True)
    private.mkdir(parents=True, exist_ok=True)
    with (blind / "reviews.jsonl").open("w") as reviews_file, \
         (private / "model_judgments.jsonl").open("w") as judgments_file, \
         (private / "key.csv").open("w", newline="") as key_file, \
         (blind / "human_scores_template.csv").open("w", newline="") as template_file:
        key_writer = csv.DictWriter(key_file, fieldnames=("review_id", "job_id", "item", "kind",
                                                    "model", "arm", "run", "cve_id"))
        score_writer = csv.DictWriter(template_file, fieldnames=("review_id", "reviewer_name",
            "reviewed_utc", "label",
            "false_count", "speculative_count", "plausible_count", "false_severities",
            "correctness_count", "maintainability_count", "reason"))
        key_writer.writeheader()
        score_writer.writeheader()
        inventory = {row["item"]: row for row in read_json(out / "snapshot/inventory.json")}
        for index, job in enumerate(shuffled, 1):
            review_id = f"R{index:04}"
            review = check_result(out, "reviews", job, protocol)
            judgment = check_result(out, "judgments", job, protocol)
            record = {"review_id": review_id, "item": job["item"], "kind": job["kind"],
                      "diff": (out / "snapshot/inputs" / f"{job['item']}.diff").read_text(),
                      "ground_truth": truth[job["item"]] if job["kind"] == "case" else
                                      "This change is not known to introduce a vulnerability.",
                      "review": review["text"]}
            if job["kind"] == "control":
                record["historical_source"] = controls[job["item"]]
            reviews_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            judgments_file.write(json.dumps({"review_id": review_id,
                "model_judgment": judgment["text"]}, ensure_ascii=False) + "\n")
            key_writer.writerow({"review_id": review_id, "job_id": job["id"],
                "item": job["item"], "kind": job["kind"], "model": job["model"],
                "arm": job["arm"], "run": job["run"],
                "cve_id": inventory[job["item"]].get("cve_id", "")})
            score_writer.writerow({"review_id": review_id})
    print(f"Created blinded packet at {blind}; keep {private / 'key.csv'} separate")


def majority(labels: list[str]) -> str:
    assert len(labels) == 3 and all(x in ("Caught", "Partial", "Missed") for x in labels)
    for label in ("Caught", "Partial", "Missed"):
        if labels.count(label) >= 2:
            return label
    return "Partial"


def summarize(out: Path, human_csv: Path | None) -> None:
    verify(out, complete=True)
    protocol, jobs = load_prepared(out)
    overrides = {}
    human_evidence = None
    if human_csv:
        if not (out / "packet/private/key.csv").exists():
            raise ValueError("Create the blinded packet before importing human scores")
        key = {row["review_id"]: row["job_id"] for row in
               csv.DictReader((out / "packet/private/key.csv").open())}
        supplied = human_csv.read_bytes()
        digest = sha(supplied)
        retained = out / "human_adjudication" / f"{digest}.csv"
        retained.parent.mkdir(exist_ok=True)
        if not retained.exists():
            with retained.open("xb") as file:
                file.write(supplied)
        human_evidence = {"sha256": digest, "path": str(retained.relative_to(out))}
        for row in csv.DictReader(io.StringIO(supplied.decode("utf-8-sig"))):
            if row["review_id"] not in key:
                raise ValueError(f"Unknown review ID: {row['review_id']}")
            if row["reason"].strip():
                if not row["reviewer_name"].strip() or not row["reviewed_utc"].strip():
                    raise ValueError(f"Human reviewer and UTC date required: {row['review_id']}")
                try:
                    reviewed_at = datetime.fromisoformat(row["reviewed_utc"])
                except ValueError as exc:
                    raise ValueError(f"Invalid human review date: {row['review_id']}") from exc
                if reviewed_at.tzinfo is None:
                    raise ValueError(f"Human review date needs UTC offset: {row['review_id']}")
                overrides[key[row["review_id"]]] = row
    rows = {}
    for job in jobs:
        judgment = check_result(out, "judgments", job, protocol)
        parsed = dict(judgment["parsed"])
        override = overrides.get(job["id"])
        if override:
            if job["kind"] == "case":
                if override["label"] not in ("Caught", "Partial", "Missed"):
                    raise ValueError(f"Invalid human label: {job['id']}")
                parsed["label"] = override["label"]
            else:
                for column in ("false", "speculative", "plausible"):
                    value = override[column + "_count"].strip()
                    if not value or int(value) < 0:
                        raise ValueError(f"Missing or negative human {column} count: {job['id']}")
                    parsed[column] = int(value)
                parsed["findings"] = sum(parsed[column] for column in
                                         ("false", "speculative", "plausible"))
                parsed["false_severities"] = [value.strip() for value in
                    override["false_severities"].split(";") if value.strip()]
                if len(parsed["false_severities"]) != parsed["false"]:
                    raise ValueError(f"Provide one severity per human false claim: {job['id']}")
                for column in ("correctness", "maintainability"):
                    value = override[column + "_count"].strip()
                    if value:
                        if int(value) < 0:
                            raise ValueError(f"Negative human {column} count: {job['id']}")
                        parsed[column] = int(value)
        rows[job["id"]] = parsed
    cases = []
    controls = []
    inventory = {row["item"]: row for row in read_json(out / "snapshot/inventory.json")}
    for model in protocol["models"]:
        for arm in protocol["prompts"]:
            for item in [f"item_{i:02}" for i in range(1, 25)]:
                labels = [rows[f"{item}__{model}__{arm}__run{i}"]["label"] for i in (1, 2, 3)]
                cases.append({"item": item, "cve_id": inventory[item]["cve_id"],
                              "model": model, "arm": arm,
                              "runs": "/".join(labels), "score": majority(labels),
                              "mixed": len(set(labels)) > 1})
            for item in [f"BENIGN-{i:02}" for i in range(1, 11)]:
                for run in (1, 2, 3):
                    job_id = f"{item}__{model}__{arm}__run{run}"
                    parsed = rows[job_id]
                    review_words = len(check_result(out, "reviews",
                        next(job for job in jobs if job["id"] == job_id), protocol)["text"].split())
                    controls.append({"item": item, "model": model, "arm": arm,
                                     "run": run, "review_words": review_words, **parsed})
    by_arm = {}
    for model in protocol["models"]:
        for arm in protocol["prompts"]:
            key = f"{model}_{arm}"
            c = [row for row in cases if row["model"] == model and row["arm"] == arm]
            b = [row for row in controls if row["model"] == model and row["arm"] == arm]
            review_meta = [check_result(out, "reviews", job, protocol)["meta"] for job in jobs
                           if job["model"] == model and job["arm"] == arm]
            judge_meta = [check_result(out, "judgments", job, protocol)["meta"] for job in jobs
                          if job["model"] == model and job["arm"] == arm]
            false_severities = Counter(severity for row in b if row["false"] > 0
                                       for severity in row["false_severities"])
            by_arm[key] = {
                "cases": {label: sum(row["score"] == label for row in c)
                          for label in ("Caught", "Partial", "Missed")},
                "checkpoint_caught": sum(row["score"] == "Caught" for row in c
                                         if row["item"] in protocol["first_haiku_generic_items"]),
                "checkpoint_denominator": 5,
                "remaining_caught": sum(row["score"] == "Caught" for row in c
                                        if row["item"] not in protocol["first_haiku_generic_items"]),
                "remaining_denominator": 19,
                "mixed_label_cases": sum(row["mixed"] for row in c),
                "false_alarm_reviews": sum(row["false"] > 0 for row in b),
                "false_alarm_controls": sum(any(row["false"] > 0 for row in b
                                              if row["item"] == item)
                                            for item in {row["item"] for row in b}),
                "false_security_findings": sum(row["false"] for row in b),
                "false_severity_counts": dict(false_severities),
                "speculative_questions": sum(row["speculative"] for row in b),
                "security_findings": sum(row["findings"] for row in b),
                "mean_control_review_words": round(statistics.mean(row["review_words"]
                                                                  for row in b), 1),
                "review_input_tokens": sum((row["usage"] or {}).get("input_tokens", 0)
                                           for row in review_meta),
                "review_output_tokens": sum((row["usage"] or {}).get("output_tokens", 0)
                                            for row in review_meta),
                "median_review_latency_seconds": statistics.median(row["latency_seconds"]
                                                                    for row in review_meta),
                "judge_input_tokens": sum((row["usage"] or {}).get("input_tokens", 0)
                                          for row in judge_meta),
                "judge_output_tokens": sum((row["usage"] or {}).get("output_tokens", 0)
                                           for row in judge_meta),
                "median_judge_latency_seconds": statistics.median(row["latency_seconds"]
                                                                   for row in judge_meta),
            }
    prompt_changes = {}
    for model in protocol["models"]:
        generic = {row["cve_id"] for row in cases if row["model"] == model
                   and row["arm"] == "generic" and row["score"] == "Caught"}
        security = {row["cve_id"] for row in cases if row["model"] == model
                    and row["arm"] == "security" and row["score"] == "Caught"}
        prompt_changes[model] = {"gained": sorted(security - generic),
                                 "retained": sorted(security & generic),
                                 "lost": sorted(generic - security)}
    report = {"status": "provisional until independent human signoff",
              "human_override_rows_supplied": len(overrides), "total_review_runs": 408,
              "human_scoring_evidence": human_evidence,
              "by_arm": by_arm, "prompt_changes": prompt_changes,
              "case_rows": cases, "control_rows": controls,
              "generated_utc": utc_now()}
    write_json(out / "summary.json", report)
    print(f"Saved provisional summary to {out / 'summary.json'}; "
          f"{len(overrides)}/408 run judgments have identified human overrides")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "prepare", "run", "judge", "verify", "packet", "summarize"))
    parser.add_argument("--out", type=Path, help="Dedicated run directory, preferably build/openemr-next-run")
    parser.add_argument("--phase", choices=("checkpoint", "rest"), help="Required for run and judge")
    parser.add_argument("--execute", action="store_true", help="Permit paid API calls")
    parser.add_argument("--complete", action="store_true", help="Require all reviews and judgments")
    parser.add_argument("--human-csv", type=Path, help="Optional filled human_scores_template.csv")
    args = parser.parse_args()
    if args.action == "plan":
        protocol, items = source_inventory()
        jobs = make_jobs(protocol, items)
        print("Frozen sources valid: 24 cases, 10 controls, 2 models, 2 prompts, 3 runs")
        print("Checkpoint first:", ", ".join(protocol["first_haiku_generic_items"]))
        print("Review calls:", len(jobs), "(15 checkpoint, 393 rest)")
        print("No API call made")
        return
    if args.out is None:
        parser.error("--out is required except for plan")
    out = args.out.resolve()
    if args.action == "prepare":
        prepare(out)
    elif args.action == "run":
        if not args.phase:
            parser.error("run requires --phase checkpoint or --phase rest")
        run_reviews(out, args.phase, args.execute)
    elif args.action == "judge":
        if not args.phase:
            parser.error("judge requires --phase checkpoint or --phase rest")
        judge(out, args.phase, args.execute)
    elif args.action == "verify":
        verify(out, args.complete)
    elif args.action == "packet":
        packet(out)
    elif args.action == "summarize":
        summarize(out, args.human_csv)


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
