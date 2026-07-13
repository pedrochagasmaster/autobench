# Autobench Edge Node First-Time Setup

This runbook bootstraps Autobench on a Hadoop Edge Node. It is not the default
release workflow. After bootstrap, use the installed `edge-deploy-core`
package:

```powershell
python -m edge_deploy release
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
| Normal operator release | `python -m edge_deploy release` | Default release path after the node is bootstrapped. |
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
python -m edge_deploy release
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

## 7. Shared Offline Telemetry Layout

Trusted `update.sh` (deployment owner) provisions the portable shared telemetry
tree after each reset. Per-user `install.sh` never creates these shared parents;
it only prepares the private home under `/ads_storage/$USER/.autobench`.

Exact layout and modes:

| Path | Mode | Role |
| --- | --- | --- |
| `/ads_storage/autobench/telemetry` | `0755` | Shared telemetry parent (trusted owner) |
| `/ads_storage/autobench/telemetry/users` | `1777` | Sticky world-writable per-user JSONL directory |
| `/ads_storage/autobench/telemetry/users/<token>.jsonl` | `0644` | Per-user shared events (world-readable) |
| `/ads_storage/<user>/.autobench/telemetry/events.jsonl` | private `0600` under `0700` dirs | Private dual-write destination |

Override the shared parent with an absolute `AUTOBENCH_TELEMETRY_DIR` (the
directory whose direct child is `users/`). For trusted provisioning
(`update.sh` / `scripts/provision_telemetry_dirs.sh`) and the filesystem
validator (`scripts/validate_telemetry_filesystem.py --dir`), relative paths and
lexical `.` / `..` components are rejected before any directory mutation or
probe. The aggregation CLI (`benchmark.py telemetry … --dir`) is separate and
is not the enforcement surface described here. Telemetry is default-on;
case-insensitive `AUTOBENCH_TELEMETRY` values `0`, `false`, `off`, or `no`
opt-out of future private and shared writes without deleting existing records.

The portable profile intentionally discloses usernames and approved event data
as world-readable local files. Treat telemetry as self-reported product data,
not an audit record. Retention, rotation, and deletion authorization remain
operator-owned.

If the shared capability gate fails at runtime, shared writes are disabled and
private writes continue. A failing operator validator must not be used as a
reason to weaken the runtime gate. Monitor owner/token mismatches (possible
username pre-creation denial of service). Sticky cross-user deletion and
precreation behavior require a separate two-account operational check; the
filesystem validator does not exercise cross-user sticky deletion.

Validate on the actual edge-node mount (assumptions: Linux,
`O_APPEND` / `O_NOFOLLOW` / `O_NONBLOCK` / `O_CLOEXEC`, nonblocking `flock`,
sticky `1777`, `fstat`, same-directory rename, and
`/proc/sys/fs/protected_hardlinks == 1`):

```bash
cd /ads_storage/autobench
python scripts/validate_telemetry_filesystem.py
# or: python scripts/validate_telemetry_filesystem.py --dir /ads_storage/autobench/telemetry
```

`--dir` for `scripts/validate_telemetry_filesystem.py` and
`AUTOBENCH_TELEMETRY_DIR` for trusted provisioning must name an absolute
telemetry parent (the directory whose direct child is `users/`). This absolute /
no-`.` / no-`..` policy applies to those operator inputs, not to the aggregation
CLI's `--dir`.

Expect deterministic `PASS:` lines and exit status `0`. Any `FAIL:` line with
exit status `1` is actionable; do not treat the run as successful.

## Troubleshooting

| Issue | Cause | Fix |
|---|---|---|
| `autobench: command not found` | Shell has not picked up `~/.local/bin` | Run `export PATH="$HOME/.local/bin:$PATH"` or open a new SSH session. |
| Dependency install fails | No internet and no offline wheels | Refresh `offline_packages/` with `deploy_and_install.ps1`. |
| Output write fails | Working directory not writable | Run from a writable directory or choose an output path under `/tmp` or `/ads_storage/$USER`. |
| Git prompts during pull | Remote credentials not cached/configured | Configure an approved read-only credential strategy before automating pulls. |
