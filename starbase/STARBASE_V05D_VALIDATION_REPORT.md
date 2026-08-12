# Project StarBase v5D Validation Report

## User-returned v5C certification bundle
The uploaded strict LucidFlex50 / Sydney economics bundle reconciled internally:
- 4,342 strict eligible/routed trades
- 295 accounts provisioned
- 229 completed payouts
- $138,405.628125 payout cash
- $29,500 modeled external account costs under the explicit $100/account certification assumption
- $108,905.628125 modeled realized household cash
- 37 active funded accounts and $3,700 active-account cost basis
- $5,486.259375 accrued-but-blocked estimated trader payout capacity

This certifies Step 24 for the controlled test path.

## v5D automated validation
- Python compileall: PASS
- Automated suite: **88 / 88 PASS**
- New fee tests verify:
  - NQ/MNQ/ES/MES point values
  - profile instrument inference
  - Lucid vs Tradeify NQ rates differ
  - Apex Rithmic vs Tradovate rates differ
  - unresolved fee combinations remain unresolved instead of borrowing a rate
  - manual overrides are explicitly labeled
  - fee and realism snapshots are included in the downloadable bundle

## Certification target
Use saved Sydney NQ and compare the same strict strategy through at least LucidFlex50 and Tradeify Select50. The automatically selected NQ round-trip fee must change from $3.50 (Lucid) to $5.76 (Tradeify), and the raw-control commission total/net result must change accordingly.
