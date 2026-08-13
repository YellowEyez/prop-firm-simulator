# StarBase v5G Changelog — Live Account State Foundation

## Progress
- User-certified baseline entering this release: **31 / 60 verified**.
- v5G implements **Step 28 — Live-account state model**.
- Step 28 remains deployment-pending until the Live State Verification Lab reports **7 / 7 PASS**.
- Next sequential target after certification: **Step 29 — Sim-funded -> live transition rules**.

## Added
- `starbase_live_profiles_v1.json`: separate versioned live-state profile catalog, verified 2026-08-13.
- `starbase_live.py`: auditable `LiveAccountState`, live profile resolution, balance/risk-tier revaluation, rule snapshot hashing, and 7-fixture Step-28 verification suite.
- `starbase_live_ui.py`: new **Live Account State Lab (v5G)** workspace.
- Live state support for clear current public structures including LucidLive, Tradeify Elite, MFFU Flex Live, Apex Live core state, and Topstep transition-derived state.
- Explicit block for FundedNext Rapid Live 50K because the current official article contains conflicting lock-floor statements. StarBase preserves the conflict instead of choosing one silently.
- Golden Verification Lab Boolean display cleanup: `True/False` is shown as text instead of `1/0` where possible.

## Deliberately not added yet
- Automatic sim-funded -> live transition selection/timing (Step 29).
- Live withdrawal execution (Step 30).
- Live transition forfeiture / erased-value accounting (Step 31).
- FUNDED-A/B/C and LIVE-A/B/C mature state machine (Step 32).
