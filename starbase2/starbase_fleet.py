"""Project StarBase v5A single-product funded fleet engine.

Purpose
-------
Turn an audited TradingView strategy/profile into a persistent fleet of independently
stateful simulated-funded prop accounts while preserving StarBase's 6 PM ET futures
sessions and one-trade-per-account/session routing semantics.

v5A deliberately limits itself to ONE product/account-size and FUNDED-ONLY research.
It adds two fleet modes:
  * FIXED_FLEET: use exactly N persistent funded accounts, no automatic replacements.
  * FORCE_100_CAPTURE: provision fresh funded accounts on demand so every eligible
    strategy signal receives an account slot (account-count rules intentionally ignored).

Acquisition costs are NOT yet included. That is Step 24/25 work. Therefore the fleet
reports payout cash and account inventory separately and never calls payout cash minus
zero acquisition costs a final business profit.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from io import BytesIO
import json
import math
from typing import Any, Dict, List, Optional
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
from starbase_lifecycle import (
    LifecycleConfig,
    _eligible_work,
    _resolve_start_balance,
    _payout_quote,
    _payout_share,
    _funded_floor_after_payout,
    _PAYOUT_ENGINE_SUPPORT,
)

FLEET_ENGINE_VERSION = "5.0A"
FLEET_SCHEMA_VERSION = "5A.0.0"


@dataclass(frozen=True)
class FleetConfig:
    product_id: str
    account_size: int
    capacity_mode: str = "FIXED_FLEET"  # FIXED_FLEET | FORCE_100_CAPTURE
    fixed_accounts: int = 10
    max_trades_per_account_per_session: int = 1
    commission_per_contract_round_trip: float = 0.0
    include_review_rows: bool = False
    intraday_order_assumption: str = "MFE_BEFORE_MAE_CONSERVATIVE"
    payout_request_mode: str = "MAX_ALLOWED"
    reward_share_override_percent: Optional[float] = None
    household_name: str = "Josh"


@dataclass
class FleetRun:
    summary: Dict[str, Any]
    household_sessions: pd.DataFrame
    accounts: pd.DataFrame
    trades: pd.DataFrame
    payouts: pd.DataFrame
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


def _new_account(rulebook: Dict[str, Any], cfg: FleetConfig, ordinal: int, provision_session: Optional[str]) -> _AccountState:
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
    )


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
    if cfg.capacity_mode not in {"FIXED_FLEET", "FORCE_100_CAPTURE"}:
        raise HistoricalRunnerError("v5A supports FIXED_FLEET or FORCE_100_CAPTURE")
    if cfg.fixed_accounts < 1:
        raise HistoricalRunnerError("fixed_accounts must be >= 1")
    if cfg.max_trades_per_account_per_session < 1:
        raise HistoricalRunnerError("max trades/account/session must be >= 1")

    firm, product, stage_rules = _find_stage(rulebook, cfg.product_id, cfg.account_size, "sim_funded")
    if not _PAYOUT_ENGINE_SUPPORT.get(cfg.product_id):
        raise HistoricalRunnerError("v5A fleet mode requires a modeled funded payout engine")

    work = _eligible_work(ledger, cfg.include_review_rows)
    baseline = raw_strategy_baseline(
        ledger,
        include_review_rows=cfg.include_review_rows,
        commission_per_contract_round_trip=cfg.commission_per_contract_round_trip,
    )

    accounts: List[_AccountState] = []
    next_account = 1
    if cfg.capacity_mode == "FIXED_FLEET":
        for _ in range(cfg.fixed_accounts):
            accounts.append(_new_account(rulebook, cfg, next_account, None))
            next_account += 1

    trade_rows: List[Dict[str, Any]] = []
    payout_rows: List[Dict[str, Any]] = []
    household_rows: List[Dict[str, Any]] = []
    total_shortfall = 0
    total_routed = 0
    total_provisioned = len(accounts)

    for sid_raw, group in work.groupby("futures_session_id", sort=False, dropna=False):
        sid = str(sid_raw)
        group = group.copy()
        group["__entry"] = pd.to_datetime(group["entry_time_et"], errors="coerce", utc=True)
        group = group.sort_values(["__entry", "source_file", "source_trade_id"], na_position="last").drop(columns="__entry")

        session_trade_count: Dict[str, int] = {}
        session_account_net: Dict[str, float] = {}
        session_account_source_net: Dict[str, float] = {}
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

        for signal_ordinal, (_, row) in enumerate(group.iterrows(), start=1):
            active_with_slot = [
                a for a in accounts
                if a.status == "ACTIVE" and session_trade_count.get(a.account_id, 0) < cfg.max_trades_per_account_per_session
            ]
            if not active_with_slot and cfg.capacity_mode == "FORCE_100_CAPTURE":
                a = _new_account(rulebook, cfg, next_account, sid)
                next_account += 1
                accounts.append(a)
                total_provisioned += 1
                session_new_accounts += 1
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
            session_account_source_net[account.account_id] = session_account_source_net.get(account.account_id, 0.0) + float(tr["source_trade_net_pnl"])
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

        active_end = sum(1 for a in accounts if a.status == "ACTIVE")
        failed_cum = sum(1 for a in accounts if a.status == "FAILED")
        completed_cum = sum(1 for a in accounts if a.status == "PAYOUT_CYCLE_COMPLETE")
        wallet_cum = sum(a.wallet_cash for a in accounts)
        account_profit_inventory = sum(a.balance - a.start_balance for a in accounts if a.status == "ACTIVE")
        # Aggregate displayed prop balances are NOT household cash. They are shown only as inventory diagnostics.
        aggregate_prop_balance = sum(a.balance for a in accounts if a.status == "ACTIVE")

        household_rows.append({
            "household": cfg.household_name,
            "futures_session_id": sid,
            "source_signals": int(len(group)),
            "signals_routed": routed,
            "signals_unrouted_capacity": shortfall,
            "signal_capture_percent": (routed / len(group) * 100.0) if len(group) else 0.0,
            "accounts_traded": len(session_accounts_traded),
            "winning_trades": winners,
            "losing_trades": losers,
            "flat_trades": flats,
            "source_strategy_gross_pnl": source_gross,
            "firm_commissions": source_commission,
            "source_strategy_net_after_commission": source_net,
            "account_realized_trading_pnl_until_breach": account_realized,
            "payout_deductions_from_prop_accounts": session_payout_gross,
            "payout_cash_to_household": session_payout_cash,
            "account_acquisition_costs": 0.0,
            "household_realized_cash_change_before_account_costs": session_payout_cash,
            "new_accounts_provisioned": session_new_accounts,
            "accounts_failed": len(session_failures),
            "accounts_completed_payout_cycle": len(session_cycle_completes),
            "active_accounts_end": active_end,
            "failed_accounts_cumulative": failed_cum,
            "completed_accounts_cumulative": completed_cum,
            "household_wallet_cash_cumulative": wallet_cum,
            "active_account_profit_inventory_not_cash": account_profit_inventory,
            "aggregate_active_prop_balances_not_cash": aggregate_prop_balance,
        })

    account_rows = []
    for a in accounts:
        # End-of-data payout availability if the account is still active.
        payout_available = 0.0
        payout_eligible = False
        payout_reason = "INACTIVE"
        if a.status == "ACTIVE" and a.payout_rules:
            q = _payout_quote(
                cfg.product_id,
                cfg.account_size,
                a.payout_rules,
                start_balance=a.start_balance,
                balance=a.balance,
                cycle_start_balance=a.cycle_start_balance,
                cycle_session_pnls=a.cycle_session_pnls,
                qualifying_days=a.qualifying_days,
                payout_count=a.payout_count,
                request_mode="MAX_ALLOWED",
            )
            payout_available = float(q.get("available_now") or 0.0)
            payout_eligible = bool(q.get("eligible"))
            payout_reason = str(q.get("reason"))
        account_rows.append({
            "account_id": a.account_id,
            "status": a.status,
            "failure_reason": a.failure_reason,
            "failure_session": a.failure_session,
            "provision_session": a.provision_session,
            "starting_balance": a.start_balance,
            "ending_balance": a.balance,
            "ending_failure_floor": a.floor,
            "account_profit_inventory_not_cash": a.balance - a.start_balance,
            "trades_routed": a.trades_routed,
            "sessions_traded": a.sessions_traded,
            "wins": a.winning_trades,
            "losses": a.losing_trades,
            "firm_commissions": a.total_commission,
            "source_trade_net_pnl": a.total_source_net_pnl,
            "account_realized_pnl_until_breach": a.total_account_realized_pnl,
            "payout_count": a.payout_count,
            "gross_payout_deductions": a.gross_payouts,
            "trader_wallet_cash": a.wallet_cash,
            "qualifying_days_current_cycle": a.qualifying_days,
            "payout_available_now_gross": payout_available,
            "payout_eligible_now": payout_eligible,
            "payout_eligibility_reason": payout_reason,
        })

    accounts_df = pd.DataFrame(account_rows)
    household_df = pd.DataFrame(household_rows)
    trades_df = pd.DataFrame(trade_rows)
    payouts_df = pd.DataFrame(payout_rows)

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
    unpaid_available = float(accounts_df.loc[accounts_df["payout_eligible_now"], "payout_available_now_gross"].sum()) if not accounts_df.empty else 0.0
    active_profit_inventory = float(accounts_df.loc[accounts_df["status"] == "ACTIVE", "account_profit_inventory_not_cash"].sum()) if not accounts_df.empty else 0.0
    summary = {
        "engine_version": FLEET_ENGINE_VERSION,
        "schema_version": FLEET_SCHEMA_VERSION,
        "run_id": f"SB5A-{fingerprint}",
        "household": cfg.household_name,
        "firm": firm.get("display_name"),
        "product": product.get("display_name"),
        "product_id": cfg.product_id,
        "account_size": cfg.account_size,
        "stage": "FUNDED_ONLY_FLEET",
        "capacity_mode": cfg.capacity_mode,
        "fixed_accounts_requested": cfg.fixed_accounts if cfg.capacity_mode == "FIXED_FLEET" else None,
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
        "unpaid_payout_available_at_end_gross": unpaid_available,
        "active_account_profit_inventory_not_cash": active_profit_inventory,
        "total_firm_commissions": float(accounts_df["firm_commissions"].sum()) if not accounts_df.empty else 0.0,
        "account_acquisition_costs": None,
        "realized_household_net_after_all_costs": None,
        "economics_status": "PAYOUT_AND_TRADING_FEES_ONLY_ACCOUNT_ACQUISITION_COSTS_NOT_YET_MODELED",
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
        lines = [
            "# Project StarBase v5A — Josh Single-Product Funded Fleet", "",
            f"Run ID: **{run.summary.get('run_id')}**",
            f"Product: **{run.summary.get('firm')} / {run.summary.get('product')} / ${run.summary.get('account_size'):,}**",
            f"Capacity mode: **{run.summary.get('capacity_mode')}**",
            f"Signals routed: **{run.summary.get('signals_routed'):,} / {run.summary.get('source_eligible_trades'):,}**",
            f"Signal capture: **{run.summary.get('signal_capture_percent',0):.2f}%**",
            f"Accounts provisioned: **{run.summary.get('accounts_provisioned'):,}**",
            f"Payout cash received: **${run.summary.get('payout_cash_received',0):,.2f}**", "",
            "IMPORTANT: v5A does not yet include evaluation/direct-funded acquisition costs, resets, activation fees, subscriptions or refunds.",
            "Therefore payout cash is NOT final business profit. Step 24/25 will add exact acquisition/fee economics.",
            "End-of-data active accounts and unpaid payout eligibility are preserved rather than treated as failures.",
        ]
        z.writestr("REPORT.md", "\n".join(lines) + "\n")
    return buf.getvalue()
