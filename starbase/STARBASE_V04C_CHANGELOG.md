# Project StarBase v4C — Lifecycle-Correct Trader + Account Comparison

## Why this release exists
v4B intentionally kept trading evaluation accounts after targets were reached and had no funded payout engine. That made materially different prop products look too similar because the dominant output was simply a long-running strategy equity curve.

v4C fixes that structural limitation while remaining a one-account / one-lineage verification layer.

## Added
- Evaluation-only research mode that stops at PASS / FAIL / expiry when encoded.
- Funded-only research mode that assumes the funded account already exists.
- Evaluation -> Funded single-lineage mode using only sessions after the evaluation passes.
- Rule-based payout engine for current core products: LucidFlex, LucidDirect, Tradeify Select Flex, FundedNext Futures Flex, MFFU Flex 50K, Apex EOD PA.
- Payout strategies: MAX_ALLOWED, MINIMUM_ONLY, NONE.
- Trader wallet cash separated from remaining simulated account value.
- End-of-data unpaid payout availability preserved separately.
- Payout ledger downloads.
- Same-profile Account Comparison Lab.
- Optional reward-share override for product-specific promotions/add-ons.
- Apex 30-calendar-day evaluation access field in the versioned rulebook.
- Correct MFFU Flex funded $0 P&L starting balance handling and $100 MLL reset after first payout.
- Fleet requirements expanded with Fixed / Rule-Constrained / Auto-Provision / Target-Capture / Force-100%-Capture research modes.
- Linked-account / compatibility graph requirement added for v5+.

## Still intentionally later
- Multi-account fleet fan-out.
- Passed-evaluation bank and replenishment factory.
- Household/multi-firm caps and linked-account constraints.
- Full live transition / live payout engine.
- Account acquisition economics and recurring replacement costs in the production fleet.
- Exact 1NQ/2NQ/3NQ state-dependent profile switching.
- Rolling-start pass probability and full optimizer.

v4C is designed to prove that one exact strategy profile behaves differently when the actual account lifecycle rules differ.
