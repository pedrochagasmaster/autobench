# Edge Node TUI Operating Model for Autobench

Autobench follows the reusable Edge Node TUI model proven by Dispatch:
committed Git state is the deployable source of truth, the shared deployed tree
is separate from per-user runtime state, and real production validation uses an
SSH/tmux terminal harness rather than plain subprocess tests.

## Autobench Surfaces

1. **Local development machine**
   - Edit source under `D:\Projects\autobench`.
   - Use PowerShell and `py` for local commands.
   - Run `tools/dev/local_check.ps1` before publishing a deployable change.

2. **Corporate deployment remote**
   - The deployment transport is
     `https://scm.mastercard.int/stash/scm/~e176097/dispatch.git`.
   - Configure it as `bitbucket` so Edge Node instructions are explicit.
   - Keep GitHub `origin` only for the external mirror/review workflow when
     needed.

3. **Shared deployed tree**
   - Default path: `/ads_storage/autobench`.
   - Contains `benchmark.py`, `tui_app.py`, `core/`, `utils/`, `config/`,
     `presets/`, `tests/fixtures/`, `install.sh`, docs, and production harness.
   - May be updated by Git pull or by the existing zip/offline bundle path.

4. **Per-user runtime home**
   - Default path: `/ads_storage/$USER/.autobench`.
   - Contains the user's virtualenv, logs, cache, config, and
     `installed_version`.
   - `install.sh` may refresh dependencies and launchers, but must preserve this
     runtime home.

## Required Artifacts

Autobench includes:

- `install.sh`: idempotent per-user installer.
- `onboarding.md`: short end-user install and launch path.
- `docs/development-workflow.md`: local to Git to Edge update loop.
- `docs/edge-node-first-time-setup.md`: operator bootstrap guide.
- `docs/production-testing.md`: tmux/SSH harness and safety levels.
- `tools/dev/local_check.ps1`: strongest local check command.
- `tools/dev/git_sync_status.ps1`: remote and branch status helper.
- `tools/prod_tui/`: production harness, config template, reports, logs, and
  drift manifest tooling.
- `.gitattributes`: LF normalization for Linux-bound files.
- `.gitignore`: generated report/log/screen/bundle exclusions.

## Golden Path

1. Develop and test locally.
2. Commit the change.
3. Push to the corporate remote.
4. On each Edge Node, fetch and checkout the target commit.
5. Run `./install.sh`.
6. Verify drift is zero with `py -m tools.prod_tui drift`.
7. Run Level 1/2 smoke through tmux/SSH.
8. Record node, commit, version, installer exit, drift status, and report path.

Zip upload and incremental sync are fallback paths. They are useful for offline
installs or fast iteration, but they do not replace a committed deployment
record.

## Installer Contract

`install.sh` selects a Python interpreter that matches the bundled offline
wheels. When `offline_packages/` (or `vendor/`) contains binary wheels, the
installer reads their CPython ABI tag (e.g. `cp310`) and requires a matching
`python3.X` interpreter (currently 3.10); with no binary wheels it falls back to
any supported 3.10+. It then creates `/ads_storage/$USER/.autobench/venv`,
installs pinned requirements from `offline_packages/` or `vendor/` when present,
writes launchers to `~/.local/bin/autobench` and `~/.local/bin/autobench-cli`,
records `VERSION` in `installed_version`, and prints the exact next command when
`PATH` is stale.

It must not require `source install.sh`, overwrite user state, store secrets,
silently continue after a dependency install failure, or build the venv with an
interpreter whose ABI does not match the bundled wheels (it fails with an
actionable message instead of emitting a cryptic pip "No matching distribution"
error).

## Production Harness Contract

The harness records:

- node and repo path,
- deployed commit and version,
- terminal geometry when available,
- pass/fail checks with failure classes,
- redacted command output,
- drift manifest or smoke report path.

Safety levels:

1. **Level 1:** SSH/tmux alive, compileall clean, TUI starts, home screen
   renders, help/quit keys work.
2. **Level 2:** installer runs, launcher resolves, runtime version matches,
   user runtime directory is writable, terminal geometry is acceptable.
3. **Level 3:** controlled share analysis using `tests/fixtures/gate_demo.csv`
   and a scratch output path. No arbitrary user data is launched by a smoke test.

## Rollback

Rollback is a Git checkout plus reinstall:

```bash
cd /ads_storage/autobench
git fetch bitbucket
git checkout <previous-known-good-sha>
./install.sh
autobench-cli config list
```

After rollback, run Level 1/2 smoke and record the deployed commit.
