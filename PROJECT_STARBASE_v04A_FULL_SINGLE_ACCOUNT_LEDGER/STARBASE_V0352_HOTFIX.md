# Project StarBase v3.5.2 - Asset Path / Nested Deployment Hotfix

## Why this release exists
A Streamlit Cloud deployment launched `app.py` from a nested repository folder. The app referenced `logo_dark.png` with a working-directory-relative path, which caused `MediaFileStorageError` even though the logo existed beside `app.py`.

## Fixes
- Added `starbase_paths.py` and resolve packaged assets relative to the source directory (`Path(__file__).resolve().parent`).
- Logo rendering now uses an absolute packaged-asset path.
- Missing logo gracefully falls back to text instead of crashing the entire app.
- `verify_starbase_install.py` now works from any current working directory and validates assets beside `app.py`.
- Added `.gitignore` for `.DS_Store`, Python caches, local environments, and secrets.
- Added deterministic path tests.

## Deployment layouts supported
Both are now valid:

1. Repository-root app:
   `repo/app.py`
2. Nested app:
   `repo/project_starbase_v0352/app.py`

For a nested app, configure Streamlit's entrypoint to that exact nested `app.py` path. The matching `requirements.txt` must stay beside it.
