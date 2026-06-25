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

## Configure

Copy the template for each node:

```powershell
Copy-Item tools/prod_tui/config-template.yaml tools/prod_tui/config-node04.yaml
```

Set `host`, `repo_path`, `session_name`, terminal size, and any SSH options.
Populate the report-contract fields in the node config as needed:
`source_commit`, `bitbucket_snapshot_sha`, `deployed_commit`,
`runtime_python_path`, `runtime_python_version`, `update_method`,
`install_decision`, `dependency_signal`, and `permission_evidence`. Do not
commit personal credentials or passcodes.

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

- `./install.sh` can run,
- `autobench` and `autobench-cli` resolve,
- `/ads_storage/$USER/.autobench/installed_version` matches `VERSION`,
- runtime home is writable,
- the deployed path is the expected repo path.

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
drift and smoke blocks, wrapper checks, permission evidence, and auth handoff
state.

## Human-Gated Edge Acceptance

Human-gated Edge acceptance starts only after the operator has a node-specific
deployment or rollback target. Record the node, old SHA, rollback SHA (target
SHA), smoke level, and wrapper checks in the acceptance note or handoff.

Use local verification to qualify code before deployment, but local verification
is not a substitute for real Edge acceptance when SSH, Kerberos, storage,
permissions, tmux, or launcher behavior are in scope.
