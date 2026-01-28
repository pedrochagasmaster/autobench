# Agent Implementation Prompt: Enhanced Analysis Features Refactoring

You are a senior software engineer tasked with refactoring the Enhanced Analysis Features in the Peer Benchmark Tool. This document contains everything you need to complete this task with 100% certainty.

---

## Project Context

### What This Project Does
The **Peer Benchmark Tool** is a Python CLI/TUI application that performs privacy-compliant peer benchmarking analysis. It compares a target entity (e.g., a bank) against peer entities across multiple dimensions, applying privacy-preserving weights to prevent identification of individual peers.

### Key Files You Will Modify

| File | Purpose | Lines (approx) |
|------|---------|----------------|
| `benchmark.py` | Main CLI entry point, analysis orchestration | ~3000 |
| `tui_app.py` | Textual TUI application | ~1400 |
| `core/data_loader.py` | Data loading and validation | ~750 |
| `core/dimensional_analyzer.py` | Core analysis engine | ~2200 |
| `core/report_generator.py` | Excel/publication report generation | ~650 |
| `utils/config_manager.py` | Configuration management | ~550 |
| `tests/test_enhanced_features.py` | Tests for new features | ~200 |

### Technology Stack
- Python 3.10+
- pandas, numpy
- openpyxl (Excel generation)
- textual (TUI framework)
- argparse (CLI)
- pytest (testing)

---

## Current State (What Was Just Implemented)

A large feature PR added "Enhanced Analysis Features" including:
1. **Input Validation** - Data quality checks before analysis
2. **Distortion Analysis** - Measuring impact of privacy weighting
3. **Preset Comparison** - Testing all optimization presets
4. **Publication Format** - Stakeholder-friendly Excel output
5. **TUI Integration** - Validation modal, new checkboxes

**Problem**: The implementation has critical bugs, duplicate code, missing edge case handling, and no tests.

---

## Your Tasks (In Order)

### TASK 1: Fix Duplicate Variable Declarations

**File**: `benchmark.py`  
**Location**: Inside `run_share_analysis()` function, around lines 616-625

**What's Wrong**: The same 5 config variables are declared TWICE in a row.

**Find This Code**:
```python
include_preset_comparison = config.get('output', 'include_preset_comparison', default=False)
include_distortion_summary = config.get('output', 'include_distortion_summary', default=False)
include_calculated_metrics = config.get('output', 'include_calculated_metrics', default=False)
output_format = config.get('output', 'output_format', default='analysis')
fraud_in_bps = config.get('output', 'fraud_in_bps', default=True)
include_preset_comparison = config.get('output', 'include_preset_comparison', default=False)
include_distortion_summary = config.get('output', 'include_distortion_summary', default=False)
include_calculated_metrics = config.get('output', 'include_calculated_metrics', default=False)
output_format = config.get('output', 'output_format', default='analysis')
```

**Fix**: Delete the duplicate lines 6-9. Keep only the first 5 declarations.

**Verification**: Search for `include_preset_comparison = config.get` - should appear only ONCE in `run_share_analysis()`.

---

### TASK 2: Fix Bare Exception Handling in TUI

**File**: `tui_app.py`  
**Location**: Inside `run_analysis()` method, around lines 3146-3152

**What's Wrong**: Bare `except:` catches system exceptions like `KeyboardInterrupt`, `SystemExit`.

**Find This Code**:
```python
try:
    args.validate_input = self.query_one("#validate_input").value
    args.analyze_distortion = self.query_one("#analyze_distortion").value
    args.compare_presets = self.query_one("#compare_presets").value
    args.include_calculated = self.query_one("#include_calculated").value
    args.output_format = self.query_one("#output_format").value
except:
    args.validate_input = True
```

**Replace With**:
```python
try:
    args.validate_input = self.query_one("#validate_input").value
    args.analyze_distortion = self.query_one("#analyze_distortion").value
    args.compare_presets = self.query_one("#compare_presets").value
    args.include_calculated = self.query_one("#include_calculated").value
    args.output_format = self.query_one("#output_format").value
except (LookupError, AttributeError):
    # Fallback if widgets not found (backward compatibility)
    args.validate_input = True
    args.analyze_distortion = False
    args.compare_presets = False
    args.include_calculated = False
    args.output_format = 'analysis'
```

**Also Find** (around line 3203-3206):
```python
try:
    args.fraud_in_bps = self.query_one("#fraud_in_bps").value
except:
    args.fraud_in_bps = False
```

**Replace With**:
```python
try:
    args.fraud_in_bps = self.query_one("#fraud_in_bps").value
except (LookupError, AttributeError):
    args.fraud_in_bps = True  # Default ON per requirements
```

---

### TASK 3: Fix Empty DataFrame Edge Case in Preset Comparison

**File**: `benchmark.py`  
**Location**: Inside `run_preset_comparison()` function, around lines 481-492

**What's Wrong**: `idxmin()` raises `ValueError` on empty DataFrame.

**Find This Code**:
```python
# Mark best preset (lowest mean absolute distortion/effect)
if not comparison_df.empty:
    distortion_col = 'Mean_Abs_Distortion_PP' if 'Mean_Abs_Distortion_PP' in comparison_df.columns else 'Mean_Abs_Effect_PP'
    if distortion_col in comparison_df.columns:
        min_idx = comparison_df[distortion_col].idxmin()
        comparison_df['Best'] = ''
        comparison_df.loc[min_idx, 'Best'] = '⭐'
        best_preset = comparison_df.loc[min_idx, 'Preset']
        logger.info(f"\nBest preset (lowest mean abs distortion): {best_preset}")
```

**Replace With**:
```python
# Mark best preset (lowest mean absolute distortion/effect)
if not comparison_df.empty:
    distortion_col = 'Mean_Abs_Distortion_PP' if 'Mean_Abs_Distortion_PP' in comparison_df.columns else 'Mean_Abs_Effect_PP'
    if distortion_col in comparison_df.columns:
        valid_values = comparison_df[distortion_col].dropna()
        if not valid_values.empty:
            min_idx = comparison_df[distortion_col].idxmin()
            comparison_df['Best'] = ''
            comparison_df.loc[min_idx, 'Best'] = '⭐'
            best_preset = comparison_df.loc[min_idx, 'Preset']
            logger.info(f"\nBest preset (lowest mean abs distortion): {best_preset}")
        else:
            logger.warning("No valid distortion data to determine best preset")
```

---

### TASK 4: Fix Time Column with None Values

**File**: `core/dimensional_analyzer.py`  
**Location**: Inside `calculate_share_distortion()` method, around line 2132

**What's Wrong**: `sorted()` fails if time column contains `None` values.

**Find This Code**:
```python
if self.time_column and self.time_column in df.columns:
    time_periods = sorted(df[self.time_column].unique())
```

**Replace With**:
```python
if self.time_column and self.time_column in df.columns:
    # Filter out None values to avoid TypeError in sorted()
    time_periods = sorted([t for t in df[self.time_column].unique() if t is not None])
    null_count = df[self.time_column].isna().sum()
    if null_count > 0:
        logger.warning(f"Time column '{self.time_column}' contains {null_count} null values - excluded from time-based analysis")
```

**Also Fix Same Pattern In**: `calculate_rate_weight_effect()` method, around line 2254.

---

### TASK 5: Add Empty Dimensions Guard

**File**: `benchmark.py`  
**Location**: At the very start of `run_preset_comparison()` function body

**Add This Code** (after the docstring):
```python
def run_preset_comparison(
    df: pd.DataFrame,
    metric_col: str,
    # ... other params
) -> pd.DataFrame:
    """..."""  # existing docstring
    
    # Guard against empty dimensions
    if not dimensions:
        logger.warning("No dimensions provided for preset comparison. Skipping.")
        return pd.DataFrame()
    
    # ... rest of existing code
```

---

### TASK 6: Add Ambiguous Entity Name Detection

**File**: `benchmark.py`  
**Location**: In both `run_share_analysis()` and `run_rate_analysis()`, after loading data but before the existing entity resolution logic.

**Find This Code** (appears twice, in both functions):
```python
resolved_entity = args.entity
if args.entity:
    entity_upper = str(args.entity).upper()
    match = next((e for e in df[entity_col].unique() if e is not None and str(e).upper() == entity_upper), None)
    if match and match != args.entity:
        logger.warning(f"Target entity case mismatch. Using '{match}' instead of '{args.entity}'.")
        resolved_entity = str(match)
```

**Replace With**:
```python
resolved_entity = args.entity
if args.entity:
    entity_upper = str(args.entity).upper()
    all_matches = [e for e in df[entity_col].unique() 
                   if e is not None and str(e).upper() == entity_upper]
    
    if len(all_matches) > 1:
        logger.error(f"Ambiguous entity name: '{args.entity}' matches multiple entities: {all_matches}")
        logger.error("Please specify the exact entity name with correct casing.")
        return 1
    elif len(all_matches) == 1:
        match = all_matches[0]
        if match != args.entity:
            logger.warning(f"Target entity case mismatch. Using '{match}' instead of '{args.entity}'.")
        resolved_entity = str(match)
    # If no matches, resolved_entity stays as args.entity (will fail validation later)
```

---

### TASK 7: Create Validation Runner Module (Code Deduplication)

**File**: `core/validation_runner.py` (NEW FILE)

**Create This File**:
```python
"""
Validation orchestration for both share and rate analysis.
Extracted to eliminate code duplication between run_share_analysis() and run_rate_analysis().
"""
import logging
from typing import List, Optional, Dict, Any, Tuple

import pandas as pd

from core.data_loader import DataLoader, ValidationIssue, ValidationSeverity

logger = logging.getLogger(__name__)


def run_input_validation(
    df: pd.DataFrame,
    config: 'ConfigManager',
    data_loader: DataLoader,
    analysis_type: str,
    metric_col: Optional[str] = None,
    total_col: Optional[str] = None,
    numerator_cols: Optional[Dict[str, str]] = None,
    entity_col: str = 'issuer_name',
    dimensions: Optional[List[str]] = None,
    time_col: Optional[str] = None,
    target_entity: Optional[str] = None,
) -> Tuple[Optional[List[ValidationIssue]], bool]:
    """
    Run validation and return issues + should_abort flag.
    
    Parameters
    ----------
    df : pd.DataFrame
        Input data
    config : ConfigManager
        Configuration manager instance
    data_loader : DataLoader
        Data loader with validation methods
    analysis_type : str
        'share' or 'rate'
    metric_col : str, optional
        For share analysis: the metric column
    total_col : str, optional
        For rate analysis: the denominator column
    numerator_cols : dict, optional
        For rate analysis: mapping of rate name to numerator column
    entity_col : str
        Entity identifier column
    dimensions : list, optional
        Dimensions to validate
    time_col : str, optional
        Time column if present
    target_entity : str, optional
        Target entity for analysis
        
    Returns
    -------
    Tuple[Optional[List[ValidationIssue]], bool]
        (issues, should_abort): List of issues and whether to abort analysis.
        issues is None if validation is disabled.
    """
    validate_input = config.get('input', 'validate_input', default=True)
    if not validate_input:
        logger.info("Input validation is disabled.")
        return None, False
    
    logger.info("Running input data validation...")
    
    val_dimensions = dimensions if dimensions else data_loader.get_available_dimensions(df)
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
    elif analysis_type == 'rate':
        issues = data_loader.validate_rate_input(
            df=df,
            total_col=total_col,
            numerator_cols=numerator_cols or {},
            entity_col=entity_col,
            dimensions=val_dimensions,
            time_col=time_col,
            target_entity=target_entity,
            thresholds=thresholds
        )
    else:
        logger.error(f"Unknown analysis type: {analysis_type}")
        return [], True
    
    # Categorize issues
    errors = [i for i in issues if i.severity == ValidationSeverity.ERROR]
    warnings = [i for i in issues if i.severity == ValidationSeverity.WARNING]
    infos = [i for i in issues if i.severity == ValidationSeverity.INFO]
    
    # Log all issues
    for issue in issues:
        if issue.severity == ValidationSeverity.ERROR:
            logger.error(f"VALIDATION ERROR [{issue.category}]: {issue.message}")
        elif issue.severity == ValidationSeverity.WARNING:
            logger.warning(f"VALIDATION WARNING [{issue.category}]: {issue.message}")
        else:
            logger.info(f"VALIDATION INFO [{issue.category}]: {issue.message}")
    
    # Summary and decision
    if errors:
        logger.error(f"Found {len(errors)} ERROR(s), {len(warnings)} WARNING(s), {len(infos)} INFO(s)")
        logger.error("Analysis ABORTED due to validation errors. Fix the data and retry.")
        return issues, True
    elif warnings:
        logger.warning(f"Found {len(warnings)} WARNING(s), {len(infos)} INFO(s). Proceeding with analysis.")
    elif infos:
        logger.info(f"Found {len(infos)} INFO(s). Data quality is good.")
    else:
        logger.info("Input validation passed with no issues.")
    
    return issues, False
```

---

### TASK 8: Update benchmark.py to Use Validation Runner

**File**: `benchmark.py`

**Step 8a**: Add import at top of file (around line 27):
```python
from core.validation_runner import run_input_validation
```

**Step 8b**: In `run_share_analysis()`, find the large validation block (approximately lines 543-588) that starts with:
```python
# ========================================
# Input Data Validation (Phase 2 feature)
# ========================================
validation_issues = None
validate_input = config.get('input', 'validate_input', default=True)
```

**Replace the entire block** (from `# Input Data Validation` to `logger.info("Input validation passed with no issues.")`) with:
```python
# ========================================
# Input Data Validation
# ========================================
val_dimensions = args.dimensions if args.dimensions else data_loader.get_available_dimensions(df)
validation_issues, should_abort = run_input_validation(
    df=df,
    config=config,
    data_loader=data_loader,
    analysis_type='share',
    metric_col=metric_col,
    entity_col=entity_col,
    dimensions=val_dimensions,
    time_col=time_col,
    target_entity=args.entity
)
if should_abort:
    return 1
```

**Step 8c**: Do the same replacement in `run_rate_analysis()`. Find the validation block (around lines 828-878) and replace with:
```python
# ========================================
# Input Data Validation
# ========================================
val_dimensions = args.dimensions if args.dimensions else data_loader.get_available_dimensions(df)
numerator_cols = {}
if hasattr(args, 'approved_col') and args.approved_col:
    numerator_cols['approval'] = args.approved_col
if hasattr(args, 'fraud_col') and args.fraud_col:
    numerator_cols['fraud'] = args.fraud_col

validation_issues, should_abort = run_input_validation(
    df=df,
    config=config,
    data_loader=data_loader,
    analysis_type='rate',
    total_col=total_col,
    numerator_cols=numerator_cols,
    entity_col=entity_col,
    dimensions=val_dimensions,
    time_col=time_col,
    target_entity=args.entity
)
if should_abort:
    return 1
```

---

### TASK 9: Add Defensive Calculations in Dimensional Analyzer

**File**: `core/dimensional_analyzer.py`  
**Location**: At the start of `calculate_share_distortion()` method body (after docstring)

**Add This Code**:
```python
def calculate_share_distortion(self, df, metric_col, dimensions, target_entity=None):
    """..."""  # existing docstring
    
    entity = target_entity or self.target_entity
    if not entity:
        logger.warning("No target entity specified for distortion calculation")
        return pd.DataFrame()
    
    # Defensive data checks
    if metric_col not in df.columns:
        logger.error(f"Metric column '{metric_col}' not found in DataFrame")
        return pd.DataFrame()
    
    if df[metric_col].isna().any():
        nan_count = df[metric_col].isna().sum()
        logger.warning(f"Metric column '{metric_col}' contains {nan_count} NaN values - these rows will be excluded")
        df = df[df[metric_col].notna()].copy()
    
    if (df[metric_col] < 0).any():
        neg_count = (df[metric_col] < 0).sum()
        logger.warning(f"Metric column '{metric_col}' contains {neg_count} negative values - these rows will be excluded")
        df = df[df[metric_col] >= 0].copy()
    
    if df.empty:
        logger.warning("No valid data remaining after filtering NaN/negative values")
        return pd.DataFrame()
    
    # ... rest of existing method
```

---

### TASK 10: Make Distortion Thresholds Configurable

**File**: `utils/config_manager.py`  
**Location**: In the `_get_default_config()` method, inside the `'output'` dict

**Find**:
```python
'output': {
    'format': 'xlsx',
    'output_format': 'analysis',
    'include_debug_sheets': False,
    # ... etc
}
```

**Add these lines** inside the `'output'` dict:
```python
'distortion_thresholds': {
    'high_distortion_pp': 1.0,
    'low_distortion_pp': 0.25,
},
```

**File**: `benchmark.py`  
**Location**: In `generate_excel_report()` function, find the conditional formatting code

**Find** (around line 2234):
```python
if col_name == 'Distortion_PP' and isinstance(value, (int, float)):
    if abs(value) > 1.0:  # High distortion (>1 pp)
        cell.fill = PatternFill(start_color="FFCCCC", ...)
    elif abs(value) < 0.25:  # Low distortion (<0.25 pp)
```

**Replace With**:
```python
if col_name == 'Distortion_PP' and isinstance(value, (int, float)):
    # Get configurable thresholds (passed via metadata or use defaults)
    high_threshold = metadata.get('distortion_thresholds', {}).get('high_distortion_pp', 1.0)
    low_threshold = metadata.get('distortion_thresholds', {}).get('low_distortion_pp', 0.25)
    
    if abs(value) > high_threshold:
        cell.fill = PatternFill(start_color="FFCCCC", end_color="FFCCCC", fill_type="solid")
    elif abs(value) < low_threshold:
        cell.fill = PatternFill(start_color="CCFFCC", end_color="CCFFCC", fill_type="solid")
```

**Also**: Update the metadata dict creation (around line 835) to include thresholds:
```python
metadata = {
    # ... existing fields ...
    'distortion_thresholds': {
        'high_distortion_pp': config.get('output', 'distortion_thresholds', 'high_distortion_pp', default=1.0),
        'low_distortion_pp': config.get('output', 'distortion_thresholds', 'low_distortion_pp', default=0.25),
    },
}
```

---

### TASK 11: Add Unit Tests

**File**: `tests/test_enhanced_features.py`

**Add These Test Cases**:
```python
import pytest
import pandas as pd
import numpy as np
from core.data_loader import DataLoader, ValidationSeverity
from core.dimensional_analyzer import DimensionalAnalyzer
from utils.config_manager import ConfigManager


class TestValidationEdgeCases:
    """Test edge cases in data validation."""
    
    @pytest.fixture
    def config(self):
        return ConfigManager()
    
    @pytest.fixture
    def data_loader(self, config):
        return DataLoader(config)
    
    def test_unicode_entity_names(self, data_loader):
        """Test validation with Unicode entity names."""
        df = pd.DataFrame({
            'issuer_name': ['Banco São Paulo', 'Itaú Unibanco', 'Bradesco', 'Santander', 'Nubank', 'Inter'],
            'metric': [100, 200, 150, 180, 90, 60],
            'dimension': ['A', 'A', 'B', 'B', 'A', 'B']
        })
        
        issues = data_loader.validate_share_input(
            df=df,
            metric_col='metric',
            entity_col='issuer_name',
            dimensions=['dimension'],
            target_entity='Banco São Paulo'
        )
        
        errors = [i for i in issues if i.severity == ValidationSeverity.ERROR]
        assert len(errors) == 0, f"Unicode entity names should not cause errors: {errors}"
    
    def test_empty_dataframe(self, data_loader):
        """Test validation with empty DataFrame."""
        df = pd.DataFrame(columns=['issuer_name', 'metric', 'dimension'])
        
        issues = data_loader.validate_share_input(
            df=df,
            metric_col='metric',
            entity_col='issuer_name',
            dimensions=['dimension']
        )
        
        # Should have error about insufficient peers
        errors = [i for i in issues if i.severity == ValidationSeverity.ERROR]
        assert any('peer' in str(i.message).lower() for i in errors)
    
    def test_null_heavy_data(self, data_loader):
        """Test validation when nulls exceed threshold."""
        df = pd.DataFrame({
            'issuer_name': ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J'],
            'metric': [100, None, None, None, None, None, 90, 80, 70, 60],  # 50% null
            'dimension': ['X'] * 10
        })
        
        issues = data_loader.validate_share_input(
            df=df,
            metric_col='metric',
            entity_col='issuer_name',
            dimensions=['dimension']
        )
        
        errors = [i for i in issues if i.severity == ValidationSeverity.ERROR]
        assert any('null' in str(i.message).lower() for i in errors)


class TestPresetComparison:
    """Test preset comparison edge cases."""
    
    def test_empty_dimensions_list(self):
        """Test preset comparison with no dimensions."""
        from benchmark import run_preset_comparison
        import logging
        
        df = pd.DataFrame({
            'issuer_name': ['A', 'B', 'C', 'D', 'E'],
            'metric': [100, 200, 150, 180, 90]
        })
        
        result = run_preset_comparison(
            df=df,
            metric_col='metric',
            entity_col='issuer_name',
            dimensions=[],  # Empty!
            target_entity='A',
            time_col=None,
            analysis_type='share',
            logger=logging.getLogger()
        )
        
        assert result.empty, "Empty dimensions should return empty DataFrame"


class TestTimeColumnHandling:
    """Test time column edge cases."""
    
    def test_time_column_with_nulls(self):
        """Test distortion calc when time column has None values."""
        df = pd.DataFrame({
            'issuer_name': ['A', 'B', 'A', 'B', 'A', 'B'],
            'metric': [100, 200, 150, 180, 90, 60],
            'dimension': ['X', 'X', 'X', 'X', 'Y', 'Y'],
            'period': ['2024-01', '2024-01', None, None, '2024-02', '2024-02']
        })
        
        analyzer = DimensionalAnalyzer(
            target_entity='A',
            entity_column='issuer_name',
            time_column='period'
        )
        
        # This should NOT raise TypeError
        result = analyzer.calculate_share_distortion(
            df=df,
            metric_col='metric',
            dimensions=['dimension'],
            target_entity='A'
        )
        
        # Should have processed the non-null time periods
        assert not result.empty


class TestDefensiveCalculations:
    """Test defensive handling of bad data."""
    
    def test_negative_values_filtered(self):
        """Test that negative values are filtered out."""
        df = pd.DataFrame({
            'issuer_name': ['A', 'B', 'C', 'D', 'E'],
            'metric': [100, -50, 150, 180, 90],  # One negative
            'dimension': ['X'] * 5
        })
        
        analyzer = DimensionalAnalyzer(
            target_entity='A',
            entity_column='issuer_name'
        )
        
        result = analyzer.calculate_share_distortion(
            df=df,
            metric_col='metric',
            dimensions=['dimension'],
            target_entity='A'
        )
        
        # Should not crash, and should have results
        assert not result.empty
```

---

## Verification Steps

After completing all tasks, run these commands:

```powershell
# 1. Check for syntax errors
py -m py_compile benchmark.py
py -m py_compile tui_app.py
py -m py_compile core/data_loader.py
py -m py_compile core/dimensional_analyzer.py
py -m py_compile core/validation_runner.py

# 2. Run existing tests
py -m pytest tests/ -v

# 3. Run the new tests
py -m pytest tests/test_enhanced_features.py -v

# 4. Quick smoke test
py benchmark.py share --csv test_data.csv --metric txn_cnt --validate-input

# 5. Verify TUI launches without error
py tui_app.py
```

---

## Success Criteria

- [ ] No `SyntaxError` when importing any module
- [ ] All existing tests pass
- [ ] All new edge case tests pass
- [ ] TUI launches without crashing
- [ ] Share analysis completes with `--validate-input`
- [ ] No bare `except:` statements remain (search: `except:` with no exception type)
- [ ] No duplicate variable declarations
- [ ] Validation logic exists in ONE place (`core/validation_runner.py`)

---

## Files Modified Summary

| File | Action | Description |
|------|--------|-------------|
| `benchmark.py` | MODIFY | Remove duplicates, use validation_runner, add guards |
| `tui_app.py` | MODIFY | Fix bare exceptions |
| `core/dimensional_analyzer.py` | MODIFY | Fix time nulls, add defensive checks |
| `core/validation_runner.py` | NEW | Extracted validation orchestration |
| `utils/config_manager.py` | MODIFY | Add distortion thresholds |
| `tests/test_enhanced_features.py` | MODIFY | Add edge case tests |

---

## Common Pitfalls to Avoid

1. **Don't break imports**: When adding `core/validation_runner.py`, ensure `core/__init__.py` exists (it should already).

2. **Watch indentation**: Python is whitespace-sensitive. Match the existing code style (4 spaces).

3. **Don't remove the logger import**: `benchmark.py` uses `logging.getLogger()` - ensure the import stays.

4. **Test incrementally**: After each task, run `py -m py_compile <file>` to catch syntax errors early.

5. **Preserve function signatures**: Don't change the parameters of `run_share_analysis()` or `run_rate_analysis()` - other code depends on them.

---

## Questions? Context You Might Need

### Q: Where is the validation modal in the TUI?
A: `tui_app.py`, class `ValidationModal` around line 129. It's a `ModalScreen` subclass.

### Q: What's the difference between share and rate analysis?
A: Share analysis compares market share percentages. Rate analysis compares rates (approval rate, fraud rate) calculated as numerator/denominator.

### Q: What are "presets"?
A: Pre-configured optimization settings (e.g., `balanced_default`, `minimal_distortion`). Stored in `presets/` directory as YAML files.

### Q: What's the TUI framework?
A: [Textual](https://textual.textualize.io/) - a Python TUI framework. Uses CSS-like styling and reactive widgets.
