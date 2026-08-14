import math
import pytest

from starbase_live import create_live_account, load_live_profiles, revalue_live_state
from starbase_live_payout import (
    LivePayoutContext,
    LivePayoutError,
    execute_live_payout,
    load_live_payout_policies,
    quote_live_payout,
    run_live_payout_verification,
)


def test_live_payout_suite_is_green():
    s = run_live_payout_verification()
    assert s["total"] == 10
    assert s["passed"] == 10
    assert s["failed"] == 0


def test_lucid_standard_payout_locks_floor_and_splits_90_10():
    lp = load_live_profiles()
    pc = load_live_payout_policies()
    state = revalue_live_state(create_live_account("lucid_live_50k", catalog=lp), 2500, catalog=lp)
    r = execute_live_payout(state, LivePayoutContext(requested_gross=1000), catalog=pc)
    assert math.isclose(r.trader_cash, 900)
    assert math.isclose(r.balance_after, 1500)
    assert math.isclose(r.failure_floor_after, 100)


def test_tradeify_full_balance_payout_closes_account():
    lp = load_live_profiles()
    pc = load_live_payout_policies()
    state = revalue_live_state(create_live_account("tradeify_elite_50k", catalog=lp), 5000, catalog=lp)
    r = execute_live_payout(state, LivePayoutContext(requested_gross=5000), catalog=pc)
    assert r.status_after == "CLOSED_FULL_WITHDRAWAL"
    assert math.isclose(r.trader_cash, 4000)


def test_mffu_requires_explicit_live_profit_ledger():
    lp = load_live_profiles()
    pc = load_live_payout_policies()
    state = revalue_live_state(create_live_account("mffu_flex_live_50k", catalog=lp), 3000, catalog=lp)
    q = quote_live_payout(state, LivePayoutContext(requested_gross=500), catalog=pc)
    assert not q.eligible
    assert "EXPLICIT_LIVE_PROFIT_LEDGER_REQUIRED" in q.reason_codes


def test_apex_before_90_days_cannot_close_safety_net():
    lp = load_live_profiles()
    pc = load_live_payout_policies()
    state = revalue_live_state(create_live_account("apex_live_uniform", catalog=lp), 3500, catalog=lp)
    q = quote_live_payout(state, LivePayoutContext(requested_gross=3500, live_days_elapsed=89, allow_safety_net_closeout=True), catalog=pc)
    assert not q.eligible
    assert "SAFETY_NET_CLOSEOUT_REQUIRES_90_LIVE_DAYS" in q.reason_codes


def test_topstep_before_30_needs_five_winning_days():
    lp = load_live_profiles()
    pc = load_live_payout_policies()
    state = create_live_account("topstep_lfa_50k", catalog=lp, starting_balance_override=10000, reserve_balance=40000)
    q = quote_live_payout(state, LivePayoutContext(requested_gross=5000, winning_days_this_cycle=4, lifetime_winning_days=10), catalog=pc)
    assert not q.eligible
    assert "NEEDS_5_WINNING_DAYS_THIS_CYCLE" in q.reason_codes


def test_daily_policy_blocks_second_same_day_request():
    lp = load_live_profiles()
    pc = load_live_payout_policies()
    state = revalue_live_state(create_live_account("tradeify_elite_50k", catalog=lp), 5000, catalog=lp)
    q = quote_live_payout(state, LivePayoutContext(payout_date="2026-01-02", last_payout_date="2026-01-02", requested_gross=1000), catalog=pc)
    assert not q.eligible
    assert "ONE_PAYOUT_REQUEST_PER_DAY" in q.reason_codes
