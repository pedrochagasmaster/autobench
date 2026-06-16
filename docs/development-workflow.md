# Development Workflow

This is the canonical workflow for making Dispatch changes locally, keeping the
corporate Bitbucket remote in sync, and updating the Hadoop Edge Nodes in a way
that can be traced back to a Git commit.

## Remotes

Keep both remotes configured:

- `origin`: GitHub, used for GitHub Issues and occasional VPN-bypass pushes.
- `bitbucket`: corporate Bitbucket, used as the writable remote from this
  machine and as the remote the Edge Nodes can pull from.

Set up Bitbucket once:

```powershell
git remote add bitbucket https://scm.mastercard.int/stash/scm/~e176097/autobench.git
git remote -v
```

If the remote already exists with the wrong URL:

```powershell
git remote set-url bitbucket https://scm.mastercard.int/stash/scm/~e176097/autobench.git
git remote -v
```

Do not remove `origin` unless the GitHub issue-tracker workflow is replaced.
When using `gh`, pass `-R pedrochagasmaster/robocop` explicitly so commands do
not depend on which Git remote is currently primary.

## First-Time Local Setup

Install the runtime package and test dependencies into the active Python
environment:

```powershell
py -m pip install -e ".[dev]"
```

Use this before running `tools/dev/local_check.ps1` on a fresh machine or after
recreating the Python environment.

## Daily Loop

1. Start from a branch or a clean `main`.

```powershell
git status --short
git branch -vv
```

2. Make the local change and run the focused tests for the files touched.

3. Run the standard local gate before sharing:

```powershell
.\tools\dev\local_check.ps1
```

The script runs:

```powershell
py -m compileall dispatch scr
py -m pytest tests tools/prod_tui/tests -q
py -m dispatch --help
```

4. Commit locally after review:

```powershell
git status --short
git diff
git add <files>
git commit -m "Describe the change"
```

5. Check remote sync state:

```powershell
.\tools\dev\git_sync_status.ps1
```

6. Push to Bitbucket when the branch is ready to move to the server:

```powershell
git push -u bitbucket HEAD
```

7. If a temporary VPN bypass is available and the GitHub mirror should be
   updated, push explicitly:

```powershell
git push origin HEAD
```

Do not push either remote from an agent session unless the user explicitly asks
for that push.

## Edge Node Update

Preferred path for committed, reviewable deployments:

```bash
cd /ads_storage/dispatch
git fetch bitbucket
git checkout main
git pull --ff-only bitbucket main
DISPATCH_PYTHON_BIN=$(command -v python3.11 || command -v python3.10) ./install.sh
```

For an exact commit:

```bash
cd /ads_storage/dispatch
git fetch bitbucket
git checkout <commit-sha>
DISPATCH_PYTHON_BIN=$(command -v python3.11 || command -v python3.10) ./install.sh
```

Rollback is the same shape: checkout the previous known-good commit and rerun
`install.sh`.

Node 03 and node 04 have independent filesystems. Update and validate each node
separately; one node being current does not imply the other is current.

## Fast Edge Iteration

Use `_seam_deploy` only when a human has already opened the authenticated
tmux/psmux session for that node. This path is for fast iteration and drift
verification, not for replacing Git history.

Verify both nodes:

```powershell
.\tools\dev\edge_sync.ps1 -Node all -Mode verify
```

Sync only `dispatch/` files to node 04:

```powershell
.\tools\dev\edge_sync.ps1 -Node 04 -Mode sync
```

Deploy `scr/` only when the change has gone through ADR-0005 review and the
operator intentionally wants full parity:

```powershell
.\tools\dev\edge_sync.ps1 -Node 04 -Mode sync -IncludeScr
```

The wrapper maps `-IncludeScr` to `_seam_deploy deploy-all`; without it, `scr/`
drift is reported but not auto-deployed.

## Full Bundle Deploy

Use the zip path for first-time setup, vendor wheel refreshes, offline installs,
or recovery when the server working tree is not usable:

```powershell
.\deploy_and_install.ps1
```

The generated `dispatch_deploy.zip` is an artifact and must not be committed.

## Production Validation

After a committed deployment, run the strongest production harness level that
matches the change:

```powershell
py -m tools.prod_tui tmux start --config tools/prod_tui/config-node04.yaml --passcode <RSA_CODE>
py -m tools.prod_tui smoke --config tools/prod_tui/config-node04.yaml --level all --save-screens
py -m tools.prod_tui job --config tools/prod_tui/config-node04.yaml --reuse-session
```

Use Level 4-6 for changes that affect job launch, status, supervision,
destination behavior, or production parity:

```powershell
py -m tools.prod_tui level --config tools/prod_tui/config-node04.yaml --level 4 --reuse-session
py -m tools.prod_tui level --config tools/prod_tui/config-node04.yaml --level 5 --reuse-session
py -m tools.prod_tui level --config tools/prod_tui/config-node04.yaml --level 6 --reuse-session
```

Never inject `Ctrl-C` into psmux sessions. Use the harness return/quit paths and
`robocop_tmux.py send` or `keys` commands.

## Change Hygiene

- Do not commit generated artifacts such as `dispatch_deploy.zip`,
  `tools/prod_tui/reports/`, `tools/prod_tui/screens/`, or captured logs.
- Do not commit passcodes, Kerberos passwords, personal config, or downloaded
  ad hoc server files.
- Keep `scr/` changes narrow and follow ADR-0005.
- Prefer Bitbucket pull or exact-commit checkout for deployments that should be
  reproducible later.
- Use `_seam_deploy verify` after any manual server edit to detect drift before
  running production checks.
