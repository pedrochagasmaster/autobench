# Implementation Agent Prompt: Rate Analysis Integration

## Objective

Develop a detailed implementation plan for integrating enhanced analysis capabilities into the Peer Benchmark Tool for BOTH share and rate workflows. These capabilities should be:
- Built INTO the tool itself (not standalone scripts)
- Accessible via `benchmark.py` CLI and `tui_app.py` TUI
- Shared between share and rate analysis where applicable

## Critical Architectural Principle

**DO NOT create standalone scripts**. The existing share analysis workflow uses standalone scripts (`test_all_presets.py`, `calculate_nubank_share.py`, etc.) because they were developed AFTER the tool was complete.

**YOU are designing these features properly**, so integrate them into:
- `benchmark.py` - via new flags and subcommands
- `tui_app.py` - via new UI controls and tabs
- `core/` modules - via enhanced functions
- Output formats - via new Excel sheets and CSV columns

## The 5 Capabilities to Integrate

### 1. Preset Comparison (Share AND Rate)

**Current situation**: Users must manually run benchmark.py multiple times with different presets

**CLI Enhancement**:
```bash
# For share analysis
py benchmark.py share --csv data.csv --compare-presets --metric volume_brl

# For rate analysis  
py benchmark.py rate --csv data.csv --compare-presets --total-col txn_cnt --approved-col appr_cnt
```

**TUI Enhancement**:
- Add checkbox: `☐ Compare All Presets` (in Analysis Options section)
- When checked, run analysis with all presets and show comparison
- Add new tab to results view: "Preset Comparison"
- Table showing: Preset | Mean Distortion | Min | Max | Selected (✓)

**Implementation Targets**:
- `benchmark.py`: Add `--compare-presets` flag to BOTH share and rate commands
- `core/dimensional_analyzer.py`: Track distortion/weight effect by preset
- `core/report_generator.py`: Add `add_preset_comparison_sheet()` function
- `tui_app.py`: Add checkbox widget + results visualization
- Output: "Preset Comparison" sheet in Excel

**Reference**: `test_all_presets.py` logic, but generalized for both workflows

---

### 2. Distortion/Weight Effect Analysis (Share AND Rate)

**Current situation**: Debug mode shows distortion but doesn't analyze it

**CLI Enhancement**:
```bash
# Share: analyze market share distortion
py benchmark.py share --csv data.csv --analyze-distortion

# Rate: analyze weight effect  
py benchmark.py rate --csv data.csv --analyze-distortion
```

**TUI Enhancement**:
- Add checkbox: `☐ Include Distortion Analysis` (in Analysis Options)
- When checked, include summary statistics in output
- Show distortion metrics in Summary panel after analysis completes

**Implementation Targets**:
- `benchmark.py`: Add `--analyze-distortion` flag to BOTH commands
- `core/dimensional_analyzer.py`: Add shared function `calculate_distortion_summary()`
- `core/report_generator.py`: Add `add_distortion_summary_sheet()` (works for both)
- `tui_app.py`: Add checkbox + summary display
- Output: "Distortion Summary" sheet with pivot tables (mean, min, max by category)

**Reference**: `analyze_distortion.py` logic, refactored as shared utility

---

### 3. Data Quality Validation (Share AND Rate)

**Current situation**: No automatic validation of input data quality

**CLI Enhancement**:
```bash
# Validation happens automatically, controlled by flag
py benchmark.py share --csv data.csv --validate-input
py benchmark.py rate --csv data.csv --validate-input
```

**TUI Enhancement**:
- Add checkbox: `☑ Validate Input Quality` (default ON)
- Run validation before analysis
- If issues found, show modal dialog with warnings
- Option to: Continue Anyway | Cancel | Fix Data

**Implementation Targets**:
- `core/data_loader.py`: Add `validate_share_input()` and `validate_rate_input()`
- Both share common checks: nulls, negative values, entity consistency
- Rate-specific: denominators > 0, numerators ≤ denominators
- Share-specific: no zeros in metrics, reasonable value ranges
- `tui_app.py`: Add validation step before running analysis
- Output: "Data Quality" sheet if issues found (optional)

**Reference**: Validation code from `RATE_ANALYSIS_WORKFLOW.md` Section 5

---

### 4. Publication-Ready Reports (Share AND Rate)

**Current situation**: Output is analysis-focused, not stakeholder-ready

**CLI Enhancement**:
```bash
# Share: simplified market share tables
py benchmark.py share --csv data.csv --publication-format

# Rate: simplified rate tables with optional BPS
py benchmark.py rate --csv data.csv --publication-format --fraud-in-bps
```

**TUI Enhancement**:
- Add dropdown: `Output Format: [Analysis ▼]` with options:
  - Analysis (default)
  - Publication
  - Both
- When Publication selected, generate stakeholder-ready formatting
- For rate analysis, add checkbox: `☑ Fraud in Basis Points` (DEFAULT ON)

**Implementation Targets**:
- `core/report_generator.py`: Add `publication_mode` parameter to report functions
- Publication mode: simpler sheets, no debug columns, professional styling
- `tui_app.py`: Add format dropdown + BPS checkbox (rate mode only)
- Output: `[entity]_[share|rate]_report_publication_*.xlsx`

**Reference**: `generate_market_share_report.py` Excel formatting patterns

---

### 5. Enhanced CSV Export (Share AND Rate)

**Current situation**: Balanced CSV has raw totals, no calculated metrics

**CLI Enhancement**:
```bash
# Share: add share percentages to CSV
py benchmark.py share --csv data.csv --export-balanced-csv --include-calculated

# Rate: add rates and weight effect to CSV
py benchmark.py rate --csv data.csv --export-balanced-csv --include-calculated
```

**TUI Enhancement**:
- Modify existing checkbox: `☐ Export Balanced CSV`
- Add sub-checkbox: `☐ Include Calculated Metrics` (indent, only if export enabled)
- When both checked, CSV includes calculated fields

**Implementation Targets**:
- `benchmark.py`: Add `--include-calculated` flag
- Extend CSV export to add columns:
  - Share: `balanced_share_%`, `raw_share_%`, `distortion_pp`
  - Rate: `approval_rate_%`, `fraud_rate_%`, `weight_effect_approval_pp`, `weight_effect_fraud_pp`
- Backwards compatible (new columns appended)
- `tui_app.py`: Add nested checkbox

**Reference**: Current balanced CSV export + calculation formulas from core modules

---

## File Modifications Required

### Core Implementation Files

#### 1. `benchmark.py` (~2400 lines)

**Sections to modify**:
- `create_parser()`: Add new flags to share and rate subparsers
- `handle_share_analysis()`: Add preset comparison, distortion analysis, validation
- `handle_rate_analysis()`: Add preset comparison, weight effect analysis, validation
- Add helper function: `run_preset_comparison(args, analysis_type)`

**New flags**:
- `--compare-presets`: Run with all presets, generate comparison
- `--analyze-distortion`: Calculate and include distortion summary
- `--validate-input`: Run data quality checks (default True)
- `--publication-format`: Generate stakeholder-ready output
- `--fraud-in-bps`: Convert fraud rates to basis points (rate only, DEFAULT TRUE)
- `--include-calculated`: Add calculated metrics to balanced CSV

**Pattern**: Study how existing flags are handled, ensure share and rate have parallel implementations

---

#### 2. `core/dimensional_analyzer.py` (~2000 lines)

**Functions to add**:
- `calculate_distortion_summary(results_by_preset)`: Shared by share and rate
  - Input: Dictionary of {preset_name: results_df}
  - Output: Summary DataFrame with mean/min/max distortion by category
  
- Enhanced returns from `_calculate_share_metrics()` and `_calculate_rate_metrics()`:
  - Add distortion tracking by category to returned dictionaries
  - Enable preset comparison at analyzer level

**Sections to modify**:
- Lines ~800-900 in `_calculate_rate_metrics()`: Add weight effect tracking
- Lines ~1100-1200 in `_calculate_share_metrics()`: Add distortion tracking
- Return enhanced metric dictionaries for both

---

#### 3. `core/report_generator.py` (~350 lines)

**Functions to add**:
- `add_preset_comparison_sheet(workbook, comparison_df, analysis_type)`: Shared
- `add_distortion_summary_sheet(workbook, summary_df, analysis_type)`: Shared
- `add_data_quality_sheet(workbook, validation_issues)`: Shared
- `apply_publication_formatting(workbook, analysis_type)`: Shared

**Functions to modify**:
- `generate_share_excel_report()`: Add calls to new sheet functions
- `generate_rate_excel_report()`: Add calls to new sheet functions
- Both should accept `publication_mode` parameter

**Pattern**: Sheet generation functions should be reusable across share and rate

---

#### 4. `core/data_loader.py` (~400 lines)

**Functions to add**:
- `validate_share_input(df, metric, entity_col, dimensions)`:
  - Check for nulls, negatives, entity name consistency
  - Verify metric columns exist
  - Return list of ValidationIssue objects
  
- `validate_rate_input(df, total_col, approved_col, fraud_col, entity_col, dimensions)`:
  - All checks from validate_share_input
  - Plus: zero denominators, numerator > denominator, rates > 100%
  - Return list of ValidationIssue objects

- Helper class: `ValidationIssue(severity, category, message, row_indices, auto_fix_available=False)`

**Validation Severity Levels and Thresholds**:
```python
from enum import Enum

class ValidationSeverity(Enum):
    ERROR = "error"       # Block analysis execution
    WARNING = "warning"   # Show warning but allow continuation
    INFO = "info"         # Informational message, log only

class ValidationIssue:
    severity: ValidationSeverity
    category: str              # e.g., "zero_denominator", "rate_exceeds_100"
    message: str               # Human-readable description
    row_indices: List[int]     # Affected row numbers
    auto_fix_available: bool   # Can be auto-fixed
    fix_description: str       # How to fix (if auto-fixable)

# Validation thresholds configuration
VALIDATION_THRESHOLDS = {
    'min_denominator': 10,           # Flag if total < 10 (unstable rates)
    'min_peer_count': 3,              # Error if fewer than 3 peers
    'max_rate_deviation': 500,        # Warn if rate > 500% (likely error)
    'min_rows_per_category': 5,       # Warn if category has < 5 data points
    'max_null_percentage': 0.05,      # Error if > 5% nulls in critical columns
    'max_entity_concentration': 0.70,  # Warn if one entity > 70% of volume
}
```

**Pattern**: Shared validation logic extracted to common helper functions

---

#### 5. `tui_app.py` (~1166 lines)

**Major changes needed**:

**Add new UI widgets** (in `BenchmarkApp.compose()`):
```python
# Analysis Options Section (new container)
with Vertical(id="analysis-options"):
    yield Label("Analysis Options", classes="section-header")
    yield Checkbox("Compare All Presets", id="compare-presets")
    yield Checkbox("Include Distortion Analysis", id="analyze-distortion")
    yield Checkbox("Validate Input Quality", id="validate-input", value=True)
    
    with Horizontal(id="output-format-row"):
        yield Label("Output Format:")
        yield Select([
            ("Analysis (Technical)", "analysis"),
            ("Publication (Stakeholder)", "publication"),
            ("Both", "both")
        ], id="output-format")
    
    with Horizontal(id="export-options-row"):
        yield Checkbox("Export Balanced CSV", id="export-balanced-csv")
        yield Checkbox("  └ Include Calculated Metrics", id="include-calculated")
    
    # Rate-specific (show/hide based on active tab)
    yield Checkbox("Fraud in Basis Points", id="fraud-in-bps", value=True, classes="rate-only")
```

**Modify `run_analysis()` method**:
- Collect flag values from checkboxes
- Build command with new flags
- Run validation before analysis if checkbox checked
- Show validation modal if issues found

**Add validation modal with detailed interaction**:
```python
class ValidationModal(Screen):
    """Modal showing data quality issues with severity indicators."""
    
    def __init__(self, issues: List[ValidationIssue]):
        super().__init__()
        self.issues = issues
        self.errors = [i for i in issues if i.severity == ValidationSeverity.ERROR]
        self.warnings = [i for i in issues if i.severity == ValidationSeverity.WARNING]
        self.infos = [i for i in issues if i.severity == ValidationSeverity.INFO]
    
    def compose(self):
        yield Container(
            Label("Data Quality Issues Found", classes="modal-title"),
            Label(f"❌ {len(self.errors)} Errors (will block analysis)", 
                  classes="error-summary" if self.errors else "hidden"),
            Label(f"⚠️  {len(self.warnings)} Warnings (can proceed with caution)",
                  classes="warning-summary" if self.warnings else "hidden"),
            Label(f"ℹ️  {len(self.infos)} Info messages",
                  classes="info-summary" if self.infos else "hidden"),
            ListView(id="issues-list"),  # Populated with issue details
            Horizontal(
                Button("Export Report", id="export"),
                Button("Continue Anyway", id="continue", 
                       variant="warning",
                       disabled=len(self.errors) > 0),  # Disabled if errors present
                Button("Cancel", id="cancel", variant="primary")
            )
        )
    
    def on_mount(self):
        """Populate issue list with detailed information."""
        list_view = self.query_one("#issues-list", ListView)
        for issue in self.issues:
            icon = {ValidationSeverity.ERROR: "❌", 
                    ValidationSeverity.WARNING: "⚠️", 
                    ValidationSeverity.INFO: "ℹ️"}[issue.severity]
            list_view.append(ListItem(Label(f"{icon} {issue.message}")))
```

**Pattern**: Study existing checkbox handling, add new widgets following same patterns

---

### Documentation Files

#### 6. `README.md` (484 lines)

**Sections to add**:

**Enhanced Analysis Features** (new section after "Analysis Types"):
```markdown
## Enhanced Analysis Features

### Preset Comparison
Compare multiple preset configurations in one run:
```bash
py benchmark.py share --csv data.csv --compare-presets --metric volume_brl
```
Output includes "Preset Comparison" sheet with distortion metrics.

### Distortion Analysis  
Automatic distortion summary statistics:
```bash
py benchmark.py share --csv data.csv --analyze-distortion
```
Adds "Distortion Summary" sheet with mean/min/max by category.

### Data Quality Validation
Automatic input validation (enabled by default):
```bash
py benchmark.py rate --csv data.csv --validate-input
```
Shows warnings for data quality issues before analysis runs.

### Publication Format
Stakeholder-ready reports with simplified formatting:
```bash
py benchmark.py share --csv data.csv --publication-format
```
```

**Update CLI Reference section** (lines 242-266):
- Add all new flags to parameter table
- Add examples using new flags

---

#### 7. `AGENTS.md` (633 lines)

**Sections to add**:

**Enhanced Workflow Features** (after "Configuration System"):
- Document new flags and their behavior
- Explain preset comparison internals
- Describe validation pipeline

**TUI Enhancements** (in "TUI Development Patterns"):
- New checkbox widgets and their bindings
- Validation modal implementation
- Dynamic UI elements (fraud-in-bps visibility)

**Update Output Structure section**:
- Document new Excel sheets
- Update balanced CSV schema

---

## Integration Architecture

```
User Interface Layer
├── benchmark.py CLI
│   ├── share subcommand
│   │   ├── --compare-presets
│   │   ├── --analyze-distortion  
│   │   ├── --validate-input
│   │   ├── --publication-format
│   │   └── --include-calculated
│   └── rate subcommand  
│       ├── --compare-presets
│       ├── --analyze-distortion
│       ├── --validate-input
│       ├── --publication-format
│       ├── --fraud-in-bps
│       └── --include-calculated
│
└── tui_app.py TUI
    ├── Analysis Options Panel
    │   ├── Compare Presets checkbox
    │   ├── Analyze Distortion checkbox
    │   ├── Validate Input checkbox
    │   ├── Output Format dropdown
    │   └── Export options checkboxes
    └── Validation Modal (conditional)

Core Logic Layer
├── core/data_loader.py
│   ├── validate_share_input()
│   ├── validate_rate_input()
│   └── ValidationIssue class
│
├── core/dimensional_analyzer.py
│   ├── calculate_distortion_summary() [SHARED]
│   ├── Enhanced _calculate_share_metrics()
│   └── Enhanced _calculate_rate_metrics()
│
└── core/report_generator.py
    ├── add_preset_comparison_sheet() [SHARED]
    ├── add_distortion_summary_sheet() [SHARED]
    ├── add_data_quality_sheet() [SHARED]
    └── apply_publication_formatting() [SHARED]

Output Layer
├── Excel Reports
│   ├── Standard sheets
│   ├── [NEW] Preset Comparison
│   ├── [NEW] Distortion Summary
│   └── [NEW] Data Quality
└── Enhanced CSV
    └── [NEW] Calculated metric columns
```

---

## Key Design Principles

### 1. Share and Rate Parity
Every enhancement should work for BOTH share and rate analysis:
- Same flag names where applicable
- Same TUI controls (with conditional visibility)
- Shared core functions where possible

### 2. Backwards Compatibility
- Default behavior unchanged
- New features opt-in via flags
- Existing commands continue to work

### 3. Code Reuse
Don't duplicate logic:
- Distortion summary: one function for both share and rate
- Report sheets: parameterized by analysis type
- Validation: shared base + specific extensions

### 4. Single Entrypoint
- Everything via `benchmark.py` or `tui_app.py`
- No new top-level scripts
- TUI and CLI have feature parity

### 5. Consolidated Output
- All enhancements in ONE Excel file per run
- Enhanced CSV is an extension, not separate file
- No scattered outputs

---

## Implementation Plan Structure

Your deliverable should be organized as:

```markdown
# Enhanced Analysis Implementation Plan

## Executive Summary
- Overview of 5 capabilities
- Shared vs specific features
- Integration approach

## Part 1: CLI Integration (benchmark.py)

### 1.1 New Flag Definitions
- Flag names, types, defaults
- Validation rules
- Interaction between flags

### 1.2 Share Command Enhancements
- Modifications to handle_share_analysis()
- Preset comparison logic
- Distortion analysis integration

### 1.3 Rate Command Enhancements  
- Modifications to handle_rate_analysis()
- Weight effect analysis integration
- BPS conversion logic

### 1.4 Shared Helper Functions
- run_preset_comparison()
- build_enhanced_csv()
- Other utilities

## Part 2: Core Module Extensions

### 2.1 data_loader.py
- ValidationIssue class specification
- validate_share_input() implementation
- validate_rate_input() implementation
- Shared validation utilities

### 2.2 dimensional_analyzer.py
- calculate_distortion_summary() specification
- Enhancements to share metrics calculation
- Enhancements to rate metrics calculation
- Return value schema changes

### 2.3 report_generator.py
- add_preset_comparison_sheet() specification
- add_distortion_summary_sheet() specification
- add_data_quality_sheet() specification
- apply_publication_formatting() specification
- Modifications to existing report functions

## Part 3: TUI Integration (tui_app.py)

### 3.1 New UI Widgets
- Analysis Options panel layout
- Checkbox widgets and IDs
- Output format dropdown
- Conditional visibility logic (fraud-in-bps)

### 3.2 Validation Modal
- Screen class specification
- Issue display logic
- User action handling

### 3.3 Analysis Execution Flow
- Collect flag values from UI
- Run validation step
- Command construction
- Result display

### 3.4 CSS Styling
- New widget styles
- Nested checkbox indentation
- Modal dialog styling

## Part 4: Output Format Enhancements

### 4.1 Excel Sheet Additions
- Preset Comparison schema
- Distortion Summary schema
- Data Quality schema
- Sheet ordering

### 4.2 Enhanced CSV Schema
- New columns for share analysis
- New columns for rate analysis
- Backwards compatibility

### 4.3 Publication Format Specification
- Simplified sheet structure
- Formatting rules
- Title and subtitle patterns

## Part 5: Testing Strategy

### 5.1 Unit Tests
- Validation functions
- Distortion summary calculation
- Sheet generation functions

### 5.2 Integration Tests
- CLI flag combinations
- TUI workflow scenarios
- Share and rate parity

### 5.3 Regression Tests
- Existing workflows unchanged
- Default behavior preserved
- Output compatibility

## Part 6: Documentation Updates

### 6.1 README.md
- Enhanced features section
- Updated examples
- New flag documentation

### 6.2 AGENTS.md
- Workflow patterns
- TUI development guide
- Output structure updates

### 6.3 Workflow Documentation Alignment
- SHARE_ANALYSIS_WORKFLOW.md updates
- RATE_ANALYSIS_WORKFLOW.md updates
- Cross-references

## Part 7: Implementation Phases

### Phase 1: Foundation (Week 1)
- Validation infrastructure
- Core module enhancements
- Basic CLI flags

### Phase 2: Analysis Features (Week 2)
- Preset comparison
- Distortion analysis
- Enhanced CSV

### Phase 3: TUI Integration (Week 3)
- UI widgets
- Validation modal
- End-to-end TUI flow

### Phase 4: Polish (Week 4)
- Publication formatting
- Documentation
- Testing and validation
```

---

## Critical Implementation Notes

### TUI-Specific Considerations

1. **Dynamic Widget Visibility**:
   - `fraud-in-bps` checkbox only visible when Rate tab active
   - `include-calculated` checkbox only enabled when `export-balanced-csv` checked
   - Use Textual reactive properties for this

2. **Validation Modal Flow**:
   ```python
   async def on_button_pressed(self, event):
       if event.button.id == "validate-input":
           issues = validate_input_data()
           if issues:
               await self.push_screen(ValidationModal(issues))
           else:
               self.run_analysis()
   ```

3. **Progress Indication**:
   - When `--compare-presets` enabled, show progress bar
   - Update for each preset: "Running balanced_default... (2/5)"

4. **Result Visualization**:
   - After analysis, show summary in TUI
   - Include distortion metrics if `--analyze-distortion` was checked

### Shared Code Patterns

Extract common logic into utilities:

```python
# In core/utils.py (create if doesn't exist)

def calculate_distortion(entity_value, raw_peer_total, balanced_peer_total, analysis_type):
    """Calculate distortion for share or weight effect for rate."""
    if analysis_type == "share":
        raw = entity_value / (entity_value + raw_peer_total) * 100
        balanced = entity_value / (entity_value + balanced_peer_total) * 100
        return balanced - raw
    elif analysis_type == "rate":
        # Weight effect calculation (different formula)
        raw_rate = raw_peer_total['numerator'] / raw_peer_total['denominator'] * 100
        balanced_rate = balanced_peer_total['numerator'] / balanced_peer_total['denominator'] * 100
        return balanced_rate - raw_rate
```

---

## Success Criteria

1. ✅ All 5 capabilities work for BOTH share and rate
2. ✅ TUI has feature parity with CLI
3. ✅ Existing workflows unchanged (backwards compatible)
4. ✅ Shared code maximized (no duplication)
5. ✅ Single entrypoint (no standalone scripts)
6. ✅ Consolidated output (one Excel, enhanced CSV)
7. ✅ Documentation updated (README, AGENTS, workflows)
8. ✅ TUI validation modal works smoothly
9. ✅ Preset comparison completes in reasonable time
10. ✅ Publication format meets stakeholder needs

---

## Getting Started

1. **Understand current TUI structure**: Read `tui_app.py` completely
2. **Map existing flag handling**: Trace how `--debug` and `--export-balanced-csv` work in both CLI and TUI
3. **Design shared utilities**: Identify common logic between share and rate
4. **Spec out TUI widgets**: Define exact widget hierarchy and IDs
5. **Plan validation flow**: Design ValidationModal interaction pattern
6. **Create implementation plan**: Follow structure above with complete specifications

**Remember**: You're designing a cohesive tool enhancement, not bolting on features. Every change should feel native to the tool.
