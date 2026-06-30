---
name: autobench-edge-deploy
description: Handles Autobench release, recovery, bootstrap, and Edge Node validation. The default release path is edge-deploy-core; repo-local scripts are recovery and diagnostic tools.
---

# Autobench Edge Deploy

Use the shared release orchestrator for normal Autobench releases:

```powershell
cd D:\Projects\edge-deploy-core
py -m edge_deploy release --tool autobench --smoke standard
```

Use `--tool both` for coordinated Autobench + Dispatch releases.

Read [WORKFLOW.md](WORKFLOW.md) before doing any repo-local recovery,
bootstrap, or manual node work.

## Deployment Model

- Local `main` in `D:\Projects\autobench` is the source tree unless the user
  explicitly selects another commit.
- `edge-deploy-core` owns the default publish, node update, drift, smoke, and
  report workflow.
- `origin` is GitHub and is not the deployment target unless the user asks.
- `bitbucket` is the corporate Autobench deployment remote:
  `https://scm.mastercard.int/stash/scm/~e176097/autobench.git`.
- The shared deployed tree is `/ads_storage/autobench`.
- Per-user runtime state lives under `/ads_storage/$USER/.autobench`.
- `update.sh`, `deploy_and_install.ps1`, and `setup_remote_env.sh` are
  bootstrap/recovery tools, not the default release interface.

## Standard Nodes

- node03: `hde2stl020003.mastercard.int`
- node04: `hde2stl020004.mastercard.int`

The release orchestrator opens the SSH flow and waits for human-entered RSA
PASSCODEs. Never handle PASSCODEs in chat, scripts, or config files.

## Required Verification

For the default release, verify:

- `edge-deploy\reports\release-*\release.json` reports success.
- Both Autobench rollout reports passed.
- Drift and smoke checks passed for node03 and node04.
- `remote_git_preflight` is present for each node.
- No secret-shaped values appear in the report.

For recovery work, also record the exact local source commit, deployment SHA,
node, command output, drift result, smoke result, permission evidence, and why
the orchestrator path was not enough.

## Operational Lessons

- Prefer the orchestrated release report over manual terminal notes.
- Inspect release reports before touching live tmux sessions.
- Use authenticated tmux sessions only for recovery or deep troubleshooting.
- If Git reports a corrupt `refs/remotes/bitbucket/main`, use the bounded
  repair path documented in [WORKFLOW.md](WORKFLOW.md); the orchestrator and
  current `update.sh` already self-heal the known signature.
- Linux wrappers must use `python`, not the Windows `py` launcher.
- Do not use the stale `dispatch.git` remote for Autobench deployment.
