from __future__ import annotations

import pandas as pd
import streamlit as st

from starbase_live import (
    LiveStateError,
    create_live_account,
    live_profile_rows,
    load_live_profiles,
    profile_by_id,
    run_live_state_verification,
    state_as_dict,
)


def render_live_state_page():
    st.header("🔴 StarBase v5G — Live Account State Lab")
    st.caption(
        "Step 28 makes live accounts first-class state objects. This page verifies starting balance, failure floor, Daily Loss Limit, reserve/vault fields, and current contract tier. "
        "Sim-funded → live transition orchestration is Step 29; live withdrawals are Step 30; live forfeiture accounting is Step 31."
    )

    catalog = load_live_profiles()
    c1, c2, c3 = st.columns(3)
    c1.metric("Live profile schema", catalog.get("schema_version"))
    c2.metric("Profiles verified as of", catalog.get("verified_as_of"))
    c3.metric("Current StarBase progress", "33 / 60 verified")

    with st.expander("What Step 28 does — and does not — certify", expanded=False):
        st.markdown(
            """
**Step 28 certifies the live account's state vocabulary and starting/risk geometry:** balance convention, failure floor, drawdown family, Daily Loss Limit, reserve/Bonus-Vault placeholders, contract tier, and rule provenance.

It deliberately does **not** yet decide *when* a trader is moved live, execute live payouts, erase/convert simulated profits, or enforce household cooldowns. Those are Steps **29–31**.
"""
        )

    st.subheader("Current live-state profiles")
    rows = pd.DataFrame(live_profile_rows(catalog))
    st.dataframe(rows, use_container_width=True, hide_index=True)

    with st.expander("Inspect one live profile", expanded=False):
        labels = {p["display_name"]: p["profile_id"] for p in catalog.get("profiles", [])}
        label = st.selectbox("Live profile", list(labels), key="live_profile_select_v5g")
        profile = profile_by_id(catalog, labels[label])
        st.json(profile)
        if profile.get("state_grade") == "CONFLICTING_OFFICIAL_TEXT":
            st.error("StarBase refuses to instantiate this profile because the current official text contains a load-bearing internal conflict. The conflict is preserved rather than guessed.")
        elif str(profile.get("starting_balance_mode", "")).startswith("TRANSITION_DERIVED"):
            st.warning("This profile requires transition-derived capital. Step 28 can hold that state, but Step 29 will calculate it from the actual simulated-account inventory.")

    st.divider()
    st.subheader("Step 28 certification")
    st.write("Click one button. No TradingView CSV is needed.")
    if st.button("Run Live State Verification Suite", type="primary", key="run_live_state_v5g"):
        st.session_state["live_state_v5g_result"] = run_live_state_verification(catalog)

    suite = st.session_state.get("live_state_v5g_result")
    if suite:
        a, b, c, d = st.columns(4)
        a.metric("Live fixtures", suite["total"])
        b.metric("Passed", suite["passed"])
        c.metric("Failed", suite["failed"])
        d.metric("Profile schema", suite["profile_schema"])
        if suite["all_pass"]:
            st.success(f"LIVE STATE SUITE PASSED — {suite['passed']} / {suite['total']} fixtures matched expected state values.")
        else:
            st.error("LIVE STATE SUITE FAILED — do not certify Step 28.")
        st.caption(f"Live profiles verified as of: {suite['profiles_verified_as_of']} | Suite: {suite['suite_version']}")

        for result in suite["results"]:
            icon = "✅" if result["pass"] else "❌"
            with st.expander(f"{icon} {result['fixture_id']} — {result['profile_id']}", expanded=not result["pass"]):
                df = pd.DataFrame(result.get("checks") or [])
                if not df.empty:
                    df = df.rename(columns={"field": "Exact field", "expected": "Expected", "actual": "StarBase actual", "pass": "Matches"})
                    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Manual state inspector")
    st.caption("This is for inspection only; it does not execute live payouts or transitions yet.")
    selectable = [p for p in catalog.get("profiles", []) if p.get("state_grade") != "CONFLICTING_OFFICIAL_TEXT"]
    options = {p["display_name"]: p for p in selectable}
    chosen_label = st.selectbox("Profile to instantiate", list(options), key="live_state_manual_profile")
    chosen = options[chosen_label]
    kwargs = {}
    if str(chosen.get("starting_balance_mode", "")).startswith("TRANSITION_DERIVED"):
        min_start = float(chosen.get("minimum_starting_balance") or 0)
        kwargs["starting_balance_override"] = st.number_input("Transition-derived starting balance", min_value=min_start, value=max(min_start, 10000.0), step=500.0)
        kwargs["reserve_balance"] = st.number_input("Transition-derived reserve balance", min_value=0.0, value=0.0, step=500.0)
    if st.button("Create / inspect live account state", key="create_live_state_v5g"):
        try:
            state = create_live_account(chosen["profile_id"], catalog=catalog, **kwargs)
            st.session_state["live_manual_state_v5g"] = state
        except LiveStateError as exc:
            st.error(str(exc))
    state = st.session_state.get("live_manual_state_v5g")
    if state:
        snap = state_as_dict(state)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Live balance", f"${state.balance:,.2f}")
        m2.metric("Failure floor", "—" if state.failure_floor is None else f"${state.failure_floor:,.2f}")
        m3.metric("Current cushion", "—" if state.cushion is None else f"${state.cushion:,.2f}")
        m4.metric("Max minis / micros", f"{state.max_minis or '—'} / {state.max_micros or '—'}")
        st.json(snap)
