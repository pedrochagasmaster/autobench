# Plan 010: Speed up output generation — bulk Excel row writes and vectorized balanced-export math

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat e0950c4..HEAD -- core/report_generator.py core/balanced_export.py core/impact_calculator.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW
- **Depends on**: plans/003-analysis-run-integration-test.md (safety net), plans/007-sanitize-formula-injection.md (touches the same write sites — land 007 first to avoid conflicts)
- **Category**: perf
- **Planned at**: commit `e0950c4`, 2026-06-10

## Why this matters

Every run pays Python-loop costs at the output stage: Excel sheets are written cell-by-cell with nested loops (orders of magnitude slower than bulk row appends for large validation/impact sheets), and the balanced CSV export computes weighted sums via `iterrows` inside dimension × category × time × metric loops — `O(D × C × T × M × P)` Python-level iteration where a vectorized multiply-and-sum would do. On export-heavy runs (debug sheets, impact analysis, balanced CSV) this adds many seconds per run and multiplies across the 18-case gate.

## Current state

- `core/report_generator.py:366-368` — DataFrame body written cell-by-cell:

```python
for r_idx, row_data in enumerate(result_data.itertuples(index=False), start=row):
    for c_idx, value in enumerate(row_data, start=1):
        worksheet.cell(row=r_idx, column=c_idx, value=value)
```

  Same pattern at `:423-425` (`_write_optional_dataframe_sheet`, routed through `_excel_safe_value`). Per-cell styling on the publication path (~lines 857-870) and a column-width pass iterating every cell of every column (~lines 889-900) — read those regions before editing.
- openpyxl's fast path already exists in this codebase: `dataframe_to_rows` / `ws.append` is used around `core/report_generator.py:491` (preset-comparison sheet) — that is the pattern to converge on.
- `core/balanced_export.py:111-115` — the iterrows hot loop:

```python
balanced_metric = 0.0
for _, row in cat_df.iterrows():
    peer = row[entity_col]
    weight = weights.multiplier(peer, dimension)
    balanced_metric += row[metric] * weight
```

  Similar sites at `balanced_export.py:285`, `:475`, `:510`, and in `core/impact_calculator.py` at `:80-84`, `:112-116`, `:186-190`, `:226-230` (per the audit; verify each with `rg -n "iterrows" core/balanced_export.py core/impact_calculator.py`).
- `weights.multiplier(peer, dimension)` comes from `WeightLookup` (`core/balanced_export.py:407` — `WeightLookup.from_analyzer(analyzer)`). The per-dimension map you need **already exists**: `WeightLookup.map_for_dimension(dimension)` (`core/contracts.py:259-265`), and `core/impact_calculator.py:15-16` already has a `build_weight_map_for_dimension()` helper using it — reuse these instead of hand-building `{peer: multiplier}` dicts.
- Gate cross-validation (`scripts/perform_gate_test.py` invoking `utils/csv_validator.py`) compares CSV values against Excel values — your refactor must be **numerically identical**, not just close. Beware: summing order can change float results at the 1e-15 level; the validator and gate use tolerances (check `utils/csv_validator.py` for its comparison tolerance before assuming exactness matters).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Full suite | `py -m pytest tests/ -q` | all pass |
| Gate (the real check) | `py scripts/perform_gate_test.py` | exit 0, 18 cases |
| Integration | `py -m pytest tests/test_analysis_run_integration.py -q` (file created by plan 003 — skip this row if 003 has not landed) | all pass |
| Typecheck | `py -m mypy core/ utils/` | exit 0 (note: `core.balanced_export` has `ignore_errors=True` in mypy.ini) |

## Scope

**In scope**:
- `core/report_generator.py` (write loops only — no sheet-content changes)
- `core/balanced_export.py` (computation vectorization only — no schema changes)
- `core/impact_calculator.py` (same)

**Out of scope**:
- `core/solvers/lp_solver.py`, `core/subset_search.py` — LP-side performance (audit PERF-01/04) is a larger separate effort, deliberately not planned this round.
- `core/analysis_run.py` orchestration — no shared-aggregation refactor here (audit PERF-03).
- Sheet names, column orders, number formats — structure and values must be identical; purely cosmetic cell-style differences are acceptable only where Step 4 explicitly says so (the gate checks structure/values, not styles).

## Git workflow

- Branch: `advisor/010-output-performance`
- Commit per file; message style: `perf: <imperative>`
- Do NOT push or open a PR unless instructed.

## Steps

### Step 1: Baseline timing

Record a before number so the win is measurable:

```powershell
Measure-Command { py benchmark.py share --csv tests/fixtures/gate_demo.csv --entity Target --metric txn_cnt --dimensions card_type channel --time-col year_month --preset balanced_default --debug --analyze-impact --export-balanced-csv --include-calculated --output plans_perf_before.xlsx }
```

Note the `TotalSeconds`. Delete the generated files afterward (they're gitignored anyway).

### Step 2: Vectorize `balanced_export.py`

For each iterrows site, replace with a mapped multiply-sum. Pattern (adapt to local variable names):

```python
weight_map = weights.map_for_dimension(dimension)  # existing helper, core/contracts.py:259-265
balanced_metric = float((cat_df[metric] * cat_df[entity_col].map(weight_map)).sum())
```

Hoist `weight_map` out of inner loops where `dimension` doesn't change (one map per dimension, reused across categories/time/metrics). Preserve existing NaN handling: check how the current loop treats NaN metric values (`row[metric] * weight` with NaN propagates; `.sum()` skips NaN by default — use `.sum(skipna=False)` if and only if the old code propagated NaN; confirm by reading each site).

**Verify**: `py scripts/perform_gate_test.py` → exit 0 (this includes CSV↔Excel cross-validation of the rate export).

### Step 3: Vectorize `impact_calculator.py`

Same transformation at the four iterrows sites. The weighted-total semantics are identical.

**Verify**: `py -m pytest tests/ -q` → all pass; gate → exit 0.

### Step 4: Bulk-write Excel DataFrame bodies

In `core/report_generator.py`, convert the two cell-by-cell DataFrame writers to row-wise appends. For `_write_optional_dataframe_sheet` (the sheet is created fresh, so append order is clean):

```python
from openpyxl.utils.dataframe import dataframe_to_rows
...
for row_values in df.itertuples(index=False, name=None):
    ws.append([self._excel_safe_value(v) for v in row_values])
```

(`ws.append` after writing the header row continues below it.) For the in-place writer — the method is `_write_metric_sheet`, `core/report_generator.py:339-368` — the sheet may already have content above `row`; keep cursor semantics: either keep `cell()` but write whole rows via `ws.append` when the write starts at the sheet's current max row, or batch with a single loop over `itertuples(name=None)` writing lists. The essential change: eliminate the per-cell Python attribute machinery where possible, keep header styling (bold font on header row only).

Do NOT change the column-width pass or per-cell publication styling in this step unless trivial — if the width pass (~889-900) is a measurable cost, cap it to sampling the first 50 rows per column, preserving the same width formula.

**Verify**: gate → exit 0; open one gate workbook manually if in doubt about header bolding (cosmetic-only differences are acceptable per gate, which checks structure/values, not styles).

### Step 5: After timing + full verification

Re-run the Step 1 command; record `TotalSeconds`. Expect a reduction on this small fixture (modest) — the structural win shows on large data.

**Verify**: `py -m pytest tests/ -q` → all pass; `py scripts/perform_gate_test.py` → exit 0; `py -m mypy core/ utils/` → exit 0. Report before/after seconds in the PR description.

## Test plan

No new tests required — numerical equivalence is enforced by the gate's CSV↔Excel cross-validation and existing golden-output tests (`tests/test_golden_outputs.py`). If you want extra confidence on Step 2, add one unit test comparing the vectorized weighted sum against an explicit Python-loop computation on a small frame with a NaN value included.

## Done criteria

- [ ] `rg -n "iterrows" core/balanced_export.py core/impact_calculator.py` → no matches (exit code 1)
- [ ] `py scripts/perform_gate_test.py` exits 0 (CSV↔Excel cross-validation passes)
- [ ] `py -m pytest tests/ -q` exits 0
- [ ] Before/after timing recorded in the PR/commit message
- [ ] `plans/README.md` status row updated

## STOP conditions

- Gate cross-validation reports value mismatches after Step 2/3 — your NaN or ordering semantics differ from the original loop. Revert the specific site, study the old behavior, retry once; if it still mismatches, report with the differing values.
- `WeightLookup.multiplier` turns out to have per-row (not per-peer-per-dimension) behavior — the hoisted map would be wrong; report.
- The in-place Excel writer (Step 4) feeds sheets where rows are interleaved with non-DataFrame content in a way `append` can't reproduce — leave that site as-is and note it; the optional-sheet writer is the bigger win.

## Maintenance notes

- New export columns must use vectorized patterns — reviewers should reject new `iterrows` in these files.
- The larger aggregation-reuse refactor (one shared fact table across optimization/validation/export — audit PERF-03) and LP-side caching (PERF-01/04) remain open and are where the next order-of-magnitude lives.
