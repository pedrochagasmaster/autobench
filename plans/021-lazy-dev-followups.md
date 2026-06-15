# Plan 021: Lazy-dev follow-ups — replace hand-rolled logic with pandas/stdlib and collapse duplicated helpers

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat fd40937..HEAD -- core/impact_calculator.py core/dimensional_analyzer.py utils/config_manager.py utils/config_overrides.py utils/validators.py utils/preset_manager.py utils/csv_validator.py core/analysis_run.py benchmark.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P3
- **Effort**: M
- **Risk**: LOW (steps 1–7) / MEDIUM (step 8)
- **Depends on**: none (lands cleanly on top of the PR that introduced this plan)
- **Category**: tech-debt
- **Planned at**: commit `fd40937`, 2026-06-14 (PR "lazy-dev cleanup")

## Why this matters

A "lazy senior dev" pass (the best code is the code never written) found several
spots where the codebase hand-rolls something pandas or the stdlib already does,
or keeps two copies of the same helper. The first cleanup PR took only the
**zero-risk deletions** (unused `ConfigManager` methods, a dead weight-map shim,
dead TUI nested wrappers, the legacy `ADVANCED_FIELD_MAP` adapter). This plan
covers the remaining items, which change live code paths and therefore need the
gate + CSV↔Excel cross-validation as a safety net rather than being folded into a
pure-deletion PR.

Net effect is fewer lines, fewer duplicated helpers, and analytics expressed in
the vocabulary the rest of the codebase already uses (pandas), at no new
dependency cost.

## Current state

All line references verified at commit `fd40937`.

1. **Hand-rolled summary stats** — `core/impact_calculator.py:228-315`
   `calculate_impact_summary` builds `summary_rows` by manually computing
   `mean/min/max/std/count` in three near-identical blocks (Overall, By
   Dimension, By Time Period) for the share path and again per rate column for
   the rate path. This is exactly `DataFrame.groupby(...).agg(['mean','min','max','std','count'])`.

2. **Manual rank maps** — `core/dimensional_analyzer.py` weight finalization
   (~lines 905-945) builds base/adjusted share dicts, calls `sorted(..., reverse=True)`
   twice, and assembles `{peer: i+1}` rank maps by hand. `pandas.Series.rank(ascending=False, method='first')` is the edge-case-correct one-liner (ties → stable first-seen order, matching "1 = highest share").

3. **Triplicated nested dict access** — after the first PR removed the TUI copy,
   two implementations of the same walk remain: the canonical
   `utils/config_overrides.py:50-76` (`nested_get`/`nested_set`) and
   `utils/config_manager.py` `ConfigManager.get` (`:761`) + `_set_nested` (`:745`),
   which re-implement the identical descent.

4. **Lean-mode profile = 17 manual `_set_nested` calls** —
   `utils/config_manager.py:680` `_apply_runtime_profiles` writes ~17 hard-coded
   paths one `_set_nested` call at a time. The class already has a deep-merge:
   `_merge_config` (`:564`). One nested override dict + one `_merge_config` call
   is the same behavior, fewer lines, no new dependency.

5. **Duplicated BIC-percentile assembly** — `core/analysis_run.py:1042-1046` and
   `:1123-1127` are the same block building a `bic_percentiles` dict from the
   config default + per-request `approval`/`fraud` overrides.

6. **`benchmark.py` compatibility wrappers** — `benchmark.py:37` `get_presets_help`
   reimplements a subset of `PresetManager.format_preset_list()`; `benchmark.py:402`
   `run_preset_comparison` is a pure pass-through to
   `core.preset_comparison.run_preset_comparison`. Tests import the CLI copies
   (`tests/test_enhanced_features.py`).

7. **Duplicate raw config loading + stdlib hygiene** —
   `utils/validators.py:load_config` does YAML/JSON load with an **inline**
   `import json`; `utils/config_manager.py` `_file_declares_posture` re-opens and
   parses the same file shapes without validation. Also `YAML_AVAILABLE`
   try/import is duplicated in `utils/validators.py` and `utils/preset_manager.py`.

8. **`csv_validator.load_excel_data` manual sheet walk** —
   `utils/csv_validator.py:63-119` iterates openpyxl rows by hand, detects the
   header row ("Category" present), and assembles a list-of-lists → DataFrame per
   sheet. `pandas.read_excel(..., sheet_name=..., header=None, engine='openpyxl')`
   plus a header-row scan covers it. **Medium risk**: this is the tool that
   cross-checks Control 3.2 CSV exports against the workbook — numeric parity is
   non-negotiable, so it lands last and behind the gate.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Full suite | `py -m pytest tests/ -q` | all pass |
| Gate (CSV↔Excel cross-validation) | `py scripts/perform_gate_test.py` | `Passed 18, Failed 0, Errors 0` |
| Lint | `py -m ruff check .` | all checks passed |
| Typecheck (local-only) | `py -m mypy core/ utils/` | no new errors vs baseline |
| CSV validator spot check (step 8) | `py utils/csv_validator.py <report>.xlsx <report>_balanced.csv --verbose` | matches pre-change output |

## Scope

**In scope**: `core/impact_calculator.py`, `core/dimensional_analyzer.py`,
`utils/config_manager.py`, `utils/config_overrides.py`, `utils/validators.py`,
`utils/preset_manager.py`, `utils/csv_validator.py`, `core/analysis_run.py`,
`benchmark.py`, and the directly affected tests
(`tests/test_enhanced_features.py`, plus any test asserting summary-row order).

**Out of scope**:
- The deprecated `DimensionalAnalyzer` v4.0 wrappers (`calculate_global_weights`,
  `calculate_share_distortion`, etc.) kept alive by `tests/test_legacy_wrappers.py`
  — intentional deprecation surface, removed on the v4.0 schedule, not here.
- `_weighted_percentile` (`core/dimensional_analyzer.py`) — already numpy-based;
  there is no simpler stdlib weighted-percentile.
- `ConfigValidator` (`utils/validators.py`) — replacing it would *add* a
  dependency (jsonschema/pydantic), the opposite of lazy.
- Any god-module split of `analysis_run.py` / `dimensional_analyzer.py` — see the
  README's "Deliberately deferred" section.

## Git workflow

- Branch: `cursor/021-lazy-dev-followups-<suffix>`
- One commit per numbered step; message style `refactor: <imperative>` / `perf: <imperative>` / `fix: <imperative>`.
- Do NOT force-push or amend. Do NOT open a PR unless instructed.

## Steps

Order is by ascending risk. Stop at any step and ship what's green if later steps reveal parity problems.

### Step 1: Collapse the nested-dict helpers (item 3)

Have `ConfigManager.get` and `_set_nested` delegate to
`config_overrides.nested_get` / `nested_set` (import at top of
`utils/config_manager.py`). Keep the public `get(*path, default=None)` signature
unchanged (it accepts varargs and a default; `nested_get` returns `None` for a
missing path, so apply the `default` after the call).

**Verify**: `py -m pytest tests/test_config_precedence*.py tests/test_tui_contracts.py -q` → all pass; full suite green.

### Step 2: Lean-mode profile via `_merge_config` (item 4)

In `_apply_runtime_profiles`, build one nested dict of the lean-mode overrides
and pass it to `self._merge_config(...)` instead of 17 sequential `_set_nested`
calls. Confirm `_merge_config` is a *deep* merge (it is — `:564`) so unrelated
keys are preserved.

**Verify**: `py -m pytest tests/ -q` → all pass. If a lean-mode test exists, it must still assert the same resolved values.

### Step 3: De-duplicate BIC-percentile assembly (item 5)

Extract a small helper (free function in `core/analysis_run.py` or a method on
`AnalysisRunRequest`) that builds the `bic_percentiles` dict from
`(config_default, approval_override, fraud_override)`, and call it at both
`:1042` and `:1123`.

**Verify**: `py -m pytest tests/ -q` and `py scripts/perform_gate_test.py` → both green (rate-mode gate cases exercise this).

### Step 4: Remove `benchmark.py` compatibility wrappers (item 6)

- Replace `get_presets_help` body with a call to `PresetManager().format_preset_list()` (trim/prepend the CLI header only if the help text visibly changes).
- Delete `run_preset_comparison` from `benchmark.py`; update `tests/test_enhanced_features.py` to import `run_preset_comparison` from `core.preset_comparison`.
- First search for other importers: `rg -n "from benchmark import|benchmark\.run_preset_comparison|benchmark\.get_presets_help"`.

**Verify**: `py benchmark.py config list` shows the preset table; `py -m pytest tests/test_enhanced_features.py -q` → all pass.

### Step 5: Single raw-config loader + stdlib hygiene (item 7)

- Add `load_raw_config(path) -> dict` (stdlib `json.loads` + `yaml.safe_load` over `Path(path).read_text(encoding="utf-8")`); use it in both `validators.load_config` (then validate) and `ConfigManager._file_declares_posture`.
- Move the inline `import json` in `load_config` to module top.
- Collapse the duplicated `YAML_AVAILABLE` try/import into one shared flag.

**Verify**: `py -m pytest tests/ -q` → all pass; `py -m ruff check .` → clean.

### Step 6: Vectorize `calculate_impact_summary` (item 1)

Rewrite the share and rate paths using `groupby(...).agg(['mean','min','max','std','count'])` + `pd.concat`, then `round(4)` once. **Preserve exactly**: column names (`Aggregation`, `Level`, `Mean_Impact_PP`, `Min_Impact_PP`, `Max_Impact_PP`, `Std_Impact_PP`, `Count`, and `Rate` on the rate path), the `Overall`/`By Dimension`/`By Time Period` ordering, the `std → 0.0 when count == 1` rule (pandas gives `NaN`; `fillna(0.0)` the std column), and the empty-frame early return.

**Verify**: add/extend one assert-based check that feeds a tiny known DataFrame and compares the output frame to the pre-change values (capture them first by running the current function). `py scripts/perform_gate_test.py` → green (gate builds impact/distortion sheets).

### Step 7: Vectorize rank computation (item 2)

Replace the manual sort + `{peer: i+1}` maps with a small DataFrame and
`Series.rank(ascending=False, method='first')` for `Base_Rank`/`Adjusted_Rank`;
`Delta = Adjusted_Rank - Base_Rank`. `method='first'` reproduces the existing
"first-seen wins ties" behavior of the `sorted()`+enumerate approach.

**Verify**: `py -m pytest tests/ -q` → all pass (rank-change tests exist); gate green; spot-check a Rank Changes sheet against a pre-change run.

### Step 8 (MEDIUM RISK, do last): `csv_validator.load_excel_data` via pandas (item 8)

Replace the manual openpyxl row walk with `pd.read_excel(path, sheet_name=...,
header=None, engine='openpyxl')` + a header-row scan. **Must** preserve
`data_only=True` semantics (read cached cell *values*, not formulas) — verify the
workbooks under test store cached values; if any sheet has formulas without
cached values, keep openpyxl for that path and STOP.

**Verify**: before changing, run `py utils/csv_validator.py` on a freshly
generated gate report and save the output. After changing, the output must be
byte-identical. `py scripts/perform_gate_test.py` → `Passed 18` (the gate runs
the CSV↔Excel cross-validation internally).

### Step 9: Full verification

**Verify**: `py -m pytest tests/ -q` (all pass) · `py scripts/perform_gate_test.py` (18/0/0) · `py -m ruff check .` (clean) · `py -m mypy core/ utils/` (no new errors).

## Test plan

- Steps 1–5, 7: covered by the existing suite + gate (no behavior change).
- Step 6: leaves behind ONE runnable assert-based check (smallest thing that
  fails if the groupby rewrite drifts) comparing the rewritten summary frame to
  pre-captured values for a tiny fixture.
- Step 8: parity proven by byte-identical `csv_validator` output + the gate's
  built-in cross-validation; no new test framework.

## Done criteria

- [ ] `ConfigManager.get`/`_set_nested` delegate to `config_overrides` helpers (no second copy of the walk)
- [ ] `_apply_runtime_profiles` uses a single `_merge_config` call
- [ ] One BIC-percentile builder, called at both `analysis_run` sites
- [ ] `benchmark.py` no longer defines `run_preset_comparison`; `get_presets_help` delegates to `PresetManager`
- [ ] One `load_raw_config`; no inline `import json`; one `YAML_AVAILABLE`
- [ ] `calculate_impact_summary` and the rank computation use pandas; outputs unchanged
- [ ] `csv_validator.load_excel_data` uses `pd.read_excel` with identical output (or step 8 reported as STOPed with reason)
- [ ] `py -m pytest tests/ -q`, `py scripts/perform_gate_test.py`, `py -m ruff check .` all green; `plans/README.md` row updated

## STOP conditions

- Any search reveals a caller this plan claims doesn't exist (drift since `fd40937`) — report; do not delete code with live callers.
- A pandas rewrite (step 6/7) changes any numeric value, column name, or row
  order in a gate output, or flips a Control 3.2 compliance verdict — revert that
  step and report. Compliance numerics are a legal requirement; never trade
  correctness for fewer lines.
- Step 8: a workbook sheet has formulas without cached values, or
  `csv_validator` output is not byte-identical — keep openpyxl for that path and
  report.
- mypy newly fails after a delegation/extraction and the fix is more than a
  one-line annotation — report instead of expanding scope.

## Maintenance notes

- These are independent; ship steps 1–5 even if 6–8 reveal parity issues.
- The `csv_validator` swap (step 8) intersects the SECURITY-06 note in
  `plans/README.md` ("openpyxl XML-bomb on csv_validator reads", accepted risk,
  trusted-input utility). `pd.read_excel` still uses openpyxl under the hood, so
  the risk posture is unchanged — no new mitigation needed.
- Mark any intentional simplification at the code site with a `ponytail:` comment
  naming the ceiling and upgrade path if the shortcut has one (e.g. the header-row
  scan in step 8 assumes the "Category" marker — note it).
