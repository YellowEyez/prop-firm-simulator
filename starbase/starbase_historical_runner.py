"""Project StarBase v4B chronological single-account historical runner.

v4B is the first StarBase engine that consumes audited TradingView trades and routes
those trades through one prop account chronologically. It enforces trade/session caps,
firm commissions, drawdown floors, MAE-aware breaches and basic soft DLL pauses.

Evaluation pass/funded activation and payout transitions remain later v4 stages. v4B
shows target/consistency progress but does not automatically change stage.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from io import BytesIO
import json
import math
from typing import Any, Dict, Iterable, List, Optional, Tuple
import zipfile

import pandas as pd

from starbase_integrity import assess_rule_coverage, drawdown_semantics, sha256_text, stable_json
from starbase_rulebook import product_details

RUNNER_ENGINE_VERSION = "4.0B"
RUNNER_SCHEMA_VERSION = "4B.0.0"


class HistoricalRunnerError(ValueError):
    pass


@dataclass(frozen=True)
class DrawdownPolicy:
    drawdown_type: str
    max_loss: float
    floor_update_basis: str
    breach_test_basis: str
    breach_frequency: str
    floor_lock_behavior: str
    lock_floor: Optional[float]
    policy_source: str
    confidence: str
    notes: str = ""


@dataclass(frozen=True)
class RunnerConfig:
    product_id: str
    account_size: int
    stage: str
    max_trades_per_session: int = 1
    commission_per_contract_round_trip: float = 0.0
    include_review_rows: bool = False
    intraday_order_assumption: str = "MFE_BEFORE_MAE_CONSERVATIVE"
    starting_balance_override: Optional[float] = None
    platform_variant: str = "DEFAULT"


@dataclass
class HistoricalRunResult:
    summary: Dict[str, Any]
    trades: pd.DataFrame
    sessions: pd.DataFrame
    config: Dict[str, Any]
    rule_snapshot: Dict[str, Any]


# Explicit current rule semantics verified for the products we actively use. These
# enrich the v3 rulebook without pretending a generic drawdown label is enough.
# Values are expressed as lock-floor offsets from the nominal account balance.
_EXPLICIT_POLICIES: Dict[Tuple[str, str], Dict[str, Any]] = {
    ("lucid_flex", "evaluation"): {
        "floor_update_basis": "END_OF_SESSION_HIGH_CLOSE",
        "breach_test_basis": "INTRADAY_EQUITY_OR_MAE",
        "breach_frequency": "TRADE_PATH",
        "floor_lock_behavior": "LOCK_AT_START_PLUS_100",
        "confidence": "VERIFIED_PRODUCT",
        "notes": "LucidFlex evaluation EOD MLL trails highest closing balance and locks at starting balance + $100.",
    },
    ("lucid_flex", "sim_funded"): {
        "floor_update_basis": "END_OF_SESSION_HIGH_CLOSE",
        "breach_test_basis": "INTRADAY_EQUITY_OR_MAE",
        "breach_frequency": "TRADE_PATH",
        "floor_lock_behavior": "LOCK_AT_START_PLUS_100",
        "confidence": "VERIFIED_PRODUCT",
        "notes": "LucidFlex funded EOD MLL trails highest closing balance and locks at starting balance + $100; payouts later reset/lock under v4F.",
    },
    ("lucid_direct", "sim_funded"): {
        "floor_update_basis": "END_OF_SESSION_HIGH_CLOSE",
        "breach_test_basis": "INTRADAY_EQUITY_OR_MAE",
        "breach_frequency": "TRADE_PATH",
        "floor_lock_behavior": "LOCK_AT_START_PLUS_100",
        "confidence": "VERIFIED_PRODUCT",
        "notes": "LucidDirect funded EOD MLL locks at starting balance + $100.",
    },
    ("tradeify_select_flex", "evaluation"): {
        "floor_update_basis": "END_OF_SESSION_HIGH_CLOSE",
        "breach_test_basis": "INTRADAY_EQUITY_OR_MAE",
        "breach_frequency": "TRADE_PATH",
        "floor_lock_behavior": "NO_LOCK_EVALUATION",
        "confidence": "VERIFIED_PRODUCT",
        "notes": "Tradeify Select evaluation uses EOD trailing drawdown; official rule states evaluation drawdown does not lock.",
    },
    ("tradeify_select_flex", "sim_funded"): {
        "floor_update_basis": "END_OF_SESSION_HIGH_CLOSE",
        "breach_test_basis": "INTRADAY_EQUITY_OR_MAE",
        "breach_frequency": "TRADE_PATH",
        "floor_lock_behavior": "LOCK_AT_START_PLUS_100",
        "confidence": "VERIFIED_PRODUCT",
        "notes": "Tradeify Select Flex funded EOD drawdown locks at starting balance + $100.",
    },
    ("fundednext_flex", "evaluation"): {
        "floor_update_basis": "END_OF_SESSION_HIGH_CLOSE",
        "breach_test_basis": "INTRADAY_EQUITY_OR_MAE",
        "breach_frequency": "TRADE_PATH",
        "floor_lock_behavior": "LOCK_AT_START_PLUS_100",
        "confidence": "VERIFIED_PRODUCT",
        "notes": "FundedNext Futures Flex Challenge EOD MLL locks at starting balance + $100.",
    },
    ("fundednext_flex", "sim_funded"): {
        "floor_update_basis": "END_OF_SESSION_HIGH_CLOSE",
        "breach_test_basis": "INTRADAY_EQUITY_OR_MAE",
        "breach_frequency": "TRADE_PATH",
        "floor_lock_behavior": "LOCK_AT_START_PLUS_100",
        "confidence": "VERIFIED_PRODUCT",
        "notes": "FundedNext Futures Flex funded EOD MLL locks at starting balance + $100; first reward lock/reset is handled later in v4F.",
    },
    ("apex_eod", "evaluation"): {
        "floor_update_basis": "END_OF_SESSION_HIGH_CLOSE",
        "breach_test_basis": "INTRADAY_EQUITY_OR_MAE",
        "breach_frequency": "TRADE_PATH",
        "floor_lock_behavior": "NO_LOCK_EVALUATION",
        "confidence": "VERIFIED_PRODUCT",
        "notes": "Current Apex EOD Evaluation recalculates the threshold at EOD and enforces it intraday; the evaluation ends when the profit target is reached, so legacy platform-specific trailing-stop rules are not applied to the current EOD product.",
    },
    ("apex_eod", "sim_funded"): {
        "floor_update_basis": "END_OF_SESSION_HIGH_CLOSE",
        "breach_test_basis": "INTRADAY_EQUITY_OR_MAE",
        "breach_frequency": "TRADE_PATH",
        "floor_lock_behavior": "LOCK_AT_START_PLUS_100",
        "confidence": "VERIFIED_PRODUCT",
        "notes": "Apex EOD PA threshold updates EOD, is enforced intraday, and stops at starting balance + $100.",
    },
}


def _find_stage(rulebook: Dict[str, Any], product_id: str, account_size: int, stage: str) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    details = product_details(rulebook, product_id)
    product = details["product"]
    size_rules = product.get("account_sizes", {}).get(str(int(account_size)))
    if not size_rules or not size_rules.get(stage):
        raise HistoricalRunnerError(f"{product_id} ${account_size:,} has no {stage} rules in StarBase v3 rulebook")
    return details["firm"], product, size_rules[stage]


def resolve_starting_balance(product_id: str, account_size: int, stage: str, stage_rules: Dict[str, Any], override: Optional[float] = None) -> float:
    if override is not None:
        return float(override)
    if stage_rules.get("starting_balance") is not None:
        return float(stage_rules["starting_balance"])
    # Current MFFU Flex/Rapid sim-funded programs are profit-account style ($0 start).
    if stage == "sim_funded" and product_id in {"mffu_flex50", "mffu_rapid50"}:
        return 0.0
    return float(account_size)


def resolve_drawdown_policy(rulebook: Dict[str, Any], config: RunnerConfig) -> DrawdownPolicy:
    firm, product, stage_rules = _find_stage(rulebook, config.product_id, config.account_size, config.stage)
    dd_type = str(stage_rules.get("drawdown_type") or "NONE")
    max_loss = float(stage_rules.get("max_loss") or 0.0)
    start = resolve_starting_balance(config.product_id, config.account_size, config.stage, stage_rules, config.starting_balance_override)

    explicit = _EXPLICIT_POLICIES.get((config.product_id, config.stage))

    if explicit is None:
        base = drawdown_semantics(dd_type, stage_rules.get("drawdown_semantics"))
        explicit = {
            "floor_update_basis": base.get("floor_update_basis", "UNKNOWN"),
            "breach_test_basis": base.get("breach_test_basis", "UNKNOWN"),
            "breach_frequency": base.get("breach_frequency", "TRADE_PATH"),
            "floor_lock_behavior": base.get("floor_lock_behavior", "UNKNOWN"),
            "confidence": "CLASS_DEFAULT_RESEARCH",
            "notes": "No product-specific v4B drawdown semantics are encoded yet; research-grade class default only.",
        }

    lock_behavior = explicit["floor_lock_behavior"]
    lock_floor: Optional[float] = None
    if lock_behavior == "LOCK_AT_START_PLUS_100":
        # For zero-based profit-account structures, the nominal account size is not the displayed P&L balance.
        # Those products stay research-grade until their exact floor representation is encoded.
        lock_floor = (start + 100.0) if start != 0 else None
    elif lock_behavior == "LOCK_AT_PROFIT_TARGET_BALANCE":
        lock_floor = start + float(stage_rules.get("profit_target") or 0.0)

    return DrawdownPolicy(
        drawdown_type=dd_type,
        max_loss=max_loss,
        floor_update_basis=explicit["floor_update_basis"],
        breach_test_basis=explicit["breach_test_basis"],
        breach_frequency=explicit["breach_frequency"],
        floor_lock_behavior=lock_behavior,
        lock_floor=lock_floor,
        policy_source=f"{firm['display_name']} / {product['display_name']} / StarBase explicit v4B" if (config.product_id, config.stage) in _EXPLICIT_POLICIES or config.product_id == "apex_eod" else "StarBase drawdown class default",
        confidence=explicit["confidence"],
        notes=explicit.get("notes", ""),
    )


def _initial_floor(start_balance: float, policy: DrawdownPolicy) -> Optional[float]:
    if policy.drawdown_type == "NONE" or policy.max_loss <= 0:
        return None
    return start_balance - policy.max_loss


def _cap_floor(raw_floor: float, policy: DrawdownPolicy) -> float:
    if policy.lock_floor is None:
        return raw_floor
    return min(raw_floor, policy.lock_floor)


def _eod_update_floor(current_floor: Optional[float], highest_eod_balance: float, policy: DrawdownPolicy) -> Optional[float]:
    if current_floor is None:
        return None
    if policy.drawdown_type == "STATIC":
        return current_floor
    if policy.floor_update_basis.startswith("END_OF_SESSION"):
        candidate = highest_eod_balance - policy.max_loss
        candidate = _cap_floor(candidate, policy)
        return max(current_floor, candidate)
    return current_floor


def _intraday_ratchet_floor(current_floor: Optional[float], peak_equity: float, policy: DrawdownPolicy) -> Optional[float]:
    if current_floor is None:
        return None
    if policy.drawdown_type != "INTRADAY_TRAILING":
        return current_floor
    candidate = _cap_floor(peak_equity - policy.max_loss, policy)
    return max(current_floor, candidate)


def _trade_low(balance_before: float, mae: float, commission: float) -> float:
    adverse = min(0.0, float(mae)) if math.isfinite(float(mae)) else 0.0
    return balance_before + adverse - commission


def _trade_peak(balance_before: float, mfe: float) -> float:
    favorable = max(0.0, float(mfe)) if math.isfinite(float(mfe)) else 0.0
    return balance_before + favorable


def _consistency_metrics(stage_rules: Dict[str, Any], session_pnls: Iterable[float], total_profit: float) -> Dict[str, Any]:
    pct = stage_rules.get("consistency_percent")
    profitable = [float(x) for x in session_pnls if float(x) > 0]
    largest = max(profitable) if profitable else 0.0
    if pct is None:
        return {"consistency_percent_limit": None, "largest_profitable_day": largest, "consistency_ratio": None, "consistency_pass": True, "adjusted_profit_target": stage_rules.get("profit_target")}
    pct = float(pct)
    ratio = (largest / total_profit * 100.0) if total_profit > 0 else math.inf if largest > 0 else 0.0
    adjusted = float(stage_rules.get("profit_target") or 0.0)
    # FundedNext Flex challenge defines the daily threshold relative to the target and increases
    # the required target when a day exceeds the threshold. Other current core products use
    # largest-day / accumulated-profit.
    return {"consistency_percent_limit": pct, "largest_profitable_day": largest, "consistency_ratio": ratio, "consistency_pass": ratio <= pct + 1e-12, "adjusted_profit_target": adjusted}


def _target_progress(product_id: str, stage_rules: Dict[str, Any], session_pnls: Iterable[float], total_profit: float) -> Dict[str, Any]:
    target = stage_rules.get("profit_target")
    if target is None:
        return {"base_profit_target": None, "effective_profit_target": None, "target_progress": None, "target_reached": False, **_consistency_metrics(stage_rules, session_pnls, total_profit)}
    target = float(target)
    c = _consistency_metrics(stage_rules, session_pnls, total_profit)
    effective = target
    pct = stage_rules.get("consistency_percent")
    profitable = [float(x) for x in session_pnls if float(x) > 0]
    largest = max(profitable) if profitable else 0.0
    if product_id == "fundednext_flex" and pct:
        effective = max(target, largest / (float(pct) / 100.0) if largest > 0 else target)
        c["adjusted_profit_target"] = effective
        c["consistency_pass"] = total_profit >= effective - 1e-9
    return {
        "base_profit_target": target,
        "effective_profit_target": effective,
        "target_progress": total_profit / effective if effective > 0 else None,
        "target_reached": total_profit >= effective - 1e-9,
        **c,
    }


def run_single_account_history(rulebook: Dict[str, Any], ledger: pd.DataFrame, config: RunnerConfig) -> HistoricalRunResult:
    if config.max_trades_per_session < 1:
        raise HistoricalRunnerError("max_trades_per_session must be >= 1")
    if config.commission_per_contract_round_trip < 0:
        raise HistoricalRunnerError("commission cannot be negative")
    if config.stage not in {"evaluation", "sim_funded"}:
        raise HistoricalRunnerError("v4B historical runner supports evaluation or sim_funded stages")

    firm, product, stage_rules = _find_stage(rulebook, config.product_id, config.account_size, config.stage)
    policy = resolve_drawdown_policy(rulebook, config)
    start_balance = resolve_starting_balance(config.product_id, config.account_size, config.stage, stage_rules, config.starting_balance_override)
    floor = _initial_floor(start_balance, policy)
    highest_eod = start_balance
    balance = start_balance
    status = "ACTIVE"
    failure_reason = ""
    failure_session = None
    failure_trade_key = None
    min_cushion = math.inf
    session_rows: List[Dict[str, Any]] = []
    trade_rows: List[Dict[str, Any]] = []
    total_commission = 0.0
    routed = 0
    skipped_cap = 0
    skipped_after_failure = 0
    dll_triggers = 0
    mae_missing = 0
    intraday_ambiguous = 0

    allowed = {"VALID", "REVIEW"} if config.include_review_rows else {"VALID"}
    work = ledger[ledger["validity_status"].isin(allowed)].copy()
    work["__entry"] = pd.to_datetime(work["entry_time_et"], errors="coerce", utc=True)
    work = work.sort_values(["__entry", "source_file", "source_trade_id"], na_position="last").drop(columns="__entry").reset_index(drop=True)

    if work.empty:
        raise HistoricalRunnerError("No eligible trades remain after audit/status filtering")

    # Pre-count how many signals the strategy produced each session.
    session_signal_counts = work.groupby("futures_session_id", dropna=False).size().to_dict()
    completed_session_pnls: List[float] = []
    traded_session_count = 0

    for sid, group in work.groupby("futures_session_id", sort=False, dropna=False):
        sid = str(sid)
        if status != "ACTIVE":
            for _, row in group.iterrows():
                skipped_after_failure += 1
                trade_rows.append({
                    "futures_session_id": sid, "entry_time_et": row.get("entry_time_et"), "source_file": row.get("source_file"), "source_trade_id": row.get("source_trade_id"),
                    "decision": "SKIP_ACCOUNT_INACTIVE", "skip_reason": status, "gross_pnl": row.get("normalized_gross_pnl"), "commission": 0.0,
                    "net_pnl": 0.0, "balance_before": balance, "balance_after": balance, "floor_before": floor, "floor_after": floor,
                    "mae": row.get("MAE"), "mfe": row.get("MFE"), "intratrade_low": None, "intratrade_peak": None, "breach": False,
                })
            continue

        session_start_balance = balance
        session_floor_start = floor
        session_net = 0.0
        session_gross = 0.0
        session_commission = 0.0
        session_routed = 0
        session_dll_paused = False
        session_breached = False

        rows = list(group.iterrows())
        for ordinal, (_, row) in enumerate(rows, start=1):
            if status != "ACTIVE":
                skipped_after_failure += 1
                decision = "SKIP_ACCOUNT_INACTIVE"
                skip_reason = status
            elif session_dll_paused:
                skipped_cap += 1
                decision = "SKIP_SESSION_PAUSED_DLL"
                skip_reason = "DLL_PAUSE"
            elif session_routed >= config.max_trades_per_session:
                skipped_cap += 1
                decision = "SKIP_SESSION_CAP"
                skip_reason = f"max_{config.max_trades_per_session}_trades_per_session"
            else:
                decision = "ROUTE"
                skip_reason = ""

            if decision != "ROUTE":
                trade_rows.append({
                    "futures_session_id": sid, "session_signal_ordinal": ordinal, "entry_time_et": row.get("entry_time_et"), "exit_time_et": row.get("exit_time_et"),
                    "source_file": row.get("source_file"), "source_trade_id": row.get("source_trade_id"), "decision": decision, "skip_reason": skip_reason,
                    "gross_pnl": row.get("normalized_gross_pnl"), "commission": 0.0, "net_pnl": 0.0,
                    "balance_before": balance, "balance_after": balance, "floor_before": floor, "floor_after": floor,
                    "mae": row.get("MAE"), "mfe": row.get("MFE"), "intratrade_low": None, "intratrade_peak": None, "breach": False,
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

            # Intraday trailing cannot be path-exact with only MFE/MAE because order is unknown.
            # StarBase therefore supports explicit conservative/optimistic research assumptions.
            if policy.drawdown_type == "INTRADAY_TRAILING" and floor is not None:
                intraday_ambiguous += 1
                if config.intraday_order_assumption == "MFE_BEFORE_MAE_CONSERVATIVE":
                    floor = _intraday_ratchet_floor(floor, peak, policy)
                # Under MAE-before-MFE the breach is checked against the old floor, then ratchet occurs after.

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
                failure_session = sid
                failure_trade_key = f"{row.get('source_file')}#{row.get('source_trade_id')}"
                session_breached = True
                # The exact liquidation fill is unavailable. Stop at the established floor for accounting,
                # and retain the source trade outcome in diagnostic columns rather than pretending recovery.
                balance = float(floor)
                realized_net_for_account = balance - balance_before
            elif dll_hit and dll_action in {"SOFT_PAUSE_SESSION", "LIQUIDATE_AND_PAUSE"}:
                # Exact liquidation fill is unavailable. Model the soft pause at the DLL boundary and mark research-grade.
                allowed_loss = max(0.0, float(dll_amount) + session_net)
                realized_net_for_account = max(net, -allowed_loss)
                balance += realized_net_for_account
                session_dll_paused = True
            elif dll_hit and dll_action == "HARD_FAIL":
                status = "FAILED"
                failure_reason = "DAILY_LOSS_LIMIT_HARD_FAIL"
                failure_session = sid
                failure_trade_key = f"{row.get('source_file')}#{row.get('source_trade_id')}"
                realized_net_for_account = net
                balance += realized_net_for_account
                session_breached = True
            else:
                realized_net_for_account = net
                balance += realized_net_for_account

            # If intraday trailing and MAE-first assumption, ratchet after the low/breach test.
            if policy.drawdown_type == "INTRADAY_TRAILING" and floor is not None and not breach and config.intraday_order_assumption == "MAE_BEFORE_MFE_OPTIMISTIC":
                floor = _intraday_ratchet_floor(floor, peak, policy)

            routed += 1
            session_routed += 1
            session_gross += gross
            session_commission += commission
            total_commission += commission
            session_net += realized_net_for_account
            if floor is not None:
                min_cushion = min(min_cushion, balance_before - floor_before if floor_before is not None else math.inf, low - floor_before if floor_before is not None else math.inf)

            trade_rows.append({
                "futures_session_id": sid, "session_signal_ordinal": ordinal, "entry_time_et": row.get("entry_time_et"), "exit_time_et": row.get("exit_time_et"),
                "source_file": row.get("source_file"), "source_trade_id": row.get("source_trade_id"), "decision": "ROUTE", "skip_reason": "",
                "direction": row.get("direction"), "contracts": contracts, "gross_pnl": gross, "commission": commission, "source_net_pnl": net,
                "account_realized_net_pnl": realized_net_for_account, "balance_before": balance_before, "balance_after": balance,
                "floor_before": floor_before, "floor_after": floor, "mae": mae, "mfe": mfe, "intratrade_low": low, "intratrade_peak": peak,
                "breach": breach, "dll_hit": dll_hit, "dll_action": dll_action, "account_status_after": status,
                "source_validity": row.get("validity_status"), "audit_warnings": row.get("audit_warnings"),
            })
            if status != "ACTIVE":
                # Remaining signals are recorded by normal loop as inactive.
                continue

        if session_routed > 0:
            traded_session_count += 1
        if status == "ACTIVE":
            # EOD floor ratchets using the closing balance only after all selected trades for the session.
            highest_eod = max(highest_eod, balance)
            floor = _eod_update_floor(floor, highest_eod, policy)
        completed_session_pnls.append(session_net)
        total_profit = balance - start_balance
        progress = _target_progress(config.product_id, stage_rules, completed_session_pnls, total_profit)
        session_rows.append({
            "futures_session_id": sid,
            "source_signals": int(session_signal_counts.get(sid, len(group))),
            "trades_routed": session_routed,
            "session_start_balance": session_start_balance,
            "session_gross_pnl": session_gross,
            "session_commission": session_commission,
            "session_net_pnl": session_net,
            "session_end_balance": balance,
            "floor_start": session_floor_start,
            "floor_end": floor,
            "highest_eod_balance": highest_eod,
            "session_dll_paused": session_dll_paused,
            "session_breached": session_breached,
            "account_status": status,
            **progress,
        })

    trades_df = pd.DataFrame(trade_rows)
    sessions_df = pd.DataFrame(session_rows)
    total_profit = balance - start_balance
    progress = _target_progress(config.product_id, stage_rules, completed_session_pnls, total_profit)
    coverage = assess_rule_coverage(rulebook, config.product_id, config.account_size, config.stage)
    has_dll_approx = dll_triggers > 0
    production_grade = (
        policy.confidence.startswith("VERIFIED")
        and policy.drawdown_type in {"EOD_TRAILING", "STATIC", "NONE"}
        and mae_missing == 0
        and not has_dll_approx
        and policy.floor_lock_behavior != "VARIANT_SELECTION_REQUIRED"
    )
    fidelity = "EXACT_PROFILE_RULE_PATH" if production_grade else "RESEARCH_GRADE_RULE_PATH"

    source_hashes = sorted(set(str(x) for x in work.get("source_sha256", pd.Series(dtype=str)).dropna().unique()))
    rule_snapshot = {
        "rulebook_schema_version": rulebook.get("schema_version"),
        "verified_as_of": rulebook.get("verified_as_of"),
        "firm_id": firm.get("firm_id"), "firm": firm.get("display_name"),
        "product_id": product.get("product_id"), "product": product.get("display_name"),
        "account_size": config.account_size, "stage": config.stage,
        "stage_rules": stage_rules,
        "drawdown_policy": asdict(policy),
        "sources": product.get("sources", []),
    }
    run_fingerprint = sha256_text(stable_json({"engine": RUNNER_ENGINE_VERSION, "config": asdict(config), "source_hashes": source_hashes, "rule_snapshot": rule_snapshot}))[:16]

    summary = {
        "runner_engine_version": RUNNER_ENGINE_VERSION,
        "runner_schema_version": RUNNER_SCHEMA_VERSION,
        "run_id": f"SB4B-{run_fingerprint}",
        "firm": firm.get("display_name"),
        "product": product.get("display_name"),
        "product_id": config.product_id,
        "account_size": config.account_size,
        "stage": config.stage,
        "starting_balance": start_balance,
        "ending_balance": balance,
        "net_account_change": total_profit,
        "status": status,
        "failure_reason": failure_reason,
        "failure_session": failure_session,
        "failure_trade": failure_trade_key,
        "initial_failure_floor": _initial_floor(start_balance, policy),
        "ending_failure_floor": floor,
        "highest_eod_balance": highest_eod,
        "minimum_observed_cushion": None if min_cushion is math.inf or not math.isfinite(min_cushion) else min_cushion,
        "source_eligible_trades": int(len(work)),
        "source_futures_sessions": int(work["futures_session_id"].nunique()),
        "traded_sessions": int(traded_session_count),
        "trades_routed": int(routed),
        "signals_skipped_by_session_cap_or_pause": int(skipped_cap),
        "signals_skipped_after_account_inactive": int(skipped_after_failure),
        "max_trades_per_account_per_session": config.max_trades_per_session,
        "total_firm_commissions": total_commission,
        "dll_triggers": int(dll_triggers),
        "mae_fallback_count": int(mae_missing),
        "intraday_path_ambiguous_trades": int(intraday_ambiguous),
        "execution_rule_fidelity": fidelity,
        "production_grade_rule_path": bool(production_grade),
        "rule_coverage": coverage.get("status"),
        "drawdown_policy_confidence": policy.confidence,
        "drawdown_type": policy.drawdown_type,
        "floor_lock_behavior": policy.floor_lock_behavior,
        "source_hashes": source_hashes,
        **progress,
    }
    return HistoricalRunResult(summary=summary, trades=trades_df, sessions=sessions_df, config=asdict(config), rule_snapshot=rule_snapshot)



def capacity_slots_for_capture(ledger: pd.DataFrame, targets=(0.80, 0.90, 0.95)) -> Dict[float, int]:
    """Minimum one-trade-per-session account slots needed to capture target signal fractions."""
    work = ledger[ledger["validity_status"] == "VALID"] if "validity_status" in ledger.columns else ledger
    counts = work.groupby("futures_session_id", dropna=True).size().astype(int)
    if counts.empty:
        return {float(t): 0 for t in targets}
    total = int(counts.sum())
    out = {}
    for target in targets:
        target = float(target)
        found = int(counts.max())
        for slots in range(1, int(counts.max()) + 1):
            captured = int(counts.clip(upper=slots).sum())
            if captured / total >= target - 1e-12:
                found = slots
                break
        out[target] = found
    return out

def tp_sl_diagnostic(ledger: pd.DataFrame, commission_per_contract_round_trip: float = 0.0) -> Dict[str, Any]:
    work = ledger[ledger["validity_status"] == "VALID"].copy()
    if work.empty:
        return {}
    gross = work["normalized_gross_pnl"].astype(float)
    commissions = work["contracts"].abs().astype(float) * float(commission_per_contract_round_trip)
    net = gross - commissions
    wins = net[net > 0]
    losses = net[net < 0]
    wr = float((net > 0).mean())
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(losses.mean()) if len(losses) else 0.0
    abs_loss = abs(avg_loss)
    be_wr = abs_loss / (avg_win + abs_loss) if avg_win > 0 and abs_loss > 0 else None
    return {
        "trades": int(len(work)), "win_rate": wr, "avg_win": avg_win, "avg_loss": avg_loss,
        "expectancy": float(net.mean()), "profit_factor": float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else None,
        "break_even_win_rate_at_observed_payoff": be_wr,
        "median_win": float(wins.median()) if len(wins) else 0.0,
        "median_loss": float(losses.median()) if len(losses) else 0.0,
    }


def theoretical_tp_sl(*, observed_win_rate: float, proposed_tp: float, proposed_sl: float, commission: float = 0.0) -> Dict[str, Any]:
    tp = abs(float(proposed_tp)); sl = abs(float(proposed_sl)); p = float(observed_win_rate)
    if tp <= 0 or sl <= 0:
        raise HistoricalRunnerError("TP and SL must be positive")
    be = (sl + commission) / (tp + sl) if (tp + sl) > 0 else math.nan
    exp = p * tp - (1.0 - p) * sl - commission
    return {"break_even_win_rate": be, "theoretical_expectancy_at_observed_win_rate": exp, "reward_to_risk": tp / sl}


def build_run_bundle(result: HistoricalRunResult) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("RUN_SUMMARY.json", json.dumps(result.summary, indent=2, default=str))
        z.writestr("RUN_CONFIG.json", json.dumps(result.config, indent=2, default=str))
        z.writestr("RULE_SNAPSHOT.json", json.dumps(result.rule_snapshot, indent=2, default=str))
        z.writestr("TRADE_ROUTING.csv", result.trades.to_csv(index=False))
        z.writestr("SESSION_LEDGER.csv", result.sessions.to_csv(index=False))
        report = [
            "# StarBase v4B Historical Single-Account Run",
            "",
            f"Run ID: `{result.summary.get('run_id')}`",
            f"Firm / product: {result.summary.get('firm')} / {result.summary.get('product')}",
            f"Account: ${result.summary.get('account_size',0):,.0f} {result.summary.get('stage')}",
            f"Status: **{result.summary.get('status')}**",
            f"Starting balance: ${result.summary.get('starting_balance',0):,.2f}",
            f"Ending balance: ${result.summary.get('ending_balance',0):,.2f}",
            f"Net account change: ${result.summary.get('net_account_change',0):,.2f}",
            f"Trades routed: {result.summary.get('trades_routed')}",
            f"Max trades/account/session: {result.summary.get('max_trades_per_account_per_session')}",
            f"Firm commissions: ${result.summary.get('total_firm_commissions',0):,.2f}",
            f"Rule-path fidelity: {result.summary.get('execution_rule_fidelity')}",
            "",
            "v4B deliberately does not yet auto-pass evaluations, activate funded accounts, or request payouts. Those state transitions are added cumulatively in v4D-v4F.",
        ]
        z.writestr("REPORT.md", "\n".join(report) + "\n")
    return buf.getvalue()
