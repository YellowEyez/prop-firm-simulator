# Project StarBase Master Build Roadmap v1.1

This is the controlling 60-step build checklist. Step numbers do not change casually.
Each release must report: code-verified steps, deployed-certified steps, newly implemented steps, and next sequential target.

## Current status at v5B

- Deployment-certified from user-returned ledgers: **24 / 60**.
- Verified steps are 1-18, 21-22, and 33-36.
- Implemented/code-regression-ready but not yet deployment-certified: **19, 20, 23, 24**.
- v5B targets **Step 24 — Exact fee and account-cost engine**. After the user's strict Sydney v5B certification passes, deployed-certified progress becomes **25 / 60**.
- v5B also contains partial research prototypes for Step 39 (Maintain-N replacement continuity) and Steps 41-42 (funded-only ending inventory). Those steps remain unchecked until their full real-rule scope is implemented and certified.
- Important: implementation is not the same as full business-profit certification. Steps 25-32 remain required before multi-firm household profit claims.

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
- [ ] 19 Evaluation PASS / FAIL / EXPIRE termination *(implemented; deployment certification still pending)*
- [ ] 20 Correct fresh-funded activation *(implemented; deployment certification still pending)*
- [x] 21 Core funded payout engine
- [x] 22 Separate payout cash vs account value
- [ ] 23 Cross-account comparison lab *(implemented; deployment certification still pending)*

## Phase 4 — Exact Economics + Single-Account Certification
- [ ] 24 Exact fee and account-cost engine *(v5B implemented/code-verified; deployment certification pending)*
- [ ] 25 Instrument-specific trading fees
- [ ] 26 Complete rule semantics for every supported product
- [ ] 27 Golden single-account verification suite for each core product

## Phase 5 — Full Live Account Logic
- [ ] 28 Live-account state model
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

A later-numbered step can be prototyped early when it helps validate architecture, but StarBase must not skip the unfinished lower-numbered trust/economics steps before making production-profit claims. In particular, v5A intentionally prototypes Steps 33-36 while Steps 24-32 remain unfinished. v5B returns to the sequential trust path at **Step 24**. After Step 24 deployment certification, the next sequential targets are **25 instrument-specific trading fees, 26 complete rule semantics, and 27 golden single-account verification**.
