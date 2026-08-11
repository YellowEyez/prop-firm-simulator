# Deploy Project StarBase v2 to the existing Streamlit app

## Recommended safe deployment
1. Keep a copy/tag of the current public repository before replacing files.
2. Copy the v2 project files into the repository root.
3. Do **not** add private TradingView CSVs, checkpoint ZIPs, transcripts, strategy archives, or credentials to the public repository.
4. Commit/push the code-only update.
5. Streamlit Community Cloud should redeploy automatically from the same repository.
6. Open the app and leave the default workspace on **TradingView Import + Audit (v2)**.
7. Upload a known test batch such as Sydney_01 and verify the audit dashboard.

## Files added in v2
- `tradingview_audit.py`
- `starbase_audit_ui.py`
- `tests/test_tradingview_audit.py`
- `STARBASE_V02_CHANGELOG.md`
- `STARBASE_V02_VALIDATION_REPORT.md`
- `BASELINE_V1_SHA256.txt`

## Files modified in v2
- `app.py` — StarBase branding + mode selector + v2 audit workspace.
- `README.md` — v2 trust-boundary notice.

## Files intentionally left unchanged
- `simulation.py`
- `prop_firms.json`
- `tooltips.py`

The unchanged legacy lifecycle/rule files are intentionally preserved for reference. Do not treat legacy simulation output as production-trusted StarBase output yet.
