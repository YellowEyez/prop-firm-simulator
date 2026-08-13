import unittest

from starbase_live import (
    LiveStateError,
    create_live_account,
    load_live_profiles,
    revalue_live_state,
    run_live_state_verification,
)


class TestStarBaseLive(unittest.TestCase):
    def setUp(self):
        self.catalog = load_live_profiles()

    def test_catalog_version_and_date(self):
        self.assertEqual(self.catalog["schema_version"], "1.0.0")
        self.assertEqual(self.catalog["verified_as_of"], "2026-08-13")

    def test_lucid_50k_state(self):
        s = create_live_account("lucid_live_50k", catalog=self.catalog)
        self.assertEqual(s.starting_balance, 0)
        self.assertEqual(s.failure_floor, -2000)
        self.assertEqual(s.max_minis, 2)
        self.assertIsNone(s.dll_amount)
        s2 = revalue_live_state(s, 4100, catalog=self.catalog)
        self.assertEqual(s2.failure_floor, 100)
        self.assertEqual(s2.max_minis, 4)

    def test_tradeify_50k_state(self):
        s = create_live_account("tradeify_elite_50k", catalog=self.catalog)
        self.assertEqual(s.failure_floor, -2000)
        self.assertEqual(s.max_minis, 2)
        s2 = revalue_live_state(s, 2200, catalog=self.catalog)
        self.assertEqual(s2.failure_floor, 100)
        self.assertEqual(s2.max_minis, 4)

    def test_mffu_live_state(self):
        s = create_live_account("mffu_flex_live_50k", catalog=self.catalog)
        self.assertEqual(s.starting_balance, 2000)
        self.assertEqual(s.failure_floor, 156)
        self.assertEqual(s.cushion, 1844)

    def test_apex_dynamic_level(self):
        s = create_live_account("apex_live_uniform", catalog=self.catalog)
        s2 = revalue_live_state(s, 12000, catalog=self.catalog)
        self.assertEqual(s2.failure_floor, 100)
        self.assertEqual(s2.max_minis, 25)
        self.assertEqual(s2.dll_amount, 5000)
        self.assertEqual(s2.risk_tier, "2")

    def test_topstep_requires_transition_balance(self):
        with self.assertRaises(LiveStateError):
            create_live_account("topstep_lfa_50k", catalog=self.catalog)
        s = create_live_account("topstep_lfa_50k", catalog=self.catalog, starting_balance_override=10000, reserve_balance=40000)
        self.assertEqual(s.starting_balance, 10000)
        self.assertEqual(s.reserve_balance, 40000)
        self.assertEqual(s.failure_floor, 1000)
        self.assertEqual(s.dll_amount, 2000)

    def test_conflicting_fundednext_is_blocked(self):
        with self.assertRaises(LiveStateError):
            create_live_account("fundednext_rapid_live_50k", catalog=self.catalog)

    def test_step28_suite(self):
        suite = run_live_state_verification(self.catalog)
        self.assertTrue(suite["all_pass"])
        self.assertEqual(suite["total"], 7)
        self.assertEqual(suite["passed"], 7)


if __name__ == "__main__":
    unittest.main()
