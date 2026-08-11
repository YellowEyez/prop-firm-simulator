# Project StarBase v4B.1 — Deployment Hotfix

Date: 2026-08-11

## Why this release exists

The v4B trading engine itself was not the cause of the Streamlit failure. Community Cloud was asked to deploy an entrypoint from a directory whose name ended in `(1)`, and its dependency resolver mis-parsed the adjacent `requirements.txt` path.

## Changes

- Canonical deploy folder is now `starbase` (no spaces or parentheses).
- Full ZIP contains a single top-level `starbase/` application folder.
- Deployment instructions explicitly use `starbase/app.py`.
- `verify_starbase_install.py` rejects unsafe app-folder names containing spaces/parentheses.
- v4B fleet-capacity text now explicitly states that the session cap is PER ACCOUNT.
- Added `STARBASE_FLEET_AND_OPTIMIZER_REQUIREMENTS.md` as a controlling design document covering stage specialization, account banking, payouts, live transitions, end-of-data inventory, exact-profile scaling, optimizer objectives, and downloadable audit artifacts.
- Trading calculations remain v4B; no fleet/lifecycle functionality is silently introduced in this hotfix.
