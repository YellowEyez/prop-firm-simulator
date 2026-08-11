# Project StarBase v2 — TradingView Import + Audit

## Scope
v2 deliberately changes source ingestion only. The legacy prop-firm lifecycle simulator is preserved behind a clearly labeled reference mode and is not yet production-trusted.

## Added
- Multi-file TradingView Strategy Tester List of Trades importer.
- Canonical StarBase trade ledger.
- 6 PM ET futures-session IDs.
- Project source-validity policy:
  - 4–6 PM ET entries invalid,
  - next-session carry invalid,
  - >2h invalid,
  - 1–2h review/quarantine,
  - backtest-end `Open` pseudo-trades invalid,
  - exact overlap duplicates across uploaded segments invalid,
  - same-source rapid reentries preserved.
- TradingView commission normalization: `normalized_gross_pnl = exported_net_pnl + exported_commission`.
- P&L/price reconciliation diagnostics and suspicious >$1,000/contract review flags.
- Downloadable canonical ledger, strict-valid ledger, flagged rows, and audit summary JSON.
- Per-file SHA-256 hashes and file audit table.
- Deterministic unit tests for v2 validity rules.

## Not changed yet
- Prop-firm rules (`prop_firms.json` remains legacy/stale).
- Evaluation/funded/live lifecycle math.
- EOD MLL/DLL semantics.
- Fleet/household routing.
- Cross-strategy near-time deduplication.
- Exact profile selector.

Those belong to v3+ according to Checkpoint 07.
