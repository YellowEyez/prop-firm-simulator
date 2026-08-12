# StarBase v3 Validation Report

Validation date: 2026-08-11

The v3 rulebook is descriptive and source-cited. It intentionally does not run lifecycle simulations yet.

Validation goals:
1. Preserve v2 TradingView audit.
2. Preserve legacy simulator files untouched.
3. Separate EOD and intraday-funded products by stage.
4. Keep intraday products visible in Research mode.
5. Allow EOD/static-only filtering without deleting data.
6. Mark partially verified product families so v4 cannot silently execute incomplete rules.
7. Require official source URLs and verification dates for all active product families.

Automated tests are in `tests/test_starbase_rulebook.py` and `tests/test_tradingview_audit.py`.
