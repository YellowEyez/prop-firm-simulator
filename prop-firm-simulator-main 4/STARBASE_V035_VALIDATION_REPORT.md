# StarBase v3.5 Validation Report

## Result
PASS

## Automated tests
- TradingView Import + Audit: 9 passing
- Versioned Rulebook: 9 passing
- Research Integrity + Provenance: 10 passing
- Total: 28 passing

## v3.5 integrity tests cover
- deterministic run IDs
- source-hash sensitivity
- exact-profile production-grade fidelity flag
- separate drawdown floor-update and breach-test axes
- verified rule coverage
- missing-stage detection
- search-breadth reference increases with trial count
- deterministic whole-session bootstrap
- valid append-only hash chain
- tamper detection

## Legacy preservation
The v3.5 build intentionally does not change the legacy lifecycle engine or legacy rule file. v4 remains the point at which trusted account-state execution begins.

## UI note
The project declares Streamlit in `requirements.txt`. This validation environment does not launch a Streamlit server, so deployment UI verification remains a post-push check on Streamlit Cloud.
