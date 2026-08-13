# StarBase v5F Changelog — Golden Verification + Rule UI Clarity

## Scoreboard entering this release
- 27 / 60 deployment-certified through v5E.
- Step 26 Rule Truth certified by user on 2026-08-13.

## New in v5F
- Golden Verification Lab with 13 independent, hand-calculated single-account fixtures.
- Explicit regression coverage for Step 19 evaluation termination, Step 20 fresh-funded activation, Step 23 cross-account differentiation, and Step 27 golden single-account controls.
- Rule Truth page now visibly shows schema version.
- Added plain-English terminology expander for DLL, MLL, qualifying/benchmark days, qualifying dollars/day, trader split, and drawdown labels.
- Renamed compact Rule Truth matrix columns to match the UI language more closely.
- Added a clear caption explaining that detailed fields such as maximum contracts, DLL, buffers and access periods live under `Inspect one product/path`.
- Golden fixtures with advanced engine gaps are labeled CORE_ARITHMETIC_ONLY or VARIANT_SPECIFIC; passing those fixtures does not erase Rule Truth engine-pending warnings.

## Certification rule
If the deployed Golden Verification Lab shows 13 / 13 PASS, certify Steps 19, 20, 23 and 27. Score becomes 31 / 60.
