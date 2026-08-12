# Project StarBase v5C Validation Report

## Automated regression

- Full Python test suite: **81 / 81 passing**.
- New workspace-routing regression proves `Josh Fleet Economics + Inventory (v5C)` maps to `fleet_economics`, not Legacy.
- New dataset-library tests cover save/load/delete, chart-interval inference, suggested naming, and full Dataset Vault export/restore.

## Real Sydney 01 library regression

Using the six known Sydney files:

- Strict valid trades: **4,342**
- REVIEW: **96**
- Invalid: **27**
- Futures sessions: **326**
- Strict normalized gross P/L: **$22,230.00**
- Inferred chart interval: **10s**
- Chart-interval detector match: **95.252%**
- Year range: **2025-2026**
- Suggested saved name: **Sydney_10s_2025-2026**

The detector uses elapsed trade seconds divided by TradingView `Duration (bars)`. The export itself does not contain an explicit chart-timeframe field, so this remains a high-confidence inference rather than immutable source metadata.

## Saved-dataset -> Josh Fleet economics regression

Sydney was saved to the new Dataset Library, reloaded from the saved raw files, re-audited, and sent through the strict LucidFlex50 Force-100% fleet with the existing Step-24 certification assumption of $100 effective funded-account acquisition cost.

Expected results remain:

- Signals routed: **4,342 / 4,342**
- Accounts provisioned: **295**
- Failed accounts: **253**
- Completed payouts: **229**
- Payout cash: **$138,405.63**
- Modeled external account cost: **$29,500.00**
- Modeled realized household net: **$108,905.63**
- Active funded accounts at data end: **37**
- Active-account cost basis: **$3,700.00**
- Claimable-now estimated trader cash: **$0.00**
- Accrued-but-blocked estimated trader cash: **$5,486.26**

This proves that storing/reloading Sydney through the Dataset Library does not change the audited strategy path or fleet economics.

## Deployment certification required from user

1. Confirm the new Dataset Library can save Sydney and detects 10s / 2025-2026.
2. Confirm Josh Fleet Economics opens the Josh page, not Legacy.
3. Select the saved Sydney dataset from Josh Fleet Economics and verify strict counts 4,342 / 96 / 27 / 326.
4. Run the existing $100 Force-100% Step-24 test. If the headline numbers above reproduce, Step 24 can be marked deployment-certified and core progress advances from 24/60 to 25/60.
