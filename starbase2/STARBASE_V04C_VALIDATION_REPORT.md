# Project StarBase v4C Validation Report

Validation scope:
- Existing v2/v3/v3.5/v4A/v4B regression suite preserved.
- New lifecycle tests added for evaluation stopping, funded payouts, MFFU zero-balance accounting, Apex safety-net payouts, eval->funded handoff, and cross-account differentiation.
- Real Sydney_01 regression run performed against multiple 50K products.

Key real-data regression facts:
- Sydney audit reproduced 4,342 strict-valid trades across 326 futures sessions.
- Evaluation runs now stop when PASS / FAIL / expiry occurs instead of trading the entire source history indefinitely.
- Funded runs now deduct encoded payouts and preserve trader cash separately from ending simulated balance.
- Same Sydney profile produced materially different funded outcomes across LucidFlex, FundedNext Flex, Apex EOD, LucidDirect, Tradeify Select Flex and MFFU Flex.

See automated test output in release verification for final pass count.
