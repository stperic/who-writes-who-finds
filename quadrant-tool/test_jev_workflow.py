import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import jev_workflow as w
from jev_workflow_policy import fingerprint, gate, percentages, probabilities, route


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.policy = w.read_json(w.STUDY / "policy.json")
        self.questions = w.read_json(w.STUDY / "questions.json")
        self.meta = w.metadata(w.read_json(w.DATASET / "manifest.json")["cases"][4], self.policy)
        self.meta["context_complete"] = True
        self.values = {k: 0.05 for k in self.questions}
        self.values.update(personal_data_access=0.96, authorization_boundary=0.93, sql_construction=0.94)

    def complete_events(self, workflow):
        approvals, checks, ai = [], [], []
        for action in workflow["required_actions"]:
            kind = self.policy["actions"][action]["kind"]
            if kind == "approval":
                approvals.append({"action": action, "actor": self.meta["authorized_approvers"][action][0],
                                  "revision": self.meta["revision"], "decision": "approved"})
            elif kind == "check":
                checks.append({"action": action, "producer": "fixture-ci", "revision": self.meta["revision"], "status": "passed"})
            elif kind == "ai":
                config = self.policy["ai_configurations"][action]
                ai.append({"action": action, "producer": "fixture-ai-runner", "revision": self.meta["revision"],
                           "status": "completed", "model": config["model"], "config_sha256": fingerprint(config),
                           "context_revisions": {c: self.meta["revision"] for c in config["required_context"]},
                           "output": {"review_status": "complete", "findings": [], "limitations": []}})
        return {"approvals": approvals, "checks": checks, "ai_reviews": ai}

    def evaluate(self, **events):
        return gate(self.values, self.meta, self.policy, **events)

    def test_noul_keeps_exact_values_and_formats_percentages(self):
        raw = {"model": "fixture", "answers": {k: {"type": "noul", "noul": p} for k, p in self.values.items()}}
        result = probabilities(raw, self.questions)
        self.assertEqual(result["sql_construction"], 0.94)
        self.assertEqual(percentages(result)["sql_construction"], "94%")
        self.assertEqual(percentages({"a": 0.94321}), {"a": "94.32%"})
        self.assertEqual(percentages({"a": 0, "b": 1}), {"a": "0%", "b": "100%"})

    def test_typed_response_failure_handling(self):
        raw = {"model": "fixture", "answers": {k: {"type": "noul", "noul": p} for k, p in self.values.items()}}
        for p in [True, "0.94", -0.1, 1.1, float("nan"), float("inf")]:
            bad = copy.deepcopy(raw)
            bad["answers"]["sql_construction"]["noul"] = p
            with self.assertRaises(ValueError): probabilities(bad, self.questions)
        bad = copy.deepcopy(raw)
        bad["answers"].pop("sql_construction")
        with self.assertRaises(ValueError): probabilities(bad, self.questions)
        bad = copy.deepcopy(raw)
        bad["answers"]["sql_construction"]["type"] = "score"
        with self.assertRaises(ValueError): probabilities(bad, self.questions)

    def test_combined_ai_and_appsec_deduplicate(self):
        self.values["sensitive_data_flow"] = 0.95
        result = route(self.values, self.meta, self.policy)
        self.assertTrue({"ai:sql", "approve:appsec", "approve:privacy", "approve:boundary", "check:sast"} <= set(result["required_actions"]))
        self.assertEqual(result["required_actions"].count("approve:privacy"), 1)
        self.assertFalse(result["review_completed"])

    def test_every_threshold_has_exact_low_uncertain_and_high_states(self):
        # At equality, the declared policy is decisive. Values between its
        # boundaries must leave a human triage obligation instead.
        for condition, limits in self.policy["thresholds"].items():
            values = {key: 0.0 for key in self.questions}
            for probability, expected in ((limits["low"], "low"),
                                          ((limits["low"] + limits["high"]) / 2, "uncertain"),
                                          (limits["high"], "high")):
                with self.subTest(condition=condition, probability=probability):
                    values[condition] = probability
                    result = route(values, self.meta, self.policy)
                    self.assertEqual(result["signal_states"][condition], expected)
                    self.assertTrue(set(self.policy["always"]) <= set(result["required_actions"]))
                    if expected == "uncertain":
                        self.assertIn("uncertain:" + condition, result["pending_reasons"])
                        self.assertIn("human:triage", result["required_actions"])
                    elif expected == "low":
                        self.assertNotIn("uncertain:" + condition, result["pending_reasons"])
                    else:
                        expected_actions = set().union(*(set(rule["actions"]) for rule in self.policy["rules"]
                                                         if rule["all_high"] == [condition]))
                        self.assertTrue(expected_actions <= set(result["model_selected_actions"]))

    def test_all_low_keeps_declared_payment_obligations(self):
        self.meta["mandatory_actions"].extend(["check:boundary", "check:sast", "approve:appsec"])
        result = route({key: 0.0 for key in self.questions}, self.meta, self.policy)
        self.assertEqual(result["model_selected_actions"], [])
        self.assertEqual(result["required_actions"], sorted(set(self.policy["always"])
                                                              | set(self.meta["mandatory_actions"])))
        self.assertFalse(result["pending_reasons"])

    def test_missing_appsec_cannot_be_replaced_by_clean_ai(self):
        events = self.complete_events(route(self.values, self.meta, self.policy))
        events["approvals"] = [a for a in events["approvals"] if a["action"] != "approve:appsec"]
        result = self.evaluate(**events)
        self.assertFalse(result["eligible_for_merge"])
        self.assertIn("approve:appsec", result["incomplete_actions"])

    def test_incomplete_ai_security_check_and_wrong_config_block(self):
        events = self.complete_events(route(self.values, self.meta, self.policy))
        for field in ("ai_reviews", "checks"):
            bad = copy.deepcopy(events)
            bad[field] = []
            self.assertFalse(self.evaluate(**bad)["eligible_for_merge"])
        events["ai_reviews"][0]["config_sha256"] = "different-prompt"
        self.assertFalse(self.evaluate(**events)["eligible_for_merge"])

    def test_earlier_revision_approval_and_ai_context_block(self):
        for field in ("approvals", "ai_reviews"):
            events = self.complete_events(route(self.values, self.meta, self.policy))
            events[field][0]["revision"] = "old-revision"
            self.assertFalse(self.evaluate(**events)["eligible_for_merge"])
        events = self.complete_events(route(self.values, self.meta, self.policy))
        events["ai_reviews"][0]["context_revisions"]["diff"] = "old-revision"
        self.assertFalse(self.evaluate(**events)["eligible_for_merge"])

    def test_unavailable_reviewer_and_unapproved_ai_block(self):
        events = self.complete_events(route(self.values, self.meta, self.policy))
        self.meta["authorized_approvers"]["approve:appsec"] = []
        self.assertFalse(self.evaluate(**events)["eligible_for_merge"])
        self.meta["approved_ai_configs"]["ai:sql"] = "unapproved"
        self.assertIn("ai_configuration_not_approved", self.evaluate(**events)["workflow"]["pending_reasons"])

    def test_uncertainty_api_failure_and_missing_context_block(self):
        events = self.complete_events(route(self.values, self.meta, self.policy))
        self.values["sql_construction"] = 0.5
        self.assertFalse(self.evaluate(**events)["eligible_for_merge"])
        self.assertFalse(gate(None, self.meta, self.policy, status="api_failure", **events)["eligible_for_merge"])
        self.meta["context_complete"] = False
        self.assertFalse(self.evaluate(**events)["eligible_for_merge"])

    def test_model_low_cannot_remove_mandatory_owner(self):
        self.meta["mandatory_actions"].append("approve:appsec")
        result = route({k: 0.01 for k in self.questions}, self.meta, self.policy)
        self.assertIn("approve:appsec", result["required_actions"])
        self.assertNotIn("approve:appsec", result["model_selected_actions"])

    def test_blocking_finding_requires_authorized_resolution(self):
        events = self.complete_events(route(self.values, self.meta, self.policy))
        finding = {"id": "F1", "blocking": True, "summary": "Fixture injection", "location": "fixture.php:10",
                   "producer": "fixture-security-reviewer", "revision": self.meta["revision"]}
        events["findings"] = [finding]
        self.assertFalse(self.evaluate(**events)["eligible_for_merge"])
        resolution = {"finding_sha256": fingerprint(finding), "revision": self.meta["revision"], "actor": "model", "reason": "fixed"}
        events["resolutions"] = [resolution]
        self.assertFalse(self.evaluate(**events)["eligible_for_merge"])
        resolution["actor"] = "fixture-appsec"
        self.assertTrue(self.evaluate(**events)["eligible_for_merge"])

    def test_ai_blocking_finding_and_disagreement_add_appsec(self):
        self.values = {k: 0.05 for k in self.questions}
        self.values["sql_construction"] = 0.95
        events = self.complete_events(route(self.values, self.meta, self.policy))
        events["ai_reviews"][0]["output"]["findings"] = [{"id": "F2", "blocking": True, "summary": "Fixture", "location": "file:1"}]
        result = self.evaluate(**events)
        self.assertIn("approve:appsec", result["workflow"]["review_added_actions"])
        self.assertFalse(result["eligible_for_merge"])
        self.assertFalse(self.evaluate(disagreement=True, **events)["eligible_for_merge"])

    def test_latest_failure_or_revocation_overrides_prior_success(self):
        for field, changes in (("checks", {"status": "failed"}), ("ai_reviews", {"status": "failed"}),
                               ("approvals", {"decision": "revoked"})):
            events = self.complete_events(route(self.values, self.meta, self.policy))
            events[field].append({**events[field][0], **changes})
            self.assertFalse(self.evaluate(**events)["eligible_for_merge"])

    def test_all_current_requirements_satisfied(self):
        events = self.complete_events(route(self.values, self.meta, self.policy))
        result = self.evaluate(**events)
        self.assertTrue(result["eligible_for_merge"])
        self.assertFalse(result["merge_performed"])
        self.assertIn("simulation", result["evidence_type"])

    def test_triage_is_not_approval_and_cannot_waive_mandatory(self):
        self.meta["mandatory_actions"].append("approve:appsec")
        original = route(None, self.meta, self.policy, "api_failure")
        triage = {"actor": "fixture-security-triage", "revision": self.meta["revision"], "routing_token": original["routing_token"],
                  "reason": "Human reviewed code and resolved failed routing", "resolved_model_actions": ["ai:sql", "check:sast"]}
        result = gate(None, self.meta, self.policy, status="api_failure", triage=triage)
        self.assertTrue(result["workflow"]["triage_accepted"])
        self.assertIn("approve:appsec", result["incomplete_actions"])
        self.assertFalse(result["eligible_for_merge"])
        triage["revision"] = "old"
        self.assertFalse(gate(None, self.meta, self.policy, status="api_failure", triage=triage)["workflow"]["triage_accepted"])

    def test_free_text_cannot_invent_missing_context(self):
        self.values["insufficient_context"] = 0.95
        self.meta["context_complete"] = False
        original = route(self.values, self.meta, self.policy)
        triage = {"actor": "fixture-security-triage", "revision": self.meta["revision"],
                  "routing_token": original["routing_token"],
                  "reason": "I reviewed the change", "context_resolution": "All context is now available",
                  "resolved_model_actions": ["ai:sql"]}
        result = route(self.values, self.meta, self.policy, triage=triage)
        self.assertFalse(result["triage_accepted"])
        self.assertIn("trusted_context_incomplete", result["pending_reasons"])

        # A trusted adapter must independently establish context completeness.
        self.meta["context_complete"] = True
        triage["routing_token"] = route(self.values, self.meta, self.policy)["routing_token"]
        resolved = route(self.values, self.meta, self.policy, triage=triage)
        self.assertTrue(resolved["triage_accepted"])
        self.assertNotIn("trusted_context_incomplete", resolved["pending_reasons"])


class HarnessTests(unittest.TestCase):
    def adjudicated_fixture(self, directory):
        # These labels exist only inside a temporary unit-test directory.
        # They simulate schema-complete attestations, never real human evidence.
        policy = w.read_json(w.STUDY / "policy.json")
        cases = [c for c in w.read_json(w.DATASET / "manifest.json")["cases"] if c["partition"] == "development"]
        universe = set(policy["actions"])
        rows = [{"case_id": c["blind_id"], "required_model_actions": [], "optional_model_actions": [],
                 "prohibited_model_actions": sorted(universe), "required_workflow_actions": policy["always"],
                 "optional_workflow_actions": [], "prohibited_workflow_actions": sorted(universe - set(policy["always"])),
                 "context_complete": True, "rationale": "UNIT TEST FIXTURE, not human evidence", "reviewed_at": "fixture"} for c in cases]
        labels = directory / "fixture-labels.json"
        w.write_json(labels, {"status": "adjudicated", "policy_sha256": fingerprint(policy), "reviewer": "UNIT_TEST_FIXTURE",
                             "reviewer_is_independent_human_security_reviewer": True, "saw_jev_outputs_or_previous_labels": False,
                             "thresholds_approved_for_evaluation": True, "cases": rows})
        path = directory / "run"
        w.prepare(path, "development", labels)
        return path

    def test_mocked_run_preserves_raw_and_cost_and_never_retries(self):
        questions = w.read_json(w.STUDY / "questions.json")
        raw = {"model": "typesafe/jev-1.14-fixture", "answers": {k: {"type": "noul", "noul": 0.01} for k in questions}, "usage": {"cost": 0.001}}
        with tempfile.TemporaryDirectory() as t:
            path = self.adjudicated_fixture(Path(t))
            with patch.dict(w.os.environ, {"OPENROUTER_API_KEY": "fixture-secret"}), patch.object(w.OpenRouterDecisionsClient, "send", return_value=raw) as send:
                self.assertEqual(w.run(path)["attempts"], 42)
                w.run(path)
                self.assertEqual(send.call_count, 42)
                self.assertEqual(set(send.call_args.args[0]), {"model", "state", "questions"})
            record = w.read_json(path / "outputs/D01_run1.json")
            self.assertEqual(record["raw"], raw)
            self.assertEqual(record["probabilities"]["sql_construction"], 0.01)
            self.assertEqual(record["percentages"]["sql_construction"], "1%")
            self.assertNotIn("fixture-secret", json.dumps(record))
            report = w.score(path)
            self.assertEqual(report["usage"]["reported_cost_usd"], 0.042)
            self.assertEqual(report["headline"]["allowed_workflow_agreement"], 42)

    def test_unknown_cost_stops_and_failure_stays_in_denominator(self):
        with tempfile.TemporaryDirectory() as t:
            path = self.adjudicated_fixture(Path(t))
            with patch.dict(w.os.environ, {"OPENROUTER_API_KEY": "fixture-secret"}), patch.object(w.OpenRouterDecisionsClient, "send", side_effect=TimeoutError("fixture-secret")) as send:
                self.assertEqual(w.run(path)["attempts"], 1)
                with self.assertRaises(ValueError): w.run(path)
                self.assertEqual(send.call_count, 1)
            report = w.score(path)
            self.assertEqual(report["headline"]["planned_requests"], 42)
            self.assertEqual(report["headline"]["execution_statuses"], {"api_failure": 1, "not_executed": 41})
            self.assertEqual(report["headline"]["unresolved"], 42)

    def test_workspace_lock_blocks_concurrent_dispatch(self):
        with tempfile.TemporaryDirectory() as t, patch.object(w.OpenRouterDecisionsClient, "send") as send:
            path = self.adjudicated_fixture(Path(t))
            (path / ".run.lock").write_text("another run")
            with self.assertRaises(ValueError): w.run(path)
            send.assert_not_called()

    def test_pending_holdout_dry_run_never_calls_model(self):
        with tempfile.TemporaryDirectory() as t, patch.object(w.OpenRouterDecisionsClient, "send") as send:
            path = Path(t) / "holdout"
            w.prepare(path, "holdout")
            result = w.run(path, True)
            self.assertEqual(result["planned_calls"], 27)
            with self.assertRaises(ValueError): w.run(path)
            send.assert_not_called()
            report = w.score(path)
            self.assertEqual(report["headline"]["planned_requests"], 27)
            self.assertIsNone(report["headline"]["allowed_workflow_agreement"])
            self.assertEqual(report["deterministic_baseline"]["details"], [])

    def test_inputs_have_eight_independent_questions_no_labels(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / "development"
            w.prepare(path, "development")
            payload = w.read_json(path / "inputs/D05.json")
            self.assertEqual(set(payload), {"state", "questions"})
            self.assertEqual(set(payload["state"]), {"change"})
            self.assertEqual(len(payload["questions"]), 8)
            self.assertTrue(all(q["type"] == "noul" for q in payload["questions"].values()))
            self.assertEqual(set(payload["state"]["change"]), {"diff", "historical_context", "context_scope"})
            report = w.score(path)
            self.assertEqual(report["headline"]["unresolved"], 42)
            self.assertIsNone(report["case_summaries"]["D05"]["stable_status_and_actions"])

    def test_freeze_detects_changed_questions(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / "development"
            w.prepare(path, "development")
            (path / "questions.json").write_text("{}")
            with self.assertRaises(ValueError): w.run(path, True)

    def test_budget_rejects_plan_over_limit(self):
        original = w.read_json
        def config(path):
            result = original(path)
            if str(path).endswith("protocol.json"):
                result["spending_limit_usd"] = 0.01
            return result
        with tempfile.TemporaryDirectory() as t, patch.object(w, "read_json", side_effect=config):
            with self.assertRaises(ValueError): w.prepare(Path(t) / "run", "development")

    def test_existing_evidence_unchanged(self):
        for name, sha in w.read_json(w.STUDY / "preserved-files.json").items():
            self.assertEqual(w.digest((w.ROOT / name).read_bytes()), sha, name)


if __name__ == "__main__":
    unittest.main()
