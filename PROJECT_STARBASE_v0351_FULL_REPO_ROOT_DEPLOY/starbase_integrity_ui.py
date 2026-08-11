from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from starbase_integrity import (
    EXECUTION_FIDELITY,
    STARBASE_VERSION,
    append_ledger_entry,
    assess_rule_coverage,
    build_research_bundle,
    build_run_manifest,
    independent_trial_max_abs_z,
    ledger_to_jsonl,
    parse_ledger_jsonl,
    sha256_bytes,
    sha256_file,
    validate_ledger_chain,
)
from starbase_rulebook import load_rulebook


def render_integrity_page():
    st.header("🧪 StarBase v3.5 — Research Integrity + Provenance")
    st.caption(
        "This workspace makes research reproducible before v4 begins trusted lifecycle execution. "
        "It records exact data hashes, rulebook hashes, execution fidelity, search breadth, and experiment lineage."
    )

    rulebook_path = Path(__file__).with_name("starbase_rules_v3.json")
    rulebook = load_rulebook(rulebook_path)
    rulebook_hash = sha256_file(rulebook_path)

    a, b, c, d = st.columns(4)
    a.metric("StarBase", STARBASE_VERSION)
    b.metric("Rulebook schema", rulebook["schema_version"])
    c.metric("Rulebook hash", rulebook_hash[:12])
    d.metric("Verified as of", rulebook["verified_as_of"])

    st.subheader("1. Execution fidelity")
    fidelity = st.selectbox(
        "How exact is this research result?",
        list(EXECUTION_FIDELITY.keys()),
        format_func=lambda k: f"{EXECUTION_FIDELITY[k]['label']} — {k}",
    )
    finfo = EXECUTION_FIDELITY[fidelity]
    if finfo["production_grade"]:
        st.success(f"{finfo['label']}: {finfo['description']}")
    else:
        st.warning(f"{finfo['label']}: {finfo['description']} This must not be presented as an exact production forecast.")

    st.subheader("2. Rule coverage + two-axis drawdown semantics")
    product_options = []
    labels = {}
    sizes_by_product = {}
    for firm in rulebook["firms"]:
        for product in firm.get("products", []):
            pid = product["product_id"]
            product_options.append(pid)
            labels[pid] = f"{firm['display_name']} — {product['display_name']}"
            sizes_by_product[pid] = sorted(int(x) for x in product["account_sizes"])
    pid = st.selectbox("Product", product_options, format_func=lambda k: labels[k])
    size = st.selectbox("Account size", sizes_by_product[pid])
    stage = st.selectbox("Stage", ["evaluation", "sim_funded", "live"])
    coverage = assess_rule_coverage(rulebook, pid, size, stage)
    grade = coverage["status"]
    if grade == "VERIFIED":
        st.success(f"Rule coverage: {grade}")
    elif grade == "NOT_MODELED":
        st.error(f"Rule coverage: {grade}")
    else:
        st.warning(f"Rule coverage: {grade}")
    st.json(coverage, expanded=False)
    st.caption(
        "Important: v3.5 separates the mechanism that updates a drawdown floor from the basis used to test a breach. "
        "Class defaults shown here are architecture defaults and must be confirmed per product before v4 production execution."
    )

    st.subheader("3. Reproducible run manifest")
    uploads = st.file_uploader(
        "Optional source files to fingerprint",
        type=None,
        accept_multiple_files=True,
        help="Files are hashed in memory. StarBase does not need to store them in the public repository.",
    )
    source_hashes = {f.name: sha256_bytes(f.getvalue()) for f in uploads or []}
    if source_hashes:
        st.dataframe(pd.DataFrame([{"File": k, "SHA-256": v} for k, v in source_hashes.items()]), hide_index=True, use_container_width=True)

    default_cfg = {
        "strategy_id": "example_strategy",
        "profile_id": "1NQ",
        "product_id": pid,
        "account_size": int(size),
        "stage": stage,
        "max_trades_per_account_per_futures_session": 1,
    }
    config_text = st.text_area("Run configuration (JSON)", json.dumps(default_cfg, indent=2), height=180)
    seed = st.number_input("Random seed (future Monte Carlo / bootstrap)", min_value=0, value=20260811, step=1)
    run_notes = st.text_area("Run notes", "")

    manifest = None
    try:
        config = json.loads(config_text)
        manifest = build_run_manifest(
            config=config,
            source_hashes=source_hashes,
            rulebook_hash=rulebook_hash,
            execution_fidelity=fidelity,
            rulebook_schema_version=rulebook["schema_version"],
            random_seed=int(seed),
            notes=run_notes,
        )
        st.code(manifest["run_id"], language=None)
        st.download_button(
            "Download RUN_MANIFEST.json",
            data=json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8"),
            file_name=f"{manifest['run_id']}_RUN_MANIFEST.json",
            mime="application/json",
        )
    except Exception as exc:
        st.error(f"Configuration error: {exc}")

    st.subheader("4. Research search-breadth warning")
    trial_count = st.number_input("Total candidate configurations searched", min_value=1, value=1, step=1)
    conf = st.select_slider("Familywise null reference", options=[0.90, 0.95, 0.99], value=0.95)
    z_ref = independent_trial_max_abs_z(int(trial_count), float(conf))
    st.metric("Independent-trial max-|Z| reference", f"{z_ref:.2f}")
    st.caption(
        "This is a warning threshold under independent standard-normal null trials, not proof of significance. "
        "Optimizer candidates are usually correlated, so v10 will also use chronological holdout and robustness gates."
    )

    st.subheader("5. Append-only experiment ledger")
    ledger_upload = st.file_uploader("Existing experiment ledger (optional JSONL)", type=["jsonl", "txt"], key="integrity_ledger")
    try:
        entries = parse_ledger_jsonl(ledger_upload.getvalue() if ledger_upload else None)
        validation = validate_ledger_chain(entries)
        if validation["valid"]:
            st.success(f"Ledger valid — {validation.get('entries', 0)} existing entries")
        else:
            st.error(f"Ledger chain invalid at entry {validation.get('index')}: {validation.get('reason')}")
    except Exception as exc:
        entries = []
        validation = {"valid": False}
        st.error(f"Could not read ledger: {exc}")

    col1, col2 = st.columns(2)
    with col1:
        experiment_name = st.text_input("Experiment name", "")
        objective = st.text_input("Primary objective", "")
        candidates = st.number_input("Candidates in this experiment", min_value=1, value=1, step=1)
    with col2:
        dev_metric = st.text_input("Development result", "")
        val_metric = st.text_input("Validation result", "")
        promoted = st.checkbox("Promoted", value=False)
    exp_notes = st.text_area("Experiment notes", "", key="exp_notes")

    updated_entries = entries
    if st.button("Append experiment entry", disabled=not (validation.get("valid") and experiment_name.strip())):
        payload = {
            "starbase_version": STARBASE_VERSION,
            "experiment_name": experiment_name.strip(),
            "run_id": manifest.get("run_id") if manifest else None,
            "execution_fidelity": fidelity,
            "objective": objective,
            "candidates_tested": int(candidates),
            "development_result": dev_metric,
            "validation_result": val_metric,
            "promoted": bool(promoted),
            "notes": exp_notes,
        }
        updated_entries = append_ledger_entry(entries, payload)
        st.session_state["v35_updated_ledger"] = updated_entries
        st.success(f"Added entry #{len(updated_entries)}")

    if st.session_state.get("v35_updated_ledger") is not None:
        updated_entries = st.session_state["v35_updated_ledger"]
    if updated_entries:
        st.download_button(
            "Download updated EXPERIMENT_LEDGER.jsonl",
            data=ledger_to_jsonl(updated_entries),
            file_name="EXPERIMENT_LEDGER.jsonl",
            mime="application/x-ndjson",
        )

    if manifest is not None:
        bundle = build_research_bundle(manifest, updated_entries)
        st.download_button(
            "Download reproducibility bundle",
            data=bundle,
            file_name=f"{manifest['run_id']}_RESEARCH_BUNDLE.zip",
            mime="application/zip",
        )

    st.info(
        "v3.5 deliberately does not run the prop lifecycle yet. It makes the next engine auditable first: exact source hashes, rule coverage, "
        "execution fidelity, deterministic seeds, and immutable experiment lineage are now available before v4 changes account balances."
    )
