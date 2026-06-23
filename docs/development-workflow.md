# Autobench Development Workflow

This is the canonical workflow for making Autobench changes locally, publishing
them to the corporate deployment remote, and updating Hadoop Edge Nodes in a way
that can be traced to a Git commit.

## Remotes

Keep remote roles explicit:

- `origin`: GitHub mirror/review remote (full branch history).
- `bitbucket`: corporate deployment remote — the **`autobench`** repo reachable by
  the Edge Nodes. (An older `dispatch` repo was used by mistake; it is obsolete —
  always target `autobench`.)

Configure Bitbucket once:

```powershell
git remote add bitbucket https://scm.mastercard.int/stash/scm/~e176097/autobench.git
git remote -v
```

If the remote already exists with another URL (e.g. the old `dispatch` URL):

```powershell
git remote set-url bitbucket https://scm.mastercard.int/stash/scm/~e176097/autobench.git
```

Bitbucket is SSO-protected. Authenticate fetches/pushes with a personal HTTP
access token (PAT) passed as a Bearer header instead of an interactive prompt:

```powershell
$env:BB_TOKEN = "<your-bitbucket-PAT>"
git -c "http.extraHeader=Authorization: Bearer $env:BB_TOKEN" ls-remote bitbucket main
```

Never commit the PAT. Do not push from an agent session unless the user
explicitly asks for the push.

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

6. Publish to Bitbucket only when ready for a server update — see
   [Publish to Bitbucket](#publish-to-bitbucket-deployment-snapshot) below.

## Publish to Bitbucket (Deployment Snapshot)

The `bitbucket` (`autobench`) repo does **not** share history with local `main`,
and a pre-receive hook rejects any commit you did not author ("you can only push
your own commits"). So you cannot push your full `main` history — publish a single
**deployment snapshot** of `main`'s tree, re-parented on the current
`bitbucket/main` and authored by you. This is always a clean fast-forward; never
force-push.

```powershell
$env:BB_TOKEN = "<your-bitbucket-PAT>"
git -c "http.extraHeader=Authorization: Bearer $env:BB_TOKEN" fetch bitbucket
$short = git rev-parse --short main
git checkout --detach main
git reset --soft bitbucket/main
git commit -m "Deploy snapshot: autobench main $short ($(Get-Date -Format 'yyyy-MM-dd HH:mm'))"
git -c "http.extraHeader=Authorization: Bearer $env:BB_TOKEN" push bitbucket "HEAD:main"
git checkout main
```

`reset --soft bitbucket/main` keeps `main`'s working tree but re-parents the new
commit onto Bitbucket's tip, so the push fast-forwards. The closing
`git checkout main` leaves local `main` untouched: Bitbucket only ever receives
snapshots derived from `main` — never pull Bitbucket back into local `main`.

Do not use `git commit-tree` for the snapshot; in agent sessions the git wrapper
injects a trailer and mangles it. Use the detached-HEAD sequence above.

## Edge Node Update

Preferred deployment path — run the tracked updater:

```bash
cd /ads_storage/autobench
./update.sh
```

`update.sh` runs `git fetch` + `git reset --hard bitbucket/main`, then re-applies
shared read/execute permissions (`chmod -R a+rX`). The hard reset (not
`git pull`) guarantees the tree — content **and** line endings — exactly matches
the repo: `.gitattributes` pins `*.sh` to LF, so script shebangs stay valid even
if a file was ever touched from a Windows working tree. The reset also restores
the executable bit on entrypoint scripts (`run_tool.sh`, `install.sh`, etc.).
Untracked paths such as `.venv/` and `offline_packages/` are preserved, so the
installed environment survives the update. (Override the source with
`AUTOBENCH_GIT_REMOTE` / `AUTOBENCH_GIT_BRANCH` if needed; defaults are
`bitbucket` / `main`.)

Always update through `update.sh` (Git), never by copying or `scp`-ing individual
files onto the node — out-of-band copies reintroduce CRLF line endings and drift
the tree from Git.

Run `./install.sh` only when dependencies changed (new/updated offline wheels):

```bash
cd /ads_storage/autobench
./update.sh
./install.sh   # only when the offline bundle changed
```

`install.sh` auto-selects an interpreter matching the bundled offline wheels
(currently CPython 3.10). Only set `AUTOBENCH_PYTHON_BIN=/path/to/python3.10`
if the node hides the right interpreter from the installer's search.

For release validation or rollback, reset to an exact snapshot commit:

```bash
cd /ads_storage/autobench
git fetch bitbucket
git reset --hard <commit-sha>
chmod -R a+rX .
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
- Prefer resetting to an exact snapshot commit for production promotion and rollback.
- After manual server edits, run drift detection before claiming parity.
