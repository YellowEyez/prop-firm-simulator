# StarBase v5G Validation Report

## Release target

- Certified baseline entering v5G: **31 / 60** core roadmap steps.
- v5G implements **Step 28 — Live-account state model**.
- Deployment certification target: **7 / 7 Live State Verification fixtures PASS**.
- Next sequential target after certification: **Step 29 — Sim-funded -> live transition rules**.

## Current official live-state sources used

- Lucid Live structure: https://support.lucidtrading.com/en/articles/13425130-new-live-structure
- Lucid live scaling: https://support.lucidtrading.com/en/articles/15245873-new-live-scaling-plan
- Tradeify Elite: https://help.tradeify.co/en/articles/12969284-tradeify-elite-program
- MFFU Flex 50K live parameters: https://help.myfundedfutures.com/en/articles/15072271-flex-plan-50-000-a-comprehensive-guide
- Apex Live Prop Trading Program: https://apextraderfunding.com/help-center/getting-started/apex-live-prop-trading-program-faq/
- Topstep Live Funded Account parameters: https://help.topstep.com/en/articles/10657969-live-funded-account-parameters
- Topstep payout policy: https://help.topstep.com/en/articles/8284233-topstep-payout-policy
- FundedNext Rapid live structure: https://helpfutures.fundednext.com/en/articles/15900277-road-to-live-trading-rapid-challenge

## Safety behavior

FundedNext Rapid Live 50K is intentionally **not instantiable** in v5G because its current official article contains internally conflicting statements about the locked MLL floor. StarBase preserves this as `CONFLICTING_OFFICIAL_TEXT` rather than selecting a preferred interpretation silently.

## Live State fixtures

1. `L01_LUCID_50K_OPEN` — $0 start, -$2,000 floor, 2 minis / 20 micros, no DLL.
2. `L02_LUCID_50K_SCALE_LOCK` — balance-tier scaling and $100 locked floor.
3. `L03_TRADEIFY_50K_OPEN` — $0 start, -$2,000 floor, 2 minis / 20 micros, no DLL.
4. `L04_MFFU_50K_OPEN` — $2,000 start, $156 minimum balance, $1,844 cushion, 3 minis / 30 micros.
5. `L05_APEX_LEVEL2` — $12,000 live balance maps to Level 2, 25 minis / 250 micros and $5,000 DLL; live MLL remains locked at $100.
6. `L06_TOPSTEP_50K_TRANSITION_STATE` — transition-derived $10,000 starting balance + $40,000 reserve example, $1,000 closure floor, $2,000 DLL, 5-minis state.
7. `L07_FUNDEDNEXT_CONFLICT_BLOCK` — conflicting current official live rule is blocked instead of guessed.

## Automated validation from working tree

- `PYTHONPATH=. pytest -q`: **111 / 111 PASS**.
- `PYTHONPATH=. python -m unittest discover -s tests -q`: **60 tests PASS**.
- Step-28 Live State Verification: **7 / 7 PASS**.
- `python -m compileall -q .`: PASS.
- `python verify_starbase_install.py --files-only`: PASS.

## Boundary

A passing Step-28 suite proves the live account state vocabulary and starting/risk geometry. It does **not** prove transition timing, withdrawal behavior, erased-value accounting, reserve release, Bonus Vault payment logic, discretionary live selection, or cooldown orchestration. Those remain Steps 29-32.
