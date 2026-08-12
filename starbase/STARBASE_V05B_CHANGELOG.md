# Project StarBase v5B — Economics + Ending Inventory

## Release purpose
v5B is the Step-24 economics/inventory release built cumulatively from the working v5A repository.
It does **not** jump ahead to live accounts or exact contract scaling.

## Added
- explicit funded-account acquisition cost basis:
  - existing/pre-owned inventory with unknown historical cost
  - manual effective funded acquisition cost per provisioned account
- per-account cost ledger and household one-time external cost
- refund/bonus field
- realized household cash bridge
- active-account ending cost basis
- claimable-now payout value
- accrued-but-not-yet-claimable payout capacity
- realistic-recoverable-future-cash placeholder intentionally left unmodeled
- payout blocker diagnostics
- confirmed residual simulated value lost on failed accounts
- unresolved value preserved at payout-cycle/live-transition boundary
- Maintain-N-active funded inventory research mode
- obvious STRICT vs REVIEW data badge
- official pricing-provenance reference file (`starbase_costs_v1.json`)
- expanded ChatGPT analysis bundle:
  - COST_LEDGER.csv
  - BOTTLENECK_SUMMARY.csv
  - FORFEITURE_AND_TRANSITION_VALUE_LEDGER.csv

## Important accounting rule
Trading commissions reduce the prop-account trade result and therefore payout production.
They are displayed as a cost drag but are **not** subtracted a second time from Josh's external cash.

## Important scope rule
For evaluation-based funded products, a funded-only simulation cannot know the true cost of manufacturing each funded account until the evaluation factory is modeled. A manual effective funded cost is therefore clearly labeled as a research assumption. Existing/pre-owned inventory never silently becomes zero-cost final business profit.

## Maintain-N warning
Maintain-N instantly provisions replacement funded inventory for research continuity. It does not yet model the real delay/cost/path of passing replacement evaluations. That remains Step 38-40 and Evaluation Factory work.

## Final packaging correction
The current official Tradeify pricing reference was rechecked before release. Select 50K reset cost is $95, not $109. `starbase_costs_v1.json` and the economics regression test were corrected before packaging.
