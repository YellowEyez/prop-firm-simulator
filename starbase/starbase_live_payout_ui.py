from __future__ import annotations

import pandas as pd
import streamlit as st

from starbase_live import create_live_account, load_live_profiles, revalue_live_state
from starbase_live_payout import (
    LivePayoutContext,
    LivePayoutError,
    execute_live_payout,
    live_payout_policy_rows,
    load_live_payout_policies,
    payout_policy_by_id,
    run_live_payout_verification,
)


def render_live_payout_page():
    st.header("StarBase v5I - Live Payout / Withdrawal Lab")
    st.caption(
        "Step 30 executes live cash withdrawals against the Step-28 live account state. It models current payout gates, splits, safety nets, payout-caused closure, and Live Bonus cash where current official rules are explicit. "
        "Final forfeiture/closure-value accounting remains Step 31."
    )

    catalog = load_live_payout_policies()
    c1, c2, c3 = st.columns(3)
    c1.metric("Live payout policy schema", catalog.get("schema_version"))
    c2.metric("Policies verified as of", catalog.get("verified_as_of"))
    c3.metric("Current StarBase progress", "33 / 60 verified")

    with st.expander("What Step 30 certifies", expanded=False):
        st.markdown(
            """
Step 30 certifies the **live withdrawal event** itself:

- how much gross live profit is presently withdrawable;
- minimum payout rules;
- trader/firm split;
- Daily vs cycle-gated access;
- safety-net / minimum-balance protection;
- when a full or special withdrawal closes the Live account;
- Lucid's first-live bonus cash as a separate external payout;
- Topstep Reserve remaining outside ordinary payout balance;
- Apex Bonus Vault release **estimate** kept separate from guaranteed cash.

Step 31 still decides the final household treatment of value left behind when a Live account closes, transitions, breaches, or forfeits Reserve/Vault/other buckets.
"""
        )

    st.subheader("Current live payout policies")
    st.dataframe(pd.DataFrame(live_payout_policy_rows(catalog)), use_container_width=True, hide_index=True)

    with st.expander("Inspect one live payout policy - detailed rules live here", expanded=False):
        labels = {p["display_name"]: p["policy_id"] for p in catalog.get("policies", [])}
        chosen = st.selectbox("Live payout policy", list(labels), key="live_payout_policy_v5i")
        st.json(payout_policy_by_id(catalog, labels[chosen]))

    st.divider()
    st.subheader("Step 30 certification")
    st.write("Click one button. No TradingView data is needed.")
    if st.button("Run Live Payout Verification Suite", type="primary", key="run_live_payout_v5i"):
        st.session_state["live_payout_v5i_suite"] = run_live_payout_verification(catalog)

    suite = st.session_state.get("live_payout_v5i_suite")
    if suite:
        a, b, c, d = st.columns(4)
        a.metric("Live payout fixtures", suite["total"])
        b.metric("Passed", suite["passed"])
        c.metric("Failed", suite["failed"])
        d.metric("Policy schema", suite["payout_schema"])
        if suite["all_pass"]:
            st.success(f"LIVE PAYOUT SUITE PASSED - {suite['passed']} / {suite['total']} fixtures matched expected withdrawal values.")
        else:
            st.error("LIVE PAYOUT SUITE FAILED - do not certify Step 30.")
        st.caption(f"Live payout policies verified as of: {suite['policies_verified_as_of']} | Suite: {suite['suite_version']}")
        for result in suite["results"]:
            label = "PASS" if result["pass"] else "FAIL"
            with st.expander(f"{label} - {result['fixture_id']}", expanded=not result["pass"]):
                df = pd.DataFrame(result.get("checks") or [])
                if not df.empty:
                    df = df.rename(columns={"field": "Exact field", "expected": "Expected", "actual": "StarBase actual", "pass": "Matches"})
                    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Manual live-withdrawal sandbox")
    st.caption("Small deterministic sandbox for understanding one live payout. This is not yet a full historical live-trading runner.")
    live_catalog = load_live_profiles()
    supported_profile_ids = []
    for p in catalog.get("policies", []):
        supported_profile_ids.extend(p.get("profile_ids") or [])
    profiles = [p for p in live_catalog.get("profiles", []) if p.get("profile_id") in supported_profile_ids and p.get("state_grade") != "CONFLICTING_OFFICIAL_TEXT"]
    options = {p["display_name"]: p for p in profiles}
    chosen_label = st.selectbox("Live account profile", list(options), key="live_payout_manual_profile")
    profile = options[chosen_label]
    kwargs = {}
    if str(profile.get("starting_balance_mode", "")).startswith("TRANSITION_DERIVED"):
        kwargs["starting_balance_override"] = st.number_input("Transition-derived starting / unlocked balance", min_value=float(profile.get("minimum_starting_balance") or 0), value=10000.0, step=500.0)
        kwargs["reserve_balance"] = st.number_input("Reserve balance", min_value=0.0, value=40000.0, step=500.0)
    state = create_live_account(profile["profile_id"], catalog=live_catalog, **kwargs)
    inspect_balance = st.number_input("Current live account balance before payout", value=float(state.starting_balance), step=100.0)
    state = revalue_live_state(state, float(inspect_balance), catalog=live_catalog)
    requested = st.number_input("Requested gross withdrawal", min_value=0.0, value=0.0, step=100.0)
    winning_cycle = st.number_input("Winning days this payout cycle (Topstep only)", min_value=0, value=0, step=1)
    lifetime_wins = st.number_input("Lifetime Live winning days (Topstep only)", min_value=0, value=0, step=1)
    live_days = st.number_input("Live days elapsed (Apex safety-net closeout only)", min_value=0, value=0, step=1)
    available_profit = st.number_input("Explicit withdrawable live-profit ledger (MFFU only)", min_value=0.0, value=0.0, step=100.0)
    allow_closeout = st.checkbox("Apex: intentionally use 90-day safety-net closeout", value=False)
    first_live_trip = st.checkbox("Lucid: first live trip (Live Bonus eligible if target reached)", value=False)
    if st.button("Execute manual live payout", key="execute_live_payout_v5i"):
        try:
            ctx = LivePayoutContext(
                requested_gross=float(requested),
                winning_days_this_cycle=int(winning_cycle),
                lifetime_winning_days=int(lifetime_wins),
                live_days_elapsed=int(live_days),
                available_live_profit=float(available_profit) if profile["firm_id"] == "mffu" else None,
                allow_safety_net_closeout=bool(allow_closeout),
                first_live_trip=bool(first_live_trip),
            )
            result = execute_live_payout(state, ctx, catalog=catalog)
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Gross withdrawal", f"${result.gross_withdrawal:,.2f}")
            m2.metric("Cash to Josh", f"${result.trader_cash + result.live_bonus_cash:,.2f}")
            m3.metric("Live balance after", f"${result.balance_after:,.2f}")
            m4.metric("Status after", result.status_after)
            st.json({
                "trader_cash": result.trader_cash,
                "firm_share": result.firm_share,
                "live_bonus_cash": result.live_bonus_cash,
                "bonus_vault_release_estimate": result.bonus_vault_release_estimate,
                "failure_floor_after": result.failure_floor_after,
                "reserve_balance_after": result.reserve_balance_after,
                "payout_count_after": result.payout_count_after,
            })
        except LivePayoutError as exc:
            st.error(str(exc))
