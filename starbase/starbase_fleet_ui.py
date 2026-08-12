"""Streamlit UI for Project StarBase v5C Josh fleet economics + inventory."""
from __future__ import annotations

import streamlit as st

from tradingview_audit import AuditPolicy, audit_tradingview_files, strict_valid_ledger, reviewed_usable_ledger
from starbase_rulebook import load_rulebook
from starbase_lifecycle import _PAYOUT_ENGINE_SUPPORT
from starbase_fleet import FleetConfig, raw_strategy_baseline, run_single_product_fleet, build_fleet_bundle
from starbase_economics import load_cost_reference, cost_reference_for_product
from starbase_dataset_library_ui import select_dataset_or_upload


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
    st.header("🏠 Josh Household — Fleet Economics + Ending Inventory (v5C)")
    st.caption("StarBase Progress: 24/60 deployment-certified. Step 24 economics is implemented and awaiting this repaired v5C UI certification. Dataset Library infrastructure D1/D2 is complete; the 60-step sequence remains intact.")
    st.info("v5C is still funded-only and one product at a time. It now separates payout cash, external account costs, embedded trading commissions, active-account cost basis, claimable payouts, accrued-but-blocked payout capacity, and unresolved live-transition value.")

    files, strategy_id, profile_id, saved_dataset = select_dataset_or_upload(
        key_prefix="v5b", default_strategy="Sydney_01", default_profile="1NQ"
    )
    household=st.text_input("Household / strategy business name", value="Josh", key="v5b_household")
    if not files:
        st.warning("Choose a saved strategy dataset or upload the exact TradingView profile to begin the fleet test.")
        return
    if saved_dataset is not None:
        st.caption(f"Saved dataset identity: **{saved_dataset.get('display_name')}** · chart interval **{saved_dataset.get('chart_interval','Unknown')}** · profile **{profile_id}**")

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

    include_review=st.checkbox("Include REVIEW trades (research only)", value=False, key="v5b_review")
    if include_review:
        st.warning(f"🟠 REVIEW TRADES INCLUDED — RESEARCH MODE. {audit.summary['review_trades']:,} quarantined trades are being added. Do not compare these numbers directly with the strict Sydney certification baseline.")
        ledger=reviewed_usable_ledger(audit)
    else:
        st.success("🟢 STRICT DATASET — CERTIFICATION MODE. REVIEW trades are excluded.")
        ledger=strict_valid_ledger(audit)

    st.subheader("1. Raw strategy control")
    base_comm=st.number_input("Round-trip commission / contract ($)", min_value=0.0, value=3.50, step=0.25, key="v5b_comm")
    baseline=raw_strategy_baseline(ledger, include_review_rows=include_review, commission_per_contract_round_trip=float(base_comm))
    b1,b2,b3,b4,b5=st.columns(5)
    b1.metric("Eligible signals", f"{baseline['eligible_trades']:,}")
    b2.metric("Gross source P/L", _money(baseline['gross_pnl']))
    b3.metric("Commissions inside P/L", _money(baseline['commissions']))
    b4.metric("Net after commission", _money(baseline['net_after_firm_commission']))
    b5.metric("Win rate", f"{baseline['win_rate']*100:.2f}%")
    st.caption("Control only: every eligible signal, no prop rules or account capacity. Commissions shown here reduce the prop-account trade result; they are not later subtracted a second time from Josh's bank-account cash.")

    rb=load_rulebook()
    opts=_funded_options(rb)
    selected_label=st.selectbox("Funded product", [o['label'] for o in opts], key="v5b_product")
    selected=next(o for o in opts if o['label']==selected_label)

    st.subheader("2. Account-cost basis")
    catalog=load_cost_reference()
    ref=cost_reference_for_product(catalog, selected['product_id'], selected['size'])
    with st.expander("Official pricing reference / provenance", expanded=False):
        st.write(f"Pricing status: **{ref.get('pricing_status','NOT_MODELED')}**")
        if ref.get('notes'):
            st.write(ref['notes'])
        detail={k:v for k,v in ref.items() if k not in {'product_id','account_size','pricing_status','acquisition_model','notes','sources'} and v is not None}
        if detail:
            st.json(detail)
        for src in ref.get('sources',[]):
            st.caption(src)

    cost_label=st.radio(
        "How should this funded-only fleet value newly provisioned funded accounts?",
        ["Existing/pre-owned funded inventory — acquisition cost unknown", "Manual effective funded acquisition cost per account"],
        horizontal=True,
        key="v5b_cost_mode",
    )
    cost_mode="EXISTING_INVENTORY_UNKNOWN_COST" if cost_label.startswith("Existing") else "MANUAL_EFFECTIVE_FUNDED_COST"
    ec1,ec2,ec3=st.columns(3)
    effective_cost=float(ec1.number_input("Effective external cost / provisioned funded account ($)", min_value=0.0, value=0.0, step=5.0, disabled=cost_mode!="MANUAL_EFFECTIVE_FUNDED_COST", help="For evaluation-based products this should eventually be replaced by the exact Evaluation Factory cost. For now you may enter a research assumption."))
    refund_bonus=float(ec2.number_input("Refund / bonus cash per provisioned account ($)", min_value=0.0, value=0.0, step=5.0, disabled=cost_mode!="MANUAL_EFFECTIVE_FUNDED_COST"))
    household_cost=float(ec3.number_input("One-time household external cost ($)", min_value=0.0, value=0.0, step=5.0))
    if cost_mode=="EXISTING_INVENTORY_UNKNOWN_COST":
        st.warning("The app can show payout cash and cash flow during the simulated period, but it will NOT call the result final business net because the original funded-account acquisition cost is unknown.")
    else:
        st.info("Manual effective funded cost is a research assumption. Once the Evaluation Factory is built, evaluation purchase/reset/pass/activation history will replace this shortcut account-by-account.")

    st.subheader("3. Fleet capacity / replacement policy")
    mode_label=st.radio(
        "Capacity mode",
        [
            "Fixed fleet — no replacements",
            "Maintain N active funded accounts — instant replacement research",
            "Force 100% signal capture — unlimited-capacity research",
        ],
        horizontal=False,
        key="v5b_mode",
    )
    if mode_label.startswith("Fixed"):
        mode="FIXED_FLEET"
    elif mode_label.startswith("Maintain"):
        mode="MAINTAIN_FIXED_ACTIVE"
    else:
        mode="FORCE_100_CAPTURE"

    c1,c2,c3,c4=st.columns(4)
    fixed=int(c1.number_input("Target / starting funded accounts", min_value=1, max_value=1000, value=30, step=1, disabled=mode=="FORCE_100_CAPTURE"))
    cap=int(c2.number_input("Max trades / account / futures session", min_value=1, max_value=20, value=1, step=1))
    payout_mode=c3.selectbox("Payout behavior", ["MAX_ALLOWED","MINIMUM_ONLY","NONE"], index=0)
    reward=c4.number_input("Reward-share override % (0 = rulebook)", min_value=0.0, max_value=100.0, value=0.0, step=1.0)

    if mode=="FORCE_100_CAPTURE":
        st.warning("Force-100% intentionally overrides real account-count limits and provisions as many funded slots as necessary. This is a theoretical capacity research mode, not a deployable household claim.")
    elif mode=="MAINTAIN_FIXED_ACTIVE":
        st.warning("Maintain-N instantly replaces failed/closed funded accounts for research continuity. Real evaluation-to-funded replacement delay and legal purchase limits are NOT modeled yet; those are Steps 38-40/43-46.")

    cfg=FleetConfig(
        product_id=selected['product_id'], account_size=selected['size'], capacity_mode=mode,
        fixed_accounts=fixed, max_trades_per_account_per_session=cap,
        commission_per_contract_round_trip=float(base_comm), include_review_rows=include_review,
        payout_request_mode=payout_mode, reward_share_override_percent=None if reward<=0 else float(reward),
        household_name=household,
        acquisition_cost_mode=cost_mode,
        effective_cost_per_funded_account=effective_cost,
        refund_or_bonus_per_account=refund_bonus,
        one_time_household_external_cost=household_cost,
    )

    if st.button("🚀 Run Josh funded fleet economics", type="primary", use_container_width=True):
        try:
            st.session_state.v5b_run=run_single_product_fleet(rb, audit.ledger, cfg)
            st.success("Fleet economics simulation complete.")
        except Exception as exc:
            st.error(str(exc))

    run=st.session_state.get("v5b_run")
    if run is None:
        return

    s=run.summary
    st.subheader("Josh household result")
    st.success("🟢 STRICT DATASET — CERTIFICATION MODE") if s.get('data_mode')=="STRICT_CERTIFICATION" else st.warning("🟠 REVIEW-INCLUDED RESEARCH RESULT")

    x1,x2,x3,x4,x5,x6=st.columns(6)
    x1.metric("Signals routed", f"{s['signals_routed']:,}")
    x2.metric("Capture", f"{s['signal_capture_percent']:.2f}%")
    x3.metric("Accounts provisioned", f"{s['accounts_provisioned']:,}")
    x4.metric("Failed accounts", f"{s['failed_accounts']:,}")
    x5.metric("Completed payouts", f"{s['completed_payouts']:,}")
    x6.metric("Payout cash received", _money(s['payout_cash_received']))

    st.markdown("#### Realized cash economics")
    y1,y2,y3,y4,y5=st.columns(5)
    y1.metric("External account/household costs", _money(s['account_and_household_external_costs']))
    y2.metric("Refunds / bonuses", _money(s['refunds_or_bonuses_received']))
    y3.metric("Firm commissions (embedded)", _money(s['total_firm_commissions_embedded_in_prop_pnl']))
    y4.metric("Cash flow since sim start", _money(s['cash_flow_since_sim_start_excluding_unknown_preexisting_inventory_cost']))
    y5.metric("Realized household NET", _money(s['realized_household_net_cash_after_modeled_external_costs']))
    if s['realized_household_net_cash_after_modeled_external_costs'] is None:
        st.error("Final household net is intentionally unavailable because the funded-account acquisition cost basis is unknown. This prevents pre-owned/fictional free accounts from masquerading as a profitable business.")
    else:
        st.caption("Realized household NET = payout cash − modeled external account/household costs + modeled refunds/bonuses. Trading commissions are already embedded in account P/L and payout production, so they are shown but not double-subtracted from bank cash.")

    st.markdown("#### Ending inventory / future payout value")
    z1,z2,z3,z4,z5,z6=st.columns(6)
    z1.metric("Active funded accounts", f"{s['active_accounts_at_end']:,}")
    z2.metric("Active-account cost basis", _money(s['active_accounts_cost_basis_at_end']))
    z3.metric("Claimable NOW (trader est.)", _money(s['claimable_now_estimated_trader_cash_at_end']))
    z4.metric("Accrued but BLOCKED (trader est.)", _money(s['accrued_but_not_claimable_estimated_trader_cash_at_end']))
    z5.metric("Active simulated profit inventory", _money(s['active_account_profit_inventory_not_cash']))
    z6.metric("Realistically recoverable future cash", "NOT MODELED")
    st.caption("Claimable NOW has cleared encoded payout gates. Accrued-but-blocked is profit capacity that exists but still needs qualifying days, safety-net/consistency/profit requirements, etc. Realistically recoverable future cash requires survival + live-transition modeling and is intentionally not guessed yet.")

    f1,f2=st.columns(2)
    f1.metric("Confirmed residual sim value forfeited", _money(s['confirmed_forfeited_residual_sim_profit']))
    f2.metric("Unresolved value at payout-cycle/live transition", _money(s['unresolved_live_transition_value']))

    tabs=st.tabs(["Household sessions", "Individual accounts", "Costs", "Bottlenecks", "Forfeiture / transition value", "Trade routing", "Payout ledger", "Download"])
    with tabs[0]:
        st.markdown("**Accounting bridge:** trading P/L, payout deductions, external account purchases, and cash paid to Josh are separate events.")
        st.dataframe(run.household_sessions, use_container_width=True, hide_index=True)
    with tabs[1]:
        st.dataframe(run.accounts, use_container_width=True, hide_index=True)
    with tabs[2]:
        if run.costs.empty:
            st.caption("No external cost events were modeled.")
        else:
            st.dataframe(run.costs, use_container_width=True, hide_index=True)
    with tabs[3]:
        if run.bottlenecks.empty:
            st.caption("No current bottlenecks recorded.")
        else:
            st.dataframe(run.bottlenecks, use_container_width=True, hide_index=True)
    with tabs[4]:
        if run.forfeitures.empty:
            st.caption("No confirmed residual forfeiture or unresolved transition value recorded.")
        else:
            st.dataframe(run.forfeitures, use_container_width=True, hide_index=True)
    with tabs[5]:
        st.dataframe(run.trades, use_container_width=True, hide_index=True)
    with tabs[6]:
        if run.payouts.empty:
            st.caption("No payouts occurred in this fleet run.")
        else:
            st.dataframe(run.payouts, use_container_width=True, hide_index=True)
    with tabs[7]:
        blob=build_fleet_bundle(run)
        st.download_button("Download complete StarBase v5C analysis ZIP", blob, "StarBase_v5C_Josh_economics_bundle.zip", "application/zip", use_container_width=True)
        st.caption("Includes household/session ledger, account inventory, trade routing, payout ledger, COST_LEDGER, BOTTLENECK_SUMMARY and forfeiture/transition-value ledger for deeper ChatGPT analysis.")
