# StarBase v3.5.1 deployment hotfix

This release is intentionally FLAT at repository root.

Required deployment layout:

- app.py
- requirements.txt
- simulation.py
- tradingview_audit.py
- starbase_audit_ui.py
- starbase_rulebook.py
- starbase_rulebook_ui.py
- starbase_integrity.py
- starbase_integrity_ui.py
- starbase_rules_v3.json
- tooltips.py
- tests/
- image/assets and documentation

For Streamlit Community Cloud, set the entrypoint to exactly:

`app.py`

Do not set the entrypoint to a nested path such as `prop-firm-simulator-main 4/app.py` for this release.

The dependency file `requirements.txt` is at repository root beside `app.py` so Streamlit Community Cloud can install Plotly and the other required packages.
