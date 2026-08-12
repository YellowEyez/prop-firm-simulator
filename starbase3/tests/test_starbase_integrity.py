import json
import unittest
from pathlib import Path

from starbase_integrity import (
    GENESIS_HASH,
    append_ledger_entry,
    assess_rule_coverage,
    bootstrap_futures_sessions,
    build_run_manifest,
    drawdown_semantics,
    independent_trial_max_abs_z,
    make_run_id,
    parse_ledger_jsonl,
    sha256_bytes,
    validate_ledger_chain,
)
from starbase_rulebook import load_rulebook


class TestStarBaseIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rulebook = load_rulebook(Path(__file__).resolve().parents[1] / "starbase_rules_v3.json")

    def test_run_id_is_deterministic(self):
        cfg = {"b": 2, "a": 1}
        h = {"x.csv": "abc"}
        self.assertEqual(make_run_id(cfg, h, "rules"), make_run_id({"a": 1, "b": 2}, h, "rules"))

    def test_run_id_changes_when_source_changes(self):
        cfg = {"a": 1}
        self.assertNotEqual(make_run_id(cfg, {"x": "1"}, "r"), make_run_id(cfg, {"x": "2"}, "r"))

    def test_manifest_exact_profile_is_production_grade(self):
        m = build_run_manifest(config={"x": 1}, source_hashes={"a": "b"}, rulebook_hash="r",
                               execution_fidelity="EXACT_PROFILE", rulebook_schema_version="3.0.0", random_seed=7)
        self.assertTrue(m["production_grade_execution"])
        self.assertTrue(m["run_id"].startswith("SB-350-"))

    def test_drawdown_axes_are_separate(self):
        s = drawdown_semantics("EOD_TRAILING")
        self.assertEqual(s["floor_update_basis"], "END_OF_SESSION")
        self.assertEqual(s["breach_test_basis"], "INTRADAY_EQUITY_OR_MAE")

    def test_rule_coverage_verified_core(self):
        c = assess_rule_coverage(self.rulebook, "lucid_flex", 50000, "evaluation")
        self.assertEqual(c["status"], "VERIFIED")
        self.assertEqual(c["drawdown_semantics"]["floor_update_basis"], "END_OF_SESSION")

    def test_rule_coverage_missing_stage(self):
        c = assess_rule_coverage(self.rulebook, "lucid_direct", 50000, "evaluation")
        self.assertEqual(c["status"], "NOT_MODELED")

    def test_independent_search_threshold_increases(self):
        self.assertGreater(independent_trial_max_abs_z(100, 0.95), independent_trial_max_abs_z(1, 0.95))

    def test_whole_session_bootstrap_is_deterministic(self):
        ids = ["A", "A", "B", "C"]
        a = bootstrap_futures_sessions(ids, n_sessions=8, seed=42)
        b = bootstrap_futures_sessions(ids, n_sessions=8, seed=42)
        self.assertEqual(a, b)
        self.assertTrue(set(a).issubset({"A", "B", "C"}))

    def test_hash_chained_experiment_ledger(self):
        ledger = append_ledger_entry([], {"experiment_name": "A"})
        ledger = append_ledger_entry(ledger, {"experiment_name": "B"})
        v = validate_ledger_chain(ledger)
        self.assertTrue(v["valid"])
        self.assertEqual(v["entries"], 2)
        self.assertEqual(ledger[0]["prev_hash"], GENESIS_HASH)
        raw = "\n".join(json.dumps(x) for x in ledger)
        self.assertEqual(len(parse_ledger_jsonl(raw)), 2)

    def test_ledger_tamper_is_detected(self):
        ledger = append_ledger_entry([], {"experiment_name": "A"})
        ledger[0]["experiment_name"] = "TAMPERED"
        self.assertFalse(validate_ledger_chain(ledger)["valid"])


if __name__ == "__main__":
    unittest.main()
