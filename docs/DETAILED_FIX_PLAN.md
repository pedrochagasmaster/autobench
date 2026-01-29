# Code Quality & Refactoring Plan

This document outlines the required fixes to address code quality issues, naming inconsistencies, and performance problems identified in the recent review of the "Impact" terminology migration and "Privacy Control 3.2" implementation.

## 1. Terminology & Naming Standardization ("Distortion" vs "Impact")

**Issue:** The codebase is in a "schizophrenic" state where the new term "Impact" is used in output columns (`Impact_PP`), but legacy terms (`Distortion`, `Weight Effect`) persist in function names, CLI flags, and internal logic wrappers.

**Goal:** Make "Impact" the primary citizen in CLI, API, and internal logic. "Distortion" should exist *only* as a deprecated compatibility layer.

### 1.1. CLI Arguments (`benchmark.py`)
*   **Problem:** The flag `--analyze-distortion` is still the primary trigger, but the help text claims it produces "impact details".
*   **Fix:**
    *   Add `--analyze-impact` as the primary flag.
    *   Keep `--analyze-distortion` as a hidden alias (or marked deprecated in help text) that sets the same config value.
    *   Ensure configuration keys favor `include_impact_summary` over `include_distortion_summary`.

### 1.2. Method Naming (`core/dimensional_analyzer.py`)
*   **Problem:** `calculate_share_distortion` contains the actual implementation (now producing "Impact" columns), while `calculate_share_impact` is a wrapper calling the old name. This is backward.
*   **Fix:**
    *   Rename the implementation method to `calculate_share_impact`.
    *   Change `calculate_share_distortion` to be the wrapper that calls `calculate_share_impact`.
    *   Apply the same fix to `calculate_rate_impact` (implementation) vs `calculate_rate_weight_effect` (wrapper).

### 1.3. Logic Duplication
*   **Problem:** Wrappers are used, but the column names returned might differ (`_Distortion_PP` vs `_Impact_PP`) if the implementation was just renamed without handling legacy column names.
*   **Fix:**
    *   The "Impact" implementation should return `Impact_PP`.
    *   If strict backward compatibility is needed for scripts consuming the dataframe, the `distortion` wrapper should rename columns (`Impact_PP` -> `Distortion_PP`) before returning. If not, simple aliasing is fine.

## 2. Optimization Loop Performance & Correctness (`core/dimensional_analyzer.py`)

**Issue:** The `_additional_constraints_penalty` function, which runs inside the hot optimization loop (invoked hundreds/thousands of times per dimension), performs static checks and redundant operations.

### 2.1. Static Checks inside Loop
*   **Problem:** `min_entities` check depends only on the peer group size, which is constant during optimization. It is checked on every iteration.
*   **Fix:** Move the `min_entities` check to `_solve_dimension_weights_heuristic` *before* defining or calling the `objective` function. If the group is too small, fail fast or apply a static penalty without the loop.

### 2.2. Redundant Type Casting
*   **Problem:** `sorted([float(s) for s in shares], reverse=True)`. The `shares` list is constructed from floats in the lines immediately preceding this. The list comprehension and casting are wasted cycles.
*   **Fix:** Sort `shares` directly: `shares.sort(reverse=True)`.

### 2.3. Magic Numbers
*   **Problem:** The objective function uses a hardcoded multiplier: `violation_penalty * 100.0`.
*   **Fix:** Define `VIOLATION_PENALTY_WEIGHT = 100.0` as a class constant or method parameter to make this heuristic explicit and tunable.

## 3. CSV Validator Cleanliness (`utils/csv_validator.py`)

**Issue:** Inconsistent output markers.
*   **Fix:** The change from "✓" to "OK" / "PASS" is good for Windows CLI compatibility. Ensure this pattern is consistent across all print statements.

## 4. Execution Plan

### Step 1: Core Logic Refactor (`core/dimensional_analyzer.py`)
1.  Define `VIOLATION_PENALTY_WEIGHT`.
2.  Refactor `_solve_dimension_weights_heuristic`:
    *   Perform `min_entities` check before inner function.
    *   Optimize `_additional_constraints_penalty` (remove casts).
3.  Rename methods:
    *   `calculate_share_distortion` -> `calculate_share_impact` (main logic).
    *   `calculate_rate_weight_effect` -> `calculate_rate_impact` (main logic).
4.  Re-add legacy methods as wrappers:
    *   `calculate_share_distortion` -> calls `calculate_share_impact`.
    *   `calculate_rate_weight_effect` -> calls `calculate_rate_impact`.

### Step 2: CLI & Config Update (`benchmark.py`, `utils/config_manager.py`)
1.  Update `benchmark.py`:
    *   Add `--analyze-impact` argument.
    *   Map both `--analyze-impact` and `--analyze-distortion` to `include_impact_summary` in config overrides.
2.  Update `utils/config_manager.py`:
    *   Ensure internal config keys use `impact` terminology.
    *   Maintain legacy mapping for `distortion` keys if loaded from old config files.

### Step 3: Verification
1.  Run `tests/test_enhanced_features.py` to ensure math and wrappers work.
2.  Run a CLI sweep (e.g., `py benchmark.py share ... --analyze-impact`) and verify "Impact Analysis" sheets appear.
3.  Run with legacy flag `--analyze-distortion` and verify it still works (producing Impact sheets is acceptable/preferred).
