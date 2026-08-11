# Project StarBase v3.5.1 - Streamlit deployment hotfix

This release contains the full StarBase v3.5 feature set and fixes deployment packaging.

## Root layout
`app.py` and `requirements.txt` are both at repository root.

## Streamlit Community Cloud
Set the entrypoint/file path to:

`app.py`

Do not select a nested path from an older extracted folder.

## Dependencies
The root `requirements.txt` declares:
- streamlit
- pandas
- numpy
- plotly

## Validation
- 28 automated StarBase tests pass from a clean extraction.
- All Python sources compile.
- The ZIP is intentionally flat at repository root.

The build environment used to create this archive has no outbound package-index access, so a live `pip install` could not be performed here. Streamlit Community Cloud will resolve the root requirements file during deployment.
