"""Project StarBase v4C lifecycle-correct single-account stage engine.

This module upgrades v4B's trade/risk runner so account products stop and pay for the
reasons their actual stage rules specify. It intentionally remains one-account / one-lineage;
fleet fan-out, passed-eval banking, household limits and live transitions are later stages.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from io import BytesIO
import json
import math
from typing import Any, Dict, Iterable, List, Optional, Tuple
import zipfile

import pandas as pd

from starbase_historical_runner import (
    HistoricalRunnerError,
    RunnerConfig,
    DrawdownPolicy,
    _find_stage,
    resolve_starting_balance,
    resolve_drawdown_policy,
    _initial_floor,
    _eod_update_floor,
    _intraday_ratchet_floor,
    _trade_low,
    _trade_peak,
    _target_progress,
)
from starbase_integrity import assess_rule_coverage, sha256_text, stable_json
from starbase_rulebook import product_details

LIFECYCLE_ENGINE_VERSION = "4.0C"
LIFECYCLE_SCHEMA_VERSION = "4C.1.0"


@dataclass(frozen=True)
class LifecycleConfig:
    product_id: str
    account_size: int
    mode: str = "EVALUATION_ONLY"  # EVALUATION_ONLY | FUNDED_ONLY | EVAL_TO_FUNDED
    max_trades_per_session: int = 1
    commission_per_contract_round_trip: float = 0.0
    include_review_rows: bool = False
    intraday_order_assumption: str = "MFE_BEFORE_MAE_CONSERVATIVE"
    platform_variant: str = "DEFAULT"
    payout_request_mode: str = "MAX_ALLOWED"  # MAX_ALLOWED | MINIMUM_ONLY | NONE
    reward_share_override_percent: Optional[float] = None


@dataclass
class StageRun:
    summary: Dict[str, Any]
    trades: pd.DataFrame
    sessions: pd.DataFrame
    payouts: pd.DataFrame
    config: Dict[str, Any]
    rule_snapshot: Dict[str, Any]


@dataclass
class LifecycleRun:
    summary: Dict[str, Any]
    evaluation: Optional[StageRun]
    funded: Optional[StageRun]
    config: Dict[str, Any]


# Funded payout engines we consider sufficiently specified for this v4C stage.
# Other products remain visible, but StarBase marks their payout engine unsupported rather
# than silently applying a generic withdrawal model.
_PAYOUT_ENGINE_SUPPORT = {
    "lucid_flex": "VERIFIED_CORE",
    "lucid_direct": "VERIFIED_CORE",
    "tradeify_select_flex": "VERIFIED_CORE",
    "fundednext_flex": "VERIFIED_CORE",
    "mffu_flex_50k": "VERIFIED_CORE",
    "apex_eod": "VERIFIED_CORE",
}


def _stage_rules(rulebook: Dict[str, Any], config: LifecycleConfig, stage: str):
    firm, product, rules = _find_stage(rulebook, config.product_id, config.account_size, stage)
    return firm, product, rules


def _runner_cfg(config: LifecycleConfig, stage: str) -> RunnerConfig:
    return RunnerConfig(
        product_id=config.product_id,
        account_size=config.account_size,
        stage=stage,
        max_trades_per_session=config.max_trades_per_session,
        commission_per_contract_round_trip=config.commission_per_contract_round_trip,
        include_review_rows=config.include_review_rows,
        intraday_order_assumption=config.intraday_order_assumption,
        platform_variant=config.platform_variant,
    )


def _resolve_start_balance(product_id: str, account_size: int, stage: str, stage_rules: Dict[str, Any]) -> float:
    # Prefer explicit profit-account representation when present. This fixes the prior MFFU
    # identifier mismatch that accidentally treated its $0 sim-funded P&L balance as $50,000.
    if stage_rules.get("starting_pnl_balance") is not None:
        return float(stage_rules["starting_pnl_balance"])
    if stage_rules.get("starting_balance") is not None:
        return float(stage_rules["starting_balance"])
    return float(account_size)


def _eligible_work(ledger: pd.DataFrame, include_review: bool) -> pd.DataFrame:
    allowed = {"VALID", "REVIEW"} if include_review else {"VALID"}
    work = ledger[ledger["validity_status"].isin(allowed)].copy()
    work["__entry"] = pd.to_datetime(work["entry_time_et"], errors="coerce", utc=True)
    work = work.sort_values(["__entry", "source_file", "source_trade_id"], na_position="last").drop(columns="__entry").reset_index(drop=True)
    if work.empty:
        raise HistoricalRunnerError("No eligible trades remain after audit/status filtering")
    return work


def _eval_pass_state(product_id: str, stage_rules: Dict[str, Any], session_pnls: Iterable[float], total_profit: float, traded_days: int) -> Dict[str, Any]:
    progress = _target_progress(product_id, stage_rules, session_pnls, total_profit)
    min_days = int(stage_rules.get("min_days") or 0)
    days_ok = traded_days >= min_days
    consistency_ok = bool(progress.get("consistency_pass", True))
    target_ok = bool(progress.get("target_reached", False))
    return {**progress, "minimum_days_required": min_days, "minimum_days_met": days_ok, "evaluation_pass_ready": target_ok and consistency_ok and days_ok}


def _payout_share(payout_rules: Dict[str, Any], config: LifecycleConfig) -> float:
    pct = config.reward_share_override_percent
    if pct is None:
        pct = payout_rules.get("profit_split_percent", 100)
    return float(pct) / 100.0


def _cycle_consistency_ok(session_pnls: List[float], cycle_profit: float, pct: Optional[float]) -> Tuple[bool, Optional[float]]:
    if pct in (None, 0):
        return True, None
    profitable = [float(x) for x in session_pnls if float(x) > 0]
    largest = max(profitable) if profitable else 0.0
    ratio = largest / cycle_profit * 100.0 if cycle_profit > 0 else math.inf if largest > 0 else 0.0
    # Most firms express this as a maximum percentage. Apex language says 50% or more is
    # not eligible; use a tiny strictness margin there in its product-specific handler.
    return ratio <= float(pct) + 1e-12, ratio


def _payout_quote(
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
    request_mode: str,
) -> Dict[str, Any]:
    support = _PAYOUT_ENGINE_SUPPORT.get(product_id)
    if not support:
        return {"supported": False, "eligible": False, "reason": "PAYOUT_ENGINE_NOT_MODELED", "gross_request": 0.0, "available_now": 0.0}
    if request_mode == "NONE":
        return {"supported": True, "eligible": False, "reason": "AUTO_PAYOUT_DISABLED", "gross_request": 0.0, "available_now": 0.0}

    q_required = int(payout_rules.get("qualifying_days") or 0)
    q_ok = qualifying_days >= q_required
    cycle_profit = balance - cycle_start_balance
    total_profit = balance - start_balance
    min_payout = float(payout_rules.get("minimum_payout") or 0.0)
    max_count = payout_rules.get("maximum_payouts")
    if max_count is not None and payout_count >= int(max_count):
        return {"supported": True, "eligible": False, "reason": "MAX_PAYOUTS_REACHED", "gross_request": 0.0, "available_now": 0.0, "cycle_profit": cycle_profit, "total_profit": total_profit}

    eligible = False
    available = 0.0
    reason = "NOT_ELIGIBLE"
    consistency_ratio = None

    if product_id == "lucid_flex":
        # 5 qualifying days, positive cycle profit. Up to 50% of current total simulated
        # profit, capped by account size; no buffer requirement.
        available = min(max(0.0, total_profit) * float(payout_rules.get("withdrawal_fraction") or 0.5), float(payout_rules.get("maximum_payout") or math.inf))
        eligible = q_ok and cycle_profit > 0 and available >= min_payout - 1e-9
        reason = "ELIGIBLE" if eligible else "NEED_QUALIFYING_DAYS_OR_PROFIT"

    elif product_id == "tradeify_select_flex":
        available = min(max(0.0, total_profit) * float(payout_rules.get("withdrawal_fraction") or 0.5), float(payout_rules.get("maximum_payout") or math.inf))
        # First payout does not require positive profit *since a prior payout* beyond the
        # total profit needed to fund the request. Later cycles must be net positive.
        cycle_ok = True if payout_count == 0 else cycle_profit > 0
        eligible = q_ok and cycle_ok and available > 0
        reason = "ELIGIBLE" if eligible else "NEED_WINNING_DAYS_OR_POSITIVE_CYCLE"

    elif product_id == "fundednext_flex":
        min_cycle = float(payout_rules.get("cycle_min_profit") or 0.0)
        available = min(max(0.0, total_profit) * float(payout_rules.get("withdrawal_fraction") or 0.5), float(payout_rules.get("maximum_payout") or math.inf))
        eligible = q_ok and cycle_profit >= min_cycle - 1e-9 and available >= min_payout - 1e-9
        reason = "ELIGIBLE" if eligible else "NEED_BENCHMARK_DAYS_OR_CYCLE_PROFIT"

    elif product_id == "mffu_flex_50k":
        min_cycle = float(payout_rules.get("cycle_min_profit") or 0.0)
        available = min(max(0.0, balance) * float(payout_rules.get("withdrawal_fraction") or 0.5), float(payout_rules.get("maximum_payout") or math.inf))
        eligible = q_ok and cycle_profit >= min_cycle - 1e-9 and available >= min_payout - 1e-9
        reason = "ELIGIBLE" if eligible else "NEED_WINNING_DAYS_OR_CYCLE_PROFIT"

    elif product_id == "apex_eod":
        safety = float(payout_rules.get("safety_net") or (start_balance + abs(float(payout_rules.get("max_loss") or 0)) + 100.0))
        caps = payout_rules.get("caps") or []
        cap = float(caps[payout_count]) if payout_count < len(caps) else math.inf
        available = min(max(0.0, balance - safety), cap)
        cons_pct = payout_rules.get("consistency_percent")
        cons_ok, consistency_ratio = _cycle_consistency_ok(cycle_session_pnls, max(0.0, cycle_profit), cons_pct)
        if cons_pct is not None and consistency_ratio is not None:
            # Apex says 50% or more is not eligible.
            cons_ok = consistency_ratio < float(cons_pct) - 1e-12
        eligible = q_ok and cons_ok and available >= min_payout - 1e-9
        reason = "ELIGIBLE" if eligible else "NEED_DAYS_CONSISTENCY_OR_SAFETY_NET"

    elif product_id == "lucid_direct":
        goal = float(payout_rules.get("profit_goal_first") if payout_count == 0 else payout_rules.get("profit_goal_later") or 0.0)
        caps = payout_rules.get("caps") or []
        cap = float(caps[payout_count]) if payout_count < len(caps) else math.inf
        cons_ok, consistency_ratio = _cycle_consistency_ok(cycle_session_pnls, max(0.0, cycle_profit), payout_rules.get("consistency_percent"))
        available = min(max(0.0, total_profit), cap)
        eligible = cycle_profit >= goal - 1e-9 and cons_ok and available >= min_payout - 1e-9
        reason = "ELIGIBLE" if eligible else "NEED_PROFIT_GOAL_OR_CONSISTENCY"

    if not eligible:
        return {"supported": True, "eligible": False, "reason": reason, "gross_request": 0.0, "available_now": max(0.0, available), "cycle_profit": cycle_profit, "total_profit": total_profit, "consistency_ratio": consistency_ratio}

    gross = max(0.0, available)
    if request_mode == "MINIMUM_ONLY" and min_payout > 0:
        gross = min(gross, min_payout)
    return {"supported": True, "eligible": True, "reason": reason, "gross_request": gross, "available_now": max(0.0, available), "cycle_profit": cycle_profit, "total_profit": total_profit, "consistency_ratio": consistency_ratio}


def _funded_floor_after_payout(product_id: str, start_balance: float, current_floor: Optional[float], payout_count_after: int, payout_rules: Dict[str, Any]) -> Optional[float]:
    if current_floor is None:
        return None
    if product_id in {"lucid_flex", "tradeify_select_flex", "fundednext_flex", "apex_eod", "lucid_direct"}:
        return max(float(current_floor), start_balance + 100.0)
    if product_id == "mffu_flex_50k" and payout_count_after >= 1:
        # Current Flex rule explicitly resets the MLL to $100 after the first payout,
        # even if the pre-payout EOD trail had already risen above that level.
        return float(payout_rules.get("post_first_payout_floor") or 100.0)
    return current_floor


def run_stage(rulebook: Dict[str, Any], ledger: pd.DataFrame, config: LifecycleConfig, stage: str) -> StageRun:
    if stage not in {"evaluation", "sim_funded"}:
        raise HistoricalRunnerError("v4C supports evaluation or sim_funded stages")
    if config.max_trades_per_session < 1:
        raise HistoricalRunnerError("max_trades_per_session must be >= 1")

    firm, product, stage_rules = _stage_rules(rulebook, config, stage)
    rcfg = _runner_cfg(config, stage)
    policy = resolve_drawdown_policy(rulebook, rcfg)
    start_balance = _resolve_start_balance(config.product_id, config.account_size, stage, stage_rules)
    floor = _initial_floor(start_balance, policy)
    highest_eod = start_balance
    balance = start_balance
    status = "ACTIVE"
    failure_reason = ""
    stop_session = None
    pass_session = None
    min_cushion = math.inf
    total_commission = 0.0
    routed = 0
    skipped_cap = 0
    skipped_inactive = 0
    dll_triggers = 0
    mae_missing = 0
    intraday_ambiguous = 0
    session_rows: List[Dict[str, Any]] = []
    trade_rows: List[Dict[str, Any]] = []
    payout_rows: List[Dict[str, Any]] = []

    work = _eligible_work(ledger, config.include_review_rows)
    session_signal_counts = work.groupby("futures_session_id", dropna=False).size().to_dict()
    completed_session_pnls: List[float] = []
    traded_session_count = 0

    payout_rules = stage_rules.get("payout") or {}
    payout_count = 0
    gross_payouts = 0.0
    wallet_cash = 0.0
    cycle_start_balance = start_balance
    cycle_session_pnls: List[float] = []
    qualifying_days = 0
    last_payout_quote: Dict[str, Any] = {"supported": bool(_PAYOUT_ENGINE_SUPPORT.get(config.product_id)), "eligible": False, "available_now": 0.0, "reason": "NOT_CHECKED"}

    first_session_dt = None
    access_days = stage_rules.get("access_calendar_days")

    for sid, group in work.groupby("futures_session_id", sort=False, dropna=False):
        sid = str(sid)
        try:
            sid_dt = pd.Timestamp(sid).tz_localize("America/New_York") if pd.Timestamp(sid).tzinfo is None else pd.Timestamp(sid)
        except Exception:
            sid_dt = None
        if first_session_dt is None and sid_dt is not None:
            first_session_dt = sid_dt
        if stage == "evaluation" and status == "ACTIVE" and access_days and first_session_dt is not None and sid_dt is not None:
            if (sid_dt.normalize() - first_session_dt.normalize()).days >= int(access_days):
                status = "EXPIRED"
                stop_session = sid

        if status != "ACTIVE":
            for _, row in group.iterrows():
                skipped_inactive += 1
                trade_rows.append({
                    "futures_session_id": sid, "entry_time_et": row.get("entry_time_et"), "source_file": row.get("source_file"), "source_trade_id": row.get("source_trade_id"),
                    "decision": "SKIP_ACCOUNT_INACTIVE", "skip_reason": status, "gross_pnl": row.get("normalized_gross_pnl"), "commission": 0.0,
                    "net_pnl": 0.0, "balance_before": balance, "balance_after": balance, "floor_before": floor, "floor_after": floor,
                    "mae": row.get("MAE"), "mfe": row.get("MFE"), "breach": False,
                })
            continue

        session_start_balance = balance
        session_floor_start = floor
        session_net = 0.0
        session_source_net = 0.0
        session_gross = 0.0
        session_commission = 0.0
        session_routed = 0
        session_dll_paused = False
        session_breached = False

        for ordinal, (_, row) in enumerate(list(group.iterrows()), start=1):
            if status != "ACTIVE":
                decision, skip_reason = "SKIP_ACCOUNT_INACTIVE", status
                skipped_inactive += 1
            elif session_dll_paused:
                decision, skip_reason = "SKIP_SESSION_PAUSED_DLL", "DLL_PAUSE"
                skipped_cap += 1
            elif session_routed >= config.max_trades_per_session:
                decision, skip_reason = "SKIP_SESSION_CAP", f"max_{config.max_trades_per_session}_trades_per_session"
                skipped_cap += 1
            else:
                decision, skip_reason = "ROUTE", ""

            if decision != "ROUTE":
                trade_rows.append({
                    "futures_session_id": sid, "session_signal_ordinal": ordinal, "entry_time_et": row.get("entry_time_et"), "exit_time_et": row.get("exit_time_et"),
                    "source_file": row.get("source_file"), "source_trade_id": row.get("source_trade_id"), "decision": decision, "skip_reason": skip_reason,
                    "gross_pnl": row.get("normalized_gross_pnl"), "commission": 0.0, "net_pnl": 0.0,
                    "balance_before": balance, "balance_after": balance, "floor_before": floor, "floor_after": floor,
                    "mae": row.get("MAE"), "mfe": row.get("MFE"), "breach": False,
                })
                continue

            contracts = abs(float(row.get("contracts") or 0.0))
            commission = contracts * float(config.commission_per_contract_round_trip)
            gross = float(row.get("normalized_gross_pnl") or 0.0)
            net = gross - commission
            mae = float(row.get("MAE")) if pd.notna(row.get("MAE")) else math.nan
            mfe = float(row.get("MFE")) if pd.notna(row.get("MFE")) else math.nan
            if not math.isfinite(mae):
                mae_missing += 1
                mae = min(0.0, gross)
            if not math.isfinite(mfe):
                mfe = max(0.0, gross)

            balance_before = balance
            floor_before = floor
            low = _trade_low(balance_before, mae, commission)
            peak = _trade_peak(balance_before, mfe)
            if policy.drawdown_type == "INTRADAY_TRAILING" and floor is not None:
                intraday_ambiguous += 1
                if config.intraday_order_assumption == "MFE_BEFORE_MAE_CONSERVATIVE":
                    floor = _intraday_ratchet_floor(floor, peak, policy)

            breach = bool(floor is not None and low <= floor + 1e-9)
            dll = stage_rules.get("dll") or {}
            dll_amount = dll.get("amount")
            dll_action = dll.get("action", "NONE")
            dll_hit = False
            if dll_amount not in (None, 0) and dll_action != "NONE":
                dll_low = session_net + min(0.0, mae) - commission
                if dll_low <= -float(dll_amount) + 1e-9:
                    dll_hit = True
                    dll_triggers += 1

            if breach:
                status = "FAILED"
                failure_reason = "MAX_LOSS_FLOOR_BREACH"
                stop_session = sid
                session_breached = True
                balance = float(floor)
                realized_net = balance - balance_before
            elif dll_hit and dll_action in {"SOFT_PAUSE_SESSION", "LIQUIDATE_AND_PAUSE"}:
                allowed_loss = max(0.0, float(dll_amount) + session_net)
                realized_net = max(net, -allowed_loss)
                balance += realized_net
                session_dll_paused = True
            elif dll_hit and dll_action == "HARD_FAIL":
                status = "FAILED"
                failure_reason = "DAILY_LOSS_LIMIT_HARD_FAIL"
                stop_session = sid
                session_breached = True
                realized_net = net
                balance += realized_net
            else:
                realized_net = net
                balance += realized_net

            if policy.drawdown_type == "INTRADAY_TRAILING" and floor is not None and not breach and config.intraday_order_assumption == "MAE_BEFORE_MFE_OPTIMISTIC":
                floor = _intraday_ratchet_floor(floor, peak, policy)

            routed += 1
            session_routed += 1
            session_gross += gross
            session_commission += commission
            total_commission += commission
            session_net += realized_net
            session_source_net += net
            if floor_before is not None:
                min_cushion = min(min_cushion, balance_before - floor_before, low - floor_before)

            trade_rows.append({
                "futures_session_id": sid, "session_signal_ordinal": ordinal, "entry_time_et": row.get("entry_time_et"), "exit_time_et": row.get("exit_time_et"),
                "source_file": row.get("source_file"), "source_trade_id": row.get("source_trade_id"), "decision": "ROUTE", "skip_reason": "",
                "direction": row.get("direction"), "contracts": contracts, "gross_pnl": gross, "commission": commission,
                "source_net_pnl": net, "account_realized_net_pnl": realized_net, "balance_before": balance_before, "balance_after": balance,
                "floor_before": floor_before, "floor_after": floor, "mae": mae, "mfe": mfe, "intratrade_low": low, "intratrade_peak": peak,
                "breach": breach, "dll_hit": dll_hit, "dll_action": dll_action, "account_status_after": status,
                "source_validity": row.get("validity_status"), "audit_warnings": row.get("audit_warnings"),
            })

        if session_routed > 0:
            traded_session_count += 1
        if status == "ACTIVE":
            highest_eod = max(highest_eod, balance)
            floor = _eod_update_floor(floor, highest_eod, policy)

        completed_session_pnls.append(session_net)
        cycle_session_pnls.append(session_net)
        total_profit = balance - start_balance
        progress = _eval_pass_state(config.product_id, stage_rules, completed_session_pnls, total_profit, traded_session_count) if stage == "evaluation" else _target_progress(config.product_id, stage_rules, completed_session_pnls, total_profit)

        pre_payout_balance = balance
        payout_event = None
        if stage == "evaluation" and status == "ACTIVE" and progress.get("evaluation_pass_ready"):
            status = "PASSED"
            pass_session = sid
            stop_session = sid
        elif stage == "sim_funded" and status == "ACTIVE" and payout_rules:
            q_threshold = float(payout_rules.get("qualifying_day_profit") or 0.0)
            if q_threshold > 0 and session_net >= q_threshold - 1e-9:
                qualifying_days += 1
            last_payout_quote = _payout_quote(
                config.product_id, config.account_size, payout_rules,
                start_balance=start_balance, balance=balance, cycle_start_balance=cycle_start_balance,
                cycle_session_pnls=cycle_session_pnls, qualifying_days=qualifying_days,
                payout_count=payout_count, request_mode=config.payout_request_mode,
            )
            if last_payout_quote.get("eligible") and float(last_payout_quote.get("gross_request") or 0.0) > 0:
                gross_request = float(last_payout_quote["gross_request"])
                share = _payout_share(payout_rules, config)
                trader_cash = gross_request * share
                pre = balance
                balance -= gross_request
                payout_count += 1
                gross_payouts += gross_request
                wallet_cash += trader_cash
                floor = _funded_floor_after_payout(config.product_id, start_balance, floor, payout_count, payout_rules)
                payout_event = {
                    "payout_number": payout_count, "futures_session_id": sid,
                    "gross_request": gross_request, "trader_share_percent": share * 100.0,
                    "trader_cash": trader_cash, "balance_before_payout": pre, "balance_after_payout": balance,
                    "floor_after_payout": floor, "qualifying_days_used": qualifying_days,
                    "cycle_profit_before_payout": last_payout_quote.get("cycle_profit"),
                }
                payout_rows.append(payout_event)
                qualifying_days = 0
                cycle_start_balance = balance
                cycle_session_pnls = []
                max_payouts = payout_rules.get("maximum_payouts")
                if max_payouts is not None and payout_count >= int(max_payouts):
                    status = "PAYOUT_CYCLE_COMPLETE"
                    stop_session = sid

        session_rows.append({
            "futures_session_id": sid, "source_signals": int(session_signal_counts.get(sid, len(group))), "trades_routed": session_routed,
            "session_start_balance": session_start_balance, "session_gross_pnl": session_gross, "session_commission": session_commission,
            "session_source_trade_net_pnl": session_source_net, "session_account_realized_trading_pnl": session_net,
            "session_net_pnl": session_net, "pre_payout_balance": pre_payout_balance,
            "payout_deduction_gross": 0.0 if payout_event is None else payout_event["gross_request"],
            "payout_cash_to_trader": 0.0 if payout_event is None else payout_event["trader_cash"],
            "session_end_balance": balance, "floor_start": session_floor_start, "floor_end": floor,
            "highest_eod_balance": highest_eod, "session_dll_paused": session_dll_paused, "session_breached": session_breached,
            "account_status": status, "qualifying_days_current_cycle": qualifying_days, "payout_count": payout_count,
            "wallet_cash": wallet_cash, "payout_event_gross": None if payout_event is None else payout_event["gross_request"],
            **progress,
        })

    # End-of-data value is deliberately decomposed instead of pretending active simulated
    # account profit is identical to cash already withdrawn.
    if stage == "sim_funded" and payout_rules:
        last_payout_quote = _payout_quote(
            config.product_id, config.account_size, payout_rules,
            start_balance=start_balance, balance=balance, cycle_start_balance=cycle_start_balance,
            cycle_session_pnls=cycle_session_pnls, qualifying_days=qualifying_days,
            payout_count=payout_count, request_mode="MAX_ALLOWED",
        )
    total_profit = balance - start_balance
    progress = _eval_pass_state(config.product_id, stage_rules, completed_session_pnls, total_profit, traded_session_count) if stage == "evaluation" else _target_progress(config.product_id, stage_rules, completed_session_pnls, total_profit)
    coverage = assess_rule_coverage(rulebook, config.product_id, config.account_size, stage)
    production_grade = policy.confidence.startswith("VERIFIED") and policy.drawdown_type in {"EOD_TRAILING", "STATIC", "NONE"} and mae_missing == 0 and policy.floor_lock_behavior != "VARIANT_SELECTION_REQUIRED"
    if stage == "sim_funded" and payout_rules and not _PAYOUT_ENGINE_SUPPORT.get(config.product_id):
        production_grade = False

    source_hashes = sorted(set(str(x) for x in work.get("source_sha256", pd.Series(dtype=str)).dropna().unique()))
    rule_snapshot = {
        "rulebook_schema_version": rulebook.get("schema_version"), "verified_as_of": rulebook.get("verified_as_of"),
        "firm_id": firm.get("firm_id"), "firm": firm.get("display_name"), "product_id": product.get("product_id"), "product": product.get("display_name"),
        "account_size": config.account_size, "stage": stage, "stage_rules": stage_rules, "drawdown_policy": asdict(policy), "sources": product.get("sources", []),
    }
    fingerprint = sha256_text(stable_json({"engine": LIFECYCLE_ENGINE_VERSION, "config": asdict(config), "stage": stage, "source_hashes": source_hashes, "rule_snapshot": rule_snapshot}))[:16]
    summary = {
        "engine_version": LIFECYCLE_ENGINE_VERSION, "schema_version": LIFECYCLE_SCHEMA_VERSION, "run_id": f"SB4C-{fingerprint}",
        "firm": firm.get("display_name"), "product": product.get("display_name"), "product_id": config.product_id, "account_size": config.account_size, "stage": stage,
        "starting_balance": start_balance, "ending_balance": balance, "net_account_change": total_profit,
        "status": status, "failure_reason": failure_reason, "stop_session": stop_session, "pass_session": pass_session,
        "initial_failure_floor": _initial_floor(start_balance, policy), "ending_failure_floor": floor, "highest_eod_balance": highest_eod,
        "minimum_observed_cushion": None if min_cushion is math.inf or not math.isfinite(min_cushion) else min_cushion,
        "source_eligible_trades": int(len(work)), "source_futures_sessions": int(work["futures_session_id"].nunique()),
        "traded_sessions": int(traded_session_count), "trades_routed": int(routed), "signals_skipped_by_session_cap_or_pause": int(skipped_cap),
        "signals_skipped_after_account_inactive": int(skipped_inactive), "max_trades_per_account_per_session": config.max_trades_per_session,
        "total_firm_commissions": total_commission, "dll_triggers": int(dll_triggers), "mae_fallback_count": int(mae_missing),
        "intraday_path_ambiguous_trades": int(intraday_ambiguous), "rule_coverage": coverage.get("status"), "production_grade_rule_path": bool(production_grade),
        "drawdown_policy_confidence": policy.confidence, "drawdown_type": policy.drawdown_type, "floor_lock_behavior": policy.floor_lock_behavior,
        "payout_engine_support": _PAYOUT_ENGINE_SUPPORT.get(config.product_id, "NOT_MODELED"), "payout_count": int(payout_count),
        "gross_payouts_deducted": gross_payouts, "trader_wallet_cash": wallet_cash, "qualifying_days_current_cycle": int(qualifying_days),
        "cycle_profit_current": balance - cycle_start_balance if stage == "sim_funded" else None,
        "payout_available_now_gross": float(last_payout_quote.get("available_now") or 0.0) if stage == "sim_funded" else 0.0,
        "payout_eligible_now": bool(last_payout_quote.get("eligible")) if stage == "sim_funded" else False,
        "payout_eligibility_reason": last_payout_quote.get("reason") if stage == "sim_funded" else None,
        "source_hashes": source_hashes, **progress,
    }
    return StageRun(summary=summary, trades=pd.DataFrame(trade_rows), sessions=pd.DataFrame(session_rows), payouts=pd.DataFrame(payout_rows), config=asdict(config), rule_snapshot=rule_snapshot)


def _ledger_after_session(ledger: pd.DataFrame, session_id: str) -> pd.DataFrame:
    if not session_id:
        return ledger.iloc[0:0].copy()
    sid = pd.to_datetime(session_id, errors="coerce")
    sess = pd.to_datetime(ledger["futures_session_id"], errors="coerce")
    return ledger[sess > sid].copy()


def run_lifecycle(rulebook: Dict[str, Any], ledger: pd.DataFrame, config: LifecycleConfig) -> LifecycleRun:
    mode = config.mode.upper()
    if mode not in {"EVALUATION_ONLY", "FUNDED_ONLY", "EVAL_TO_FUNDED"}:
        raise HistoricalRunnerError("Unknown lifecycle mode")
    evaluation = funded = None
    if mode in {"EVALUATION_ONLY", "EVAL_TO_FUNDED"}:
        evaluation = run_stage(rulebook, ledger, config, "evaluation")
        if mode == "EVAL_TO_FUNDED" and evaluation.summary.get("status") == "PASSED":
            _, product, _ = _stage_rules(rulebook, config, "evaluation")
            size_rules = product.get("account_sizes", {}).get(str(config.account_size), {})
            if not size_rules.get("sim_funded"):
                raise HistoricalRunnerError("This product has no sim-funded stage to activate after evaluation")
            remaining = _ledger_after_session(ledger, evaluation.summary.get("pass_session"))
            if not remaining.empty:
                funded = run_stage(rulebook, remaining, config, "sim_funded")
    if mode == "FUNDED_ONLY":
        funded = run_stage(rulebook, ledger, config, "sim_funded")

    wallet = float(funded.summary.get("trader_wallet_cash") or 0.0) if funded else 0.0
    available = float(funded.summary.get("payout_available_now_gross") or 0.0) if funded else 0.0
    summary = {
        "engine_version": LIFECYCLE_ENGINE_VERSION, "mode": mode,
        "evaluation_status": None if evaluation is None else evaluation.summary.get("status"),
        "evaluation_pass_session": None if evaluation is None else evaluation.summary.get("pass_session"),
        "funded_status": None if funded is None else funded.summary.get("status"),
        "funded_payouts": 0 if funded is None else funded.summary.get("payout_count", 0),
        "trader_wallet_cash": wallet,
        "unpaid_payout_available_gross": available,
        "ending_funded_balance": None if funded is None else funded.summary.get("ending_balance"),
        "ending_funded_floor": None if funded is None else funded.summary.get("ending_failure_floor"),
        "active_value_not_cash": None if funded is None else funded.summary.get("net_account_change"),
        "status_note": "End-of-data balances and payout availability are preserved separately from cash already withdrawn.",
    }
    return LifecycleRun(summary=summary, evaluation=evaluation, funded=funded, config=asdict(config))


def comparison_rows(rulebook: Dict[str, Any], ledger: pd.DataFrame, configs: Iterable[LifecycleConfig]) -> pd.DataFrame:
    rows = []
    for cfg in configs:
        try:
            result = run_lifecycle(rulebook, ledger, cfg)
            stage = result.evaluation if cfg.mode == "EVALUATION_ONLY" else result.funded
            if cfg.mode == "EVAL_TO_FUNDED":
                stage = result.funded or result.evaluation
            s = stage.summary if stage else {}
            rows.append({
                "firm": s.get("firm"), "product": s.get("product"), "size": cfg.account_size, "mode": cfg.mode,
                "status": s.get("status"), "trades": s.get("trades_routed"), "sessions": s.get("traded_sessions"),
                "ending_balance": s.get("ending_balance"), "net_account_change": s.get("net_account_change"),
                "payouts": result.summary.get("funded_payouts"), "wallet_cash": result.summary.get("trader_wallet_cash"),
                "unpaid_payout_available": result.summary.get("unpaid_payout_available_gross"),
                "evaluation_status": result.summary.get("evaluation_status"), "funded_status": result.summary.get("funded_status"),
                "production_grade": s.get("production_grade_rule_path"), "payout_engine": s.get("payout_engine_support"),
                "rankable": bool(s.get("production_grade_rule_path")) and (cfg.mode == "EVALUATION_ONLY" or s.get("payout_engine_support") != "NOT_MODELED"),
                "run_id": s.get("run_id"), "error": "",
            })
        except Exception as exc:
            rows.append({"firm": None, "product": cfg.product_id, "size": cfg.account_size, "mode": cfg.mode, "status": "ERROR", "error": str(exc)})
    return pd.DataFrame(rows)


def build_lifecycle_bundle(result: LifecycleRun) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("LIFECYCLE_SUMMARY.json", json.dumps(result.summary, indent=2, default=str))
        z.writestr("CONFIG.json", json.dumps(result.config, indent=2, default=str))
        for name, stage in (("EVALUATION", result.evaluation), ("FUNDED", result.funded)):
            if stage is None:
                continue
            z.writestr(f"{name}_SUMMARY.json", json.dumps(stage.summary, indent=2, default=str))
            z.writestr(f"{name}_RULE_SNAPSHOT.json", json.dumps(stage.rule_snapshot, indent=2, default=str))
            z.writestr(f"{name}_TRADE_ROUTING.csv", stage.trades.to_csv(index=False))
            z.writestr(f"{name}_SESSION_LEDGER.csv", stage.sessions.to_csv(index=False))
            z.writestr(f"{name}_PAYOUT_LEDGER.csv", stage.payouts.to_csv(index=False))
        lines = [
            "# StarBase v4C Lifecycle Run", "",
            f"Mode: **{result.summary.get('mode')}**",
            f"Evaluation status: **{result.summary.get('evaluation_status')}**",
            f"Funded status: **{result.summary.get('funded_status')}**",
            f"Funded payouts: **{result.summary.get('funded_payouts')}**",
            f"Trader wallet cash: **${result.summary.get('trader_wallet_cash',0):,.2f}**",
            f"Unpaid payout available at end: **${result.summary.get('unpaid_payout_available_gross',0):,.2f}**",
            "",
            "End-of-data active account value is preserved separately from realized payout cash.",
            "Fleet fan-out, passed-evaluation banking, household limits and live transitions are intentionally later stages.",
        ]
        z.writestr("REPORT.md", "\n".join(lines) + "\n")
    return buf.getvalue()
