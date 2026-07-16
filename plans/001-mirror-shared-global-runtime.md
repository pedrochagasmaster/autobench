# Plan 001: Mirror the Dispatch shared global runtime architecture in Autobench

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report; do not improvise. Keep the commits small and in the stated order.
> When done, update this plan's row in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat e7feb8f..HEAD -- install.sh onboard.sh shared_runtime.py bin run_tool.sh setup_remote_env.sh deploy_and_install.ps1 update.sh edge_deploy.yaml tests tools/prod_tui docs onboarding.md README.md requirements.txt constraints.txt`
>
> This plan was written against GitHub `origin/main` at `e7feb8f`. If any
> in-scope file changed, compare the current-state excerpts and the Dispatch
> reference implementation against live code before proceeding. Material
> contract drift is a STOP condition.

## Status

- **Priority**: P1
- **Effort**: L, multi-day
- **Risk**: HIGH
- **Depends on**: none
- **Category**: migration
- **Planned at**: commit `e7feb8f`, 2026-07-16

## Why this matters

Autobench currently shares its source tree but gives every analyst a separate
virtual environment and makes onboarding perform dependency installation.
Dispatch has already replaced that model with one Release Operator-managed,
immutable, content-addressed runtime per Edge Node. Autobench must reach the
same architecture so dependency installation, validation, activation, reuse,
failure isolation, and rollback have one operating model across both tools.

The target is full behavioral parity with Dispatch wherever the products have
the same concern. Autobench-specific behavior is limited to:

- two public launch interfaces: `autobench` for the TUI and `autobench-cli` for
  `benchmark.py`;
- the existing shared telemetry tree, which remains provisioned by the trusted
  operator path in `update.sh`;
- Autobench's Python 3.10/cp310 bundle and required imports;
- private Autobench state under `/ads_storage/<user>/.autobench`.

Do not copy Dispatch mechanically where these differences matter. Match the
same modules, guarantees, failure behavior, and tests.

## Target architecture

```text
/ads_storage/autobench/
|-- .venv/
|   |-- releases/
|   |   |-- <bundle-digest-A>/
|   |   `-- <bundle-digest-B>/
|   |-- current -> releases/<active-bundle-digest>
|   `-- install.lock
|-- bin/
|   |-- autobench
|   |-- autobench-cli
|   `-- runtime_check.sh
|-- benchmark.py
|-- tui_app.py
|-- core/
|-- utils/
|-- shared_runtime.py
|-- install.sh
`-- onboard.sh

/ads_storage/<user>/.autobench/
|-- config/
|-- logs/
|-- cache/
`-- telemetry/

~/.local/bin/autobench      -> thin script delegating to shared bin/autobench
~/.local/bin/autobench-cli  -> thin script delegating to shared bin/autobench-cli
```

The runtime identifier is the verified edge-deploy dependency bundle's
64-character SHA-256 `bundle_digest`, not the Git commit and not `VERSION`.
Source-only releases reuse a complete runtime. Dependency changes create a new
runtime. Old complete runtimes remain available for rollback.

## Required parity contract

| Concern | Required Autobench behavior |
|---------|-----------------------------|
| Ownership | One Release Operator-managed runtime per Edge Node |
| Runtime identity | Verified dependency-bundle digest |
| Construction | Build at final `.venv/releases/<digest>` path |
| Candidate privacy | Candidate is owner-only until validation completes |
| Dependency source | Verified offline bundle only; no online index |
| Validation | `pip check`, required imports, completion metadata |
| Activation | Atomic `.venv/current` symlink replacement |
| Process stability | Launcher resolves `current` to a physical path before exec |
| Reuse | Complete matching digest is reused without reinstall |
| Failure atomicity | Failed candidate never changes `current` |
| Corrupt active runtime | Never rebuild in place while `current` points to it |
| Retry | Incomplete inactive candidate is removed and rebuilt |
| Concurrency | One POSIX installation lock |
| Permissions | Analysts can read/execute; only owner can write |
| Rollback | Reactivate a retained complete runtime |
| Onboarding | Creates/repairs private state and thin launchers only |
| Migration | Replaces stale personal-venv launchers without deleting user state |
| User bundle access | Not required for onboarding or launch |
| Deployment smoke | Uses shared launchers and proves metadata/bundle agreement |
| Runtime cleanup | Never automatic |

## Current state

### Per-user installation and launch

`install.sh:5-10` derives both private state and the dependency bundle from the
calling user:

```sh
USER_NAME=${USER:-$(id -un)}
DATA_ROOT=${AUTOBENCH_DATA_ROOT:-/ads_storage/$USER_NAME}
AUTOBENCH_HOME="$DATA_ROOT/.autobench"
BUNDLE_DIR=${EDGE_DEPLOY_BUNDLE_DIR:-/ads_storage/$USER/.edge-deploy/bundles/autobench/current}
```

`install.sh:99-115` combines user-state creation and dependency installation:

```sh
mkdir -p "$AUTOBENCH_HOME/config" "$AUTOBENCH_HOME/logs" "$AUTOBENCH_HOME/cache"
"$PYTHON_BIN" -m venv "$AUTOBENCH_HOME/venv"
"$AUTOBENCH_HOME/venv/bin/pip" install --no-index ...
```

`install.sh:117-145` writes launchers tied to the personal environment and a
source-version marker:

```sh
exec "$AUTOBENCH_HOME/venv/bin/python" "$ROOT_DIR/tui_app.py" "$@"
exec "$AUTOBENCH_HOME/venv/bin/python" "$ROOT_DIR/benchmark.py" "$@"
cp "$ROOT_DIR/VERSION" "$AUTOBENCH_HOME/installed_version"
```

### Conflicting repository-local runtime

`run_tool.sh:11-23` expects a mutable repository-local `.venv` and sources its
activation script:

```sh
VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Error: Virtual environment not found at $VENV_DIR"
    exit 1
fi
source "$VENV_DIR/bin/activate"
```

`setup_remote_env.sh:23-61` creates and mutates that repository-local
environment. This is a second production runtime model and must be converged,
not retained.

### Tests and docs protect the old architecture

`tests/test_edge_node_operating_model.py:56-63` asserts that the installer
creates a personal venv launcher and `installed_version`.

`onboarding.md:3-5` says every user keeps a personal runtime.

`docs/edge-node-first-time-setup.md:79-81` says the installer installs
dependencies into each user's virtualenv.

`docs/production-testing.md:81-84` validates personal launchers,
`installed_version`, and writable runtime home.

### Existing behavior that must remain

- `AUTOBENCH_DATA_ROOT` selects an analyst's private state root.
- The TUI and CLI preserve the caller's current working directory so relative
  input and output paths keep working.
- `update.sh` provisions `/ads_storage/autobench/telemetry` and its sticky
  `users` directory. Keep this trusted operator seam.
- Private telemetry falls back to
  `/ads_storage/<user>/.autobench/telemetry/events.jsonl`.
- The runtime bundle targets Python 3.10/cp310.
- `requirements.txt` requires `pandas`, `numpy`, `openpyxl`, `PyYAML`,
  `scipy`, and `textual`. Runtime import names are respectively `pandas`,
  `numpy`, `openpyxl`, `yaml`, `scipy`, and `textual`.
- `edge_deploy.yaml` is the canonical deployment profile.
- `deploy_and_install.ps1` and `setup_remote_env.sh` are bootstrap/recovery
  paths, not a license to preserve a second runtime architecture.

## Dispatch reference implementation

Use the completed implementation in `D:\Projects\robocop` as the behavioral
reference, especially:

- `shared_runtime.py`
- `install.sh`
- `onboard.sh`
- `bin/dispatch`
- `bin/runtime_check.sh`
- `docs/adr/0007-shared-global-runtime.md`
- `tests/test_shared_runtime.py`
- `tests/test_install_onboarding.py`
- `tests/test_runtime_state_contract.py`
- `tools/prod_tui/deploy.py`
- `tools/prod_tui/drift.py`
- `tools/prod_tui/smoke_test.py`

Port fixes from the complete merged implementation, not only the first commit.
The final Dispatch implementation includes important follow-up hardening:
private bundle snapshots, active-runtime corruption protection, stale temporary
symlink cleanup, physical root resolution, shared runtime validation,
permission repair, stale launcher diagnosis, and removal of obsolete per-user
markers.

## Commands you will need

Run from `D:\Projects\autobench` on Windows unless the step explicitly uses
POSIX `sh`.

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Sync | `git switch main; git pull --ff-only origin main` | local `main` equals `origin/main` |
| Branch | `git switch -c codex/shared-global-runtime` | new short-lived branch |
| Targeted runtime tests | `py -m pytest tests/test_shared_runtime.py tests/test_install_onboarding.py tests/test_runtime_state_contract.py -q` | all pass |
| Production contract tests | `py -m pytest tests/test_production_scripts.py tests/test_edge_node_operating_model.py -q` | all pass |
| Full suite | `py -m pytest -n 4 --dist loadfile` | all pass |
| Syntax | `sh -n install.sh onboard.sh run_tool.sh bin/autobench bin/autobench-cli bin/runtime_check.sh` | exit 0 |
| Compile | `py -m compileall shared_runtime.py benchmark.py tui_app.py core utils scripts tools` | exit 0 |
| Working tree scope | `git status --short` | only intended files and `plans/` |

Use `py`, not bare `python`, for Windows verification on this machine.

## Scope

### In scope

- `shared_runtime.py` (create)
- `bin/autobench` (create)
- `bin/autobench-cli` (create)
- `bin/runtime_check.sh` (create)
- `onboard.sh` (create)
- `install.sh`
- `run_tool.sh`
- `setup_remote_env.sh`
- `deploy_and_install.ps1`
- `update.sh`
- `edge_deploy.yaml`
- `tests/bundle_helpers.py` or an Autobench-equivalent helper (create)
- `tests/test_shared_runtime.py` (create)
- `tests/test_install_onboarding.py` (create or reshape from existing seams)
- `tests/test_runtime_state_contract.py` (create)
- `tests/test_production_scripts.py`
- `tests/test_edge_node_operating_model.py`
- relevant `tools/prod_tui/` implementation and tests
- `docs/adr/0001-shared-global-runtime.md` (create; Autobench has no ADR
  directory yet)
- `README.md`
- `onboarding.md`
- `docs/edge-node-first-time-setup.md`
- `docs/production-testing.md`
- `docs/release-workflow.md`
- any existing active smoke/setup doc that still describes personal venvs
- `.gitattributes` only if needed to guarantee LF for new shell files

### Out of scope

- Changes to privacy calculations, suppression, balancing, publishable-output
  validation, or analysis semantics.
- Redesign of shared telemetry writers, capability gates, event schemas,
  aggregation, retention, or permissions.
- Installing into system Python.
- Online package installation.
- Writing launchers into `/usr/local/bin`.
- Automatically deleting personal venvs or old shared runtimes.
- Changing edge authentication, tmux/psmux transport, firewall posture, release
  tags, or Bitbucket/GitHub publication policy.
- Adding optional SQL drivers such as `pypyodbc` to the shared runtime.
- Modifying `edge-deploy-core` unless an Autobench implementation test proves a
  missing generic seam. If that occurs, stop and report the exact missing seam.

## Git workflow

- Start from current GitHub `main`.
- Branch: `codex/shared-global-runtime`.
- Follow conventional commit style already used in the repository, for example
  `feat: ...`, `fix: ...`, `test: ...`, `docs: ...`.
- Make the small commits below in order. Do not squash during implementation;
  the PR may be squash-merged later by a maintainer.
- Do not push or open a PR unless explicitly instructed.
- Never deploy, create release tags, push Bitbucket, or run a release as part of
  implementation.

## Implementation sequence

### Commit 1: Record the Autobench runtime ownership decision

Create `docs/adr/0001-shared-global-runtime.md`, using Dispatch ADR 0007 as the
structural reference and Autobench terminology throughout.

The ADR must define:

- one Release Operator-managed runtime under `/ads_storage/autobench/.venv`;
- digest-addressed immutable releases;
- final-path construction because venv entrypoints embed absolute paths;
- offline install, `pip check`, required-import validation, and completion
  metadata;
- atomic activation and physical launcher resolution;
- source-only reuse, failed-upgrade safety, rollback, and retention;
- private per-user state under `/ads_storage/<user>/.autobench`;
- the two launcher interfaces;
- separation of `install.sh` and `onboard.sh`;
- shared telemetry remaining operator-provisioned by `update.sh`.

Do not change production behavior in this commit.

**Verify**:
`py -m pytest tests/test_edge_node_operating_model.py -q`
must pass unchanged.

### Commit 2: Characterize user state and working-directory behavior

Create `tests/test_runtime_state_contract.py` before changing launch behavior.
Prove observable contracts:

1. Two values of `AUTOBENCH_DATA_ROOT` resolve distinct private Autobench homes.
2. Private `config`, `logs`, `cache`, and telemetry paths remain user-specific.
3. TUI and CLI launch from the caller's current directory.
4. Relative input/output paths are not silently rebased to the repository.
5. Application code does not require
   `/ads_storage/<user>/.autobench/venv`.
6. Shared telemetry path resolution is unchanged and remains separate from
   private state.

Prefer behavior-level tests over grepping implementation text. If no explicit
private-home helper exists, characterize the current filesystem behavior at
the nearest existing public seam rather than adding production code yet.

**Verify**:
`py -m pytest tests/test_runtime_state_contract.py -q`
must pass.

### Commit 3: Add inactive shared launchers and common runtime validation

Create:

- `bin/runtime_check.sh`
- `bin/autobench`
- `bin/autobench-cli`

`bin/runtime_check.sh` must match Dispatch's validation guarantees:

- require `.venv/current` to be a symlink;
- resolve it with `readlink -f`;
- reject missing runtime, missing completion marker, or missing Python;
- reject targets outside `<physical-root>/.venv/releases/`;
- verify marker digest matches the runtime directory name;
- verify marker records `pip_check: passed`;
- print actionable operator guidance on failure.

Both launchers must resolve the repository root physically with `pwd -P`, call
the common validator, export `PYTHONPATH` to the shared source root, preserve
the caller's cwd, and `exec` the physical runtime Python:

- `bin/autobench` executes `tui_app.py`;
- `bin/autobench-cli` executes `benchmark.py`.

Do not switch installation or onboarding yet.

Add launcher tests modeled after Dispatch
`tests/test_shared_runtime.py`:

- forwards all arguments exactly;
- preserves cwd;
- resolves the runtime physically;
- both launchers use the same runtime;
- missing `current` fails clearly;
- corrupt completion metadata fails clearly;
- target outside the release root is rejected.

**Verify**:
`sh -n bin/autobench bin/autobench-cli bin/runtime_check.sh; py -m pytest tests/test_shared_runtime.py -q`
must pass.

### Commit 4: Introduce verified manifest and digest path handling

Create standard-library-only `shared_runtime.py`, porting the complete Dispatch
module and adapting:

- manifest `tool` must be `autobench`;
- required imports must be
  `("pandas", "numpy", "openpyxl", "yaml", "scipy", "textual")`;
- messages must say Autobench;
- CLI accepts `--bundle`, `--python`, and `--root`.

Keep the module importable on Windows while installation remains POSIX-only.
Validate:

- edge-deploy manifest schema;
- 64-character lowercase digest;
- canonical digest recomputation;
- safe declared paths only under `requirements/` and `wheels/`;
- no duplicate, linked, missing, changed, or undeclared files;
- target Python metadata when present;
- complete runtime location under `.venv/releases/<digest>`.

Use a reusable Autobench bundle fixture helper modeled after
`robocop/tests/bundle_helpers.py`.

Do not call the module from `install.sh` yet.

**Verify**:
`py -m pytest tests/test_shared_runtime.py -q`
must cover malformed digest, unsafe paths, tampered files, undeclared files,
wrong tool, and incomplete layout.

### Commit 5: Add locked, final-path runtime construction

Implement construction behind `shared_runtime.install(...)`:

- create `.venv/releases` with explicit traversable modes;
- acquire `.venv/install.lock` using blocking POSIX `flock`;
- copy the verified bundle into a private installer-owned snapshot inside the
  runtime root;
- verify and install from that snapshot;
- create the venv directly at `.venv/releases/<digest>`;
- make the candidate mode `0700` before package installation;
- remove incomplete inactive candidates before retry;
- remove a failed candidate;
- never update `current` in this commit.

Do not build elsewhere and move the venv.

**Verify**:
targeted tests must prove concurrent installer exclusion, private candidate
mode, retry rebuilding an incomplete inactive candidate, and cleanup after
failure.

### Commit 6: Install and validate dependencies offline

Install through the candidate's own Python:

```text
<runtime>/bin/python -m pip install --no-index --find-links=<snapshot>/wheels
  -r <snapshot>/requirements/requirements.txt
<runtime>/bin/python -m pip check
<runtime>/bin/python -c "import pandas; import numpy; import openpyxl;
  import yaml; import scipy; import textual"
```

Then atomically write `.complete.json` with at least:

- `bundle_digest`;
- approved interpreter physical path;
- runtime interpreter physical path;
- Python version;
- `pip_check: "passed"`;
- exact required-import list.

The completion marker is the eligibility boundary. It must not exist before
all validation succeeds.

Preserve Autobench's useful interpreter/bundle mismatch diagnostics, but make
the manifest's target Python authoritative. Do not infer the runtime identity
from wheel filenames.

**Verify**:
tests must inspect recorded command order and prove no completion marker is
written after failed pip install, failed `pip check`, failed required import,
or Python target mismatch.

### Commit 7: Add atomic activation, reuse, rollback, and final permissions

Port the complete Dispatch behavior:

- reuse a matching complete runtime;
- repair read/execute permission drift on reused complete runtimes;
- clean stale `.current.tmp.*` links;
- atomically replace `current` with `os.replace`;
- reject a non-symlink object at `.venv/current`;
- never rebuild a corrupt runtime in place while it is active;
- switch to another digest without modifying the previous runtime;
- reactivate a previous complete digest for rollback;
- make completed directories traversable/readable and files readable/executable
  by analysts, while removing group/other write bits;
- never follow venv interpreter symlinks during chmod;
- retain all complete runtimes.

**Verify**:
`py -m pytest tests/test_shared_runtime.py -q`
must include Dispatch-equivalent tests for first activation, reuse, switch,
rollback, failed candidate preserving `current`, corrupt active runtime
protection, stale temporary cleanup, restrictive umask, lock exclusion, and
non-publicly-writable permissions.

### Commit 8: Split Release Operator installation from user onboarding

Rewrite `install.sh` as the non-interactive Release Operator interface:

- resolve physical root;
- resolve the approved Python 3.10 interpreter;
- require the shared repository root to be operator-writable;
- require the verified edge-deploy bundle;
- invoke `shared_runtime.py`;
- never read `AUTOBENCH_DATA_ROOT`;
- never create user directories or launchers;
- never write `installed_version`;
- print the active digest/action and point analysts to `onboard.sh`.

Create `onboard.sh` as the analyst interface:

- validate the active runtime before changing user state;
- require the shared launchers to exist and be executable;
- resolve `AUTOBENCH_DATA_ROOT`;
- create or repair private `.autobench/config`, `logs`, `cache`, and
  `telemetry` directories;
- set `.autobench` and private subdirectories to mode `0700`;
- create `~/.local/bin/autobench` and `autobench-cli` atomically as thin
  delegators to the shared launchers;
- preserve existing user files;
- repair shell `PATH` setup idempotently;
- never read a bundle, create a venv, run pip, or prompt for dependency
  information.

If existing application behavior expects particular private files, preserve
them. Do not invent an email prompt; Autobench currently has no equivalent
requirement.

**Verify**:
integration tests must prove release install creates no user state and
onboarding contains no bundle/venv/pip operation.

### Commit 9: Switch all supported launch paths and migrate existing users

Make the shared launchers canonical:

- `~/.local/bin/autobench` delegates to `/ads_storage/autobench/bin/autobench`;
- `~/.local/bin/autobench-cli` delegates to the CLI shared launcher;
- `run_tool.sh` remains only as a compatibility router and delegates to the
  shared launchers without sourcing `.venv/bin/activate`;
- `setup_alias.sh`, if still supported, must install or repair only thin
  launchers and must not encode a runtime path;
- rerunning onboarding atomically replaces launchers that reference
  `.autobench/venv`;
- existing personal venvs and private data remain untouched.

Add a clear stale-runtime diagnostic. If Autobench starts under a Python whose
physical path is inside `.autobench/venv`, tell the user to rerun
`/ads_storage/autobench/onboard.sh`. Match Dispatch's user-facing intent but
place the check at an Autobench seam shared by TUI and CLI, or explicitly test
both entrypoints if no suitable common seam exists.

**Verify**:
tests must prove:

- existing launcher migration preserves config/log/cache/telemetry contents;
- both commands resolve the same physical shared interpreter;
- two users keep distinct private homes;
- old personal venv remains untouched;
- `run_tool.sh config list` and `run_tool.sh share --help` delegate correctly;
- stale personal-runtime diagnosis is actionable.

### Commit 10: Converge bootstrap and recovery on the same architecture

Remove the alternate mutable repo-local runtime contract from
`setup_remote_env.sh` and `deploy_and_install.ps1`.

Required end state:

- bootstrap/recovery produces or receives a valid edge-deploy-compatible
  dependency bundle;
- remote installation calls `install.sh`;
- smoke calls `/ads_storage/autobench/bin/autobench-cli config list` and
  `... share --help`;
- no path creates, activates, or mutates `/ads_storage/autobench/.venv` as a
  plain venv;
- no path runs bare `pip`;
- checksum-only legacy bundles are either converted into the verified manifest
  shape before installation or rejected with guidance to use edge-deploy;
- recovery reports active runtime digest, runtime Python, completion status,
  wrapper checks, drift status, and permission evidence.

Prefer deleting obsolete setup logic to wrapping it around the new installer.
There must be one runtime architecture after this commit.

**Verify**:
production script tests must assert that bootstrap calls `install.sh`, uses
shared launchers, and contains no `source .venv/bin/activate`, direct
`.venv/bin/pip`, or plain repo-local venv construction.

### Commit 11: Update edge-deploy and production verification contracts

Update `edge_deploy.yaml`:

- include `shared_runtime.py`, `onboard.sh`, both launchers, and
  `bin/runtime_check.sh` in `runtime_paths`;
- include runtime installer/launcher inputs in `install_trigger_paths`;
- use explicit shared-launcher smoke commands;
- keep dependency inputs and cp310 target unchanged.

Update `tools/prod_tui/` and its tests to collect runtime evidence equivalent
to Dispatch:

- physical active runtime path;
- completion metadata digest;
- delivered bundle digest;
- digest equality;
- prior `pip_check` result;
- required-import probe using active runtime Python;
- both launcher exit codes;
- no publicly writable runtime entries;
- runtime-critical files present/readable;
- shared launchers executable.

For Autobench, the standard launcher smoke must include:

```bash
/ads_storage/autobench/bin/autobench-cli config list
/ads_storage/autobench/bin/autobench-cli share --help
```

The TUI launcher should receive a safe help/startup contract only if its
existing CLI behavior makes that deterministic; do not add a fake TUI flag
solely for smoke. Existing controlled-analysis smoke must invoke the shared CLI
launcher, not `py benchmark.py`.

Keep shared telemetry filesystem validation as a separate production gate.

**Verify**:

```powershell
py -m pytest tests/test_edge_node_operating_model.py tests/test_production_scripts.py -q
```

must pass with new assertions for all runtime evidence.

### Commit 12: Update operations, onboarding, rollback, and troubleshooting docs

Update all active docs to state:

- Release Operator installs/activates the global runtime once per node;
- analysts run lightweight `onboard.sh`;
- analysts need no dependency bundle and never run pip;
- user state remains private;
- shared telemetry remains a distinct operator-owned tree;
- source-only releases reuse runtime;
- dependency changes create digest-addressed runtime;
- failed candidates preserve active runtime;
- rollback reactivates a retained completed runtime;
- users repair stale launchers by rerunning onboarding;
- personal venvs are retained during migration but unsupported;
- old runtime deletion is a separate approved cleanup.

Remove active instructions that validate `installed_version`, writable runtime
home, personal dependency installation, or `source .venv/bin/activate`.

Document exact operator and analyst checks, including:

```bash
readlink -f /ads_storage/autobench/.venv/current
/ads_storage/autobench/bin/autobench-cli config list
/ads_storage/autobench/bin/autobench-cli share --help
which autobench
which autobench-cli
```

**Verify**:
the operating-model documentation tests pass and
`rg -n "personal runtime|installed_version|source \\.venv/bin/activate" README.md onboarding.md docs`
returns no active instruction describing the old architecture.

### Commit 13: Add complete migration and rollback integration coverage

Model Dispatch's integration-test seam in
`tests/test_install_onboarding.py`. Cover:

1. Release install builds a complete offline runtime without user state.
2. Failed install preserves the previous active runtime.
3. Wrong interpreter target fails before activation.
4. Existing user has private files, personal venv, and stale launchers.
5. Operator installs shared runtime.
6. User onboarding replaces only launchers and repairs directory modes.
7. Existing config/log/cache/telemetry contents remain unchanged.
8. Two users launch through the same physical Python.
9. Their private roots remain different.
10. A user with no personal bundle or personal venv can onboard.
11. Missing/corrupt global runtime fails before onboarding changes state.
12. Both shared launcher contracts work.
13. Reinstall of identical digest reuses runtime.
14. Upgrade activates a new digest.
15. Rollback reactivates the previous digest without pip or download.
16. A process that resolved the old physical runtime remains tied to it after
    `current` changes.

Use fake Python/pip binaries and temporary POSIX layouts as Dispatch does; do
not require an Edge Node for the automated suite. Skip only where the host
lacks POSIX `sh`/symlink behavior.

**Verify**:
the three targeted runtime test files pass together.

### Commit 14: Remove obsolete per-user runtime artifacts and assertions

After all replacement tests pass, remove:

- personal venv creation from supported installation/onboarding paths;
- user bundle lookup from onboarding;
- personal `installed_version` writes and checks;
- direct personal Python paths in launchers;
- plain repository `.venv` activation;
- tests encoding the old architecture;
- docs telling analysts to install dependencies;
- misleading comments that call `.venv` a mutable environment.

Keep compatibility diagnosis and migration behavior. Do not delete personal
venvs.

**Verify**:

```powershell
rg -n "\.autobench/venv|AUTOBENCH_HOME/venv|installed_version|source.*\.venv/bin/activate|\.venv/bin/pip" .
```

may match only explicit migration diagnostics, tests proving old launchers are
repaired, archived historical design material, or this plan. It must not match
an active production path or active user instruction.

### Commit 15: Run full validation and prepare the PR handoff

Run:

```powershell
sh -n install.sh onboard.sh run_tool.sh bin/autobench bin/autobench-cli bin/runtime_check.sh
py -m compileall shared_runtime.py benchmark.py tui_app.py core utils scripts tools
py -m pytest tests/test_shared_runtime.py tests/test_install_onboarding.py tests/test_runtime_state_contract.py -q
py -m pytest tests/test_production_scripts.py tests/test_edge_node_operating_model.py -q
py -m pytest -n 4 --dist loadfile
git diff --check
git status --short
```

Expected:

- every command exits 0;
- all tests pass;
- no generated reports, workbooks, CSVs, credentials, passcodes, or operator
  configuration are present;
- diff is limited to this plan's scope;
- no deployment or release action occurred.

The PR handoff must report:

- test counts and commands;
- migration risk;
- bootstrap/recovery changes;
- exact human-gated Edge validation still required on node03 then node04;
- confirmation that personal venvs and old shared runtimes are intentionally
  retained.

## Test plan summary

### `tests/test_shared_runtime.py`

Port the complete Dispatch matrix, adapted for Autobench:

- digest path and reuse;
- manifest schema/tool/digest verification;
- path and symlink safety;
- tamper/extra-file rejection;
- launcher argument and cwd preservation for both launchers;
- missing/corrupt/out-of-root runtime rejection;
- activation/reuse/switch/rollback;
- failed candidate atomicity;
- corrupt active-runtime protection;
- inactive incomplete rebuild;
- stale temporary cleanup;
- restrictive umask;
- concurrent lock;
- completed permissions.

### `tests/test_install_onboarding.py`

Exercise real shell interfaces with temporary homes, roots, bundles, and fake
interpreters. Assert filesystem effects and process argv, not shell-script text.

### `tests/test_runtime_state_contract.py`

Protect private-state isolation, cwd behavior, shared telemetry separation, and
stale personal-runtime diagnostics.

### Existing production tests

Reshape old grep assertions into observable contracts where practical. Text
assertions remain appropriate for:

- no online pip/index setting;
- install-trigger/runtime-path profile coverage;
- absence of recursive chmod;
- bootstrap command routing;
- telemetry provisioning remaining operator-owned.

## Controlled Edge Node acceptance

Implementation is not production-complete until a Release Operator performs
this separately:

1. Deploy to node03 using the normal edge-deploy release workflow.
2. Confirm the active runtime digest matches the delivered bundle digest.
3. Confirm completion metadata, `pip check`, all required imports, and runtime
   permissions.
4. Run both shared CLI smoke commands.
5. Run onboarding as an analyst with no personal bundle and no personal venv.
6. Confirm two users resolve the same physical runtime.
7. Confirm their `.autobench` state and private telemetry remain separate.
8. Confirm shared telemetry validation still passes.
9. Start a long-lived Autobench process, activate another test runtime, and
   confirm the existing process remains tied to its original physical Python.
10. Test rollback to the retained previous runtime.
11. Repeat on node04.
12. Retain personal venvs and previous global runtimes for an observation
    period. Cleanup requires separate explicit approval.

## Done criteria

All must hold:

- [ ] One runtime exists per node under
  `/ads_storage/autobench/.venv/releases/<bundle-digest>`.
- [ ] `.venv/current` activation is atomic.
- [ ] Runtime creation is locked and failure-atomic.
- [ ] Installation is offline and validated by `pip check` plus all required
  imports.
- [ ] Complete runtime permissions are analyst-readable/executable but not
  publicly writable.
- [ ] `autobench` and `autobench-cli` resolve the same physical runtime before
  exec and preserve cwd.
- [ ] `install.sh` changes no user state.
- [ ] `onboard.sh` performs no bundle, venv, or pip work.
- [ ] A user with no personal bundle or venv can onboard and run both supported
  command contracts.
- [ ] Two users share runtime and retain isolated private state.
- [ ] Existing personal-venv launchers are replaced without deleting private
  data or the old venv.
- [ ] Failed upgrade leaves the prior runtime active.
- [ ] Rollback requires no rebuild or download.
- [ ] `run_tool.sh`, bootstrap, recovery, edge-deploy smoke, and production
  harness all use the same shared runtime architecture.
- [ ] Shared telemetry provisioning and validation remain unchanged in
  ownership and guarantees.
- [ ] No active test or doc encodes the obsolete personal-runtime contract.
- [ ] Full test suite passes.
- [ ] No source file outside the declared scope is modified.
- [ ] `plans/README.md` status is updated.

## STOP conditions

Stop and report instead of improvising if:

- current GitHub `main` materially changed any installer, launcher, bundle,
  telemetry, deployment, or production-harness seam from the excerpts above;
- the edge-deploy bundle manifest does not expose the same generic schema or
  `bundle_digest` contract used by Dispatch;
- full parity appears to require a tool-specific change in `edge-deploy-core`;
  report the missing generic seam and evidence first;
- Autobench application code actually depends on a personal venv path for
  behavior other than launching;
- changing onboarding would overwrite or relocate existing private user files;
- shared telemetry tests require weakening runtime permissions or merging the
  telemetry tree into `.venv`;
- deterministic launcher smoke would require changing analysis or privacy
  semantics;
- a verification command fails twice after a reasonable focused fix;
- implementation requires deleting personal venvs, old shared runtimes,
  generated user outputs, or operator configuration;
- implementation would require deploying, tagging, pushing Bitbucket, or
  entering credentials.

## Maintenance notes

- Keep Autobench and Dispatch runtime guarantees aligned. A future hardening
  fix in either shared-runtime implementation should trigger a parity review in
  the other repository.
- `edge_deploy.yaml` runtime paths, install triggers, drift paths, bootstrap
  contents, and production permission checks must stay synchronized.
- Adding or removing a required production dependency requires updating
  `requirements.txt`, bundle generation, `REQUIRED_IMPORTS`, completion
  metadata validation, and deployment probes together.
- Never treat Git/source `VERSION` as dependency-runtime identity.
- Never recursively chmod `.venv`; venv interpreter links can point outside the
  runtime.
- Runtime cleanup is an operator retention decision, not an install/update side
  effect.
- Reviewers should scrutinize bundle snapshot integrity, active-runtime
  corruption handling, symlink containment, chmod behavior around symlinks,
  onboarding's pre-mutation validation, and the absence of a second runtime
  path.
