# Project StarBase v5A Validation Report

## Automated regression
- 66 / 66 pytest tests pass.
- New tests verify raw-baseline reconciliation, fixed fleets, one-trade/account/session routing, capacity shortfalls, force-100%-capture provisioning, replacement capacity after a failure, aggregate payout accounting, and prohibition on claiming final business net before the cost engine exists.

## Real Sydney regression
Using the six Sydney_01 1NQ source files, strict-valid only, $3.50 round-trip commission/contract:

### Audit / raw baseline
- strict valid trades: 4,342
- review: 96
- invalid: 27
- futures sessions: 326
- source gross P/L: $22,230.00
- firm commissions if every trade is taken: $15,197.00
- source net after firm commissions: $7,033.00

### LucidFlex50 funded, max 1 trade/account/session
Fixed fleet = 1:
- routed: 7
- payout cash: $487.80
- failed accounts: 1

Fixed fleet = 30, no automatic replacements:
- routed: 494
- unrouted capacity: 3,848
- accounts provisioned: 30
- failed accounts: 30
- completed payouts: 25
- payout cash: $14,120.915625

Force 100% Capture:
- routed: 4,342 / 4,342
- capture: 100%
- funded accounts provisioned over history: 295
- failed accounts: 253
- payout-cycle-complete accounts: 5
- active funded accounts at end: 37
- completed payouts: 229
- payout cash received: $138,405.628125
- active account profit inventory, not cash: $7,323.1875
- total firm commissions: $15,197.00

IMPORTANT: account acquisition costs are not modeled in v5A, so $138,405.63 is payout cash, NOT final business profit.

## v4C lifecycle regression retained
Sydney_01, one trade/account/session, $3.50 commission:
- LucidFlex50 evaluation: PASSED 2025-05-21, 34 routed trades, ending evaluation balance $53,001.
- FundedNext Flex50 evaluation: PASSED 2025-05-15, 30 routed trades, ending evaluation balance $52,560.
- Apex EOD50 Rithmic evaluation: EXPIRED 2025-04-30, 19 routed trades.
- LucidFlex50 Eval->Funded: funded stage starts fresh at $50,000 on the first later futures session, not at the evaluation ending balance.
