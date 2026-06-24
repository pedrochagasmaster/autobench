# Implementation Plan: Consolidated Edge Workflow

> Historical planning reference, not canonical operating truth.
>
> Use this file to implement and review the workflow consolidation. The
> canonical operator contracts remain:
>
> - `docs/development-workflow.md`
> - `docs/edge-node-tui-operating-model.md`
> - `docs/edge-node-first-time-setup.md`
> - `docs/production-testing.md`
> - `tools/prod_tui/README.md`
> - `.agents/skills/autobench-edge-deploy/WORKFLOW.md`

## Objective

Move Autobench onto one short, auditable Edge deployment workflow:

1. local change,
2. local gate,
3. Bitbucket deployment snapshot,
4. node update through Git,
5. explicit install or dependency-refresh decision,
6. node-specific drift and smoke verification,
7. controlled recovery or rollback,
8. one report shape for every node.

The plan preserves the current infrastructure controls while removing operator
branching that is easy to misuse during active Edge work.

## Current State Anchors

Autobench already has the important building blocks:

- `docs/development-workflow.md` defines the local-to-Bitbucket-to-Edge flow.
- `docs/edge-node-tui-operating-model.md` defines the shared deploy tree,
  per-user runtime home, golden path, installer contract, harness contract, and
  rollback model.
- `docs/edge-node-first-time-setup.md` bootstraps `/ads_storage/autobench`.
- `docs/production-testing.md` defines Level 1/2/3 smoke levels and failure
  classes.
- `tools/prod_tui/harness.py` writes JSON smoke reports and drift manifests.
- `tools/dev/local_check.ps1` is the local verification wrapper.
- `tools/dev/git_sync_status.ps1` checks remote and branch state.
- `update.sh` is the normal shared-tree sync command.
- `install.sh` is the per-user runtime and launcher installer.
- `deploy_and_install.ps1` plus `setup_remote_env.sh` is the offline bundle,
  first-time setup, dependency refresh, or recovery path.
- `run_tool.sh` is the shared-tree wrapper for server smoke commands.

Known gaps to close:

- `docs/edge-node-first-time-setup.md` still points first-time clone commands at
  the obsolete `dispatch.git` remote.
- Bitbucket publish still requires a fragile detached-HEAD manual sequence.
- Tmux/MFA handling exists as hard-won operational knowledge but is not yet a
  concrete enough operator contract in the docs and harness.
- The update/install/bundle boundary is documented but not encoded clearly
  enough for pressure situations.
- Drift and smoke reports do not yet fully express the deployment claim shape:
  source commit, Bitbucket snapshot, node, deployed commit, runtime, install
  decision, drift, smoke level, and permission evidence.

## Target Command Surface

Keep the workflow small. After this plan lands, operators should use these
commands for normal work:

```powershell
.\tools\dev\local_check.ps1
.\tools\dev\git_sync_status.ps1
.\tools\dev\publish_bitbucket_snapshot.ps1
py -m tools.prod_tui smoke --config tools/prod_tui/config-node04.yaml --level 2 --save-screens
py -m tools.prod_tui drift --local . --remote /ads_storage/autobench
```

On each Edge Node:

```bash
cd /ads_storage/autobench
AUTOBENCH_GIT_REMOTE=bitbucket AUTOBENCH_GIT_BRANCH=main ./update.sh
./install.sh        # only when the dependency signal says reinstall is needed
./run_tool.sh config list
./run_tool.sh share --help
python -m compileall benchmark.py tui_app.py core utils scripts tools
```

The offline path stays supported, but is not the default daily release path:

```powershell
.\deploy_and_install.ps1
```

## Report Contract

Every production deployment, smoke, drift, recovery, or rollback claim must name
the node and include:

- local source commit,
- Bitbucket snapshot SHA,
- Edge node host,
- deployed `/ads_storage/autobench` commit,
- `VERSION`,
- runtime Python path and version,
- update method: `update.sh`, exact-SHA reset, or offline bundle,
- install decision: skipped, run, or required but blocked,
- dependency signal used for that install decision,
- drift result and manifest/report path,
- smoke level and JSON report path,
- wrapper checks: `./run_tool.sh config list` and `./run_tool.sh share --help`,
- shared-permission evidence for `/ads_storage/autobench` and entrypoint
  scripts,
- auth or MFA handoff state if any step required human takeover.

Failure classes should stay aligned with `docs/production-testing.md`:
`harness`, `environment`, `deployment`, `tui`, and `workflow`.

## Phase 1: Normalize The Active Docs Around One Default Path

Scope:

- `docs/development-workflow.md`
- `docs/edge-node-first-time-setup.md`
- `docs/edge-node-tui-operating-model.md`
- `.agents/skills/autobench-edge-deploy/WORKFLOW.md`

Implement:

- Fix all active Autobench setup/deploy references to use
  `https://scm.mastercard.int/stash/scm/~e176097/autobench.git`.
- Remove or explicitly mark obsolete `dispatch.git` references.
- Add the same deploy decision table to the active operator docs:
  normal Git update, Git update plus install, offline bundle refresh, recovery,
  and rollback.
- Make `update.sh` the dominant default path everywhere.
- Make `deploy_and_install.ps1` clearly secondary: first-time setup, dependency
  wheel refresh, or recovery when Git access from the node is unavailable.

Acceptance criteria:

- `rg -n "dispatch\\.git" docs .agents` returns no active Autobench deploy
  instruction.
- An operator can tell in one read whether to run `update.sh`, `install.sh`,
  `deploy_and_install.ps1`, or exact-SHA rollback.
- The docs preserve the split between `/ads_storage/autobench` and
  `/ads_storage/$USER/.autobench`.

Verification:

```powershell
rg -n "dispatch\.git|autobench\.git|update\.sh|deploy_and_install|install\.sh" docs .agents
py -m pytest tests/test_edge_node_operating_model.py -q
```

STOP conditions:

- Any doc implies copying individual files to `/ads_storage/autobench`.
- Any doc treats offline bundle upload as the normal daily deployment path.
- The first-time setup path cannot be followed from an empty node checkout.

## Phase 2: Simplify The Bitbucket Snapshot Publish Flow

Scope:

- `docs/development-workflow.md`
- `tools/dev/publish_bitbucket_snapshot.ps1` (new)
- `tools/dev/git_sync_status.ps1`
- tests for any new helper logic

Implement:

- Add one supported publish helper that wraps the current authored-snapshot
  requirement.
- Preserve the deployment model: local `main` is source, Bitbucket receives a
  single snapshot commit parented on `bitbucket/main`, and no force push is
  used.
- Capture and print source commit, source short SHA, Bitbucket parent SHA, new
  snapshot SHA, author, remote URL, and push result.
- Leave the working tree on the original branch even when publish fails.
- Fail before any push when the remote URL is not the Autobench Bitbucket URL.
- Support PAT header auth without writing secrets to disk.
- If interactive auth is required, stop with an explicit handoff instruction
  instead of retrying blindly.

Acceptance criteria:

- Publishing no longer requires the operator to manually enter detached HEAD
  except while debugging.
- The helper refuses to publish to `origin` or the obsolete `dispatch.git`
  remote.
- The final output gives enough evidence to update Edge nodes and write the
  report contract.

Verification:

```powershell
py -m ruff check tools/dev
py -m pytest tests -q
.\tools\dev\local_check.ps1
```

STOP conditions:

- The helper force-pushes.
- The helper can leave the operator stranded on detached HEAD.
- The helper prints or stores a PAT.
- The helper pushes local `main` history directly to Bitbucket.

## Phase 3: Operationalize Session-First Tmux And MFA Handling

Scope:

- `docs/production-testing.md`
- `tools/prod_tui/README.md`
- `tools/prod_tui/harness.py`
- node-specific config template fields

Implement:

- Add explicit preflight steps for `tmux ls`, `tmux list-panes`, and
  `tmux capture-pane` before sending commands to any session.
- Document the PASSCODE/MFA boundary: agents may prepare SSH prompts, but humans
  enter credentials.
- Encode safe command injection guidance for commands containing quotes, globs,
  `$USER`, or command substitutions: use literal send where available.
- Add harness/report fields for session name, pane target, auth state, and
  whether human takeover was required.
- Add examples for recovering when SSH has auto-logged out and a command would
  otherwise land in local PowerShell.

Acceptance criteria:

- A blocked MFA flow ends with a ready handoff, not repeated failed attempts.
- Operator docs reflect the real tmux-first workflow used for node03/node04.
- Reports distinguish harness/auth failure from deployment or product failure.

Verification:

```powershell
py -m tools.prod_tui --help
py -m pytest tests/test_edge_node_operating_model.py -q
py -m ruff check tools/prod_tui
```

STOP conditions:

- Any instruction asks an agent to handle PASSCODE values in chat, logs, or
  scripts.
- The harness can mutate a node before proving it is in the intended remote
  shell.
- Reports cannot distinguish auth/session failure from application failure.

## Phase 4: Tighten The Update Versus Install Boundary

Scope:

- `update.sh`
- `install.sh`
- `docs/development-workflow.md`
- `docs/edge-node-first-time-setup.md`
- `docs/edge-node-tui-operating-model.md`

Implement:

- Keep `update.sh` focused on shared-tree sync, hard reset, line-ending
  normalization, and shared permissions.
- Add a dependency-change signal that compares dependency-relevant files between
  the previous deployed commit and the target commit.
- Treat these as reinstall triggers: `requirements.txt`,
  `requirements-dev.txt`, `constraints.txt`, `VERSION`, `install.sh`,
  `setup_remote_env.sh`, and `offline_packages` or `vendor` manifest changes.
- Make the post-update output say one of:
  `install not required`, `install recommended`, or `install required`.
- Keep `install.sh` idempotent and per-user; it must not overwrite user runtime
  state beyond its virtualenv/launcher contract.

Acceptance criteria:

- Operators stop running `install.sh` out of habit after source-only changes.
- Operators get a clear reinstall signal when wheel, interpreter, launcher, or
  dependency inputs changed.
- Permission reassertion remains part of the normal update path.

Verification:

```powershell
py -m pytest tests/test_edge_node_operating_model.py -q
py -m ruff check .
```

Node-side smoke after implementation:

```bash
cd /ads_storage/autobench
AUTOBENCH_GIT_REMOTE=bitbucket AUTOBENCH_GIT_BRANCH=main ./update.sh
git status --porcelain
./run_tool.sh config list
```

STOP conditions:

- `update.sh` removes `.venv`, `offline_packages`, user data, or per-user
  runtime state.
- `install.sh` silently chooses a Python interpreter whose ABI does not match
  bundled wheels.
- Dependency-change output is too vague to support the report contract.

## Phase 5: Align Offline Bundle Refresh And Recovery With The Main Workflow

Scope:

- `deploy_and_install.ps1`
- `setup_remote_env.sh`
- `docs/edge-node-first-time-setup.md`
- `docs/development-workflow.md`
- `docs/production-testing.md`

Implement:

- Make the bundle path produce the same report evidence expected from a Git
  update: source commit, bundle checksum, extraction path, runtime Python,
  install result, wrapper smoke, and drift/smoke result.
- Keep the CPython 3.10 / `cp310` wheel contract explicit.
- Ensure stale `offline_packages` caches are treated as rebuild candidates when
  dependency install fails.
- End every bundle recovery with the same verifiable state as the Git path:
  extracted tree at `/ads_storage/autobench`, executable scripts, installed
  runtime, wrapper checks, and node-specific report.

Acceptance criteria:

- First-time setup and recovery are supported without looking like the normal
  daily deploy path.
- Operators can compare bundle-based recovery evidence to Git-based deploy
  evidence.
- A failed dependency install points to bundle rebuild or interpreter mismatch,
  not generic pip noise.

Verification:

```powershell
py -m ruff check .
py -m pytest tests/test_edge_node_operating_model.py -q
```

Optional real recovery verification, human gated:

```powershell
.\deploy_and_install.ps1
```

STOP conditions:

- A bundle can be produced without checksums.
- The recovery path does not re-run wrapper smoke.
- The docs imply stale archived wheels are safe after dependency failures.

## Phase 6: Unify Drift, Smoke, And Deployment Report Output

Scope:

- `tools/prod_tui/harness.py`
- `tools/prod_tui/README.md`
- `docs/production-testing.md`
- tests for report schema and redaction

Implement:

- Extend the JSON report schema to cover the full report contract in this plan.
- Keep token, password, and passcode redaction.
- Include node-specific config name and remote repo path.
- Include local manifest path for drift and smoke report path for smoke.
- Make `--remote /ads_storage/autobench` meaningful or document the current
  limitation clearly until remote drift comparison is implemented.
- Add a single report summary line that can be pasted into a deployment handoff.

Acceptance criteria:

- A deployment claim for Autobench can be compared directly with a Dispatch
  deployment claim.
- The report tells an operator whether the issue is deploy, runtime, auth, or
  product behavior.
- Redaction tests cover credential-shaped output.

Verification:

```powershell
py -m tools.prod_tui smoke --config tools/prod_tui/config-template.yaml --level 1
py -m tools.prod_tui drift --local . --remote /ads_storage/autobench
py -m pytest tests -q
.\tools\dev\local_check.ps1
```

STOP conditions:

- Reports omit node identity.
- Reports store credentials, passcodes, or PATs.
- A zero-drift claim is printed when the remote tree was not actually compared.

## Phase 7: Standardize Rollback And Human-Gated Edge Acceptance

Scope:

- `docs/development-workflow.md`
- `docs/production-testing.md`
- `docs/edge-node-tui-operating-model.md`
- `tools/prod_tui/README.md`

Implement:

- Keep rollback as exact-SHA reset plus optional reinstall when dependency
  inputs differ.
- Require post-rollback drift and Level 1/2 smoke on each node.
- Record node, old SHA, rollback SHA, reinstall decision, drift result, smoke
  level, and wrapper checks.
- Add human-gated acceptance criteria for real node03/node04 validation.
- Make it explicit that local verification is not a substitute for real Edge
  validation when Kerberos, Impala, SSH, or node storage behavior is in scope.

Acceptance criteria:

- Rollback is explicit, repeatable, and node-specific.
- A human can decide whether a plan implementation is ready for production
  based on report artifacts rather than chat narration.
- The docs separate local completion from real Edge acceptance.

Verification:

```powershell
py -m pytest tests/test_edge_node_operating_model.py -q
.\tools\dev\local_check.ps1
```

Human-gated Edge acceptance:

```bash
cd /ads_storage/autobench
git fetch bitbucket
git reset --hard <snapshot-sha>
chmod -R a+rX .
./run_tool.sh config list
./run_tool.sh share --help
python -m compileall benchmark.py tui_app.py core utils scripts tools
```

STOP conditions:

- Rollback can be described without a target SHA.
- A production claim does not name the node.
- Real Edge validation is claimed when MFA, SSH, Kerberos, or storage access was
  blocked.

## Recommended Delivery Order

1. Phase 1: fix doc drift and default-path clarity.
2. Phase 2: add the publish helper.
3. Phase 3: harden tmux/MFA session handling.
4. Phase 4: encode the update/install decision.
5. Phase 5: align offline bundle recovery with the main report model.
6. Phase 6: unify report schema and drift/smoke evidence.
7. Phase 7: finalize rollback and human-gated acceptance.

Keep each phase independently reviewable. Do not mix deploy helper changes,
harness schema changes, and shell-script behavior changes in one commit unless a
single test proves the combined behavior and no smaller commit boundary exists.

## Definition Of Done

- Autobench has one clearly dominant deploy workflow and two explicitly
  secondary workflows: dependency refresh and recovery.
- No active setup/deploy doc points Autobench at `dispatch.git`.
- Publishing, updating, installing, dependency refreshing, drift checking,
  smoking, rolling back, and reporting each have one supported operator path.
- The normal publish path records source commit and Bitbucket snapshot SHA.
- The normal node update path records node, deployed commit, install decision,
  drift, smoke, and permission evidence.
- Local verification uses `.\tools\dev\local_check.ps1`.
- Real Edge acceptance is human-gated and node-specific.
- Generated bundles, reports, logs, screenshots, data, outputs, credentials, and
  personal config remain uncommitted.

## Non-Goals

- Do not replace Bitbucket with GitHub as the Edge deployment target.
- Do not remove the offline bundle path; keep it for first-time setup,
  dependency refresh, and recovery.
- Do not make agents handle PASSCODE, Kerberos passwords, PATs, or any other
  secret.
- Do not claim production readiness from local-only smoke checks.
