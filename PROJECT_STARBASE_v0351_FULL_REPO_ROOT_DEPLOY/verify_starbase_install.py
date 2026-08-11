"""Deployment sanity check for Project StarBase.
Run: python verify_starbase_install.py
"""
from pathlib import Path
import importlib
import sys

required_files = [
    "app.py", "requirements.txt", "simulation.py", "tradingview_audit.py",
    "starbase_audit_ui.py", "starbase_rulebook.py", "starbase_rulebook_ui.py",
    "starbase_integrity.py", "starbase_integrity_ui.py", "starbase_rules_v3.json",
    "tooltips.py",
]
missing = [p for p in required_files if not Path(p).exists()]
if missing:
    raise SystemExit(f"Missing required StarBase files: {missing}")

for name in ("streamlit", "pandas", "numpy", "plotly"):
    try:
        mod = importlib.import_module(name)
        print(f"OK dependency {name}: {getattr(mod, '__version__', 'unknown')}")
    except Exception as exc:
        raise SystemExit(f"Missing dependency {name}: {exc}") from exc

for name in (
    "simulation", "tradingview_audit", "starbase_audit_ui", "starbase_rulebook",
    "starbase_rulebook_ui", "starbase_integrity", "starbase_integrity_ui", "tooltips",
):
    importlib.import_module(name)
    print(f"OK local module {name}")

print("StarBase deployment sanity check PASSED")
