from __future__ import annotations

import json
import streamlit as st

from tradingview_audit import AuditPolicy, audit_tradingview_files, strict_valid_ledger, reviewed_usable_ledger
from starbase_rulebook import load_rulebook
from starbase_lifecycle import LifecycleConfig, run_lifecycle, comparison_rows, build_lifecycle_bundle


def _money(x):
    if x is None:
        return "—"
    return f"${float(x):,.2f}"


def _account_options(rulebook, mode: str):
    out=[]
    need_eval = mode in {"EVALUATION_ONLY","EVAL_TO_FUNDED"}
    need_funded = mode in {"FUNDED_ONLY","EVAL_TO_FUNDED"}
    for firm in rulebook.get("firms",[]):
        for product in firm.get("products",[]):
            for size_s, sr in product.get("account_sizes",{}).items():
                if need_eval and not sr.get("evaluation"):
                    continue
                if need_funded and not sr.get("sim_funded"):
                    continue
                out.append({
                    "label": f"{firm['display_name']} — {product['display_name']} — ${int(size_s)/1000:g}K",
                    "product_id": product["product_id"], "size": int(size_s),
                })
    return out


def render_lifecycle_page():
    st.header("🧭 Lifecycle-Correct Trader + Account Comparison (v4C)")
    st.caption("This workspace fixes v4B's biggest limitation: evaluations actually stop when they pass/fail/expire, and supported funded products actually take payouts. It is still one account or one eval→funded lineage; v5 fans signals across fleets.")
    st.info("If two products now produce similar results, it should be because their rules and the selected trade path genuinely did so — not because StarBase kept trading every account indefinitely after its target.")

    files = st.file_uploader("TradingView List of Trades CSV segments", type=["csv"], accept_multiple_files=True, key="v4c_files")
    c1,c2=st.columns(2)
    strategy_id=c1.text_input("Strategy ID", value="Sydney_01", key="v4c_strategy")
    profile_id=c2.text_input("Exact profile ID", value="1NQ", key="v4c_profile")
    if not files:
        st.warning("Upload the exact TradingView profile you want StarBase to trade.")
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

    rulebook=load_rulebook()
    mode_label=st.radio("Research mode", ["Evaluation only", "Funded only (assume account already exists)", "Evaluation → Funded single lineage"], horizontal=True)
    mode={"Evaluation only":"EVALUATION_ONLY","Funded only (assume account already exists)":"FUNDED_ONLY","Evaluation → Funded single lineage":"EVAL_TO_FUNDED"}[mode_label]
    opts=_account_options(rulebook, mode)
    if not opts:
        st.error("No rulebook products support this stage combination.")
        return
    selected_label=st.selectbox("Account / product", [x["label"] for x in opts], key="v4c_account")
    selected=next(x for x in opts if x["label"]==selected_label)

    r1,r2,r3,r4=st.columns(4)
    cap=r1.number_input("Max trades / account / futures session", min_value=1, max_value=100, value=1, step=1, key="v4c_cap")
    commission=r2.number_input("Round-trip commission / contract ($)", min_value=0.0, value=3.50, step=0.25, key="v4c_comm")
    include_review=r3.checkbox("Include REVIEW trades", value=False, key="v4c_review")
    payout_mode=r4.selectbox("Funded payout behavior", ["MAX_ALLOWED","MINIMUM_ONLY","NONE"], index=0, help="MAX_ALLOWED requests the largest encoded legal payout as soon as eligible. MINIMUM_ONLY is a survival sensitivity. NONE lets profit accumulate without requests.")

    platform="DEFAULT"
    if selected["product_id"]=="apex_eod":
        platform=st.selectbox("Apex evaluation platform variant", ["DEFAULT","RITHMIC","WEALTHCHARTS","TRADOVATE"], index=0)
    intraday=st.selectbox("Intraday-trailing MFE/MAE order assumption", ["MFE_BEFORE_MAE_CONSERVATIVE","MAE_BEFORE_MFE_OPTIMISTIC"], index=0)
    reward_override=st.number_input("Optional reward-share override % (0 = use rulebook)", min_value=0.0, max_value=100.0, value=0.0, step=1.0, help="Useful for account-specific promotions/add-ons such as FundedNext reward share. Zero keeps the versioned rulebook value.")

    ledger=reviewed_usable_ledger(audit) if include_review else strict_valid_ledger(audit)
    cfg=LifecycleConfig(
        product_id=selected["product_id"], account_size=selected["size"], mode=mode,
        max_trades_per_session=int(cap), commission_per_contract_round_trip=float(commission), include_review_rows=include_review,
        intraday_order_assumption=intraday, platform_variant=platform, payout_request_mode=payout_mode,
        reward_share_override_percent=None if reward_override<=0 else float(reward_override),
    )

    if st.button("▶ Run lifecycle-correct account", type="primary", use_container_width=True):
        try:
            st.session_state.v4c_result=run_lifecycle(rulebook, audit.ledger, cfg)
            st.success("Lifecycle run complete.")
        except Exception as exc:
            st.error(str(exc))

    result=st.session_state.get("v4c_result")
    if result is not None:
        st.subheader("Lifecycle result")
        q1,q2,q3,q4,q5=st.columns(5)
        q1.metric("Evaluation", str(result.summary.get("evaluation_status") or "—"))
        q2.metric("Funded", str(result.summary.get("funded_status") or "—"))
        q3.metric("Payouts", f"{int(result.summary.get('funded_payouts') or 0)}")
        q4.metric("Cash paid to trader", _money(result.summary.get("trader_wallet_cash")))
        q5.metric("Payout available at data end", _money(result.summary.get("unpaid_payout_available_gross")))
        if result.funded is not None:
            f=result.funded.summary
            p1,p2,p3,p4=st.columns(4)
            p1.metric("Ending funded balance", _money(f.get("ending_balance")))
            p2.metric("Ending failure floor", _money(f.get("ending_failure_floor")))
            p3.metric("Current qualifying days", f"{int(f.get('qualifying_days_current_cycle') or 0)}")
            p4.metric("Payout engine", str(f.get("payout_engine_support")))
            if f.get("payout_engine_support")=="NOT_MODELED":
                st.error("This product is visible for research, but its funded payout engine is not trusted/modelled yet. StarBase will not silently substitute another firm's payout formula.")
        tabs=st.tabs(["Evaluation", "Funded", "Payout ledger", "Download"])
        with tabs[0]:
            if result.evaluation is None:
                st.caption("No evaluation stage in this research mode.")
            else:
                st.json(result.evaluation.summary, expanded=False)
                st.dataframe(result.evaluation.sessions, use_container_width=True, hide_index=True)
        with tabs[1]:
            if result.funded is None:
                st.caption("No funded stage was reached/selected.")
            else:
                st.json(result.funded.summary, expanded=False)
                st.dataframe(result.funded.sessions, use_container_width=True, hide_index=True)
        with tabs[2]:
            if result.funded is None or result.funded.payouts.empty:
                st.caption("No completed payout events in this run.")
            else:
                st.dataframe(result.funded.payouts, use_container_width=True, hide_index=True)
        with tabs[3]:
            blob=build_lifecycle_bundle(result)
            st.download_button("Download complete v4C lifecycle bundle", blob, "StarBase_v4C_lifecycle_bundle.zip", "application/zip", use_container_width=True)
            st.caption("Upload this bundle back into ChatGPT for deeper diagnosis without re-sending the full source batch every time.")

    st.divider()
    st.subheader("🔬 Same-profile Account Comparison Lab")
    st.caption("Run the exact same audited strategy profile through multiple products side-by-side. This is the fastest way to detect products whose actual rules fit the strategy differently.")
    comparison_opts=_account_options(rulebook, mode)
    defaults=[x["label"] for x in comparison_opts if x["size"]==50000][:6]
    chosen=st.multiselect("Accounts to compare", [x["label"] for x in comparison_opts], default=defaults, key="v4c_compare")
    if st.button("Compare selected accounts", use_container_width=True):
        configs=[]
        for label in chosen:
            x=next(o for o in comparison_opts if o["label"]==label)
            configs.append(LifecycleConfig(
                product_id=x["product_id"], account_size=x["size"], mode=mode,
                max_trades_per_session=int(cap), commission_per_contract_round_trip=float(commission), include_review_rows=include_review,
                intraday_order_assumption=intraday, platform_variant=platform if x["product_id"]=="apex_eod" else "DEFAULT",
                payout_request_mode=payout_mode, reward_share_override_percent=None if reward_override<=0 else float(reward_override),
            ))
        st.session_state.v4c_compare_df=comparison_rows(rulebook, audit.ledger, configs)
    comp=st.session_state.get("v4c_compare_df")
    if comp is not None:
        st.dataframe(comp, use_container_width=True, hide_index=True)
        st.download_button("Download comparison CSV", comp.to_csv(index=False).encode(), "StarBase_v4C_account_comparison.csv", "text/csv")
        st.info("v4C comparison is still a single-account/single-lineage test. v5 adds fleets, passed-evaluation banks, realistic account caps, auto-provisioning, target-capture percentages, and Force-100%-Signal-Capture research mode.")
