# Edge Node TUI Operating Model for Autobench

Autobench follows the shared Edge release model: committed Git state is the
deployable source of truth, `edge-deploy-core` is the default release
orchestrator, the shared deployed tree is separate from per-user runtime state,
and the tmux/SSH harness is for release validation evidence and deep
troubleshooting.

## Autobench Surfaces

1. **Local development machine**
   - Edit source under `D:\Projects\autobench`.
   - Use PowerShell and `py` for local commands.
   - Run `tools/dev/local_check.ps1` before committing a deployable change.

2. **Corporate deployment remote**
   - The deployment transport is the `autobench` repo:
     `https://scm.mastercard.int/stash/scm/~e176097/autobench.git`.
     (An older `dispatch` repo was used by mistake and is obsolete — always
     target `autobench`.)
   - Configure it as `bitbucket` so Edge Node instructions are explicit.
   - The repo does not share history with local `main` and rejects commits you
     did not author. The default `edge_deploy release` workflow publishes the
     deployment snapshot; repo-local publishing is recovery only.
   - Keep GitHub `origin` only for the external mirror/review workflow when
     needed.

3. **Shared deployed tree**
   - Default path: `/ads_storage/autobench`.
   - Contains `benchmark.py`, `tui_app.py`, `core/`, `utils/`, `config/`,
     `presets/`, `tests/fixtures/`, `install.sh`, `update.sh`, docs, and
     production harness.
   - Updated by `edge-deploy-core` during the default release. The node-side
     `update.sh` and zip/offline bundle path remain recovery and bootstrap
     mechanisms. Never copy or `scp` individual files onto the node — that
     reintroduces CRLF line endings and drifts the tree from Git.

4. **Per-user runtime home**
   - Default path: `/ads_storage/$USER/.autobench`.
   - Contains the user's virtualenv, logs, cache, config, and
     `installed_version`.
   - `install.sh` may refresh dependencies and launchers, but must preserve this
     runtime home.

## Required Artifacts

Autobench includes:

- `install.sh`: idempotent per-user installer.
- `update.sh`: node-side Git sync used by the release orchestrator and manual
  recovery.
- `onboarding.md`: short end-user install and launch path.
- `docs/development-workflow.md`: canonical local development and
  `edge-deploy-core` release workflow.
- `docs/edge-node-first-time-setup.md`: operator bootstrap guide.
- `docs/production-testing.md`: tmux/SSH harness and safety levels.
- `tools/dev/local_check.ps1`: strongest local check command.
- `tools/dev/git_sync_status.ps1`: remote and branch status helper.
- `tools/prod_tui/`: production harness, config template, reports, logs, and
  drift manifest tooling.
- `.gitattributes`: LF normalization for Linux-bound files.
- `.gitignore`: generated report/log/screen/bundle exclusions.

## Release Decision Table

| Situation | Use | Why |
| --- | --- | --- |
| Normal development release | `py -m edge_deploy release --tool autobench --smoke standard` from `D:\Projects\edge-deploy-core` | Default production promotion, node update, drift, smoke, and report path. |
| Coordinated Autobench + Dispatch release | `py -m edge_deploy release --tool both --smoke standard` | Default shared release path when both tools change. |
| First-time bootstrap or offline dependency recovery | `deploy_and_install.ps1`, `setup_remote_env.sh`, `install.sh` | Bootstrap/recovery only. |
| Node-specific diagnosis | `tools/prod_tui`, `update.sh`, tmux/SSH inspection | Deep troubleshooting after reviewing the release report. |

## Golden Path

1. Develop and test locally.
2. Commit the change.
3. From `D:\Projects\edge-deploy-core`, run:

   ```powershell
   py -m edge_deploy release --tool autobench --smoke standard
   ```

4. Enter RSA PASSCODEs in the visible terminal when prompted.
5. Verify `edge-deploy\reports\release-*\release.json` and the Autobench
   rollout reports show passing update, drift, smoke, and
   `remote_git_preflight` checks for node03 and node04.
6. Record the release report directory, local source commit, deployment SHA,
   nodes updated, and any authentication handoff.

Zip upload, direct `update.sh`, and manual tmux operation are fallback paths.
They do not replace the orchestrated release record.

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

Rollback is a Git reset to a known-good snapshot plus, if dependencies differ, a
reinstall:

```bash
cd /ads_storage/autobench
git fetch bitbucket
git reset --hard <previous-known-good-sha>
chmod -R a+rX .
./install.sh   # only if the offline bundle differs at that commit
autobench-cli config list
```

After rollback, run Level 1/2 smoke and record the node, old SHA, rollback SHA
(target SHA), install decision, drift result, smoke level, and wrapper checks.
This is human-gated Edge acceptance: local verification is not a substitute for
real node validation when SSH, Kerberos, storage, permissions, or terminal
behavior are in scope.
