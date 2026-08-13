from __future__ import annotations

import pandas as pd
import streamlit as st

from starbase_rulebook import (
    filter_rows,
    flatten_rulebook,
    load_rulebook,
    product_details,
    rulebook_freshness,
)
from starbase_rule_semantics import rule_truth_matrix

DD_LABELS = {
    "EOD_TRAILING": "🟦 EOD trailing",
    "INTRADAY_TRAILING": "🟥 Intraday trailing",
    "STATIC": "🟩 Static",
    "NONE": "⬜ None",
    "SELECTABLE_EOD_OR_INTRADAY": "🟪 Selectable EOD / intraday",
    None: "—",
}
GRADE_LABELS = {
    "PRODUCTION_READY": "🟢 Production-ready core",
    "RULES_VERIFIED_ENGINE_PENDING": "🟡 Rules verified / engine pending",
    "VARIANT_SELECTION_REQUIRED": "🟣 Variant selection required",
    "RESEARCH_ONLY": "🟠 Research only",
    "NOT_MODELED": "🔴 Not modeled",
}


def _fmt_money(v):
    if v is None or pd.isna(v):
        return "—"
    return f"${float(v):,.0f}"


def render_rulebook_page():
    data = load_rulebook()
    rows = flatten_rulebook(data)
    fresh = rulebook_freshness(data)

    st.header("📚 StarBase v5F — Current Prop-Firm Rule Truth Layer")
    st.caption(
        "Official rules and simulation coverage are deliberately separate. A rule can be verified from the firm while the dedicated StarBase lifecycle handler is still pending."
    )

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Rulebook schema", data.get("schema_version", "—"))
    c2.metric("Verified as of", data["verified_as_of"])
    c3.metric("Freshness", fresh["grade"])
    c4.metric("Firms", len(data["firms"]))
    c5.metric("Product paths", sum(len(f.get("products", [])) for f in data["firms"]))
    c6.metric("Size variants", len(rows))

    if fresh["grade"] == "STALE":
        st.error(f"Rule snapshot is {fresh['age_days']} days old. Re-verify official firm rules before production research.")
    elif fresh["grade"] == "AGING":
        st.warning(f"Rule snapshot is {fresh['age_days']} days old and approaching the 30-day stale threshold.")
    else:
        st.success("Rule snapshot is fresh. Current verification date: 2026-08-12.")

    with st.expander("Terminology used on this page", expanded=False):
        st.markdown("""
- **DLL = Daily Loss Limit.** A daily/session loss threshold. Depending on the product it may pause trading rather than permanently fail the account.
- **MLL = Maximum Loss Limit.** The account failure floor / maximum permitted drawdown.
- **Qual Days = Qualifying or Benchmark Days.** The number of qualifying profit days required for a payout.
- **Qual $/Day = Qualifying profit required per day.** For example, 5 days × $200 means five qualifying days with at least $200 profit each.
- **Split = Trader payout/reward share.** A 95% split means the trader receives 95% of the approved gross payout before any separately modeled processing fee.
- **Eval DD / Funded DD = Evaluation/Funded Drawdown family.** EOD = end-of-day trailing; Intraday = the threshold can move intraday; Static = it does not trail.
""")

    with st.expander("How to read Rule Truth grades", expanded=False):
        for k, v in GRADE_LABELS.items():
            st.markdown(f"**{v}** — `{k}`")
        st.caption("Only production-ready stages should enter trusted rankings by default. Engine-pending and research-only paths remain visible for study, but they are not silently scored as equivalent.")

    with st.sidebar:
        st.subheader("📚 Rule Truth Filters")
        preset = st.selectbox(
            "Research preset",
            list(data["policy_presets"].keys()),
            format_func=lambda k: data["policy_presets"][k]["label"],
            key="rulebook_preset_v5e",
        )
        preset_cfg = data["policy_presets"][preset]
        st.caption(preset_cfg["description"])
        firm_options = {f["firm_id"]: f["display_name"] for f in data["firms"]}
        selected_firms = st.multiselect("Firms", list(firm_options), format_func=lambda k: firm_options[k])
        sizes = sorted({r.account_size for r in rows})
        selected_sizes = st.multiselect("Account sizes", sizes, default=sizes)
        ev_cons = sorted({r.evaluation_consistency for r in rows})
        fd_cons = sorted({r.funded_consistency for r in rows})
        selected_ev_cons = st.multiselect("Evaluation consistency", ev_cons)
        selected_fd_cons = st.multiselect("Funded consistency", fd_cons)
        grade_options = list(GRADE_LABELS)
        selected_grades = st.multiselect("Rule Truth grade", grade_options, format_func=lambda x: GRADE_LABELS[x])
        rankable_only = st.checkbox("Trusted/rankable stages only", value=False)

    filtered = filter_rows(
        rows,
        funded_drawdowns=preset_cfg["allowed_funded_drawdowns"],
        firms=selected_firms or None,
        sizes=selected_sizes or None,
        evaluation_consistency=selected_ev_cons or None,
        funded_consistency=selected_fd_cons or None,
        rule_grades=selected_grades or None,
        rankable_only=rankable_only,
        active_only=True,
    )

    table = pd.DataFrame([{
        "Firm": r.firm,
        "Product / Path": r.product,
        "Size": f"${r.account_size/1000:.0f}K",
        "Acquisition": r.acquisition_model,
        "Eval Consistency": r.evaluation_consistency,
        "Funded Consistency": r.funded_consistency,
        "Eval DD": DD_LABELS.get(r.evaluation_drawdown, r.evaluation_drawdown or "—"),
        "Funded DD": DD_LABELS.get(r.funded_drawdown, r.funded_drawdown or "—"),
        "Eval Target": _fmt_money(r.profit_target),
        "Funded MLL (Max Loss)": _fmt_money(r.funded_max_loss),
        "Qualifying / Benchmark Days": r.payout_qualifying_days if r.payout_qualifying_days is not None else "—",
        "Qualifying $ / Day": _fmt_money(r.payout_qualifying_profit),
        "Trader Split": f"{r.payout_split_percent:.0f}%" if r.payout_split_percent is not None else "—",
        "Eval Truth": GRADE_LABELS.get(r.evaluation_rule_grade, r.evaluation_rule_grade),
        "Funded Truth": GRADE_LABELS.get(r.funded_rule_grade, r.funded_rule_grade),
    } for r in filtered])

    st.subheader("Current Rule Truth matrix")
    st.dataframe(table, use_container_width=True, hide_index=True)

    st.subheader("Stage simulation coverage")
    tm = pd.DataFrame(rule_truth_matrix(data))
    tm_show = tm[["firm", "product", "stage", "verified_date", "grade", "rankable"]].copy()
    tm_show["grade"] = tm_show["grade"].map(lambda x: GRADE_LABELS.get(x, x))
    st.dataframe(tm_show, use_container_width=True, hide_index=True)

    product_ids = []
    product_labels = {}
    for firm in data["firms"]:
        for product in firm.get("products", []):
            product_ids.append(product["product_id"])
            product_labels[product["product_id"]] = f"{firm['display_name']} — {product['display_name']}"

    st.subheader("Inspect one product/path — detailed rules live here")
    st.caption("The matrix above is intentionally compact. Use this section when you need fields such as Daily Loss Limit (DLL), maximum contracts, access period, payout minimums, buffers, or other stage-specific details.")
    pid = st.selectbox("Product family", product_ids, format_func=lambda x: product_labels[x], key="v5e_product_inspector")
    details = product_details(data, pid)
    firm = details["firm"]
    product = details["product"]

    left, right = st.columns([2, 1])
    with left:
        st.markdown(f"### {product['display_name']}")
        st.write(f"**Status:** {product['status']}  |  **Verified:** {product['verified_date']}  |  **Verification:** {product.get('verification_status','UNKNOWN')}")
        st.write(f"**Acquisition:** {product.get('acquisition_model','UNKNOWN')}  |  **Engine readiness:** {product.get('simulation_readiness','UNKNOWN')}")
        rt = product.get("rule_truth") or {}
        if rt:
            with st.expander("Rule Truth / unresolved behavior", expanded=True):
                for stage in ("evaluation", "sim_funded", "live"):
                    t = rt.get(stage) or {}
                    st.markdown(f"**{stage.replace('_',' ').title()}:** {GRADE_LABELS.get(t.get('grade'), t.get('grade','—'))}")
                    for reason in t.get("unmodeled_reasons") or []:
                        st.caption(f"• {reason}")
        if product.get("notes"):
            st.warning(product["notes"])
        for size_s, sr in sorted(product["account_sizes"].items(), key=lambda kv: int(kv[0])):
            with st.expander(f"${int(size_s):,} current rules", expanded=False):
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
        st.markdown("### Firm limits already recorded")
        if firm.get("household_limits"):
            st.json(firm["household_limits"], expanded=True)
        else:
            st.caption("No firm-level limit has been encoded yet.")

    st.divider()
    st.caption(
        "Step 26 Rule Truth principle: official semantics can be VERIFIED while simulation remains ENGINE PENDING. "
        "StarBase must never turn an unimplemented rule into a generic payout/drawdown assumption just to fill a table."
    )
