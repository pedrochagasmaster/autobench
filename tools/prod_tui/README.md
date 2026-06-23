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

Set `host`, `repo_path`, `session_name`, terminal size, and SSH options. Do not
store passcodes, passwords, or tokens in config files.

## Commands

```powershell
py -m tools.prod_tui
py -m tools.prod_tui smoke --config tools/prod_tui/config-node04.yaml --level 1 --save-screens
py -m tools.prod_tui drift --local .
```

`smoke` writes JSON reports under `tools/prod_tui/reports/`. `drift` builds a
runtime-file manifest that excludes generated reports, screens, logs, caches,
data, and outputs.

For the full process, see `docs/production-testing.md`.
