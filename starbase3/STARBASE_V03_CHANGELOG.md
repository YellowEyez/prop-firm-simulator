# Project StarBase v3 — Versioned Prop-Firm Rulebook

## Purpose
v3 adds the new source-cited prop-firm rule layer while leaving the v2 TradingView audit and the original legacy simulator intact.

## Important architecture change
Intraday-trailing funded products are **not globally excluded** from StarBase. The rulebook classifies them explicitly and supplies research presets:

- Research — all verified products
- EOD/static funded focus
- Intraday-funded research

This lets StarBase compare the economics of all popular account structures without mixing the drawdown mechanics together.

## Added
- `starbase_rules_v3.json`
- `starbase_rulebook.py`
- `starbase_rulebook_ui.py`
- `tests/test_starbase_rulebook.py`
- Rulebook workspace in `app.py`
- Stage-specific drawdown classification
- Official source URLs and verification dates
- Verification/readiness statuses so incomplete products cannot silently enter the trusted v4 engine

## Seed product families
- Apex EOD
- Apex Intraday Trailing
- LucidFlex
- LucidDirect
- LucidDaily
- Tradeify Select -> Flex
- Tradeify Lightning Funded
- FundedNext Futures Flex
- MFFU Flex 50K
- MFFU Rapid 50K
- Topstep Trading Combine -> XFA Standard
- Take Profit Trader Test -> PRO -> PRO+ (partial numeric; research only until completed)

## Not changed
- v2 TradingView audit behavior
- legacy `prop_firms.json`
- legacy `simulation.py`

## Next
v4 builds the trusted single-account state machine from the v3 schema: EOD/intraday MLL, MAE breach handling, DLL actions, evaluation pass state, funded fresh-start state, payout cycles, and deterministic tests.
