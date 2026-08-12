# Project StarBase v5A — Josh Single-Product Funded Fleet

## Purpose
Move the primary viewpoint from one prop account to the strategy household while keeping each individual funded account independently auditable.

## Added
- Josh Household / Single-Product Funded Fleet workspace.
- Raw-strategy mathematical baseline using every eligible signal.
- Persistent multi-account funded fleet for one selected product/size.
- Configurable max trades/account/futures-session (default 1).
- Fixed Fleet capacity mode.
- Force 100% Signal Capture capacity mode, which provisions fresh funded accounts on demand and intentionally overrides account-count limits for research.
- Household session ledger aggregating all routed trades/accounts in each futures session.
- Individual account inventory and failure/payout state.
- Fleet payout ledger.
- Full trade-to-account routing ledger.
- End-of-data active funded account and payout-availability inventory.
- ChatGPT-oriented fleet result ZIP.

## Accounting clarity fix
v4C session rows now separate:
- source trade net P/L,
- account realized P/L until exit/breach,
- pre-payout account balance,
- gross payout deduction,
- payout cash sent to trader,
- post-payout ending balance.

Therefore a positive trading session followed by a payout can no longer look like an unexplained account-balance loss.

## Explicit limitation
v5A does NOT include account acquisition economics yet. Evaluation purchases, resets, activation fees, direct-funded purchase costs, subscriptions, refunds/promotions, and other business costs are Step 24/25. Payout cash must not be interpreted as final household profit until those steps are complete.
