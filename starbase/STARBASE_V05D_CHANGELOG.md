# Project StarBase v5D Changelog

## Progress
- Step 24 is deployment-certified from the user's strict v5C Josh economics bundle.
- Official progress entering v5D: **25/60 verified**.
- v5D implements Step 25 (instrument-specific trading fees); deployment certification is still required.

## Changes
- Added `starbase_fees_v1.json` and `starbase_fees.py`.
- Fees resolve by firm, platform/connection where relevant, futures instrument, and contract quantity.
- Core instrument metadata added for NQ, MNQ, ES, MES, including point values.
- Dataset Library now saves explicit instrument identity and point value.
- Apex fee context distinguishes Rithmic, Tradovate, and WealthCharts.
- Missing fee combinations never borrow another firm's rate. A manual verified override is required.
- Josh fleet summary/bundle now records fee status, source, effective date, instrument, and resolution method.
- Added compact Realism / Trust expander in the UI.
- Analysis ZIP now includes `FEE_SNAPSHOT.json`, `REALISM_REPORT.json`, and `REALISM_REPORT.md`.
- Realism report identifies unlimited capacity, instant replacements, manual acquisition cost, unresolved fee/rule paths, funded-only assumptions, and unresolved live-transition/future-payout value.
- Rule verification age is checked in the realism report; older snapshots are flagged instead of silently presented as current.
