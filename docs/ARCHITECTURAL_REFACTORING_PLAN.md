# Architectural Refactoring & Quality Improvement Plan

**Date:** 2026-01-31
**Status:** Planned
**Target:** `core/` module

This document outlines the implementation plan for high-priority architectural improvements and code quality fixes identified during the exhaustive codebase review.

## Executive Summary

The following changes aim to reduce complexity in the core analysis engine (`DimensionalAnalyzer`), improve data safety (`DataLoader`), eliminate logic duplication for privacy rules, and ensure robust dependency management.

## Scope of Work

1.  **Refactor `DimensionalAnalyzer` (Strategy Pattern)**: Extract optimization logic into dedicated solver classes.
2.  **Fix Column Normalization**: Prevent column name collisions in `DataLoader`.
3.  **Sync Privacy Rules**: Unify privacy logic between `PrivacyValidator` and `DimensionalAnalyzer`.
4.  **Explicit Dependencies**: Improve failure handling for optional dependencies (`openpyxl`).

---

## 1. Refactor `DimensionalAnalyzer` (Strategy Pattern)

**Objective:** Decompose the "God Object" `DimensionalAnalyzer` (~1600 lines) by extracting optimization algorithms into a Strategy pattern. This improves testability and readability.

### Current State
`DimensionalAnalyzer` contains:
- Data aggregation logic (`_build_categories`)
- Global LP solving logic (`_solve_global_weights_lp`)
- Heuristic/Bayesian solving logic (`_solve_dimension_weights_heuristic`)
- Reporting/Diagnostics logic

### Implementation Plan

#### 1.1. Create Solver Package
Create a new package structure:
```
core/
└── solvers/
    ├── __init__.py
    ├── base_solver.py
    ├── lp_solver.py
    └── heuristic_solver.py
```

#### 1.2. Define Base Interface (`base_solver.py`)
Define an abstract base class `PrivacySolver` with a standard interface:
```python
class PrivacySolver(ABC):
    @abstractmethod
    def solve(
        self,
        peers: List[str],
        categories: List[Dict[str, Any]],
        max_concentration: float,
        peer_volumes: Dict[str, float],
        **kwargs
    ) -> Optional[Dict[str, float]]:
        pass
```

#### 1.3. Extract LP Solver (`lp_solver.py`)
*   Move `_solve_global_weights_lp` logic to `LPSolver.solve`.
*   Encapsulate SciPy dependency check within this class.
*   Return not just weights but also execution stats (slack, method used) in a structured result object (e.g., `SolverResult`).

#### 1.4. Extract Heuristic Solver (`heuristic_solver.py`)
*   Move `_solve_dimension_weights_heuristic` logic to `HeuristicSolver.solve`.
*   Move the nested `objective` function logic here.
*   Accept `target_weights` and `rule_name` via `kwargs` or constructor.

#### 1.5. Update `DimensionalAnalyzer`
*   Remove extracted methods.
*   Instantiate solvers in `__init__`:
    ```python
    self.lp_solver = LPSolver(config=...)
    self.heuristic_solver = HeuristicSolver(config=...)
    ```
*   Update usage sites to call `self.lp_solver.solve(...)`.

---

## 2. Fix `DataLoader` Column Normalization

**Objective:** Prevent data corruption when column normalization produces duplicate names (e.g., "Rate (%)" and "Rate (#)" both becoming "rate").

### Current State
Regex `[^a-zA-Z0-9_]` strips all special characters blindly.

### Implementation Plan

#### 2.1. Update `_normalize_columns` in `core/data_loader.py`
Modify the normalization logic to be smarter:
1.  **Transliteration:** Replace specific separators first ( `-`, `.`, ` ` -> `_`).
2.  **Sanitization:** Remove other special characters.
3.  **Deduplication:** Check for duplicates after normalization.
    *   If duplicates exist, append a suffix (e.g., `_1`, `_2`) or fail with a clear error listing the colliding original names.

**Proposed Logic:**
```python
def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
    # 1. Replace separators
    new_cols = df.columns.str.lower().str.replace(r'[\s\-\.]+', '_', regex=True)
    # 2. Remove other special chars
    new_cols = new_cols.str.replace(r'[^a-z0-9_]', '', regex=True)
    
    # 3. Deduplicate
    if len(new_cols) != len(set(new_cols)):
        # Logic to handle duplicates or raise descriptive error
        pass
        
    df.columns = new_cols
    return df
```

---

## 3. Sync Privacy Rules (Dynamic Penalty Logic)

**Objective:** Eliminate logic duplication where privacy rules (like 6/30, 7/35) are hardcoded in `DimensionalAnalyzer`'s penalty functions, risking drift from the definitions in `PrivacyValidator`.

### Current State
`DimensionalAnalyzer._additional_constraints_penalty` has `if rule_name == '6/30': ...` blocks that duplicate logic from `PrivacyValidator`.

### Implementation Plan

#### 3.1. Enhance `PrivacyValidator` Interface
Ensure `PrivacyValidator` exposes rule configurations in a consumable format for optimization (e.g., thresholds, counts). (Already exists as `get_rule_config`).

#### 3.2. Data-Driven Penalty Calculation in `HeuristicSolver`
Refactor the penalty calculation (moved to `heuristic_solver.py` in step 1) to be generic:

1.  Retrieve rule config: `config = PrivacyValidator.get_rule_config(rule_name)`
2.  Iterate over `config['additional']` keys (e.g., `min_count_above_threshold`, `min_count_15`).
3.  Apply penalties dynamically based on the config values, removing hardcoded rule names.

**Example Concept:**
```python
# Instead of: if rule == '6/30': penalty += ...
# Use:
for constraint_type, params in rule_config['additional'].items():
    if constraint_type == 'min_count_above_threshold':
        min_count, threshold = params
        # Apply generic penalty logic for "N count above X threshold"
```

#### 3.3. Delegate Verification
Ensure `DimensionalAnalyzer` uses `PrivacyValidator.evaluate_additional_constraints` for boolean pass/fail checks instead of re-implementing the check.

---

## 4. Explicit Dependencies (`openpyxl`)

**Objective:** Improve user experience by failing fast with clear instructions if optional dependencies required for reporting are missing.

### Current State
`ReportGenerator` imports `openpyxl` inside methods like `_generate_excel_report`. If missing, it crashes deep in the execution flow.

### Implementation Plan

#### 4.1. Check in `ReportGenerator.__init__`
Perform the check during initialization if the output format requires it.

```python
class ReportGenerator:
    def __init__(self, config: Any):
        self.config = config
        self._check_dependencies()

    def _check_dependencies(self):
        try:
            import openpyxl
        except ImportError:
            # Set a flag or log a warning
            self.has_excel_support = False
        else:
            self.has_excel_support = True

    def generate_report(self, ..., format='excel'):
        if format == 'excel' and not self.has_excel_support:
            raise ImportError("Generating Excel reports requires 'openpyxl'. Please install it: pip install openpyxl")
```

---

## Verification Plan

1.  **Unit Tests:**
    *   Test `DataLoader` with colliding column names (`Rate %`, `Rate #`).
    *   Test `LPSolver` and `HeuristicSolver` in isolation (mock inputs).
    *   Test `ReportGenerator` without `openpyxl` installed (simulated).
2.  **Integration Tests:**
    *   Run a full CLI sweep (`py benchmark.py share ...`) to ensure the refactored `DimensionalAnalyzer` produces identical weights to the previous implementation.
    *   Verify `Privacy Validation` sheets still correctly report violations/passes for all supported rules (5/25, 6/30, 7/35, 10/40).
