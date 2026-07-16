# Autobench Release Workflow

Only a Release Operator performs this workflow. Normal development ends at the
merged GitHub pull request.

From the Autobench checkout:

```powershell
git switch main
git pull --ff-only origin main
python -m pip install -e ".[dev,release]"
python -m pytest -n 4 --dist loadfile
python -m edge_deploy release
```

The command requires clean local `main` exactly matching GitHub `origin/main`,
successful post-merge GitHub CI for that SHA, the configured `bitbucket`
remote, available centralized audit storage, and interactive Edge
authentication. It publishes and deploys one tool only.

When `requirements.txt` or `constraints.txt` changes, edge-deploy-core v1.1.0
builds, transfers, verifies, and installs a content-addressed offline bundle before
updating the checkout. `deploy_and_install.ps1` is bootstrap/recovery only.

The bundle digest names the immutable runtime under
`/ads_storage/autobench/.venv/releases/`. Source-only releases reuse a complete
runtime. Dependency changes build a new candidate privately; failed validation
preserves the previous `.venv/current`. Activation is atomic, and rollback
reactivates a retained complete runtime without download or pip.

Successful verification creates the same immutable release tag on GitHub and
Bitbucket. Redacted evidence is appended to the Bitbucket-only `release-log`
branch in `edge-deploy-core`.

Rollback is a separate tagged operation:

```powershell
python -m edge_deploy rollback --tag release-<UTC>-<short-sha>
```

After deployment, verify:

```bash
readlink -f /ads_storage/autobench/.venv/current
/ads_storage/autobench/bin/autobench-cli config list
/ads_storage/autobench/bin/autobench-cli share --help
```

Runtime deletion and personal-environment cleanup are separate operator
decisions and never part of release installation.

Real operator configuration lives at
`%APPDATA%\edge-deploy\config.yaml`. Bootstrap and recovery procedures remain
in [edge-node-first-time-setup.md](edge-node-first-time-setup.md); they are not
normal release paths.
