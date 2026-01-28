# Enhanced Analysis Implementation Task

## Overview
Implement the five enhanced analysis features in the Peer Benchmark Tool based on `ENHANCED_ANALYSIS_IMPLEMENTATION_PLAN.md`. Follow AGENTS.md rules strictly: privacy caps, ConfigManager-only parameters, no preset edits, no standalone scripts.

---

## Phase 1: Foundation [Week 1]

### 1.1 Data Validation Infrastructure
- [x] Add `ValidationSeverity` enum to `core/data_loader.py` (ERROR, WARNING, INFO)
- [x] Add `ValidationIssue` dataclass with severity, category, message, row_indices, auto_fix_available, fix_description
- [x] Add `VALIDATION_THRESHOLDS` dict with default values
- [x] Implement `validate_share_input()` in `core/data_loader.py`
- [x] Implement `validate_rate_input()` in `core/data_loader.py`

### 1.2 Config Extensions
- [x] Add new config keys to `utils/config_manager.py` `_get_default_config()`:
  - `input.validate_input` (bool, default True)
  - `input.validation_thresholds` (dict)
  - `output.output_format` (str: analysis|publication|both)
  - `output.include_distortion_summary` (bool)
  - `output.include_preset_comparison` (bool)
  - `output.include_calculated_metrics` (bool)
  - `output.fraud_in_bps` (bool)
- [x] Extend `ConfigManager._apply_cli_overrides()` for new flags

### 1.3 Core Helpers
- [x] Add `build_weighted_totals_df()` to `core/dimensional_analyzer.py` or `benchmark.py`
- [x] Add `calculate_share_distortion_df()` to compute raw vs balanced share
- [x] Add `calculate_rate_weight_effect_df()` to compute raw vs balanced rates
- [x] Add `calculate_distortion_summary()` to `core/dimensional_analyzer.py`

---

## Phase 2: Analysis Features [Week 2]

### 2.1 CLI Flag Additions
- [x] Add flags to **share** subcommand in `benchmark.py`:
  - `--compare-presets` (bool, default False)
  - `--analyze-distortion` (bool, default False)
  - `--validate-input` / `--no-validate-input` (bool, default True)
  - `--output-format` (choice: analysis|publication|both)
  - `--publication-format` (convenience alias)
  - `--include-calculated` (bool, default False)
- [x] Add flags to **rate** subcommand in `benchmark.py`:
  - Same as share plus `--fraud-in-bps` / `--no-fraud-in-bps` (default True)

### 2.2 Preset Comparison Integration
- [x] Add `run_preset_comparison()` helper function in `benchmark.py`
- [x] Integrate into `run_share_analysis()` when `--compare-presets` is set
- [x] Integrate into `run_rate_analysis()` when `--compare-presets` is set
- [x] Mark the best preset (lowest mean absolute distortion) in output

### 2.3 Distortion Analysis Integration
- [x] Compute distortion details in `run_share_analysis()` when `--analyze-distortion`
- [x] Compute weight effect details in `run_rate_analysis()` when `--analyze-distortion`
- [x] Generate summary stats (mean/min/max/std by dimension/category/time)

### 2.4 Data Quality Validation in CLI
- [x] Call validation functions after data load in `run_share_analysis()`
- [x] Call validation functions after data load in `run_rate_analysis()`
- [x] Abort on ERROR issues (no override); log and continue on WARNING
- [x] Validation issues logged and displayed in TUI modal

### 2.5 Enhanced CSV Export
- [x] Extend `export_balanced_csv()` for share: add `balanced_share_pct`, `raw_share_pct`, `distortion_pp`
- [x] Extend `export_balanced_csv()` for rate: add rate columns and weight effect columns

---

## Phase 3: TUI Integration [Week 3]

### 3.1 New TUI Widgets
- [x] Add checkboxes in `tui_app.py`:
  - `compare_presets`
  - `analyze_distortion`
  - `validate_input` (default True)
  - `include_calculated` (nested under export, disabled unless export checked)
  - `fraud_in_bps` (rate-only, default True)
- [x] Add Select widget for `output_format` (analysis, publication, both)

### 3.2 Validation Modal
- [x] Implement `ValidationModal(ModalScreen)` in `tui_app.py`
  - Show counts of ERROR/WARNING/INFO
  - List issue messages in ListView
  - Buttons: Proceed (disabled on ERRORs), Cancel

### 3.3 TUI Analysis Flow Updates
- [x] Update `run_analysis()` to collect new UI option values
- [x] Run validation if enabled before analysis
- [x] Show modal if issues; abort on ERRORs
- [x] Backend integration complete (preset comparison runs automatically)

### 3.4 CSS Styling
- [x] Add styles for analysis options container
- [x] Add styles for indented checkboxes
- [x] Add rate-only visibility class
- [x] Add validation modal layout

---

## Phase 4: Output & Publication [Week 4]

### 4.1 Report Generator Extensions
- [x] Add helper `add_preset_comparison_sheet()` to `core/report_generator.py`
- [x] Add helper `add_distortion_summary_sheet()` 
- [x] Add helper `add_data_quality_sheet()`
- [x] Methods added to ReportGenerator class

### 4.2 Publication Workbook
- [x] Add `generate_publication_workbook()` function to ReportGenerator
- [x] Supports fraud_in_bps conversion for rate analysis
- [x] Professional styling with executive summary sheet
- [x] Auto-adjusting column widths

### 4.3 Documentation Updates
- [x] Update README.md with new features section
- [x] Update AGENTS.md with new flags, behaviors, sheets
- [x] Update workflow docs to reference built-in features

---

## Phase 5: Verification

### 5.1 Unit Tests
- [x] Test `validate_share_input()` - 3 tests passing
- [x] Test `validate_rate_input()` - 2 tests passing
- [x] Test distortion calculations - 1 test passing
- [x] Test CSV export columns - 1 test (conditional on file existence)

### 5.2 Integration Tests
- [x] CLI runs with new flags for share and rate
- [x] Verify default behavior unchanged without new flags
- [x] Verify output sheets and CSV columns

### 5.3 Manual Verification
- [x] Run share analysis with all new flags
- [x] Verified: CSV has Raw_Metric, Distortion_PP columns
- [x] Verified: Excel has Preset Comparison, Distortion Summary sheets
- [x] TUI implementation complete (validation modal, checkboxes, workflow)
