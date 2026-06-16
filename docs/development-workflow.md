# Autobench Development Workflow

This is the canonical workflow for making Autobench changes locally, publishing
them to the corporate deployment remote, and updating Hadoop Edge Nodes in a way
that can be traced to a Git commit.

## Remotes

Keep remote roles explicit:

- `origin`: GitHub mirror/review remote.
- `bitbucket`: corporate deployment remote reachable by the Edge Nodes.

Configure Bitbucket once:

```powershell
git remote add bitbucket https://scm.mastercard.int/stash/scm/~e176097/dispatch.git
git remote -v
```

If the remote already exists with another URL:

```powershell
git remote set-url bitbucket https://scm.mastercard.int/stash/scm/~e176097/dispatch.git
```

Do not push from an agent session unless the user explicitly asks for the push.

## First-Time Local Setup

```powershell
py -m pip install -r requirements.txt -r requirements-dev.txt -c constraints.txt
```

## Daily Loop

1. Inspect branch and local changes:

```powershell
git status --short --branch
git branch -vv
```

2. Make the change and run focused tests.

3. Run the standard local gate:

```powershell
.\tools\dev\local_check.ps1
```

The script runs compile, lint, typecheck, full gate, and pytest using the repo
standard `py` launcher.

4. Commit locally after review:

```powershell
git diff
git add <files>
git commit -m "Describe the change"
```

5. Check remote sync state:

```powershell
.\tools\dev\git_sync_status.ps1
```

6. Push to Bitbucket only when ready for server update:

```powershell
git push -u bitbucket HEAD
```

## Edge Node Update

Preferred deployment path:

```bash
cd /ads_storage/autobench
git fetch bitbucket
git checkout main
git pull --ff-only bitbucket main
AUTOBENCH_PYTHON_BIN=$(command -v python3.11 || command -v python3.10) ./install.sh
```

For release validation or rollback, use an exact commit:

```bash
cd /ads_storage/autobench
git fetch bitbucket
git checkout <commit-sha>
./install.sh
```

Treat each Edge Node as independent until shared storage is proven. Validate
each node separately and name the node in every production claim.

## Full Bundle Deploy

Use the existing offline path for first-time setup, dependency wheel refreshes,
or recovery when Git access from the node is unavailable:

```powershell
.\deploy_and_install.ps1
```

The generated `autobench_deploy.zip` is an artifact and must not be committed.

## Production Validation

After deployment, run the production harness with the node-specific config:

```powershell
py -m tools.prod_tui smoke --config tools/prod_tui/config-node04.yaml --level 2 --save-screens
py -m tools.prod_tui drift --local . --remote /ads_storage/autobench
```

For changes that affect end-to-end analysis behavior, also run the repository
gate on the deployed tree:

```bash
cd /ads_storage/autobench
autobench-cli config list
autobench-cli share --csv tests/fixtures/gate_demo.csv --entity Target --metric txn_cnt --dimensions card_type channel --time-col year_month --preset balanced_default --export-balanced-csv --output /tmp/autobench_smoke.xlsx
```

## Change Hygiene

- Do not commit generated bundles, reports, logs, screens, or local data.
- Do not commit credentials, passcodes, personal config, or internal screenshots.
- Prefer exact commit checkout for production promotion and rollback.
- After manual server edits, run drift detection before claiming parity.
