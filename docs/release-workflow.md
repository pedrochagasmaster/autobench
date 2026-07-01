# Autobench Release Workflow

Only a Release Operator performs this workflow. Normal development ends at the
merged GitHub pull request.

From the Autobench checkout:

```powershell
git switch main
git pull --ff-only origin main
python -m pip install -e ".[dev,release]"
python -m pytest
python -m edge_deploy release
```

The command requires clean local `main` exactly matching GitHub `origin/main`,
successful post-merge GitHub CI for that SHA, the configured `bitbucket`
remote, available centralized audit storage, and interactive Edge
authentication. It publishes and deploys one tool only.

Successful verification creates the same immutable release tag on GitHub and
Bitbucket. Redacted evidence is appended to the Bitbucket-only `release-log`
branch in `edge-deploy-core`.

Rollback is a separate tagged operation:

```powershell
python -m edge_deploy rollback --tag release-<UTC>-<short-sha>
```

Real operator configuration lives at
`%APPDATA%\edge-deploy\config.yaml`. Bootstrap and recovery procedures remain
in [edge-node-first-time-setup.md](edge-node-first-time-setup.md); they are not
normal release paths.
