# StarBase v5I Validation Report

## Release boundary
Entering user-certified progress: **33 / 60**.

v5I implements **Step 30 - Live payout / withdrawal engine**. Deployment certification requires **10 / 10** Live Payout fixtures.

## Verification fixtures
1. `P01_LUCID_PARTIAL_LOCK` - 90/10 withdrawal and payout-caused $100 live MLL lock.
2. `P02_LUCID_FIRST_LIVE_BONUS` - $2,000 50K-source first-live bonus is external cash and is not deducted from live balance.
3. `P03_TRADEIFY_PARTIAL` - partial Elite withdrawal at 80/20.
4. `P04_TRADEIFY_FULL_CLOSE` - full Elite balance withdrawal closes the account.
5. `P05_MFFU_LIVE_PROFIT_ONLY` - explicit live-profit ledger, $250+ live payout core, 80/20 split, $156 minimum-balance state preserved.
6. `P06_APEX_ABOVE_SAFETY_NET` - standard 90/10 withdrawal only from above the $3,100 safety net.
7. `P07_APEX_90DAY_CLOSEOUT` - after 90 live days, safety-net closeout may withdraw through the safety net and closes the account.
8. `P08_TOPSTEP_PRE30_HALF` - 5 winning days unlock up to 50% of unlocked LFA balance; Reserve remains untouched.
9. `P09_TOPSTEP_POST30_FULL_CLOSE` - after 30 lifetime live winning days, daily full unlocked-balance payout closes the LFA.
10. `P10_FUNDEDNEXT_CONFLICT_BLOCK` - unresolved FundedNext live-floor conflict remains blocked.

## Source-tree validation
- Dedicated Live Payout suite: **10 / 10 PASS**.
- Full pytest suite: **132 / 132 PASS**.
- unittest-discoverable suite: **72 / 72 PASS**.

## Important scope notes
- Step 31 remains required for final account-closure forfeiture treatment, Reserve/Vault loss, transition residual value, and household-level erased-value accounting.
- Apex Bonus Vault release is reported as an eligibility estimate only, not guaranteed cash.
- Lucid's current standard Live structure page does not state a numeric minimum payout; StarBase does not invent one.
