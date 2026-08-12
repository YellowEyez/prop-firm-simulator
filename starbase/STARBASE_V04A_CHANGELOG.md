# Project StarBase v4A — Single-Account State + Accounting Ledger

## Purpose
v4A begins the trusted lifecycle engine with the smallest auditable unit: one account and one accounting ledger.

## Added
- `starbase_account.py`: immutable account state + hash-chained accounting ledger.
- `starbase_account_ui.py`: Streamlit workspace for account initialization and manual accounting verification.
- `tests/test_starbase_account.py`: deterministic v4A regression tests.
- New app workspace: **Single-Account State + Ledger (v4A)**.

## Accounting separation
v4A explicitly separates:
- **prop-account balance**: trading P&L minus firm commissions,
- **external business cash**: evaluation/activation/reset costs and, later, payouts.

An evaluation purchase therefore does not incorrectly reduce the nominal prop-account balance.

## Rule provenance
Each account snapshots:
- firm/product/size/stage,
- rulebook schema + verified-as-of date,
- rule coverage status,
- drawdown class,
- reference max loss / initial floor,
- SHA-256 of the exact stage-rule payload.

## Deliberate v4A boundary
v4A does **not** enforce:
- drawdown breaches or ratchets,
- MAE account death,
- DLL behavior,
- evaluation target / consistency / min-days pass logic,
- funded activation,
- payout eligibility or withdrawals.

Those remain later cumulative v4 stages so no partially implemented rule can masquerade as a trusted result.
