"""Streamlit UI for the StarBase Strategy Dataset Library."""
from __future__ import annotations

import streamlit as st

from tradingview_audit import AuditPolicy, audit_tradingview_files
from starbase_fees import infer_instrument_from_profile, instrument_spec
from starbase_dataset_library import (
    delete_dataset,
    export_dataset_vault,
    import_dataset_vault,
    infer_chart_interval,
    infer_year_range,
    list_datasets,
    load_dataset_sources,
    save_dataset,
    suggested_dataset_name,
)


def _dataset_label(d: dict) -> str:
    return f"{d.get('display_name','Unnamed')}  |  {d.get('instrument_root','?')} · {d.get('profile_id','?')}  |  {d.get('audit_summary',{}).get('strict_valid_trades',0):,} strict trades"


def render_dataset_library_page() -> None:
    st.header("🗃️ Strategy Dataset Library (v5F)")
    st.caption("Upload a TradingView strategy once, give it a durable identity/notes, and reuse it throughout StarBase without repeatedly selecting every CSV segment.")
    st.warning("Streamlit Community Cloud runtime storage is not guaranteed to survive an app redeploy/restart. Use the **Dataset Vault ZIP** below as your portable backup. After a redeploy, restoring the whole library takes one ZIP upload instead of re-uploading every CSV segment.")

    tabs = st.tabs(["Saved strategies", "Add TradingView dataset", "Vault backup / restore"])

    with tabs[0]:
        datasets = list_datasets()
        if not datasets:
            st.info("No saved strategy datasets yet. Use **Add TradingView dataset**.")
        else:
            labels = [_dataset_label(d) for d in datasets]
            selected_label = st.selectbox("Saved dataset", labels, key="v5c_lib_select")
            d = datasets[labels.index(selected_label)]
            a = d.get("audit_summary", {})
            c1,c2,c3,c4,c5,c6 = st.columns(6)
            c1.metric("Strict valid", f"{a.get('strict_valid_trades',0):,}")
            c2.metric("Review", f"{a.get('review_trades',0):,}")
            c3.metric("Invalid", f"{a.get('invalid_trades',0):,}")
            c4.metric("Sessions", f"{a.get('active_futures_sessions',0):,}")
            c5.metric("Chart interval", d.get("chart_interval") or "Unknown")
            yr = str(d.get("start_year") or "?") if d.get("start_year") == d.get("end_year") else f"{d.get('start_year','?')}-{d.get('end_year','?')}"
            c6.metric("Years", yr)
            st.markdown(f"**Strategy ID:** `{d.get('strategy_id')}`  \n**Instrument:** `{d.get('instrument_root','Unknown')}`  \n**Profile:** `{d.get('profile_id')}`  \n**Dataset ID:** `{d.get('dataset_id')}`")
            conf = float(d.get("chart_interval_detection_confidence") or 0)
            detected = d.get("chart_interval_detected", "Unknown")
            if d.get("chart_interval") != detected:
                st.info(f"Chart interval was manually saved as **{d.get('chart_interval')}**. StarBase's duration-bars detector estimated **{detected}** ({conf:.0%} match).")
            elif d.get("chart_interval_detection_ambiguous"):
                st.warning(f"Chart interval estimate **{detected}** is not fully certain ({conf:.0%} match). TradingView's export does not carry an explicit chart-timeframe field, so verify this label if it matters.")
            else:
                st.success(f"Likely chart interval: **{detected}** ({conf:.0%} of usable duration/bar samples match).")
            if d.get("notes"):
                st.markdown("**Notes**")
                st.write(d["notes"])
            with st.expander("Source files / hashes"):
                st.json(d.get("files", []))

            confirm = st.checkbox("I understand deletion removes this dataset from the current StarBase runtime library", key=f"del_confirm_{d['dataset_id']}")
            if st.button("🗑️ Remove selected dataset", disabled=not confirm, key=f"delete_{d['dataset_id']}"):
                delete_dataset(d["dataset_id"])
                st.success("Dataset removed from the runtime library. Export a new vault if you want your backup to reflect the deletion.")
                st.rerun()

    with tabs[1]:
        files = st.file_uploader(
            "Upload all TradingView List of Trades CSV segments for ONE exact strategy/profile",
            type=["csv"], accept_multiple_files=True, key="v5c_add_files",
            help="Example: all Sydney segments 01-06 together. The saved dataset then becomes one selectable StarBase strategy asset.",
        )
        m1,m2,m3 = st.columns(3)
        strategy_id = m1.text_input("Strategy ID", value="Sydney", key="v5c_add_strategy")
        profile_id = m2.text_input("Exact profile ID", value="1NQ", key="v5c_add_profile")
        inferred = infer_instrument_from_profile(profile_id) or "NQ"
        instrument = m3.selectbox("Futures instrument", ["NQ","MNQ","ES","MES","OTHER"], index=["NQ","MNQ","ES","MES","OTHER"].index(inferred if inferred in {"NQ","MNQ","ES","MES"} else "OTHER"), key="v5d_add_instrument")
        spec = instrument_spec(instrument) if instrument != "OTHER" else {}
        default_point = float(spec.get("point_value", 20.0))
        point_value = float(st.number_input("Point value / contract ($)", min_value=0.01, value=default_point, step=0.25, key=f"v5d_add_point_{instrument}", help="Auto-filled from the selected futures contract. Change only if you are deliberately using another contract specification."))
        if files:
            try:
                audit = audit_tradingview_files(files, strategy_id=strategy_id, profile_id=profile_id, policy=AuditPolicy(point_value_per_contract=point_value))
                interval = infer_chart_interval(audit.ledger)
                y0,y1 = infer_year_range(audit.ledger)
                suggestion = suggested_dataset_name(strategy_id, interval.label, y0, y1)
                st.success(f"Parsed {audit.summary['strict_valid_trades']:,} strict-valid trades across {audit.summary['active_futures_sessions']:,} futures sessions.")
                i1,i2,i3 = st.columns(3)
                i1.metric("Detected interval", interval.label)
                i2.metric("Detector match", f"{interval.confidence:.0%}")
                i3.metric("Years", str(y0) if y0 == y1 else f"{y0}-{y1}")
                if interval.ambiguous:
                    st.warning("The chart interval estimate is ambiguous. TradingView does not export the chart timeframe directly; StarBase infers it from elapsed trade time ÷ Duration (bars). Confirm or override it below.")
                display_name = st.text_input("Saved dataset name", value=suggestion, key="v5c_add_name", help="Example: Sydney_10s_2025-2026")
                chart_interval = st.text_input("Chart interval label", value=interval.label, key="v5c_add_interval", help="You may override this if you know the true chart timeframe.")
                notes = st.text_area("Strategy notes", value="", height=130, key="v5c_add_notes", placeholder="Example: Sydney baseline; exact 1NQ profile; TP/SL notes; intended role; known experiments...")
                if st.button("💾 Save strategy dataset to StarBase library", type="primary", use_container_width=True, key="v5c_save"):
                    saved = save_dataset(files, display_name=display_name, strategy_id=strategy_id, profile_id=profile_id, notes=notes, point_value_per_contract=point_value, chart_interval_override=chart_interval, instrument_root=instrument)
                    st.success(f"Saved **{saved['display_name']}**. It can now be selected from Josh Fleet Economics without re-uploading these CSVs.")
                    st.rerun()
            except Exception as exc:
                st.error(f"Dataset audit/save failed: {exc}")
        else:
            st.caption("Select all CSV segments for one exact TradingView profile. Multiple-file upload is supported here.")

    with tabs[2]:
        datasets = list_datasets()
        st.metric("Datasets in runtime library", len(datasets))
        vault = export_dataset_vault()
        st.download_button("⬇️ Download complete StarBase Dataset Vault ZIP", vault, "StarBase_Dataset_Vault.zip", "application/zip", use_container_width=True)
        st.caption("Keep this vault somewhere safe. It contains the saved raw CSV segments plus names, notes, hashes, timeframe inference and audit metadata for every dataset in the current library.")
        incoming = st.file_uploader("Restore a StarBase Dataset Vault ZIP", type=["zip"], accept_multiple_files=False, key="v5c_vault_import")
        replace = st.checkbox("Replace datasets that already exist", value=False, key="v5c_vault_replace")
        if incoming is not None and st.button("Restore dataset vault", key="v5c_vault_restore"):
            try:
                result = import_dataset_vault(incoming.getvalue(), replace_existing=replace)
                st.success(f"Restored {len(result['imported'])} dataset(s); skipped {len(result['skipped'])}; library now has {result['total_library']} dataset(s).")
                st.rerun()
            except Exception as exc:
                st.error(f"Vault restore failed: {exc}")


def select_dataset_or_upload(*, key_prefix: str, default_strategy: str = "Sydney_01", default_profile: str = "1NQ"):
    """Shared source selector for simulation pages.

    Returns (files, strategy_id, profile_id, dataset_manifest_or_none).
    """
    datasets = list_datasets()
    options = []
    if datasets:
        options.append("Saved Strategy Dataset")
    options.append("Upload CSVs for this run")
    mode = st.radio("Strategy data source", options, horizontal=True, key=f"{key_prefix}_source_mode")

    if mode == "Saved Strategy Dataset":
        labels = [_dataset_label(d) for d in datasets]
        selected_label = st.selectbox("Saved strategy dataset", labels, key=f"{key_prefix}_dataset")
        d = datasets[labels.index(selected_label)]
        files = load_dataset_sources(d["dataset_id"])
        st.success(f"Using saved dataset **{d['display_name']}** · **{d.get('instrument_root','Unknown')}** · {d.get('chart_interval','Unknown')} · {d.get('start_year','?')}-{d.get('end_year','?')}")
        if d.get("notes"):
            with st.expander("Saved strategy notes", expanded=False):
                st.write(d["notes"])
        return files, d.get("strategy_id") or default_strategy, d.get("profile_id") or default_profile, d

    files = st.file_uploader("TradingView List of Trades CSV segments", type=["csv"], accept_multiple_files=True, key=f"{key_prefix}_files")
    c1,c2 = st.columns(2)
    strategy = c1.text_input("Strategy ID", value=default_strategy, key=f"{key_prefix}_strategy")
    profile = c2.text_input("Exact profile ID", value=default_profile, key=f"{key_prefix}_profile")
    if files:
        st.caption("Tip: save this batch in **Strategy Dataset Library** if you want to reuse it without selecting every CSV again.")
    return files, strategy, profile, None
