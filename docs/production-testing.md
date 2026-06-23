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
Do not commit personal credentials or passcodes.

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
py -m tools.prod_tui drift --local .
```

The report ignores generated reports, logs, screens, caches, bytecode, local
data, and output directories. A zero-drift deployment should be recorded as:

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
writing output.
