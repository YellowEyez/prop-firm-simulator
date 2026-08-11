# Project StarBase v3.5 Changelog

## Purpose
Research Integrity + Provenance foundation before the trusted v4 single-account lifecycle engine.

## Added
- `starbase_integrity.py`
  - execution fidelity taxonomy: EXACT_PROFILE / DERIVED_SHADOW / SYNTHETIC_GEOMETRY / UNRESOLVED
  - deterministic run IDs from config + source hashes + rulebook hash
  - run manifests and reproducibility bundles
  - rule coverage assessment
  - separate drawdown floor-update and breach-test semantics
  - append-only SHA-256 hash-chained experiment ledger
  - independent-trial max-|Z| search-breadth reference
  - deterministic whole-futures-session bootstrap primitive
- `starbase_integrity_ui.py`
  - new Streamlit workspace for provenance, search breadth, rule coverage, run manifests, and experiment ledgers
- `tests/test_starbase_integrity.py`
  - 10 deterministic tests

## Changed
- `app.py`: adds `Research Integrity + Provenance (v3.5)` workspace.
- `README.md`: documents v3.5.

## Intentionally unchanged
- `simulation.py` legacy lifecycle engine
- `prop_firms.json` legacy rule file
- `starbase_rules_v3.json` v3 rule snapshot
- TradingView v2 importer/audit semantics

## Important design note
v3.5 does not claim that the drawdown class alone proves every firm's exact breach mechanics. Class defaults are explicitly marked as requiring product-level confirmation before v4 trusted execution.
