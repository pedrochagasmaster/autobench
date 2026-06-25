# Autobench Edge Deploy Workflow

Run from `D:\Projects\autobench` unless a command is explicitly remote.

## 1. Local Preflight

```powershell
git status --short --branch
git remote -v
git log --oneline --decorate --max-count=8
.\tools\dev\local_check.ps1
```

If the worktree is dirty, identify whether the dirt belongs to the current deployment work. Preserve unrelated user changes. Do not commit generated bundles, reports, logs, screenshots, local data, or credentials.

## 2. Confirm Bitbucket Remote

The deployment remote must be the corporate Autobench repo:

```powershell
git remote -v
git remote set-url bitbucket https://scm.mastercard.int/stash/scm/~e176097/autobench.git
```

Do not deploy Autobench to the old `dispatch.git` remote.

## Deployment Decision Table

| Situation | Use | Why |
| --- | --- | --- |
| Normal daily deployment | `./update.sh` | Git update of `/ads_storage/autobench` without reinstalling user runtime state. |
| Dependencies, interpreter, or launcher inputs changed | `./update.sh` then `./install.sh` | Shared tree changes landed, then per-user runtime is refreshed only when needed. |
| Git unavailable on the node, first-time setup, or recovery | `./deploy_and_install.ps1` | Offline bundle path for bootstrap or recovery when the Git path cannot complete. |
| Need a known-good production state | exact-SHA `git reset --hard <snapshot-sha>` | Node-specific rollback or validation against a named Bitbucket snapshot. |

## 3. Publish a Deployment Snapshot

Autobench Bitbucket history may not share local `main` history and may reject commits not authored by the current user. Use the documented detached-HEAD snapshot sequence, not a direct local-history push:

```powershell
$env:BB_TOKEN = "<your-bitbucket-PAT>"
.\tools\dev\publish_bitbucket_snapshot.ps1
git fetch bitbucket main
git log --oneline -1 bitbucket/main
```

Never commit the PAT. If interactive Bitbucket auth is required, leave a tmux or terminal prompt ready for user takeover instead of retrying blindly.

## 4. Prepare Authenticated Edge Sessions

Inspect sessions before sending commands:

```powershell
tmux ls
tmux list-panes -a -F "#{session_name}:#{window_index}.#{pane_index} #{pane_current_command} #{pane_current_path}"
tmux capture-pane -t <session> -p -S -80
```

If SSH has auto-logged out, put the pane back at PASSCODE prompt:

```powershell
tmux send-keys -t <session> 'ssh -p 2222 -o ServerAliveInterval=30 e176097@hde2stl020003.mastercard.int' Enter
tmux send-keys -t <session> 'ssh -p 2222 -o ServerAliveInterval=30 e176097@hde2stl020004.mastercard.int' Enter
```

Wait for the user to authenticate and confirm remote shell prompts before running mutating commands.

## 5. Update Each Node Through Git

Use `update.sh` for the normal path:

```bash
cd /ads_storage/autobench
AUTOBENCH_GIT_REMOTE=bitbucket AUTOBENCH_GIT_BRANCH=main ./update.sh
git log --oneline -1
git status --porcelain
```

For rollback or exact snapshot validation:

```bash
cd /ads_storage/autobench
git fetch bitbucket
git reset --hard <snapshot-sha>
chmod -R a+rX .
git log --oneline -1
git status --porcelain
```

Use `tmux send-keys -l` when injecting complex commands from PowerShell:

```powershell
$cmd = @'
cd /ads_storage/autobench && echo __AUTOBENCH_NODE_DEPLOY_START__ && AUTOBENCH_GIT_REMOTE=bitbucket AUTOBENCH_GIT_BRANCH=main ./update.sh && git log --oneline -1 && git status --porcelain && echo __AUTOBENCH_NODE_DEPLOY_END__
'@
tmux send-keys -t <session> -l $cmd
tmux send-keys -t <session> Enter
```

Poll until markers appear:

```powershell
tmux capture-pane -t <session> -p -S -160
```

## 6. Refresh Offline Dependencies When Needed

Use this path for first-time setup, dependency wheel refreshes, or recovery when Git access from the node is unavailable:

```powershell
.\deploy_and_install.ps1
```

The script:

- downloads Linux CPython 3.10 / `cp310` wheels into `offline_packages/`,
- writes `SHA256SUMS`,
- creates `autobench_deploy.zip`,
- uploads it to `/ads_storage/autobench`,
- extracts it remotely,
- runs `setup_remote_env.sh`.

On-node manual equivalent:

```bash
cd /ads_storage/autobench
/sys_apps_01/python/python310/bin/python3.10 -m zipfile -e autobench_deploy.zip .
chmod +x setup_remote_env.sh
./setup_remote_env.sh
```

If `setup_remote_env.sh` cannot install `textual<7,>=0.40.0` or other pinned packages, rebuild and re-upload a fresh offline bundle. Do not trust a stale archived `offline_packages/` cache.

## 7. Install Per-User Launchers

Run when user launchers or per-user venv need refresh:

```bash
cd /ads_storage/autobench
./install.sh
cat /ads_storage/$USER/.autobench/installed_version
export PATH="$HOME/.local/bin:$PATH"
which autobench
which autobench-cli
autobench-cli config list
```

`install.sh` auto-selects an interpreter matching bundled wheel ABI tags. Only set `AUTOBENCH_PYTHON_BIN=/path/to/python3.10` when the node hides the matching interpreter.

## 8. Remote Smoke Checks

From `/ads_storage/autobench`:

```bash
python -m compileall benchmark.py tui_app.py core utils scripts tools
./run_tool.sh config list
./run_tool.sh share --help
./run_tool.sh share \
  --csv tests/fixtures/gate_demo.csv \
  --entity Target \
  --metric txn_cnt \
  --dimensions card_type channel \
  --time-col year_month \
  --preset balanced_default \
  --export-balanced-csv \
  --output /tmp/autobench_smoke.xlsx
```

If using per-user launchers, also verify:

```bash
autobench-cli config list
autobench-cli share --csv tests/fixtures/gate_demo.csv --entity Target --metric txn_cnt --dimensions card_type channel --time-col year_month --preset balanced_default --export-balanced-csv --output /tmp/autobench_cli_smoke.xlsx
```

## 9. Production Harness and Drift

Use node-specific configs when present:

```powershell
py -m tools.prod_tui smoke --config tools/prod_tui/config-node04.yaml --level 2 --save-screens
py -m tools.prod_tui drift --local . --remote /ads_storage/autobench
```

For behavior changes, run Level 3 controlled analysis only against tracked fixtures or scratch output paths.

## 10. Shared Permissions

Apply on each node:

```bash
cd /ads_storage/autobench
chmod 755 /ads_storage/autobench
chmod -R a+rX /ads_storage/autobench
chmod a+x /ads_storage/autobench/*.sh
```

Verify with quote-free commands:

```bash
ls -ld /ads_storage/autobench
ls -l /ads_storage/autobench/*.sh
find /ads_storage/autobench -type d ! -perm -001 -print | head -20
```

Expected evidence:

- `/ads_storage/autobench` is `drwxr-xr-x` or more permissive.
- `install.sh`, `update.sh`, `setup_remote_env.sh`, and `run_tool.sh` are `-rwxr-xr-x` or more permissive.
- The non-world-traversable directory scan prints no paths.

## 11. Final Report

Include:

- local source commit
- Bitbucket snapshot SHA
- nodes updated
- local `tools/dev/local_check.ps1` result
- remote `update.sh` or offline bundle result
- remote compile / wrapper / launcher smoke result
- production harness and drift result, if run
- shared-permission evidence
- any auth handoff, stale remote, or package-cache issue
