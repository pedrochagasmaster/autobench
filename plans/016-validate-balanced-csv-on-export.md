# Plan 016: Validate the balanced CSV against the workbook automatically on export

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat e0950c4..HEAD -- core/analysis_run.py utils/csv_validator.py core/audit_package.py utils/config_manager.py benchmark.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none (plan 003's integration test is a helpful net)
- **Category**: direction
- **Planned at**: commit `e0950c4`, 2026-06-10

## Why this matters

The README tells BI users (Power BI/Tableau) to ingest the balanced CSV, and tells contributors to cross-check it against the workbook **manually** with `py utils/csv_validator.py <xlsx> <csv>`. The gate test already runs that exact validator as a subprocess for its rate-export cases — proving the check works — but production runs never do it. A divergence between CSV and Excel (a bug in either writer) would reach BI dashboards unnoticed until someone manually validates. Wiring the existing validator into the export path makes "audit-ready" true by default and surfaces the result in run metadata and the audit package.

## Current state

- `core/analysis_run.py:1503-1515` — the export call site inside `_execute_run`:

```python
if request.export_balanced_csv:
    mode_spec.export_balanced_csv_fn(...)
    artifacts.csv_output = analysis_output_file.rsplit('.', 1)[0] + '_balanced.csv'
```

  At this point `analysis_output_file` (the analysis workbook) has already been written by `write_outputs` (line 1502). The audit log (1522) and audit package (1534) are written *after* — so a validation result computed here can flow into both.
- `utils/csv_validator.py` — a print-based CLI script (`Usage: python utils/csv_validator.py <excel_file> <csv_file> [--tolerance PERCENT]`), exit code 0 on pass, 1 on failure. It auto-detects rate vs share exports (`is_share_export_csv`, lines 39-52) and time columns; share CSVs without `Balanced_*_Share_%` columns are not fully checkable (per README: "share exports are schema-checked by the gate unless a workbook exposes explicit `Balanced_*_Share_%` columns").
- The proven invocation pattern, from `scripts/perform_gate_test.py:477-486`:

```python
validator_script = self.root_dir / "utils" / "csv_validator.py"
cmd = [sys.executable, str(validator_script), str(analysis_file), str(csv_file)]
proc = subprocess.run(cmd, cwd=self.root_dir, capture_output=True, text=True)
if proc.returncode != 0:
    failures.append(f"CSV Validation failed:\n{proc.stdout}\n{proc.stderr}")
```

  Note the gate runs the full validator **only for rate exports**; for share exports it does a schema check (required columns `Dimension`, `Category`, ≥1 `Balanced_*` column) — see `scripts/perform_gate_test.py:463-476`. Mirror that split.
- `core/audit_package.py:32-44` — `build_validation_summary(metadata)` builds the `validation_summary.json` from metadata keys; a new key added to run metadata can be surfaced there with a one-line addition.
- Config: a new CLI flag needs **three** wiring points, not two: (1) `benchmark.py` (`create_parser`) declares the flag — follow the paired-boolean pattern of `--validate-input` / `--no-validate-input`; (2) `utils/config_manager.py:731-776` `_apply_cli_overrides` maps the flat key to a config path; (3) `COMMON_CLI_OVERRIDES` in `core/analysis_run.py:41-59` — the tuple of arg names that `build_run_config` (line ~167) forwards from the parsed args into `ConfigManager`. **Omitting (3) makes the flag silently dead.** Add `'validate_export'` there.
- Lean mode (`utils/config_manager.py:803-827`) disables optional heavy artifacts — the new validation must be off under lean.
- Note: `metadata` (the local dict in `_execute_run`) and `artifacts.metadata` are the same dict object (passed by reference into `build_analysis_artifacts`) — writing `metadata['export_validation']` is sufficient for both the audit log and the audit package to see it.
- Posture context: `balanced_default` (the default preset) sets `compliance_posture: "strict"` (`presets/balanced_default.yaml:3`) — so the strict fail-closed behavior in Step 2 applies to default-preset runs. That is intended (fail-closed by default); only `best_effort`/`accuracy_first` postures degrade to warn-only.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Manual validator run | `py utils/csv_validator.py <xlsx> <csv> --verbose` | exit 0 |
| Full suite | `py -m pytest tests/ -q` | all pass |
| Gate | `py scripts/perform_gate_test.py` | exit 0, 18 cases |
| Typecheck | `py -m mypy core/ utils/` | exit 0 |

## Scope

**In scope**:
- `core/analysis_run.py` (post-export validation hook)
- `benchmark.py` (CLI flag)
- `utils/config_manager.py` (config key + CLI mapping + lean-mode disable)
- `core/audit_package.py` (surface the result in `build_validation_summary`)
- `config/template.yaml` (document the new key)
- tests (new `tests/test_export_validation.py` or extend `tests/test_output_artifacts.py`)
- `README.md` (one paragraph: validation now automatic)

**Out of scope**:
- `utils/csv_validator.py` internals — invoke it as a subprocess exactly like the gate does; do not refactor it into a library in this plan (follow-up if the subprocess cost ever matters).
- TUI wiring — the config default covers TUI runs since both interfaces share `_execute_run`; no new widget.
- Share-export full validation — the validator cannot fully check share CSVs without share-percent columns; schema-check only, mirroring the gate.

## Git workflow

- Branch: `advisor/016-validate-export`
- Commit message style: `feat: validate balanced CSV against workbook on export`
- Do NOT push or open a PR unless instructed.

## Steps

### Step 1: Add the config key and CLI flag

- `utils/config_manager.py`: in `_get_default_config()` add `output.validate_export: true`. In `_apply_cli_overrides` mapping add `'validate_export': ('output', 'validate_export')`. In the lean-mode profile (`_apply_runtime_profiles`, ~line 803-827) set it to `False` alongside the other disabled artifacts.
- `core/analysis_run.py`: add `'validate_export'` to `COMMON_CLI_OVERRIDES` (lines 41-59) so the CLI value reaches `ConfigManager` (see Current state — without this the flag is dead).
- `benchmark.py` parser: add paired flags `--validate-export` / `--no-validate-export` (default `None` so the config default wins; follow exactly how `--validate-input`/`--no-validate-input` are declared and mapped).
- `config/template.yaml`: document the key under `output:` with a one-line comment.

**Verify**: `py benchmark.py share --help` shows the new flags; `py -m pytest tests/ -q` → all pass.

### Step 2: Add the validation hook in `_execute_run`

In `core/analysis_run.py`, immediately after `artifacts.csv_output` is set (line ~1515), when `config.get('output', 'validate_export', default=True)` and the CSV was exported and the analysis workbook exists:

- **Rate runs**: run the validator as a subprocess (pattern from the gate, excerpt above — use `sys.executable`, the repo-root-resolved `utils/csv_validator.py` path via `Path(__file__).resolve().parents[1] / "utils" / "csv_validator.py"`, `capture_output=True`). Record `metadata['export_validation'] = {'checked': True, 'passed': proc.returncode == 0, 'mode': 'full'}`.
- **Share runs**: schema check in-process (mirror `perform_gate_test.py:466-474`): required columns `Dimension`, `Category`, ≥1 `Balanced_*` column. Record the same metadata shape with `'mode': 'schema'`.
- On pass: log at INFO exactly `"Export validation passed (mode=%s): balanced CSV is consistent with the workbook"` — Step 2's manual verify and the tests key on the `Export validation passed` substring.
- On failure: log at ERROR (`"Export validation FAILED ..."` + the captured stdout/stderr tail); if the run posture (`compliance_context['compliance_posture']`) is `strict`, raise `RuntimeError("Balanced CSV failed cross-validation against the workbook")` after logging (artifacts stay on disk for debugging); otherwise continue with the metadata flag set to `passed: False`.
- Keep this entire block inside a `try/except` that converts unexpected validator-launch errors (not validation failures) into a logged warning + `{'checked': False}` — a broken validator must not take down non-strict runs.

**Verify**: run a rate export manually and confirm the log line:

```powershell
py benchmark.py rate --csv tests/fixtures/gate_demo.csv --entity Target --total-col total --approved-col approved --fraud-col fraud --dimensions card_type channel --time-col year_month --preset balanced_default --export-balanced-csv --output plans_v16.xlsx
```

→ exit 0, log contains `Export validation passed`. Delete the generated files.

### Step 3: Surface in the audit package

In `core/audit_package.py`'s `build_validation_summary` (lines 32-44), add `"export_validation": metadata.get("export_validation")`.

**Verify**: `py -m pytest tests/ -q` → all pass.

### Step 4: Tests

New tests (in `tests/test_export_validation.py`):
1. Rate run with `export_balanced_csv=True` → `artifacts.metadata['export_validation']['passed'] is True`, `'mode' == 'full'`. Drive via `core.analysis_run.execute_rate_run` directly (build the `AnalysisRunRequest` yourself; the pattern is `tests/test_analysis_run_integration.py` if plan 003 landed). Do NOT use `benchmark.run_rate_analysis` for assertions — it returns an `int` exit code, not artifacts.
2. Share run with export → `'mode' == 'schema'`, passed.
3. Tampered CSV: after a rate run, corrupt one `Balanced_Total` value in the CSV, invoke just the validation helper (factor the hook body into a testable function, e.g. `_validate_balanced_export(...) -> dict` in `core/analysis_run.py`) → `passed is False`.
4. `--no-validate-export` → `export_validation` absent or `checked: False`.
5. Lean mode (`lean=True`) → validation skipped.

**Verify**: `py -m pytest tests/test_export_validation.py -q` → all pass.

### Step 5: Docs + full verification

Add one paragraph to `README.md`'s "Validation and Testing" noting exports are now auto-validated and the manual command remains available for ad-hoc checks.

**Verify**: `py -m pytest tests/ -q` → all pass; `py scripts/perform_gate_test.py` → exit 0; `py -m mypy core/ utils/` → exit 0.

## Test plan

See Step 4 — pass, schema-mode, fail-detection, opt-out, lean-skip.

## Done criteria

- [ ] Rate exports run the cross-validator automatically; result lands in `metadata['export_validation']` and `validation_summary.json`
- [ ] Strict posture + validation failure fails the run; non-strict logs ERROR and continues
- [ ] `--no-validate-export` and lean mode skip it
- [ ] `py -m pytest tests/ -q`, `py scripts/perform_gate_test.py`, `py -m mypy core/ utils/` all exit 0
- [ ] `plans/README.md` status row updated

## STOP conditions

- The validator subprocess fails on a *clean* gate-fixture rate export (returncode ≠ 0 with no tampering) — the validator and exporter disagree at baseline; that is a real product bug (audit context: the gate currently passes, so this would be drift). Report with the validator output.
- The subprocess invocation cannot reliably resolve the script path when the package is run from a different cwd — report rather than hardcoding absolute paths.
- Adding the strict-posture `RuntimeError` breaks a gate case (a strict gate case with export exists and fails) — report the case id.

## Maintenance notes

- The validation helper is subprocess-based by design (reuses the gate-proven interface). If run volume makes the ~1s subprocess cost matter, the follow-up is extracting a library entry point from `utils/csv_validator.py` — keep the metadata contract identical.
- Plan 010 (vectorized exports) changes the CSV writer's math paths; this validation is precisely the net that catches an equivalence slip there — land whichever comes second with both in place.
