# Project StarBase v2 — Validation Report

Validation date: 2026-08-11

## Automated deterministic tests
All v2 unit tests passed:

1. 4:00–5:59:59 PM ET entry rejection.
2. Next-6:00-PM futures-session carry rejection.
3. 1–2 hour review / >2 hour rejection.
4. Same-source rapid reentry preservation.
5. Exact overlap duplicate rejection.
6. TradingView embedded commission reversal.
7. Backtest-end `Open` pseudo-trade rejection.
8. Pre-6-PM futures-session ID assignment.

## Real-data regression: Sydney_01 1NQ
Six original TradingView segments were passed through StarBase v2.

Expected/reproduced core results:
- Parsed trade records: **4,465**
- Strict valid trades: **4,342**
- Review trades: **96**
- Invalid trades: **27** = 25 holds >2h + 2 `Open` pseudo-trades
- Active futures sessions: **326**
- Exact overlap duplicates: **0**
- Normalized clean gross P&L: **$22,230**
- Strict win rate: **61.4924%**
- Strict expectancy/trade: **$5.1198**

This exactly reproduces the controlling Sydney audit counts used immediately before StarBase development.

## Real-data regression: Julie_01 exact 1NQ
- Parsed trade records: **9,676**
- Strict valid trades: **9,566**
- Review trades: **85**
- Invalid trades: **25**
- Active futures sessions: **310**
- Strict normalized gross P&L: **-$68,250**
- Strict win rate: **57.0876%**
- Strict expectancy/trade: **-$7.1346**

## Real-data regression: Julie_01 exact 2NQ
- Parsed trade records: **18,517**
- Strict valid trades: **18,499**
- Review trades: **14**
- Invalid trades: **4**
- Active futures sessions: **310**
- Strict normalized gross P&L: **-$373,590**
- Strict win rate: **55.8679%**
- Strict expectancy/trade: **-$20.1951**
- Price/P&L reconciliation warnings: **4,524**

The 4,524 2NQ price/P&L mismatches remain **audit warnings, not quarantine failures**, because the prior exact-profile investigation established that TradingView's multi-contract bookkeeping/path behavior can legitimately produce these mismatches. This preserves the previously audited 18,499 strict 2NQ trades rather than falsely rejecting them.

## Performance
On the current container, the approximate import/audit times were:
- Sydney 4,465 trades: ~4 seconds
- Julie 1NQ 9,676 trades: ~9 seconds
- Julie 2NQ 18,517 trades: ~20 seconds

This is suitable for current Deep Backtest batch sizes and dramatically faster than the discarded first parser implementation.

## v2 trust boundary
These validations establish trust in **source ingestion and source validity classification only**. They do not validate the legacy evaluation/funded/payout engine. That engine remains reference-only until StarBase v3/v4+.
