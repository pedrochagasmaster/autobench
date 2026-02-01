# Comprehensive Core Logic Review

**Date:** 2026-01-31
**Scope:** `core/` module (all files)
**Status:** Post-Fix Verification & Architectural Analysis

## Executive Summary

The `core` module implements a sophisticated privacy-preserving benchmarking engine. It includes data loading, dimensional analysis, privacy validation, and report generation. The recent implementation of `LPSolver` and `HeuristicSolver` along with dynamic privacy constraints shows a high level of maturity. However, `DimensionalAnalyzer` remains a "God Class" with significant complexity, and there are potential scalability concerns in the linear programming formulation for large peer groups.

## Detailed Findings

### 1. Architecture & Design

#### 1.1. DimensionalAnalyzer Complexity (`core/dimensional_analyzer.py`)
*   **Observation:** The `DimensionalAnalyzer` class is over 1000 lines long. It handles:
    *   Configuration & State Management
    *   Category Aggregation (Time-aware and standard)
    *   Solver orchestration (Global vs Per-Dimension)
    *   Fallback logic (Subsets, Heuristics)
    *   Diagnostics & Reporting prep
*   **Risk:** [HIGH] High maintenance cost. Adding new features (e.g., a new solver type or new privacy rule format) requires modifying this massive file, increasing regression risks.
*   **Recommendation:** Refactor into smaller components:
    *   `CategoryBuilder`: Handle `_build_categories` and `_build_time_aware_categories`.
    *   `PrivacyOrchestrator`: Handle the logic of trying LP, then Subsets, then Heuristics.
    *   `DiagnosticsEngine`: Handle `_compute_structural_caps_diagnostics` and `_dimension_unbalance_scores`.

#### 1.2. Privacy Logic Duplication
*   **Observation:** Both `PrivacyValidator` (`core/privacy_validator.py`) and `DimensionalAnalyzer` (via `_evaluate_additional_constraints` and `_find_additional_constraint_violations`) contain logic for evaluating privacy rules like "6/30" or "7/35".
*   **Risk:** [MEDIUM] Inconsistency. If a rule definition changes in `PrivacyValidator`, the checking logic in `DimensionalAnalyzer` might drift if not updated perfectly in sync (though `DimensionalAnalyzer` calls `PrivacyValidator` methods in some places, it also has its own penalty logic in `HeuristicSolver`).
*   **Recommendation:** Centralize *all* rule evaluation logic in `PrivacyValidator` or a dedicated `PrivacyRulesEngine`. The solvers should query this engine for penalty functions or violation checks rather than implementing them inline.

### 2. Algorithmic & Performance Analysis

#### 2.1. LP Solver Scalability (`core/solvers/lp_solver.py`)
*   **Observation:** The rank preservation constraints generate $O(P^2)$ constraints where $P$ is the number of peers.
    ```python
    for a in range(P):
        for b in range(a + 1, P):
            pair_indices.append((i, j))
    ```
*   **Risk:** [MEDIUM] For small peer groups ($P < 20$), this is negligible. If the tool is used for large benchmarks ($P > 100$), the number of constraints will explode (e.g., 100 peers $\approx$ 5000 rank constraints), potentially slowing down the `highs` solver.
*   **Recommendation:** If scaling to large peer groups is a requirement, consider strictly penalizing only deviation from initial rank *value* rather than relative pairwise ordering, or use a "neighbor-only" rank constraint approach ($O(P)$).

#### 2.2. Heuristic Solver Efficiency (`core/solvers/heuristic_solver.py`)
*   **Observation:** The `objective` function iterates over all unique constraints (`constraint_map.keys()`) in every step of the minimization.
*   **Risk:** [LOW] Python loops are slow. With many dimensions and categories (e.g., time-series data with many months), the number of constraints could be large.
*   **Recommendation:** The current pre-calculation of `constraint_data` is a good optimization. Further optimization would require vectorization using `numpy` for the violation checks instead of Python loops, but this adds complexity. Keep as is unless profiling shows a bottleneck.

### 3. Code Quality & Safety

#### 3.1. Data Loading Robustness (`core/data_loader.py`)
*   **Observation:** `_normalize_columns` uses aggressive regex replacement (`[^a-z0-9_]`).
*   **Risk:** [LOW] It resolves collisions by appending indices, which is safe but might produce non-deterministic column names if input column order varies.
*   **Observation:** Schema validation relies on flexible string matching (e.g., `any(term in col.lower()...)`).
*   **Risk:** [LOW] False positives. A column named "Total Count of Voids" might be matched as `total_count` (valid) but contain irrelevant data. Explicit mapping configuration is safer for production systems.

#### 3.2. Type Safety
*   **Observation:** Good use of `typing` throughout.
*   **Observation:** `linprog` import is wrapped in `try/except` for optional dependency, handled correctly.

#### 3.3. State Management
*   **Observation:** `DimensionalAnalyzer` carries significant state (`self.global_weights`, `self.per_dimension_weights`, `self.last_lp_stats`).
*   **Risk:** [MEDIUM] Debugging "why did it choose these weights?" requires inspecting the state at the right time. The `get_weights_dataframe` method is a good mitigation, exposing this state for reporting.

### 4. Specific Logic Checks

#### 4.1. Privacy Rule "4/35"
*   **Observation:** In `PrivacyValidator.select_rule`, `4/35` is returned for peer counts >= 4. However, the docstring notes "Merchant benchmarking only".
*   **Risk:** [LOW] If this is used for issuer benchmarking, it might be too lenient (or strict depending on context). Ensure `select_rule` context (merchant vs issuer) is propagated correctly. Currently, `merchant_mode` param exists but logic seems to default to peer-count based selection only in some paths.

## Conclusion

The core logic is robust and implements advanced privacy protections. The code quality is high, with recent fixes addressing previous performance concerns (O(N^2) loops). The primary area for improvement is architectural decomposition of `DimensionalAnalyzer` to improve maintainability and testability.

## Recommendations for Next Sprint

1.  **Refactor `DimensionalAnalyzer`**: Extract `CategoryBuilder` and `PrivacyOrchestrator` classes.
2.  **Centralize Privacy Logic**: Move all "checking" and "penalty calculation" logic into `PrivacyValidator` to avoid drift.
3.  **Scalability Test**: Run a benchmark with P=100 and high category count to verify LP solver performance.
