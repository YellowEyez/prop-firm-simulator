"""Streamlit UI for Project StarBase v4A account state + accounting ledger."""
from __future__ import annotations

import json
import pandas as pd
import streamlit as st

from starbase_account import (
    ACCOUNT_STATUSES,
    AccountStateError,
    create_account_from_rulebook,
    ledger_to_records,
    post_account_cost,
    post_trade,
    set_status,
    start_session,
    state_to_dict,
    verify_account_ledger,
)
from starbase_rulebook import load_rulebook


def _money(v):
    return "—" if v is None else f"${float(v):,.2f}"


def _download_json(obj) -> bytes:
    return json.dumps(obj, indent=2, default=str).encode("utf-8")


def render_account_state_page() -> None:
    rulebook = load_rulebook()
    st.header("🧾 StarBase v4A — Single-Account State + Accounting Ledger")
    st.caption(
        "Trusted accounting substrate for one prop account. v4A records balances, commissions, external account costs, "
        "sessions, status, and rule provenance. It deliberately does NOT enforce drawdown breaches, DLLs, pass/fail, or payouts yet."
    )
    st.info(
        "**v4A boundary:** The displayed initial failure floor is a reference derived from the current rulebook. "
        "It is NOT enforced or ratcheted until v4B. This prevents partially implemented risk logic from masquerading as a trusted simulation."
    )

    product_rows = []
    for firm in rulebook["firms"]:
        for product in firm.get("products", []):
            for size_s, size_rules in product.get("account_sizes", {}).items():
                for stage in ("evaluation", "sim_funded", "live"):
                    if stage in size_rules:
                        product_rows.append({
                            "firm_id": firm["firm_id"], "firm": firm["display_name"],
                            "product_id": product["product_id"], "product": product["display_name"],
                            "size": int(size_s), "stage": stage,
                            "label": f"{firm['display_name']} — {product['display_name']} — ${int(size_s)/1000:g}K — {stage.replace('_',' ').title()}"
                        })

    labels = [r["label"] for r in product_rows]
    choice = st.selectbox("Account definition", labels, key="v4a_account_definition")
    selected = next(r for r in product_rows if r["label"] == choice)
    default_id = f"{selected['firm_id'].upper()}-{selected['product_id'].upper()}-{selected['size']}-{selected['stage'].upper()}-001"
    account_id = st.text_input("Account ID", value=default_id, key="v4a_account_id")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Create / reset v4A account", type="primary", use_container_width=True):
            try:
                state, ledger = create_account_from_rulebook(
                    rulebook,
                    product_id=selected["product_id"],
                    account_size=selected["size"],
                    stage=selected["stage"],
                    account_id=account_id.strip() or default_id,
                )
                st.session_state.v4a_state = state
                st.session_state.v4a_ledger = ledger
                st.success("Account initialized from the versioned rulebook.")
            except AccountStateError as exc:
                st.error(str(exc))
    with c2:
        st.caption("Creating a v4A account snapshots its rule identity but does not yet run lifecycle rules.")

    state = st.session_state.get("v4a_state")
    ledger = st.session_state.get("v4a_ledger")
    if state is None or ledger is None:
        st.warning("Create an account above to inspect the v4A accounting engine.")
        return

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Prop balance", _money(state.balance), delta=f"{state.balance-state.starting_balance:+,.2f}")
    k2.metric("Net trading P&L", _money(state.lifetime_net_pnl))
    k3.metric("Commissions", _money(state.lifetime_commissions))
    k4.metric("External cash flow", _money(state.external_cash_flow))
    k5.metric("Trades", f"{state.trade_count:,}")

    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Status", state.status)
    a2.metric("Stage", state.stage.replace("_", " ").title())
    a3.metric("Reference max loss", _money(state.reference_max_loss))
    a4.metric("Reference initial floor", _money(state.reference_initial_failure_floor))

    if state.rule_coverage_status != "VERIFIED":
        st.warning(f"Rule coverage for this stage is **{state.rule_coverage_status}**. v4A still permits accounting inspection, but later trusted lifecycle execution will honor coverage gates.")

    tabs = st.tabs(["Ledger", "Manual accounting test", "Account state", "Rule provenance"])
    with tabs[0]:
        check = verify_account_ledger(ledger)
        if check["valid"]:
            st.success(f"Ledger hash chain valid — {check['event_count']} events")
        else:
            st.error("Ledger verification failed")
            st.json(check["errors"])
        df = pd.DataFrame(ledger_to_records(ledger))
        display_cols = [
            "sequence", "event_type", "session_id", "balance_before", "balance_delta", "balance_after",
            "external_cash_delta", "gross_pnl", "commission", "status_before", "status_after", "note", "event_hash"
        ]
        st.dataframe(df[display_cols], use_container_width=True, hide_index=True)
        st.download_button("Download account ledger CSV", df.to_csv(index=False).encode("utf-8"), f"{state.account_id}_ledger.csv", "text/csv")
        st.download_button("Download account ledger JSON", _download_json(ledger_to_records(ledger)), f"{state.account_id}_ledger.json", "application/json")

    with tabs[1]:
        st.warning("These controls test v4A accounting only. They do not enforce prop rules yet.")
        with st.form("v4a_session_form"):
            sid = st.text_input("Futures session ID", value=state.current_session_id or "2026-08-11")
            if st.form_submit_button("Start / reset session accounting"):
                state, ledger = start_session(state, ledger, sid, note="Manual v4A accounting test")
                st.session_state.v4a_state, st.session_state.v4a_ledger = state, ledger
                st.rerun()
        with st.form("v4a_trade_form"):
            gross = st.number_input("Gross trade P&L before firm commission ($)", value=325.0, step=25.0)
            commission = st.number_input("Firm / round-trip commission cost ($)", min_value=0.0, value=3.5, step=0.5)
            note = st.text_input("Trade note", value="Manual v4A test trade")
            if st.form_submit_button("Post realized trade"):
                try:
                    state, ledger = post_trade(state, ledger, gross_pnl=gross, commission=commission, note=note)
                    st.session_state.v4a_state, st.session_state.v4a_ledger = state, ledger
                    st.rerun()
                except AccountStateError as exc:
                    st.error(str(exc))
        with st.form("v4a_cost_form"):
            cost = st.number_input("External account cost ($)", min_value=0.0, value=100.0, step=10.0)
            cost_note = st.text_input("Cost note", value="Evaluation / activation / reset cost test")
            if st.form_submit_button("Post external account cost"):
                state, ledger = post_account_cost(state, ledger, amount=cost, note=cost_note)
                st.session_state.v4a_state, st.session_state.v4a_ledger = state, ledger
                st.rerun()
        with st.form("v4a_status_form"):
            status = st.selectbox("Manual status test", sorted(ACCOUNT_STATUSES), index=sorted(ACCOUNT_STATUSES).index(state.status) if state.status in ACCOUNT_STATUSES else 0)
            if st.form_submit_button("Record status change"):
                state, ledger = set_status(state, ledger, status=status, note="Manual v4A status test")
                st.session_state.v4a_state, st.session_state.v4a_ledger = state, ledger
                st.rerun()

    with tabs[2]:
        st.json(state_to_dict(state), expanded=True)
        st.download_button("Download account state JSON", _download_json(state_to_dict(state)), f"{state.account_id}_state.json", "application/json")

    with tabs[3]:
        st.write(f"**Rulebook schema:** {state.rulebook_schema_version}")
        st.write(f"**Rulebook verified as of:** {state.rulebook_verified_as_of}")
        st.write(f"**Rule snapshot SHA-256:** `{state.rule_snapshot_hash}`")
        st.write(f"**Drawdown class:** {state.drawdown_type or '—'}")
        st.write(f"**Coverage:** {state.rule_coverage_status}")
        st.caption("The snapshot hash anchors this account to the exact stage-rule payload used at creation time.")
