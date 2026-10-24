#!/usr/bin/env python3
"""Focused Jev workflow experiment, reusing the existing public dataset and API."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import shutil
import time
import zipfile

from jev import ROOT, OpenRouterDecisionsClient, digest, load_env, read_json, write_json
from jev_followup import validate_partition, usage_summary, verify
from jev_workflow_policy import baseline_values, fingerprint, gate, percentages, probabilities, route

STUDY = ROOT / "jev-study/workflow-v1"
DATASET = ROOT / "jev-study/v2/dataset"
CODE = ["quadrant-tool/jev.py", "quadrant-tool/jev_followup.py", "quadrant-tool/jev_policy_v2.py",
        "quadrant-tool/jev_workflow_policy.py", "quadrant-tool/jev_workflow.py"]


def metadata(case, policy):
    """Explicit study fixtures, not real repository owner information."""
    return {"status": "simulation_fixture_not_real_ownership", "revision": case.get("revision") or case["diff_sha256"],
            "mandatory_actions": ["approve:peer", "check:tests"], "context_complete": False,
            "authorized_approvers": {a: ["fixture-" + a] for a, spec in policy["actions"].items() if spec["kind"] == "approval"},
            "check_producers": {a: ["fixture-ci"] for a, spec in policy["actions"].items() if spec["kind"] == "check"},
            "approved_ai_configs": {a: fingerprint(c) for a, c in policy["ai_configurations"].items()},
            "ai_producers": ["fixture-ai-runner"], "finding_producers": ["fixture-security-reviewer"],
            "finding_resolution_actors": ["fixture-appsec"], "triage_actors": ["fixture-security-triage"]}


def packet(destination):
    policy = read_json(STUDY / "policy.json")
    manifest = read_json(DATASET / "manifest.json")
    destination.mkdir(parents=True, exist_ok=False)
    forms = []
    for case in manifest["cases"]:
        payload = read_json(DATASET / case["input"])
        trusted = metadata(case, policy)
        # No source IDs, selection strata, old answers or model outputs.
        write_json(destination / (case["blind_id"] + ".json"), {
            "change": payload, "trusted_requirements": {
                "mandatory_actions": trusted["mandatory_actions"],
                "owner_availability": "All roles available in the simulated policy. Real staffing not evaluated.",
                "context_complete": "Determine from historical source; do not assume complete."}})
        forms.append({"case_id": case["blind_id"], "required_model_actions": None, "optional_model_actions": None,
                      "prohibited_model_actions": None, "required_workflow_actions": None,
                      "optional_workflow_actions": None, "prohibited_workflow_actions": None,
                      "context_complete": None, "rationale": "", "missing_context": [], "reviewed_at": ""})
    write_json(destination / "workflow-labels.json", {"status": "pending", "policy_sha256": fingerprint(policy),
               "reviewer": "", "reviewer_is_independent_human_security_reviewer": False,
               "saw_jev_outputs_or_previous_labels": None, "thresholds_approved_for_evaluation": False,
               "cases": sorted(forms, key=lambda x: x["case_id"])})
    shutil.copyfile(STUDY / "policy.json", destination / "policy.json")
    shutil.copyfile(STUDY / "ADJUDICATION.md", destination / "README.md")
    with zipfile.ZipFile(destination.parent / "workflow-adjudication-packet.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(destination.iterdir()):
            archive.write(path, "workflow-adjudication/" + path.name)
    return {"cases": len(forms), "human_adjudication": "pending"}


def labels_for(path, cases, policy):
    if path is None:
        return {"status": "pending_independent_human_security_review", "cases": []}
    doc = read_json(path)
    if (doc.get("status") != "adjudicated" or doc.get("policy_sha256") != fingerprint(policy)
            or not doc.get("reviewer", "").strip()
            or doc.get("reviewer_is_independent_human_security_reviewer") is not True
            or doc.get("saw_jev_outputs_or_previous_labels") is not False
            or doc.get("thresholds_approved_for_evaluation") is not True):
        raise ValueError("Independent security-reviewer adjudication and policy approval are incomplete")
    indexed = {r["case_id"]: r for r in doc["cases"]}
    if len(indexed) != len(doc["cases"]):
        raise ValueError("Duplicate label case")
    result = []
    universe = set(policy["actions"])
    for case in cases:
        row = indexed[case["blind_id"]]
        for scope in ("model", "workflow"):
            lists = [row[k + "_" + scope + "_actions"] for k in ("required", "optional", "prohibited")]
            if any(not isinstance(x, list) or len(x) != len(set(x)) for x in lists):
                raise ValueError("Complete required, optional and prohibited action lists")
            required, optional, prohibited = map(set, lists)
            if required & optional or required & prohibited or optional & prohibited or required | optional | prohibited != universe:
                raise ValueError("Labels must partition all workflow actions")
        if not set(policy["always"]) <= set(row["required_workflow_actions"]):
            raise ValueError("Human labels cannot omit mandatory actions")
        if not isinstance(row.get("context_complete"), bool) or not row.get("rationale", "").strip() or not row.get("reviewed_at", "").strip():
            raise ValueError("Missing context assessment or human rationale/date")
        if not row["context_complete"] and (not row["missing_context"] or "human:triage" not in row["required_workflow_actions"]):
            raise ValueError("Incomplete context requires recorded gaps and workflow triage")
        result.append({**row, "id": case["id"]})
    return {**doc, "status": "human_attested_not_identity_verified", "cases": result}


def prepare(workspace, partition, labels=None):
    manifest = read_json(DATASET / "manifest.json")
    validate_partition(manifest)
    cases = [c for c in manifest["cases"] if c["partition"] == partition]
    policy, questions, protocol = (read_json(STUDY / f"{name}.json") for name in ("policy", "questions", "protocol"))
    if protocol["runs"] != 3 or not re.fullmatch(r"typesafe/jev-[0-9][a-zA-Z0-9.\-]*", protocol["model"]):
        raise ValueError("Use three requests per case and an explicit Jev model version")
    if set(questions) != set(policy["thresholds"]):
        raise ValueError("Question IDs and category thresholds differ")
    for name in ("spending_limit_usd", "per_request_reservation_usd"):
        if not valid_cost(protocol[name]) or protocol[name] == 0:
            raise ValueError("Positive finite spending limits required")
    key = labels_for(labels, cases, policy)
    planned = len(cases) * protocol["runs"]
    if planned > protocol["max_calls"] or planned * protocol["per_request_reservation_usd"] > protocol["spending_limit_usd"]:
        raise ValueError("Plan exceeds configured request or reserved spending limit")
    inputs, owners = {}, {}
    by_id = {r["id"]: r for r in key["cases"]}
    for case in cases:
        source = read_json(DATASET / case["input"])
        if digest(json.dumps(source, sort_keys=True)) != case["input_sha256"]:
            raise ValueError("Historical input hash differs from the dataset")
        inputs[case["id"]] = {"state": {"change": source}, "questions": questions}
        owners[case["id"]] = metadata(case, policy)
        if case["id"] in by_id:
            owners[case["id"]]["context_complete"] = by_id[case["id"]]["context_complete"]
    workspace.mkdir(parents=True, exist_ok=False)
    (workspace / "inputs").mkdir()
    (workspace / "outputs").mkdir()
    for name, data in (("policy", policy), ("questions", questions), ("protocol", protocol),
                       ("cases", cases), ("labels", key), ("metadata", owners)):
        write_json(workspace / f"{name}.json", data)
    for item, payload in inputs.items():
        write_json(workspace / "inputs" / (item + ".json"), payload)
    freeze = {"version": "jev-workflow-freeze-1.0", "partition": partition,
              "stage": "adjudicated_evaluation" if labels else "preparation_only",
              "created_at": datetime.now(timezone.utc).isoformat(), "planned_calls": planned,
              "code": {p: digest((ROOT / p).read_bytes()) for p in CODE},
              "files": {str(p.relative_to(workspace)): digest(p.read_bytes()) for p in sorted(workspace.rglob("*.json"))}}
    write_json(workspace / "freeze.json", freeze)
    return freeze


def run(workspace, dry_run=False):
    if dry_run:
        return _run(workspace, True)
    lock = workspace / ".run.lock"
    try:
        with lock.open("x") as handle:
            handle.write("Exclusive workflow run; reconcile interrupted requests before removing a stale lock.\n")
    except FileExistsError:
        raise ValueError("Another run or an interrupted run holds this workspace lock") from None
    try:
        return _run(workspace, False)
    finally:
        lock.unlink()


def _run(workspace, dry_run=False):
    freeze = verify(workspace)
    protocol = read_json(workspace / "protocol.json")
    if dry_run:
        return {"status": "dry_run", "partition": freeze["partition"], "planned_calls": freeze["planned_calls"],
                "questions_per_call": len(read_json(workspace / "questions.json")), "model": protocol["model"],
                "spending_limit_usd": protocol["spending_limit_usd"],
                "reserved_usd": freeze["planned_calls"] * protocol["per_request_reservation_usd"],
                "live_calls": 0, "adjudication": freeze["stage"], "downstream_model_calls": 0}
    if freeze["stage"] != "adjudicated_evaluation":
        raise ValueError("Independent human workflow adjudication is pending; use --dry-run")
    # All prior attempts count, including errors. Unknown cost stops further calls.
    fingerprint_freeze = digest((workspace / "freeze.json").read_bytes())
    existing = list((workspace / "outputs").glob("*.json"))
    expected = {f'{c["id"]}_run{n}.json': (c["id"], n) for c in read_json(workspace / "cases.json")
                for n in range(1, protocol["runs"] + 1)}
    for path in existing:
        r = read_json(path)
        if (r.get("freeze_sha256") != fingerprint_freeze or path.name not in expected
                or (r.get("id"), r.get("run")) != expected[path.name]):
            raise ValueError("Output provenance mismatch")
        cost = r.get("usage", {}).get("cost")
        if not valid_cost(cost) or cost > protocol["per_request_reservation_usd"]:
            raise ValueError("Unknown or excessive prior cost; stop for budget reconciliation")
    load_env(ROOT / ".env")
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise ValueError("OPENROUTER_API_KEY is not configured")
    client = OpenRouterDecisionsClient(os.environ["OPENROUTER_API_KEY"])
    count = len(existing)
    for case in read_json(workspace / "cases.json"):
        payload = read_json(workspace / "inputs" / (case["id"] + ".json"))
        for repeat in range(1, protocol["runs"] + 1):
            target = workspace / "outputs" / f'{case["id"]}_run{repeat}.json'
            if target.exists():
                continue
            if count >= protocol["max_calls"] or (count + 1) * protocol["per_request_reservation_usd"] > protocol["spending_limit_usd"]:
                return {"status": "budget_stopped", "attempts": count}
            record = {"id": case["id"], "run": repeat, "freeze_sha256": fingerprint_freeze,
                      "requested_model": protocol["model"], "resolved_model": None, "raw": None,
                      "probabilities": None, "percentages": None, "status": "api_failure", "usage": {},
                      "started_at": datetime.now(timezone.utc).isoformat()}
            started = time.monotonic()
            # Persist before the call: an interrupted/in-flight request must not be retried or treated as free.
            write_json(target, record)
            try:
                raw = client.send({"model": protocol["model"], **payload})
                record["raw"] = raw
                if isinstance(raw, dict):
                    record.update(resolved_model=raw.get("model"), usage=raw.get("usage") if isinstance(raw.get("usage"), dict) else {})
                values = probabilities(raw, payload["questions"])
                record.update(status="ok", probabilities=values, percentages=percentages(values))
            except Exception as error:
                record["error_type"] = type(error).__name__
                record["status"] = "invalid_response" if record["raw"] is not None else "api_failure"
                if isinstance(getattr(error, "code", None), int):
                    record["http_status"] = error.code
            record["wall_seconds"] = round(time.monotonic() - started, 6)
            write_json(target, record)
            count += 1
            cost = record["usage"].get("cost")
            if not valid_cost(cost) or cost > protocol["per_request_reservation_usd"]:
                return {"status": "cost_unknown_or_reservation_exceeded_stop", "attempts": count}
    return {"status": "completed_attempts", "attempts": count}


def valid_cost(value):
    return not isinstance(value, bool) and isinstance(value, (float, int)) and math.isfinite(value) and value >= 0


def agreement(actions, label, scope, unresolved):
    if label is None:
        return {"agreement": None, "missing_actions": None, "additional_actions": None, "label_status": "pending"}
    required = set(label["required_" + scope + "_actions"])
    allowed = required | set(label["optional_" + scope + "_actions"])
    selected = set(actions)
    return {"agreement": not unresolved and required <= selected <= allowed,
            "missing_actions": sorted(required - selected), "additional_actions": sorted(selected - allowed),
            "label_status": "human_attested"}


def summarize(rows):
    labeled = bool(rows) and all(r["workflow_score"]["agreement"] is not None for r in rows)
    resolved = [r for r in rows if not r["unresolved"]]
    return {"planned_requests": len(rows), "unresolved": sum(r["unresolved"] for r in rows),
            "execution_statuses": dict(Counter(r["status"] for r in rows)),
            "allowed_workflow_agreement": sum(r["workflow_score"]["agreement"] for r in rows) if labeled else None,
            "incorrect_resolved_workflows": sum(not r["workflow_score"]["agreement"] for r in resolved) if labeled else None,
            "missing_required_actions_on_resolved_requests": sum(len(r["workflow_score"]["missing_actions"]) for r in resolved) if labeled else None,
            "additional_actions_on_resolved_requests": sum(len(r["workflow_score"]["additional_actions"]) for r in resolved) if labeled else None,
            "missing_appsec_or_owner_approvals_on_resolved_requests": sum(len(set(r["workflow_score"]["missing_actions"]) & {"approve:appsec", "approve:privacy", "approve:boundary"}) for r in resolved) if labeled else None}


def score(workspace):
    freeze = verify(workspace)
    protocol, policy, questions, owners = (read_json(workspace / (name + ".json")) for name in ("protocol", "policy", "questions", "metadata"))
    labels = {r["id"]: r for r in read_json(workspace / "labels.json")["cases"]}
    cases = read_json(workspace / "cases.json")
    rows, baseline_rows, records = [], [], []
    for case in cases:
        item = case["id"]
        for repeat in range(1, protocol["runs"] + 1):
            path = workspace / "outputs" / f"{item}_run{repeat}.json"
            values, status = None, "not_executed"
            if path.exists():
                r = read_json(path)
                if r.get("freeze_sha256") != digest((workspace / "freeze.json").read_bytes()) or r.get("id") != item or r.get("run") != repeat:
                    raise ValueError("Output provenance mismatch")
                records.append(r)
                status = r["status"]
                if status == "ok":
                    values = probabilities(r["raw"], questions)
            w = route(values, owners[item], policy, status)
            unresolved = bool(w["pending_reasons"])
            rows.append({"id": item, "run": repeat, "synthetic": case["synthetic"], "status": status,
                         "unresolved": unresolved, "workflow": w,
                         "model_score": agreement(w["model_selected_actions"], labels.get(item), "model", bool(w["model_pending_reasons"])),
                         "workflow_score": agreement(w["required_actions"], labels.get(item), "workflow", unresolved)})
        # Holdout baselines are also withheld until independent adjudication.
        if freeze["partition"] == "development" or labels:
            diff = read_json(workspace / "inputs" / (item + ".json"))["state"]["change"]["diff"]
            flags = baseline_values(diff, questions)
            b = route(flags, owners[item], policy)
            b.pop("probabilities")
            b.pop("percentages")
            b["rule_flags_not_model_probabilities"] = flags
            unresolved = bool(b["pending_reasons"])
            baseline_rows.append({"id": item, "run": 1, "synthetic": case["synthetic"], "status": "deterministic_baseline",
                                  "unresolved": unresolved, "workflow": b,
                                  "model_score": agreement(b["model_selected_actions"], labels.get(item), "model", bool(b["model_pending_reasons"])),
                                  "workflow_score": agreement(b["required_actions"], labels.get(item), "workflow", unresolved)})
    summaries = {}
    for item in [c["id"] for c in cases]:
        selected = [r for r in rows if r["id"] == item]
        summaries[item] = {**summarize(selected), "stable_status_and_actions":
                           (len({(r["status"], tuple(r["workflow"]["required_actions"]), tuple(r["workflow"]["pending_reasons"])) for r in selected}) == 1)
                           if all(r["status"] == "ok" for r in selected) else None}
    return {"configuration_sha256": digest((workspace / "freeze.json").read_bytes()),
            "evidence": "new_workflow_configuration_no_legacy_probabilities_reused", "partition": freeze["partition"],
            "requested_model": protocol["model"], "resolved_models": sorted({r["resolved_model"] for r in records if r.get("resolved_model")}),
            "live_response_records": len(records), "headline": summarize(rows), "case_summaries": summaries,
            "real_cases": summarize([r for r in rows if not r["synthetic"]]),
            "synthetic_cases": summarize([r for r in rows if r["synthetic"]]),
            "usage": usage_summary(records), "details": rows,
            "deterministic_baseline": {"headline": summarize(baseline_rows), "details": baseline_rows},
            "limits": ["All planned requests remain in the denominator; repeats are correlated.",
                       "Pending human labels mean agreement and missed-action metrics are unknown.",
                       "Model-selected actions are separate from trusted mandatory requirements.",
                       "No downstream detection quality, best-model selection or production enforcement measured."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("packet", "prepare", "run", "score"):
        p = sub.add_parser(command)
        p.add_argument("workspace", type=Path)
        if command == "prepare":
            p.add_argument("--partition", required=True, choices=["development", "holdout"])
            p.add_argument("--labels", type=Path)
        if command == "run":
            p.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "packet":
            result = packet(args.workspace)
        elif args.command == "prepare":
            result = prepare(args.workspace, args.partition, args.labels)
        elif args.command == "run":
            result = run(args.workspace, args.dry_run)
        else:
            result = score(args.workspace)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, KeyError, OSError) as error:
        print(f"Jev workflow: {error}", file=__import__("sys").stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
