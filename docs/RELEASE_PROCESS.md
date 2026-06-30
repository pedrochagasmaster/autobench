# Autobench Release Process

The default release process is the shared orchestrator documented in
[`docs/development-workflow.md`](./development-workflow.md).

```powershell
cd D:\Projects\edge-deploy-core
py -m edge_deploy release --tool autobench --smoke standard
```

Use `--tool both` when Autobench and Dispatch must be promoted together.

The release is complete only when the generated
`edge-deploy\reports\release-*\release.json` reports success and the
Autobench rollout reports for node03 and node04 show passing update, drift, and
smoke checks.

## Bootstrap and Recovery

`deploy_and_install.ps1`, `setup_remote_env.sh`, and direct `update.sh` usage
are retained for first-time node setup, offline dependency refreshes, and
recovery when the orchestrator cannot complete. They are not the default
release workflow.

For those cases, follow
[`docs/edge-node-first-time-setup.md`](./edge-node-first-time-setup.md) and
`.agents/skills/autobench-edge-deploy/WORKFLOW.md`, then record why the normal
release command was bypassed.
