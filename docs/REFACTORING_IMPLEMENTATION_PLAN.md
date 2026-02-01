# Refined Architectural Refactoring Implementation Plan

**Date:** 2026-01-31  
**Status:** Proposed  
**Based on:** [Analysis of original plan](file:///C:/Users/e176097/.gemini/antigravity/brain/fb164f7c-a7f9-4695-bbe8-97ca935e0d68/analysis.md)

---

## User Review Required

> [!IMPORTANT]
> **Phase 1 (Strategy Pattern)** is the most impactful change. I recommend implementing phases sequentially, with integration tests run between each phase. Would you prefer to tackle all 4 phases or focus on specific ones first?

> [!WARNING]
> **Breaking change consideration:** The solver module extraction (Phase 1) will change internal class structure. External CLI interface remains unchanged, but any code importing `DimensionalAnalyzer` internals will need updates.

---

## Proposed Changes

### Phase 1: Extract Solver Classes (Strategy Pattern)

**Goal:** Decompose `DimensionalAnalyzer` from 3050 lines by extracting optimization algorithms.

---

#### [NEW] [__init__.py](file:///d:/Projects/Peer%20Benchmark%20Tool/core/solvers/__init__.py)

Create new `core/solvers/` package with exports:
```python
from .base_solver import PrivacySolver, SolverResult
from .lp_solver import LPSolver
from .heuristic_solver import HeuristicSolver
```

---

#### [NEW] [base_solver.py](file:///d:/Projects/Peer%20Benchmark%20Tool/core/solvers/base_solver.py)

Define abstract interface:
```python
@dataclass
class SolverResult:
    weights: Dict[str, float]
    method: str
    stats: Dict[str, Any]
    success: bool

class PrivacySolver(ABC):
    @abstractmethod
    def solve(self, peers, categories, max_concentration, peer_volumes, **kwargs) -> Optional[SolverResult]:
        pass
```

---

#### [NEW] [lp_solver.py](file:///d:/Projects/Peer%20Benchmark%20Tool/core/solvers/lp_solver.py)

Extract from `DimensionalAnalyzer._solve_global_weights_lp` (lines 252-486):
- Move all LP constraint building logic
- Encapsulate SciPy availability check
- Return `SolverResult` with stats (slack, method used)

---

#### [NEW] [heuristic_solver.py](file:///d:/Projects/Peer%20Benchmark%20Tool/core/solvers/heuristic_solver.py)

Extract from `DimensionalAnalyzer._solve_dimension_weights_heuristic` (lines 1487-1722):
- Move `objective()` function
- Move penalty calculation (will use shared helper after Phase 3)
- Accept `target_weights` and `rule_name` in constructor

---

#### [MODIFY] [dimensional_analyzer.py](file:///d:/Projects/Peer%20Benchmark%20Tool/core/dimensional_analyzer.py)

- Remove `_solve_global_weights_lp` and `_solve_dimension_weights_heuristic` methods
- Add imports: `from .solvers import LPSolver, HeuristicSolver`
- In `__init__`, instantiate solvers:
  ```python
  self.lp_solver = LPSolver(tolerance=self.tolerance, ...)
  self.heuristic_solver = HeuristicSolver(config=...)
  ```
- Update call sites to use `self.lp_solver.solve(...)`

**Expected reduction:** ~500 lines removed from `DimensionalAnalyzer`

---

### Phase 2: Fix Column Normalization (DataLoader)

**Goal:** Prevent data corruption from duplicate normalized column names.

---

#### [MODIFY] [data_loader.py](file:///d:/Projects/Peer%20Benchmark%20Tool/core/data_loader.py)

Update `_normalize_columns` method (lines 222-245):

```python
def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
    # 1. Lowercase and strip
    new_cols = df.columns.str.lower().str.strip()
    # 2. Replace common separators with underscores
    new_cols = new_cols.str.replace(r'[\s\-\.]+', '_', regex=True)
    # 3. Remove remaining special characters
    new_cols = new_cols.str.replace(r'[^a-z0-9_]', '', regex=True)
    
    # 4. Deduplicate - append suffix if collision detected
    seen = {}
    final_cols = []
    for i, col in enumerate(new_cols):
        if col in seen:
            original_a = df.columns[seen[col]]
            original_b = df.columns[i]
            logger.warning(
                f"Column name collision after normalization: "
                f"'{original_a}' and '{original_b}' both normalize to '{col}'. "
                f"Appending suffix."
            )
            final_cols.append(f"{col}_{i}")
        else:
            seen[col] = i
            final_cols.append(col)
    
    df.columns = final_cols
    return df
```

---

### Phase 3: Sync Privacy Rules

**Goal:** Eliminate hardcoded rule thresholds in penalty function, use `PrivacyValidator` as single source of truth.

---

#### [MODIFY] [privacy_validator.py](file:///d:/Projects/Peer%20Benchmark%20Tool/core/privacy_validator.py)

Add helper method to expose constraint thresholds for optimization:

```python
@classmethod
def get_penalty_thresholds(cls, rule_name: str) -> Dict[str, Tuple[int, float]]:
    """Return thresholds for penalty calculation in optimization.
    
    Returns dict with keys like 'min_count_above_threshold', 'min_count_15', etc.
    Each value is (count, threshold_percentage).
    """
    rule = cls.RULES.get(rule_name, {})
    additional = rule.get('additional', {})
    
    result = {}
    if 'min_count_above_threshold' in additional:
        result['min_count_above_threshold'] = additional['min_count_above_threshold']
    if 'min_count_15' in additional:
        result['tier_15'] = (additional['min_count_15'], 15.0)
        result['tier_8'] = (additional.get('min_count_8', 1), 8.0)
    if 'min_count_20' in additional:
        result['tier_20'] = (additional['min_count_20'], 20.0)
        result['tier_10'] = (additional.get('min_count_10', 1), 10.0)
    
    return result
```

---

#### [MODIFY] [dimensional_analyzer.py](file:///d:/Projects/Peer%20Benchmark%20Tool/core/dimensional_analyzer.py) or [heuristic_solver.py](file:///d:/Projects/Peer%20Benchmark%20Tool/core/solvers/heuristic_solver.py)

Refactor `_additional_constraints_penalty` (lines 994-1058) to use dynamic lookup:

```python
def _additional_constraints_penalty(self, shares, rule_name, thresholds=None):
    if thresholds is None:
        thresholds = PrivacyValidator.get_penalty_thresholds(rule_name)
    
    if not thresholds:
        return 0.0
    
    shares_sorted = sorted(shares, reverse=True)
    penalty = 0.0
    
    # Generic penalty for all threshold tiers
    for key, (min_count, threshold) in thresholds.items():
        idx = min_count - 1
        observed = shares_sorted[idx] if idx < len(shares_sorted) else 0.0
        penalty += max(0.0, threshold - observed) ** 2
    
    return penalty
```

---

### Phase 4: Explicit Dependency Handling

**Goal:** Fail fast with clear message when optional Excel dependency is missing.

---

#### [MODIFY] [report_generator.py](file:///d:/Projects/Peer%20Benchmark%20Tool/core/report_generator.py)

Add dependency check at format selection time (before deep execution):

```python
def generate_report(self, results, output_file, format='excel', ...):
    # Early check for Excel dependencies
    if format == 'excel':
        self._ensure_excel_support()
    # ... rest of method
    
def _ensure_excel_support(self):
    """Check Excel dependencies before attempting to generate."""
    try:
        import openpyxl
    except ImportError:
        raise ImportError(
            "Generating Excel reports requires 'openpyxl'. "
            "Install it with: pip install openpyxl\n"
            "Or use --format csv or --format json instead."
        )
```

---

## Verification Plan

### Automated Tests

Run existing test suite to ensure no regressions:

```powershell
cd "d:\Projects\Peer Benchmark Tool"
python -m pytest tests\ -v
```

### New Unit Tests to Add

#### [NEW] [test_solvers.py](file:///d:/Projects/Peer%20Benchmark%20Tool/tests/test_solvers.py)

Test isolated solver behavior:
- `test_lp_solver_returns_valid_weights`
- `test_heuristic_solver_respects_bounds`
- `test_solver_result_contains_stats`

#### [NEW] [test_data_loader_normalization.py](file:///d:/Projects/Peer%20Benchmark%20Tool/tests/test_data_loader_normalization.py)

Test column collision handling:
- `test_collision_detection_rate_percent_hash` - Test "Rate (%)" and "Rate (#)" 
- `test_no_collision_unique_columns`
- `test_suffix_appended_on_collision`

### Integration Tests

Run CLI sweep tests to verify end-to-end behavior unchanged:

```powershell
cd "d:\Projects\Peer Benchmark Tool"
# Share analysis
python benchmark.py share --csv data\e176097_tpv_nubank_filtered.csv --entity-col issuer_name --entity Others --metric volume_brl --dimensions product_cd credit_debit_ind --output outputs\test_refactor.xlsx

# Rate analysis  
python benchmark.py rate --csv data\e176097_tpv_nubank_filtered.csv --entity-col issuer_name --entity Others --total total_txn --approved txn_count --dimensions product_cd --output outputs\test_rate_refactor.xlsx
```

### Manual Verification

1. **Verify Excel output still works** - Open generated `.xlsx` file in Excel
2. **Test missing openpyxl** - Rename/remove openpyxl package temporarily, run with `--format excel`, confirm clear error message appears

---

## Implementation Order

| Phase | Effort | Risk | Recommended Order |
|-------|--------|------|-------------------|
| Phase 2 (Column Normalization) | Low | Low | 1st - Smallest, safest |
| Phase 4 (Dependency Handling) | Low | Low | 2nd - Quick win |
| Phase 3 (Privacy Rules Sync) | Medium | Medium | 3rd - Requires Phase 1 location |
| Phase 1 (Strategy Pattern) | High | Medium | 4th - Most impactful, do last |

> [!TIP]
> Alternative: If you want the biggest impact first, start with Phase 1, but be prepared for a larger PR.
