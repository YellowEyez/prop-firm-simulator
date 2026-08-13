# StarBase v5F Validation Report

## Roadmap state entering v5F
- User deployment-certified v5E Rule Truth: **27 / 60 verified**.
- Step 26 is checked off.
- v5F implements Step 27 and deployment-certification controls for older Steps 19, 20 and 23.

## Golden suite
The v5F Golden Verification Lab contains **13 independent hand-calculated fixtures**. Expected values are hard-coded controls, not recomputed from the rulebook.

Coverage includes:
- LucidFlex evaluation pass termination.
- LucidFlex funded payout arithmetic.
- Tradeify Select Flex evaluation target/40% consistency/3-day path.
- Tradeify Select Flex funded payout core arithmetic.
- FundedNext Flex evaluation consistency/target path.
- FundedNext Flex 95% funded reward-share variant.
- MFFU Flex evaluation minimum-day/consistency path.
- MFFU Flex $0 simulated-funded P&L starting balance and $100 post-first-payout floor.
- Apex EOD evaluation pass termination.
- Apex EOD funded safety-net payout core arithmetic.
- LucidDirect first payout/20% consistency core arithmetic.
- Evaluation -> fresh funded lineage proving evaluation profit does not carry into funded balance.
- Cross-account comparison proving the same five +$500 trades produce different Lucid vs FundedNext trader-wallet cash.

## Source-tree validation
- Golden fixtures: **13 / 13 PASS**.
- Full pytest: **102 / 102 PASS**.
- unittest discoverable subset: **52 / 52 PASS**.
- Python compileall: PASS.
- Deployment structural check (`verify_starbase_install.py --files-only`): PASS.

## Important scope labels
A passing golden fixture does not silently promote advanced unimplemented behavior. Fixtures marked `CORE_ARITHMETIC_ONLY` or `VARIANT_SPECIFIC` retain Rule Truth warnings for items such as funded contract scaling tiers, dynamic DLL tiers, withdrawal-processing variants, and live transitions.

## Deployment certification
If the deployed `Golden Verification Lab (v5F)` shows **13 passed / 0 failed**, certify:
- Step 19 Evaluation PASS/FAIL/EXPIRE termination
- Step 20 Correct fresh-funded activation
- Step 23 Cross-account comparison lab
- Step 27 Golden single-account verification suite

The verified roadmap count then becomes **31 / 60**. Next sequential target: **Step 28 — Live-account state model**.
