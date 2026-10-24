"""Checks for study validity and failure handling, without model API calls."""

import json
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

import jev


class JevTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name) / "study"
        self.manifest = jev.prepare(self.workspace)
        self.policy = jev.read_json(self.workspace / "policy.json")

    def test_preparation_preserves_full_large_diff_and_blinds_metadata(self):
        payload = jev.read_json(self.workspace / "inputs/item_05.json")
        original = (jev.ROOT / "openemr-study/data/original/diffs/CVE-2026-25146.diff").read_text()
        self.assertGreater(len(original), 60_000)
        self.assertEqual(original, payload["diff"])
        for path in (self.workspace / "inputs").glob("*.json"):
            text = path.read_text()
            self.assertNotRegex(text, r"CVE-\d{4}-|BENIGN-\d+|source_id|label_status")
        with self.assertRaises(FileExistsError):
            jev.prepare(self.workspace)

    def test_frozen_inputs_and_labels_cannot_change_silently(self):
        path = self.workspace / "answer-key.json"
        path.write_text(path.read_text() + " ")
        with self.assertRaisesRegex(ValueError, "Frozen answer-key"):
            jev.verify_workspace(self.workspace)

    def test_routes_are_multiple_and_combined_authority_is_advisory(self):
        result = jev.disposition(["construction", "sensitive_data", "auth_boundary"], self.policy)
        self.assertEqual(result["reviewer_roles"], ["boundary_owner", "data_privacy_owner", "pr_reviewer"])
        self.assertEqual(result["ai_authority"], "advisory")
        self.assertTrue(result["human_approval_required"])
        self.assertFalse(result["merge_approved"])

    def test_invalid_or_ungrounded_output_is_an_error(self):
        valid = {"routes": ["construction"], "evidence": [{
            "route": "construction", "quote": "+query", "reason": "Changed SQL"
        }], "context_needed": []}
        self.assertEqual(jev.validate_response(json.dumps(valid), self.policy, "+query"), valid)
        invalids = ["", "No issues", "null", "[]", "{}"]
        for routes in (["construction", "low_impact"], ["invented"], [], ["construction", "construction"]):
            invalids.append(json.dumps({**valid, "routes": routes}))
        invalids.append(json.dumps({**valid, "evidence": []}))
        invalids.append(json.dumps({**valid, "evidence": [{**valid["evidence"][0], "quote": "not in input"}]}))
        for raw in invalids:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                jev.validate_response(raw, self.policy, "+query")

    def test_smoke_score_is_marked_and_does_not_use_gold_as_predictions(self):
        with patch("sys.stderr"):
            counts = jev.run(self.workspace, "smoke", "smoke-fixture", 3)
        self.assertEqual(counts["ok"], 42)
        result = jev.score(self.workspace)
        self.assertEqual(result["evidence_type"], "SMOKE_ONLY_NOT_MODEL_EVIDENCE")
        self.assertEqual(result["counts"]["planned_runs"], 42)
        self.assertEqual(result["counts"]["acceptable_route_sets"], 9)
        self.assertEqual(result["counts"]["unsafe_peer_only_runs"], 33)
        self.assertEqual(result["by_case_kind"]["cve"]["planned_runs"], 24)
        self.assertEqual(result["repeat_consistency"]["cases_with_identical_routes"], 14)
        with patch("sys.stderr"):
            self.assertEqual(jev.run(self.workspace, "smoke", "smoke-fixture", 3), {"existing": 42})
        with self.assertRaisesRegex(ValueError, "configuration changed"):
            jev.run(self.workspace, "smoke", "changed-model", 3)

    def test_errors_and_missing_runs_stay_out_of_routing_denominator(self):
        with patch("sys.stderr"):
            jev.run(self.workspace, "smoke", "smoke-fixture", 1)
        first = self.workspace / "outputs/item_01_run1.json"
        record = jev.read_json(first)
        record["status"] = "error"
        jev.write_json(first, record)
        (self.workspace / "outputs/item_02_run1.json").unlink()
        result = jev.score(self.workspace)
        self.assertEqual(result["counts"]["planned_runs"], 14)
        self.assertEqual(result["counts"]["execution_errors"], 1)
        self.assertEqual(result["counts"]["missing_runs"], 1)
        self.assertEqual(result["counts"]["valid_runs"], 12)

    def test_truncated_output_never_becomes_a_route(self):
        with patch("sys.stderr"), patch.object(jev, "call_provider", return_value=("{}", "test-model", "length", {})):
            counts = jev.run(self.workspace, "smoke", "smoke-fixture", 1)
        self.assertEqual(counts, {"error": 14})
        result = jev.score(self.workspace)
        self.assertEqual(result["counts"]["execution_errors"], 14)
        self.assertEqual(result["counts"].get("valid_runs", 0), 0)
        record = jev.read_json(self.workspace / "outputs/item_01_run1.json")
        self.assertEqual(record["fallback"], "human_triage_required_no_approval")
        self.assertNotIn("disposition", record)
        with patch("sys.stderr"):
            resumed = jev.run(self.workspace, "smoke", "smoke-fixture", 1)
        self.assertEqual(resumed, {"existing": 14, "error": 14})

    def test_optional_route_is_accepted_but_unrelated_owner_is_counted(self):
        with patch("sys.stderr"):
            jev.run(self.workspace, "smoke", "smoke-fixture", 1)
        path = self.workspace / "outputs/item_01_run1.json"
        record = jev.read_json(path)
        quote = jev.read_json(self.workspace / "inputs/item_01.json")["diff"].splitlines()[0]
        routes = ["auth_boundary", "sensitive_data"]
        def update_record():
            record["raw"] = json.dumps({"routes": routes, "context_needed": [], "evidence": [
                {"route": route, "quote": quote, "reason": "Schema fixture, not a model judgment"}
                for route in routes]})
            jev.write_json(path, record)
        update_record()
        detail = jev.score(self.workspace)["details"][0]
        self.assertEqual(detail["missing_roles"], [])
        self.assertEqual(detail["unnecessary_routes"], [])
        routes.append("security_config")
        update_record()
        self.assertEqual(jev.score(self.workspace)["details"][0]["unnecessary_routes"], ["security_config"])

    def test_operational_error_does_not_log_exception_secrets(self):
        with patch("sys.stderr"), patch.object(jev, "call_provider", side_effect=TimeoutError("SECRET-DO-NOT-LOG")):
            jev.run(self.workspace, "smoke", "smoke-fixture", 1)
        text = (self.workspace / "outputs/item_01_run1.json").read_text()
        self.assertNotIn("SECRET-DO-NOT-LOG", text)
        self.assertEqual(json.loads(text)["error_type"], "TimeoutError")

    def test_score_rejects_mismatched_output_provenance(self):
        with patch("sys.stderr"):
            jev.run(self.workspace, "smoke", "smoke-fixture", 1)
        path = self.workspace / "outputs/item_01_run1.json"
        record = jev.read_json(path)
        record["input_sha256"] = "different-input"
        jev.write_json(path, record)
        with self.assertRaisesRegex(ValueError, "provenance mismatch"):
            jev.score(self.workspace)

    def test_dry_run_needs_no_endpoint_and_writes_no_results(self):
        result = jev.run(self.workspace, "openai", "explicit-model-id", 3, True)
        self.assertEqual(result["calls"], 42)
        self.assertFalse((self.workspace / "run-config.json").exists())
        self.assertEqual(list((self.workspace / "outputs").iterdir()), [])

    def test_dotenv_loads_quotes_without_overriding_environment_or_executing(self):
        path = Path(self.temp.name) / ".env"
        path.write_text('# comment\nexport OPENROUTER_API_KEY="local-key" # comment\n'
                        "OPENAI_API_KEY='$(touch /tmp/never-execute)'\nHOME=/untrusted\n")
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "existing-key"}, clear=True):
            jev.load_env(path)
            self.assertEqual(os.environ["OPENROUTER_API_KEY"], "existing-key")
            self.assertEqual(os.environ["OPENAI_API_KEY"], "$(touch /tmp/never-execute)")
            self.assertNotIn("HOME", os.environ)
        path.write_text('OPENROUTER_API_KEY="PRIVATE-UNFINISHED\n')
        with self.assertRaisesRegex(ValueError, r"^Invalid .env quoting on line 1$"):
            jev.load_env(path)

    def decisions_response(self, selected=()):
        return {"id": "fixture-request", "model": "typesafe/jev-1.14-fixture", "provider": "TypeSafe",
                "answers": {route: {"type": "noul", "noul": 0.9 if route in selected else 0.1}
                            for route in self.policy["routes"]},
                "usage": {"input_tokens": 123, "cost": 0.0001}}

    def test_openrouter_sends_actual_decisions_protocol_and_keeps_auth_out_of_body(self):
        response = self.decisions_response(["auth_boundary", "sensitive_data"])
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "PRIVATE-FIXTURE"}):
            client = jev.provider_client("openrouter")
        client._opener = Mock()
        client._opener.open.return_value = io.BytesIO(json.dumps(response).encode())
        payload = jev.read_json(self.workspace / "inputs/item_03.json")
        raw, resolved, finish, usage = jev.call_provider(client, "openrouter", "typesafe/jev-1.14", payload)
        request = client._opener.open.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(request.full_url, "https://openrouter.ai/api/alpha/decisions")
        self.assertEqual(request.get_header("Authorization"), "Bearer PRIVATE-FIXTURE")
        self.assertEqual(set(body), {"model", "state", "questions"})
        self.assertEqual(body["state"]["diff"], payload["diff"])
        self.assertNotIn("PRIVATE-FIXTURE", request.data.decode())
        self.assertNotIn("CVE-", request.data.decode())
        self.assertEqual(set(body["questions"]), set(self.policy["routes"]))
        self.assertEqual(resolved, response["model"])
        self.assertEqual(finish, "typed_decisions")
        self.assertEqual(usage["cost"], 0.0001)
        prediction = jev.validate_decisions(raw, self.policy, 0.5)
        self.assertEqual(prediction["routes"], ["auth_boundary", "sensitive_data"])
        self.assertFalse(prediction["evidence_available"])

    def test_decisions_abstain_and_conflict_are_not_silent_peer_approval(self):
        prediction = jev.validate_decisions(json.dumps(self.decisions_response()), self.policy, 0.5)
        self.assertTrue(prediction["abstained"])
        self.assertEqual(prediction["routes"], [])
        response = self.decisions_response(["auth_boundary", "low_impact"])
        prediction = jev.validate_decisions(json.dumps(response), self.policy, 0.5)
        self.assertEqual(prediction["routes"], ["auth_boundary"])
        self.assertTrue(prediction["conflicting_low_impact"])

    def test_decisions_reject_incomplete_or_invalid_probabilities(self):
        for value in (True, "0.9", -0.1, 1.1, float("nan"), float("inf")):
            response = self.decisions_response()
            response["answers"]["auth_boundary"]["noul"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                jev.validate_decisions(json.dumps(response), self.policy, 0.5)
        response = self.decisions_response()
        response["answers"].pop("construction")
        with self.assertRaises(ValueError):
            jev.validate_decisions(json.dumps(response), self.policy, 0.5)

    def test_decisions_run_and_score_track_abstentions_separately(self):
        client = Mock()
        client.send.return_value = self.decisions_response()
        with patch.object(jev, "provider_client", return_value=client), patch("sys.stderr"):
            self.assertEqual(jev.run(self.workspace, "openrouter", "typesafe/jev-1.14", 1), {"abstain": 14})
        result = jev.score(self.workspace)
        self.assertEqual(result["counts"]["abstained_runs"], 14)
        self.assertEqual(result["counts"]["execution_errors"], 0)
        self.assertEqual(result["counts"]["valid_runs"], 0)
        self.assertEqual(result["decision_threshold"], 0.5)
        self.assertAlmostEqual(result["api_usage"]["reported_cost_usd"], 0.0014)
        self.assertEqual(result["api_usage"]["cost_reporting_runs"], 14)
        self.assertEqual(len(result["case_summaries"]), 14)
        self.assertEqual(result["case_summaries"][0]["abstained_runs"], 1)
        with patch.object(jev, "provider_client", return_value=client), patch("sys.stderr"):
            self.assertEqual(jev.run(self.workspace, "openrouter", "typesafe/jev-1.14", 1),
                             {"existing": 14, "abstain": 14})


if __name__ == "__main__":
    unittest.main()
