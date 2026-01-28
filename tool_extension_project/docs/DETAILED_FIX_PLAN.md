# Detailed Fix Plan

This plan expands the review findings into concrete, ordered work items with file-level guidance, edge cases, and test coverage. It assumes:
- Validation hard-fails on ERRORs.
- Preset comparison is exhaustive (all presets + per-dimension variants).
- Distortion/weight-effect calculations are **target vs peers**.

## Phase 0 — Quick Safety Checks (pre-work)
- Confirm current diff scope and uncommitted files.
- Identify whether any generated outputs in repo should be excluded before finalizing fixes.

## Phase 1 — Validation correctness and TUI parity (highest risk)

### 1.1 Fix TUI ValidationModal crash
**File:** `tui_app.py`  
**Issue:** Modal tries to read `issue.context` which does not exist.  
**Fix:**
- Remove `issue.context` usage.
- If extra context is needed, use `row_indices` or add a new optional field to `ValidationIssue` (but update dataclass and all call sites).
**Edge cases:**
- Empty issues list should still render cleanly.

### 1.2 Correct TUI validation calls + enforce hard-fail
**File:** `tui_app.py`  
**Issue:** Wrong function signatures and exceptions are ignored, then analysis proceeds.  
**Fix:**
- Call `validate_share_input(df, metric, entity_col, dimensions, time_col, target_entity, thresholds)`.
- Call `validate_rate_input(df, total_col, numerator_cols, entity_col, dimensions, time_col, target_entity, thresholds)`.
- Build `numerator_cols` dict from approved/fraud.
- If `issues` contains any ERROR, abort and keep the run button enabled.
- Remove "proceed anyway" path for validation exceptions; validation errors should hard-fail unless validation is disabled.
**Edge cases:**
- Auto-detected dimensions vs manual selections.
- Missing file path or CSV load failure.

### 1.3 Use config thresholds in validation
**Files:** `benchmark.py`, `tui_app.py`  
**Fix:**
- Load thresholds from `config.get('input', 'validation_thresholds')`.
- Pass thresholds into validation functions.
**Edge cases:**
- Missing thresholds config should fallback to defaults.

### 1.4 Emit Data Quality sheet in analysis output
**Files:** `benchmark.py`, `core/report_generator.py`  
**Fix:**
- Capture `validation_issues` in metadata.
- Use `ReportGenerator.add_data_quality_sheet()` (or equivalent) for analysis workbook if validation ran.
**Edge cases:**
- Validation disabled should skip the sheet.

## Phase 2 — Correct distortion/weight-effect math (core correctness)

### 2.1 Fix enhanced CSV share math (target vs peers)
**File:** `benchmark.py` (inside `export_balanced_csv` share block)  
**Current bug:** Uses portfolio totals for share, not target vs peers.  
**Fix:**
- When calculating raw share:
  - `raw_share = target_raw / (target_raw + raw_peer_total)`
- When calculating balanced share:
  - `balanced_share = target_raw / (target_raw + balanced_peer_total)`
- Compute distortion as `balanced_share - raw_share`.
**Edge cases:**
- Target entity not present in category/time (share should be 0 with explicit handling).
- Peer-only mode: define distortion as percent change in totals or skip with a clear rule.

### 2.2 Fix enhanced CSV rate math (peer-only weighted effect)
**File:** `benchmark.py` (inside `export_balanced_csv` rate block)  
**Current bug:** Includes target in peer totals.  
**Fix:**
- For raw peer rate: sum numerators/denominators from peers only.
- For balanced peer rate: sum weighted peer numerators/denominators only.
- Weight effect = balanced peer rate - raw peer rate.
**Edge cases:**
- Denominator = 0: set rate 0 and avoid divide-by-zero.
- Missing approved/fraud columns when not requested.

### 2.3 Fix `DimensionalAnalyzer.calculate_share_distortion`
**File:** `core/dimensional_analyzer.py`  
**Current bug:** Requires global weights; fails for per-dimension mode; uses weights without peer fallback.  
**Fix:**
- Allow per-dimension mode by merging dimension weights with global weights.
- If global weights absent but per-dimension weights exist, still compute.
**Edge cases:**
- Missing peers in per-dimension weights should fall back to global weights (not 1.0).

### 2.4 Fix `DimensionalAnalyzer.calculate_rate_weight_effect`
**File:** `core/dimensional_analyzer.py`  
**Current bug:** Same as share — requires global weights, includes target.  
**Fix:**
- Exclude target entity from peer calculations.
- Merge per-dimension weights with global weights.
**Edge cases:**
- Peer-only mode: treat all entities as peers (no target exclusion).

## Phase 3 — Exhaustive preset comparison

### 3.1 Enumerate all presets and per-dimension variants
**File:** `benchmark.py` (`run_preset_comparison`)  
**Fix:**
- Use `PresetManager.list_presets()` for base list.
- For each preset, include a `+perdim` variant.
**Edge cases:**
- Skip duplicates if a preset already implies per-dimension mode.
- Ensure consistent naming for the comparison sheet (e.g., `balanced_default+perdim`).

### 3.2 Rate preset comparison for multi-rate
**File:** `benchmark.py` (`run_preset_comparison`)  
**Fix:**
- Compute effect summary per rate type (approval/fraud).
- Define selection rule (e.g., maximize worst-case or average across rate types).
**Edge cases:**
- Only approval or only fraud present.

## Phase 4 — Publication output wiring

### 4.1 Enable publication workbook generation
**Files:** `benchmark.py`, `core/report_generator.py`  
**Fix:**
- Read `output_format` from config and call `generate_publication_workbook` for `publication` or `both`.
- Choose output filename suffix: `_publication`.
**Edge cases:**
- If `output` is explicitly set, derive a safe publication filename without overwriting.

### 4.2 Avoid mutating analysis DataFrames
**File:** `core/report_generator.py`  
**Fix:**
- Copy DataFrames before converting fraud rates to BPS.
- Apply conversion only to intended columns (not BIC or weight-effect).
**Edge cases:**
- Multi-rate sheets with both approval and fraud columns.

## Phase 5 — Config and flag parity

### 5.1 Use merged config instead of CLI args
**Files:** `benchmark.py`  
**Fix:**
- Replace direct `getattr(args, ...)` checks for enhanced features with values from `config.get(...)`.
**Edge cases:**
- `--no-validate-input` must override config default correctly.

### 5.2 Avoid ambiguous CSV naming
**File:** `benchmark.py`  
**Fix:**
- Keep original metric names instead of replacing with `Metric`.
**Edge cases:**
- Multiple secondary metrics must remain distinct.

## Phase 6 — Tests (minimum coverage)

### 6.1 Unit tests
**File:** `tests/test_enhanced_features.py`  
**Add tests:**
- Target-vs-peer distortion math for share.
- Target-vs-peer weight effect for rate.
- Per-dimension weight fallback.
- Validation hard-fail path.

### 6.2 Integration tests
**Add new test file:** `tests/test_cli_enhanced.py`  
**Scenarios:**
- Share with `--analyze-distortion --export-balanced-csv --include-calculated`.
- Rate with approval+fraud and `--analyze-distortion`.
- `--compare-presets` includes `+perdim`.
- `--output-format both` produces analysis + publication workbooks.

## Phase 7 — Documentation reconciliation

### 7.1 Update `README.md` and `AGENTS.md`
- Ensure the documented behavior matches the hard-fail validation, exhaustive presets, and target-vs-peer distortion.

### 7.2 Align workflows
- Update `RATE_ANALYSIS_WORKFLOW.md` and `SHARE_ANALYSIS_WORKFLOW.md` to reflect built-in comparison and distortion logic.

## Exit Criteria
- Validation hard-fails in CLI and TUI with correct issue list.
- Preset comparison lists all presets and per-dimension variants.
- Distortion/weight-effect math matches target-vs-peers definition.
- Publication workbook is generated when requested.
- Enhanced CSV math is correct and backward-compatible.
- Tests cover core paths without relying on external output files.
