# Project StarBase v5C — Dataset Library + Workspace Routing Repair

## Why this release exists

v5B contained the correct Josh fleet-economics implementation, but the sidebar label and routing predicate did not match. Selecting `Josh Fleet Economics + Inventory (v5B)` could therefore fall through to the Legacy Simulator, which explains the single-file uploader and missing v5B economics page seen in deployment.

v5C repairs that routing defect and removes prefix-string routing entirely. Workspace labels now map to stable internal routing keys in `starbase_workspaces.py`, with regression tests that specifically prove Josh Fleet Economics cannot route to Legacy.

## Strategy Dataset Library

v5C adds a reusable Strategy Dataset Library.

A saved dataset stores:

- user-defined dataset name,
- Strategy ID,
- exact execution profile ID,
- free-form notes,
- all original TradingView CSV segments,
- per-file SHA-256 hashes,
- audit summary,
- first/last timestamps and year range,
- inferred chart interval plus confidence/method,
- point-value audit setting.

The chart interval is inferred primarily from `elapsed trade seconds / Duration (bars)`, which is materially stronger than trusting filenames. Because TradingView List-of-Trades exports do not include an explicit chart-timeframe field, the user can override the inferred label.

Saved datasets can be reused from:

- Historical Single-Account Trader,
- Lifecycle + Account Comparison,
- Josh Fleet Economics + Inventory.

## Portable Dataset Vault

Streamlit Community Cloud runtime filesystem persistence is not guaranteed across app redeploys/restarts. v5C therefore supports a portable `StarBase_Dataset_Vault.zip` containing the library's raw CSVs, manifests, names, notes and hashes. A full saved library can be restored with one ZIP upload.

Datasets can also be deleted from the current runtime library.

## Progress discipline

This is a corrective/infrastructure release. Core deployment-certified progress remains **24 / 60** until the Step-24 economics certification can finally be run on the correctly routed Josh page.

Non-numbered infrastructure milestone completed in v5C:

- **D1 — Reusable named Strategy Dataset Library + portable vault**.
