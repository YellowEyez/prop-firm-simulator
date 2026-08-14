"""Project StarBase v5I live payout / withdrawal engine (Step 30).

This module executes live cash withdrawals against first-class LiveAccountState
objects created in Step 28 / Step 29. It deliberately does not finalize all
closure/forfeiture consequences; those remain Step 31.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

from starbase_integrity import sha256_text, stable_json
from starbase_live import LiveAccountState, LiveStateError, create_live_account, load_live_profiles, revalue_live_state, state_as_dict
from starbase_paths import asset_path

LIVE_PAYOUT_ENGINE_VERSION = "5I.1.0"
LIVE_PAYOUT_SCHEMA_VERSION = "1.0.0"


class LivePayoutError(ValueError):
    pass


@dataclass(frozen=True)
class LivePayoutContext:
    payout_date: str = "2026-01-02"
    requested_gross: float = 0.0
    last_payout_date: Optional[str] = None
    winning_days_this_cycle: int = 0
    lifetime_winning_days: int = 0
    live_days_elapsed: int = 0
    available_live_profit: Optional[float] = None
    first_live_trip: bool = False
    live_bonus_already_paid: bool = False
    allow_safety_net_closeout: bool = False
    monthly_live_withdrawals_gross: float = 0.0


@dataclass(frozen=True)
class LivePayoutQuote:
    policy_id: str
    profile_id: str
    eligible: bool
    reason_codes: tuple[str, ...]
    cadence: str
    split_percent: float
    minimum_gross_payout: float
    maximum_gross_available: float
    requested_gross: float
    trader_cash_from_requested: float
    would_close_account: bool
    live_bonus_cash_eligible: float
    bonus_vault_release_estimate: float
    policy_grade: str
    verified_as_of: str
    source_urls: tuple[str, ...]


@dataclass(frozen=True)
class LivePayoutResult:
    policy_id: str
    payout_date: str
    executed: bool
    reason_codes: tuple[str, ...]
    gross_withdrawal: float
    trader_cash: float
    firm_share: float
    live_bonus_cash: float
    bonus_vault_release_estimate: float
    balance_before: float
    balance_after: float
    failure_floor_before: Optional[float]
    failure_floor_after: Optional[float]
    status_before: str
    status_after: str
    reserve_balance_after: float
    bonus_vault_balance_after: float
    cumulative_live_withdrawals_after: float
    trader_wallet_cash_after: float
    payout_count_after: int
    policy_grade: str
    verified_as_of: str
    source_urls: tuple[str, ...]
    rule_snapshot_hash: str
    state_after: LiveAccountState


def load_live_payout_policies(path: Optional[str | Path] = None) -> Dict[str, Any]:
    p = Path(path) if path else asset_path("starbase_live_payouts_v1.json")
    data = json.loads(Path(p).read_text(encoding="utf-8"))
    if data.get("schema_version") != LIVE_PAYOUT_SCHEMA_VERSION:
        raise LivePayoutError(f"Unsupported live payout policy schema: {data.get('schema_version')}")
    return data


def payout_policy_by_id(catalog: Dict[str, Any], policy_id: str) -> Dict[str, Any]:
    for p in catalog.get("policies", []):
        if p.get("policy_id") == policy_id:
            return p
    raise LivePayoutError(f"Unknown live payout policy: {policy_id}")


def payout_policy_for_profile(catalog: Dict[str, Any], profile_id: str) -> Dict[str, Any]:
    for p in catalog.get("policies", []):
        if profile_id in (p.get("profile_ids") or []):
            return p
    raise LivePayoutError(f"No live payout policy is mapped to profile {profile_id}")


def live_payout_policy_rows(catalog: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    cat = catalog or load_live_payout_policies()
    rows: List[Dict[str, Any]] = []
    for p in cat.get("policies", []):
        rows.append({
            "Firm": p.get("firm_name"),
            "Policy": p.get("display_name"),
            "Policy ID": p.get("policy_id"),
            "Cadence": p.get("cadence"),
            "Trader Split": p.get("profit_split_percent"),
            "Minimum Gross Payout": p.get("minimum_gross_payout"),
            "Withdrawable Basis": p.get("withdrawable_basis"),
            "Policy Grade": p.get("policy_grade"),
        })
    return rows


def _policy_hash(catalog: Dict[str, Any], policy: Dict[str, Any]) -> str:
    return sha256_text(stable_json({
        "engine_version": LIVE_PAYOUT_ENGINE_VERSION,
        "schema": catalog.get("schema_version"),
        "verified_as_of": catalog.get("verified_as_of"),
        "policy": policy,
    }))


def _same_day_block(ctx: LivePayoutContext) -> bool:
    return bool(ctx.last_payout_date and ctx.payout_date and ctx.last_payout_date == ctx.payout_date)


def _lucid_max(state: LiveAccountState, policy: Dict[str, Any]) -> float:
    lock = float(policy.get("post_payout_floor_lock") or 0.0)
    return max(float(state.balance) - lock, 0.0)


def _bonus_eligibility(state: LiveAccountState, policy: Dict[str, Any], ctx: LivePayoutContext) -> float:
    b = policy.get("live_bonus") or {}
    if not b or not ctx.first_live_trip or ctx.live_bonus_already_paid:
        return 0.0
    size = str(state.source_account_size or "")
    target = (b.get("targets_by_source_size") or {}).get(size)
    bonus = (b.get("bonus_by_source_size") or {}).get(size)
    if target is None or bonus is None:
        return 0.0
    return float(bonus) if float(state.balance) >= float(target) else 0.0


def quote_live_payout(
    state: LiveAccountState,
    ctx: LivePayoutContext,
    *,
    catalog: Optional[Dict[str, Any]] = None,
) -> LivePayoutQuote:
    if state.status != "ACTIVE":
        raise LivePayoutError(f"Live account must be ACTIVE to request a payout; status is {state.status}.")
    cat = catalog or load_live_payout_policies()
    policy = payout_policy_for_profile(cat, state.profile_id)
    requested = max(float(ctx.requested_gross), 0.0)
    split = float(policy.get("profit_split_percent") or 0.0)
    minimum = float(policy.get("minimum_gross_payout") or 0.0)
    reasons: List[str] = []
    max_gross = 0.0
    would_close = False
    bonus_cash = 0.0
    vault_estimate = 0.0

    if _same_day_block(ctx):
        reasons.append("ONE_PAYOUT_REQUEST_PER_DAY")

    pid = str(policy.get("policy_id"))
    if pid == "lucid_live_standard":
        max_gross = _lucid_max(state, policy)
        bonus_cash = _bonus_eligibility(state, policy, ctx)
    elif pid == "tradeify_elite_live":
        max_gross = max(float(state.balance) - float(policy.get("trading_capital_floor") or 0.0), 0.0)
        would_close = requested > 0 and math.isclose(requested, max_gross, abs_tol=1e-9) and max_gross > 0
    elif pid == "mffu_flex_live_50k":
        if ctx.available_live_profit is None:
            reasons.append("EXPLICIT_LIVE_PROFIT_LEDGER_REQUIRED")
        else:
            available_profit = max(float(ctx.available_live_profit), 0.0)
            room_above_floor = max(float(state.balance) - float(policy.get("minimum_balance") or 0.0), 0.0)
            max_gross = min(available_profit, room_above_floor)
    elif pid == "apex_live_uniform":
        safety = float(policy.get("safety_net_balance") or 0.0)
        normal = max(float(state.balance) - safety, 0.0)
        if ctx.allow_safety_net_closeout:
            required_days = int(policy.get("safety_net_closeout_after_live_days") or 0)
            if int(ctx.live_days_elapsed) < required_days:
                reasons.append("SAFETY_NET_CLOSEOUT_REQUIRES_90_LIVE_DAYS")
                max_gross = normal
            else:
                max_gross = max(float(state.balance), 0.0)
                would_close = requested > 0
        else:
            max_gross = normal
        vault_rate = float(policy.get("bonus_vault_monthly_release_rate") or 0.0)
        vault_estimate = min(float(state.bonus_vault_balance), max((float(ctx.monthly_live_withdrawals_gross) + requested) * vault_rate, 0.0))
    elif pid == "topstep_lfa":
        if int(ctx.lifetime_winning_days) >= int(policy.get("daily_unlock_after_lifetime_winning_days") or 0):
            max_gross = max(float(state.balance), 0.0)
        else:
            pre = policy.get("pre_daily_unlock") or {}
            req_days = int(pre.get("required_winning_days") or 0)
            if int(ctx.winning_days_this_cycle) < req_days:
                reasons.append(f"NEEDS_{req_days}_WINNING_DAYS_THIS_CYCLE")
            max_gross = max(float(state.balance) * float(pre.get("max_withdrawal_fraction_of_unlocked_balance") or 0.0), 0.0)
        would_close = requested > 0 and math.isclose(requested, float(state.balance), abs_tol=1e-9) and float(state.balance) > 0
    else:
        raise LivePayoutError(f"Payout policy {pid} is not executable in Step 30.")

    if requested > max_gross + 1e-9:
        reasons.append("REQUEST_EXCEEDS_AVAILABLE_GROSS")
    if requested > 0 and requested + 1e-9 < minimum:
        reasons.append("REQUEST_BELOW_MINIMUM")
    if requested == 0 and bonus_cash <= 0:
        reasons.append("NO_WITHDRAWAL_OR_BONUS_REQUESTED")

    eligible = len(reasons) == 0
    trader_cash = requested * (split / 100.0) if eligible else 0.0
    return LivePayoutQuote(
        policy_id=pid,
        profile_id=state.profile_id,
        eligible=eligible,
        reason_codes=tuple(reasons),
        cadence=str(policy.get("cadence") or "UNRESOLVED"),
        split_percent=split,
        minimum_gross_payout=minimum,
        maximum_gross_available=max_gross,
        requested_gross=requested,
        trader_cash_from_requested=trader_cash,
        would_close_account=would_close,
        live_bonus_cash_eligible=bonus_cash,
        bonus_vault_release_estimate=vault_estimate,
        policy_grade=str(policy.get("policy_grade") or "UNRESOLVED"),
        verified_as_of=str(cat.get("verified_as_of") or ""),
        source_urls=tuple(str(x) for x in (policy.get("source_urls") or [])),
    )


def execute_live_payout(
    state: LiveAccountState,
    ctx: LivePayoutContext,
    *,
    catalog: Optional[Dict[str, Any]] = None,
) -> LivePayoutResult:
    cat = catalog or load_live_payout_policies()
    policy = payout_policy_for_profile(cat, state.profile_id)
    quote = quote_live_payout(state, ctx, catalog=cat)
    if not quote.eligible:
        raise LivePayoutError("Payout request is not eligible: " + ", ".join(quote.reason_codes))

    gross = float(ctx.requested_gross)
    trader_cash = gross * (quote.split_percent / 100.0)
    firm_share = gross - trader_cash
    balance_after = float(state.balance) - gross
    floor_after = state.failure_floor
    status_after = state.status

    if quote.policy_id == "lucid_live_standard" and gross > 0:
        floor_after = float(policy.get("post_payout_floor_lock") or 100.0)
    if quote.would_close_account:
        if quote.policy_id == "apex_live_uniform" and ctx.allow_safety_net_closeout:
            status_after = "CLOSED_SAFETY_NET_WITHDRAWAL"
        else:
            status_after = "CLOSED_FULL_WITHDRAWAL"

    new_state = replace(
        state,
        balance=balance_after,
        failure_floor=floor_after,
        cushion=None if floor_after is None else balance_after - float(floor_after),
        cumulative_live_withdrawals=float(state.cumulative_live_withdrawals) + gross,
        trader_wallet_cash=float(state.trader_wallet_cash) + trader_cash + float(quote.live_bonus_cash_eligible),
        live_payout_count=int(getattr(state, "live_payout_count", 0)) + (1 if gross > 0 else 0),
        last_live_payout_date=ctx.payout_date if gross > 0 else getattr(state, "last_live_payout_date", None),
        live_bonus_cash_received=float(getattr(state, "live_bonus_cash_received", 0.0)) + float(quote.live_bonus_cash_eligible),
        status=status_after,
    )

    # Recompute dynamic contract tier after a non-closing withdrawal. Preserve payout-specific floor lock.
    if status_after == "ACTIVE":
        try:
            projected = revalue_live_state(new_state, balance_after, catalog=load_live_profiles(), floor_locked=(quote.policy_id == "lucid_live_standard" and gross > 0))
            new_state = replace(projected, failure_floor=floor_after, cushion=None if floor_after is None else balance_after - float(floor_after))
        except (LiveStateError, ValueError):
            pass

    rid = sha256_text(stable_json({
        "engine": LIVE_PAYOUT_ENGINE_VERSION,
        "policy_hash": _policy_hash(cat, policy),
        "account_id": state.account_id,
        "balance_before": state.balance,
        "context": asdict(ctx),
        "gross": gross,
        "bonus": quote.live_bonus_cash_eligible,
    }))
    return LivePayoutResult(
        policy_id=quote.policy_id,
        payout_date=ctx.payout_date,
        executed=True,
        reason_codes=tuple(),
        gross_withdrawal=gross,
        trader_cash=trader_cash,
        firm_share=firm_share,
        live_bonus_cash=float(quote.live_bonus_cash_eligible),
        bonus_vault_release_estimate=float(quote.bonus_vault_release_estimate),
        balance_before=float(state.balance),
        balance_after=balance_after,
        failure_floor_before=state.failure_floor,
        failure_floor_after=floor_after,
        status_before=state.status,
        status_after=status_after,
        reserve_balance_after=float(new_state.reserve_balance),
        bonus_vault_balance_after=float(new_state.bonus_vault_balance),
        cumulative_live_withdrawals_after=float(new_state.cumulative_live_withdrawals),
        trader_wallet_cash_after=float(new_state.trader_wallet_cash),
        payout_count_after=int(getattr(new_state, "live_payout_count", 0)),
        policy_grade=quote.policy_grade,
        verified_as_of=quote.verified_as_of,
        source_urls=quote.source_urls,
        rule_snapshot_hash=rid,
        state_after=new_state,
    )


def payout_result_as_dict(result: LivePayoutResult) -> Dict[str, Any]:
    d = asdict(result)
    d["state_after"] = state_as_dict(result.state_after)
    return d


def run_live_payout_verification(catalog: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cat = catalog or load_live_payout_policies()
    live_catalog = load_live_profiles()
    fixtures: List[Dict[str, Any]] = []

    # P01 Lucid: payout locks MLL to $100 and pays 90% to trader.
    s = revalue_live_state(create_live_account("lucid_live_50k", catalog=live_catalog), 2500.0, catalog=live_catalog)
    r = execute_live_payout(s, LivePayoutContext(requested_gross=1000.0, first_live_trip=False), catalog=cat)
    fixtures.append({"id": "P01_LUCID_PARTIAL_LOCK", "result": r, "expected": {"gross_withdrawal": 1000.0, "trader_cash": 900.0, "balance_after": 1500.0, "failure_floor_after": 100.0, "status_after": "ACTIVE"}})

    # P02 Lucid live bonus: external cash, not deducted from account balance.
    s = revalue_live_state(create_live_account("lucid_live_50k", catalog=live_catalog), 2100.0, catalog=live_catalog)
    r = execute_live_payout(s, LivePayoutContext(requested_gross=0.0, first_live_trip=True, live_bonus_already_paid=False), catalog=cat)
    fixtures.append({"id": "P02_LUCID_FIRST_LIVE_BONUS", "result": r, "expected": {"live_bonus_cash": 2000.0, "balance_after": 2100.0, "trader_wallet_cash_after": 2000.0, "status_after": "ACTIVE"}})

    # P03 Tradeify: partial daily withdrawal at 80/20.
    s = revalue_live_state(create_live_account("tradeify_elite_50k", catalog=live_catalog), 5000.0, catalog=live_catalog)
    r = execute_live_payout(s, LivePayoutContext(requested_gross=2000.0), catalog=cat)
    fixtures.append({"id": "P03_TRADEIFY_PARTIAL", "result": r, "expected": {"trader_cash": 1600.0, "firm_share": 400.0, "balance_after": 3000.0, "status_after": "ACTIVE"}})

    # P04 Tradeify: withdrawing the full live balance closes the account.
    s = revalue_live_state(create_live_account("tradeify_elite_50k", catalog=live_catalog), 5000.0, catalog=live_catalog)
    r = execute_live_payout(s, LivePayoutContext(requested_gross=5000.0), catalog=cat)
    fixtures.append({"id": "P04_TRADEIFY_FULL_CLOSE", "result": r, "expected": {"trader_cash": 4000.0, "balance_after": 0.0, "status_after": "CLOSED_FULL_WITHDRAWAL"}})

    # P05 MFFU: use explicit live-profit ledger; do not treat $2,000 seed as payout profit.
    s = revalue_live_state(create_live_account("mffu_flex_live_50k", catalog=live_catalog), 3000.0, catalog=live_catalog)
    r = execute_live_payout(s, LivePayoutContext(requested_gross=500.0, available_live_profit=1000.0), catalog=cat)
    fixtures.append({"id": "P05_MFFU_LIVE_PROFIT_ONLY", "result": r, "expected": {"trader_cash": 400.0, "balance_after": 2500.0, "failure_floor_after": 156.0, "status_after": "ACTIVE"}})

    # P06 Apex: ordinary live payout can only use profits above $3,100 safety net.
    s = revalue_live_state(create_live_account("apex_live_uniform", catalog=live_catalog), 5000.0, catalog=live_catalog)
    r = execute_live_payout(s, LivePayoutContext(requested_gross=1000.0, live_days_elapsed=30), catalog=cat)
    fixtures.append({"id": "P06_APEX_ABOVE_SAFETY_NET", "result": r, "expected": {"trader_cash": 900.0, "balance_after": 4000.0, "status_after": "ACTIVE"}})

    # P07 Apex: after 90 live days, safety-net closeout can withdraw the account and close it.
    s = revalue_live_state(create_live_account("apex_live_uniform", catalog=live_catalog), 3500.0, catalog=live_catalog)
    r = execute_live_payout(s, LivePayoutContext(requested_gross=3500.0, live_days_elapsed=90, allow_safety_net_closeout=True), catalog=cat)
    fixtures.append({"id": "P07_APEX_90DAY_CLOSEOUT", "result": r, "expected": {"trader_cash": 3150.0, "balance_after": 0.0, "status_after": "CLOSED_SAFETY_NET_WITHDRAWAL"}})

    # P08 Topstep pre-30: 5 winning days unlock up to 50% of unlocked balance.
    s = create_live_account("topstep_lfa_50k", catalog=live_catalog, starting_balance_override=10000.0, reserve_balance=40000.0)
    r = execute_live_payout(s, LivePayoutContext(requested_gross=5000.0, winning_days_this_cycle=5, lifetime_winning_days=10), catalog=cat)
    fixtures.append({"id": "P08_TOPSTEP_PRE30_HALF", "result": r, "expected": {"trader_cash": 4500.0, "balance_after": 5000.0, "reserve_balance_after": 40000.0, "status_after": "ACTIVE"}})

    # P09 Topstep post-30: daily full unlocked-balance payout closes account.
    s = create_live_account("topstep_lfa_50k", catalog=live_catalog, starting_balance_override=10000.0, reserve_balance=40000.0)
    s = revalue_live_state(s, 8000.0, catalog=live_catalog)
    r = execute_live_payout(s, LivePayoutContext(requested_gross=8000.0, winning_days_this_cycle=0, lifetime_winning_days=30), catalog=cat)
    fixtures.append({"id": "P09_TOPSTEP_POST30_FULL_CLOSE", "result": r, "expected": {"trader_cash": 7200.0, "balance_after": 0.0, "reserve_balance_after": 40000.0, "status_after": "CLOSED_FULL_WITHDRAWAL"}})

    # P10 FundedNext remains non-executable because its live state is unresolved.
    blocked = False
    msg = ""
    try:
        create_live_account("fundednext_rapid_live_50k", catalog=live_catalog)
    except LiveStateError as exc:
        blocked = True
        msg = str(exc)
    fixtures.append({"id": "P10_FUNDEDNEXT_CONFLICT_BLOCK", "special": True, "pass": blocked and bool(msg), "checks": [
        {"field": "live profile blocked", "expected": True, "actual": blocked, "pass": blocked},
        {"field": "explicit reason", "expected": "non-empty", "actual": msg, "pass": bool(msg)},
    ]})

    results: List[Dict[str, Any]] = []
    for f in fixtures:
        if f.get("special"):
            results.append({"fixture_id": f["id"], "pass": f["pass"], "checks": f["checks"]})
            continue
        actual = payout_result_as_dict(f["result"])
        checks: List[Dict[str, Any]] = []
        for field, expected in f["expected"].items():
            got = actual.get(field)
            if isinstance(expected, float):
                ok = got is not None and math.isclose(float(got), expected, abs_tol=1e-6)
            else:
                ok = got == expected
            checks.append({"field": field, "expected": expected, "actual": got, "pass": ok})
        results.append({"fixture_id": f["id"], "pass": all(c["pass"] for c in checks), "checks": checks})

    passed = sum(1 for x in results if x["pass"])
    return {
        "suite_version": LIVE_PAYOUT_ENGINE_VERSION,
        "payout_schema": cat.get("schema_version"),
        "policies_verified_as_of": cat.get("verified_as_of"),
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "all_pass": passed == len(results),
        "results": results,
    }
