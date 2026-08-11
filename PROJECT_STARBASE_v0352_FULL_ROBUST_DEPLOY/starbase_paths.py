"""Path helpers for Project StarBase packaged assets.

All packaged resources are resolved relative to this source directory, not the
process working directory. This makes Streamlit deployment robust whether the
app is located at repository root or inside a subdirectory.
"""
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent


def asset_path(name: str) -> Path:
    """Return an absolute path to a packaged StarBase asset."""
    return APP_DIR / name


def existing_asset(name: str) -> Path | None:
    """Return the packaged asset path when it exists, otherwise None."""
    path = asset_path(name)
    return path if path.is_file() else None
