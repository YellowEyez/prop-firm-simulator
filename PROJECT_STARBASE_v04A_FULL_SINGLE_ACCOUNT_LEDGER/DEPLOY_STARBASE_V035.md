# Deploy StarBase v3.5 with GitHub Desktop

## One-time setup
1. Install GitHub Desktop.
2. Sign in.
3. On GitHub, open the StarBase repository, choose **Code > Open with GitHub Desktop**, and clone it to a local folder.

## Recommended update workflow from now on
Use the **PATCH ONLY** ZIP unless the release notes explicitly say a full replacement is required.

1. In GitHub Desktop, click **Fetch origin** / **Pull origin** first so the local folder is current.
2. Extract the patch ZIP directly into the cloned StarBase repository folder.
3. Allow Windows/macOS to replace files with the same names.
4. Return to GitHub Desktop. The **Changes** view will show all additions/modifications automatically.
5. Review the change list.
6. Commit with a message such as `StarBase v3.5 research integrity`.
7. Click **Push origin**.
8. Streamlit Cloud should redeploy from the pushed repository.

## Why not upload the release ZIP to GitHub?
A ZIP committed to the repository remains a ZIP. Streamlit does not unpack it into application files automatically.

## Full ZIP
The full ZIP is a complete snapshot for backup, disaster recovery, or rebuilding the repository from scratch.

## Patch ZIP
The patch is the normal day-to-day update mechanism. It contains only new/changed files. If a future patch needs files removed, the release will include an explicit delete manifest/update script.
