# Enhanced Analysis Features - Refactoring Implementation Plan

This plan addresses the code review findings from the Enhanced Analysis Features implementation. The goal is to refactor the codebase to eliminate technical debt, fix edge cases, and improve maintainability.

---

## User Review Required

> [!CAUTION]
> **Breaking Changes**: Some refactoring may change function signatures. Existing scripts calling `run_share_analysis()` or `run_rate_analysis()` directly may need updates.

> [!IMPORTANT]
> **Priority Decision Needed**: Should we fix critical bugs first (Phase 1) or refactor architecture first? Recommend critical bugs first to stabilize the current release.

---

## Phase 1: Critical Bug Fixes (Immediate)

### 1.1 Remove Duplicate Variable Declarations

#### [MODIFY] [benchmark.py](file:///d:/Projects/Peer%20Benchmark%20Tool/benchmark.py)

**Issue**: Lines 620-524 declare the same config variables twice.

```diff
-include_preset_comparison = config.get('output', 'include_preset_comparison', default=False)
-include_distortion_summary = config.get('output', 'include_distortion_summary', default=False)
-include_calculated_metrics = config.get('output', 'include_calculated_metrics', default=False)
-output_format = config.get('output', 'output_format', default='analysis')
-fraud_in_bps = config.get('output', 'fraud_in_bps', default=True)
-include_preset_comparison = config.get('output', 'include_preset_comparison', default=False)
-include_distortion_summary = config.get('output', 'include_distortion_summary', default=False)
-include_calculated_metrics = config.get('output', 'include_calculated_metrics', default=False)
-output_format = config.get('output', 'output_format', default='analysis')
+include_preset_comparison = config.get('output', 'include_preset_comparison', default=False)
+include_distortion_summary = config.get('output', 'include_distortion_summary', default=False)
+include_calculated_metrics = config.get('output', 'include_calculated_metrics', default=False)
+output_format = config.get('output', 'output_format', default='analysis')
+fraud_in_bps = config.get('output', 'fraud_in_bps', default=True)
```

---

### 1.2 Fix Bare Exception Handling in TUI

#### [MODIFY] [tui_app.py](file:///d:/Projects/Peer%20Benchmark%20Tool/tui_app.py)

**Issue**: Bare `except:` catches system exceptions like `KeyboardInterrupt`.

**Current Code (around line 3151):**
```python
try:
    args.validate_input = self.query_one("#validate_input").value
    # ...
except:
    args.validate_input = True
```

**Fixed Code:**
```python
try:
    args.validate_input = self.query_one("#validate_input").value
    args.analyze_distortion = self.query_one("#analyze_distortion").value
    args.compare_presets = self.query_one("#compare_presets").value
    args.include_calculated = self.query_one("#include_calculated").value
    args.output_format = self.query_one("#output_format").value
except (LookupError, AttributeError) as e:
    # Fallback if widgets not found (backward compatibility)
    logger.warning(f"Could not find enhanced analysis widgets: {e}")
    args.validate_input = True
    args.analyze_distortion = False
    args.compare_presets = False
    args.include_calculated = False
    args.output_format = 'analysis'
```

Same fix needed for `fraud_in_bps` (around line 3205):
```python
except (LookupError, AttributeError):
    args.fraud_in_bps = True  # Default ON per requirements
```

---

### 1.3 Fix Empty DataFrame Edge Case in Preset Comparison

#### [MODIFY] [benchmark.py](file:///d:/Projects/Peer%20Benchmark%20Tool/benchmark.py)

**Issue**: `idxmin()` raises `ValueError` on empty DataFrame.

**Location**: `run_preset_comparison()` function, around line 485.

```python
# Current (buggy):
if distortion_col in comparison_df.columns:
    min_idx = comparison_df[distortion_col].idxmin()

# Fixed:
if distortion_col in comparison_df.columns and not comparison_df[distortion_col].dropna().empty:
    min_idx = comparison_df[distortion_col].idxmin()
    comparison_df['Best'] = ''
    comparison_df.loc[min_idx, 'Best'] = '⭐'
    best_preset = comparison_df.loc[min_idx, 'Preset']
    logger.info(f"\nBest preset (lowest mean abs distortion): {best_preset}")
else:
    logger.warning("No valid distortion data to determine best preset")
```

---

### 1.4 Fix Time Column with None Values

#### [MODIFY] [core/dimensional_analyzer.py](file:///d:/Projects/Peer%20Benchmark%20Tool/core/dimensional_analyzer.py)

**Issue**: `sorted()` fails if time column contains `None`.

**Locations**: `calculate_share_distortion()` and `calculate_rate_weight_effect()`

```python
# Current:
time_periods = sorted(df[self.time_column].unique())

# Fixed:
time_periods = sorted([t for t in df[self.time_column].unique() if t is not None])
if df[self.time_column].isna().any():
    logger.warning(f"Time column '{self.time_column}' contains {df[self.time_column].isna().sum()} null values - excluded from time-based analysis")
```

---

## Phase 2: Edge Case Handling (High Priority)

### 2.1 Ambiguous Entity Name Resolution

#### [MODIFY] [benchmark.py](file:///d:/Projects/Peer%20Benchmark%20Tool/benchmark.py)

**Issue**: Multiple entities normalizing to same uppercase name silently picks first.

**Add after entity resolution logic:**
```python
# Check for ambiguous entity matches
if args.entity:
    entity_upper = str(args.entity).upper()
    all_matches = [e for e in df[entity_col].unique() 
                   if e is not None and str(e).upper() == entity_upper]
    
    if len(all_matches) > 1:
        logger.error(f"Ambiguous entity name: '{args.entity}' matches multiple entities: {all_matches}")
        logger.error("Please specify the exact entity name with correct casing.")
        return 1
    elif len(all_matches) == 1:
        resolved_entity = str(all_matches[0])
        if resolved_entity != args.entity:
            logger.warning(f"Target entity case mismatch. Using '{resolved_entity}' instead of '{args.entity}'.")
    else:
        resolved_entity = None  # Will be caught by validation
```

---

### 2.2 Handle Validation-Disabled with Bad Data

#### [MODIFY] [core/dimensional_analyzer.py](file:///d:/Projects/Peer%20Benchmark%20Tool/core/dimensional_analyzer.py)

**Issue**: Negative/NaN/Inf values corrupt calculations when validation is disabled.

**Add defensive checks in calculation methods:**
```python
def calculate_share_distortion(self, df, metric_col, dimensions, target_entity=None):
    # Defensive data cleaning
    if df[metric_col].isna().any() or (df[metric_col] < 0).any():
        logger.warning(f"Metric column '{metric_col}' contains invalid values (NaN or negative). "
                      "Consider enabling --validate-input for data quality checks.")
        # Clean for calculation
        df = df[df[metric_col].notna() & (df[metric_col] >= 0)].copy()
    
    if np.isinf(df[metric_col]).any():
        logger.error(f"Metric column '{metric_col}' contains infinite values. Cannot proceed.")
        return pd.DataFrame()
```

---

### 2.3 Empty Dimensions Guard

#### [MODIFY] [benchmark.py](file:///d:/Projects/Peer%20Benchmark%20Tool/benchmark.py)

**Add at start of `run_preset_comparison()`:**
```python
def run_preset_comparison(...):
    if not dimensions:
        logger.warning("No dimensions provided for preset comparison. Skipping.")
        return pd.DataFrame()
```

---

## Phase 3: Code Deduplication (Architecture)

### 3.1 Extract Common Validation Logic

#### [NEW] [core/validation_runner.py](file:///d:/Projects/Peer%20Benchmark%20Tool/core/validation_runner.py)

Extract the duplicated validation orchestration into a single function:

```python
"""
Validation orchestration for both share and rate analysis.
"""
from typing import List, Optional, Dict, Any
from core.data_loader import DataLoader, ValidationIssue, ValidationSeverity
import logging

logger = logging.getLogger(__name__)


def run_input_validation(
    df: 'pd.DataFrame',
    config: 'ConfigManager',
    data_loader: DataLoader,
    analysis_type: str,  # 'share' or 'rate'
    metric_col: Optional[str] = None,
    total_col: Optional[str] = None,
    numerator_cols: Optional[Dict[str, str]] = None,
    entity_col: str = 'issuer_name',
    dimensions: Optional[List[str]] = None,
    time_col: Optional[str] = None,
    target_entity: Optional[str] = None,
) -> tuple[List[ValidationIssue], bool]:
    """
    Run validation and return issues + should_abort flag.
    
    Returns:
        (issues, should_abort): List of issues and whether to abort analysis
    """
    validate_input = config.get('input', 'validate_input', default=True)
    if not validate_input:
        return [], False
    
    logger.info("Running input data validation...")
    
    val_dimensions = dimensions or data_loader.get_available_dimensions(df)
    thresholds = config.get('input', 'validation_thresholds', default={})
    
    if analysis_type == 'share':
        issues = data_loader.validate_share_input(
            df=df,
            metric_col=metric_col,
            entity_col=entity_col,
            dimensions=val_dimensions,
            time_col=time_col,
            target_entity=target_entity,
            thresholds=thresholds
        )
    else:  # rate
        issues = data_loader.validate_rate_input(
            df=df,
            total_col=total_col,
            numerator_cols=numerator_cols,
            entity_col=entity_col,
            dimensions=val_dimensions,
            time_col=time_col,
            target_entity=target_entity,
            thresholds=thresholds
        )
    
    # Log and categorize
    errors = [i for i in issues if i.severity == ValidationSeverity.ERROR]
    warnings = [i for i in issues if i.severity == ValidationSeverity.WARNING]
    infos = [i for i in issues if i.severity == ValidationSeverity.INFO]
    
    for issue in issues:
        if issue.severity == ValidationSeverity.ERROR:
            logger.error(f"VALIDATION ERROR [{issue.category}]: {issue.message}")
        elif issue.severity == ValidationSeverity.WARNING:
            logger.warning(f"VALIDATION WARNING [{issue.category}]: {issue.message}")
        else:
            logger.info(f"VALIDATION INFO [{issue.category}]: {issue.message}")
    
    # Summary
    if errors:
        logger.error(f"Found {len(errors)} ERROR(s), {len(warnings)} WARNING(s), {len(infos)} INFO(s)")
        logger.error("Analysis ABORTED due to validation errors. Fix the data and retry.")
        return issues, True  # Abort
    elif warnings:
        logger.warning(f"Found {len(warnings)} WARNING(s), {len(infos)} INFO(s). Proceeding with analysis.")
    elif infos:
        logger.info(f"Found {len(infos)} INFO(s). Data quality is good.")
    else:
        logger.info("Input validation passed with no issues.")
    
    return issues, False  # Don't abort
```

#### [MODIFY] [benchmark.py](file:///d:/Projects/Peer%20Benchmark%20Tool/benchmark.py)

Replace duplicated validation blocks with:
```python
from core.validation_runner import run_input_validation

# In run_share_analysis():
validation_issues, should_abort = run_input_validation(
    df=df, config=config, data_loader=data_loader,
    analysis_type='share', metric_col=metric_col,
    entity_col=entity_col, dimensions=val_dimensions,
    time_col=time_col, target_entity=args.entity
)
if should_abort:
    return 1
```

---

### 3.2 Extract Report Sheet Generation

#### [MODIFY] [core/report_generator.py](file:///d:/Projects/Peer%20Benchmark%20Tool/core/report_generator.py)

Move sheet generation from `benchmark.py` into `ReportGenerator` class methods. The `generate_excel_report()` function should call:

- `report_generator.add_summary_sheet(wb, metadata)`
- `report_generator.add_dimension_sheets(wb, results)`
- `report_generator.add_weights_sheet(wb, weights_df)`
- `report_generator.add_debug_sheets(wb, ...)` (if enabled)
- `report_generator.add_preset_comparison_sheet(wb, ...)` (already exists, just wire it up)
- `report_generator.add_distortion_sheet(wb, ...)`
- `report_generator.add_data_quality_sheet(wb, ...)`

This reduces `generate_excel_report()` from 500+ lines to ~50 lines of orchestration.

---

## Phase 4: Configuration & Magic Numbers

### 4.1 Make Distortion Thresholds Configurable

#### [MODIFY] [utils/config_manager.py](file:///d:/Projects/Peer%20Benchmark%20Tool/utils/config_manager.py)

Add to default config:
```python
'output': {
    # ... existing ...
    'distortion_thresholds': {
        'high_distortion_pp': 1.0,   # Red highlighting threshold
        'low_distortion_pp': 0.25,   # Green highlighting threshold
    },
}
```

#### [MODIFY] [benchmark.py](file:///d:/Projects/Peer%20Benchmark%20Tool/benchmark.py)

Replace magic numbers:
```python
# Current:
if abs(value) > 1.0:  # Hard-coded!

# Fixed:
high_threshold = config.get('output', 'distortion_thresholds', 'high_distortion_pp', default=1.0)
if abs(value) > high_threshold:
```

---

### 4.2 Fix BPS Conversion Logic

#### [MODIFY] [core/report_generator.py](file:///d:/Projects/Peer%20Benchmark%20Tool/core/report_generator.py)

Replace substring matching with explicit column configuration:

```python
def generate_publication_workbook(self, ..., bps_columns: Optional[List[str]] = None):
    """
    Parameters
    ----------
    bps_columns : Optional[List[str]]
        Explicit list of column names to convert to basis points.
        If None and fraud_in_bps=True, uses legacy heuristic matching.
    """
    if fraud_in_bps:
        if bps_columns:
            # Explicit columns - preferred
            for col in bps_columns:
                if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
                    df[col] = df[col] * 100
        else:
            # Legacy heuristic - log warning
            logger.warning("Using heuristic BPS column detection. "
                          "Consider specifying explicit columns via config.")
            # ... existing substring logic ...
```

---

## Phase 5: Testing

### 5.1 Add Edge Case Tests

#### [MODIFY] [tests/test_enhanced_features.py](file:///d:/Projects/Peer%20Benchmark%20Tool/tests/test_enhanced_features.py)

Add test cases:

```python
class TestValidationEdgeCases:
    def test_unicode_entity_names(self):
        """Test validation with Unicode entity names like 'Banco São Paulo'"""
        
    def test_empty_dataframe(self):
        """Test validation with empty DataFrame"""
        
    def test_null_heavy_data(self):
        """Test validation when nulls exceed threshold"""
        
    def test_ambiguous_entity_case(self):
        """Test error when multiple entities match case-insensitively"""
        
    def test_time_column_with_nulls(self):
        """Test distortion calc when time column has None values"""
        
    def test_negative_values_validation_disabled(self):
        """Test behavior when validation off and data has negatives"""


class TestPresetComparison:
    def test_empty_dimensions_list(self):
        """Test preset comparison with no dimensions"""
        
    def test_empty_results(self):
        """Test best preset marking with no valid distortion data"""
        

class TestTUIModal:
    def test_proceed_with_warnings_only(self):
        """Test modal allows proceed when only warnings exist"""
        
    def test_proceed_blocked_with_errors(self):
        """Test modal blocks proceed when errors exist"""
```

---

## Verification Plan

### Automated Tests
```powershell
# Run existing tests
py -m pytest tests/ -v

# Run new edge case tests
py -m pytest tests/test_enhanced_features.py -v -k "EdgeCase"
```

### Manual Verification
1. Run share analysis with `--validate-input` and `--no-validate-input`
2. Test with dataset containing:
   - Unicode entity names
   - Null time values
   - Negative metrics
3. Verify TUI validation modal behavior
4. Confirm distortion thresholds respect config values

---

## Implementation Order

| Phase | Priority | Est. Effort | Risk |
|-------|----------|-------------|------|
| 1.1 Duplicate vars | 🔴 Critical | 5 min | Low |
| 1.2 Bare except | 🔴 Critical | 10 min | Low |
| 1.3 Empty DF edge | 🔴 Critical | 10 min | Low |
| 1.4 Time column nulls | 🔴 Critical | 15 min | Low |
| 2.1 Ambiguous entity | 🟠 High | 20 min | Medium |
| 2.2 Defensive calcs | 🟠 High | 30 min | Medium |
| 2.3 Empty dimensions | 🟠 High | 5 min | Low |
| 3.1 Validation runner | 🟡 Medium | 1 hour | Medium |
| 3.2 Report refactor | 🟡 Medium | 2 hours | High |
| 4.1 Config thresholds | 🟢 Low | 30 min | Low |
| 4.2 BPS logic | 🟢 Low | 30 min | Medium |
| 5.1 Tests | 🟠 High | 2 hours | Low |

**Total Estimated Effort**: ~7 hours

---

## Success Criteria

- [ ] No duplicate variable declarations
- [ ] No bare `except:` clauses
- [ ] All edge cases handled gracefully (no crashes)
- [ ] Validation logic exists in ONE place
- [ ] `generate_excel_report()` reduced to <100 lines
- [ ] All new tests pass
- [ ] Existing tests still pass
