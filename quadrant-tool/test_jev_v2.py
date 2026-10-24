import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import jev_followup as study
from jev_policy_v2 import ROLES, baseline, estimate, gate, metric, obligations


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = study.read_json(study.V2 / "policy.json")
        self.meta = copy.deepcopy(study.read_json(study.V2 / "metadata.json")["cases"]["D01"])
        self.meta["context_complete"] = True
        self.meta["mandatory_roles"] = ["peer_reviewer", "boundary_owner"]
        self.p = {r: 0.1 for r in ROLES}
        self.p["low_impact"] = 0.9

    def complete(self, obligation):
        approvals = [{"role": r, "actor": self.meta["available_reviewers"][r][0],
                      "revision": self.meta["revision"], "decision": "approved"}
                     for r in obligation["required_roles"]]
        checks = [{"name": c, "producer": "fixture-ci", "revision": self.meta["revision"], "status": "passed"}
                  for c in obligation["required_checks"]]
        return approvals, checks

    def test_model_cannot_remove_mandatory_owner_or_approve(self):
        o = obligations(estimate(self.p), self.meta, self.policy)
        self.assertIn("boundary_owner", o["required_roles"])
        self.assertFalse(o["merge_approved"])
        a, c = self.complete(o)
        self.assertFalse(gate(o, self.meta, a[:1], c)["eligible_for_merge"])
        self.assertTrue(gate(o, self.meta, a, c)["eligible_for_merge"])

    def test_incomplete_stale_or_untrusted_check_blocks(self):
        o = obligations(estimate(self.p), self.meta, self.policy)
        a, c = self.complete(o)
        for mutation in ({"status": "pending"}, {"revision": "old"}, {"producer": "model"}):
            check = {**c[0], **mutation}
            self.assertFalse(gate(o, self.meta, a, [check])["eligible_for_merge"])

    def test_stale_or_untrusted_approval_blocks(self):
        o = obligations(estimate(self.p), self.meta, self.policy)
        a, c = self.complete(o)
        for mutation in ({"revision": "old"}, {"actor": "model"}, {"decision": "requested"}):
            bad = copy.deepcopy(a)
            bad[0].update(mutation)
            self.assertFalse(gate(o, self.meta, bad, c)["eligible_for_merge"])

    def test_abstention_failure_and_conflict_block_even_with_reviews(self):
        for p in (estimate({r: 0.1 for r in ROLES}), estimate(None, error=True),
                  estimate({**self.p, "auth_boundary": 0.8}), estimate({"low_impact": True})):
            o = obligations(p, self.meta, self.policy)
            a, c = self.complete(o)
            self.assertTrue(o["triage_required"])
            self.assertFalse(gate(o, self.meta, a, c)["eligible_for_merge"])

    def test_missing_context_requires_documented_resolution(self):
        self.meta["context_complete"] = False
        triage = {"actor": "fixture-triage-owner", "revision": self.meta["revision"],
                  "routes": ["low_impact"], "reason": "Reviewed changed behavior"}
        o = obligations(estimate(self.p), self.meta, self.policy, triage)
        self.assertTrue(o["triage_required"])
        triage["context_resolution"] = "Human inspected caller and confirmed invariant for this revision"
        o = obligations(estimate(self.p), self.meta, self.policy, triage)
        self.assertFalse(o["triage_required"])
        self.assertIn("boundary_owner", o["required_roles"])
        self.assertFalse(gate(o, self.meta, [], [])["review_completed"])

    def test_triage_does_not_supply_approval_or_waive_mandatory_checks(self):
        triage = {"actor": "fixture-triage-owner", "revision": self.meta["revision"],
                  "routes": ["low_impact"], "reason": "Documented exception to proposed construction review"}
        p = {"status": "conflict", "routes": ["construction", "low_impact"]}
        o = obligations(p, self.meta, self.policy, triage)
        self.assertTrue(o["triage_accepted"])
        self.assertEqual(o["required_checks"], ["unit_tests"])
        self.assertFalse(gate(o, self.meta, [], [])["eligible_for_merge"])
        triage["actor"] = "model"
        self.assertTrue(obligations(p, self.meta, self.policy, triage)["triage_required"])

    def test_unavailable_owner_never_disappears(self):
        self.meta["available_reviewers"]["boundary_owner"] = []
        o = obligations(estimate(self.p), self.meta, self.policy)
        self.assertIn("boundary_owner", o["required_roles"])
        self.assertIn("unavailable_reviewer", o["triage_reasons"])

    def test_no_numeric_coercion_or_nonfinite_probabilities(self):
        for value in (True, float("nan"), float("inf"), -0.1, 1.1, "0.9"):
            self.assertEqual(estimate({**self.p, "low_impact": value})["status"], "invalid_response")

    def test_baselines_depend_on_diff_or_availability_only(self):
        diff = "diff --git a/composer.json b/composer.json\n+++ b/composer.json\n+\"library\":\"2.0\""
        self.assertEqual(baseline(diff, "rules", [])['routes'], ["security_config"])
        self.assertEqual(baseline("", "all_available_specialists", ["boundary_owner"])["routes"], ["auth_boundary"])

    def test_unresolved_is_not_incorrect_or_success(self):
        label = {"required": ["auth_boundary"], "optional": []}
        row = metric({"status": "abstention", "routes": []}, label)
        row["id"] = "case"
        counts = study.summarize([row])
        self.assertEqual((counts["planned_calls"], counts["agreement"], counts["incorrect"], counts["unresolved"]), (1, 0, 0, 1))


class StudyTests(unittest.TestCase):
    def test_partition_rejects_related_cases_and_duplicate_diff(self):
        original = study.read_json(study.V2 / "dataset/manifest.json")
        study.validate_partition(original)
        bad = copy.deepcopy(original)
        bad["cases"][-1]["diff_sha256"] = bad["cases"][0]["diff_sha256"]
        with self.assertRaises(ValueError):
            study.validate_partition(bad)
        bad = copy.deepcopy(original)
        bad["cases"][-1].update(repo=bad["cases"][0]["repo"], family=bad["cases"][0]["family"])
        with self.assertRaises(ValueError):
            study.validate_partition(bad)

    def test_holdout_refuses_unadjudicated_labels_without_network(self):
        with tempfile.TemporaryDirectory() as t, patch.object(study.OpenRouterDecisionsClient, "send") as send:
            with self.assertRaises(ValueError):
                study.prepare(Path(t) / "run", "holdout")
            with self.assertRaises((ValueError, KeyError)):
                study.prepare(Path(t) / "run", "holdout", study.V2 / "dataset/packet/blank-labels.json")
            send.assert_not_called()

    def test_freeze_tampering_and_missing_calls(self):
        with tempfile.TemporaryDirectory() as t:
            w = Path(t) / "run"
            study.prepare(w, "development")
            study.verify(w)
            report = study.score(w)
            counts = report["methods"]["jev_threshold_0.5"]["headline"]
            self.assertEqual(counts["planned_calls"], 42)
            self.assertEqual(counts["unresolved"], 42)
            (w / "inputs/D01.json").write_text("{}")
            with self.assertRaises(ValueError):
                study.verify(w)

    def test_errors_preserved_on_resume_and_raw_outputs_retained(self):
        with tempfile.TemporaryDirectory() as t:
            w = Path(t) / "run"
            study.prepare(w, "development")
            with patch.dict(study.os.environ, {"OPENROUTER_API_KEY": "fixture-key"}), patch.object(study.OpenRouterDecisionsClient, "send", side_effect=TimeoutError) as send:
                study.run(w)
                self.assertEqual(send.call_count, 42)
                study.run(w)
                self.assertEqual(send.call_count, 42)
            report = study.score(w)
            self.assertEqual(report["methods"]["jev_threshold_0.5"]["headline"]["status_counts"], {"api_failure": 42})
            record = study.read_json(w / "outputs/D01_run1.json")
            self.assertNotIn("fixture-key", json.dumps(record))

    def test_context_arms_differ_only_in_context(self):
        with tempfile.TemporaryDirectory() as t:
            a, b = Path(t) / "diff", Path(t) / "context"
            study.prepare(a, "development", context="diff-only")
            study.prepare(b, "development", context="historical")
            for path in (a / "inputs").glob("*.json"):
                x, y = study.read_json(path), study.read_json(b / "inputs" / path.name)
                x["state"].pop("historical_context")
                y["state"].pop("historical_context")
                self.assertEqual(x, y)

    def test_packet_contains_no_prior_labels_or_model_outputs(self):
        packet = study.V2 / "dataset/packet"
        for p in packet.glob("case_*.json"):
            data = study.read_json(p)
            self.assertEqual(set(data), {"diff", "historical_context", "context_scope"})
            self.assertNotRegex(p.read_text(), r"\b(?:CVE-\d{4}-\d+|GHSA-[a-z0-9-]+)\b")

    def test_success_preserves_raw_probabilities_model_ids_and_cost(self):
        raw = {"model": "typesafe/jev-1.14-fixture", "provider": "fixture", "id": "fixture-response",
               "answers": {r: {"type": "noul", "noul": 0.9 if r == "low_impact" else 0.1} for r in ROLES},
               "usage": {"cost": 0.001}}
        with tempfile.TemporaryDirectory() as t:
            w = Path(t) / "run"
            study.prepare(w, "development")
            with patch.dict(study.os.environ, {"OPENROUTER_API_KEY": "fixture-key"}), patch.object(study.OpenRouterDecisionsClient, "send", return_value=raw):
                study.run(w)
            r = study.read_json(w / "outputs/D01_run1.json")
            self.assertEqual(r["raw"], raw)
            self.assertEqual(r["probabilities"]["low_impact"], 0.9)
            self.assertEqual(r["requested_model"], "typesafe/jev-1.14")
            self.assertEqual(study.score(w)["usage"]["reported_cost_usd"], 0.042)

    def test_published_evidence_and_available_decks_are_byte_identical(self):
        hashes = study.read_json(study.V2 / "protected-files.json")
        for p, expected in hashes.items():
            path = study.ROOT / p
            if p.endswith(".pptx") and not path.exists():
                continue  # Local presentation backups are excluded from GitHub.
            self.assertEqual(study.digest(path.read_bytes()), expected, p)
        original = {str(p.relative_to(study.ROOT)) for p in study.ARCHIVE.rglob("*") if p.is_file()}
        protected = {p for p in hashes if p.startswith(str(study.ARCHIVE.relative_to(study.ROOT)) + "/")}
        self.assertEqual(original, protected)


if __name__ == "__main__":
    unittest.main()
