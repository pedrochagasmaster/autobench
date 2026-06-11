# Plan 009: Remove dead code and refactor leftovers (uncalled report entry points, 13-line shim, analyzer_ref, CLI passthroughs)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat e0950c4..HEAD -- core/excel_reports.py core/privacy_validation_builder.py core/analysis_run.py core/audit_log.py benchmark.py core/dimensional_analyzer.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: tech-debt
- **Planned at**: commit `e0950c4`, 2026-06-10

## Why this matters

Several refactor waves (report-model extraction, orchestration extraction) left dead entry points and shims that mislead readers about the real code paths: two large uncalled functions in `core/excel_reports.py`, a 13-line adapter module, a live object reference stored in serializable metadata (with a special-case strip at audit-write time), and compatibility passthroughs in `benchmark.py` that keep tests importing from the wrong layer. Removing them shrinks the surface an agent or contributor must read to understand output generation.

## Current state

All claims below verified at commit `e0950c4`:

1. **Dead report entry points** — `core/excel_reports.py:38-83` `generate_excel_report(...)` and `:146-200` `generate_multi_rate_excel_report(...)` have **zero callers** (`rg -n "generate_excel_report|generate_multi_rate_excel_report" -t py` matches only their definitions; `core/report_generator.py`'s `_generate_excel_report` is a different, used method). The live path is `generate_report_model_excel` / `generate_multi_rate_report_model_excel` (`core/excel_reports.py:85-143`), called from `core/output_artifacts.py`.
2. **Shim module** — `core/privacy_validation_builder.py` is in its entirety:

```python
def build_privacy_validation_dataframe(analyzer, df, metric_col, dimensions) -> pd.DataFrame:
    return build_privacy_validation_result(analyzer, df, metric_col, dimensions).to_dataframe()
```

   Its only importer is `core/dimensional_analyzer.py` (import near line 29; the consumer is the **method definition** `DimensionalAnalyzer.build_privacy_validation_dataframe` around lines 1272-1274, whose body just forwards to the shim function).
3. **Live object in metadata** — `core/analysis_run.py:1035` stores `'analyzer_ref': analyzer` in share-mode metadata; `core/audit_log.py:22` strips it at write time. Test documenting the leak: `tests/test_benchmark_orchestration_helpers.py:574-609`.
4. **CLI passthroughs** — `benchmark.py:40-69`: `_resolve_consistency_mode` and `_build_dimensional_analyzer` are one-line forwards to `core.analysis_run` helpers ("Compatibility wrapper" docstrings). `tests/test_benchmark_orchestration_helpers.py:9` imports them from `benchmark`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Full suite | `py -m pytest tests/ -q` | all pass |
| Gate | `py scripts/perform_gate_test.py` | exit 0 |
| Lint | `py -m ruff check --select E,F --ignore E501,F401 benchmark.py core/ utils/ tui_app.py` | exit 0 |
| Typecheck | `py -m mypy core/ utils/` | exit 0 |

## Scope

**In scope**:
- `core/excel_reports.py` (delete two functions)
- `core/privacy_validation_builder.py` (delete file)
- `core/dimensional_analyzer.py` (inline the shim call)
- `core/analysis_run.py` (remove `analyzer_ref`)
- `core/audit_log.py` (remove the strip special-case)
- `benchmark.py` (remove passthroughs)
- `tests/test_benchmark_orchestration_helpers.py` (update imports/assertions)

**Out of scope**:
- The deprecated `DimensionalAnalyzer` wrapper APIs (`calculate_global_weights`, `calculate_share_distortion`, etc., scheduled for v4.0 with `DeprecationWarning`s and kept alive by `tests/test_legacy_wrappers.py`) — they are *intentional* deprecation surface, not dead code.
- Any consolidation of `output_artifacts`/`excel_reports`/`report_generator` layering beyond deleting the dead functions — larger refactor, not this plan.

## Git workflow

- Branch: `advisor/009-dead-code-cleanup`
- One commit per numbered step; message style: `refactor: <imperative>` / `chore: <imperative>`
- Do NOT push or open a PR unless instructed.

## Steps

### Step 1: Delete the dead report entry points

Remove `generate_excel_report` and `generate_multi_rate_excel_report` from `core/excel_reports.py`. Then re-run the caller check.

**Verify**: `py -m pytest tests/ -q` → all pass; `rg -n "\bgenerate_excel_report\b" -t py` matches only `report_generator.py`'s private `_generate_excel_report`.

### Step 2: Delete the shim module

In `core/dimensional_analyzer.py`, replace the import of `core.privacy_validation_builder` with a direct import of `build_privacy_validation_result` from `core.privacy_validation`, and inline `.to_dataframe()` at the call site (~lines 1272-1274). Delete `core/privacy_validation_builder.py`.

**Verify**: `py -m pytest tests/ -q` → all pass; `rg -n "privacy_validation_builder" -t py` → no matches (exit code 1).

### Step 3: Remove `analyzer_ref` from metadata

- In `core/analysis_run.py` (~line 1035), delete the `'analyzer_ref': analyzer` entry. First check what consumes it: `rg -n "analyzer_ref" -t py` — expected consumers are `core/audit_log.py:22` (the strip) and the test. If anything else reads it, STOP.
- In `core/audit_log.py:22`, remove the now-unneeded strip.
- Update `tests/test_benchmark_orchestration_helpers.py:574-609` — the test that asserts the strip behavior should now assert `analyzer_ref` is absent from metadata in the first place.

**Verify**: `py -m pytest tests/test_benchmark_orchestration_helpers.py -q` → all pass; `rg -n "analyzer_ref" -t py` → no matches (exit code 1).

### Step 4: Remove `benchmark.py` passthroughs

Delete `_resolve_consistency_mode` and `_build_dimensional_analyzer` from `benchmark.py` (lines 40-69) and their now-unused imports. Update `tests/test_benchmark_orchestration_helpers.py` to import the real helpers from `core.analysis_run` instead — note the real names have **no leading underscore**: `resolve_consistency_mode` and `build_dimensional_analyzer`. Search for any other importers first: `rg -n "_resolve_consistency_mode|_build_dimensional_analyzer" -t py`

**Verify**: `py -m pytest tests/ -q` → all pass.

### Step 5: Full verification

**Verify**: `py scripts/perform_gate_test.py` → exit 0; `py -m ruff check --select E,F --ignore E501,F401 benchmark.py core/ utils/ tui_app.py` → exit 0; `py -m mypy core/ utils/` → exit 0.

## Test plan

No new tests — this is deletion. The existing suite + gate are the safety net; the one behavioral test updated is the `analyzer_ref` strip test (now asserts absence).

## Done criteria

- [ ] `core/privacy_validation_builder.py` no longer exists
- [ ] `rg -n "analyzer_ref|privacy_validation_builder" -t py` → no matches (exit code 1)
- [ ] `generate_excel_report`/`generate_multi_rate_excel_report` (module-level, `excel_reports.py`) deleted
- [ ] `benchmark.py` no longer defines `_resolve_consistency_mode` / `_build_dimensional_analyzer`
- [ ] `py -m pytest tests/ -q`, `py scripts/perform_gate_test.py`, lint, and `py -m mypy core/ utils/` all exit 0
- [ ] `plans/README.md` status row updated

## STOP conditions

- Any search in steps 1–4 reveals a caller this plan claims doesn't exist (drift since `e0950c4`) — report it; do not delete code with live callers.
- Something outside `audit_log.py`/tests reads `analyzer_ref` (e.g. debug sheets pulling optimizer facts off the live object) — report; replacing it with a serializable summary is a design change beyond this plan.
- mypy newly fails in `core/dimensional_analyzer.py` after inlining — fix the type annotation if trivial (one line); otherwise report.

## Maintenance notes

- After this lands, the only Excel write path is `output_artifacts → excel_reports.generate_report_model_excel → ReportGenerator.generate_report_model`. The audit's larger layering consolidation (DEBT-05 remainder) is easier afterwards and remains open.
- v4.0 deprecation removals (`test_legacy_wrappers.py`) are a separate, scheduled task — don't bundle.
