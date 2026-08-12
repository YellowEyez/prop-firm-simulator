"""Project StarBase v5B single-product funded fleet economics engine.

Purpose
-------
Turn an audited TradingView strategy/profile into a persistent fleet of independently
stateful simulated-funded prop accounts while preserving StarBase's 6 PM ET futures
sessions and one-trade-per-account/session routing semantics.

v5B deliberately limits itself to ONE product/account-size and FUNDED-ONLY research.
It adds two fleet modes:
  * FIXED_FLEET: use exactly N persistent funded accounts, no automatic replacements.
  * FORCE_100_CAPTURE: provision fresh funded accounts on demand so every eligible
    strategy signal receives an account slot (account-count rules intentionally ignored).

v5B adds an explicit acquisition-cost basis, ending payout-inventory valuation, Maintain-N replacement research, and bottleneck/forfeiture ledgers. Exact evaluation-to-funded manufacturing economics remain a later lifecycle step, so evaluation-based funded-only runs must use a clearly labeled effective-cost assumption or remain unknown-cost inventory research.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from io import BytesIO
import json
import math
from typing import Any, Dict, List, Optional, Tuple
import zipfile

import pandas as pd

from starbase_historical_runner import (
    HistoricalRunnerError,
    RunnerConfig,
    DrawdownPolicy,
    _find_stage,
    resolve_drawdown_policy,
    _initial_floor,
    _eod_update_floor,
    _intraday_ratchet_floor,
    _trade_low,
    _trade_peak,
)
from starbase_integrity import assess_rule_coverage, sha256_text, stable_json
from starbase_economics import AcquisitionCostPolicy
from starbase_lifecycle import (
    LifecycleConfig,
    _eligible_work,
    _resolve_start_balance,
    _payout_quote,
    _payout_share,
    _funded_floor_after_payout,
    _PAYOUT_ENGINE_SUPPORT,
)

FLEET_ENGINE_VERSION = "5.0B"
FLEET_SCHEMA_VERSION = "5B.0.0"


@dataclass(frozen=True)
class FleetConfig:
    product_id: str
    account_size: int
    capacity_mode: str = "FIXED_FLEET"  # FIXED_FLEET | MAINTAIN_FIXED_ACTIVE | FORCE_100_CAPTURE
    fixed_accounts: int = 10
    max_trades_per_account_per_session: int = 1
    commission_per_contract_round_trip: float = 0.0
    include_review_rows: bool = False
    intraday_order_assumption: str = "MFE_BEFORE_MAE_CONSERVATIVE"
    payout_request_mode: str = "MAX_ALLOWED"
    reward_share_override_percent: Optional[float] = None
    household_name: str = "Josh"
    acquisition_cost_mode: str = "EXISTING_INVENTORY_UNKNOWN_COST"
    effective_cost_per_funded_account: float = 0.0
    refund_or_bonus_per_account: float = 0.0
    one_time_household_external_cost: float = 0.0


@dataclass
class FleetRun:
    summary: Dict[str, Any]
    household_sessions: pd.DataFrame
    accounts: pd.DataFrame
    trades: pd.DataFrame
    payouts: pd.DataFrame
    costs: pd.DataFrame
    bottlenecks: pd.DataFrame
    forfeitures: pd.DataFrame
    config: Dict[str, Any]
    rule_snapshot: Dict[str, Any]


@dataclass
class _AccountState:
    account_id: str
    start_balance: float
    balance: float
    floor: Optional[float]
    highest_eod: float
    policy: DrawdownPolicy
    payout_rules: Dict[str, Any]
    status: str = "ACTIVE"
    failure_reason: str = ""
    failure_session: Optional[str] = None
    payout_count: int = 0
    gross_payouts: float = 0.0
    wallet_cash: float = 0.0
    cycle_start_balance: float = 0.0
    cycle_session_pnls: Optional[List[float]] = None
    qualifying_days: int = 0
    total_commission: float = 0.0
    total_source_net_pnl: float = 0.0
    total_account_realized_pnl: float = 0.0
    trades_routed: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    flat_trades: int = 0
    sessions_traded: int = 0
    provision_session: Optional[str] = None
    acquisition_cost: float = 0.0
    refund_or_bonus: float = 0.0

    def __post_init__(self):
        if self.cycle_session_pnls is None:
            self.cycle_session_pnls = []
        if self.cycle_start_balance == 0.0 and self.start_balance != 0.0:
            self.cycle_start_balance = self.start_balance


def raw_strategy_baseline(ledger: pd.DataFrame, *, include_review_rows: bool, commission_per_contract_round_trip: float) -> Dict[str, Any]:
    """Pure strategy control: all eligible signals, no prop-account rules/capacity."""
    work = _eligible_work(ledger, include_review_rows)
    contracts = pd.to_numeric(work.get("contracts", 0), errors="coerce").fillna(0).abs()
    gross = pd.to_numeric(work.get("normalized_gross_pnl", 0), errors="coerce").fillna(0.0)
    commissions = contracts * float(commission_per_contract_round_trip)
    net = gross - commissions
    per_session = work.assign(
        __gross=gross,
        __commission=commissions,
        __net=net,
    ).groupby("futures_session_id", dropna=False).agg(
        source_signals=("source_trade_id", "size"),
        strategy_gross_pnl=("__gross", "sum"),
        strategy_commissions=("__commission", "sum"),
        strategy_net_after_firm_commission=("__net", "sum"),
    ).reset_index()
    return {
        "eligible_trades": int(len(work)),
        "futures_sessions": int(work["futures_session_id"].nunique()),
        "gross_pnl": float(gross.sum()),
        "commissions": float(commissions.sum()),
        "net_after_firm_commission": float(net.sum()),
        "wins": int((net > 0).sum()),
        "losses": int((net < 0).sum()),
        "flats": int((net == 0).sum()),
        "win_rate": float((net > 0).mean()) if len(net) else 0.0,
        "sessions": per_session,
    }


def _new_account(
    rulebook: Dict[str, Any],
    cfg: FleetConfig,
    ordinal: int,
    provision_session: Optional[str],
    cost_policy: Optional[AcquisitionCostPolicy] = None,
) -> _AccountState:
    firm, product, stage_rules = _find_stage(rulebook, cfg.product_id, cfg.account_size, "sim_funded")
    if not _PAYOUT_ENGINE_SUPPORT.get(cfg.product_id):
        raise HistoricalRunnerError(f"{cfg.product_id} funded payout engine is not modeled; v5A will not fleet-rank an incomplete product")
    rcfg = RunnerConfig(
        product_id=cfg.product_id,
        account_size=cfg.account_size,
        stage="sim_funded",
        max_trades_per_session=cfg.max_trades_per_account_per_session,
        commission_per_contract_round_trip=cfg.commission_per_contract_round_trip,
        include_review_rows=cfg.include_review_rows,
        intraday_order_assumption=cfg.intraday_order_assumption,
    )
    policy = resolve_drawdown_policy(rulebook, rcfg)
    start = _resolve_start_balance(cfg.product_id, cfg.account_size, "sim_funded", stage_rules)
    floor = _initial_floor(start, policy)
    return _AccountState(
        account_id=f"{cfg.product_id.upper()}-{cfg.account_size}-{ordinal:04d}",
        start_balance=start,
        balance=start,
        floor=floor,
        highest_eod=start,
        policy=policy,
        payout_rules=stage_rules.get("payout") or {},
        cycle_start_balance=start,
        provision_session=provision_session,
        acquisition_cost=cost_policy.provision_external_cost() if cost_policy else 0.0,
        refund_or_bonus=cost_policy.provision_refund_or_bonus() if cost_policy else 0.0,
    )


def _provision_cost_event(account: _AccountState, session_id: Optional[str], cost_policy: AcquisitionCostPolicy, *, note: str) -> Dict[str, Any]:
    return {
        "futures_session_id": session_id or "PRE_SIMULATION",
        "account_id": account.account_id,
        "event_type": "FUNDED_ACCOUNT_PROVISION",
        "external_cash_cost": float(account.acquisition_cost),
        "refund_or_bonus_cash": float(account.refund_or_bonus),
        "net_external_cash_change": -float(account.acquisition_cost) + float(account.refund_or_bonus),
        "cost_basis_mode": cost_policy.mode,
        "cost_basis_known": cost_policy.cost_basis_known,
        "note": note,
    }


def _payout_blockers(
    product_id: str,
    account_size: int,
    payout_rules: Dict[str, Any],
    *,
    start_balance: float,
    balance: float,
    cycle_start_balance: float,
    cycle_session_pnls: List[float],
    qualifying_days: int,
    payout_count: int,
) -> Tuple[List[str], float, Dict[str, Any]]:
    """Return explicit blocker codes plus gross payout capacity before unmet gates.

    `_payout_quote(..., MAX_ALLOWED)` already computes the legal gross request capacity
    implied by current account profit, caps and safety nets. When the quote is ineligible,
    that amount is *accrued capacity*, not cash that can be requested now.
    """
    quote = _payout_quote(
        product_id,
        account_size,
        payout_rules,
        start_balance=start_balance,
        balance=balance,
        cycle_start_balance=cycle_start_balance,
        cycle_session_pnls=cycle_session_pnls,
        qualifying_days=qualifying_days,
        payout_count=payout_count,
        request_mode="MAX_ALLOWED",
    )
    if not quote.get("supported"):
        return ["PAYOUT_ENGINE_NOT_MODELED"], 0.0, quote
    if quote.get("eligible"):
        return [], float(quote.get("available_now") or 0.0), quote

    blockers: List[str] = []
    q_required = int(payout_rules.get("qualifying_days") or 0)
    if qualifying_days < q_required:
        blockers.append(f"NEEDS_{q_required-qualifying_days}_MORE_QUALIFYING_DAY(S)")

    cycle_profit = float(quote.get("cycle_profit") or (balance - cycle_start_balance))
    total_profit = float(quote.get("total_profit") or (balance - start_balance))
    min_payout = float(payout_rules.get("minimum_payout") or 0.0)
    capacity = float(quote.get("available_now") or 0.0)

    if product_id == "lucid_flex":
        if cycle_profit <= 0:
            blockers.append("NEEDS_POSITIVE_CYCLE_PROFIT")
        if capacity < min_payout - 1e-9:
            blockers.append(f"PAYOUT_CAPACITY_BELOW_MINIMUM_{min_payout:g}")
    elif product_id == "tradeify_select_flex":
        if payout_count > 0 and cycle_profit <= 0:
            blockers.append("NEEDS_POSITIVE_POST_PAYOUT_CYCLE")
        if capacity <= 0:
            blockers.append("NO_WITHDRAWABLE_PROFIT")
    elif product_id == "fundednext_flex":
        min_cycle = float(payout_rules.get("cycle_min_profit") or 0.0)
        if cycle_profit < min_cycle - 1e-9:
            blockers.append(f"CYCLE_PROFIT_BELOW_{min_cycle:g}")
        if capacity < min_payout - 1e-9:
            blockers.append(f"PAYOUT_CAPACITY_BELOW_MINIMUM_{min_payout:g}")
    elif product_id == "mffu_flex_50k":
        min_cycle = float(payout_rules.get("cycle_min_profit") or 0.0)
        if cycle_profit < min_cycle - 1e-9:
            blockers.append(f"CYCLE_PROFIT_BELOW_{min_cycle:g}")
        if capacity < min_payout - 1e-9:
            blockers.append(f"PAYOUT_CAPACITY_BELOW_MINIMUM_{min_payout:g}")
    elif product_id == "apex_eod":
        safety = float(payout_rules.get("safety_net") or 0.0)
        if balance <= safety + min_payout - 1e-9:
            blockers.append("SAFETY_NET_PLUS_MINIMUM_PAYOUT_NOT_CLEARED")
        cons_pct = payout_rules.get("consistency_percent")
        ratio = quote.get("consistency_ratio")
        if cons_pct is not None and ratio is not None and float(ratio) >= float(cons_pct) - 1e-12:
            blockers.append(f"PAYOUT_CONSISTENCY_AT_OR_ABOVE_{float(cons_pct):g}_PERCENT")
    elif product_id == "lucid_direct":
        goal = float(payout_rules.get("profit_goal_first") if payout_count == 0 else payout_rules.get("profit_goal_later") or 0.0)
        if cycle_profit < goal - 1e-9:
            blockers.append(f"CYCLE_PROFIT_BELOW_GOAL_{goal:g}")
        cons_pct = payout_rules.get("consistency_percent")
        ratio = quote.get("consistency_ratio")
        if cons_pct is not None and ratio is not None and float(ratio) > float(cons_pct) + 1e-12:
            blockers.append(f"PAYOUT_CONSISTENCY_ABOVE_{float(cons_pct):g}_PERCENT")
        if capacity < min_payout - 1e-9:
            blockers.append(f"PAYOUT_CAPACITY_BELOW_MINIMUM_{min_payout:g}")

    if not blockers:
        blockers.append(str(quote.get("reason") or "OTHER_PAYOUT_GATE"))
    return blockers, max(0.0, capacity), quote


def _trader_share_for_account(cfg: FleetConfig, account: _AccountState) -> float:
    lcfg = LifecycleConfig(
        product_id=cfg.product_id,
        account_size=cfg.account_size,
        mode="FUNDED_ONLY",
        commission_per_contract_round_trip=cfg.commission_per_contract_round_trip,
        payout_request_mode=cfg.payout_request_mode,
        reward_share_override_percent=cfg.reward_share_override_percent,
    )
    return _payout_share(account.payout_rules, lcfg)


def _trade_account(account: _AccountState, row: pd.Series, cfg: FleetConfig, stage_rules: Dict[str, Any], sid: str) -> Dict[str, Any]:
    contracts = abs(float(row.get("contracts") or 0.0))
    commission = contracts * float(cfg.commission_per_contract_round_trip)
    gross = float(row.get("normalized_gross_pnl") or 0.0)
    source_net = gross - commission
    mae = float(row.get("MAE")) if pd.notna(row.get("MAE")) else math.nan
    mfe = float(row.get("MFE")) if pd.notna(row.get("MFE")) else math.nan
    mae_fallback = False
    if not math.isfinite(mae):
        mae = min(0.0, gross)
        mae_fallback = True
    if not math.isfinite(mfe):
        mfe = max(0.0, gross)

    balance_before = account.balance
    floor_before = account.floor
    low = _trade_low(balance_before, mae, commission)
    peak = _trade_peak(balance_before, mfe)

    if account.policy.drawdown_type == "INTRADAY_TRAILING" and account.floor is not None:
        if cfg.intraday_order_assumption == "MFE_BEFORE_MAE_CONSERVATIVE":
            account.floor = _intraday_ratchet_floor(account.floor, peak, account.policy)

    breach = bool(account.floor is not None and low <= account.floor + 1e-9)
    dll = stage_rules.get("dll") or {}
    dll_amount = dll.get("amount")
    dll_action = dll.get("action", "NONE")
    # One-account/session is the primary use; for custom >1 cap the caller supplies
    # session-to-date account P&L via row metadata.
    prior_session_net = float(row.get("__account_session_net_before") or 0.0)
    dll_hit = False
    if dll_amount not in (None, 0) and dll_action != "NONE":
        dll_low = prior_session_net + min(0.0, mae) - commission
        if dll_low <= -float(dll_amount) + 1e-9:
            dll_hit = True

    if breach:
        account.status = "FAILED"
        account.failure_reason = "MAX_LOSS_FLOOR_BREACH"
        account.failure_session = sid
        account.balance = float(account.floor)
        account_realized = account.balance - balance_before
    elif dll_hit and dll_action in {"SOFT_PAUSE_SESSION", "LIQUIDATE_AND_PAUSE"}:
        allowed_loss = max(0.0, float(dll_amount) + prior_session_net)
        account_realized = max(source_net, -allowed_loss)
        account.balance += account_realized
    elif dll_hit and dll_action == "HARD_FAIL":
        account.status = "FAILED"
        account.failure_reason = "DAILY_LOSS_LIMIT_HARD_FAIL"
        account.failure_session = sid
        account_realized = source_net
        account.balance += account_realized
    else:
        account_realized = source_net
        account.balance += account_realized

    if account.policy.drawdown_type == "INTRADAY_TRAILING" and account.floor is not None and not breach:
        if cfg.intraday_order_assumption == "MAE_BEFORE_MFE_OPTIMISTIC":
            account.floor = _intraday_ratchet_floor(account.floor, peak, account.policy)

    account.total_commission += commission
    account.total_source_net_pnl += source_net
    account.total_account_realized_pnl += account_realized
    account.trades_routed += 1
    if source_net > 0:
        account.winning_trades += 1
    elif source_net < 0:
        account.losing_trades += 1
    else:
        account.flat_trades += 1

    return {
        "account_id": account.account_id,
        "futures_session_id": sid,
        "entry_time_et": row.get("entry_time_et"),
        "exit_time_et": row.get("exit_time_et"),
        "source_file": row.get("source_file"),
        "source_trade_id": row.get("source_trade_id"),
        "direction": row.get("direction"),
        "contracts": contracts,
        "source_gross_pnl": gross,
        "commission": commission,
        "source_trade_net_pnl": source_net,
        "account_realized_pnl_until_exit_or_breach": account_realized,
        "balance_before": balance_before,
        "balance_after_trade_before_payout": account.balance,
        "floor_before": floor_before,
        "floor_after_trade": account.floor,
        "mae": mae,
        "mfe": mfe,
        "intratrade_low": low,
        "intratrade_peak": peak,
        "mae_fallback": mae_fallback,
        "breach": breach,
        "dll_hit": dll_hit,
        "dll_action": dll_action,
        "account_status_after_trade": account.status,
        "audit_warnings": row.get("audit_warnings"),
    }


def _finalize_account_session(account: _AccountState, cfg: FleetConfig, sid: str, session_realized: float) -> Optional[Dict[str, Any]]:
    """EOD floor + payout processing for one account that traded this session."""
    if account.status == "ACTIVE":
        account.highest_eod = max(account.highest_eod, account.balance)
        account.floor = _eod_update_floor(account.floor, account.highest_eod, account.policy)

    account.sessions_traded += 1
    account.cycle_session_pnls.append(float(session_realized))

    payout_event = None
    if account.status == "ACTIVE" and account.payout_rules:
        q_threshold = float(account.payout_rules.get("qualifying_day_profit") or 0.0)
        if q_threshold > 0 and session_realized >= q_threshold - 1e-9:
            account.qualifying_days += 1
        quote = _payout_quote(
            cfg.product_id,
            cfg.account_size,
            account.payout_rules,
            start_balance=account.start_balance,
            balance=account.balance,
            cycle_start_balance=account.cycle_start_balance,
            cycle_session_pnls=account.cycle_session_pnls,
            qualifying_days=account.qualifying_days,
            payout_count=account.payout_count,
            request_mode=cfg.payout_request_mode,
        )
        if quote.get("eligible") and float(quote.get("gross_request") or 0.0) > 0:
            gross_request = float(quote["gross_request"])
            lcfg = LifecycleConfig(
                product_id=cfg.product_id,
                account_size=cfg.account_size,
                mode="FUNDED_ONLY",
                commission_per_contract_round_trip=cfg.commission_per_contract_round_trip,
                payout_request_mode=cfg.payout_request_mode,
                reward_share_override_percent=cfg.reward_share_override_percent,
            )
            share = _payout_share(account.payout_rules, lcfg)
            trader_cash = gross_request * share
            pre = account.balance
            account.balance -= gross_request
            account.payout_count += 1
            account.gross_payouts += gross_request
            account.wallet_cash += trader_cash
            account.floor = _funded_floor_after_payout(cfg.product_id, account.start_balance, account.floor, account.payout_count, account.payout_rules)
            payout_event = {
                "account_id": account.account_id,
                "futures_session_id": sid,
                "payout_number": account.payout_count,
                "gross_payout_deduction": gross_request,
                "trader_share_percent": share * 100.0,
                "trader_wallet_cash": trader_cash,
                "balance_before_payout": pre,
                "balance_after_payout": account.balance,
                "failure_floor_after_payout": account.floor,
                "qualifying_days_used": account.qualifying_days,
                "cycle_profit_before_payout": quote.get("cycle_profit"),
            }
            account.qualifying_days = 0
            account.cycle_start_balance = account.balance
            account.cycle_session_pnls = []
            max_payouts = account.payout_rules.get("maximum_payouts")
            if max_payouts is not None and account.payout_count >= int(max_payouts):
                account.status = "PAYOUT_CYCLE_COMPLETE"
    return payout_event


def run_single_product_fleet(rulebook: Dict[str, Any], ledger: pd.DataFrame, cfg: FleetConfig) -> FleetRun:
    if cfg.capacity_mode not in {"FIXED_FLEET", "MAINTAIN_FIXED_ACTIVE", "FORCE_100_CAPTURE"}:
        raise HistoricalRunnerError("v5B supports FIXED_FLEET, MAINTAIN_FIXED_ACTIVE, or FORCE_100_CAPTURE")
    if cfg.fixed_accounts < 1:
        raise HistoricalRunnerError("fixed_accounts must be >= 1")
    if cfg.max_trades_per_account_per_session < 1:
        raise HistoricalRunnerError("max trades/account/session must be >= 1")

    cost_policy = AcquisitionCostPolicy(
        mode=cfg.acquisition_cost_mode,
        effective_cost_per_funded_account=float(cfg.effective_cost_per_funded_account),
        refund_or_bonus_per_account=float(cfg.refund_or_bonus_per_account),
        one_time_household_external_cost=float(cfg.one_time_household_external_cost),
    )
    try:
        cost_policy.validate()
    except ValueError as exc:
        raise HistoricalRunnerError(str(exc)) from exc

    firm, product, stage_rules = _find_stage(rulebook, cfg.product_id, cfg.account_size, "sim_funded")
    if not _PAYOUT_ENGINE_SUPPORT.get(cfg.product_id):
        raise HistoricalRunnerError("v5B fleet mode requires a modeled funded payout engine")

    work = _eligible_work(ledger, cfg.include_review_rows)
    baseline = raw_strategy_baseline(
        ledger,
        include_review_rows=cfg.include_review_rows,
        commission_per_contract_round_trip=cfg.commission_per_contract_round_trip,
    )

    accounts: List[_AccountState] = []
    cost_rows: List[Dict[str, Any]] = []
    forfeiture_rows: List[Dict[str, Any]] = []
    next_account = 1

    if cost_policy.one_time_household_external_cost > 0:
        cost_rows.append({
            "futures_session_id": "PRE_SIMULATION",
            "account_id": "HOUSEHOLD",
            "event_type": "ONE_TIME_HOUSEHOLD_EXTERNAL_COST",
            "external_cash_cost": float(cost_policy.one_time_household_external_cost),
            "refund_or_bonus_cash": 0.0,
            "net_external_cash_change": -float(cost_policy.one_time_household_external_cost),
            "cost_basis_mode": cost_policy.mode,
            "cost_basis_known": True,
            "note": "User-entered household-level external cost.",
        })

    def provision(session_id: Optional[str], note: str) -> _AccountState:
        nonlocal next_account
        a = _new_account(rulebook, cfg, next_account, session_id, cost_policy)
        next_account += 1
        accounts.append(a)
        cost_rows.append(_provision_cost_event(a, session_id, cost_policy, note=note))
        return a

    if cfg.capacity_mode in {"FIXED_FLEET", "MAINTAIN_FIXED_ACTIVE"}:
        for _ in range(cfg.fixed_accounts):
            provision(None, "Initial funded inventory for fleet research.")

    trade_rows: List[Dict[str, Any]] = []
    payout_rows: List[Dict[str, Any]] = []
    household_rows: List[Dict[str, Any]] = []
    total_shortfall = 0
    total_routed = 0
    total_provisioned = len(accounts)
    pre_sim_cost_pending = sum(float(r.get("external_cash_cost") or 0.0) for r in cost_rows if r.get("futures_session_id") == "PRE_SIMULATION")
    pre_sim_refund_pending = sum(float(r.get("refund_or_bonus_cash") or 0.0) for r in cost_rows if r.get("futures_session_id") == "PRE_SIMULATION")
    first_session = True

    for sid_raw, group in work.groupby("futures_session_id", sort=False, dropna=False):
        sid = str(sid_raw)
        group = group.copy()
        group["__entry"] = pd.to_datetime(group["entry_time_et"], errors="coerce", utc=True)
        group = group.sort_values(["__entry", "source_file", "source_trade_id"], na_position="last").drop(columns="__entry")

        session_trade_count: Dict[str, int] = {}
        session_account_net: Dict[str, float] = {}
        session_accounts_traded: List[str] = []
        session_payout_cash = 0.0
        session_payout_gross = 0.0
        session_new_accounts = 0
        session_failures: List[str] = []
        session_cycle_completes: List[str] = []
        source_gross = 0.0
        source_commission = 0.0
        source_net = 0.0
        account_realized = 0.0
        winners = losers = flats = 0
        routed = shortfall = 0

        session_external_cost = pre_sim_cost_pending if first_session else 0.0
        session_refunds = pre_sim_refund_pending if first_session else 0.0
        first_session = False

        # Maintain-N research replaces closed accounts before the session begins.
        if cfg.capacity_mode == "MAINTAIN_FIXED_ACTIVE":
            active_count = sum(1 for a in accounts if a.status == "ACTIVE")
            while active_count < cfg.fixed_accounts:
                a = provision(sid, "Maintain-N replacement funded account (instant funded-inventory research assumption).")
                total_provisioned += 1
                session_new_accounts += 1
                session_external_cost += a.acquisition_cost
                session_refunds += a.refund_or_bonus
                active_count += 1

        for signal_ordinal, (_, row) in enumerate(group.iterrows(), start=1):
            active_with_slot = [
                a for a in accounts
                if a.status == "ACTIVE" and session_trade_count.get(a.account_id, 0) < cfg.max_trades_per_account_per_session
            ]

            if not active_with_slot and cfg.capacity_mode == "FORCE_100_CAPTURE":
                a = provision(sid, "Force-100%-capture funded account provision.")
                total_provisioned += 1
                session_new_accounts += 1
                session_external_cost += a.acquisition_cost
                session_refunds += a.refund_or_bonus
                active_with_slot = [a]
            elif not active_with_slot and cfg.capacity_mode == "MAINTAIN_FIXED_ACTIVE":
                # If an account failed earlier in this same session, restore the configured
                # active fleet size on demand. This is intentionally an instant-inventory
                # research assumption, not yet the real evaluation-to-funded replacement queue.
                active_count = sum(1 for a in accounts if a.status == "ACTIVE")
                if active_count < cfg.fixed_accounts:
                    a = provision(sid, "Intraday Maintain-N replacement after account closure (research assumption).")
                    total_provisioned += 1
                    session_new_accounts += 1
                    session_external_cost += a.acquisition_cost
                    session_refunds += a.refund_or_bonus
                    active_with_slot = [a]

            if not active_with_slot:
                shortfall += 1
                total_shortfall += 1
                trade_rows.append({
                    "futures_session_id": sid,
                    "session_signal_ordinal": signal_ordinal,
                    "account_id": "",
                    "decision": "UNROUTED_CAPACITY_SHORTFALL",
                    "source_file": row.get("source_file"),
                    "source_trade_id": row.get("source_trade_id"),
                    "source_gross_pnl": row.get("normalized_gross_pnl"),
                })
                continue

            account = active_with_slot[0]
            prior = session_account_net.get(account.account_id, 0.0)
            row2 = row.copy()
            row2["__account_session_net_before"] = prior
            tr = _trade_account(account, row2, cfg, stage_rules, sid)
            tr["session_signal_ordinal"] = signal_ordinal
            tr["decision"] = "ROUTE"
            trade_rows.append(tr)

            session_trade_count[account.account_id] = session_trade_count.get(account.account_id, 0) + 1
            session_account_net[account.account_id] = session_account_net.get(account.account_id, 0.0) + float(tr["account_realized_pnl_until_exit_or_breach"])
            if account.account_id not in session_accounts_traded:
                session_accounts_traded.append(account.account_id)

            routed += 1
            total_routed += 1
            source_gross += float(tr["source_gross_pnl"])
            source_commission += float(tr["commission"])
            source_net += float(tr["source_trade_net_pnl"])
            account_realized += float(tr["account_realized_pnl_until_exit_or_breach"])
            if float(tr["source_trade_net_pnl"]) > 0:
                winners += 1
            elif float(tr["source_trade_net_pnl"]) < 0:
                losers += 1
            else:
                flats += 1
            if account.status == "FAILED" and account.account_id not in session_failures:
                session_failures.append(account.account_id)

        # EOD finalization and payouts are per ACCOUNT, after all of that account's trades.
        for account_id in session_accounts_traded:
            account = next(a for a in accounts if a.account_id == account_id)
            before_payouts = account.payout_count
            payout = _finalize_account_session(account, cfg, sid, session_account_net.get(account_id, 0.0))
            if payout is not None:
                payout_rows.append(payout)
                session_payout_cash += float(payout["trader_wallet_cash"])
                session_payout_gross += float(payout["gross_payout_deduction"])
            if before_payouts != account.payout_count and account.status == "PAYOUT_CYCLE_COMPLETE":
                session_cycle_completes.append(account.account_id)

        # Maintain-N means the target active inventory is restored after end-of-session
        # closures too, so the end-of-data balance sheet shows the inventory Josh would
        # actually be carrying into the next futures session under this research policy.
        if cfg.capacity_mode == "MAINTAIN_FIXED_ACTIVE":
            active_count = sum(1 for a in accounts if a.status == "ACTIVE")
            while active_count < cfg.fixed_accounts:
                a = provision(sid, "End-of-session Maintain-N replacement after failure/payout-cycle closure (research assumption).")
                total_provisioned += 1
                session_new_accounts += 1
                session_external_cost += a.acquisition_cost
                session_refunds += a.refund_or_bonus
                active_count += 1

        active_end = sum(1 for a in accounts if a.status == "ACTIVE")
        failed_cum = sum(1 for a in accounts if a.status == "FAILED")
        completed_cum = sum(1 for a in accounts if a.status == "PAYOUT_CYCLE_COMPLETE")
        wallet_cum = sum(a.wallet_cash for a in accounts)
        account_profit_inventory = sum(a.balance - a.start_balance for a in accounts if a.status == "ACTIVE")
        aggregate_prop_balance = sum(a.balance for a in accounts if a.status == "ACTIVE")
        total_external_cost_cum = sum(float(r.get("external_cash_cost") or 0.0) for r in cost_rows)
        total_refund_cum = sum(float(r.get("refund_or_bonus_cash") or 0.0) for r in cost_rows)
        cash_flow_cum = wallet_cum - total_external_cost_cum + total_refund_cum

        household_rows.append({
            "household": cfg.household_name,
            "futures_session_id": sid,
            "data_mode": "REVIEW_INCLUDED_RESEARCH" if cfg.include_review_rows else "STRICT_CERTIFICATION",
            "source_signals": int(len(group)),
            "signals_routed": routed,
            "signals_unrouted_capacity": shortfall,
            "signal_capture_percent": (routed / len(group) * 100.0) if len(group) else 0.0,
            "accounts_traded": len(session_accounts_traded),
            "winning_trades": winners,
            "losing_trades": losers,
            "flat_trades": flats,
            "source_strategy_gross_pnl": source_gross,
            "firm_commissions_embedded_in_prop_pnl": source_commission,
            "source_strategy_net_after_commission": source_net,
            "account_realized_trading_pnl_until_breach": account_realized,
            "payout_deductions_from_prop_accounts": session_payout_gross,
            "payout_cash_to_household": session_payout_cash,
            "external_account_and_household_costs": session_external_cost,
            "refunds_or_bonuses": session_refunds,
            "household_realized_external_cash_change": session_payout_cash - session_external_cost + session_refunds,
            "new_accounts_provisioned": session_new_accounts,
            "accounts_failed": len(session_failures),
            "accounts_completed_payout_cycle": len(session_cycle_completes),
            "active_accounts_end": active_end,
            "failed_accounts_cumulative": failed_cum,
            "completed_accounts_cumulative": completed_cum,
            "household_wallet_cash_cumulative": wallet_cum,
            "external_costs_cumulative": total_external_cost_cum,
            "refunds_or_bonuses_cumulative": total_refund_cum,
            "household_cash_flow_cumulative_after_modeled_external_costs": cash_flow_cum,
            "active_account_profit_inventory_not_cash": account_profit_inventory,
            "aggregate_active_prop_balances_not_cash": aggregate_prop_balance,
        })

    account_rows = []
    for a in accounts:
        blockers: List[str] = []
        claimable_gross = 0.0
        accrued_blocked_gross = 0.0
        quote = {"reason": "INACTIVE", "available_now": 0.0, "eligible": False}
        if a.status == "ACTIVE" and a.payout_rules:
            blockers, capacity, quote = _payout_blockers(
                cfg.product_id,
                cfg.account_size,
                a.payout_rules,
                start_balance=a.start_balance,
                balance=a.balance,
                cycle_start_balance=a.cycle_start_balance,
                cycle_session_pnls=a.cycle_session_pnls,
                qualifying_days=a.qualifying_days,
                payout_count=a.payout_count,
            )
            if quote.get("eligible"):
                claimable_gross = capacity
            else:
                accrued_blocked_gross = capacity
        share = _trader_share_for_account(cfg, a) if a.payout_rules else 1.0
        residual_profit = max(0.0, a.balance - a.start_balance)

        if a.status == "FAILED" and residual_profit > 0:
            forfeiture_rows.append({
                "account_id": a.account_id,
                "futures_session_id": a.failure_session,
                "classification": "CONFIRMED_ACCOUNT_CLOSED_RESIDUAL_SIM_PROFIT_LOST",
                "status": "CONFIRMED",
                "gross_value": residual_profit,
                "estimated_trader_cash_value": residual_profit * share,
                "reason": a.failure_reason or "ACCOUNT_FAILED",
                "note": "Positive simulated profit remaining above starting balance when the account closed is no longer available for future payout.",
            })
        elif a.status == "PAYOUT_CYCLE_COMPLETE" and residual_profit > 0:
            forfeiture_rows.append({
                "account_id": a.account_id,
                "futures_session_id": None,
                "classification": "LIVE_TRANSITION_VALUE_UNRESOLVED",
                "status": "UNRESOLVED_NOT_COUNTED_AS_FORFEITED_OR_CASH",
                "gross_value": residual_profit,
                "estimated_trader_cash_value": None,
                "reason": "PAYOUT_CYCLE_COMPLETE",
                "note": "Full live-transition rules are Step 29-31 work. This value is preserved but not counted as cash or confirmed forfeiture.",
            })

        account_rows.append({
            "account_id": a.account_id,
            "status": a.status,
            "failure_reason": a.failure_reason,
            "failure_session": a.failure_session,
            "provision_session": a.provision_session,
            "acquisition_cost_basis": a.acquisition_cost if cost_policy.cost_basis_known else None,
            "refund_or_bonus_basis": a.refund_or_bonus if cost_policy.cost_basis_known else None,
            "starting_balance": a.start_balance,
            "ending_balance": a.balance,
            "ending_failure_floor": a.floor,
            "account_profit_inventory_not_cash": a.balance - a.start_balance,
            "trades_routed": a.trades_routed,
            "sessions_traded": a.sessions_traded,
            "wins": a.winning_trades,
            "losses": a.losing_trades,
            "firm_commissions_embedded_in_prop_pnl": a.total_commission,
            "source_trade_net_pnl": a.total_source_net_pnl,
            "account_realized_pnl_until_breach": a.total_account_realized_pnl,
            "payout_count": a.payout_count,
            "gross_payout_deductions": a.gross_payouts,
            "trader_wallet_cash": a.wallet_cash,
            "qualifying_days_current_cycle": a.qualifying_days,
            "claimable_now_gross": claimable_gross,
            "claimable_now_estimated_trader_cash": claimable_gross * share,
            "accrued_but_blocked_gross_capacity": accrued_blocked_gross,
            "accrued_but_blocked_estimated_trader_cash": accrued_blocked_gross * share,
            "payout_blockers": "; ".join(blockers) if blockers else ("ELIGIBLE_NOW" if claimable_gross > 0 else str(quote.get("reason") or "NONE")),
            "payout_eligibility_reason_raw": quote.get("reason"),
        })

    accounts_df = pd.DataFrame(account_rows)
    household_df = pd.DataFrame(household_rows)
    trades_df = pd.DataFrame(trade_rows)
    payouts_df = pd.DataFrame(payout_rows)
    costs_df = pd.DataFrame(cost_rows)
    forfeitures_df = pd.DataFrame(forfeiture_rows)

    bottleneck_rows: List[Dict[str, Any]] = []
    if total_shortfall:
        bottleneck_rows.append({
            "category": "CAPACITY",
            "reason": "UNROUTED_CAPACITY_SHORTFALL",
            "count": int(total_shortfall),
            "gross_value_affected": None,
            "estimated_trader_cash_value_affected": None,
            "note": "Valid source signals that could not be assigned an account slot.",
        })
    if not accounts_df.empty:
        failed = accounts_df[accounts_df["status"] == "FAILED"]
        for reason, g in failed.groupby("failure_reason", dropna=False):
            bottleneck_rows.append({
                "category": "ACCOUNT_FAILURE",
                "reason": str(reason or "UNKNOWN_FAILURE"),
                "count": int(len(g)),
                "gross_value_affected": float(g["account_profit_inventory_not_cash"].clip(lower=0).sum()),
                "estimated_trader_cash_value_affected": None,
                "note": "Account closures by recorded failure reason.",
            })
        active = accounts_df[accounts_df["status"] == "ACTIVE"]
        if not active.empty:
            for _, r in active.iterrows():
                blocker_text = str(r.get("payout_blockers") or "")
                if blocker_text and blocker_text not in {"ELIGIBLE_NOW", "NONE"}:
                    for blocker in [x.strip() for x in blocker_text.split(";") if x.strip()]:
                        bottleneck_rows.append({
                            "category": "ENDING_PAYOUT_BLOCKER",
                            "reason": blocker,
                            "count": 1,
                            "gross_value_affected": float(r.get("accrued_but_blocked_gross_capacity") or 0.0),
                            "estimated_trader_cash_value_affected": float(r.get("accrued_but_blocked_estimated_trader_cash") or 0.0),
                            "note": "Active end-of-data account has accrued payout capacity but has not cleared this gate.",
                        })
    if bottleneck_rows:
        bdf = pd.DataFrame(bottleneck_rows)
        bottlenecks_df = bdf.groupby(["category", "reason", "note"], as_index=False, dropna=False).agg(
            count=("count", "sum"),
            gross_value_affected=("gross_value_affected", "sum"),
            estimated_trader_cash_value_affected=("estimated_trader_cash_value_affected", "sum"),
        )
    else:
        bottlenecks_df = pd.DataFrame(columns=["category", "reason", "note", "count", "gross_value_affected", "estimated_trader_cash_value_affected"])

    coverage = assess_rule_coverage(rulebook, cfg.product_id, cfg.account_size, "sim_funded")
    source_hashes = sorted(set(str(x) for x in work.get("source_sha256", pd.Series(dtype=str)).dropna().unique()))
    rule_snapshot = {
        "rulebook_schema_version": rulebook.get("schema_version"),
        "verified_as_of": rulebook.get("verified_as_of"),
        "firm": firm.get("display_name"),
        "product_id": product.get("product_id"),
        "product": product.get("display_name"),
        "account_size": cfg.account_size,
        "stage": "sim_funded",
        "stage_rules": stage_rules,
        "rule_coverage": coverage,
        "sources": product.get("sources", []),
    }
    fingerprint = sha256_text(stable_json({"engine": FLEET_ENGINE_VERSION, "config": asdict(cfg), "source_hashes": source_hashes, "rule_snapshot": rule_snapshot}))[:16]

    active_accounts = int((accounts_df["status"] == "ACTIVE").sum()) if not accounts_df.empty else 0
    failed_accounts = int((accounts_df["status"] == "FAILED").sum()) if not accounts_df.empty else 0
    completed_accounts = int((accounts_df["status"] == "PAYOUT_CYCLE_COMPLETE").sum()) if not accounts_df.empty else 0
    wallet_cash = float(accounts_df["trader_wallet_cash"].sum()) if not accounts_df.empty else 0.0
    claimable_gross = float(accounts_df["claimable_now_gross"].sum()) if not accounts_df.empty else 0.0
    claimable_cash = float(accounts_df["claimable_now_estimated_trader_cash"].sum()) if not accounts_df.empty else 0.0
    accrued_blocked_gross = float(accounts_df["accrued_but_blocked_gross_capacity"].sum()) if not accounts_df.empty else 0.0
    accrued_blocked_cash = float(accounts_df["accrued_but_blocked_estimated_trader_cash"].sum()) if not accounts_df.empty else 0.0
    active_profit_inventory = float(accounts_df.loc[accounts_df["status"] == "ACTIVE", "account_profit_inventory_not_cash"].sum()) if not accounts_df.empty else 0.0
    external_costs = float(costs_df["external_cash_cost"].sum()) if not costs_df.empty else 0.0
    refunds = float(costs_df["refund_or_bonus_cash"].sum()) if not costs_df.empty else 0.0
    cash_flow_ex_unknown_cost = wallet_cash - external_costs + refunds
    realized_net = cash_flow_ex_unknown_cost if cost_policy.cost_basis_known else None
    active_cost_basis = float(accounts_df.loc[accounts_df["status"] == "ACTIVE", "acquisition_cost_basis"].fillna(0.0).sum()) if cost_policy.cost_basis_known and not accounts_df.empty else None
    failed_cost_basis = float(accounts_df.loc[accounts_df["status"] == "FAILED", "acquisition_cost_basis"].fillna(0.0).sum()) if cost_policy.cost_basis_known and not accounts_df.empty else None
    completed_cost_basis = float(accounts_df.loc[accounts_df["status"] == "PAYOUT_CYCLE_COMPLETE", "acquisition_cost_basis"].fillna(0.0).sum()) if cost_policy.cost_basis_known and not accounts_df.empty else None
    confirmed_forfeited = float(forfeitures_df.loc[forfeitures_df["status"] == "CONFIRMED", "gross_value"].sum()) if not forfeitures_df.empty else 0.0
    unresolved_transition = float(forfeitures_df.loc[forfeitures_df["status"].str.startswith("UNRESOLVED", na=False), "gross_value"].sum()) if not forfeitures_df.empty else 0.0

    summary = {
        "engine_version": FLEET_ENGINE_VERSION,
        "schema_version": FLEET_SCHEMA_VERSION,
        "run_id": f"SB5B-{fingerprint}",
        "household": cfg.household_name,
        "firm": firm.get("display_name"),
        "product": product.get("display_name"),
        "product_id": cfg.product_id,
        "account_size": cfg.account_size,
        "stage": "FUNDED_ONLY_FLEET",
        "data_mode": "REVIEW_INCLUDED_RESEARCH" if cfg.include_review_rows else "STRICT_CERTIFICATION",
        "include_review_rows": bool(cfg.include_review_rows),
        "capacity_mode": cfg.capacity_mode,
        "fixed_accounts_requested": cfg.fixed_accounts if cfg.capacity_mode in {"FIXED_FLEET", "MAINTAIN_FIXED_ACTIVE"} else None,
        "max_trades_per_account_per_session": cfg.max_trades_per_account_per_session,
        "source_eligible_trades": int(len(work)),
        "source_futures_sessions": int(work["futures_session_id"].nunique()),
        "signals_routed": int(total_routed),
        "signals_unrouted_capacity": int(total_shortfall),
        "signal_capture_percent": float(total_routed / len(work) * 100.0) if len(work) else 0.0,
        "accounts_provisioned": int(total_provisioned),
        "active_accounts_at_end": active_accounts,
        "failed_accounts": failed_accounts,
        "payout_cycle_complete_accounts": completed_accounts,
        "completed_payouts": int(accounts_df["payout_count"].sum()) if not accounts_df.empty else 0,
        "payout_cash_received": wallet_cash,
        "claimable_now_gross_at_end": claimable_gross,
        "claimable_now_estimated_trader_cash_at_end": claimable_cash,
        "accrued_but_not_claimable_gross_capacity_at_end": accrued_blocked_gross,
        "accrued_but_not_claimable_estimated_trader_cash_at_end": accrued_blocked_cash,
        "estimated_realistically_recoverable_future_payout_cash": None,
        "active_account_profit_inventory_not_cash": active_profit_inventory,
        "total_firm_commissions_embedded_in_prop_pnl": float(accounts_df["firm_commissions_embedded_in_prop_pnl"].sum()) if not accounts_df.empty else 0.0,
        "acquisition_cost_mode": cost_policy.mode,
        "cost_basis_known": cost_policy.cost_basis_known,
        "account_and_household_external_costs": external_costs,
        "account_acquisition_costs": external_costs if cost_policy.cost_basis_known else None,
        "refunds_or_bonuses_received": refunds,
        "cash_flow_since_sim_start_excluding_unknown_preexisting_inventory_cost": cash_flow_ex_unknown_cost,
        "realized_household_net_cash_after_modeled_external_costs": realized_net,
        "realized_household_net_after_all_costs": realized_net,
        "active_accounts_cost_basis_at_end": active_cost_basis,
        "failed_accounts_cost_basis": failed_cost_basis,
        "payout_cycle_complete_accounts_cost_basis": completed_cost_basis,
        "confirmed_forfeited_residual_sim_profit": confirmed_forfeited,
        "unresolved_live_transition_value": unresolved_transition,
        "economics_status": "MODELED_EXTERNAL_COST_BASIS" if cost_policy.cost_basis_known else "UNKNOWN_FUNDED_ACQUISITION_COST_NOT_YET_MODELED",
        "rule_coverage": coverage.get("status"),
        "payout_engine_support": _PAYOUT_ENGINE_SUPPORT.get(cfg.product_id, "NOT_MODELED"),
        "raw_strategy_baseline": {k: v for k, v in baseline.items() if k != "sessions"},
        "source_hashes": source_hashes,
    }

    return FleetRun(
        summary=summary,
        household_sessions=household_df,
        accounts=accounts_df,
        trades=trades_df,
        payouts=payouts_df,
        costs=costs_df,
        bottlenecks=bottlenecks_df,
        forfeitures=forfeitures_df,
        config=asdict(cfg),
        rule_snapshot=rule_snapshot,
    )

def build_fleet_bundle(run: FleetRun) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("HOUSEHOLD_SUMMARY.json", json.dumps(run.summary, indent=2, default=str))
        z.writestr("CONFIG.json", json.dumps(run.config, indent=2, default=str))
        z.writestr("RULE_SNAPSHOT.json", json.dumps(run.rule_snapshot, indent=2, default=str))
        z.writestr("HOUSEHOLD_SESSION_LEDGER.csv", run.household_sessions.to_csv(index=False))
        z.writestr("ACCOUNT_INVENTORY.csv", run.accounts.to_csv(index=False))
        z.writestr("TRADE_ROUTING.csv", run.trades.to_csv(index=False))
        z.writestr("PAYOUT_LEDGER.csv", run.payouts.to_csv(index=False))
        z.writestr("COST_LEDGER.csv", run.costs.to_csv(index=False))
        z.writestr("BOTTLENECK_SUMMARY.csv", run.bottlenecks.to_csv(index=False))
        z.writestr("FORFEITURE_AND_TRANSITION_VALUE_LEDGER.csv", run.forfeitures.to_csv(index=False))
        lines = [
            "# Project StarBase v5B — Josh Fleet Economics + Inventory", "",
            f"Run ID: **{run.summary.get('run_id')}**",
            f"Data mode: **{run.summary.get('data_mode')}**",
            f"Product: **{run.summary.get('firm')} / {run.summary.get('product')} / ${run.summary.get('account_size'):,}**",
            f"Capacity mode: **{run.summary.get('capacity_mode')}**",
            f"Signals routed: **{run.summary.get('signals_routed'):,} / {run.summary.get('source_eligible_trades'):,}**",
            f"Signal capture: **{run.summary.get('signal_capture_percent',0):.2f}%**",
            f"Accounts provisioned: **{run.summary.get('accounts_provisioned'):,}**",
            f"Payout cash received: **${run.summary.get('payout_cash_received',0):,.2f}**",
            f"External account/household costs modeled: **${run.summary.get('account_and_household_external_costs',0):,.2f}**",
            f"Refunds/bonuses modeled: **${run.summary.get('refunds_or_bonuses_received',0):,.2f}**",
            f"Claimable now at data end (estimated trader cash): **${run.summary.get('claimable_now_estimated_trader_cash_at_end',0):,.2f}**",
            f"Accrued but blocked at data end (estimated trader cash if gates later clear): **${run.summary.get('accrued_but_not_claimable_estimated_trader_cash_at_end',0):,.2f}**", "",
        ]
        if run.summary.get("realized_household_net_cash_after_modeled_external_costs") is None:
            lines += [
                "**Final business net is NOT certified for this run.** The funded acquisition cost basis is unknown/pre-existing.",
                "Use Manual Effective Funded Cost for a research-grade costed fleet, or later run the full evaluation factory to manufacture funded accounts exactly.", "",
            ]
        else:
            lines += [
                f"Realized household net cash after modeled external costs: **${run.summary.get('realized_household_net_cash_after_modeled_external_costs',0):,.2f}**",
                "This is exact only to the stated cost assumption. Trading commissions are already embedded in prop-account P&L and are not subtracted a second time from household cash.", "",
            ]
        lines += [
            "End-of-data accounts are preserved. Claimable-now and accrued-but-blocked payout capacity are reported separately.",
            "Estimated realistically recoverable future payout cash remains intentionally unmodeled until survival/live-transition logic is complete.",
            "Confirmed residual value lost on failed accounts is separated from unresolved live-transition value.",
        ]
        z.writestr("REPORT.md", "\n".join(lines) + "\n")
    return buf.getvalue()
