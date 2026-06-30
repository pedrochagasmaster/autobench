# Autobench Edge Deploy Workflow

Run normal releases from `D:\Projects\edge-deploy-core`, not from this repo.

## 1. Default Release

```powershell
cd D:\Projects\autobench
git status --short --branch
.\tools\dev\local_check.ps1
git add <files>
git commit -m "Describe the change"

cd D:\Projects\edge-deploy-core
py -m edge_deploy release --tool autobench --smoke standard
```

Use `--tool both` when Autobench and Dispatch should be released in the same
process.

The release command owns:

- deployment snapshot publication,
- node03 and node04 update,
- interactive RSA prompt handling in the visible terminal,
- safe Git preflight and bounded remote-tracking-ref repair,
- drift and smoke validation,
- JSON release reports under `edge-deploy\reports\release-*`.

## 2. Release Evidence

Accept the release only when:

- `release.json` has `overall_status: "passed"`,
- each Autobench rollout report has `status: "passed"`,
- update, drift, and smoke checks passed for node03 and node04,
- `remote_git_preflight` is present for each node,
- no secret-shaped values are present in the report.

Report the release directory, local source commit, deployment SHA, nodes
updated, and any authentication handoff.

## 3. Recovery Entry Criteria

Use the remaining sections only when:

- the release command is unavailable,
- a release report points to a node-specific condition that needs manual
  inspection,
- a first-time node bootstrap is required,
- offline dependencies must be refreshed outside the orchestrator.

Do not use these commands as the normal release workflow.

## 4. Repo-Local Snapshot Recovery

Autobench Bitbucket history may not share local `main` history and may reject
commits not authored by the current user. If the orchestrator cannot publish,
the repo-local helper can create a deployment snapshot:

```powershell
cd D:\Projects\autobench
$env:BB_TOKEN = "<your-bitbucket-PAT>"
.\tools\dev\publish_bitbucket_snapshot.ps1
git fetch bitbucket main
git log --oneline -1 bitbucket/main
```

Never commit the PAT. Record why the orchestrator publish path was bypassed.

## 5. Manual Node Recovery

Prepare authenticated sessions only after inspecting current panes:

```powershell
tmux ls
tmux list-panes -a -F "#{session_name}:#{window_index}.#{pane_index} #{pane_current_command} #{pane_current_path}"
tmux capture-pane -t <session> -p -S -80
```

If SSH has logged out, restart SSH and let the human enter the RSA PASSCODE.

On the node, the recovery update shape is:

```bash
cd /ads_storage/autobench
AUTOBENCH_GIT_REMOTE=bitbucket AUTOBENCH_GIT_BRANCH=main ./update.sh
git log --oneline -1
git status --porcelain
```

`update.sh` preserves untracked runtime paths, reasserts shared permissions,
and repairs the known corrupt `refs/remotes/bitbucket/main` signature. If the
script reports `install required` or dependencies changed, run:

```bash
cd /ads_storage/autobench
./install.sh
cat /ads_storage/$USER/.autobench/installed_version
```

## 6. Offline Bootstrap or Dependency Recovery

Use the bundle path only for first-time setup, dependency wheel refreshes, or
recovery when Git access from the node is not usable:

```powershell
cd D:\Projects\autobench
.\deploy_and_install.ps1
```

The generated `autobench_deploy.zip` is an artifact and must not be committed.

## 7. Recovery Smoke and Drift

From the local repo:

```powershell
py -m tools.prod_tui smoke --config tools/prod_tui/config-node04.yaml --level 2 --save-screens
py -m tools.prod_tui drift --local . --remote /ads_storage/autobench
```

From the deployed tree:

```bash
cd /ads_storage/autobench
python -m compileall benchmark.py tui_app.py core utils scripts tools
./run_tool.sh config list
./run_tool.sh share --help
./run_tool.sh share --csv tests/fixtures/gate_demo.csv --entity Target --metric txn_cnt --dimensions card_type channel --time-col year_month --preset balanced_default --export-balanced-csv --output /tmp/autobench_smoke.xlsx
```

## 8. Final Recovery Report

Include:

- why the default `edge_deploy release` path was not sufficient,
- local source commit,
- deployment SHA,
- nodes touched,
- remote update/install/smoke evidence,
- drift evidence,
- shared-permission evidence,
- any authentication or remote-state issue.
