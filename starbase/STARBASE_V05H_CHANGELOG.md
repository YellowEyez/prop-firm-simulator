# StarBase v5H Changelog - Live Transition Engine

## Progress
- User-certified baseline entering release: **32 / 60 verified**.
- Step 28 is now permanently checked off after the deployed v5G Live State Lab passed 7/7.
- v5H implements **Step 29 - Sim-funded -> live transition rules**.
- Step 29 remains pending deployment certification until the v5H Live Transition Lab reports 7/7 PASS.
- Next sequential target after certification: **Step 30 - Live payout/withdrawal engine**.

## Added
- `starbase_live_transition.py`: event-driven live transition engine.
- `starbase_live_transition_ui.py`: dedicated Live Transition Lab.
- `starbase_live_transitions_v1.json`: source-cited transition policy catalog.
- Lucid current transition semantics: all simulated prop accounts close; funded accounts with >=1 payout can move live; zero-payout funded accounts may create an evaluation-cost refund when cost basis is known; live starts fresh at $0.
- Tradeify Elite eligibility and mandatory selected transition: 3 payouts on one account or 10 total creates consideration eligibility; firm selection remains discretionary; all Sim Funded/evaluation accounts close; funded accounts with >=1 payout can create Elite accounts; sim profit does not carry.
- MFFU Flex threshold/review transition: five consecutive approved payouts on an account, $100K total sim payout cap, or risk-team approval; live starts at $2,000; remaining Sim accounts are suspended while Live is active.
- Apex invitation transition: active evaluations can create refunds; positive PA simulated balances are tracked in Bonus Vault; one $0 live account opens initially; invitation-decline branch preserves the current $3,000 final reward rule while simulated/Vault value is marked for Step-31 disposition.
- Topstep LFA call-up: all XFAs close; eligible XFA sizes determine the rounded LFA tier; transferable balance is capped at the LFA tier before the 20%/80% tradable/Reserve split; excess transfer value is preserved for Step-31 accounting.
- Added Topstep 100K and 150K live state profiles so mixed XFA inventories cannot incorrectly instantiate a 50K live profile.
- FundedNext Rapid live transition remains blocked while the destination live profile has conflicting official lock-floor text.

## Safety behavior
- Discretionary live selections are never inferred from TradingView history.
- Tradeify eligibility thresholds do not automatically execute a transition.
- Cash already paid to the trader is always preserved separately from transition value.
- Step 29 records transition-value buckets but does not yet call them final forfeited household cash; Step 31 owns that final accounting.
