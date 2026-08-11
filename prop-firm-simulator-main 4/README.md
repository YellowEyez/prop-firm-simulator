# Project StarBase v2

> **Current trusted scope:** TradingView Import + Audit. The original simulator is preserved as `Legacy Simulator (reference only)` until its prop-firm lifecycle engine is rewritten in later StarBase versions.

See `STARBASE_V02_CHANGELOG.md` for the v2 boundary and `tests/test_tradingview_audit.py` for deterministic source-integrity tests.

---

# prop-firm-simulator
## Project StarBase v3.5 — Research Integrity + Provenance

v3.5 adds a reproducibility layer before the trusted v4 lifecycle engine changes any account balance. The new workspace provides:

- execution-fidelity labels (`EXACT_PROFILE`, `DERIVED_SHADOW`, `SYNTHETIC_GEOMETRY`, `UNRESOLVED`),
- deterministic run IDs from config + source hashes + rulebook hash,
- downloadable run manifests and reproducibility bundles,
- explicit rule-coverage grades,
- two-axis drawdown semantics (floor update basis vs breach-test basis),
- append-only hash-chained experiment ledgers,
- research search-breadth / independent-null max-|Z| warning thresholds,
- deterministic whole-futures-session bootstrap foundations for later Monte Carlo.

StarBase does not persist private TradingView datasets in the public repository. Files uploaded in the UI can be fingerprinted in memory and their hashes recorded in a run manifest.
