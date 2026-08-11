from __future__ import annotations

import pandas as pd
import streamlit as st

from starbase_rulebook import filter_rows, flatten_rulebook, load_rulebook, product_details

DD_LABELS = {
    "EOD_TRAILING": "🟦 EOD trailing",
    "INTRADAY_TRAILING": "🟥 Intraday trailing",
    "STATIC": "🟩 Static",
    "NONE": "⬜ None",
    "SELECTABLE_EOD_OR_INTRADAY": "🟪 Selectable EOD / intraday",
    None: "—"
}


def _fmt_money(v):
    if v is None or pd.isna(v):
        return "—"
    return f"${float(v):,.0f}"


def render_rulebook_page():
    data = load_rulebook()
    rows = flatten_rulebook(data)

    st.header("📚 StarBase v3 — Versioned Prop-Firm Rulebook")
    st.caption(
        "This page is the new source-cited rule layer. It does not execute lifecycle math yet. "
        "v4 will consume this schema instead of the stale legacy prop_firms.json."
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Verified as of", data["verified_as_of"])
    c2.metric("Firms", len(data["firms"]))
    c3.metric("Product families", sum(len(f.get("products", [])) for f in data["firms"]))
    c4.metric("Account-size variants", len(rows))

    st.info(
        "StarBase no longer globally hides intraday-trailing funded products. Use Research mode to compare everything, "
        "or the EOD/static preset to isolate products that match the project's usual production preference."
    )

    with st.sidebar:
        st.subheader("📚 v3 Rule Filters")
        preset = st.selectbox(
            "Research preset",
            list(data["policy_presets"].keys()),
            format_func=lambda k: data["policy_presets"][k]["label"],
            key="rulebook_preset"
        )
        preset_cfg = data["policy_presets"][preset]
        st.caption(preset_cfg["description"])
        firm_options = {f["firm_id"]: f["display_name"] for f in data["firms"]}
        selected_firms = st.multiselect("Firms", list(firm_options), format_func=lambda k: firm_options[k])
        sizes = sorted({r.account_size for r in rows})
        selected_sizes = st.multiselect("Account sizes", sizes, default=sizes)

    filtered = filter_rows(
        rows,
        funded_drawdowns=preset_cfg["allowed_funded_drawdowns"],
        firms=selected_firms or None,
        sizes=selected_sizes or None,
        active_only=True
    )

    table = pd.DataFrame([{
        "Firm": r.firm,
        "Product": r.product,
        "Size": f"${r.account_size/1000:.0f}K",
        "Acquisition": r.acquisition_model,
        "Eval DD": DD_LABELS.get(r.evaluation_drawdown, r.evaluation_drawdown or "—"),
        "Funded DD": DD_LABELS.get(r.funded_drawdown, r.funded_drawdown or "—"),
        "Live DD": DD_LABELS.get(r.live_drawdown, r.live_drawdown or "—"),
        "Eval Target": _fmt_money(r.profit_target),
        "Eval MLL": _fmt_money(r.evaluation_max_loss),
        "Funded MLL": _fmt_money(r.funded_max_loss),
        "Qual Days": r.payout_qualifying_days if r.payout_qualifying_days is not None else "—",
        "Qual $/Day": _fmt_money(r.payout_qualifying_profit),
        "Split": f"{r.payout_split_percent:.0f}%" if r.payout_split_percent is not None else "—",
        "Verification": r.verification_status,
        "v4 readiness": r.simulation_readiness,
    } for r in filtered])

    st.subheader("Current product matrix")
    st.dataframe(table, use_container_width=True, hide_index=True)

    product_ids = []
    product_labels = {}
    for firm in data["firms"]:
        for product in firm.get("products", []):
            product_ids.append(product["product_id"])
            product_labels[product["product_id"]] = f"{firm['display_name']} — {product['display_name']}"

    st.subheader("Inspect one product")
    pid = st.selectbox("Product family", product_ids, format_func=lambda x: product_labels[x])
    details = product_details(data, pid)
    firm = details["firm"]; product = details["product"]

    left, right = st.columns([2, 1])
    with left:
        st.markdown(f"### {product['display_name']}")
        st.write(f"**Status:** {product['status']}  |  **Verified:** {product['verified_date']}  |  **Verification:** {product.get('verification_status','UNKNOWN')}")
        st.write(f"**Acquisition:** {product.get('acquisition_model','UNKNOWN')}  |  **v4 readiness:** {product.get('simulation_readiness','UNKNOWN')}")
        if product.get("notes"):
            st.warning(product["notes"])
        for size_s, sr in sorted(product["account_sizes"].items(), key=lambda kv: int(kv[0])):
            with st.expander(f"${int(size_s):,} rules", expanded=False):
                for stage in ("evaluation", "sim_funded", "live"):
                    if stage not in sr:
                        continue
                    st.markdown(f"**{stage.replace('_',' ').title()}**")
                    st.json(sr[stage], expanded=False)
    with right:
        st.markdown("### Official sources")
        urls = list(dict.fromkeys((firm.get("sources") or []) + (product.get("sources") or [])))
        for url in urls:
            st.markdown(f"- {url}")
        st.markdown("### Household / firm limits")
        if firm.get("household_limits"):
            st.json(firm["household_limits"], expanded=True)
        else:
            st.caption("Not yet encoded in v3.")

    st.divider()
    st.caption(
        "v3 rule data is intentionally explicit about partial verification. A product marked RULES_PARTIAL_BEFORE_V4 is visible for research, "
        "but StarBase will not execute it in the trusted v4 engine until the missing numeric rules are filled and tested."
    )
