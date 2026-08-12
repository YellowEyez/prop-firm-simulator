# Project StarBase v4B Validation Report

## Automated tests

51 / 51 tests pass in the source tree.

New v4B tests verify:

- one-trade-per-session routing cap,
- unused signal preservation,
- MAE killing an eventual winner before recovery,
- LucidFlex EOD floor ratchet and +$100 lock,
- Tradeify Select evaluation no-lock behavior,
- Apex EOD evaluation platform variant requirement,
- per-contract commission accounting,
- TP/SL calculator isolation from historical execution,
- fleet capacity slot calculation from whole-session signal counts.

## Sydney_01 regression

Using the six previously audited Sydney 1NQ source segments:

- strict-valid trades: 4,342
- review: 96
- invalid: 27
- futures sessions: 326

LucidFlex 50K evaluation, one trade/account/session, $3.50 round-trip commission/contract:

- trades routed: 326
- signals left unused by one-account cap: 4,016
- commissions: $1,141.00
- starting balance: $50,000.00
- historical v4B ending balance if the account is intentionally allowed to continue after target: $60,004.00
- ending EOD MLL floor: $50,100.00
- MAE fallback count: 0
- v4B drawdown rule-path fidelity: production-grade for this selected product/stage

**Important:** the $60,004 figure is not an evaluation lifecycle result because v4B deliberately does not stop/transition the account at the pass point. v4D will add pass logic; v4E will initialize the fresh funded account.

## Capacity preview regression

For Sydney strict-valid signals with one trade/account/session:

- minimum slots for ~80% mechanical signal capture: 22
- minimum slots for ~90%: 32
- minimum slots for ~95%: 43

This is a capacity preview only. v5 will perform actual multi-account allocation and lifecycle constraints.

## Deployment note

The build environment used to construct StarBase does not include the Streamlit package, so a local Streamlit server launch cannot be performed here. `requirements.txt` retains `streamlit`, `pandas`, `numpy`, and `plotly`; Python compilation and deterministic engine tests are used as the local validation gate.
