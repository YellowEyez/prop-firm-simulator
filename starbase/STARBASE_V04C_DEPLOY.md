# Deploy Project StarBase v4C

This release uses the same safe deployment layout as v4B.1.

Upload/replace the folder named exactly:

`starbase`

Do not rename it to a downloaded ZIP name and do not add `(1)` or spaces to the deployed application folder.

In Streamlit Community Cloud set the Main file path to:

`starbase/app.py`

The dependency file is located beside the app entrypoint at:

`starbase/requirements.txt`

Recommended first verification:
1. Open `Lifecycle + Account Comparison (v4C)`.
2. Upload Sydney_01 or another known exact TradingView profile.
3. Choose Funded only.
4. Compare several 50K products.
5. Confirm the products no longer all accumulate one generic large ending balance; payout/failure paths should differ by encoded rules.
