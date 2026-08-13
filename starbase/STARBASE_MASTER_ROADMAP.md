# Project StarBase Master Build Roadmap v1.2

This is the controlling 60-step build checklist. Step numbers do not change casually.
Each release must report: deployed-certified steps, newly implemented steps awaiting certification, and the next sequential target.

## Current status at v5G

- Deployment-certified by the user through v5F: **31 / 60**.
- v5F deployment certification closed Steps **19, 20, 23 and 27** with **13 / 13 Golden fixtures PASS**.
- Verified steps are **1-27 except no gaps**, plus the intentionally early fleet prototypes **33-36**. This yields 31 verified core steps total.
- v5G implements **Step 28 — Live-account state model**. Step 28 is code/regression-ready but remains unchecked until the user runs the deployed Live State Verification Lab and gets 7/7 PASS.
- The next sequential target after Step 28 certification is **Step 29 — Sim-funded -> live transition rules**.
- v5B-v5D contain partial research prototypes for Step 39 (Maintain-N replacement continuity) and Steps 41-42 (funded-only ending inventory). Those steps remain unchecked until their full real-rule scope is implemented and certified.
- Important: Step 28 state support is not the same as live-transition/payout certification. Steps 29-32 remain required before live business-profit claims.

### Supporting infrastructure milestones (do not renumber the 60 core steps)
- [x] **D1 — Reusable Strategy Dataset Library + Dataset Vault (v5C)**
- [x] **D2 — Exact workspace routing map (v5C)**
- [x] **D3 — Rule Truth / simulation-coverage separation (v5E)**
- [x] **D4 — Versioned Live Profile Catalog + provenance (v5G)**: verified live-state profiles are stored separately from transition/payout orchestration; internally conflicting official text is preserved and blocked rather than guessed.

## Phase 1 — Trusted TradingView Input
- [x] 1 Freeze original simulator baseline
- [x] 2 Reliable Streamlit deployment structure
- [x] 3 Multi-file TradingView importer
- [x] 4 Canonical trade ledger
- [x] 5 Correct 6 PM ET futures-session engine
- [x] 6 Invalid/review trade audit
- [x] 7 Duplicate + suspicious-trade handling
- [x] 8 Commission/source normalization

## Phase 2 — Rulebook + Research Integrity
- [x] 9 Versioned prop-firm rulebook
- [x] 10 Separate drawdown families
- [x] 11 Rule provenance
- [x] 12 Rule coverage status
- [x] 13 Execution-fidelity labels
- [x] 14 Reproducible run IDs
- [x] 15 Research experiment ledger

## Phase 3 — Trusted Single-Account Engine
- [x] 16 Explicit account-state object + accounting ledger
- [x] 17 Chronological single-account trade routing
- [x] 18 MAE-aware drawdown breach engine
- [x] 19 Evaluation PASS / FAIL / EXPIRE termination
- [x] 20 Correct fresh-funded activation
- [x] 21 Core funded payout engine
- [x] 22 Separate payout cash vs account value
- [x] 23 Cross-account comparison lab

## Phase 4 — Exact Economics + Single-Account Certification
- [x] 24 Exact fee and account-cost engine
- [x] 25 Instrument-specific trading fees
- [x] 26 Complete rule semantics / Rule Truth for supported products
- [x] 27 Golden single-account verification suite for core products

## Phase 5 — Full Live Account Logic
- [ ] 28 Live-account state model *(v5G implemented; deployment certification pending 7/7 Live State Lab PASS)*
- [ ] 29 Sim-funded -> live transition rules
- [ ] 30 Live payout/withdrawal engine
- [ ] 31 Live-transition forfeiture accounting
- [ ] 32 FUNDED-A/B/C + LIVE-A/B/C states

## Phase 6 — Fleet Engine
- [x] 33 Multiple persistent accounts of one product
- [x] 34 One trade per account per futures session
- [x] 35 Fixed-fleet mode
- [x] 36 Force 100% Signal Capture research mode
- [ ] 37 Target-capture mode
- [ ] 38 Legal auto-provisioning mode
- [ ] 39 Replacement/account-failure queue under real purchase rules/costs
- [ ] 40 Passed-evaluation bank
- [ ] 41 Funded and live inventory banks
- [ ] 42 End-of-data full fleet balance sheet (eval + funded + live)

## Phase 7 — Multi-Firm Household
- [ ] 43 Household engine
- [ ] 44 Firm/household/account limits
- [ ] 45 Linked/incompatible-account rules
- [ ] 46 Cross-firm capacity allocator

## Phase 8 — Strategy Teams and Routing
- [ ] 47 Stage-specific strategy assignment
- [ ] 48 Firm/product-specific strategy assignment
- [ ] 49 Cross-strategy opportunity deduplication
- [ ] 50 Routing-priority engine

## Phase 9 — Exact Contract Scaling
- [ ] 51 Exact execution-profile library
- [ ] 52 Account-state profile selector
- [ ] 53 Cushion/risk safety cap
- [ ] 54 Dynamic-policy research -> exact TradingView validation loop

## Phase 10 — Optimization Laboratory
- [ ] 55 Evaluation Factory optimizer
- [ ] 56 Funded Payout optimizer
- [ ] 57 Live optimizer
- [ ] 58 TP/SL/filter hypothesis lab
- [ ] 59 Multi-objective robustness optimizer
- [ ] 60 Permanent simulation archive + ChatGPT analysis package

## Release discipline

A later-numbered step can be prototyped early when it validates architecture, but StarBase must not skip unfinished lower-numbered trust/economics steps before making production-profit claims. v5F certified the full single-account trust block through Step 27. v5G starts the live trust block at Step 28 with a separate versioned Live Profile Catalog and Live State Lab. Transition timing, payout execution, erased/forfeited values, cooldown orchestration, and mature live-stage state classification remain Steps 29-32 and are not silently implied by a passing Step-28 state fixture.
