# StarBase v5I Changelog - Live Payout / Withdrawal Engine

## Progress boundary
- User-certified baseline entering v5I: **33 / 60 verified**.
- Newly certified before this release: **Step 29 - Sim-funded -> Live transition rules**.
- v5I implements **Step 30 - Live payout / withdrawal engine**.
- Step 30 remains unchecked until deployed **10 / 10 Live Payout Verification Suite PASS**.
- Next sequential target after certification: **Step 31 - Live-transition forfeiture accounting**.

## Added
- `starbase_live_payouts_v1.json`: versioned, source-linked live payout policy catalog verified 2026-08-14.
- `starbase_live_payout.py`: deterministic live withdrawal quote/execution engine.
- `starbase_live_payout_ui.py`: dedicated Live Payout / Withdrawal Lab.
- `tests/test_starbase_live_payout.py`: core payout and guardrail tests.
- New workspace route `Live Payout / Withdrawal Lab (v5I)`.

## Current live withdrawal coverage
- LucidLive current standard: daily core withdrawal path, 90/10 state metadata, payout-caused MLL lock, first-live bonus tracked separately from account balance. Numeric payout minimum is not invented where the current standard Live structure page does not state one.
- Tradeify Elite: daily 80/20 withdrawals; full-balance payout closes the Elite Live account.
- MFFU Flex Live 50K: daily 80/20, $250 minimum; explicit live-profit ledger required so live seed capital is not silently treated as payout profit.
- Apex Live: daily 90/10, $500 minimum, ordinary withdrawals above $3,100 safety net; optional 90-day safety-net closeout branch. Bonus Vault monthly release is an estimate only until all eligibility details are modeled.
- Topstep LFA: 5 x $150 winning days before each payout cycle, up to 50% of unlocked balance; daily payout access after 30 lifetime Live winning days; Reserve is never treated as ordinary withdrawable balance.
- FundedNext Rapid Live remains blocked because its current live-floor source conflict is unresolved.

## Boundaries intentionally preserved
- Step 30 executes the withdrawal event. It does not finalize every dollar forfeited when an account closes, a Reserve/Vault is lost, or a transition ends. That remains Step 31.
- No historical live strategy runner or live scaling optimizer is implied by this release.
