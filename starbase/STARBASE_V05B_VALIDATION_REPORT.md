# Project StarBase v5B Validation Report

Validation date: 2026-08-12

## Automated regression
- **75 / 75 tests passing**
- All Python modules compile.
- Deployment sanity check passes with the stable `starbase/app.py` structure.

New regression coverage proves:
1. manual effective funded acquisition cost is charged to every provisioned account;
2. unknown/pre-owned funded inventory does not produce a false final-business-net figure;
3. Maintain-N replaces a failed funded account and charges the replacement;
4. active accounts separate claimable-now from accrued-but-blocked payout capacity;
5. STRICT data mode is explicit;
6. confirmed residual simulated value on failed accounts is preserved in the forfeiture ledger;
7. official pricing reference file loads and retains source provenance.

## Strict Sydney 1NQ regression
Input: six Sydney TradingView files, REVIEW OFF, LucidFlex50 funded, 1 trade/account/futures-session, $3.50 round-trip commission/contract, MAX_ALLOWED payouts.

Audit control:
- Strict valid: 4,342
- REVIEW: 96
- Invalid: 27
- Futures sessions: 326
- Raw gross source P/L: $22,230.00
- Raw commission drag: $15,197.00
- Raw net after commission: $7,033.00

### Force 100% capture, unknown/pre-owned funded cost
- Signals routed: 4,342 / 4,342
- Accounts provisioned: 295
- Failed accounts: 253
- Payout-cycle-complete accounts: 5
- Active funded at end: 37
- Completed payouts: 229
- Payout cash: $138,405.628125
- Final household net: intentionally unavailable because acquisition cost is unknown
- Accrued-but-blocked estimated trader cash at end: $5,486.259375
- Active simulated profit inventory: $7,323.1875

### Force 100% capture, manual effective funded cost = $100/account
- Same trading/account path as above
- External funded-account costs: $29,500.00
- Realized household cash after modeled external cost: $108,905.628125
- Active funded cost basis at end: $3,700.00

### Maintain 30 active, manual effective funded cost = $100/account
- Signals routed: 3,890
- Capacity shortfall: 452
- Accounts provisioned over history: 275
- Active funded at data end: 30
- Failed accounts: 239
- Payout-cycle-complete: 6
- Completed payouts: 219
- Payout cash: $131,821.396875
- External funded-account costs: $27,500.00
- Realized household cash after modeled external cost: $104,321.396875
- Active funded cost basis at end: $3,000.00

## Certification meaning
The $100/account scenario is a deterministic **cost-engine test assumption**, not a claim that a LucidFlex50 funded account truly costs $100 to manufacture. Exact evaluation-factory acquisition economics remain later work.

## Pricing-reference re-verification before packaging
- Tradeify Select 50K current list purchase price: $165; reset fee corrected to $95; no activation fee. The pricing reference is provenance-only until the evaluation factory computes actual funded-account acquisition cost from attempts/resets.
- FundedNext Flex reference retains its current tiered challenge-price/reset structure and zero activation/monthly fee fields.
- MFFU Flex50 reference retains $153 evaluation / $153 reset / $0 activation from current official help material.
- Lucid and Apex effective checkout costs remain user-confirmation-required where live checkout/promotions/variants prevent a stable single number from being safely hard-coded.
