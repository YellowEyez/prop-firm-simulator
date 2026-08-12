"""Streamlit UI for Project StarBase v5A Josh single-product funded fleet."""
from __future__ import annotations

import streamlit as st

from tradingview_audit import AuditPolicy, audit_tradingview_files, strict_valid_ledger, reviewed_usable_ledger
from starbase_rulebook import load_rulebook
from starbase_lifecycle import _PAYOUT_ENGINE_SUPPORT
from starbase_fleet import FleetConfig, raw_strategy_baseline, run_single_product_fleet, build_fleet_bundle


def _money(x):
    if x is None:
        return "—"
    return f"${float(x):,.2f}"


def _funded_options(rulebook):
    out=[]
    for firm in rulebook.get("firms",[]):
        for product in firm.get("products",[]):
            if not _PAYOUT_ENGINE_SUPPORT.get(product.get("product_id")):
                continue
            for size_s,sr in product.get("account_sizes",{}).items():
                if not sr.get("sim_funded"):
                    continue
                out.append({
                    "label": f"{firm['display_name']} — {product['display_name']} — ${int(size_s)/1000:g}K",
                    "product_id": product["product_id"], "size": int(size_s),
                })
    return out


def render_fleet_page():
    st.header("🏠 Josh Household — Single-Product Funded Fleet (v5A)")
    st.caption("The main view is now the strategy household, not one prop account. Every individual funded account remains independently auditable underneath it.")
    st.info("v5A is funded-only and one product at a time. It adds Fixed Fleet and Force-100%-Signal-Capture research. Exact account acquisition costs and legal household caps are later numbered steps, so payout cash is NOT yet final business profit.")

    files=st.file_uploader("TradingView List of Trades CSV segments", type=["csv"], accept_multiple_files=True, key="v5a_files")
    c1,c2,c3=st.columns(3)
    household=c1.text_input("Household / strategy business name", value="Josh", key="v5a_household")
    strategy_id=c2.text_input("Strategy ID", value="Sydney_01", key="v5a_strategy")
    profile_id=c3.text_input("Exact profile ID", value="1NQ", key="v5a_profile")
    if not files:
        st.warning("Upload the exact TradingView profile to begin the fleet test.")
        return
    try:
        audit=audit_tradingview_files(files, strategy_id=strategy_id, profile_id=profile_id, policy=AuditPolicy())
    except Exception as exc:
        st.error(f"TradingView audit failed: {exc}")
        return
    a1,a2,a3,a4=st.columns(4)
    a1.metric("Strict valid", f"{audit.summary['strict_valid_trades']:,}")
    a2.metric("Review", f"{audit.summary['review_trades']:,}")
    a3.metric("Invalid", f"{audit.summary['invalid_trades']:,}")
    a4.metric("Sessions", f"{audit.summary['active_futures_sessions']:,}")

    include_review=st.checkbox("Include REVIEW trades", value=False, key="v5a_review")
    ledger=reviewed_usable_ledger(audit) if include_review else strict_valid_ledger(audit)

    st.subheader("1. Raw strategy baseline")
    base_comm=st.number_input("Round-trip firm commission / contract ($)", min_value=0.0, value=3.50, step=0.25, key="v5a_comm")
    baseline=raw_strategy_baseline(ledger, include_review_rows=True, commission_per_contract_round_trip=float(base_comm))
    b1,b2,b3,b4,b5=st.columns(5)
    b1.metric("All eligible signals", f"{baseline['eligible_trades']:,}")
    b2.metric("Gross source P/L", _money(baseline['gross_pnl']))
    b3.metric("Firm commissions", _money(baseline['commissions']))
    b4.metric("Net after commission", _money(baseline['net_after_firm_commission']))
    b5.metric("Win rate", f"{baseline['win_rate']*100:.2f}%")
    st.caption("This is the mathematical control: every eligible signal, no prop rules, no account capacity. Fleet results should reconcile back to this opportunity stream.")

    rb=load_rulebook()
    opts=_funded_options(rb)
    selected_label=st.selectbox("Funded product", [o['label'] for o in opts], key="v5a_product")
    selected=next(o for o in opts if o['label']==selected_label)

    st.subheader("2. Fleet capacity")
    mode_label=st.radio(
        "Capacity mode",
        ["Fixed fleet", "Force 100% signal capture (unlimited-capacity research)"],
        horizontal=True,
        key="v5a_mode",
    )
    mode="FIXED_FLEET" if mode_label=="Fixed fleet" else "FORCE_100_CAPTURE"
    c1,c2,c3,c4=st.columns(4)
    fixed=int(c1.number_input("Starting funded accounts", min_value=1, max_value=500, value=30, step=1, disabled=mode!="FIXED_FLEET"))
    cap=int(c2.number_input("Max trades / account / futures session", min_value=1, max_value=20, value=1, step=1))
    payout_mode=c3.selectbox("Payout behavior", ["MAX_ALLOWED","MINIMUM_ONLY","NONE"], index=0)
    reward=c4.number_input("Reward-share override % (0 = rulebook)", min_value=0.0, max_value=100.0, value=0.0, step=1.0)

    st.warning("Force-100% mode intentionally overrides real account-count limits. It still enforces each individual account's funded rules. StarBase will report how many funded accounts the strategy actually consumed. Account acquisition costs are not yet included.") if mode=="FORCE_100_CAPTURE" else None

    cfg=FleetConfig(
        product_id=selected['product_id'], account_size=selected['size'], capacity_mode=mode,
        fixed_accounts=fixed, max_trades_per_account_per_session=cap,
        commission_per_contract_round_trip=float(base_comm), include_review_rows=include_review,
        payout_request_mode=payout_mode, reward_share_override_percent=None if reward<=0 else float(reward),
        household_name=household,
    )

    if st.button("🚀 Run Josh funded fleet", type="primary", use_container_width=True):
        try:
            st.session_state.v5a_run=run_single_product_fleet(rb, audit.ledger, cfg)
            st.success("Fleet simulation complete.")
        except Exception as exc:
            st.error(str(exc))

    run=st.session_state.get("v5a_run")
    if run is None:
        return

    s=run.summary
    st.subheader("Josh household result")
    x1,x2,x3,x4,x5,x6=st.columns(6)
    x1.metric("Signals routed", f"{s['signals_routed']:,}")
    x2.metric("Capture", f"{s['signal_capture_percent']:.2f}%")
    x3.metric("Accounts provisioned", f"{s['accounts_provisioned']:,}")
    x4.metric("Failed accounts", f"{s['failed_accounts']:,}")
    x5.metric("Completed payouts", f"{s['completed_payouts']:,}")
    x6.metric("Payout cash received", _money(s['payout_cash_received']))

    y1,y2,y3,y4=st.columns(4)
    y1.metric("Active funded at data end", f"{s['active_accounts_at_end']:,}")
    y2.metric("Unpaid payout available", _money(s['unpaid_payout_available_at_end_gross']))
    y3.metric("Active profit inventory (not cash)", _money(s['active_account_profit_inventory_not_cash']))
    y4.metric("Total firm commissions", _money(s['total_firm_commissions']))

    st.error("Final household NET PROFIT is intentionally not shown yet because v5A does not include evaluation/direct-funded acquisition costs, resets, activation fees, subscriptions, refunds, or promotions. Those are Steps 24-25 and must be correct before payout cash becomes business profit.")

    tabs=st.tabs(["Household sessions", "Individual accounts", "Trade routing", "Payout ledger", "Download"])
    with tabs[0]:
        st.markdown("**Accounting bridge:** trading P/L and prop-account payout deductions are separate from cash sent to Josh. A profitable session can end with lower prop balances after a payout without being an accounting error.")
        st.dataframe(run.household_sessions, use_container_width=True, hide_index=True)
    with tabs[1]:
        st.dataframe(run.accounts, use_container_width=True, hide_index=True)
    with tabs[2]:
        st.dataframe(run.trades, use_container_width=True, hide_index=True)
    with tabs[3]:
        if run.payouts.empty:
            st.caption("No payouts occurred in this fleet run.")
        else:
            st.dataframe(run.payouts, use_container_width=True, hide_index=True)
    with tabs[4]:
        blob=build_fleet_bundle(run)
        st.download_button("Download complete Josh fleet analysis ZIP", blob, "StarBase_v5A_Josh_fleet_bundle.zip", "application/zip", use_container_width=True)
        st.caption("This package is intentionally designed to upload back into ChatGPT for deeper account/session/bottleneck analysis.")
