# One-time repository replacement

This bootstrap tree replaces the current repository contents with the project stored under `_incoming/`.

## Before running

1. Create a fine-grained GitHub personal access token restricted to this repository.
2. Grant it:
   - **Contents: Read and write**
   - **Workflows: Read and write**
3. Add the token to the repository as an Actions secret named `REPO_WRITE_TOKEN`.
4. Open **Actions → Apply _incoming repository replacement → Run workflow**.
5. Enter exactly: `REPLACE REPOSITORY`.

The workflow deletes the old tracked tree, copies `_incoming/` to the repository root, commits, and pushes to the branch from which it was started. The bootstrap workflow deletes itself and is replaced by the final CI workflow.
