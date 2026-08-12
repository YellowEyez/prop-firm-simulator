# StarBase v4A Validation Report

**Build:** Project StarBase v4A — Single-Account State + Accounting Ledger  
**Source baseline:** exact user-uploaded working `PROJECT_STARBASE_v0352_FULL_ROBUST_DEPLOY(1).zip`  
**Scope:** cumulative v3.5.2 + v4A only. No v4B drawdown enforcement or later lifecycle logic is included.

## Automated regression status
- 43 / 43 tests passing before packaging.
- Includes all prior TradingView audit, rulebook, research-integrity, and deployment-path tests.
- Includes new v4A account-state/accounting tests.

## v4A deterministic checks
- Fresh nominal account initialization.
- Fresh simulated-funded account does **not** inherit evaluation profit.
- Reference initial failure-floor arithmetic from the current rulebook.
- Gross P&L minus commission updates prop-account balance exactly.
- External account costs remain outside prop-account balance.
- Session P&L resets without erasing lifetime P&L.
- Account status changes are ledgered.
- Negative commission input is rejected.
- Undefined product-stage combinations are rejected.
- SHA-256 account-ledger chain validates.
- Deliberate ledger tampering is detected.
- Rule snapshot hash is stable and non-empty.

## Deployment/package checks
- `app.py` and `requirements.txt` remain at repository root.
- Required dependencies remain declared: Streamlit, pandas, numpy, Plotly.
- v4A account modules are present at repository root.
- Top-level Python files parse/compile.
- Final release is re-extracted into a clean directory and the complete test suite is rerun there.

## Intentional limitation
This environment does not have Streamlit installed, so a local Streamlit server is not launched here. The prior user-deployed v3.5.2 baseline is the known-good Streamlit base, and v4A is cumulative on that exact ZIP.
