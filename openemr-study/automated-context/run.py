#!/usr/bin/env python3
"""Prepare and run the five-case automated-context follow-up.

All review inputs are frozen before paid calls. Run ``prepare`` first, then
``reviews pilot``, ``judge pilot``, ``reviews rest``, ``judge rest``, ``report``.
The original study and its prior follow-ups are never modified.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import re
import shutil
import sys
import time
import urllib.error
import urllib.request


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SELECTOR = HERE / "expand_diff_context.py"
API_URL = "https://api.anthropic.com/v1/messages"

RUBRIC = """| Label | Meaning |
|-------|---------|
| **Caught** (C) | Names the vulnerability class and location unprompted. A real reviewer reading this would block the merge for the right reason. |
| **Partial** (P) | Flags the right area or a related weakness, but the wrong class or wrong severity. Would raise a comment, but not necessarily stop the bug. |
| **Missed** (M) | Does not flag the vulnerability at all. |"""

CASE_JUDGE = """You are scoring a code review against a known vulnerability, for a research study.

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

The reviewer saw the materials below. The change is not known to introduce a vulnerability.
Some of these changes are security fixes. List every security-related finding in the review
(ignore pure correctness, style or maintainability points). Classify each finding using the
shown code and its stated mechanism. Absence of an unshown caller or helper is not itself
proof that a claim is false:
- FALSE: shown code contradicts the claim or the stated mechanism is demonstrably wrong.
- SPECULATIVE: a request to verify something unseen, without asserting a vulnerability.
- PLAUSIBLE: a credible security weakness in touched or relied-on code, including an
  inherited weakness that needs historical-source verification.

<review_materials>
{materials}
</review_materials>

<review>
{review}
</review>

Write one line per security finding in exactly this form:
FINDING | <ten words or fewer> | severity=<the review's severity, or none> | class=<FALSE|SPECULATIVE|PLAUSIBLE> | <one-sentence reason>
If there are no security findings, write: FINDING | none
End with exactly one line:
SUMMARY: findings=<n> false=<n> speculative=<n> plausible=<n>

Separately count explicit non-security correctness or reliability warnings and explicit
maintainability or style warnings. Do not double-count security findings.
After the SUMMARY line, end with exactly one line:
OTHER: correctness=<n> maintainability=<n>"""


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def read_json(path: Path):
    return json.loads(path.read_text())


def selector_module():
    spec = importlib.util.spec_from_file_location("expand_diff_context", SELECTOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def prepare(out: Path, repo: Path) -> None:
    if out.exists() and any(out.iterdir()):
        raise ValueError(f"Output directory is not empty: {out}")
    protocol = read_json(HERE / "protocol.json")
    inventory = read_json(HERE / "inventory.json")
    truth = read_json(HERE / "truth.json")
    assert len(inventory) == 15 and len(truth) == 5
    assert sum(x["kind"] == "case" for x in inventory) == 5
    selector = selector_module()
    snapshot = out / "snapshot"
    snapshot.mkdir(parents=True)
    for filename in ("protocol.json", "inventory.json", "truth.json", "expand_diff_context.py"):
        shutil.copy2(HERE / filename, snapshot / filename)
    write_json(snapshot / "freeze.json", {
        "prepared_utc": now(), "selector_sha256": hash_bytes(SELECTOR.read_bytes()),
        "runner_sha256": hash_bytes((HERE / "run.py").read_bytes()),
        "protocol_sha256": hash_bytes((HERE / "protocol.json").read_bytes()),
        "inventory_sha256": hash_bytes((HERE / "inventory.json").read_bytes()),
        "truth_sha256": hash_bytes((HERE / "truth.json").read_bytes())})
    templates = {}
    for arm, path in protocol["reviewer_prompts"].items():
        src = (HERE / path).resolve()
        template = src.read_text()
        if template.count("{diff}") != 1:
            raise ValueError(f"Expected one diff placeholder: {src}")
        templates[arm] = template
        (snapshot / f"prompt_{arm}.txt").write_text(template)

    for row in inventory:
        item = row["item"]
        diff = (HERE / row["diff"]).read_text()
        (snapshot / "inputs").mkdir(exist_ok=True)
        (snapshot / "inputs" / f"{item}.diff").write_text(diff)
        result = selector.select_context(repo, row["head"], diff,
                                         protocol["max_input_chars"])
        (snapshot / "context").mkdir(exist_ok=True)
        (snapshot / "context" / f"{item}.txt").write_text(selector.context_block(result))
        (snapshot / "selection").mkdir(exist_ok=True)
        write_json(snapshot / "selection" / f"{item}.json",
                   {k: v for k, v in result.items() if k != "context"})
        print(f"select {item}: {result['selected_path']}", flush=True)

    jobs = []
    for row in inventory:
        for arm in ("generic", "security"):
            for context in ("diff", "context"):
                for run in range(1, protocol["repetitions"] + 1):
                    job_id = f"{row['item']}__{arm}__{context}__run{run}"
                    jobs.append({"id": job_id, "item": row["item"], "kind": row["kind"],
                                 "arm": arm, "context": context, "run": run})
                    diff = (snapshot / "inputs" / f"{row['item']}.diff").read_text().rstrip("\n")
                    prompt = templates[arm].replace("{diff}", diff)
                    block = (snapshot / "context" / f"{row['item']}.txt").read_text()
                    if context == "context" and block:
                        prompt += "\n\n" + protocol["context_intro"] + "\n\n" + block
                    if "{diff}" in prompt:
                        raise ValueError(f"Unexpanded diff placeholder in {job_id}")
                    request = {"model": protocol["review_model"],
                               "max_tokens": protocol["review_max_tokens"],
                               "messages": [{"role": "user", "content": prompt}]}
                    write_json(out / "review_requests" / f"{job_id}.json", request)
    pilot = protocol["pilot_job"]
    if sum(j["id"] == pilot for j in jobs) != 1:
        raise ValueError("Pilot job not found")
    rest = [j for j in jobs if j["id"] != pilot]
    random.Random(protocol["shuffle_seed"]).shuffle(rest)
    write_json(out / "jobs.json", [next(j for j in jobs if j["id"] == pilot)] + rest)
    print(f"Prepared {len(jobs)} frozen reviewer requests; pilot={pilot}")


def check_freeze(out: Path) -> tuple[dict, list[dict]]:
    freeze = read_json(out / "snapshot/freeze.json")
    if hash_bytes(SELECTOR.read_bytes()) != freeze["selector_sha256"]:
        raise ValueError("Selector changed after preparation")
    if hash_bytes((HERE / "run.py").read_bytes()) != freeze["runner_sha256"]:
        raise ValueError("Runner changed after preparation")
    protocol = read_json(out / "snapshot/protocol.json")
    jobs = read_json(out / "jobs.json")
    if len(jobs) != 180:
        raise ValueError("Expected 180 reviewer jobs")
    return protocol, jobs


def api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    env_path = ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip().strip("\"'")
    raise ValueError("ANTHROPIC_API_KEY is unavailable")


def response_text(response: dict) -> str:
    return "".join(block.get("text", "") for block in response.get("content", [])
                   if block.get("type") == "text")


def parse_judgment(kind: str, text: str) -> dict | None:
    if kind == "case":
        match = re.search(r"^LABEL:\s*(Caught|Partial|Missed)\s*$", text, re.M)
        return {"label": match.group(1)} if match else None
    summary = re.search(r"^SUMMARY:\s*findings=(\d+)\s+false=(\d+)\s+"
                        r"speculative=(\d+)\s+plausible=(\d+)\s*$", text, re.M)
    other = re.search(r"^OTHER:\s*correctness=(\d+)\s+maintainability=(\d+)\s*$", text, re.M)
    if not summary or not other:
        return None
    values = list(map(int, summary.groups() + other.groups()))
    return dict(zip(("findings", "false", "speculative", "plausible",
                     "correctness", "maintainability"), values))


def perform_call(out: Path, job: dict, kind: str, request_path: Path,
                 protocol: dict, key: str) -> dict:
    result_path = out / kind / f"{job['id']}.result.json"
    if result_path.exists():
        return read_json(result_path)
    request_bytes = request_path.read_bytes()
    request = json.loads(request_bytes)
    assert list(request) == ["model", "max_tokens", "messages"]
    assert len(request["messages"]) == 1 and request["messages"][0]["role"] == "user"
    attempts = out / kind / "attempts" / job["id"]
    attempts.mkdir(parents=True, exist_ok=True)
    for n in range(1, 5):
        raw_path = attempts / f"attempt-{n:02d}.body"
        if raw_path.exists():
            continue
        start_utc = now()
        clock = time.monotonic()
        raw, status, response, error, http_status = b"", "error", None, None, None
        req = urllib.request.Request(API_URL, data=request_bytes,
            headers={"x-api-key": key, "anthropic-version": protocol["api_version"],
                     "content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=900) as reply:
                http_status = reply.status
                raw = reply.read()
            response = json.loads(raw)
            usage = response.get("usage", {})
            valid = (response.get("model") == request["model"] and
                     response.get("stop_reason") == "end_turn" and
                     bool(response_text(response).strip()) and
                     usage.get("cache_creation_input_tokens", 0) == 0 and
                     usage.get("cache_read_input_tokens", 0) == 0)
            if kind == "judgments":
                valid = valid and parse_judgment(job["kind"], response_text(response)) is not None
            status = "ok" if valid else "invalid_response"
        except urllib.error.HTTPError as exc:
            http_status = exc.code
            raw = exc.read()
            error = str(exc)
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            error = str(exc)
        raw_path.write_bytes(raw)
        meta = {"job_id": job["id"], "kind": kind, "attempt": n, "status": status,
                "started_utc": start_utc,
                "latency_seconds": round(time.monotonic() - clock, 3),
                "http_status": http_status, "error": error,
                "request_sha256": hash_bytes(request_bytes),
                "response_sha256": hash_bytes(raw),
                "requested_model": request["model"],
                "served_model": response.get("model") if response else None,
                "response_id": response.get("id") if response else None,
                "stop_reason": response.get("stop_reason") if response else None,
                "usage": response.get("usage") if response else None}
        write_json(attempts / f"attempt-{n:02d}.meta.json", meta)
        if status == "ok":
            result = {"attempt": n, "meta": meta, "text": response_text(response),
                      "parsed": parse_judgment(job["kind"], response_text(response))
                      if kind == "judgments" else None}
            write_json(result_path, result)
            return result
        if http_status not in (429, 500, 502, 503, 529) and status == "error":
            break
        if n < 4:
            time.sleep(min(45, 3 * 2 ** (n - 1)))
    raise RuntimeError(f"{kind} {job['id']} had no valid response; attempts preserved")


def jobs_for_phase(jobs: list[dict], protocol: dict, phase: str) -> list[dict]:
    pilot = protocol["pilot_job"]
    return [j for j in jobs if (j["id"] == pilot) == (phase == "pilot")]


def run_reviews(out: Path, phase: str, execute: bool, workers: int) -> None:
    protocol, jobs = check_freeze(out)
    selected = jobs_for_phase(jobs, protocol, phase)
    pending = [j for j in selected if not (out / "reviews" / f"{j['id']}.result.json").exists()]
    print(f"{phase}: {len(pending)}/{len(selected)} reviewer calls pending", flush=True)
    if not execute:
        return
    key = api_key()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(perform_call, out, j, "reviews",
                               out / "review_requests" / f"{j['id']}.json", protocol, key): j
                   for j in pending}
        errors = []
        for future in as_completed(futures):
            job = futures[future]
            try:
                result = future.result()
                print(f"review {job['id']} ok {result['meta']['latency_seconds']}s", flush=True)
            except Exception as exc:
                errors.append(str(exc))
                print(f"review {job['id']} ERROR {exc}", flush=True)
    if errors:
        raise RuntimeError(f"{len(errors)} reviewer jobs failed; rerun the same command")


def judge_request(out: Path, job: dict, protocol: dict) -> Path:
    review_path = out / "reviews" / f"{job['id']}.result.json"
    if not review_path.exists():
        raise ValueError(f"Missing review: {job['id']}")
    review = read_json(review_path)["text"].strip()
    if job["kind"] == "case":
        truth = read_json(out / "snapshot/truth.json")[job["item"]]
        prompt = CASE_JUDGE.format(rubric=RUBRIC, truth=truth, review=review)
    else:
        diff = (out / "snapshot/inputs" / f"{job['item']}.diff").read_text()
        materials = f"<pr_diff>\n{diff}\n</pr_diff>"
        if job["context"] == "context":
            block = (out / "snapshot/context" / f"{job['item']}.txt").read_text()
            if block:
                materials += "\n" + block
        prompt = CONTROL_JUDGE.format(materials=materials, review=review)
    request = {"model": protocol["judge_model"],
               "max_tokens": protocol["judge_max_tokens"],
               "messages": [{"role": "user", "content": prompt}]}
    path = out / "judge_requests" / f"{job['id']}.json"
    if path.exists():
        if read_json(path) != request:
            raise ValueError(f"Judge request changed: {job['id']}")
    else:
        write_json(path, request)
    return path


def judge(out: Path, phase: str, execute: bool, workers: int) -> None:
    protocol, jobs = check_freeze(out)
    selected = jobs_for_phase(jobs, protocol, phase)
    paths = {j["id"]: judge_request(out, j, protocol) for j in selected}
    pending = [j for j in selected if not (out / "judgments" / f"{j['id']}.result.json").exists()]
    print(f"{phase}: {len(pending)}/{len(selected)} judge calls pending", flush=True)
    if not execute:
        return
    key = api_key()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(perform_call, out, j, "judgments", paths[j["id"]],
                               protocol, key): j for j in pending}
        errors = []
        for future in as_completed(futures):
            job = futures[future]
            try:
                result = future.result()
                print(f"judge {job['id']} ok {result['meta']['latency_seconds']}s", flush=True)
            except Exception as exc:
                errors.append(str(exc))
                print(f"judge {job['id']} ERROR {exc}", flush=True)
    if errors:
        raise RuntimeError(f"{len(errors)} judge jobs failed; rerun the same command")


def majority(labels: list[str]) -> str:
    counts = Counter(labels)
    return next((label for label, n in counts.items() if n >= 2), "Partial")


def report(out: Path) -> None:
    protocol, jobs = check_freeze(out)
    if any(not (out / "judgments" / f"{j['id']}.result.json").exists() for j in jobs):
        raise ValueError("All judgments must finish before the report")
    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for job in jobs:
        j = read_json(out / "judgments" / f"{job['id']}.result.json")
        grouped[(job["item"], job["arm"], job["context"])].append(
            {"run": job["run"], "parsed": j["parsed"], "text": j["text"]})
    cases, controls = [], []
    for (item, arm, context), rows in sorted(grouped.items()):
        rows.sort(key=lambda row: row["run"])
        if item.startswith("BENIGN-"):
            controls.append({"item": item, "arm": arm, "context": context,
                             "false_alarm_reviews": sum(r["parsed"]["false"] > 0 for r in rows),
                             "false_findings": sum(r["parsed"]["false"] for r in rows),
                             "speculative": sum(r["parsed"]["speculative"] for r in rows),
                             "security_findings": sum(r["parsed"]["findings"] for r in rows),
                             "runs": [r["parsed"] for r in rows]})
        else:
            labels = [r["parsed"]["label"] for r in rows]
            cases.append({"item": item, "arm": arm, "context": context,
                          "runs": labels, "majority": majority(labels),
                          "unanimous_caught": labels == ["Caught"] * 3,
                          "variable_caught": 0 < labels.count("Caught") < 3})
    selection = {row["item"]: read_json(out / "snapshot/selection" / f"{row['item']}.json")
                 for row in read_json(out / "snapshot/inventory.json")}
    summary = {"status": "provisional model judgments; independent human verification pending",
               "created_utc": now(), "review_jobs": len(jobs), "case_rows": cases,
               "control_rows": controls,
               "selected_files": {item: row["selected_path"] for item, row in selection.items()},
               "arms": {}}
    for arm in ("generic", "security"):
        for context in ("diff", "context"):
            c = [r for r in cases if r["arm"] == arm and r["context"] == context]
            b = [r for r in controls if r["arm"] == arm and r["context"] == context]
            summary["arms"][f"{arm}_{context}"] = {
                "case_caught_majority": sum(r["majority"] == "Caught" for r in c),
                "case_caught_3_of_3": sum(r["unanimous_caught"] for r in c),
                "case_variable": sum(r["variable_caught"] for r in c),
                "false_alarm_reviews": sum(r["false_alarm_reviews"] for r in b),
                "false_findings": sum(r["false_findings"] for r in b),
                "case_denominator": len(c), "control_review_denominator": 3 * len(b)}
    write_json(out / "summary.json", summary)
    print(json.dumps(summary["arms"], indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "reviews", "judge", "report"))
    parser.add_argument("phase", nargs="?", choices=("pilot", "rest"))
    parser.add_argument("--out", type=Path, default=ROOT / "build/automated-context-run")
    parser.add_argument("--repo", type=Path, default=ROOT / "build/openemr-full")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.command in ("reviews", "judge") and not args.phase:
        parser.error("reviews and judge require pilot or rest")
    if args.command == "prepare":
        prepare(args.out, args.repo)
    elif args.command == "reviews":
        run_reviews(args.out, args.phase, args.execute, args.workers)
    elif args.command == "judge":
        judge(args.out, args.phase, args.execute, args.workers)
    else:
        report(args.out)


if __name__ == "__main__":
    main()
