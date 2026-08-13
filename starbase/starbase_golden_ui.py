from __future__ import annotations

import pandas as pd
import streamlit as st

from starbase_golden import run_golden_suite


def render_golden_page():
    st.header("🧪 StarBase v5F — Golden Single-Account Verification")
    st.caption(
        "Tiny hand-calculated account stories are compared dollar-for-dollar with the StarBase lifecycle engine. "
        "These controls are intentionally independent of your Sydney/Julie datasets."
    )

    st.info(
        "Certification target: every golden fixture must PASS. A large historical backtest can hide a small state-machine error; these tiny fixtures cannot."
    )

    if st.button("Run Golden Verification Suite", type="primary", key="run_golden_v5f"):
        st.session_state["golden_v5f_result"] = run_golden_suite()

    suite = st.session_state.get("golden_v5f_result")
    if not suite:
        st.caption("Click the button once. No TradingView upload is needed for this certification step.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Golden fixtures", suite["total"])
    c2.metric("Passed", suite["passed"])
    c3.metric("Failed", suite["failed"])
    c4.metric("Rulebook schema", suite["rulebook_schema"])
    st.caption(f"Rulebook verified as of: {suite['rulebook_verified_as_of']} | Golden suite: {suite['suite_version']}")

    if suite["all_pass"]:
        st.success(f"GOLDEN SUITE PASSED — {suite['passed']} / {suite['total']} fixtures matched their independent expected values.")
    else:
        st.error(f"GOLDEN SUITE FAILED — {suite['failed']} fixture(s) did not match. Do not advance the StarBase certification score.")

    st.dataframe(suite["summary"], use_container_width=True, hide_index=True)

    with st.expander("What this suite certifies", expanded=False):
        st.markdown(
            """
- **Step 19:** evaluations stop when they pass instead of continuing to consume later trades.
- **Step 20:** a funded account starts fresh; evaluation profits are not carried into funded balance.
- **Step 23:** the same exact trade path produces different outcomes when product rules differ.
- **Step 27:** core single-account arithmetic has independent hand-calculated regression controls.

Some funded products remain **engine-pending for advanced rules** such as contract-scaling tiers or dynamic Daily Loss Limit tiers. A passing core arithmetic fixture does not erase those explicit Rule Truth warnings.
"""
        )

    st.subheader("Fixture details")
    for result in suite["results"]:
        icon = "✅" if result["pass"] else "❌"
        with st.expander(f"{icon} {result['fixture_id']} — {result['title']}", expanded=not result["pass"]):
            st.write(result["purpose"])
            st.caption(f"Verification scope: {result.get('confidence','—')}")
            checks = pd.DataFrame(result.get("checks") or [])
            if not checks.empty:
                checks = checks.rename(columns={"field": "Exact field", "expected": "Hand-calculated expected", "actual": "StarBase actual", "pass": "Matches"})
                st.dataframe(checks, use_container_width=True, hide_index=True)
            if result.get("confidence") != "FULL_CORE":
                st.warning("This fixture verifies the stated core arithmetic only. Advanced product behavior that is still engine-pending remains non-rankable until its dedicated handler is completed.")
