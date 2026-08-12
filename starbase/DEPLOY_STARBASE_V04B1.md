# StarBase v4B.1 Safe Streamlit Deployment

This release is a deployment hotfix for v4B. Trading logic is intentionally unchanged except for clearer fleet-semantics text/documentation.

## Important folder rule

Use the folder name exactly:

`starbase`

Do not rename it to a folder containing spaces or parentheses such as:

`PROJECT_STARBASE... (1)`

The prior Streamlit Community Cloud dependency failure came from the `(1)` path being mis-parsed when locating `requirements.txt`.

## GitHub layout

The supported nested layout is:

repo-root/
    starbase/
        app.py
        requirements.txt
        ...

Set the Streamlit main module path to:

`starbase/app.py`

Streamlit officially supports a dependency file in the same directory as the entrypoint.

You may leave older StarBase folders elsewhere in the repository temporarily; they are ignored as long as the deployed main module points to `starbase/app.py`.

## Recommended Python version

For Community Cloud, select Python 3.12 in Advanced settings unless a later StarBase release explicitly changes the deployment baseline.

## Sanity check

From a local terminal, if available:

`python starbase/verify_starbase_install.py --files-only`

Use the version without `--files-only` only in an environment where Streamlit dependencies are already installed.

The script checks required files and dependencies beside the StarBase entrypoint.
