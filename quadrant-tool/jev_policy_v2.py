"""Pure deterministic study policy. Inputs marked trusted must come from CI/owners.

This is a tested workflow simulation, not a deployed branch-protection system.
Model output is never accepted as metadata, approval, check status or triage.
"""
import math
import re

ROLES = {
    "auth_boundary": "boundary_owner",
    "sensitive_data": "data_privacy_owner",
    "construction": "pr_reviewer",
    "security_config": "platform_security_owner",
    "low_impact": "peer_reviewer",
}
SPECIALISTS = set(ROLES) - {"low_impact"}


def estimate(probabilities, threshold=0.5, error=False):
    if error:
        return {"status": "api_failure", "routes": [], "probabilities": probabilities}
    if (not isinstance(probabilities, dict) or set(probabilities) != set(ROLES)
            or any(isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p)
                   or not 0 <= p <= 1 for p in probabilities.values())):
        return {"status": "invalid_response", "routes": [], "probabilities": probabilities}
    selected = sorted(r for r, p in probabilities.items() if p >= threshold)
    status = "proposed" if selected else "abstention"
    if "low_impact" in selected and len(selected) > 1:
        status = "conflict"
    return {"status": status, "routes": selected, "probabilities": probabilities}


def baseline(diff, mode, available_roles):
    if mode == "all_available_specialists":
        routes = sorted(r for r in SPECIALISTS if ROLES[r] in available_roles)
        return {"status": "proposed" if routes else "abstention", "routes": routes}
    if mode != "rules":
        raise ValueError("Unknown baseline")
    # Frozen, deliberately simple patterns; code comments can trigger false positives.
    changed = "\n".join(line[1:] for line in diff.splitlines()
                        if line[:1] in {"+", "-"} and not line.startswith(("+++", "---")))
    patterns = {
        "auth_boundary": r"\b(auth\w*|acl\w*|session\w*|tenant\w*|patient\w*|IPatient\w*|isPortal|pid)\b",
        "sensitive_data": r"\b(patient\w*|secret\w*|gateway_api_key|password\w*|readfile|document\w*|backup\w*)\b",
        "construction": r"\b(sql\w*|SELECT|ORDER BY|exec|shell_exec|system|XMLReader|parse\w*|echo|html\w*|javascript)\b",
        "security_config": r"\b(encrypt\w*|decrypt\w*|openssl\w*|CURLOPT_SSL\w*|verify_peer|PARSEHUGE|XINCLUDE)\b",
    }
    routes = {r for r, pattern in patterns.items() if re.search(pattern, changed, re.I)}
    if re.search(r"^\+\+\+ b/(?:.*/)?(?:composer\.(?:json|lock)|package(?:-lock)?\.json|requirements[^/]*\.txt|pyproject\.toml)$", diff, re.M):
        routes.add("security_config")
    return {"status": "proposed", "routes": sorted(routes or {"low_impact"})}


def obligations(proposal, metadata, policy, triage=None):
    """Compute obligations from estimates plus trusted metadata, never approval.

    Authorized triage may resolve uncertain routing and documented exceptions to
    model-added roles. It cannot remove metadata-mandated checks or owner roles.
    """
    reasons = []
    if proposal["status"] != "proposed":
        reasons.append(proposal["status"])
    if not metadata["context_complete"]:
        reasons.append("missing_context")
    routes = set(proposal.get("routes", []))
    if not routes <= ROLES.keys():
        routes = set()
        reasons.append("invalid_routes")
    accepted_triage = False
    if triage is not None:
        chosen = triage.get("routes")
        valid = (triage.get("actor") in metadata["triage_actors"]
                 and triage.get("revision") == metadata["revision"]
                 and isinstance(triage.get("reason"), str) and bool(triage["reason"].strip())
                 and isinstance(chosen, list) and bool(chosen) and set(chosen) <= ROLES.keys()
                 and not ("low_impact" in chosen and len(chosen) > 1)
                 and (metadata["context_complete"] or triage.get("context_resolution", "").strip()))
        if valid:
            routes = set(chosen)
            reasons = []
            accepted_triage = True
        else:
            reasons.append("invalid_triage")
    required_roles = set(metadata["mandatory_roles"]) | {ROLES[r] for r in routes}
    required_checks = set(metadata["mandatory_checks"])
    for r in routes:
        required_checks.update(policy["route_checks"][r])
    unavailable = sorted(r for r in required_roles if not metadata["available_reviewers"].get(r))
    if unavailable:
        reasons.append("unavailable_reviewer")
    return {"proposed_route": proposal, "effective_routes": sorted(routes),
            "required_roles": sorted(required_roles), "required_checks": sorted(required_checks),
            "triage_required": bool(reasons), "triage_reasons": sorted(set(reasons)),
            "triage_record": triage, "triage_accepted": accepted_triage,
            "unavailable_roles": unavailable, "review_completed": False, "merge_approved": False,
            "review_tier": "enhanced_review" if routes & SPECIALISTS else "standard_review",
            "ai_role": "advisory_category_estimator"}


def gate(obligation, metadata, approvals, checks):
    """Assess trusted workflow events for this exact revision (simulation only)."""
    approved = {a["role"] for a in approvals
                if a.get("revision") == metadata["revision"] and a.get("decision") == "approved"
                and a.get("actor") in metadata["available_reviewers"].get(a.get("role"), [])}
    passed = {c["name"] for c in checks if c.get("revision") == metadata["revision"]
              and c.get("status") == "passed"
              and c.get("producer") in metadata["trusted_check_producers"].get(c.get("name"), [])}
    missing_roles = sorted(set(obligation["required_roles"]) - approved)
    missing_checks = sorted(set(obligation["required_checks"]) - passed)
    blocked = obligation["triage_required"] or bool(missing_roles or missing_checks)
    return {"eligible_for_merge": not blocked, "review_completed": not blocked,
            "missing_approvals": missing_roles, "incomplete_checks": missing_checks,
            "triage_required": obligation["triage_required"], "merge_performed": False,
            "evidence_type": "workflow_simulation_only"}


def metric(proposal, label):
    """Unresolved requests stay in the denominator, separate from incorrect routes."""
    unresolved = proposal["status"] != "proposed"
    required, optional = set(label["required"]), set(label["optional"])
    routes = set(proposal["routes"])
    return {"status": proposal["status"], "routes": sorted(routes), "unresolved": unresolved,
            "agreement": not unresolved and required <= routes <= required | optional,
            "incorrect": not unresolved and not (required <= routes <= required | optional),
            "missing_routes": sorted(required - routes) if not unresolved else [],
            "unnecessary_routes": sorted(routes - required - optional) if not unresolved else [],
            "missing_roles": sorted({ROLES[r] for r in required - routes}) if not unresolved else [],
            "unnecessary_roles": sorted({ROLES[r] for r in routes - required - optional}) if not unresolved else [],
            "missing_specialist_roles": sorted({ROLES[r] for r in (required - routes) & SPECIALISTS}) if not unresolved else [],
            "unresolved_required_role_assignments": len(required) if unresolved else 0,
            "unsafe_peer_only": not unresolved and routes == {"low_impact"} and bool(required & SPECIALISTS)}
