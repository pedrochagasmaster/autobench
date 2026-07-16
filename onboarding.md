# Autobench Onboarding

The Release Operator installs one shared runtime per Edge Node. Analysts do not
need a dependency bundle and never run pip.

## Onboard

```bash
cd /ads_storage/autobench
./onboard.sh
```

Onboarding validates the active shared runtime, creates or repairs private
state under `/ads_storage/$USER/.autobench`, and atomically installs thin
`autobench` and `autobench-cli` launchers in `~/.local/bin`. Existing config,
logs, cache, telemetry, and old personal virtual environments are retained.

If the commands are not available in the current shell:

```bash
export PATH="$HOME/.local/bin:$PATH"
which autobench
which autobench-cli
```

## Launch

Run from the directory containing your inputs and desired outputs:

```bash
cd /path/to/my/work
autobench
autobench-cli config list
autobench-cli share --help
```

The launchers preserve the current working directory. Relative input and output
paths remain relative to where you launched Autobench.

## Troubleshooting

If onboarding reports that the shared runtime is missing or invalid, ask the
Release Operator to run `/ads_storage/autobench/install.sh`. Analysts cannot
repair or replace the shared runtime.

If Autobench warns that it is running from an unsupported personal virtual
environment, rerun:

```bash
/ads_storage/autobench/onboard.sh
```

This replaces stale launchers without deleting the old environment or private
files.
