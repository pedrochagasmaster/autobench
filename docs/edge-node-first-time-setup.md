# Autobench Edge Node First-Time Setup

This runbook bootstraps Autobench on a Hadoop Edge Node. It is not the default
release workflow. After bootstrap, use the installed `edge-deploy-core`
package:

```powershell
py -m edge_deploy release --tool autobench --smoke standard
```

## 1. Prepare the Deployable Tree

The preferred ongoing model is a Git working tree backed by the corporate remote:

```bash
cd /ads_storage
git clone -o bitbucket https://scm.mastercard.int/stash/scm/~e176097/autobench.git autobench
cd /ads_storage/autobench
git remote -v
```

If the node cannot reach Git, use the existing offline bundle workflow:

```powershell
.\deploy_and_install.ps1
```

The bundle path remains a fallback for first-time setup, dependency refresh, and
recovery. A Git-backed shared tree is preferred for bootstrap because the
default `edge_deploy release` workflow can then manage repeatable updates.

## Release and Bootstrap Decision Table

| Situation | Use | Why |
| --- | --- | --- |
| Normal development release | `py -m edge_deploy release --tool autobench --smoke standard` | Default release path after the node is bootstrapped. |
| First-time Git tree setup | `git clone -o bitbucket ... /ads_storage/autobench` | Creates the shared tree the orchestrator updates. |
| Git unavailable, offline dependency refresh, or recovery | `deploy_and_install.ps1`, `setup_remote_env.sh`, `install.sh` | Bootstrap/recovery only. |
| Node-specific diagnosis | `update.sh`, `tools.prod_tui`, tmux/SSH inspection | Deep troubleshooting after reviewing the release report. |

## 2. Verify Prerequisites

SSH to the node and confirm Python and storage:

```bash
ssh -p 2222 <user>@<edge-node>
# The offline bundle ships CPython 3.10 (cp310) wheels, so confirm 3.10 is present:
/sys_apps_01/python/python310/bin/python3.10 --version || python3.10 --version
mkdir -p /ads_storage/$USER/.autobench
touch /ads_storage/$USER/.autobench/.smoke_test
```

If the workflow requires Kerberos-backed data access, initialize Kerberos before
running analyses:

```bash
kinit
klist
```

## 3. Install for the Current User

```bash
cd /ads_storage/autobench
chmod +x install.sh
./install.sh
```

The installer reads the CPython ABI tag of the bundled offline wheels (currently
`cp310`) and automatically selects a matching `python3.10` interpreter, so you do
not normally set `AUTOBENCH_PYTHON_BIN`. If the node has only a mismatched
interpreter (for example `python3.11`), the installer stops with a clear message
rather than failing later inside pip; install Python 3.10 or point it at one:

```bash
AUTOBENCH_PYTHON_BIN=/sys_apps_01/python/python310/bin/python3.10 ./install.sh
```

The installer creates `/ads_storage/$USER/.autobench`, installs dependencies
into that user's virtualenv, writes `~/.local/bin/autobench` and
`~/.local/bin/autobench-cli`, and records `/ads_storage/$USER/.autobench/installed_version`.

## 4. Post-Install Checks

```bash
export PATH="$HOME/.local/bin:$PATH"
which autobench
which autobench-cli
autobench-cli config list
```

Run a small share smoke:

```bash
cd /ads_storage/autobench
autobench-cli share \
  --csv tests/fixtures/gate_demo.csv \
  --entity Target \
  --metric txn_cnt \
  --dimensions card_type channel \
  --time-col year_month \
  --preset balanced_default \
  --export-balanced-csv \
  --output /tmp/autobench_setup_smoke.xlsx
```

## 5. Hand Off to End Users

After the shared tree is deployed, send users the short flow in
[`onboarding.md`](../onboarding.md). They should not need Git, bundle, or
rollback details to launch the TUI.

## 6. Updating the Deployment

For normal releases, do not update the node by hand. Use the installed
`edge-deploy-core` release orchestrator:

```powershell
py -m edge_deploy release --tool autobench --smoke standard
```

For bootstrap recovery or a node-specific repair, update through Git, never by
copying or `scp`-ing individual files onto it. Out-of-band copies from a
Windows working tree reintroduce CRLF line endings and leave the tree drifted
from Git.

Recovery command from the node:

```bash
cd /ads_storage/autobench
./update.sh            # recovery Git fetch + reset --hard to the canonical branch
```

`update.sh` preserves untracked files and is also used internally by the
orchestrator. If running it manually, record why the default release command was
not enough, then capture the install decision, dependency signal, drift result,
and smoke result.

## Troubleshooting

| Issue | Cause | Fix |
|---|---|---|
| `autobench: command not found` | Shell has not picked up `~/.local/bin` | Run `export PATH="$HOME/.local/bin:$PATH"` or open a new SSH session. |
| Dependency install fails | No internet and no offline wheels | Refresh `offline_packages/` with `deploy_and_install.ps1`. |
| Output write fails | Working directory not writable | Run from a writable directory or choose an output path under `/tmp` or `/ads_storage/$USER`. |
| Git prompts during pull | Remote credentials not cached/configured | Configure an approved read-only credential strategy before automating pulls. |
