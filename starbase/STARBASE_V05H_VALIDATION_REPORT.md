# StarBase v5H Validation Report - Step 29

## Baseline
- Certified entry state: **32 / 60 verified**.
- Step 28 certified by deployed v5G 7/7 Live State Lab PASS.
- v5H implements Step 29; deployment certification remains pending.

## Transition fixtures
1. `T01_LUCID_ALL_SIM_CLOSE` - explicit Lucid call-up closes all simulated prop accounts, creates two live accounts from payout-bearing funded accounts, refunds known original evaluation cost for a zero-payout funded account, preserves already-paid cash, and does not carry simulated profit into live.
2. `T02_TRADEIFY_ELITE_MULTI_ACCOUNT` - Tradeify selected transition creates one Elite live account per payout-bearing funded account, closes all Sim/evaluation accounts, tracks base reward-pool entitlement, and preserves wallet cash.
3. `T03_MFFU_THRESHOLD_TRANSITION` - five consecutive approved payouts triggers Live without inventing a discretionary date; triggering account becomes a $2,000 live account and remaining simulated inventory is suspended.
4. `T04_APEX_BONUS_VAULT` - explicit Apex invitation deactivates PAs, totals positive simulated PA balances into Bonus Vault, refunds an active evaluation with known cost basis, and creates one $0 live account.
5. `T05_APEX_DECLINE_FINAL_REWARD` - declining an Apex invitation creates the documented $3,000 final reward and no live account; simulated value remains a Step-31 disposition item.
6. `T06_TOPSTEP_RESERVE_DERIVATION` - mixed 50K/150K XFA sizes average to a 100K LFA; $50K combined eligible balance becomes $10K tradable + $40K Reserve.
7. `T07_FUNDEDNEXT_CONFLICT_BLOCK` - transition remains blocked while the current destination live profile contains conflicting official text.

## Additional guards
- Tradeify explicit call-up before its documented minimum eligibility threshold is rejected as inconsistent input.
- Topstep transfer cap is applied before the 20%/80% split. Example: four 50K XFAs holding $25K each produce a 50K LFA with $10K tradable, $40K Reserve, and $50K excess preserved for Step-31 accounting.
- Topstep 50K/100K/150K live profiles use the current starting DLL/position-size tiers plus <=$10K and <=$5K safeguards.

## Full automated regression
- Full pytest suite must pass before packaging.
- Exact release ZIP is re-extracted and retested before delivery.

## Not certified by Step 29
- Live payouts/withdrawals (Step 30).
- Final household forfeiture/erased-value ledger semantics (Step 31).
- Mature FUNDED-A/B/C and LIVE-A/B/C state classification (Step 32).

## Final source-tree results
- pytest: **124 / 124 PASS**
- unittest discover: **72 / 72 PASS**
- Golden single-account suite: **13 / 13 PASS**
- Live State suite: **7 / 7 PASS**
- Live Transition suite: **7 / 7 PASS**
- Python compilation: **47 files compiled successfully**
- Deployment file sanity check: **PASS**
