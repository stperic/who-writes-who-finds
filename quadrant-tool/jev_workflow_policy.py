"""Focused workflow policy and merge-gate simulation. No model execution here.

Metadata, workflow events, triage and finding resolutions are trusted inputs from
an authenticated workflow adapter. The model can supply only probabilities.
"""
import json
import math
import re

from jev import digest
from jev_policy_v2 import baseline as category_baseline


def fingerprint(value):
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":")))


def probabilities(raw, questions):
    if not isinstance(raw, dict) or not isinstance(raw.get("model"), str) or not raw["model"].strip():
        raise ValueError("Missing resolved model")
    answers = raw.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(questions):
        raise ValueError("Missing or unexpected question answers")
    result = {}
    for key, answer in answers.items():
        if not isinstance(answer, dict) or answer.get("type") != "noul":
            raise ValueError("Expected typed Noul answer")
        p = answer.get("noul")
        if isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p <= 1:
            raise ValueError("Noul must be a finite probability between zero and one")
        result[key] = p
    return result


def percentages(values):
    # Formatting never changes the underlying numerical answers.
    return {k: f"{p * 100:.2f}".rstrip("0").rstrip(".") + "%" for k, p in values.items()}


def route(values, metadata, policy, status="ok", triage=None, review_state=None):
    review_state = review_state or {}
    reasons, states, selected = [], {}, set()
    if status != "ok":
        reasons.append(status)
    else:
        values = probabilities({"model": "policy-input", "answers": {
            k: {"type": "noul", "noul": p} for k, p in values.items()}}, policy["thresholds"])
        for key, p in values.items():
            limits = policy["thresholds"][key]
            if not 0 <= limits["low"] < limits["high"] <= 1:
                raise ValueError("Invalid category thresholds")
            states[key] = "high" if p >= limits["high"] else "low" if p <= limits["low"] else "uncertain"
            if states[key] == "uncertain":
                reasons.append("uncertain:" + key)
        for rule in policy["rules"]:
            if all(states[k] == "high" for k in rule["all_high"]):
                selected.update(rule["actions"])
        if states["insufficient_context"] == "high":
            reasons.append("model_reports_missing_context")
    model_pending = list(reasons)
    if reasons:
        selected.add("human:triage")
    if not metadata["context_complete"]:
        reasons.append("trusted_context_incomplete")
    mandatory = set(policy["always"]) | set(metadata["mandatory_actions"])
    if not mandatory <= policy["actions"].keys():
        raise ValueError("Unknown mandatory action")
    token = fingerprint({"values": values, "status": status, "metadata": metadata, "policy": policy})
    effective = set(selected)
    accepted = False
    if triage is not None:
        actions = triage.get("resolved_model_actions")
        accepted = (triage.get("actor") in metadata["triage_actors"]
                    and triage.get("revision") == metadata["revision"]
                    and triage.get("routing_token") == token
                    and bool(triage.get("reason", "").strip())
                    and isinstance(actions, list) and set(actions) <= policy["actions"].keys()
                    and "human:triage" not in actions
                    and metadata["context_complete"]
                    and (not any("context" in r for r in reasons) or bool(triage.get("context_resolution", "").strip())))
        if accepted:
            effective = set(actions)
            reasons = []
        else:
            reasons.append("invalid_triage")
    review_added = set()
    if review_state.get("security_findings_detected"):
        review_added.add("approve:appsec")
    for condition, additions in policy["during_review"].items():
        if review_state.get(condition):
            review_added.update(additions)
            reasons.append(condition)
    required = mandatory | effective | review_added
    unavailable = [a for a in required if policy["actions"][a]["kind"] == "approval"
                   and not metadata["authorized_approvers"].get(a)]
    unapproved_ai = [a for a in required if policy["actions"][a]["kind"] == "ai"
                     and metadata["approved_ai_configs"].get(a) != fingerprint(policy["ai_configurations"][a])]
    if unavailable:
        reasons.append("unavailable_required_reviewer")
    if unapproved_ai:
        reasons.append("ai_configuration_not_approved")
    if reasons:
        required.add("human:triage")
    return {"revision": metadata["revision"], "policy_version": policy["version"], "routing_token": token,
            "probabilities": values, "percentages": percentages(values) if values else {}, "signal_states": states,
            "model_pending_reasons": model_pending,
            "model_selected_actions": sorted(selected), "mandatory_actions": sorted(mandatory),
            "effective_model_actions": sorted(effective), "review_added_actions": sorted(review_added),
            "required_actions": sorted(required), "pending_reasons": sorted(set(reasons)),
            "unavailable_actions": sorted(unavailable), "triage_accepted": accepted,
            "triage_record": triage, "review_completed": False, "merge_approved": False}


def baseline_values(diff, question_ids):
    """Adapt the existing transparent baseline; 0/1 are rule flags, not model probabilities."""
    categories = set(category_baseline(diff, "rules", [])["routes"])
    changed = "\n".join(s[1:] for s in diff.splitlines() if s[:1] in {"+", "-"} and not s.startswith(("+++", "---")))
    flags = {
        "personal_data_access": {"auth_boundary", "sensitive_data"} <= categories,
        "authorization_boundary": "auth_boundary" in categories,
        "patient_tenant_scoping": bool(re.search(r"\b(patient\w*|tenant\w*|IPatient\w*|pid)\b", changed, re.I)),
        "sql_construction": bool(re.search(r"\b(sql\w*|SELECT|ORDER BY)\b", changed, re.I)),
        "command_parser_output": "construction" in categories and bool(re.search(r"\b(exec|shell_exec|system|XMLReader|parse\w*|echo|html\w*|javascript)\b", changed, re.I)),
        "sensitive_data_flow": "sensitive_data" in categories,
        "security_configuration": "security_config" in categories,
        "insufficient_context": False,
    }
    return {k: float(flags[k]) for k in question_ids}


def gate(values, metadata, policy, approvals=(), checks=(), ai_reviews=(), findings=(), resolutions=(),
         status="ok", triage=None, disagreement=False):
    """Recompute obligations and verify trusted current-revision completion events."""
    revision = metadata["revision"]
    trusted_findings = [f for f in findings if f.get("revision") == revision
                        and f.get("producer") in metadata["finding_producers"]]
    completed_ai, missing_evidence = set(), False
    # Event lists are trusted chronological streams. Later failures/revocations
    # must supersede earlier completion records for the same current revision.
    latest_ai = {e.get("action"): e for e in ai_reviews if e.get("revision") == revision
                 and e.get("producer") in metadata["ai_producers"]}
    for event in latest_ai.values():
        action = event.get("action")
        if action not in policy["ai_configurations"] or event.get("producer") not in metadata["ai_producers"]:
            continue
        config = policy["ai_configurations"][action]
        output = event.get("output", {})
        valid = (event.get("revision") == revision and event.get("status") == "completed"
                 and event.get("config_sha256") == fingerprint(config) and event.get("model") == config["model"]
                 and all(event.get("context_revisions", {}).get(k) == revision for k in config["required_context"])
                 and isinstance(output, dict) and output.get("review_status") == "complete"
                 and isinstance(output.get("limitations"), list) and isinstance(output.get("findings"), list)
                 and all(isinstance(f, dict) and isinstance(f.get("blocking"), bool) and f.get("id")
                         and f.get("summary") and f.get("location") for f in output["findings"]))
        if not valid:
            if event.get("revision") == revision:
                missing_evidence = True
            continue
        completed_ai.add(action)
        trusted_findings.extend({**f, "producer": event["producer"], "revision": revision} for f in output["findings"])
    blocking = [f for f in trusted_findings if f.get("blocking") is True]
    resolved = {r.get("finding_sha256") for r in resolutions if r.get("revision") == revision
                and r.get("actor") in metadata["finding_resolution_actors"] and r.get("reason", "").strip()}
    unresolved = [f for f in blocking if fingerprint(f) not in resolved]
    state = {"blocking_findings": bool(unresolved), "security_findings_detected": bool(blocking),
             "missing_evidence": missing_evidence, "disagreement": disagreement}
    workflow = route(values, metadata, policy, status, triage, state)
    latest_approvals = {(a.get("action"), a.get("actor")): a for a in approvals if a.get("revision") == revision
                        and a.get("actor") in metadata["authorized_approvers"].get(a.get("action"), [])}
    denied = {a["action"] for a in latest_approvals.values() if a.get("decision") in {"changes_requested", "revoked", "rejected"}}
    approved = {a["action"] for a in latest_approvals.values() if a.get("decision") == "approved"} - denied
    latest_checks = {c.get("action"): c for c in checks if c.get("revision") == revision
                     and c.get("producer") in metadata["check_producers"].get(c.get("action"), [])}
    passed = {c["action"] for c in latest_checks.values() if c.get("status") == "passed"}
    completed = approved | passed | completed_ai
    if workflow["triage_accepted"] and not workflow["pending_reasons"]:
        completed.add("human:triage")
    incomplete = sorted(set(workflow["required_actions"]) - completed)
    eligible = not incomplete and not workflow["pending_reasons"] and not unresolved
    return {"evidence_type": "local_workflow_simulation_not_CI_enforcement", "workflow": workflow,
            "incomplete_actions": incomplete, "unresolved_blocking_findings": unresolved,
            "review_completed": eligible, "eligible_for_merge": eligible, "merge_performed": False}
