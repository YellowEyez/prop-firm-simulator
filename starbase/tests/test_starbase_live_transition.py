import unittest

from starbase_live_transition import (
    LiveTransitionError,
    SimTransitionAccount,
    execute_live_transition,
    load_transition_policies,
    run_live_transition_verification,
)


class TestStarBaseLiveTransition(unittest.TestCase):
    def setUp(self):
        self.catalog = load_transition_policies()

    def test_catalog_version_and_date(self):
        self.assertEqual(self.catalog["schema_version"], "1.0.0")
        self.assertEqual(self.catalog["verified_as_of"], "2026-08-13")

    def test_discretionary_callup_is_not_inferred(self):
        a = SimTransitionAccount("L1", "lucid", "lucid_flex", "SIM_FUNDED", 50000, current_profit_balance=500, payout_count=5)
        r = execute_live_transition("lucid_standard_live", [a], catalog=self.catalog, explicit_callup=False)
        self.assertFalse(r.transition_executed)
        self.assertEqual(r.decision_grade, "AWAITING_DISCRETIONARY_CALLUP")

    def test_lucid_closes_all_sim_and_refunds_zero_payout_funded(self):
        accounts = [
            SimTransitionAccount("F1", "lucid", "lucid_flex", "SIM_FUNDED", 50000, current_profit_balance=700, payout_count=2, acquisition_cost_basis=90),
            SimTransitionAccount("F2", "lucid", "lucid_flex", "SIM_FUNDED", 50000, current_profit_balance=300, payout_count=0, acquisition_cost_basis=90),
            SimTransitionAccount("E1", "lucid", "lucid_flex", "EVALUATION", 50000, acquisition_cost_basis=90),
        ]
        r = execute_live_transition("lucid_standard_live", accounts, catalog=self.catalog, explicit_callup=True)
        self.assertEqual(r.source_accounts_becoming_live, 1)
        self.assertEqual(r.simulated_accounts_closed, 3)
        self.assertEqual(r.refunds_created, 90)
        self.assertEqual(len(r.live_accounts), 1)
        self.assertEqual(r.live_accounts[0].starting_balance, 0)

    def test_tradeify_three_payouts_is_review_eligible_but_not_automatic(self):
        a = SimTransitionAccount("T1", "tradeify", "tradeify_select_flex", "SIM_FUNDED", 50000, payout_count=3)
        r = execute_live_transition("tradeify_elite", [a], catalog=self.catalog, explicit_callup=False)
        self.assertFalse(r.transition_executed)
        self.assertEqual(r.decision_grade, "REVIEW_ELIGIBLE_AWAITING_SELECTION")

    def test_tradeify_callup_before_minimum_is_blocked(self):
        a = SimTransitionAccount("T1", "tradeify", "tradeify_select_flex", "SIM_FUNDED", 50000, payout_count=2)
        r = execute_live_transition("tradeify_elite", [a], catalog=self.catalog, explicit_callup=True)
        self.assertFalse(r.transition_executed)
        self.assertEqual(r.decision_grade, "CALLUP_INPUT_CONFLICTS_WITH_DOCUMENTED_MINIMUMS")

    def test_mffu_five_consecutive_can_trigger_without_manual_callup(self):
        a = SimTransitionAccount("M1", "mffu", "mffu_flex_50k", "SIM_FUNDED", 50000, payout_count=5, consecutive_approved_payouts=5)
        r = execute_live_transition("mffu_flex_live", [a], catalog=self.catalog)
        self.assertTrue(r.transition_executed)
        self.assertEqual(r.live_accounts[0].starting_balance, 2000)

    def test_apex_bonus_vault_and_eval_refund(self):
        accounts = [
            SimTransitionAccount("PA1", "apex", "apex_eod", "SIM_FUNDED", 50000, current_profit_balance=2000),
            SimTransitionAccount("PA2", "apex", "apex_eod", "SIM_FUNDED", 100000, current_profit_balance=-50),
            SimTransitionAccount("E1", "apex", "apex_eod", "EVALUATION", 50000, acquisition_cost_basis=167),
        ]
        r = execute_live_transition("apex_live_invitation", accounts, catalog=self.catalog, explicit_callup=True)
        self.assertEqual(r.bonus_vault_tracked, 2000)
        self.assertEqual(r.refunds_created, 167)
        self.assertEqual(len(r.live_accounts), 1)
        self.assertEqual(r.live_accounts[0].bonus_vault_balance, 2000)

    def test_apex_decline_yields_final_reward_no_live(self):
        a = SimTransitionAccount("PA1", "apex", "apex_eod", "SIM_FUNDED", 50000, current_profit_balance=2000)
        r = execute_live_transition("apex_live_invitation", [a], catalog=self.catalog, explicit_callup=True, accept_invitation=False)
        self.assertEqual(r.final_reward_cash, 3000)
        self.assertEqual(len(r.live_accounts), 0)

    def test_topstep_derives_size_start_and_reserve(self):
        accounts = [
            SimTransitionAccount("1", "topstep", "topstep_standard", "SIM_FUNDED", 50000, current_profit_balance=10000, payout_count=1),
            SimTransitionAccount("2", "topstep", "topstep_standard", "SIM_FUNDED", 50000, current_profit_balance=10000, payout_count=1),
            SimTransitionAccount("3", "topstep", "topstep_standard", "SIM_FUNDED", 50000, current_profit_balance=10000, payout_count=1),
            SimTransitionAccount("4", "topstep", "topstep_standard", "SIM_FUNDED", 50000, current_profit_balance=10000, payout_count=1),
            SimTransitionAccount("5", "topstep", "topstep_standard", "SIM_FUNDED", 150000, current_profit_balance=10000, payout_count=1),
        ]
        r = execute_live_transition("topstep_lfa_callup", accounts, catalog=self.catalog, explicit_callup=True)
        self.assertEqual(r.live_accounts[0].source_account_size, 100000)
        self.assertEqual(r.live_accounts[0].starting_balance, 10000)
        self.assertEqual(r.topstep_reserve_tracked, 40000)

    def test_topstep_caps_transfer_before_twenty_percent_split(self):
        accounts = [
            SimTransitionAccount("1", "topstep", "topstep_standard", "SIM_FUNDED", 50000, current_profit_balance=25000, payout_count=1),
            SimTransitionAccount("2", "topstep", "topstep_standard", "SIM_FUNDED", 50000, current_profit_balance=25000, payout_count=1),
            SimTransitionAccount("3", "topstep", "topstep_standard", "SIM_FUNDED", 50000, current_profit_balance=25000, payout_count=1),
            SimTransitionAccount("4", "topstep", "topstep_standard", "SIM_FUNDED", 50000, current_profit_balance=25000, payout_count=1),
        ]
        r = execute_live_transition("topstep_lfa_callup", accounts, catalog=self.catalog, explicit_callup=True)
        self.assertEqual(r.live_accounts[0].source_account_size, 50000)
        self.assertEqual(r.live_accounts[0].starting_balance, 10000)
        self.assertEqual(r.topstep_reserve_tracked, 40000)
        self.assertEqual(r.excess_transfer_value, 50000)

    def test_fundednext_transition_remains_blocked(self):
        a = SimTransitionAccount("FN", "fundednext", "fundednext_rapid", "SIM_FUNDED", 50000)
        with self.assertRaises(LiveTransitionError):
            execute_live_transition("fundednext_rapid_live", [a], catalog=self.catalog, explicit_callup=True)

    def test_step29_suite(self):
        suite = run_live_transition_verification(self.catalog)
        self.assertTrue(suite["all_pass"])
        self.assertEqual(suite["total"], 7)
        self.assertEqual(suite["passed"], 7)


if __name__ == "__main__":
    unittest.main()
