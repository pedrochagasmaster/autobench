# Autobench Edge Node First-Time Setup

This runbook bootstraps Autobench on a Hadoop Edge Node.

## 1. Prepare the Deployable Tree

The preferred ongoing model is a Git working tree backed by the corporate remote:

```bash
cd /ads_storage
git clone -o bitbucket https://scm.mastercard.int/stash/scm/~e176097/dispatch.git autobench
cd /ads_storage/autobench
git remote -v
```

If the node cannot reach Git, use the existing offline bundle workflow:

```powershell
.\deploy_and_install.ps1
```

The bundle path remains a fallback for first-time setup, dependency refresh, and
recovery. The Git path is the preferred repeatable deployment model.

## 2. Verify Prerequisites

SSH to the node and confirm Python and storage:

```bash
ssh -p 2222 <user>@<edge-node>
python3.11 --version || python3.10 --version || /sys_apps_01/python/python310/bin/python3.10 --version
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
AUTOBENCH_PYTHON_BIN=$(command -v python3.11 || command -v python3.10) ./install.sh
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

## Troubleshooting

| Issue | Cause | Fix |
|---|---|---|
| `autobench: command not found` | Shell has not picked up `~/.local/bin` | Run `export PATH="$HOME/.local/bin:$PATH"` or open a new SSH session. |
| Dependency install fails | No internet and no offline wheels | Refresh `offline_packages/` with `deploy_and_install.ps1`. |
| Output write fails | Working directory not writable | Run from a writable directory or choose an output path under `/tmp` or `/ads_storage/$USER`. |
| Git prompts during pull | Remote credentials not cached/configured | Configure an approved read-only credential strategy before automating pulls. |
