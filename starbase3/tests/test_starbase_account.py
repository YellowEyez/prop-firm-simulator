import copy
import unittest

from starbase_account import (
    AccountStateError,
    create_account_from_rulebook,
    post_account_cost,
    post_trade,
    set_status,
    start_session,
    verify_account_ledger,
)
from starbase_rulebook import load_rulebook


class StarBaseAccountV4ATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rulebook = load_rulebook()

    def make_lucid(self):
        return create_account_from_rulebook(
            self.rulebook,
            product_id="lucid_flex",
            account_size=50000,
            stage="evaluation",
            account_id="TEST-LUCID-001",
            timestamp_utc="2026-08-11T12:00:00+00:00",
        )

    def test_account_initializes_fresh_at_nominal_balance(self):
        state, ledger = self.make_lucid()
        self.assertEqual(state.starting_balance, 50000)
        self.assertEqual(state.balance, 50000)
        self.assertEqual(state.trade_count, 0)
        self.assertEqual(len(ledger), 1)
        self.assertEqual(ledger[0].event_type, "ACCOUNT_OPENED")

    def test_funded_account_starts_fresh_and_does_not_inherit_evaluation_profit(self):
        state, ledger = create_account_from_rulebook(
            self.rulebook, product_id="lucid_flex", account_size=50000, stage="sim_funded",
            account_id="TEST-LUCID-FUNDED-001", timestamp_utc="2026-08-11T12:00:00+00:00"
        )
        self.assertEqual(state.starting_balance, 50000)
        self.assertEqual(state.balance, 50000)
        self.assertEqual(state.lifetime_net_pnl, 0)
        self.assertEqual(ledger[0].event_type, "ACCOUNT_OPENED")

    def test_initial_reference_floor_is_rulebook_balance_minus_max_loss(self):
        state, _ = self.make_lucid()
        self.assertEqual(state.reference_max_loss, 2000)
        self.assertEqual(state.reference_initial_failure_floor, 48000)

    def test_trade_posts_gross_minus_commission(self):
        state, ledger = self.make_lucid()
        state, ledger = start_session(state, ledger, "2026-08-11", timestamp_utc="2026-08-11T22:00:00+00:00")
        state, ledger = post_trade(state, ledger, gross_pnl=325, commission=3.5, timestamp_utc="2026-08-11T22:01:00+00:00")
        self.assertAlmostEqual(state.balance, 50321.5)
        self.assertAlmostEqual(state.lifetime_gross_pnl, 325)
        self.assertAlmostEqual(state.lifetime_commissions, 3.5)
        self.assertAlmostEqual(state.lifetime_net_pnl, 321.5)
        self.assertAlmostEqual(state.session_net_pnl, 321.5)
        self.assertEqual(state.trade_count, 1)

    def test_account_cost_is_external_cash_not_prop_balance(self):
        state, ledger = self.make_lucid()
        state, ledger = post_account_cost(state, ledger, amount=100, timestamp_utc="2026-08-11T12:01:00+00:00")
        self.assertEqual(state.balance, 50000)
        self.assertEqual(state.external_cash_flow, -100)
        self.assertEqual(state.account_costs_paid, 100)

    def test_new_session_resets_session_pnl_not_lifetime(self):
        state, ledger = self.make_lucid()
        state, ledger = start_session(state, ledger, "A")
        state, ledger = post_trade(state, ledger, gross_pnl=100, commission=4)
        state, ledger = start_session(state, ledger, "B")
        self.assertEqual(state.current_session_id, "B")
        self.assertEqual(state.session_net_pnl, 0)
        self.assertEqual(state.lifetime_net_pnl, 96)

    def test_status_change_is_audited(self):
        state, ledger = self.make_lucid()
        state, ledger = set_status(state, ledger, status="PAUSED")
        self.assertEqual(state.status, "PAUSED")
        self.assertEqual(ledger[-1].status_after, "PAUSED")
        self.assertEqual(ledger[-1].event_type, "STATUS_CHANGED")

    def test_negative_commission_is_rejected(self):
        state, ledger = self.make_lucid()
        with self.assertRaises(AccountStateError):
            post_trade(state, ledger, gross_pnl=100, commission=-1)

    def test_undefined_stage_is_rejected(self):
        with self.assertRaises(AccountStateError):
            create_account_from_rulebook(self.rulebook, product_id="lucid_direct", account_size=50000, stage="evaluation")

    def test_ledger_hash_chain_verifies(self):
        state, ledger = self.make_lucid()
        state, ledger = post_account_cost(state, ledger, amount=50)
        state, ledger = start_session(state, ledger, "S1")
        state, ledger = post_trade(state, ledger, gross_pnl=-500, commission=3.5)
        check = verify_account_ledger(ledger)
        self.assertTrue(check["valid"])
        self.assertEqual(check["event_count"], 4)

    def test_tampered_ledger_is_detected(self):
        state, ledger = self.make_lucid()
        state, ledger = post_trade(state, ledger, gross_pnl=325, commission=3.5)
        tampered = copy.deepcopy(ledger)
        object.__setattr__(tampered[-1], "balance_after", 99999)
        self.assertFalse(verify_account_ledger(tampered)["valid"])

    def test_rule_snapshot_is_stable_and_nonempty(self):
        s1, _ = self.make_lucid()
        s2, _ = self.make_lucid()
        self.assertEqual(s1.rule_snapshot_hash, s2.rule_snapshot_hash)
        self.assertEqual(len(s1.rule_snapshot_hash), 64)


if __name__ == "__main__":
    unittest.main()
