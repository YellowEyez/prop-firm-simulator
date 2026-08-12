"""Streamlit UI for Project StarBase v4B chronological single-account runner."""
from __future__ import annotations

import json
import pandas as pd
import streamlit as st

from starbase_historical_runner import (
    HistoricalRunnerError,
    RunnerConfig,
    build_run_bundle,
    capacity_slots_for_capture,
    run_single_account_history,
    theoretical_tp_sl,
    tp_sl_diagnostic,
)
from starbase_rulebook import load_rulebook
from tradingview_audit import AuditPolicy, audit_tradingview_files, reviewed_usable_ledger, strict_valid_ledger
from starbase_dataset_library_ui import select_dataset_or_upload


def _money(x):
    return "—" if x is None else f"${float(x):,.2f}"


def _pct(x):
    return "—" if x is None else f"{float(x)*100:.2f}%"


def render_historical_runner_page() -> None:
    st.header("🏁 StarBase v4B — Historical Single-Account Trader")
    st.caption(
        "The first StarBase workspace that actually routes chronological TradingView trades into a prop account. "
        "v4B enforces the per-account futures-session trade cap, commissions, MAE-aware drawdown breaches, EOD floor ratcheting, and basic DLL pauses."
    )
    st.info(
        "**Current boundary:** v4B trades one account. It shows evaluation target/consistency progress, but does not yet auto-pass into funded or request payouts. "
        "Those transitions arrive cumulatively in v4D-v4F. v5 then fans the same signal stream across many accounts."
    )

    files, strategy_id, profile_id, saved_dataset = select_dataset_or_upload(
        key_prefix="v4b", default_strategy="Sydney_01", default_profile="1NQ"
    )

    if not files:
        st.warning("Choose a saved strategy dataset or upload one or more TradingView CSV segments to begin trading the account.")
        return

    try:
        audit = audit_tradingview_files(files, strategy_id=strategy_id, profile_id=profile_id, policy=AuditPolicy())
    except Exception as exc:
        st.error(f"TradingView audit failed: {exc}")
        return

    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Strict valid", f"{audit.summary['strict_valid_trades']:,}")
    a2.metric("Review", f"{audit.summary['review_trades']:,}")
    a3.metric("Invalid", f"{audit.summary['invalid_trades']:,}")
    a4.metric("Futures sessions", f"{audit.summary['active_futures_sessions']:,}")

    rulebook = load_rulebook()
    options = []
    for firm in rulebook["firms"]:
        for product in firm.get("products", []):
            for size_s, size_rules in product.get("account_sizes", {}).items():
                for stage in ("evaluation", "sim_funded"):
                    if size_rules.get(stage):
                        options.append({
                            "label": f"{firm['display_name']} — {product['display_name']} — ${int(size_s)/1000:g}K — {stage.replace('_',' ').title()}",
                            "product_id": product["product_id"], "size": int(size_s), "stage": stage,
                        })
    choice = st.selectbox("Prop account", [x["label"] for x in options], key="v4b_account")
    selected = next(x for x in options if x["label"] == choice)

    r1, r2, r3 = st.columns(3)
    max_trades = r1.number_input("Max trades / account / futures session", min_value=1, max_value=100, value=1, step=1, key="v4b_cap")
    commission = r2.number_input("Round-trip commission / contract ($)", min_value=0.0, value=3.50, step=0.25, key="v4b_comm")
    include_review = r3.checkbox("Include REVIEW trades", value=False, key="v4b_review")

    platform_variant = "DEFAULT"
    if selected["product_id"] == "apex_eod" and selected["stage"] == "evaluation":
        platform_variant = st.selectbox("Apex evaluation platform variant", ["DEFAULT", "RITHMIC", "WEALTHCHARTS", "TRADOVATE"], index=0)

    intraday_assumption = st.selectbox(
        "Intraday-trailing path assumption (only used for intraday DD products)",
        ["MFE_BEFORE_MAE_CONSERVATIVE", "MAE_BEFORE_MFE_OPTIMISTIC"],
        index=0,
        help="MFE and MAE do not reveal which occurred first. Intraday-trailing results are research-grade until exact tick/path data exists.",
    )

    source_ledger = reviewed_usable_ledger(audit) if include_review else strict_valid_ledger(audit)
    strict_for_capacity = strict_valid_ledger(audit)
    if not strict_for_capacity.empty:
        sc = strict_for_capacity.groupby("futures_session_id").size()
        slots = capacity_slots_for_capture(strict_for_capacity)
        with st.expander("Fleet capacity preview (bridge to v5)", expanded=True):
            q1, q2, q3, q4 = st.columns(4)
            q1.metric("Avg valid signals / session", f"{sc.mean():.1f}")
            q2.metric("Median", f"{sc.median():.0f}")
            q3.metric("95th percentile", f"{sc.quantile(.95):.0f}")
            q4.metric("Maximum", f"{sc.max():.0f}")
            f1, f2, f3 = st.columns(3)
            f1.metric("1-trade slots for 80% capture", f"{slots[0.80]}")
            f2.metric("1-trade slots for 90% capture", f"{slots[0.90]}")
            f3.metric("1-trade slots for 95% capture", f"{slots[0.95]}")
            st.caption("v4B still trades one account because it is the arithmetic-verification layer. In v5, the cap applies PER ACCOUNT: if a session has 30 valid signals and 30 eligible accounts with a 1-trade/session cap, StarBase can route up to 30 signals to 30 different accounts, subject to firm limits, account state, and routing rules.")

    diag = tp_sl_diagnostic(source_ledger, commission)
    if diag:
        with st.expander("Strategy profile diagnostics + TP/SL calculator", expanded=False):
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("Win rate after firm commission", _pct(diag["win_rate"]))
            d2.metric("Avg winner", _money(diag["avg_win"]))
            d3.metric("Avg loser", _money(diag["avg_loss"]))
            d4.metric("Expectancy / source trade", _money(diag["expectancy"]))
            st.caption(f"Observed-payoff break-even win rate: {_pct(diag.get('break_even_win_rate_at_observed_payoff'))}. This is descriptive, not an alternate-exit replay.")
            t1, t2 = st.columns(2)
            tp = t1.number_input("Proposed total-dollar TP ($)", min_value=1.0, value=max(1.0, round(abs(diag.get("median_win") or 325.0), 2)), step=25.0)
            sl = t2.number_input("Proposed total-dollar SL ($)", min_value=1.0, value=max(1.0, round(abs(diag.get("median_loss") or 500.0), 2)), step=25.0)
            calc = theoretical_tp_sl(observed_win_rate=diag["win_rate"], proposed_tp=tp, proposed_sl=sl, commission=commission)
            c1, c2, c3 = st.columns(3)
            c1.metric("Theoretical B/E WR", _pct(calc["break_even_win_rate"]))
            c2.metric("Theoretical expectancy", _money(calc["theoretical_expectancy_at_observed_win_rate"]))
            c3.metric("Reward / risk", f"{calc['reward_to_risk']:.3f}x")
            st.warning("This calculator does **not** mutate historical trades. Exact alternate TP/SL validation still requires an exact TradingView profile or a clearly labeled shadow replay.")

    if st.button("▶ Run chronological single-account simulation", type="primary", use_container_width=True):
        try:
            cfg = RunnerConfig(
                product_id=selected["product_id"], account_size=selected["size"], stage=selected["stage"],
                max_trades_per_session=int(max_trades), commission_per_contract_round_trip=float(commission),
                include_review_rows=include_review, intraday_order_assumption=intraday_assumption,
                platform_variant=platform_variant,
            )
            result = run_single_account_history(rulebook, audit.ledger, cfg)
            st.session_state.v4b_result = result
            st.success(f"Run complete: {result.summary['run_id']}")
        except HistoricalRunnerError as exc:
            st.error(str(exc))

    result = st.session_state.get("v4b_result")
    if result is None:
        return

    s = result.summary
    st.subheader("Run result")
    if s["status"] == "FAILED":
        st.error(f"Account failed — {s['failure_reason']} — session {s['failure_session']}")
    else:
        st.success("Account survived the available historical stream.")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Ending balance", _money(s["ending_balance"]), delta=f"{s['net_account_change']:+,.2f}")
    k2.metric("Trades routed", f"{s['trades_routed']:,}")
    k3.metric("Signals skipped", f"{s['signals_skipped_by_session_cap_or_pause']:,}")
    k4.metric("Firm commissions", _money(s["total_firm_commissions"]))
    k5.metric("Ending failure floor", _money(s["ending_failure_floor"]))

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Source sessions", f"{s['source_futures_sessions']:,}")
    m2.metric("Sessions traded", f"{s['traded_sessions']:,}")
    m3.metric("Target progress", "—" if s.get("target_progress") is None else f"{100*s['target_progress']:.1f}%")
    m4.metric("Rule path", "PRODUCTION-GRADE" if s["production_grade_rule_path"] else "RESEARCH-GRADE")

    if not s["production_grade_rule_path"]:
        st.warning(
            f"This run is **research-grade**. Drawdown confidence: {s['drawdown_policy_confidence']}; "
            f"MAE fallbacks: {s['mae_fallback_count']}; intraday-path ambiguous trades: {s['intraday_path_ambiguous_trades']}; DLL triggers requiring approximate liquidation: {s['dll_triggers']}."
        )

    tabs = st.tabs(["Equity + floor", "Session ledger", "Trade routing", "Downloads", "Rule snapshot"])
    with tabs[0]:
        if not result.sessions.empty:
            chart = result.sessions[["futures_session_id", "session_end_balance", "floor_end"]].copy().set_index("futures_session_id")
            st.line_chart(chart)
            st.caption("Each point is a completed 6 PM ET futures session. The failure floor only ratchets when the selected product's encoded rule says it should.")
    with tabs[1]:
        st.dataframe(result.sessions, use_container_width=True, hide_index=True)
    with tabs[2]:
        st.dataframe(result.trades, use_container_width=True, hide_index=True)
    with tabs[3]:
        bundle = build_run_bundle(result)
        st.download_button("Download complete StarBase run bundle ZIP", bundle, f"{s['run_id']}_StarBase_v4B_bundle.zip", "application/zip", use_container_width=True)
        st.download_button("Download session ledger CSV", result.sessions.to_csv(index=False).encode(), f"{s['run_id']}_sessions.csv", "text/csv")
        st.download_button("Download trade routing CSV", result.trades.to_csv(index=False).encode(), f"{s['run_id']}_trades.csv", "text/csv")
        st.caption("The ZIP is designed to be uploaded back into ChatGPT for deeper analysis without needing the original giant strategy CSV batch every time.")
    with tabs[4]:
        st.json(result.rule_snapshot, expanded=False)
        st.code(json.dumps(result.config, indent=2), language="json")
