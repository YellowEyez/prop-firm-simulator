"""Project StarBase v2 TradingView import and audit engine.

This module is intentionally independent of the legacy prop-firm simulator.
It converts TradingView Strategy Tester "List of Trades" CSV exports into a
canonical trade ledger and applies the project-level validity policy before any
lifecycle simulation is allowed to use the data.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, time
from io import BytesIO
from pathlib import Path
from typing import Iterable, List, Mapping, Optional, Sequence, Tuple, Union
from zoneinfo import ZoneInfo
import hashlib
import math
import re

import numpy as np
import pandas as pd

ET = ZoneInfo("America/New_York")

REQUIRED_TV_COLUMNS = {
    "Trade number",
    "Type",
    "Date and time",
    "Signal",
    "Price USD",
    "Size (qty)",
    "Net PnL USD",
    "Commission USD",
    "Favorable excursion USD",
    "Adverse excursion USD",
    "Duration (bars)",
}

CANONICAL_COLUMNS = [
    "strategy_id",
    "profile_id",
    "source_file",
    "source_trade_id",
    "entry_time_et",
    "exit_time_et",
    "futures_session_id",
    "direction",
    "entry_price",
    "exit_price",
    "contracts",
    "exported_net_pnl",
    "exported_commission",
    "normalized_gross_pnl",
    "firm_commission_pnl",
    "MFE",
    "MAE",
    "entry_signal",
    "exit_signal",
    "validity_status",
    "validity_reason",
    "review_status",
]

EXTRA_AUDIT_COLUMNS = [
    "hold_seconds",
    "hold_minutes",
    "duration_bars",
    "seconds_per_bar",
    "implied_contracts_from_pnl",
    "pnl_math_difference",
    "exact_duplicate",
    "duplicate_of",
    "source_sha256",
    "audit_warnings",
]


class TradingViewAuditError(ValueError):
    """Raised when a TradingView export cannot be safely parsed."""


@dataclass(frozen=True)
class AuditPolicy:
    """Project-level source validity policy for TradingView trade exports."""

    timezone: str = "America/New_York"
    futures_session_start_hour: int = 18
    forbidden_entry_start_hour: int = 16
    forbidden_entry_end_hour: int = 18
    review_hold_seconds: int = 60 * 60
    reject_hold_seconds: int = 2 * 60 * 60
    suspicious_abs_pnl_per_contract: float = 1000.0
    pnl_math_tolerance_dollars: float = 25.0
    point_value_per_contract: float = 20.0  # NQ default; user-configurable in UI
    reject_backtest_open_rows: bool = True
    reject_exact_file_duplicates: bool = True


@dataclass
class AuditResult:
    ledger: pd.DataFrame
    summary: Mapping[str, object]
    file_summary: pd.DataFrame


def _clean_id(value: str, fallback: str) -> str:
    value = (value or "").strip()
    if not value:
        return fallback
    return re.sub(r"\s+", "_", value)


def _parse_timestamp_et(value: object, tz: ZoneInfo = ET) -> pd.Timestamp:
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return pd.NaT
    # TradingView exports in this project are local Eastern wall-clock timestamps.
    if getattr(ts, "tzinfo", None) is None:
        return pd.Timestamp(ts).tz_localize(tz, ambiguous="NaT", nonexistent="shift_forward")
    return pd.Timestamp(ts).tz_convert(tz)


def futures_session_id(ts: pd.Timestamp, session_start_hour: int = 18) -> Optional[str]:
    """Return the futures-session start date (session begins at 18:00 ET)."""
    if pd.isna(ts):
        return None
    local = ts.tz_convert(ET) if ts.tzinfo else ts.tz_localize(ET)
    session_date = local.date() if local.time() >= time(session_start_hour, 0) else (local.date() - timedelta(days=1))
    return session_date.isoformat()


def _file_bytes_and_name(source: Union[str, Path, bytes, BytesIO, object], default_name: str) -> Tuple[bytes, str]:
    if isinstance(source, (str, Path)):
        p = Path(source)
        return p.read_bytes(), p.name
    if isinstance(source, bytes):
        return source, default_name
    if isinstance(source, BytesIO):
        return source.getvalue(), default_name
    # Streamlit UploadedFile exposes getvalue() and name.
    if hasattr(source, "getvalue"):
        return source.getvalue(), getattr(source, "name", default_name)
    if hasattr(source, "read"):
        data = source.read()
        return data, getattr(source, "name", default_name)
    raise TradingViewAuditError(f"Unsupported input type: {type(source)!r}")


def _read_tv_csv(source: Union[str, Path, bytes, BytesIO, object], default_name: str) -> Tuple[pd.DataFrame, str, str]:
    raw, name = _file_bytes_and_name(source, default_name)
    digest = hashlib.sha256(raw).hexdigest()
    try:
        df = pd.read_csv(BytesIO(raw))
    except UnicodeDecodeError:
        df = pd.read_csv(BytesIO(raw), encoding="utf-8-sig")
    missing = sorted(REQUIRED_TV_COLUMNS.difference(df.columns))
    if missing:
        raise TradingViewAuditError(
            f"{name}: not a recognized TradingView List of Trades export. Missing columns: {', '.join(missing)}"
        )
    return df, name, digest


def _direction_from_entry_type(value: str) -> Optional[str]:
    v = str(value).strip().lower()
    if "entry long" in v:
        return "long"
    if "entry short" in v:
        return "short"
    return None


def _safe_float(value: object, default: float = math.nan) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _trade_row_from_pair(
    entry: pd.Series,
    exit_row: pd.Series,
    *,
    strategy_id: str,
    profile_id: str,
    source_file: str,
    source_sha256: str,
    source_trade_id: object,
    policy: AuditPolicy,
) -> dict:
    tz = ZoneInfo(policy.timezone)
    entry_ts = _parse_timestamp_et(entry.get("Date and time"), tz)
    exit_ts = _parse_timestamp_et(exit_row.get("Date and time"), tz)
    direction = _direction_from_entry_type(entry.get("Type", ""))

    entry_price = _safe_float(entry.get("Price USD"))
    exit_price = _safe_float(exit_row.get("Price USD"))
    contracts = _safe_float(entry.get("Size (qty)"), 0.0)

    # TradingView repeats trade-level outcome fields on entry and exit rows. Prefer exit.
    exported_net = _safe_float(exit_row.get("Net PnL USD"), _safe_float(entry.get("Net PnL USD"), 0.0))
    exported_commission = _safe_float(exit_row.get("Commission USD"), _safe_float(entry.get("Commission USD"), 0.0))
    normalized_gross = exported_net + exported_commission
    mfe = _safe_float(exit_row.get("Favorable excursion USD"), _safe_float(entry.get("Favorable excursion USD")))
    mae = _safe_float(exit_row.get("Adverse excursion USD"), _safe_float(entry.get("Adverse excursion USD")))
    duration_bars = _safe_float(exit_row.get("Duration (bars)"), _safe_float(entry.get("Duration (bars)")))

    hold_seconds = math.nan
    seconds_per_bar = math.nan
    if not pd.isna(entry_ts) and not pd.isna(exit_ts):
        hold_seconds = (exit_ts - entry_ts).total_seconds()
        if duration_bars and duration_bars > 0:
            seconds_per_bar = hold_seconds / duration_bars

    sign = 1.0 if direction == "long" else -1.0 if direction == "short" else math.nan
    theoretical = math.nan
    implied_contracts = math.nan
    pnl_math_difference = math.nan
    if direction and contracts > 0 and np.isfinite(entry_price) and np.isfinite(exit_price):
        price_points = (exit_price - entry_price) * sign
        theoretical = price_points * policy.point_value_per_contract * contracts
        pnl_math_difference = normalized_gross - theoretical
        denom = price_points * policy.point_value_per_contract
        if abs(denom) > 1e-12:
            implied_contracts = normalized_gross / denom

    entry_session = futures_session_id(entry_ts, policy.futures_session_start_hour) if not pd.isna(entry_ts) else None
    exit_session = futures_session_id(exit_ts, policy.futures_session_start_hour) if not pd.isna(exit_ts) else None

    invalid_reasons: List[str] = []
    review_reasons: List[str] = []
    warning_reasons: List[str] = []

    if pd.isna(entry_ts) or pd.isna(exit_ts):
        invalid_reasons.append("missing_or_invalid_timestamp")
    elif exit_ts < entry_ts:
        invalid_reasons.append("exit_before_entry")

    if direction is None:
        invalid_reasons.append("unknown_direction")
    if not np.isfinite(entry_price) or not np.isfinite(exit_price):
        invalid_reasons.append("missing_price")
    if not np.isfinite(contracts) or contracts <= 0:
        invalid_reasons.append("invalid_contract_quantity")

    if not pd.isna(entry_ts):
        tm = entry_ts.timetz().replace(tzinfo=None)
        if time(policy.forbidden_entry_start_hour, 0) <= tm < time(policy.forbidden_entry_end_hour, 0):
            invalid_reasons.append("entry_in_16_18_et_forbidden_window")

    if entry_session is not None and exit_session is not None and entry_session != exit_session:
        invalid_reasons.append("crossed_next_18_et_futures_session")

    if np.isfinite(hold_seconds):
        if hold_seconds > policy.reject_hold_seconds:
            invalid_reasons.append("hold_over_2_hours")
        elif hold_seconds > policy.review_hold_seconds:
            review_reasons.append("hold_1_to_2_hours")

    exit_signal = str(exit_row.get("Signal", "") or "")
    if policy.reject_backtest_open_rows and exit_signal.strip().lower() == "open":
        invalid_reasons.append("backtest_end_open_pseudo_trade")

    if contracts > 0 and abs(normalized_gross) / contracts > policy.suspicious_abs_pnl_per_contract:
        review_reasons.append("suspicious_abs_pnl_over_1000_per_contract")

    if np.isfinite(pnl_math_difference) and abs(pnl_math_difference) > policy.pnl_math_tolerance_dollars:
        # This is a review flag rather than automatic rejection because TradingView can report
        # nontrivial position bookkeeping on some multi-contract/partial-exit runs.
        warning_reasons.append("pnl_price_math_mismatch")

    validity_status = "INVALID" if invalid_reasons else ("REVIEW" if review_reasons else "VALID")
    review_status = ";".join(review_reasons) if review_reasons else "CLEAR"

    return {
        "strategy_id": strategy_id,
        "profile_id": profile_id,
        "source_file": source_file,
        "source_trade_id": source_trade_id,
        "entry_time_et": entry_ts.isoformat() if not pd.isna(entry_ts) else None,
        "exit_time_et": exit_ts.isoformat() if not pd.isna(exit_ts) else None,
        "futures_session_id": entry_session,
        "direction": direction,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "contracts": contracts,
        "exported_net_pnl": exported_net,
        "exported_commission": exported_commission,
        "normalized_gross_pnl": normalized_gross,
        "firm_commission_pnl": 0.0,
        "MFE": mfe,
        "MAE": mae,
        "entry_signal": str(entry.get("Signal", "") or ""),
        "exit_signal": exit_signal,
        "validity_status": validity_status,
        "validity_reason": ";".join(invalid_reasons) if invalid_reasons else "",
        "review_status": review_status,
        "hold_seconds": hold_seconds,
        "hold_minutes": hold_seconds / 60.0 if np.isfinite(hold_seconds) else math.nan,
        "duration_bars": duration_bars,
        "seconds_per_bar": seconds_per_bar,
        "implied_contracts_from_pnl": implied_contracts,
        "pnl_math_difference": pnl_math_difference,
        "exact_duplicate": False,
        "duplicate_of": "",
        "source_sha256": source_sha256,
        "audit_warnings": ";".join(warning_reasons) if warning_reasons else "",
    }


def parse_tradingview_file(
    source: Union[str, Path, bytes, BytesIO, object],
    *,
    strategy_id: str,
    profile_id: str,
    policy: Optional[AuditPolicy] = None,
    default_name: str = "uploaded.csv",
) -> Tuple[pd.DataFrame, dict]:
    """Parse one TradingView Strategy Tester List of Trades CSV efficiently."""
    policy = policy or AuditPolicy()
    df, source_name, digest = _read_tv_csv(source, default_name)
    strategy_id = _clean_id(strategy_id, "strategy")
    profile_id = _clean_id(profile_id, "profile")

    work = df.copy()
    work["__type_lower"] = work["Type"].astype(str).str.strip().str.lower()
    entries = work[work["__type_lower"].str.startswith("entry")].copy()
    exits = work[work["__type_lower"].str.startswith("exit")].copy()

    entry_counts = entries.groupby("Trade number", dropna=False).size()
    exit_counts = exits.groupby("Trade number", dropna=False).size()
    all_ids = list(dict.fromkeys(work["Trade number"].tolist()))
    valid_ids = [
        tid for tid in all_ids
        if int(entry_counts.get(tid, 0)) == 1 and int(exit_counts.get(tid, 0)) == 1
    ]
    valid_id_set = set(valid_ids)
    malformed_ids = [tid for tid in all_ids if tid not in valid_id_set]

    # Index once. This is dramatically faster than filtering the full DataFrame per trade.
    entry_idx = entries.set_index("Trade number", drop=False)
    exit_idx = exits.set_index("Trade number", drop=False)
    work_idx = work.set_index("Trade number", drop=False)

    rows: List[dict] = []
    for trade_id in valid_ids:
        entry = entry_idx.loc[trade_id]
        exit_row = exit_idx.loc[trade_id]
        # With valid counts these are Series, but protect against unexpected duplicate indexes.
        if isinstance(entry, pd.DataFrame):
            entry = entry.iloc[0]
        if isinstance(exit_row, pd.DataFrame):
            exit_row = exit_row.iloc[0]
        rows.append(_trade_row_from_pair(
            entry, exit_row, strategy_id=strategy_id, profile_id=profile_id,
            source_file=source_name, source_sha256=digest, source_trade_id=trade_id, policy=policy
        ))

    for trade_id in malformed_ids:
        base = work_idx.loc[trade_id]
        if isinstance(base, pd.DataFrame):
            base = base.iloc[0]
        ec = int(entry_counts.get(trade_id, 0)); xc = int(exit_counts.get(trade_id, 0))
        rows.append({
            "strategy_id": strategy_id,
            "profile_id": profile_id,
            "source_file": source_name,
            "source_trade_id": trade_id,
            "entry_time_et": None,
            "exit_time_et": None,
            "futures_session_id": None,
            "direction": None,
            "entry_price": math.nan,
            "exit_price": math.nan,
            "contracts": _safe_float(base.get("Size (qty)"), 0.0),
            "exported_net_pnl": _safe_float(base.get("Net PnL USD"), 0.0),
            "exported_commission": _safe_float(base.get("Commission USD"), 0.0),
            "normalized_gross_pnl": _safe_float(base.get("Net PnL USD"), 0.0) + _safe_float(base.get("Commission USD"), 0.0),
            "firm_commission_pnl": 0.0,
            "MFE": _safe_float(base.get("Favorable excursion USD")),
            "MAE": _safe_float(base.get("Adverse excursion USD")),
            "entry_signal": "",
            "exit_signal": "",
            "validity_status": "INVALID",
            "validity_reason": f"malformed_trade_pair_entry_{ec}_exit_{xc}",
            "review_status": "CLEAR",
            "hold_seconds": math.nan,
            "hold_minutes": math.nan,
            "duration_bars": _safe_float(base.get("Duration (bars)")),
            "seconds_per_bar": math.nan,
            "implied_contracts_from_pnl": math.nan,
            "pnl_math_difference": math.nan,
            "exact_duplicate": False,
            "duplicate_of": "",
            "source_sha256": digest,
            "audit_warnings": "",
        })

    ledger = pd.DataFrame(rows, columns=CANONICAL_COLUMNS + EXTRA_AUDIT_COLUMNS)
    file_summary = {
        "source_file": source_name,
        "source_sha256": digest,
        "raw_rows": int(len(df)),
        "trade_numbers": int(df["Trade number"].nunique(dropna=False)),
        "ledger_rows": int(len(ledger)),
        "malformed_pairs": int(len(malformed_ids)),
    }
    return ledger, file_summary


def _duplicate_signature(row: pd.Series) -> Tuple:
    def r(v):
        return None if pd.isna(v) else round(float(v), 6)
    return (
        row.get("entry_time_et"), row.get("exit_time_et"), row.get("direction"),
        r(row.get("entry_price")), r(row.get("exit_price")), r(row.get("contracts")),
        r(row.get("normalized_gross_pnl")), row.get("entry_signal"), row.get("exit_signal"),
    )


def mark_exact_duplicates(ledger: pd.DataFrame, policy: Optional[AuditPolicy] = None) -> pd.DataFrame:
    """Mark exact duplicate trade records across files without collapsing same-source rapid reentries."""
    policy = policy or AuditPolicy()
    if ledger.empty:
        return ledger.copy()
    out = ledger.copy()
    seen = {}
    for idx, row in out.iterrows():
        sig = _duplicate_signature(row)
        if sig in seen:
            original_idx = seen[sig]
            out.at[idx, "exact_duplicate"] = True
            original = out.loc[original_idx]
            out.at[idx, "duplicate_of"] = f"{original['source_file']}#{original['source_trade_id']}"
            if policy.reject_exact_file_duplicates:
                existing = str(out.at[idx, "validity_reason"] or "")
                reasons = [r for r in existing.split(";") if r]
                if "exact_overlap_duplicate" not in reasons:
                    reasons.append("exact_overlap_duplicate")
                out.at[idx, "validity_reason"] = ";".join(reasons)
                out.at[idx, "validity_status"] = "INVALID"
        else:
            seen[sig] = idx
    return out


def _sort_ledger(ledger: pd.DataFrame) -> pd.DataFrame:
    out = ledger.copy()
    sort_ts = pd.to_datetime(out["entry_time_et"], errors="coerce", utc=True)
    out["__sort_ts"] = sort_ts
    out = out.sort_values(["__sort_ts", "source_file", "source_trade_id"], na_position="last").drop(columns="__sort_ts")
    return out.reset_index(drop=True)


def audit_tradingview_files(
    sources: Sequence[Union[str, Path, bytes, BytesIO, object]],
    *,
    strategy_id: str,
    profile_id: str,
    policy: Optional[AuditPolicy] = None,
) -> AuditResult:
    """Parse and audit multiple TradingView CSV segments into one canonical ledger."""
    policy = policy or AuditPolicy()
    ledgers = []
    summaries = []
    errors = []
    for i, source in enumerate(sources, start=1):
        try:
            ledger, summary = parse_tradingview_file(
                source, strategy_id=strategy_id, profile_id=profile_id, policy=policy,
                default_name=f"uploaded_{i:02d}.csv"
            )
            ledgers.append(ledger)
            summaries.append(summary)
        except Exception as exc:  # retain per-file error rather than losing entire batch
            name = getattr(source, "name", str(source))
            errors.append({"source_file": name, "error": str(exc)})

    if not ledgers:
        detail = "; ".join(f"{e['source_file']}: {e['error']}" for e in errors)
        raise TradingViewAuditError(f"No TradingView files could be parsed. {detail}")

    combined = pd.concat(ledgers, ignore_index=True)
    combined = mark_exact_duplicates(combined, policy)
    combined = _sort_ledger(combined)

    valid = combined[combined["validity_status"] == "VALID"]
    review = combined[combined["validity_status"] == "REVIEW"]
    invalid = combined[combined["validity_status"] == "INVALID"]
    warning_mask = combined["audit_warnings"].fillna("").astype(str).str.len() > 0
    warning_trades = combined[warning_mask]
    usable_with_review = combined[combined["validity_status"].isin(["VALID", "REVIEW"])]

    reason_counts = {}
    for col in ["validity_reason", "review_status", "audit_warnings"]:
        for cell in combined[col].fillna("").astype(str):
            for reason in [r for r in cell.split(";") if r and r != "CLEAR"]:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1

    entry_ts = pd.to_datetime(usable_with_review["entry_time_et"], errors="coerce", utc=True).dt.tz_convert(policy.timezone)
    exit_ts = pd.to_datetime(usable_with_review["exit_time_et"], errors="coerce", utc=True).dt.tz_convert(policy.timezone)
    sessions = usable_with_review["futures_session_id"].dropna().nunique()

    strict_gross = float(valid["normalized_gross_pnl"].sum()) if len(valid) else 0.0
    strict_win_rate = float((valid["normalized_gross_pnl"] > 0).mean()) if len(valid) else math.nan
    strict_avg = float(valid["normalized_gross_pnl"].mean()) if len(valid) else math.nan

    summary = {
        "strategy_id": _clean_id(strategy_id, "strategy"),
        "profile_id": _clean_id(profile_id, "profile"),
        "files_received": len(sources),
        "files_parsed": len(ledgers),
        "files_failed": len(errors),
        "parsed_trade_records": int(len(combined)),
        "strict_valid_trades": int(len(valid)),
        "review_trades": int(len(review)),
        "invalid_trades": int(len(invalid)),
        "warning_trades": int(len(warning_trades)),
        "usable_including_review": int(len(usable_with_review)),
        "active_futures_sessions": int(sessions),
        "first_entry_et": entry_ts.min().isoformat() if entry_ts.notna().any() else None,
        "last_exit_et": exit_ts.max().isoformat() if exit_ts.notna().any() else None,
        "strict_normalized_gross_pnl": strict_gross,
        "strict_win_rate": strict_win_rate,
        "strict_expectancy_per_trade": strict_avg,
        "embedded_export_commission_total": float(usable_with_review["exported_commission"].sum()),
        "exact_duplicate_count": int(combined["exact_duplicate"].sum()),
        "reason_counts": reason_counts,
        "file_errors": errors,
        "policy": asdict(policy),
    }
    return AuditResult(combined, summary, pd.DataFrame(summaries))


def audit_summary_table(result: AuditResult) -> pd.DataFrame:
    s = result.summary
    rows = [
        ("Files parsed", s["files_parsed"]),
        ("Parsed trade records", s["parsed_trade_records"]),
        ("Strict valid trades", s["strict_valid_trades"]),
        ("Review / quarantine trades", s["review_trades"]),
        ("Invalid trades", s["invalid_trades"]),
        ("Audit-warning trades", s["warning_trades"]),
        ("Exact overlap duplicates", s["exact_duplicate_count"]),
        ("Active futures sessions", s["active_futures_sessions"]),
        ("Embedded export commissions", s["embedded_export_commission_total"]),
        ("Strict normalized gross P&L", s["strict_normalized_gross_pnl"]),
        ("Strict win rate", s["strict_win_rate"]),
        ("Strict expectancy / trade", s["strict_expectancy_per_trade"]),
        ("First entry ET", s["first_entry_et"]),
        ("Last exit ET", s["last_exit_et"]),
    ]
    return pd.DataFrame(rows, columns=["Metric", "Value"])


def strict_valid_ledger(result: AuditResult) -> pd.DataFrame:
    """Rows permitted to feed later StarBase lifecycle engines without manual review."""
    return result.ledger[result.ledger["validity_status"] == "VALID"].copy().reset_index(drop=True)


def reviewed_usable_ledger(result: AuditResult) -> pd.DataFrame:
    """Rows that are valid or review-state; caller must explicitly accept review rows."""
    return result.ledger[result.ledger["validity_status"].isin(["VALID", "REVIEW"])].copy().reset_index(drop=True)
