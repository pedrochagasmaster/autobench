# Autobench Production Testing

Autobench production validation uses the same operating model as Dispatch:

```text
local machine
  tmux or psmux session
    pane: ssh -p 2222 <user>@<edge-node>
      remote shell
        cd /ads_storage/autobench
        autobench
```

The harness lives in `tools/prod_tui/`. It records JSON reports under
`tools/prod_tui/reports/`, optional screen captures under
`tools/prod_tui/screens/`, and logs under `tools/prod_tui/logs/`.

For normal production releases, run the shared orchestrator instead of driving
this harness directly:

```powershell
python -m edge_deploy release
```

Use this document for deeper validation, recovery, or diagnosis after reviewing
the release report.

## Configure

Copy the template for each node:

```powershell
Copy-Item tools/prod_tui/config-template.yaml tools/prod_tui/config-node04.yaml
```

Set `host`, `repo_path`, `session_name`, terminal size, and any SSH options.
Populate the report-contract fields in the node config as needed:
`source_commit`, `bitbucket_snapshot_sha`, `deployed_commit`,
`runtime_python_path`, `runtime_python_version`, `update_method`,
`active_runtime_path`, `runtime_digest`, `delivered_bundle_digest`,
`runtime_pip_check`, `install_decision`, `dependency_signal`, and
`permission_evidence`. Do not
commit personal credentials or passcodes. Prefer copying `permission_evidence`
from the `update.sh` or `setup_remote_env.sh` output instead of typing it by
hand.

Before sending commands to any session, prove you are targeting the intended
remote shell:

```powershell
tmux ls
tmux list-panes -a -F "#{session_name}:#{window_index}.#{pane_index} #{pane_current_command} #{pane_current_path}"
tmux capture-pane -t <session> -p -S -80
```

If SSH has auto-logged out, stop at the PASSCODE prompt and hand control to the
human operator. Agents may prepare SSH commands and record auth state in the
report, but humans enter credentials. A blocked auth flow should end in a ready
human takeover, not repeated retries.

## Level 1: Safe TUI Smoke

```powershell
py -m tools.prod_tui smoke --config tools/prod_tui/config-node04.yaml --level 1 --save-screens
```

Checks:

- tmux/SSH session is alive,
- terminal geometry is recorded,
- `py -m compileall benchmark.py tui_app.py core utils` succeeds remotely,
- TUI launch command starts,
- help and quit paths are exercised when a terminal session is available.

## Level 2: Environment Checks

```powershell
py -m tools.prod_tui smoke --config tools/prod_tui/config-node04.yaml --level 2 --save-screens
```

Adds:

- `.venv/current` resolves physically under `.venv/releases/`,
- completion metadata and delivered bundle digests agree,
- prior `pip check` passed and all required imports succeed,
- both shared CLI smoke commands exit zero,
- runtime-critical files are readable and shared launchers are executable,
- no runtime entry is group- or world-writable.

Exact operator checks:

```bash
readlink -f /ads_storage/autobench/.venv/current
/ads_storage/autobench/bin/autobench-cli config list
/ads_storage/autobench/bin/autobench-cli share --help
```

## Shared Telemetry Filesystem Validation

After `update.sh` (or an orchestrated release that runs it), validate the
portable shared telemetry mount on the actual node. Do not substitute a local
tmpfs run for edge acceptance of these guarantees.

```bash
cd /ads_storage/autobench
python scripts/validate_telemetry_filesystem.py
python scripts/validate_telemetry_filesystem.py --dir /ads_storage/autobench/telemetry
```

Use an absolute `--dir` with `scripts/validate_telemetry_filesystem.py` (and
absolute `AUTOBENCH_TELEMETRY_DIR` for trusted provisioning). Relative paths,
lexical `.` / `..` components, and symlink ancestors in the shared path are
rejected before probes. This does not describe `benchmark.py telemetry … --dir`
aggregation-CLI behavior.

Expected status: every line is `PASS: ...` and the process exits `0`. Any
`FAIL: ...` line with exit `1` means shared telemetry must stay gated off until
operators repair the mount; do not weaken the runtime capability gate to force
shared writes.

The validator checks Linux primitives (`O_APPEND`, `O_NOFOLLOW`, `O_NONBLOCK`,
`O_CLOEXEC`, nonblocking `flock`), `/proc/sys/fs/protected_hardlinks == 1`,
parent mode `0755` and `users` mode `1777` (real non-symlink dirs owned by the
trusted effective uid), safe `O_EXCL|O_NOFOLLOW` probe creation, `fstat`
owner/nlink reporting, append-despite-seek, final `0644`, contended/released
child flock behavior, timeout-bounded FIFO `O_NONBLOCK` open, symlink rejection,
and same-directory rename inode/content preservation. It never reads telemetry
payloads.

Cross-user sticky deletion is outside this script's scope; perform a separate
two-account operational check for sticky/precreation behavior. When shared
capability fails, shared writes stay disabled and private telemetry remains the
fallback. Flag owner/token mismatches during monitoring. Retention and deletion
authorization are operator-owned. Telemetry remains self-reported product data,
not an audit log.

Confirm trusted provisioning evidence from `update.sh` shows:

```text
Telemetry permission evidence:
drwxr-xr-x ... /ads_storage/autobench/telemetry
drwxrwxrwt ... /ads_storage/autobench/telemetry/users
```

## Level 3: Controlled Analysis

Use only a known fixture and a scratch output path:

```powershell
py -m tools.prod_tui smoke --config tools/prod_tui/config-node04.yaml --level 3 --save-screens
```

The controlled action is equivalent to:

```bash
autobench-cli share --csv tests/fixtures/gate_demo.csv --entity Target --metric txn_cnt --dimensions card_type channel --time-col year_month --preset balanced_default --export-balanced-csv --output /tmp/autobench_prod_smoke.xlsx
```

Never use arbitrary user files as a production smoke fixture.

## Drift

To compare deployable files in the local tree:

```powershell
py -m tools.prod_tui drift --local . --remote /ads_storage/autobench
```

The report ignores generated reports, logs, screens, caches, bytecode, local
data, and output directories. When `--remote` is provided, the path is recorded
in the report and summary line, but live remote filesystem comparison is not
yet implemented. In that mode the harness must not claim zero drift or
`IN_SYNC`; it should report the remote comparison as not implemented. A
local-only zero-drift run may be recorded as:

```text
MATCH=<n> DRIFT=0 IN_SYNC
```

## Failure Classes

The JSON report uses these failure classes:

- `harness`: local tmux/psmux, SSH config, or harness command failure.
- `environment`: Python, storage, launcher, or dependency failure.
- `deployment`: commit, version, installed tree, or drift mismatch.
- `tui`: render, keybinding, quit, or terminal behavior failure.
- `workflow`: controlled fixture analysis failure.

Generated reports redact common token, password, and passcode patterns before
writing output. The smoke report can carry source/snapshot/deployed commit
metadata, runtime Python, update method, install decision, dependency signal,
runtime/bundle digest evidence, prior `pip check`, drift and smoke blocks,
wrapper checks, permission evidence, and auth handoff state.

## Human-Gated Edge Acceptance

Human-gated Edge acceptance starts only after the operator has a node-specific
deployment or rollback target. Record the node, old SHA, rollback SHA (target
SHA), smoke level, and wrapper checks in the acceptance note or handoff.

Use local verification to qualify code before deployment, but local verification
is not a substitute for real Edge acceptance when SSH, Kerberos, storage,
permissions, tmux, or launcher behavior are in scope.

On node03 and then node04, also verify two analysts resolve the same physical
runtime while their `.autobench` homes remain separate. Start a long-lived
process, activate another completed digest, and confirm the old process remains
bound to its original runtime. Test rollback by reactivating the retained prior
digest. Personal virtual environments and old shared runtimes remain on disk
until separately approved cleanup.
