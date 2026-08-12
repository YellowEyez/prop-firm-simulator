"""Deployment sanity check for Project StarBase.
Run from anywhere: python /path/to/verify_starbase_install.py
"""
from pathlib import Path
import importlib
import sys

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

# Streamlit Community Cloud can behave poorly when a nested app directory contains
# spaces/parentheses. The supported StarBase folder name is deliberately simple.
unsafe = any(ch.isspace() for ch in APP_DIR.name) or any(ch in APP_DIR.name for ch in "()")
if unsafe:
    raise SystemExit(
        f"Unsafe StarBase deployment folder name: {APP_DIR.name!r}. "
        "Rename the app directory to 'starbase' and deploy 'starbase/app.py'."
    )

required_files = [
    "app.py", "requirements.txt", "simulation.py", "tradingview_audit.py",
    "starbase_audit_ui.py", "starbase_rulebook.py", "starbase_rulebook_ui.py",
    "starbase_integrity.py", "starbase_integrity_ui.py", "starbase_rules_v3.json",
    "starbase_paths.py", "starbase_economics.py", "starbase_costs_v1.json",
    "starbase_fleet.py", "starbase_fleet_ui.py", "tooltips.py", "logo_dark.png", "logo_light.png",
]
missing = [p for p in required_files if not (APP_DIR / p).exists()]
if missing:
    raise SystemExit(f"Missing required StarBase files beside app.py: {missing}")

files_only = "--files-only" in sys.argv
if not files_only:
    for name in ("streamlit", "pandas", "numpy", "plotly"):
        try:
            mod = importlib.import_module(name)
            print(f"OK dependency {name}: {getattr(mod, '__version__', 'unknown')}")
        except Exception as exc:
            raise SystemExit(f"Missing dependency {name}: {exc}") from exc
else:
    print("Dependency import check skipped (--files-only).")

if not files_only:
    for name in (
        "simulation", "tradingview_audit", "starbase_audit_ui", "starbase_rulebook",
        "starbase_rulebook_ui", "starbase_integrity", "starbase_integrity_ui", "starbase_paths",
        "starbase_economics", "starbase_fleet", "starbase_fleet_ui", "tooltips",
    ):
        importlib.import_module(name)
        print(f"OK local module {name}")

print(f"StarBase deployment sanity check PASSED from {APP_DIR}")
