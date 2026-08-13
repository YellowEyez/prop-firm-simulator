"""Project StarBase v5H sim-funded to live transition engine (Step 29).

This module models the transition event itself. It intentionally does not execute
live withdrawals (Step 30) or promote all transition-value dispositions into the
final household forfeiture ledger (Step 31).

Core safety principle: discretionary firm decisions are event inputs, never inferred
from historical trade performance.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from starbase_integrity import sha256_text, stable_json
from starbase_live import LiveAccountState, LiveStateError, create_live_account, load_live_profiles, state_as_dict
from starbase_paths import asset_path

TRANSITION_ENGINE_VERSION = "5H.1.0"
TRANSITION_SCHEMA_VERSION = "1.0.0"


class LiveTransitionError(ValueError):
    pass


@dataclass(frozen=True)
class SimTransitionAccount:
    account_id: str
    firm_id: str
    product_id: str
    stage: str  # EVALUATION | SIM_FUNDED
    account_size: int
    status: str = "ACTIVE"
    current_profit_balance: float = 0.0
    payout_count: int = 0
    consecutive_approved_payouts: int = 0
    gross_payouts_received: float = 0.0
    trader_wallet_cash_received: float = 0.0
    claimable_now_trader_cash: float = 0.0
    accrued_blocked_trader_cash: float = 0.0
    acquisition_cost_basis: Optional[float] = None


@dataclass(frozen=True)
class TransitionAccountDisposition:
    account_id: str
    prior_stage: str
    prior_status: str
    new_status: str
    becomes_live: bool
    live_profile_id: Optional[str]
    current_profit_balance: float
    cash_already_received_preserved: float
    claimable_now_at_transition: float
    accrued_blocked_at_transition: float
    acquisition_cost_refund: float
    transition_value_bucket: str
    transition_value_amount: float
    note: str


@dataclass(frozen=True)
class LiveTransitionResult:
    transition_id: str
    policy_id: str
    firm_id: str
    trigger_model: str
    trigger_reason: str
    trigger_satisfied: bool
    explicit_callup_received: bool
    transition_executed: bool
    decision_grade: str
    dispositions: tuple[TransitionAccountDisposition, ...]
    live_accounts: tuple[LiveAccountState, ...]
    cash_already_received_preserved: float
    refunds_created: float
    final_reward_cash: float
    bonus_vault_tracked: float
    reward_pool_tracked: float
    topstep_reserve_tracked: float
    topstep_seed_supplement: float
    unresolved_transition_value: float
    known_noncarried_sim_value: float
    excess_transfer_value: float
    simulated_accounts_closed: int
    simulated_accounts_suspended: int
    source_accounts_becoming_live: int
    warnings: tuple[str, ...]
    source_urls: tuple[str, ...]
    rule_snapshot_hash: str


def load_transition_policies(path: Optional[str | Path] = None) -> Dict[str, Any]:
    p = Path(path) if path else asset_path("starbase_live_transitions_v1.json")
    data = json.loads(Path(p).read_text(encoding="utf-8"))
    if data.get("schema_version") != TRANSITION_SCHEMA_VERSION:
        raise LiveTransitionError(f"Unsupported transition policy schema: {data.get('schema_version')}")
    return data


def transition_policy_by_id(catalog: Dict[str, Any], policy_id: str) -> Dict[str, Any]:
    for policy in catalog.get("policies", []):
        if policy.get("policy_id") == policy_id:
            return policy
    raise LiveTransitionError(f"Unknown transition policy: {policy_id}")


def transition_policy_rows(catalog: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    cat = catalog or load_transition_policies()
    rows: List[Dict[str, Any]] = []
    for p in cat.get("policies", []):
        rows.append({
            "Firm": p.get("firm_name"),
            "Policy": p.get("policy_id"),
            "Trigger Model": p.get("trigger_model"),
            "Transition Grade": p.get("transition_grade"),
            "Explicit Call-up Required": bool(p.get("execution_requires_explicit_callup")),
            "Closure Scope": p.get("closure_scope"),
            "Max Live Accounts": p.get("max_live_accounts"),
        })
    return rows


def _active(accounts: Iterable[SimTransitionAccount]) -> List[SimTransitionAccount]:
    return [a for a in accounts if str(a.status).upper() in {"ACTIVE", "PAYOUT_CYCLE_COMPLETE", "PAYOUT_READY"}]


def _cash_preserved(accounts: Sequence[SimTransitionAccount]) -> float:
    return float(sum(max(0.0, float(a.trader_wallet_cash_received)) for a in accounts))


def _policy_hash(catalog: Dict[str, Any], policy: Dict[str, Any], inputs: Dict[str, Any]) -> str:
    payload = {
        "transition_engine_version": TRANSITION_ENGINE_VERSION,
        "transition_schema_version": catalog.get("schema_version"),
        "transition_verified_as_of": catalog.get("verified_as_of"),
        "policy": policy,
        "inputs": inputs,
    }
    return sha256_text(stable_json(payload))


def _empty_disposition(a: SimTransitionAccount, *, new_status: str, note: str, bucket: str = "NONE", amount: float = 0.0, refund: float = 0.0, becomes_live: bool = False, live_profile_id: Optional[str] = None) -> TransitionAccountDisposition:
    return TransitionAccountDisposition(
        account_id=a.account_id,
        prior_stage=a.stage,
        prior_status=a.status,
        new_status=new_status,
        becomes_live=becomes_live,
        live_profile_id=live_profile_id,
        current_profit_balance=float(a.current_profit_balance),
        cash_already_received_preserved=float(a.trader_wallet_cash_received),
        claimable_now_at_transition=float(a.claimable_now_trader_cash),
        accrued_blocked_at_transition=float(a.accrued_blocked_trader_cash),
        acquisition_cost_refund=float(refund),
        transition_value_bucket=bucket,
        transition_value_amount=float(amount),
        note=note,
    )


def _lucid_transition(policy: Dict[str, Any], accounts: Sequence[SimTransitionAccount], explicit_callup: bool) -> Dict[str, Any]:
    if not explicit_callup:
        return {"trigger_satisfied": False, "decision_grade": "AWAITING_DISCRETIONARY_CALLUP", "dispositions": [], "live_accounts": [], "warnings": ["Lucid review eligibility does not guarantee a live transition. An explicit risk-team call-up is required."], "refunds": 0.0, "vault": 0.0, "reward_pool": 0.0, "reserve": 0.0, "seed": 0.0, "unresolved": 0.0, "noncarried": 0.0, "excess": 0.0, "closed": 0, "suspended": 0, "source_live": 0}
    live_catalog = load_live_profiles()
    active = _active(accounts)
    live_sources = [a for a in active if a.stage == "SIM_FUNDED" and a.payout_count >= 1]
    live_sources = live_sources[: int(policy.get("max_live_accounts") or len(live_sources))]
    live_ids = {a.account_id for a in live_sources}
    dispositions: List[TransitionAccountDisposition] = []
    lives: List[LiveAccountState] = []
    refunds = 0.0
    noncarried = 0.0
    unresolved = 0.0
    for a in active:
        profit = max(0.0, float(a.current_profit_balance))
        if a.account_id in live_ids:
            profile = (policy.get("live_profile_by_size") or {}).get(str(a.account_size))
            if not profile:
                raise LiveTransitionError(f"No Lucid live profile mapping for {a.account_size}")
            lives.append(create_live_account(profile, catalog=live_catalog, account_id=f"LIVE-{a.account_id}"))
            noncarried += profit
            dispositions.append(_empty_disposition(a, new_status="CLOSED_MOVED_LIVE", note="Eligible funded account moves to a fresh $0 Lucid live account. Sim profit does not carry.", bucket="KNOWN_NONCARRIED_SIM_PROFIT_PENDING_STEP31", amount=profit, becomes_live=True, live_profile_id=profile))
        elif a.stage == "SIM_FUNDED" and a.payout_count == 0:
            refund = float(a.acquisition_cost_basis or 0.0)
            refunds += refund
            noncarried += profit
            dispositions.append(_empty_disposition(a, new_status="CLOSED_ZERO_PAYOUT_REFUND", note="Zero-payout funded account does not move live; original evaluation cost is refundable when known.", bucket="KNOWN_NONCARRIED_SIM_PROFIT_PENDING_STEP31", amount=profit, refund=refund))
        else:
            unresolved += profit
            dispositions.append(_empty_disposition(a, new_status="CLOSED_BY_LIVE_TRANSITION", note="All remaining simulated prop accounts close on Lucid live transition.", bucket="TRANSITION_VALUE_PENDING_STEP31", amount=profit))
    return {"trigger_satisfied": True, "decision_grade": "EXPLICIT_DISCRETIONARY_CALLUP", "dispositions": dispositions, "live_accounts": lives, "warnings": [], "refunds": refunds, "vault": 0.0, "reward_pool": 0.0, "reserve": 0.0, "seed": 0.0, "unresolved": unresolved, "noncarried": noncarried, "excess": 0.0, "closed": len(dispositions), "suspended": 0, "source_live": len(live_sources)}


def _tradeify_transition(policy: Dict[str, Any], accounts: Sequence[SimTransitionAccount], explicit_callup: bool, household_payouts_since_last_transition: int) -> Dict[str, Any]:
    active = _active(accounts)
    max_single = max([a.payout_count for a in active if a.stage == "SIM_FUNDED"] or [0])
    eligible_for_review = max_single >= int(policy["review_eligibility"]["single_account_payouts"]) or int(household_payouts_since_last_transition) >= int(policy["review_eligibility"]["household_payouts_since_last_transition"])
    if not explicit_callup or not eligible_for_review:
        if explicit_callup and not eligible_for_review:
            grade = "CALLUP_INPUT_CONFLICTS_WITH_DOCUMENTED_MINIMUMS"
            warning = "Tradeify call-up input was supplied before the documented minimum eligibility threshold. StarBase will not execute that transition."
        else:
            grade = "REVIEW_ELIGIBLE_AWAITING_SELECTION" if eligible_for_review else "NOT_YET_REVIEW_ELIGIBLE"
            warning = "Tradeify eligibility thresholds are minimum consideration thresholds, not automatic live qualification."
        return {"trigger_satisfied": False, "decision_grade": grade, "dispositions": [], "live_accounts": [], "warnings": [warning], "refunds": 0.0, "vault": 0.0, "reward_pool": 0.0, "reserve": 0.0, "seed": 0.0, "unresolved": 0.0, "noncarried": 0.0, "excess": 0.0, "closed": 0, "suspended": 0, "source_live": 0}
    live_catalog = load_live_profiles()
    live_sources = [a for a in active if a.stage == "SIM_FUNDED" and a.payout_count >= 1]
    live_sources = live_sources[: int(policy.get("max_live_accounts") or len(live_sources))]
    live_ids = {a.account_id for a in live_sources}
    dispositions: List[TransitionAccountDisposition] = []
    lives: List[LiveAccountState] = []
    reward_pool = 0.0
    noncarried = 0.0
    unresolved = 0.0
    for a in active:
        profit = max(0.0, float(a.current_profit_balance))
        if a.account_id in live_ids:
            profile = (policy.get("live_profile_by_size") or {}).get(str(a.account_size))
            if not profile:
                raise LiveTransitionError(f"No Tradeify Elite profile mapping for {a.account_size}")
            lives.append(create_live_account(profile, catalog=live_catalog, account_id=f"LIVE-{a.account_id}"))
            reward_pool += float((policy.get("base_reward_pool_by_size") or {}).get(str(a.account_size), 0.0))
            noncarried += profit
            dispositions.append(_empty_disposition(a, new_status="CLOSED_MOVED_ELITE", note="Eligible funded account becomes a fresh $0 Elite Live account. Sim profit/progress does not carry.", bucket="KNOWN_NONCARRIED_SIM_PROFIT_PENDING_STEP31", amount=profit, becomes_live=True, live_profile_id=profile))
        else:
            unresolved += profit
            dispositions.append(_empty_disposition(a, new_status="CLOSED_BY_ELITE_TRANSITION", note="All Sim Funded and evaluation accounts close when the trader is selected for Elite.", bucket="TRANSITION_VALUE_PENDING_STEP31", amount=profit))
    return {"trigger_satisfied": True, "decision_grade": "EXPLICIT_MANDATORY_SELECTION", "dispositions": dispositions, "live_accounts": lives, "warnings": [], "refunds": 0.0, "vault": 0.0, "reward_pool": reward_pool, "reserve": 0.0, "seed": 0.0, "unresolved": unresolved, "noncarried": noncarried, "excess": 0.0, "closed": len(dispositions), "suspended": 0, "source_live": len(live_sources)}


def _mffu_transition(policy: Dict[str, Any], accounts: Sequence[SimTransitionAccount], explicit_callup: bool, household_total_sim_payouts: float) -> Dict[str, Any]:
    active = _active(accounts)
    funded = [a for a in active if a.stage == "SIM_FUNDED"]
    same_account = [a for a in funded if a.consecutive_approved_payouts >= int(policy["review_eligibility"]["same_account_consecutive_approved_payouts"])]
    cap_hit = float(household_total_sim_payouts) >= float(policy["review_eligibility"]["household_total_sim_payout_cap"])
    trigger_sources = same_account
    trigger_satisfied = bool(trigger_sources or cap_hit or explicit_callup)
    if not trigger_satisfied:
        return {"trigger_satisfied": False, "decision_grade": "NOT_YET_TRIGGERED", "dispositions": [], "live_accounts": [], "warnings": [], "refunds": 0.0, "vault": 0.0, "reward_pool": 0.0, "reserve": 0.0, "seed": 0.0, "unresolved": 0.0, "noncarried": 0.0, "excess": 0.0, "closed": 0, "suspended": 0, "source_live": 0}
    if not trigger_sources:
        if not funded:
            raise LiveTransitionError("MFFU transition has no active Sim Funded account to move live.")
        trigger_sources = [max(funded, key=lambda a: (a.payout_count, a.current_profit_balance))]
    live_catalog = load_live_profiles()
    live_ids = {a.account_id for a in trigger_sources}
    dispositions: List[TransitionAccountDisposition] = []
    lives: List[LiveAccountState] = []
    unresolved = 0.0
    closed = 0
    suspended = 0
    for a in active:
        profit = max(0.0, float(a.current_profit_balance))
        if a.account_id in live_ids:
            profile = (policy.get("live_profile_by_size") or {}).get(str(a.account_size))
            if not profile:
                raise LiveTransitionError(f"No MFFU live profile mapping for {a.account_size}")
            lives.append(create_live_account(profile, catalog=live_catalog, account_id=f"LIVE-{a.account_id}"))
            unresolved += profit
            closed += 1
            dispositions.append(_empty_disposition(a, new_status="CLOSED_MOVED_LIVE", note="Triggering Flex Sim Funded account moves to Live. Official current source does not state that residual Sim profit becomes live cash, so StarBase preserves it as unresolved until Step 31.", bucket="TRANSITION_VALUE_PENDING_STEP31", amount=profit, becomes_live=True, live_profile_id=profile))
        else:
            unresolved += profit
            suspended += 1
            dispositions.append(_empty_disposition(a, new_status="SUSPENDED_WHILE_LIVE", note="MFFU does not allow simultaneous Sim and Live trading. Remaining simulated accounts are preserved but suspended rather than silently failed.", bucket="SUSPENDED_SIM_VALUE", amount=profit))
    return {"trigger_satisfied": True, "decision_grade": "AUTOMATIC_THRESHOLD_OR_EXPLICIT_RISK_REVIEW", "dispositions": dispositions, "live_accounts": lives, "warnings": ["Remaining Sim accounts are suspended while Live is active; Step 31 will finalize any eventual value disposition."], "refunds": 0.0, "vault": 0.0, "reward_pool": 0.0, "reserve": 0.0, "seed": 0.0, "unresolved": unresolved, "noncarried": 0.0, "excess": 0.0, "closed": closed, "suspended": suspended, "source_live": len(trigger_sources)}


def _apex_transition(policy: Dict[str, Any], accounts: Sequence[SimTransitionAccount], explicit_callup: bool, accept_invitation: bool) -> Dict[str, Any]:
    if not explicit_callup:
        return {"trigger_satisfied": False, "decision_grade": "AWAITING_DISCRETIONARY_INVITATION", "dispositions": [], "live_accounts": [], "warnings": ["Apex live selection is discretionary and cannot be inferred from the trade ledger."], "refunds": 0.0, "vault": 0.0, "reward_pool": 0.0, "reserve": 0.0, "seed": 0.0, "unresolved": 0.0, "noncarried": 0.0, "excess": 0.0, "closed": 0, "suspended": 0, "source_live": 0, "final_reward": 0.0}
    active = _active(accounts)
    dispositions: List[TransitionAccountDisposition] = []
    refunds = 0.0
    vault = 0.0
    unresolved = 0.0
    if not accept_invitation:
        final_reward = float((policy.get("decline_live_invitation") or {}).get("final_reward") or 0.0)
        for a in active:
            profit = max(0.0, float(a.current_profit_balance))
            unresolved += profit
            dispositions.append(_empty_disposition(a, new_status="CLOSED_LIVE_INVITATION_DECLINED", note="Apex live invitation declined; simulated services end. Bonus Vault and simulated balances are not preserved.", bucket="DECLINE_VALUE_PENDING_STEP31", amount=profit))
        return {"trigger_satisfied": True, "decision_grade": "LIVE_INVITATION_DECLINED", "dispositions": dispositions, "live_accounts": [], "warnings": [], "refunds": 0.0, "vault": 0.0, "reward_pool": 0.0, "reserve": 0.0, "seed": 0.0, "unresolved": unresolved, "noncarried": 0.0, "excess": 0.0, "closed": len(dispositions), "suspended": 0, "source_live": 0, "final_reward": final_reward}
    for a in active:
        profit = max(0.0, float(a.current_profit_balance))
        if a.stage == "EVALUATION":
            refund = float(a.acquisition_cost_basis or 0.0)
            refunds += refund
            dispositions.append(_empty_disposition(a, new_status="CLOSED_REFUNDED_ACTIVE_EVALUATION", note="Active Apex evaluation closes on live selection and its known evaluation cost is refunded.", bucket="NONE", amount=0.0, refund=refund))
        else:
            vault += profit
            dispositions.append(_empty_disposition(a, new_status="DEACTIVATED_TO_BONUS_VAULT", note="Open profitable PA simulated profit is tracked in the Apex Bonus Vault; the PA itself is deactivated.", bucket="BONUS_VAULT_TRACKED", amount=profit))
    live = create_live_account(str(policy.get("live_profile_id")), catalog=load_live_profiles(), account_id="LIVE-APEX-001", bonus_vault_balance=vault)
    return {"trigger_satisfied": True, "decision_grade": "EXPLICIT_DISCRETIONARY_INVITATION_ACCEPTED", "dispositions": dispositions, "live_accounts": [live], "warnings": ["Apex starts with one live account; additional live accounts are later scaling events, not created at transition."], "refunds": refunds, "vault": vault, "reward_pool": 0.0, "reserve": 0.0, "seed": 0.0, "unresolved": 0.0, "noncarried": 0.0, "excess": 0.0, "closed": len(dispositions), "suspended": 0, "source_live": 1, "final_reward": 0.0}


def _round_topstep_tier(avg_size: float) -> int:
    for tier in (50000, 100000, 150000):
        if avg_size <= tier:
            return tier
    return 150000


def _topstep_transition(policy: Dict[str, Any], accounts: Sequence[SimTransitionAccount], explicit_callup: bool) -> Dict[str, Any]:
    if not explicit_callup:
        return {"trigger_satisfied": False, "decision_grade": "AWAITING_RISK_TEAM_CALLUP", "dispositions": [], "live_accounts": [], "warnings": ["Topstep live call-up is discretionary and cannot be inferred from a fixed payout count."], "refunds": 0.0, "vault": 0.0, "reward_pool": 0.0, "reserve": 0.0, "seed": 0.0, "unresolved": 0.0, "noncarried": 0.0, "excess": 0.0, "closed": 0, "suspended": 0, "source_live": 0}
    active = [a for a in _active(accounts) if a.stage == "SIM_FUNDED"]
    if not active:
        raise LiveTransitionError("Topstep call-up requires at least one active XFA.")
    with_payout = [a for a in active if a.payout_count >= 1]
    eligible = with_payout if with_payout else active
    avg_size = sum(a.account_size for a in eligible) / len(eligible)
    lfa_size = _round_topstep_tier(avg_size)
    combined = float(sum(max(0.0, a.current_profit_balance) for a in eligible))
    transferable = min(combined, float(lfa_size))
    starting = min(max(0.20 * transferable, 10000.0), float(lfa_size))
    reserve = max(transferable - starting, 0.0)
    seed = max(starting - transferable, 0.0)
    excess = max(combined - float(lfa_size), 0.0)
    dispositions: List[TransitionAccountDisposition] = []
    eligible_ids = {a.account_id for a in eligible}
    for a in active:
        bucket = "TRANSFERRED_TO_LIVE_OR_RESERVE" if a.account_id in eligible_ids else "CLOSED_XFA_NOT_USED_FOR_LIVE_SIZE"
        dispositions.append(_empty_disposition(a, new_status="CLOSED_ON_LIVE_CALLUP", note="All XFAs close when Topstep calls the trader to Live.", bucket=bucket, amount=max(0.0, float(a.current_profit_balance))))
    profile_id = (policy.get("live_profile_by_size") or {}).get(str(lfa_size))
    if not profile_id:
        raise LiveTransitionError(f"No Topstep live profile mapping for derived LFA size {lfa_size}")
    live = create_live_account(str(profile_id), catalog=load_live_profiles(), account_id="LIVE-TOPSTEP-001", starting_balance_override=starting, reserve_balance=reserve)
    return {"trigger_satisfied": True, "decision_grade": "EXPLICIT_RISK_TEAM_CALLUP", "dispositions": dispositions, "live_accounts": [live], "warnings": [f"LFA size determined as ${lfa_size:,.0f} from average eligible XFA size ${avg_size:,.2f}."], "refunds": 0.0, "vault": 0.0, "reward_pool": 0.0, "reserve": reserve, "seed": seed, "unresolved": 0.0, "noncarried": 0.0, "excess": excess, "closed": len(dispositions), "suspended": 0, "source_live": 1, "lfa_size": lfa_size}


def execute_live_transition(
    policy_id: str,
    accounts: Sequence[SimTransitionAccount],
    *,
    catalog: Optional[Dict[str, Any]] = None,
    explicit_callup: bool = False,
    trigger_reason: str = "",
    household_payouts_since_last_transition: int = 0,
    household_total_sim_payouts: float = 0.0,
    accept_invitation: bool = True,
) -> LiveTransitionResult:
    cat = catalog or load_transition_policies()
    policy = transition_policy_by_id(cat, policy_id)
    if policy.get("transition_grade") == "BLOCKED_CONFLICTING_LIVE_PROFILE":
        raise LiveTransitionError("Transition is blocked because the destination live profile has unresolved conflicting official text.")
    firm_id = str(policy.get("firm_id"))
    bad_firms = sorted({a.firm_id for a in accounts if a.firm_id != firm_id})
    if bad_firms:
        raise LiveTransitionError(f"Transition input contains accounts from other firms: {bad_firms}")
    if not accounts:
        raise LiveTransitionError("At least one simulated account is required.")

    if policy_id == "lucid_standard_live":
        core = _lucid_transition(policy, accounts, explicit_callup)
    elif policy_id == "tradeify_elite":
        core = _tradeify_transition(policy, accounts, explicit_callup, household_payouts_since_last_transition)
    elif policy_id == "mffu_flex_live":
        core = _mffu_transition(policy, accounts, explicit_callup, household_total_sim_payouts)
    elif policy_id == "apex_live_invitation":
        core = _apex_transition(policy, accounts, explicit_callup, accept_invitation)
    elif policy_id == "topstep_lfa_callup":
        core = _topstep_transition(policy, accounts, explicit_callup)
    else:
        raise LiveTransitionError(f"No Step-29 transition handler for {policy_id}")

    trigger_satisfied = bool(core.get("trigger_satisfied"))
    executed = trigger_satisfied and bool(core.get("dispositions") or core.get("live_accounts") or core.get("final_reward"))
    inputs = {
        "policy_id": policy_id,
        "accounts": [asdict(a) for a in accounts],
        "explicit_callup": explicit_callup,
        "trigger_reason": trigger_reason,
        "household_payouts_since_last_transition": int(household_payouts_since_last_transition),
        "household_total_sim_payouts": float(household_total_sim_payouts),
        "accept_invitation": bool(accept_invitation),
    }
    rid = _policy_hash(cat, policy, inputs)
    return LiveTransitionResult(
        transition_id=f"TR-{rid[:12]}",
        policy_id=policy_id,
        firm_id=firm_id,
        trigger_model=str(policy.get("trigger_model")),
        trigger_reason=str(trigger_reason or "EXPLICIT_TEST_EVENT"),
        trigger_satisfied=trigger_satisfied,
        explicit_callup_received=bool(explicit_callup),
        transition_executed=executed,
        decision_grade=str(core.get("decision_grade")),
        dispositions=tuple(core.get("dispositions") or []),
        live_accounts=tuple(core.get("live_accounts") or []),
        cash_already_received_preserved=_cash_preserved(accounts),
        refunds_created=float(core.get("refunds") or 0.0),
        final_reward_cash=float(core.get("final_reward") or 0.0),
        bonus_vault_tracked=float(core.get("vault") or 0.0),
        reward_pool_tracked=float(core.get("reward_pool") or 0.0),
        topstep_reserve_tracked=float(core.get("reserve") or 0.0),
        topstep_seed_supplement=float(core.get("seed") or 0.0),
        unresolved_transition_value=float(core.get("unresolved") or 0.0),
        known_noncarried_sim_value=float(core.get("noncarried") or 0.0),
        excess_transfer_value=float(core.get("excess") or 0.0),
        simulated_accounts_closed=int(core.get("closed") or 0),
        simulated_accounts_suspended=int(core.get("suspended") or 0),
        source_accounts_becoming_live=int(core.get("source_live") or 0),
        warnings=tuple(str(x) for x in (core.get("warnings") or [])),
        source_urls=tuple(str(x) for x in (policy.get("source_urls") or [])),
        rule_snapshot_hash=rid,
    )


def transition_result_as_dict(result: LiveTransitionResult) -> Dict[str, Any]:
    d = asdict(result)
    d["live_accounts"] = [state_as_dict(x) for x in result.live_accounts]
    d["dispositions"] = [asdict(x) for x in result.dispositions]
    return d


def run_live_transition_verification(catalog: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cat = catalog or load_transition_policies()
    fixtures: List[Dict[str, Any]] = []

    lucid_accounts = [
        SimTransitionAccount("L-F1", "lucid", "lucid_flex", "SIM_FUNDED", 50000, current_profit_balance=900, payout_count=2, trader_wallet_cash_received=1200, acquisition_cost_basis=100),
        SimTransitionAccount("L-F2", "lucid", "lucid_flex", "SIM_FUNDED", 50000, current_profit_balance=400, payout_count=1, trader_wallet_cash_received=500, acquisition_cost_basis=100),
        SimTransitionAccount("L-F3", "lucid", "lucid_flex", "SIM_FUNDED", 50000, current_profit_balance=250, payout_count=0, acquisition_cost_basis=100),
        SimTransitionAccount("L-E1", "lucid", "lucid_flex", "EVALUATION", 50000, current_profit_balance=0, acquisition_cost_basis=100),
    ]
    r = execute_live_transition("lucid_standard_live", lucid_accounts, catalog=cat, explicit_callup=True, trigger_reason="RISK_TEAM_SELECTED")
    fixtures.append({"id": "T01_LUCID_ALL_SIM_CLOSE", "result": r, "expected": {"transition_executed": True, "source_accounts_becoming_live": 2, "simulated_accounts_closed": 4, "refunds_created": 100.0, "known_noncarried_sim_value": 1550.0, "cash_already_received_preserved": 1700.0, "live_count": 2, "live_start_sum": 0.0}})

    tradeify_accounts = [
        SimTransitionAccount("T-F1", "tradeify", "tradeify_select_flex", "SIM_FUNDED", 50000, current_profit_balance=1200, payout_count=3, trader_wallet_cash_received=2200),
        SimTransitionAccount("T-F2", "tradeify", "tradeify_select_daily", "SIM_FUNDED", 50000, current_profit_balance=600, payout_count=1, trader_wallet_cash_received=700),
        SimTransitionAccount("T-E1", "tradeify", "tradeify_select_flex", "EVALUATION", 50000, current_profit_balance=0),
    ]
    r = execute_live_transition("tradeify_elite", tradeify_accounts, catalog=cat, explicit_callup=True, trigger_reason="TRADEIFY_SELECTED", household_payouts_since_last_transition=4)
    fixtures.append({"id": "T02_TRADEIFY_ELITE_MULTI_ACCOUNT", "result": r, "expected": {"transition_executed": True, "source_accounts_becoming_live": 2, "simulated_accounts_closed": 3, "reward_pool_tracked": 8000.0, "known_noncarried_sim_value": 1800.0, "cash_already_received_preserved": 2900.0, "live_count": 2}})

    mffu_accounts = [
        SimTransitionAccount("M-F1", "mffu", "mffu_flex_50k", "SIM_FUNDED", 50000, current_profit_balance=900, payout_count=5, consecutive_approved_payouts=5, trader_wallet_cash_received=8000),
        SimTransitionAccount("M-F2", "mffu", "mffu_flex_50k", "SIM_FUNDED", 50000, current_profit_balance=350, payout_count=1),
    ]
    r = execute_live_transition("mffu_flex_live", mffu_accounts, catalog=cat, trigger_reason="FIVE_CONSECUTIVE_APPROVED_PAYOUTS")
    fixtures.append({"id": "T03_MFFU_THRESHOLD_TRANSITION", "result": r, "expected": {"transition_executed": True, "source_accounts_becoming_live": 1, "simulated_accounts_closed": 1, "simulated_accounts_suspended": 1, "unresolved_transition_value": 1250.0, "live_count": 1, "live_start_sum": 2000.0}})

    apex_accounts = [
        SimTransitionAccount("A-PA1", "apex", "apex_eod", "SIM_FUNDED", 50000, current_profit_balance=2200, payout_count=1, trader_wallet_cash_received=1500),
        SimTransitionAccount("A-PA2", "apex", "apex_eod", "SIM_FUNDED", 100000, current_profit_balance=1800, payout_count=0),
        SimTransitionAccount("A-E1", "apex", "apex_eod", "EVALUATION", 50000, acquisition_cost_basis=167),
    ]
    r = execute_live_transition("apex_live_invitation", apex_accounts, catalog=cat, explicit_callup=True, trigger_reason="APEX_INVITATION_ACCEPTED")
    fixtures.append({"id": "T04_APEX_BONUS_VAULT", "result": r, "expected": {"transition_executed": True, "source_accounts_becoming_live": 1, "simulated_accounts_closed": 3, "bonus_vault_tracked": 4000.0, "refunds_created": 167.0, "cash_already_received_preserved": 1500.0, "live_count": 1, "live_start_sum": 0.0}})

    r = execute_live_transition("apex_live_invitation", apex_accounts, catalog=cat, explicit_callup=True, trigger_reason="APEX_INVITATION_DECLINED", accept_invitation=False)
    fixtures.append({"id": "T05_APEX_DECLINE_FINAL_REWARD", "result": r, "expected": {"transition_executed": True, "source_accounts_becoming_live": 0, "simulated_accounts_closed": 3, "final_reward_cash": 3000.0, "live_count": 0}})

    topstep_accounts = [
        SimTransitionAccount("TS-1", "topstep", "topstep_standard", "SIM_FUNDED", 50000, current_profit_balance=10000, payout_count=1),
        SimTransitionAccount("TS-2", "topstep", "topstep_standard", "SIM_FUNDED", 50000, current_profit_balance=10000, payout_count=1),
        SimTransitionAccount("TS-3", "topstep", "topstep_consistency", "SIM_FUNDED", 50000, current_profit_balance=10000, payout_count=1),
        SimTransitionAccount("TS-4", "topstep", "topstep_consistency", "SIM_FUNDED", 50000, current_profit_balance=10000, payout_count=1),
        SimTransitionAccount("TS-5", "topstep", "topstep_standard", "SIM_FUNDED", 150000, current_profit_balance=10000, payout_count=1),
    ]
    r = execute_live_transition("topstep_lfa_callup", topstep_accounts, catalog=cat, explicit_callup=True, trigger_reason="RISK_TEAM_CALLUP")
    fixtures.append({"id": "T06_TOPSTEP_RESERVE_DERIVATION", "result": r, "expected": {"transition_executed": True, "source_accounts_becoming_live": 1, "simulated_accounts_closed": 5, "topstep_reserve_tracked": 40000.0, "topstep_seed_supplement": 0.0, "excess_transfer_value": 0.0, "live_count": 1, "live_start_sum": 10000.0, "live_source_size": 100000}})

    blocked = False
    blocked_message = ""
    try:
        execute_live_transition("fundednext_rapid_live", [SimTransitionAccount("FN-1", "fundednext", "fundednext_rapid", "SIM_FUNDED", 50000, current_profit_balance=2000)], catalog=cat, explicit_callup=True)
    except LiveTransitionError as exc:
        blocked = True
        blocked_message = str(exc)
    fixtures.append({"id": "T07_FUNDEDNEXT_CONFLICT_BLOCK", "special": True, "pass": blocked and bool(blocked_message), "checks": [{"field": "transition blocked", "expected": True, "actual": blocked, "pass": blocked}, {"field": "explicit reason", "expected": "non-empty", "actual": blocked_message, "pass": bool(blocked_message)}]})

    results: List[Dict[str, Any]] = []
    for f in fixtures:
        if f.get("special"):
            results.append({"fixture_id": f["id"], "pass": f["pass"], "checks": f["checks"]})
            continue
        r: LiveTransitionResult = f["result"]
        actual = transition_result_as_dict(r)
        derived = {
            "live_count": len(r.live_accounts),
            "live_start_sum": sum(x.starting_balance for x in r.live_accounts),
            "live_source_size": r.live_accounts[0].source_account_size if r.live_accounts else None,
        }
        actual.update(derived)
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
        "suite_version": TRANSITION_ENGINE_VERSION,
        "transition_schema": cat.get("schema_version"),
        "policies_verified_as_of": cat.get("verified_as_of"),
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "all_pass": passed == len(results),
        "results": results,
    }
