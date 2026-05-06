# Core Logic Review - Peer Benchmark Tool

**Date:** February 1, 2026  
**Reviewer:** Senior Developer Code Review  
**Scope:** `/core/` module - Business logic layer  

---

## Executive Summary

The core module implements a sophisticated privacy-compliant peer benchmarking system. The architecture demonstrates solid engineering principles with clear separation of concerns, but several areas warrant attention for maintainability, robustness, and future scalability.

### Overall Assessment: **B+ (Good with Notable Issues)**

| Aspect | Rating | Notes |
|--------|--------|-------|
| Architecture | A- | Clean separation, well-structured solver pattern |
| Code Quality | B | Functional but some methods are excessively long |
| Maintainability | B- | Tight coupling in places, inconsistent patterns |
| Error Handling | C+ | Inconsistent exception handling strategy |
| Performance | B | Reasonable, but some optimization opportunities |
| Documentation | B+ | Good docstrings, but some complex logic undocumented |

---

## Detailed Findings

### 1. DimensionalAnalyzer (`dimensional_analyzer.py`) - 2,549 lines

**The core orchestration class. Critical for all analysis.**

#### 1.1 Architecture Strengths ✅

- **Strategy Pattern for Solvers**: Clean delegation to `LPSolver` and `HeuristicSolver` with fallback chain
- **Builder Pattern**: `CategoryBuilder` properly extracts category construction logic
- **Separation of Concerns**: Diagnostics extracted to `DiagnosticsEngine`
- **Configurable Behavior**: Extensive parameterization allows fine-tuning without code changes

#### 1.2 Critical Issues 🔴

##### 1.2.1 God Class Anti-Pattern
The class has **40+ instance variables** and **30+ methods**. This violates Single Responsibility Principle:

```python
# Lines 42-85 constructor parameters
def __init__(
    self,
    target_entity: Optional[str],
    entity_column: str = 'entity_identifier',
    bic_percentile: float = 0.85,
    debug_mode: bool = False,
    consistent_weights: bool = False,
    max_iterations: int = 1000,
    tolerance: float = 1.0,
    max_weight: float = 10.0,
    min_weight: float = 0.01,
    volume_preservation_strength: float = 0.5,
    prefer_slacks_first: bool = False,
    auto_subset_search: bool = False,
    # ... 30+ more parameters
):
```

**Recommendation**: Split into focused classes:
- `WeightOptimizer` - weight calculation logic
- `PrivacyConstraintManager` - privacy rule handling
- `AnalysisCalculator` - share/rate metric computation

##### 1.2.2 Excessive Method Length
`calculate_global_privacy_weights()` spans **~400 lines** (lines 978-1380). This method:
- Handles multiple algorithm paths (LP → subset search → heuristic)
- Contains nested conditionals 5+ levels deep
- Mixes orchestration logic with implementation details

**Impact**: Extremely difficult to test individual behaviors; high cognitive load for maintenance.

##### 1.2.3 State Management Complexity
The class accumulates state across method calls:
```python
self.global_weights = {}
self.per_dimension_weights: Dict[str, Dict[str, float]] = {}
self.weight_methods: Dict[str, str] = {}
self.last_lp_stats: Dict[str, Any] = {}
self.subset_search_results: List[Dict[str, Any]] = []
self.rank_changes_df: pd.DataFrame = pd.DataFrame()
self.privacy_validation_df: pd.DataFrame = pd.DataFrame()
self.additional_constraint_violations: List[Dict[str, Any]] = []
self.dynamic_constraint_stats: Dict[str, int] = {}
# ... more state variables
```

**Risk**: Hard to reason about object lifecycle; potential for stale state bugs.

##### 1.2.4 Duplicate Code in Share/Rate Analysis
`analyze_dimension_share()` (lines 1845-1908) and `analyze_dimension_rate()` (lines 1910-1978) share ~70% identical structure:

```python
# Both methods have nearly identical:
# - Time-aware vs non-time-aware branching
# - Category iteration loops
# - Result aggregation logic
```

**Recommendation**: Extract a template method or use a strategy pattern for the metric-specific calculations.

#### 1.3 Medium Priority Issues 🟡

##### 1.3.1 Magic Numbers
Several hardcoded values without clear documentation:
```python
# Line 289 - What does 1e-6 represent?
COMPARISON_EPSILON = 1e-6

# Line 291 - Why exactly 1e-3?
if max_excess > 1e-3:
    return weights
```

##### 1.3.2 Inconsistent Validation
Some methods silently return empty results on invalid input:
```python
def _calculate_share_metrics(...):
    if len(peer_df) == 0:
        logger.warning(f"No peers found...")
        return None  # Caller must check
```

Other methods raise exceptions. This inconsistency makes error handling unreliable.

##### 1.3.3 Deep Nesting in Validation Loop
Lines 1200-1350 contain validation logic with 6+ levels of nesting:
```python
if converged:
    if self.enforce_additional_constraints:
        if rule_name in ('6/30', '7/35', '10/40'):
            violations = ...
            if violations:
                if heuristic_result:
                    if not heuristic_result.success:
                        # etc.
```

**Recommendation**: Extract to separate methods with early returns.

##### 1.3.4 Deprecated Method Wrappers
Multiple deprecated methods exist that simply wrap new methods:
```python
def calculate_global_weights(self, ...):
    """DEPRECATED: Use calculate_global_privacy_weights instead."""
    logger.warning("calculate_global_weights is deprecated...")
    # ... legacy logic

def calculate_share_distortion(self, ...):
    """Deprecated wrapper for calculate_share_impact."""
    logger.warning("calculate_share_distortion is deprecated...")
    return self.calculate_share_impact(...)
```

**Recommendation**: Set a deprecation timeline and remove in next major version.

---

### 2. PrivacyValidator (`privacy_validator.py`) - 759 lines

**Implements Mastercard Control 3.2 privacy rules.**

#### 2.1 Strengths ✅

- **Declarative Rule Definitions**: `RULES` dict clearly documents all privacy rules
- **Static Methods for Rule Logic**: Allows stateless validation
- **Fallback Rule Support**: `validate_fallback_rules()` tries progressively permissive rules

#### 2.2 Issues 🔴

##### 2.2.1 Rule Configuration Hardcoding
Rules are hardcoded in the class:
```python
RULES = {
    '5/25': {'min_entities': 5, 'max_concentration': 25.0},
    '6/30': {'min_entities': 6, 'max_concentration': 30.0,
             'additional': {'min_count_above_threshold': (3, 7.0)}},
    # ...
}
```

**Risk**: Regulatory changes require code changes and redeployment.

**Recommendation**: Externalize to configuration file with schema validation.

##### 2.2.2 Epsilon Comparison Inconsistency

> **Status (2026-05-06):** Resolved. Both `PrivacyValidator` (line 33) and
> `DimensionalAnalyzer` (line 22) now import the single
> `COMPARISON_EPSILON = 1e-9` exported by `core/constants.py`. The note below
> is preserved for historical context only — do not chase this issue.

The class historically used `COMPARISON_EPSILON = 1e-3` while
`DimensionalAnalyzer` used `1e-6`, which created boundary-condition
disagreements between validator and analyzer.

##### 2.2.3 Complex Additional Constraint Logic
`evaluate_additional_constraints_with_thresholds()` (lines 293-362) has complex branching for different rule types:

```python
if rule_name == '6/30':
    if use_tiers:
        min_count, threshold = thresholds.get('tier_1', (3, 7.0))
    else:
        min_count, threshold = thresholds.get('min_count_above_threshold', (3, 7.0))
    # ...
elif rule_name == '7/35':
    # Different structure
elif rule_name == '10/40':
    # Yet another structure
```

**Recommendation**: Use polymorphism - create rule-specific validator classes.

#### 2.3 Medium Priority 🟡

##### 2.3.1 Incomplete Protected Entity Handling
Protected entities feature appears partially implemented:
```python
def __init__(self, ..., protected_entities: Optional[List[str]] = None, 
             protected_max_concentration: float = 25.0):
```

But `protected_max_concentration` is always 25% regardless of selected rule.

---

### 3. DataLoader (`data_loader.py`) - 882 lines

**Handles data ingestion and validation.**

#### 3.1 Strengths ✅

- **Comprehensive Validation**: `validate_share_input()` and `validate_rate_input()` cover many edge cases
- **Structured Validation Results**: `ValidationIssue` dataclass with severity levels
- **Column Normalization**: Handles various naming conventions gracefully

#### 3.2 Issues 🔴

##### 3.2.1 SQL Injection Vulnerability
```python
def load_from_sql_table(self, table_name: str) -> pd.DataFrame:
    connection = self.config.get_sql_connection()
    query = f"SELECT * FROM {table_name}"  # UNSAFE!
    df = pd.read_sql(query, connection)
```

**Critical**: Direct string interpolation allows SQL injection if `table_name` comes from user input.

**Fix**: Use parameterized queries or validate table name against allowlist.

##### 3.2.2 Unbounded File Reading
```python
def load_from_csv(self, file_path: str) -> pd.DataFrame:
    df = pd.read_csv(file_path)  # No size limits
```

**Risk**: Memory exhaustion with large files.

**Recommendation**: Add optional `nrows` parameter and chunk processing for large files.

#### 3.3 Medium Priority 🟡

##### 3.3.1 Heuristic Column Detection Fragility
Column detection relies on keyword matching:
```python
count_cols = [col for col in df.columns 
             if any(term in col.lower() for term in 
                   ['transaction_count', 'txn_count', 'count', 'cnt'])]
```

**Risk**: False positives (e.g., `account_type` matches `count`).

##### 3.3.2 Error Message Leakage
Validation error messages include full column lists:
```python
message=f"Required columns not found: {missing_cols}. Available: {list(df.columns)}"
```

**Risk**: May expose sensitive schema information in logs/UI.

---

### 4. ReportGenerator (`report_generator.py`) - 687 lines

**Generates Excel, CSV, and JSON reports.**

#### 4.1 Strengths ✅

- **Format Independence**: Clean abstraction for multiple output formats
- **Publication Mode**: Stakeholder-friendly output separate from debug output
- **Defensive Excel Import**: Checks for openpyxl before use

#### 4.2 Issues 🟡

##### 4.2.1 BPS Conversion Logic is Fragile
```python
def _should_convert_rate_column(column_name: str, convert_all_rates: bool) -> bool:
    col_lower = str(column_name).lower()
    if 'weight_effect' in col_lower or 'effect' in col_lower:
        return False
    # ... more string matching
```

**Risk**: Column naming changes could break BPS conversion silently.

##### 4.2.2 Sheet Name Truncation Without Collision Check

> **Status (2026-05-06):** Resolved. `ReportGenerator._build_unique_sheet_name`
> (lines 100–114) now adds a numeric suffix on collision, and the per-metric
> sheet uses the plain dimension name instead of the legacy `Metric_{i}_{...}`
> prefix (sheets are named after the dimension, e.g. `flag_domestic`). Note
> kept for history; do not reintroduce the legacy naming.

Historical concern: ``sheet_name = f"Metric_{i+1}_{metric_name[:20]}"`` did not
guard against two metrics sharing the same first 20 characters.

---

### 5. Solvers (`core/solvers/`)

**LP and Heuristic optimization implementations.**

#### 5.1 LPSolver (`lp_solver.py`) - 256 lines

##### 5.1.1 Strengths ✅
- **Clear Constraint Formulation**: Well-documented LP setup
- **Fallback Solver Methods**: Tries highs → highs-ds → highs-ipm
- **Comprehensive Statistics**: Returns detailed solver stats

##### 5.1.2 Issues 🟡

###### Tight Coupling to SciPy
```python
try:
    from scipy.optimize import linprog
    _SCIPY_AVAILABLE = True
except ImportError:
    linprog = None
    _SCIPY_AVAILABLE = False
```

**Observation**: The entire LP capability depends on SciPy. Consider documenting this as a hard dependency or providing a pure-Python fallback for simple cases.

###### Numerical Precision Concerns
```python
A_ub_rows.append(row)  # Float64 accumulation
# ...
res = linprog(c=c, A_ub=A_ub, ...)  # Large matrix operations
```

**Risk**: With many peers/categories, numerical precision may degrade. No explicit conditioning or scaling.

#### 5.2 HeuristicSolver (`heuristic_solver.py`) - 451 lines

##### 5.2.1 Issues 🟡

###### Hardcoded Penalty Weight
```python
VIOLATION_PENALTY_WEIGHT = 1000.0
```

**Risk**: This magic number significantly impacts optimization behavior but isn't configurable.

###### Code Duplication with DimensionalAnalyzer
`_build_constraint_stats()` and `_assess_additional_constraints_applicability()` are nearly identical to methods in `DimensionalAnalyzer`:

```python
# HeuristicSolver lines 250-300
def _build_constraint_stats(self, ...):
    # ~50 lines of identical logic

# DimensionalAnalyzer lines 370-420
def _build_constraint_stats(self, ...):
    # Same implementation
```

**Recommendation**: Extract to shared utility module or `DiagnosticsEngine`.

---

### 6. CategoryBuilder (`category_builder.py`) - 200 lines

#### 6.1 Strengths ✅
- **Clean Extraction**: Successfully separates category construction from analyzer
- **Time-Aware Support**: Handles both simple and time-aware categories

#### 6.2 Issues 🟡

##### Naming Convention for Time-Aware Dimensions
```python
all_categories.append({
    'dimension': f'_TIME_TOTAL_{self.time_column}',  # Underscore prefix = internal?
    'category': time_period,
    # ...
})
```

**Risk**: Magic string patterns used for dimension names could conflict with user data. Should document that dimension names starting with `_` are reserved.

---

### 7. DiagnosticsEngine (`diagnostics_engine.py`) - 80 lines

#### 7.1 Assessment ✅

A well-focused utility class. No significant issues.

**Minor**: Could benefit from more detailed docstrings explaining the mathematical basis for `dimension_unbalance_scores()`.

---

### 8. ValidationRunner (`validation_runner.py`) - 121 lines

#### 8.1 Assessment ✅

Clean orchestration of validation logic. Good extraction from main benchmark code.

**Minor**: `ConfigManager` type hint is quoted string - consider proper import for better IDE support.

---

## Cross-Cutting Concerns

### 9.1 Logging Strategy

**Observation**: Mix of logging approaches:
```python
logger.info(f"String interpolation {value}")  # f-string (preferred)
logger.info("Format string %s", value)         # lazy formatting
logger.warning("Concatenation " + str(value))  # string concat (avoid)
```

**Recommendation**: Standardize on lazy formatting for performance (`logger.info("Message %s", value)`).

### 9.2 Type Hints

**Observation**: Inconsistent type hint coverage. Some methods fully typed:
```python
def validate_share_input(
    self,
    df: pd.DataFrame,
    metric_col: str,
    entity_col: str,
    dimensions: List[str],
    ...
) -> List[ValidationIssue]:
```

Others have no hints:
```python
def _map_columns_to_canonical(self, columns):  # No hints
```

**Recommendation**: Add `py.typed` marker and complete type coverage. Run `mypy` in CI.

### 9.3 Testing Considerations

**Observation**: The tight coupling between `DimensionalAnalyzer` and `PrivacyValidator` makes unit testing difficult. Many methods require fully constructed `DimensionalAnalyzer` instances with many parameters.

**Recommendation**: Introduce dependency injection for validators and solvers.

---

## Recommendations Summary

### High Priority 🔴

1. **Fix SQL Injection** in `DataLoader.load_from_sql_table()`
2. **Refactor DimensionalAnalyzer** - Extract weight optimization and metric calculation to separate classes
3. **Standardize Epsilon Values** - Use consistent comparison tolerance across modules
4. **Externalize Privacy Rules** - Move `RULES` dict to configuration file

### Medium Priority 🟡

5. **Extract Common Code** - `_build_constraint_stats()` appears in 3 places
6. **Remove Deprecated Methods** - Schedule removal of `calculate_global_weights()`, `calculate_share_distortion()`, etc.
7. **Add Size Limits** - Protect against memory exhaustion in CSV loading
8. **Complete Type Hints** - Enable mypy strict mode

### Low Priority (Tech Debt) 🟢

9. **Reduce Method Length** - Target <50 lines per method
10. **Standardize Logging** - Use lazy formatting consistently
11. **Document Magic Numbers** - Add constants with descriptive names
12. **Add Metrics** - Instrument key methods for performance monitoring

---

## Appendix: Code Metrics

| File | Lines | Classes | Methods | Cyclomatic Complexity (Est.) |
|------|-------|---------|---------|------------------------------|
| dimensional_analyzer.py | 2,549 | 1 | 32 | High (>20) |
| privacy_validator.py | 759 | 1 | 15 | Medium (10-20) |
| data_loader.py | 882 | 3 | 14 | Medium |
| report_generator.py | 687 | 1 | 12 | Low (<10) |
| lp_solver.py | 256 | 1 | 1 | Medium |
| heuristic_solver.py | 451 | 1 | 7 | Medium |
| category_builder.py | 200 | 1 | 2 | Low |
| diagnostics_engine.py | 80 | 1 | 2 | Low |
| validation_runner.py | 121 | 0 | 3 | Low |

**Total Core Module**: ~5,985 lines of code

---

*End of Review*
