# Deploy StarBase v5C

1. Keep the application folder named exactly `starbase`.
2. Upload/replace the full `starbase` folder in the GitHub repository.
3. Streamlit Main file path must remain `starbase/app.py`.
4. Do not rename the deployed folder to the ZIP filename or add `(1)` to the app directory.
5. After deployment, first select `Strategy Dataset Library (v5C)` and perform the certification test in `STARBASE_V05C_VALIDATION_REPORT.md`.

The Dataset Library runtime store is intentionally excluded from Git. Download a Dataset Vault ZIP whenever you want a portable backup. Community Cloud runtime writes are not guaranteed to survive redeploys/restarts.
