---
name: autobench-edge-deploy
description: Deploys this repo's Autobench tree to the corporate Bitbucket deployment remote and updates Hadoop Edge Node checkouts under /ads_storage/autobench. Use when the user asks to push Autobench to Bitbucket, update edge nodes, deploy node03/node04, refresh offline packages, run production TUI smoke/drift checks, or make remote Autobench files executable for all users.
---

# Autobench Edge Deploy

Use this skill for Autobench-specific deployment work. It captures the known-good flow for publishing local `main` as a Bitbucket deployment snapshot, updating `/ads_storage/autobench`, refreshing offline dependencies when needed, running Edge Node smoke checks, and enforcing shared permissions.

For exact commands, use [WORKFLOW.md](WORKFLOW.md). Read it before touching the remote nodes.

## Deployment Model

- Local `main` is the source tree.
- `origin` is GitHub and is not the deployment target unless the user explicitly asks.
- `bitbucket` must be the corporate `autobench` repo: `https://scm.mastercard.int/stash/scm/~e176097/autobench.git`.
- Bitbucket does not share local history. Publish a deployment snapshot authored by the current user and parented on `bitbucket/main`; do not push local `main` history directly.
- The shared deployed tree is `/ads_storage/autobench`.
- Per-user runtime state lives under `/ads_storage/$USER/.autobench`.
- `update.sh` is the preferred Git update path. `deploy_and_install.ps1` plus `setup_remote_env.sh` is the offline package refresh or first-time recovery path.

## Standard Nodes

- node03: `hde2stl020003.mastercard.int`
- node04: `hde2stl020004.mastercard.int`

Always inspect live tmux panes before sending commands. If SSH has auto-logged out, start SSH in the pane and let the user enter PASSCODE. Never handle PASSCODE in chat or scripts.

## Required Verification

Before publishing:

- `git status --short --branch`
- `git remote -v`
- `git log --oneline --decorate --max-count=8`
- `.\tools\dev\local_check.ps1`

After Bitbucket push:

- `git fetch bitbucket main`
- `git log --oneline -1 bitbucket/main`

On each node after update:

- `/ads_storage/autobench` is at the deployed snapshot.
- `git status --porcelain` is empty, excluding intentional untracked runtime artifacts.
- `py -m tools.prod_tui drift --local . --remote /ads_storage/autobench` or the node-side drift equivalent reports no unexpected drift.
- `python -m compileall benchmark.py tui_app.py core utils scripts tools` succeeds on the deployed tree.
- `./run_tool.sh config list` and `./run_tool.sh share --help` work from `/ads_storage/autobench`.
- If `install.sh` was run, `/ads_storage/$USER/.autobench/installed_version` matches `VERSION` and `~/.local/bin/autobench-cli config list` works.
- Shared permissions are verified with `ls -ld`, `ls -l`, and a directory traversal scan.

## Operational Lessons

- Prefer `tmux capture-pane` and metadata before attaching or guessing.
- Use authenticated tmux sessions for Edge work; noninteractive SSH may fail on PASSCODE policy.
- Use `tmux send-keys -l` for commands containing quotes, globs, `$USER`, or `$(...)`; plain `send-keys` can mangle shell quoting.
- If a command lands in local PowerShell after SSH logout, stop, reauthenticate, and rerun remotely.
- The offline bundle targets CPython 3.10 / `cp310`; if dependency install fails with wheel compatibility errors, rebuild `offline_packages` with `deploy_and_install.ps1`.
- Linux wrappers must use `python`, not the Windows `py` launcher.
- Do not use the stale `dispatch.git` remote for Autobench deployment.

## Reporting

Report the exact Bitbucket snapshot SHA, local source commit, nodes updated, local validation, remote update/install/smoke evidence, drift evidence, permission evidence, and any auth or remote-state issue.
