# Autobench Production TUI Harness

This directory contains the local tmux/psmux + SSH harness for validating the
real Autobench Textual TUI on a Hadoop Edge Node.

## Prerequisites

- `tmux` on Linux/macOS, or `psmux` on Windows.
- `ssh` available locally.
- Autobench deployed at `repo_path` on the Edge Node.
- Python 3.10+ available on the Edge Node.

## Configure

Copy `config-template.yaml` to a node-specific file:

```powershell
Copy-Item tools/prod_tui/config-template.yaml tools/prod_tui/config-node04.yaml
```

Set `host`, `repo_path`, `session_name`, terminal size, SSH options, and the
deployment metadata fields you need for the final report contract:
`source_commit`, `bitbucket_snapshot_sha`, `deployed_commit`,
`runtime_python_*`, `update_method`, `install_decision`, `dependency_signal`,
and `permission_evidence`. Copy the permission evidence from the live
`update.sh` or `setup_remote_env.sh` output; do not invent it in chat. Do not
store passcodes, passwords, or tokens in config files.

Before sending commands to a live node, inspect the tmux session first:

```powershell
tmux ls
tmux list-panes -a -F "#{session_name}:#{window_index}.#{pane_index} #{pane_current_command} #{pane_current_path}"
tmux capture-pane -t <session> -p -S -80
```

Agents may prepare the SSH prompt, but humans enter PASSCODE or any other
credential. If auth blocks the flow, stop with a ready human takeover handoff
instead of retrying blindly.

## Commands

```powershell
py -m tools.prod_tui
py -m tools.prod_tui smoke --config tools/prod_tui/config-node04.yaml --level 1 --save-screens
py -m tools.prod_tui drift --local . --remote /ads_storage/autobench
```

`smoke` writes JSON reports under `tools/prod_tui/reports/`. The report schema
can now carry the source commit, Bitbucket snapshot SHA, deployed commit,
runtime Python, update method, install decision and signal, drift block, smoke
block, wrapper checks, permission evidence, and auth handoff state. `drift`
builds a runtime-file manifest that excludes generated reports, screens, logs,
caches, data, and outputs. When `--remote` is provided, the path is recorded in
the report and summary line, but live remote filesystem comparison is not yet
implemented, so the command must not claim `DRIFT=0` or `IN_SYNC` for remote
mode.

Use the harness outputs as part of human-gated Edge acceptance. For rollback or
promotion, record the node, old SHA, rollback SHA (target SHA), smoke level,
and wrapper checks; local verification is not a substitute for real Edge
acceptance.

For the full process, see `docs/production-testing.md`.
