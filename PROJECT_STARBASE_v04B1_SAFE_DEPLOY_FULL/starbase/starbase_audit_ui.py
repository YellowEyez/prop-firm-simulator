"""Streamlit UI for Project StarBase v2 TradingView Import + Audit."""
from __future__ import annotations

import json
import pandas as pd
import streamlit as st

from tradingview_audit import (
    AuditPolicy,
    TradingViewAuditError,
    audit_summary_table,
    audit_tradingview_files,
    strict_valid_ledger,
)


def _csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def render_tradingview_audit_page() -> None:
    st.header("🛰️ StarBase v2 — TradingView Import + Audit")
    st.caption(
        "Canonical trade ingestion and source-integrity gate. No prop-firm lifecycle math is run in this mode yet."
    )

    st.info(
        "**v2 safety boundary:** This page audits TradingView Strategy Tester List of Trades exports. "
        "The legacy simulator remains available separately, but its funded/rule logic is not yet production-trusted."
    )

    with st.expander("What v2 validates", expanded=False):
        st.markdown(
            """
            - Futures sessions are anchored at **6:00 PM Eastern**.
            - Entries from **4:00 PM through 5:59:59 PM ET** are invalid.
            - A trade that survives into the **next 6:00 PM futures session** is invalid.
            - Holds **over 2 hours** are invalid; **1–2 hours** are quarantined for review.
            - Backtest-end `Open` pseudo-trades are rejected.
            - Exact overlap duplicates across uploaded CSV segments are rejected.
            - Same-source rapid reentries remain separate trades.
            - TradingView's exported commission is preserved and reversed into `normalized_gross_pnl`; firm commissions remain zero until the rule engine applies them later.
            - Suspicious P&L and price/P&L reconciliation issues are flagged for review rather than silently deleted.
            """
        )

    meta1, meta2, meta3 = st.columns([1.2, 1.2, 1])
    with meta1:
        strategy_id = st.text_input("Strategy ID", value="Strategy_01", help="Example: Sydney_01, Julie_01, Dahlia_01")
    with meta2:
        profile_id = st.text_input("Execution Profile ID", value="1NQ", help="Example: 1NQ, 2NQ, Quality_1NQ")
    with meta3:
        point_value = st.number_input(
            "Point value / contract ($)", min_value=0.01, value=20.0, step=0.25,
            help="NQ = $20/point. Used only for price/P&L audit diagnostics in v2."
        )

    uploaded_files = st.file_uploader(
        "Upload one or more TradingView List of Trades CSV segments",
        type=["csv"], accept_multiple_files=True,
        help="Upload consecutive segments of the same strategy/profile together."
    )

    if not uploaded_files:
        st.markdown("#### Recommended next step")
        st.write("Upload a known batch such as Sydney_01 or Julie_01 to validate the importer in your deployed StarBase app.")
        return

    policy = AuditPolicy(point_value_per_contract=float(point_value))
    try:
        result = audit_tradingview_files(
            uploaded_files, strategy_id=strategy_id, profile_id=profile_id, policy=policy
        )
    except TradingViewAuditError as exc:
        st.error(str(exc))
        return

    s = result.summary
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Strict valid", f"{s['strict_valid_trades']:,}")
    k2.metric("Review", f"{s['review_trades']:,}")
    k3.metric("Invalid", f"{s['invalid_trades']:,}")
    k4.metric("Warnings", f"{s['warning_trades']:,}")
    k5.metric("Futures sessions", f"{s['active_futures_sessions']:,}")
    k6.metric("Duplicate overlap", f"{s['exact_duplicate_count']:,}")

    p1, p2, p3 = st.columns(3)
    p1.metric("Strict normalized gross P&L", f"${s['strict_normalized_gross_pnl']:,.2f}")
    wr = s['strict_win_rate']
    p2.metric("Strict win rate", "N/A" if pd.isna(wr) else f"{wr:.2%}")
    exp = s['strict_expectancy_per_trade']
    p3.metric("Strict expectancy / trade", "N/A" if pd.isna(exp) else f"${exp:,.2f}")

    if s["review_trades"]:
        st.warning(
            f"{s['review_trades']:,} trades are quarantined for review and are **not** included in the strict-valid download."
        )
    if s["invalid_trades"]:
        st.error(
            f"{s['invalid_trades']:,} trades are invalid under the current project policy and cannot feed production lifecycle simulation."
        )
    if s.get("file_errors"):
        st.warning("Some files could not be parsed. See the File Audit tab.")

    tabs = st.tabs(["Audit Summary", "Flags / Warnings", "Canonical Ledger", "File Audit", "Policy"])
    with tabs[0]:
        st.dataframe(audit_summary_table(result), use_container_width=True, hide_index=True)
        reasons = pd.DataFrame(
            sorted(s["reason_counts"].items(), key=lambda x: (-x[1], x[0])), columns=["Reason", "Count"]
        )
        if not reasons.empty:
            st.markdown("##### Flag counts")
            st.dataframe(reasons, use_container_width=True, hide_index=True)

    with tabs[1]:
        flagged = result.ledger[(result.ledger["validity_status"].isin(["INVALID", "REVIEW"])) | (result.ledger["audit_warnings"].fillna("") != "")].copy()
        if flagged.empty:
            st.success("No invalid or review-state trades found.")
        else:
            display_cols = [
                "validity_status", "validity_reason", "review_status", "audit_warnings", "source_file", "source_trade_id",
                "entry_time_et", "exit_time_et", "direction", "contracts", "normalized_gross_pnl",
                "hold_minutes", "entry_signal", "exit_signal", "duplicate_of"
            ]
            st.dataframe(flagged[display_cols], use_container_width=True, hide_index=True)
            st.download_button(
                "Download flagged audit rows",
                data=_csv_bytes(flagged),
                file_name=f"{strategy_id}_{profile_id}_flagged_audit.csv",
                mime="text/csv",
            )

    with tabs[2]:
        st.caption("This is the canonical ledger that later StarBase lifecycle engines will consume.")
        st.dataframe(result.ledger.head(1000), use_container_width=True, hide_index=True)
        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                "Download full canonical ledger",
                data=_csv_bytes(result.ledger),
                file_name=f"{strategy_id}_{profile_id}_canonical_ledger.csv",
                mime="text/csv",
            )
        with c2:
            strict = strict_valid_ledger(result)
            st.download_button(
                "Download strict-valid ledger only",
                data=_csv_bytes(strict),
                file_name=f"{strategy_id}_{profile_id}_strict_valid.csv",
                mime="text/csv",
            )

    with tabs[3]:
        if not result.file_summary.empty:
            st.dataframe(result.file_summary, use_container_width=True, hide_index=True)
        if s.get("file_errors"):
            st.markdown("##### File errors")
            st.dataframe(pd.DataFrame(s["file_errors"]), use_container_width=True, hide_index=True)

    with tabs[4]:
        st.json(s["policy"])
        st.caption(
            "These are Project StarBase source-integrity defaults, not prop-firm rules. Firm-specific close times and rule versions enter in v3/v4."
        )

    st.download_button(
        "Download audit summary JSON",
        data=json.dumps(s, indent=2, default=str).encode("utf-8"),
        file_name=f"{strategy_id}_{profile_id}_audit_summary.json",
        mime="application/json",
    )
