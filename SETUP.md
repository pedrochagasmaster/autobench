# Edge Node Setup

Autobench uses one immutable shared runtime per Edge Node. The runtime lives at
`/ads_storage/autobench/.venv/releases/<bundle-digest>` and is activated through
the `.venv/current` symlink.

Normal releases use:

```powershell
python -m edge_deploy release
```

edge-deploy builds and verifies the Linux CPython 3.10 (`cp310`) dependency
bundle. The Release Operator then installs or reuses that digest-addressed
runtime:

```bash
cd /ads_storage/autobench
./install.sh
readlink -f /ads_storage/autobench/.venv/current
/ads_storage/autobench/bin/autobench-cli config list
/ads_storage/autobench/bin/autobench-cli share --help
```

Analysts run `./onboard.sh` once. They do not receive the bundle, create a
virtual environment, or install packages.

`deploy_and_install.ps1` and `setup_remote_env.sh` are recovery entrypoints
only. They require the verified edge-deploy bundle to exist and converge on
`install.sh`; checksum-only `offline_packages` archives are unsupported.

See [docs/edge-node-first-time-setup.md](docs/edge-node-first-time-setup.md),
[onboarding.md](onboarding.md), and
[docs/release-workflow.md](docs/release-workflow.md).
