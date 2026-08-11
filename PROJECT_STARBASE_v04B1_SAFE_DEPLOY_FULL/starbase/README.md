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

---

# Project StarBase v4A — Trusted Single-Account State + Ledger

v4A adds the first trusted lifecycle substrate: a single account object and an immutable, hash-chained accounting ledger. It deliberately stops before drawdown/pass/payout enforcement so those mechanics can be added and regression-tested cumulatively in v4B-v4H.

Use the **Single-Account State + Ledger (v4A)** workspace to initialize one account from the v3 rulebook and inspect how prop-account balance, firm commissions, sessions, account status, and external business cash are recorded.

---

# Project StarBase v4B — Historical Single-Account Trader

v4B is the first cumulative StarBase build that routes real audited TradingView trades through a prop account chronologically.

The **Historical Single-Account Trader (v4B)** workspace now supports:

- multiple TradingView CSV segments,
- strict-valid vs optional REVIEW rows,
- configurable `max trades / account / futures session` (default 1),
- per-contract round-trip firm commission,
- MAE-aware hard drawdown breach detection,
- EOD floor ratcheting and product-specific lock semantics where verified,
- research-grade intraday-trailing path assumptions when MFE/MAE ordering is unknowable,
- basic soft-DLL session pauses,
- evaluation target/consistency progress display,
- fleet-capacity preview for 80% / 90% / 95% signal capture,
- TP/SL break-even and theoretical payoff diagnostics that never mutate historical executions,
- downloadable run bundles containing summary, config, rule snapshot, trade routing and session ledger.

**Boundary:** v4B trades one account but deliberately does not yet auto-pass evaluations, activate a fresh funded account, or request payouts. Those transitions remain the cumulative v4D-v4F steps. v5 will distribute the same signal stream across many accounts.


# Project StarBase v4B.1 — Deployment Hotfix + Fleet Semantics Lock

v4B.1 keeps the v4B historical single-account trading logic intact and fixes the supported deployment layout. The canonical Streamlit folder is `starbase` and the main module is `starbase/app.py`. Avoid spaces and parentheses in the deployed app-directory name.

The controlling fleet/optimizer design requirements are now preserved in `STARBASE_FLEET_AND_OPTIMIZER_REQUIREMENTS.md`. Most importantly, the future `1 trade per account per futures session` rule applies independently to every account. Thirty valid signals can therefore feed up to thirty eligible accounts in one session when account inventory and firm rules allow it.
