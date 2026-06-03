# Production Readiness Implementation Plan

Date: 2026-05-30

Scope: address the issues found during the latest PR/docs review, CLI smoke
tests, gate/unit verification, and manual TUI testing.

## Evidence

- Latest merged PR: #18, "De-slop audit remediation: all 10 phases
  (F01-F40, T01-T12)", merged 2026-05-30.
- Baseline checks after #18:
  - `py scripts/perform_gate_test.py` passed 18/18 cases.
  - `py -m pytest tests/ -v` passed 106 tests with two expected deprecation
    warnings.
  - `ruff check --select E,F --ignore E501,F401 benchmark.py core/ utils/
    tui_app.py` passed.
- CLI user smoke:
  - Share and rate runs completed against `tests/fixtures/gate_demo.csv`.
  - Both runs reported `fully_compliant` under strict posture.
  - Rate CSV/Excel validation passed.
- Manual TUI smoke:
  - `py /workspace/tui_app.py` can render the initial UI, but crashes during
    startup/logging with Textual `RuntimeError: The 'call_from_thread' method
    must run in a different thread from the app`.
- CSV validator smoke:
  - The rate validator works for rate output.
  - Running the validator against share output fails because the validator is
    rate-oriented while README usage presents it generically.

## Non-negotiable invariants

Every implementation step must preserve:

1. Mastercard Control 3.2 privacy caps and additional participant thresholds.
2. Existing preset semantics and compliance posture behavior.
3. Public CLI flags, config keys, workbook sheets, and CSV export schemas unless
   a documented deprecation window is added.
4. Offline deployment constraints described in `SETUP.md`.
5. Deprecated distortion aliases until the planned v4 removal window.

## Phase 1 - Restore the TUI happy path

Goal: make the documented first-run path usable.

### Task 1.1 - Fix TUI logging thread handling

Files:
- `tui_app.py`
- `tests/test_tui_contracts.py`

Steps:
1. Update `LogHandler.emit()` so it does not call `app.call_from_thread()` when
   already running on the Textual app thread.
2. Use a single helper for log-widget writes from app-thread and worker-thread
   contexts.
3. Keep background analysis logging safe for worker threads.
4. Add a contract test for app-thread log emission.

Validation:
- `py -m pytest tests/test_tui_contracts.py -v`
- `TERM=xterm timeout 5s py tui_app.py` from the repository root and from
  `tests/fixtures/`
- Manual TUI launch with computer use

### Task 1.2 - Add an end-to-end TUI smoke path

Files:
- `tui_app.py`
- `tests/test_tui_contracts.py`
- optional: `tests/test_tui_smoke.py`

Steps:
1. Add a smoke test that loads `tests/fixtures/gate_demo.csv`, populates
   headers, selects `issuer_name`, `Target`, `year_month`, `txn_cnt`,
   `card_type`, and `channel`.
2. Run share analysis through the shared `AnalysisRunRequest` seam.
3. Assert a report path and completion log are produced.
4. Capture at least one manual walkthrough after the automated smoke is green.

Validation:
- `py -m pytest tests/test_tui_contracts.py -v`
- `py scripts/perform_gate_test.py`
- Manual TUI video showing file selection, share run, and completion

### Task 1.3 - Improve file selection resilience

Files:
- `tui_app.py`
- `README.md`

Steps:
1. Ensure typing a CSV path manually triggers header loading when the field is
   submitted or loses focus.
2. Keep Browse as a convenience, not a single point of failure.
3. Show a clear validation message instead of crashing when a path is invalid.
4. Document both Browse and manual path entry in the TUI workflow.

Validation:
- Manual path entry smoke
- Browse selection smoke
- Invalid path smoke

## Phase 2 - Resolve CSV validator scope and docs mismatch

Goal: make validator behavior predictable for users and CI.

### Task 2.1 - Decide share validator fate

Options:
- Rate-only validator: rename docs and CLI output copy to state clearly that
  `utils/csv_validator.py` validates rate balanced totals only.
- Full validator: extend `utils/csv_validator.py` to validate share exports by
  comparing share CSV columns to share workbook columns.

Recommended first move: document the current rate-only scope, then add full
share validation only if downstream BI users need it.

Files:
- `README.md`
- `utils/CSV_VALIDATOR_README.md`
- `utils/csv_validator.py`
- `tests/test_csv_validator.py`

Validation:
- `py utils/csv_validator.py outputs/manual_rate.xlsx outputs/manual_rate_balanced.csv --verbose`
- `py -m pytest tests/test_csv_validator.py -v`

### Task 2.2 - Add validator UX guardrails

Steps:
1. Detect share CSVs before running rate validation.
2. If share validation is unsupported, fail with an explicit message:
   "share exports are not supported by this validator yet".
3. Ensure README examples use rate outputs when recommending the validator.

Validation:
- Share CSV validator invocation exits non-zero with an explanatory message.
- Rate CSV validator invocation passes.

## Phase 3 - Make first-run documentation executable

Goal: a new user can copy/paste docs and get a compliant report.

Files:
- `README.md`
- `tests/fixtures/gate_demo.csv`
- optional: `data/README.md`

Steps:
1. Replace the README tiny sample with a fixture-backed example that has at
   least one target and six peers.
2. Use Linux-friendly paths in the main examples, with Windows notes where
   useful.
3. Include one share command, one rate command, one TUI command, and expected
   success signals.
4. Add a "known local outputs" note so users know generated Excel/CSV/log files
   are ignored.

Validation:
- Run every command shown in the first-run section.
- `git diff --check`

## Phase 4 - Add CI for production gates

Goal: prevent regressions from merging without the same baseline checks that
manual review currently runs.

Files:
- `.github/workflows/ci.yml`
- `requirements-dev.txt`
- `AGENTS.md`

Steps:
1. Add a GitHub Actions workflow for Python 3.10 and 3.12 if dependency support
   allows it.
2. Install runtime and dev dependencies.
3. Run:
   - `ruff check --select E,F --ignore E501,F401 benchmark.py core/ utils/ tui_app.py`
   - `py -m pytest tests/ -v`
   - `py scripts/perform_gate_test.py`
4. Upload gate outputs as CI artifacts on failure.
5. Document CI as the required merge gate.

Validation:
- CI passes on a pull request.
- Local commands still pass.

## Phase 5 - Strengthen release and offline deployment

Goal: make production deployment repeatable on the offline Mastercard server.

Files:
- `SETUP.md`
- `deploy_and_install.ps1`
- `run_tool.sh`
- optional: `docs/RELEASE_PROCESS.md`

Steps:
1. Add a release checklist covering version, tests, gate, artifact bundle, and
   rollback.
2. Pin and verify offline package bundles.
3. Add a server-side smoke command that runs `share --help`, `config list`, and
   one fixture-backed analysis if a fixture is deployed.
4. Document how to recover from failed dependency installs.

Validation:
- Dry-run bundle generation locally.
- Run documented server smoke in a production-like environment when available.

## Phase 6 - Add golden and performance regression coverage

Goal: protect business-visible output and large-run behavior.

Files:
- `tests/fixtures/`
- `tests/test_golden_outputs.py`
- `scripts/`

Steps:
1. Create small golden fixtures for share, rate, peer-only, publication, and
   time-aware modes.
2. Assert stable workbook sheet presence, key metric ranges, compliance verdicts,
   and CSV schemas.
3. Add a larger synthetic benchmark for category/peer/time scaling.
4. Track runtime and solver stats without making tests flaky.

Validation:
- `py -m pytest tests/test_golden_outputs.py -v`
- Optional benchmark script with saved summary output

## Phase 7 - Productize the guided workflow

Goal: move from a technical tool to a production product.

Workstreams:
1. TUI guided wizard:
   - data import
   - schema mapping
   - validation preview
   - preset explanation
   - run progress
   - report summary
2. Run history:
   - input hash
   - config snapshot
   - preset
   - compliance verdict
   - output paths
3. Audit package:
   - workbook
   - CSV
   - audit log
   - config
   - validation summary
4. Optional web/API surface:
   - queued jobs
   - RBAC
   - signed audit artifacts
   - BI integration

Validation:
- Manual user walkthroughs for the happy path and common failure paths.
- Acceptance tests for run metadata and audit package contents.

## Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| TUI thread fix breaks worker-thread logging | Analysis logs stop appearing | Add tests for app-thread and worker-thread log emission |
| Share validator behavior is ambiguous | Users distrust exported CSVs | Make rate-only scope explicit or implement share validation |
| CI gate becomes slow/noisy | Developers bypass it | Keep gate fixture small and upload failure artifacts |
| Golden tests overfit formatting | Refactors become painful | Assert business invariants and schemas, not every cell |
| Offline packaging drifts from CI | Server install fails late | Build release bundles from the same locked dependencies CI uses |

## Definition of done

This plan is complete when:

1. The TUI can complete a share analysis from `gate_demo.csv` through user
   interaction.
2. CLI, gate, unit, lint, and relevant CSV validation checks pass.
3. README first-run commands are executable from a clean clone.
4. CI enforces the same checks.
5. Offline deployment has a documented, repeatable release path.
