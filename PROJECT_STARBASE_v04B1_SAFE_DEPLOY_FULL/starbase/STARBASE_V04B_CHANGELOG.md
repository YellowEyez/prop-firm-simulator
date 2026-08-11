# Project StarBase v4B — Historical Single-Account Trader

## Purpose

v4A established auditable accounting. v4B is the first StarBase release that consumes audited TradingView trade history and actually routes it through a prop-account risk path.

## Added

- `starbase_historical_runner.py`
- `starbase_historical_runner_ui.py`
- `tests/test_starbase_historical_runner.py`
- New Streamlit workspace: **Historical Single-Account Trader (v4B)**

## Trusted mechanics introduced

1. Chronological routing of audited TradingView trades.
2. Configurable maximum trades per account per 6 PM ET futures session.
3. Per-contract round-trip firm commissions.
4. Hard maximum-loss breach detection using TradingView MAE against the established floor.
5. EOD trailing-floor ratcheting after session close.
6. Product-specific floor-lock semantics for currently verified core products.
7. Basic soft DLL pause behavior with explicit research-grade warning where exact liquidation fill is unavailable.
8. Explicit research-grade handling for intraday-trailing products because MFE/MAE alone do not reveal path order.
9. Evaluation target and consistency progress diagnostics without prematurely changing account stage.
10. Fleet-capacity preview based on actual signals per futures session.
11. Downloadable reproducibility bundle for deeper ChatGPT/offline analysis.

## Current drawdown semantics references

The v4B product-specific policies were checked against current official rule pages on 2026-08-11. Important references include:

- https://support.lucidtrading.com/en/articles/12945815-lucidflex-drawdown
- https://support.lucidtrading.com/en/articles/12945805-lucidflex-consistency-percentage
- https://help.tradeify.co/en/articles/10495897-rules-trailing-max-drawdowns
- https://help.tradeify.co/en/articles/10468320-rules-consistency-rule
- https://helpfutures.fundednext.com/en/articles/14298225-what-is-the-maximum-loss-limit-at-fundednext-futures-and-how-does-it-work
- https://helpfutures.fundednext.com/en/articles/14878851-is-there-any-consistency-rule-in-the-fundednext-futures-flex-challenge-and-fundednext-account
- https://apextraderfunding.com/help-center/eod-trailing-drawdown-accounts/eod-drawdown-explained/
- https://apextraderfunding.com/help-center/additional-helpful-items/daily-loss-limit-explained/

## Intentional boundaries

v4B does **not** yet:

- automatically pass an evaluation,
- initialize a new funded account after a pass,
- enforce funded payout eligibility,
- deduct payouts,
- transition to live,
- replace failed accounts,
- route one strategy across multiple accounts.

Those remain cumulative v4D-v5 steps so each state transition can be independently regression-tested.
