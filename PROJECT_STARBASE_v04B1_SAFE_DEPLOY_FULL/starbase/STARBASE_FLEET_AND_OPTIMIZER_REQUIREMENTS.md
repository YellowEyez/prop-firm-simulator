# Project StarBase — Fleet, Stage-Specialization, and Optimizer Requirements

Status: CONTROLLING DESIGN REQUIREMENTS
Recorded: 2026-08-11
Applies to: v5+ fleet/household/profile/optimizer development

## 1. One trade per account per futures session semantics

The setting `max_trades_per_account_per_futures_session = 1` applies to EACH INDIVIDUAL ACCOUNT, not to the entire strategy or household.

Example: if Sydney produces 30 valid chronological signals in one 6 PM ET futures session and 30 eligible accounts are available, StarBase may route up to 30 signals that session: one different signal to each account. Firm/household caps, stage eligibility, account state, risk rules, deduplication, and routing policy can reduce that number.

v4B is intentionally a single-account verification layer. It can route only the first eligible signal to that one account and exposes the remaining signals as unused capacity. v5 is the fleet layer that distributes those remaining signals across many accounts.

## 2. Required research modes

StarBase must support distinct modes without forcing every test through the full lifecycle:

- Evaluation-only research
- Sim-funded-only research
- Live-only research
- Full evaluation -> funded -> live lifecycle
- Direct-funded-only research where the firm/product supports it

These modes are research tools. They must be clearly labeled so artificial stage isolation is not confused with a real full-lifecycle business forecast.

## 3. Strategy role specialization

Different exact strategy profiles may be assigned to different roles, firms, products, sizes, or account states.

Examples:
- Dahlia -> evaluations
- Sydney -> funded accounts
- Luna -> live accounts
- Julie_1NQ -> fragile/fresh account states
- Julie_2NQ -> higher-cushion states, only if exact profile/risk policy allows

StarBase must permit independent stage-role testing and combined team testing.

## 4. Evaluation inventory / banking

Evaluation-only or evaluation-factory tests must track:

- evaluations purchased
- evaluations active
- evaluations failed
- evaluations passed
- passed/waiting inventory
- evaluation progress still alive at end-of-data
- money spent on accounts that remain active at end-of-data
- reset/repurchase costs

If the user intentionally runs an evaluation-bank research mode, passed evaluations remain banked inventory rather than being automatically forced into funded trading unless the selected policy says so.

## 5. Funded inventory and payout accounting

Funded research must track per account:

- fresh funded activation
- current balance and failure floor
- qualifying/profitable days
- payout eligibility
- payout amount available but not yet requested
- payout requests and actual user cash received
- payout caps/splits
- post-payout balance/floor/cushion
- funded failures and exact failure reasons
- remaining funded accounts at end-of-data
- positive account balances/profits that remain economically relevant at end-of-data
- simulated profits forfeited because of failure, transition, closure, expiration, or other rules

End-of-data must NOT be treated as automatic failure or liquidation.

## 6. Live transition accounting

When a firm's rules trigger or permit a move to live, StarBase must record:

- the exact trigger/review event
- whether transition is deterministic or discretionary
- funded accounts closed by the transition
- unpaid simulated-funded payout value erased/forfeited
- passed/waiting inventory affected
- refunds/credits/bonuses if applicable
- live account starting state
- live account limits
- post-transition cooldown / restart restrictions

The engine must preserve both cash already withdrawn and economic value still present/forfeited at transition.

## 7. End-of-backtest balance sheet

Every serious run should finish with a household balance sheet, not one net-profit number.

Required categories include:

- realized payout cash
- live withdrawals
- bonuses/refunds
- evaluation/reset/activation/direct-funded costs
- commissions/fees
- active evaluations and their progress
- passed/waiting evaluations
- active funded accounts
- payout-eligible but unpaid amounts
- active live accounts
- remaining account balances/cushions
- forfeited simulated profits
- erased evaluation progress
- failed/expired/closed accounts by exact reason
- unused valid strategy signals / capacity shortfall

## 8. Firm/account constraints

Routing must enforce current versioned rules including where applicable:

- household limits
- evaluation limits
- funded/sim-funded limits
- live limits
- total allocation limits
- purchase limits
- inactivity/dormancy rules
- DLL/MLL rules
- consistency requirements
- payout requirements/caps
- contract limits/scaling rules
- live-transition restrictions

EOD, intraday-trailing, static, and hybrid products must remain clearly separated and individually testable.

## 9. Exact-profile contract scaling

StarBase must never treat fixed-dollar 2NQ/3NQ execution as `1NQ P&L x quantity` for production-grade forecasts.

Permanent workflow:

1. Load exact TradingView profiles such as 1NQ, 2NQ, 3NQ.
2. Use StarBase to research which account states can safely use each exact profile.
3. Define a candidate state/cushion scaling policy.
4. Implement the promising dynamic policy in Pine/TradingView.
5. Export the exact dynamic run.
6. Use StarBase for final lifecycle validation.

Every run must retain execution-fidelity classification: EXACT / DERIVED-SHADOW / SYNTHETIC-GEOMETRY / UNRESOLVED.

## 10. Stage-aware risk/profile optimization

The optimizer must eventually search stage-specific choices rather than one universal setting.

Examples:
- different TP/SL candidates by firm/product/stage
- different exact contract profile by cushion/account state
- different entry filter or strategy role for eval vs funded vs live
- fresh-account defensive profile vs mature-account profile

Synthetic TP/SL calculators may suggest hypotheses, but production validation requires exact TradingView execution or explicitly labeled shadow analysis.

## 11. Optimizer objectives

The optimizer must not maximize one historical dollar number. It should rank candidates across multiple gates:

### Strategy quality
- expectancy
- win/loss geometry
- trade count
- loss clustering

### Robustness
- chronological development vs holdout
- 2025 vs 2026 or equivalent time partitions
- month/quarter stability
- worst rolling windows

### Prop economics
- evaluation pass probability
- expected cost per funded account
- funded payout #1 probability
- expected payout wallet
- lifecycle value
- household realized cash
- remaining end-of-data economic value

### Operational feasibility
- account inventory required
- account purchase cash requirement
- unused signals
- capacity shortfalls
- live occupancy
- replacement demand
- firm concentration

### Research credibility
- number of parameter trials searched
- execution fidelity
- rule coverage
- holdout degradation
- search-breadth/noise-ceiling diagnostics

## 12. Result explainability and downloads

Every run must provide detailed downloadable artifacts suitable for deeper ChatGPT analysis, including eventually:

- RUN_MANIFEST.json
- CONFIG.json
- RULEBOOK_SNAPSHOT.json
- SOURCE_HASHES.json
- STRATEGY_PROFILES.json
- ACCOUNT_LEDGER.csv
- TRADE_ROUTING.csv
- PAYOUT_LEDGER.csv
- COST_LEDGER.csv
- ACTIVE_INVENTORY.csv
- FAILURES.csv
- UNUSED_SIGNALS.csv
- MONTHLY.csv
- QUARTERLY.csv
- OPTIMIZER_DIAGNOSTICS.csv/json
- REPORT.md

Every account pass, payout, failure, closure, transition, and routing decision must be traceable.

## 13. Capacity/fleet goal

StarBase is ultimately a prop-business simulator, not a single-account toy. A high-frequency strategy that produces dozens of valid signals per session should be able to feed dozens of eligible accounts when the household inventory and firm rules permit it.

The single-account engine exists only to prove the arithmetic before multiplying it across a fleet.
