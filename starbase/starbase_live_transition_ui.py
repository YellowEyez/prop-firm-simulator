from __future__ import annotations

import pandas as pd
import streamlit as st

from starbase_live_transition import (
    LiveTransitionError,
    SimTransitionAccount,
    execute_live_transition,
    load_transition_policies,
    run_live_transition_verification,
    transition_policy_by_id,
    transition_policy_rows,
    transition_result_as_dict,
)


def _money(v):
    return "-" if v is None else f"${float(v):,.2f}"


def render_live_transition_page():
    st.header("StarBase v5H - Live Transition Lab")
    st.caption(
        "Step 29 models the event that moves simulated-funded inventory into Live. Discretionary firm call-ups are explicit inputs, never inferred from TradingView history. "
        "Live withdrawals remain Step 30; final transition-forfeiture household accounting remains Step 31."
    )

    catalog = load_transition_policies()
    c1, c2, c3 = st.columns(3)
    c1.metric("Transition policy schema", catalog.get("schema_version"))
    c2.metric("Policies verified as of", catalog.get("verified_as_of"))
    c3.metric("Current StarBase progress", "32 / 60 verified")

    with st.expander("What Step 29 certifies", expanded=False):
        st.markdown(
            """
Step 29 answers the **transition-event** questions:

- Was the trigger automatic, threshold-based, or discretionary?
- Which simulated accounts close, suspend, or become Live?
- Which funded accounts are eligible to create Live accounts?
- Is cash already paid to Josh preserved? *(Yes - it never goes backward.)*
- Are evaluation-cost refunds created by the transition?
- Does simulated value become a Bonus Vault / Reserve / tracked transition bucket, or does it not carry?
- What exact Live state is created at transition?

Step 29 does **not** yet execute Live withdrawals or convert every transition-value bucket into final realized/forfeited household cash. Those are Steps 30-31.
"""
        )

    st.subheader("Current live-transition policies")
    st.dataframe(pd.DataFrame(transition_policy_rows(catalog)), use_container_width=True, hide_index=True)

    with st.expander("Inspect one transition policy - detailed rules live here", expanded=False):
        labels = {f"{p['firm_name']} - {p['policy_id']}": p["policy_id"] for p in catalog.get("policies", [])}
        chosen = st.selectbox("Transition policy", list(labels), key="transition_policy_v5h")
        st.json(transition_policy_by_id(catalog, labels[chosen]))

    st.divider()
    st.subheader("Step 29 certification")
    st.write("Click one button. No TradingView data is needed.")
    if st.button("Run Live Transition Verification Suite", type="primary", key="run_transition_v5h"):
        st.session_state["transition_v5h_suite"] = run_live_transition_verification(catalog)

    suite = st.session_state.get("transition_v5h_suite")
    if suite:
        a, b, c, d = st.columns(4)
        a.metric("Transition fixtures", suite["total"])
        b.metric("Passed", suite["passed"])
        c.metric("Failed", suite["failed"])
        d.metric("Policy schema", suite["transition_schema"])
        if suite["all_pass"]:
            st.success(f"LIVE TRANSITION SUITE PASSED - {suite['passed']} / {suite['total']} fixtures matched expected transition values.")
        else:
            st.error("LIVE TRANSITION SUITE FAILED - do not certify Step 29.")
        st.caption(f"Transition policies verified as of: {suite['policies_verified_as_of']} | Suite: {suite['suite_version']}")

        for result in suite["results"]:
            icon = "PASS" if result["pass"] else "FAIL"
            with st.expander(f"{icon} - {result['fixture_id']}", expanded=not result["pass"]):
                df = pd.DataFrame(result.get("checks") or [])
                if not df.empty:
                    df = df.rename(columns={"field": "Exact field", "expected": "Expected", "actual": "StarBase actual", "pass": "Matches"})
                    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Manual transition sandbox")
    st.caption("Small scenario sandbox for understanding transition mechanics. It does not replace the later Josh household transition engine.")
    policy_ids = {p["firm_name"] + " - " + p["policy_id"]: p["policy_id"] for p in catalog.get("policies", []) if p.get("transition_grade") != "BLOCKED_CONFLICTING_LIVE_PROFILE"}
    label = st.selectbox("Policy to inspect", list(policy_ids), key="manual_transition_policy_v5h")
    pid = policy_ids[label]
    explicit = st.checkbox("Explicit firm live call-up / selection has occurred", value=False, key="manual_transition_callup_v5h")
    st.info("The sandbox uses a single synthetic 50K funded account. Use the verification fixtures above for certified multi-account examples.")
    payout_count = st.number_input("Funded payouts already completed", min_value=0, value=1, step=1, key="manual_transition_payouts_v5h")
    sim_profit = st.number_input("Current simulated profit balance", value=1000.0, step=100.0, key="manual_transition_profit_v5h")
    cost_basis = st.number_input("Known acquisition/evaluation cost basis", min_value=0.0, value=100.0, step=10.0, key="manual_transition_cost_v5h")
    if st.button("Evaluate / execute transition sandbox", key="manual_transition_run_v5h"):
        firm = transition_policy_by_id(catalog, pid)["firm_id"]
        source_product = transition_policy_by_id(catalog, pid).get("source_products", [""])[0]
        account = SimTransitionAccount(
            account_id="SANDBOX-F1",
            firm_id=firm,
            product_id=source_product,
            stage="SIM_FUNDED",
            account_size=50000,
            current_profit_balance=float(sim_profit),
            payout_count=int(payout_count),
            consecutive_approved_payouts=int(payout_count),
            acquisition_cost_basis=float(cost_basis),
        )
        try:
            result = execute_live_transition(
                pid,
                [account],
                catalog=catalog,
                explicit_callup=explicit,
                household_payouts_since_last_transition=int(payout_count),
                household_total_sim_payouts=0.0,
                trigger_reason="MANUAL_SANDBOX",
            )
            st.session_state["manual_transition_v5h_result"] = result
        except LiveTransitionError as exc:
            st.error(str(exc))

    result = st.session_state.get("manual_transition_v5h_result")
    if result:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Transition executed", "Yes" if result.transition_executed else "No")
        m2.metric("Live accounts created", len(result.live_accounts))
        m3.metric("Refunds created", _money(result.refunds_created))
        m4.metric("Value pending Step 31", _money(result.unresolved_transition_value + result.known_noncarried_sim_value + result.excess_transfer_value))
        if result.warnings:
            with st.expander("Transition notes / realism warnings", expanded=False):
                for w in result.warnings:
                    st.warning(w)
        st.json(transition_result_as_dict(result))
