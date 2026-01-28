# Enhanced Analysis Implementation Plan

## Executive Summary
- Integrate five enhancements (preset comparison, distortion analysis, data quality validation, publication output, enhanced CSV) directly into `benchmark.py` and `tui_app.py`, reusing shared core logic in `core/`.
- Preserve current defaults and behavior unless new flags or UI options are explicitly enabled.
- Keep all privacy caps intact and ensure all optimization parameters continue to flow through `ConfigManager` merged config (no direct CLI bypass).
- Produce a single analysis workbook per run, plus a separate publication workbook when `output_format` is `publication` or `both`, and optional enhanced CSV.
- Eliminate the need for standalone scripts by embedding their logic as reusable functions.

## Part 1: CLI Integration (benchmark.py)

### 1.1 New Flag Definitions
Add flags to both `share` and `rate` subcommands in `create_parser()`:
- `--compare-presets` (bool, default False)
  - Runs the analysis for all available presets plus per-dimension variants and adds a "Preset Comparison" sheet.
- `--analyze-distortion` (bool, default False)
  - Computes distortion/weight-effect details and summaries and adds "Distortion Details" + "Distortion Summary" sheets.
- `--validate-input` / `--no-validate-input` (bool, default True)
  - Validation errors always abort (no CLI override to proceed).
- `--output-format` (choice: `analysis|publication|both`, default `analysis`)
  - Add `--publication-format` as a convenience alias for `--output-format=publication`.
- `--include-calculated` (bool, default False)
  - Only meaningful when `--export-balanced-csv` is set.
- `--fraud-in-bps` / `--no-fraud-in-bps` (rate only, default True)
  - Presentation-only conversion (percent to basis points) for publication output.

Config integration (to honor "opt_config" rule):
- Add new keys in default config and validators:
  - `input.validate_input` (bool)
  - `output.output_format` (str: analysis|publication|both)
  - `output.include_distortion_summary` (bool)
  - `output.include_preset_comparison` (bool)
  - `output.include_calculated_metrics` (bool)
  - `output.fraud_in_bps` (bool)
- Extend `ConfigManager._apply_cli_overrides()` mapping to map new flags to these keys.

### 1.2 Share Command Enhancements
Key entrypoint: `run_share_analysis()` in `benchmark.py`.

1. Data validation (pre-run)
   - After `df = data_loader.load_data(args)` and before analysis, call
     `data_loader.validate_share_input(...)`.
   - If any ERROR issues exist, abort with a clear log summary (no override).
   - If WARNINGS exist, log and continue.
   - Attach validation issues to metadata for report generation and TUI display.

2. Preset comparison (optional)
   - Add helper `run_preset_comparison(args, analysis_type='share', df, dimensions, metric_col, ...)`.
   - Use `PresetManager.list_presets()` to build the list of presets.
   - Include per-dimension variants for every preset (e.g., `preset+perdim`) and any
     additional preset combinations present in `presets/` (maximize comparisons).
   - Compute distortion summaries for each preset and return a comparison DataFrame.
   - Mark "Selected" for the best preset (lowest mean absolute distortion), but keep the
     primary analysis output using the user-specified preset (backwards compatible).

3. Distortion analysis (optional)
   - Compute distortion details directly from raw data and analyzer weights
     (see Part 2.2) instead of reading external CSVs.
   - Add a `distortion_details_df` (raw vs balanced share) and a `distortion_summary_df`
     (mean/min/max/std by dimension/category/time) and include both in output.

4. Publication format
   - If `output_format` is `publication` or `both`, generate a separate publication workbook
     with stakeholder-ready tables (analysis workbook remains intact).
   - Use generalized formatting patterns from `generate_market_share_report.py` and
     `generate_combined_report.py`.

5. Enhanced CSV
   - If `--export-balanced-csv` and `--include-calculated` are set, append
     `balanced_share_pct`, `raw_share_pct`, and `distortion_pp` for the primary metric.

### 1.3 Rate Command Enhancements
Key entrypoint: `run_rate_analysis()` in `benchmark.py`.

1. Data validation (pre-run)
   - Call `data_loader.validate_rate_input(...)` with total, approved, fraud columns.
   - Abort on ERROR issues (no override); continue with warnings.

2. Preset comparison (optional)
   - Reuse `run_preset_comparison(..., analysis_type='rate')`.
   - Include per-dimension variants for every preset to maximize comparisons.
   - Summarize weight effect metrics by rate type (approval/fraud).

3. Distortion/weight-effect analysis (optional)
   - Compute raw and balanced peer rates from raw data and weighted totals.
   - Produce both detailed and summary tables (mean/min/max/std).

4. Publication format
   - If `output_format` is `publication` or `both`, produce a separate publication workbook
     with simplified tables for approval and/or fraud.
   - If `fraud_in_bps` is enabled, convert fraud rates (percent * 100) in publication output only.

5. Enhanced CSV
   - Append computed rate metrics:
     `approval_rate_pct`, `fraud_rate_pct`,
     `weight_effect_approval_pp`, `weight_effect_fraud_pp`,
     plus raw rate columns (`raw_approval_rate_pct`, `raw_fraud_rate_pct`).
   - Preserve current columns and append new columns at the end.

### 1.4 Shared Helper Functions
Add shared helpers in `benchmark.py` or a new `core/utils.py`:
- `run_preset_comparison(...)`
  - Inputs: df, analysis_type, dimensions, metric/columns, time_col, entity.
  - Outputs: `comparison_df`, `best_preset`, `all_preset_results` (optional for deep debug).
- `build_weighted_totals_df(...)`
  - Produces a DataFrame equivalent to the balanced CSV but in-memory.
  - Reuse in export, distortion, and publication outputs.
- `calculate_share_distortion_df(...)`
  - Computes raw vs balanced share and distortion using raw df + weighted totals.
  - Handles entity and peer-only modes.
- `calculate_rate_weight_effect_df(...)`
  - Computes raw/balanced rates and weight effect using raw df + weighted totals.

## Part 2: Core Module Extensions

### 2.1 core/data_loader.py
Add validation infrastructure:
- `ValidationSeverity` Enum: `ERROR`, `WARNING`, `INFO`.
- `ValidationIssue` dataclass:
  - `severity`, `category`, `message`, `row_indices`, `auto_fix_available`, `fix_description`.
- `VALIDATION_THRESHOLDS` dict (default values from prompt):
  - `min_denominator`, `min_peer_count`, `max_rate_deviation`,
    `min_rows_per_category`, `max_null_percentage`, `max_entity_concentration`.

Validation functions:
- `validate_share_input(df, metric, entity_col, dimensions, time_col, target_entity, thresholds) -> List[ValidationIssue]`
  - Missing columns (ERROR).
  - Nulls in critical columns > threshold (ERROR).
  - Negative values (ERROR).
  - Zero metric rows (WARNING).
  - Target entity missing (ERROR if provided).
  - Peer count below threshold (ERROR).
  - Per-category row counts below threshold (WARNING).
  - Entity concentration > threshold (WARNING).
- `validate_rate_input(df, total_col, approved_col, fraud_col, entity_col, dimensions, time_col, target_entity, thresholds) -> List[ValidationIssue]`
  - All share checks above.
  - Denominator <= 0 (ERROR).
  - Numerator > denominator (ERROR).
  - Rate > 100% (ERROR).
  - Denominator < `min_denominator` (WARNING).

Config integration:
- Allow optional overrides for thresholds via config file (new `input.validation_thresholds`).
- Update validators in `utils/validators.py` to accept new config fields.

### 2.2 core/dimensional_analyzer.py
Add shared analysis helpers (used by both CLI and TUI):
- `calculate_distortion_summary(distortion_df, analysis_type) -> pd.DataFrame`
  - Groups by `Dimension`, `Category`, optional `Time`, and (for rate) `Rate_Type`.
  - Aggregates `mean`, `min`, `max`, `std`, and `mean_abs` as needed.
- `build_weighted_totals_df(df, dimensions, metric/columns, time_col, analyzer)`
  - Create in-memory balanced totals without writing CSV.
  - Reuse existing weighting logic from `export_balanced_csv`.

Enhance metric calculations:
- Add optional flag or context to `_calculate_share_metrics` and `_calculate_rate_metrics` to
  expose raw/balanced totals needed for distortion when `analyze_distortion` is enabled.
- Keep existing outputs unchanged when new flags are off.

### 2.3 core/report_generator.py
Given `benchmark.py` currently owns most Excel generation, use this module as a shared helper layer:
- Add helper functions:
  - `add_preset_comparison_sheet(wb, comparison_df, analysis_type)`
  - `add_distortion_summary_sheet(wb, summary_df, analysis_type)`
  - `add_data_quality_sheet(wb, validation_issues)`
  - `apply_publication_formatting(wb, analysis_type, fraud_in_bps)`
- Add publication report builders:
  - Share publication: simplified market share tables derived from balanced totals.
  - Rate publication: approval/fraud tables with optional BPS conversion.
- Update `benchmark.py` report generation (`generate_excel_report` and
  `generate_multi_rate_excel_report`) to call these helpers after creating base sheets.

## Part 3: TUI Integration (tui_app.py)

### 3.1 New UI Widgets
Add an "Analysis Options" block near the existing "Analysis Options" section:
- Checkboxes:
  - `compare_presets`
  - `analyze_distortion`
  - `validate_input` (default True)
  - `export_balanced_csv` (existing, but add nested `include_calculated`)
  - `include_calculated` (disabled unless export is checked)
  - `fraud_in_bps` (rate-only, default True)
- Select:
  - `output_format` (analysis, publication, both)

### 3.2 Validation Modal
Implement `ValidationModal(ModalScreen)`:
- Shows counts of ERROR/WARNING/INFO.
- Lists issue messages in a `ListView`.
- Buttons:
  - Proceed (only when there are no ERRORs).
  - Cancel.
  - Export Report (optional, to save issues as CSV).

### 3.3 Analysis Execution Flow
Update `run_analysis()`:
- Collect new UI option values and map to args.
- If validation enabled:
  - Run validation in the same worker thread.
  - If issues exist, show modal and wait for user response; proceed only when no ERRORs.
- For compare-presets:
  - Show progress status in the log and optional progress bar widget.

### 3.4 CSS Styling
Add styles for:
- Analysis Options container.
- Indented "Include Calculated Metrics" checkbox.
- Rate-only visibility class.
- Validation modal layout.

## Part 4: Output Format Enhancements

### 4.1 Excel Sheet Additions
Sheet definitions:
- "Preset Comparison"
  - Columns: `Preset`, `Mean_Distortion_pp`, `Mean_Abs_Distortion_pp`, `Min`, `Max`, `Std`, `Selected`.
  - Rate analysis: add `Rate_Type` column.
- "Distortion Details"
  - Share: `Dimension`, `Category`, `Time`, `Raw_Share_pct`, `Balanced_Share_pct`, `Distortion_pp`.
  - Rate: `Rate_Type`, `Dimension`, `Category`, `Time`, `Raw_Rate_pct`, `Balanced_Rate_pct`, `Weight_Effect_pp`.
- "Distortion Summary"
  - Share: `Dimension`, `Category`, `Time`, `Mean`, `Min`, `Max`, `Std`, `Mean_Abs`.
  - Rate: `Rate_Type`, `Dimension`, `Category`, `Time`, `Mean`, `Min`, `Max`, `Std`, `Mean_Abs`.
- "Data Quality"
  - `Severity`, `Category`, `Message`, `Count`, `Sample_Rows`, `Fix_Available`, `Fix_Description`.

Analysis workbook sheet order:
1) Summary
2) Distortion Details
3) Distortion Summary
4) Preset Comparison
5) Dimension sheets
6) Secondary Metrics (if any)
7) Peer Weights (debug)
8) Weight Methods
9) Rank Changes
10) Privacy Validation (debug)

Publication workbook sheet order (separate file):
1) Publication Summary
2) Share Tables or Rate Tables (approval/fraud)

### 4.2 Enhanced CSV Schema
Share analysis (append columns):
- `balanced_share_pct`
- `raw_share_pct`
- `distortion_pp`
Peer-only mode:
- `raw_share_pct` and `balanced_share_pct` blank,
  `distortion_pp` as percent change in total (balanced vs raw).

Rate analysis (append columns):
- `approval_rate_pct` (balanced)
- `fraud_rate_pct` (balanced)
- `raw_approval_rate_pct`
- `raw_fraud_rate_pct`
- `weight_effect_approval_pp`
- `weight_effect_fraud_pp`

### 4.3 Publication Format Specification
Share publication:
- Compute entity market share from raw entity totals and balanced peer totals.
- Produce pivot tables by `Dimension` and `Time` when time column is present.
- Apply formatting patterns from `generate_market_share_report.py`:
  - Title row, subtitle row, shaded header, percent formatting, fixed column widths.

Rate publication:
- Provide simplified tables of approval and/or fraud rates.
- If multi-rate, create separate tables or sheets for approval and fraud.
- Apply optional `fraud_in_bps` conversion (percent * 100) only in publication output.

## Part 5: Testing Strategy

### 5.1 Unit Tests
- `DataLoader.validate_share_input` and `validate_rate_input`.
- `calculate_share_distortion_df` and `calculate_rate_weight_effect_df`.
- `calculate_distortion_summary`.
- `export_balanced_csv` with `include_calculated=True`.

### 5.2 Integration Tests
- CLI runs for share and rate with new flags:
  - `--compare-presets`, `--analyze-distortion`, `--publication-format`, `--include-calculated`.
- Ensure default behavior unchanged with no new flags.
- Validate output sheets and CSV columns.

### 5.3 Regression Tests
- Confirm existing outputs (dimension sheets, weights, privacy validation) still present.
- Validate that global/per-dimension weighting logic is unchanged.
- Confirm no new presets or preset file changes.

## Part 6: Documentation Updates

### 6.1 README.md
- Add "Enhanced Analysis Features" section.
- Add new CLI examples for share and rate.
- Add new flag descriptions in CLI reference tables.

### 6.2 AGENTS.md
- Add new flags and behavior.
- Describe preset comparison, distortion summary, validation pipeline.
- Update output structure to include new sheets and CSV columns.
- Document TUI widgets and modal behavior.

### 6.3 Workflow Documentation Alignment
- Update `SHARE_ANALYSIS_WORKFLOW.md` and `RATE_ANALYSIS_WORKFLOW.md` to reflect
  built-in features and remove references to standalone scripts as primary workflow.

## Part 7: Implementation Phases

### Phase 1: Foundation (Week 1)
- Add validation classes and thresholds.
- Add config fields and validator support.
- Add core helpers for weighted totals and distortion/weight-effect calculation.

### Phase 2: Analysis Features (Week 2)
- Implement preset comparison in CLI.
- Implement distortion summary sheets.
- Add enhanced CSV calculations.

### Phase 3: TUI Integration (Week 3)
- Add new widgets and wiring.
- Implement validation modal and compare-presets progress display.

### Phase 4: Polish (Week 4)
- Publication formatting.
- Documentation updates.
- Regression testing.
