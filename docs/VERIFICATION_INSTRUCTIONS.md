# Verification Instructions

This document provides instructions for verifying the "Impact" terminology refactor and performance optimizations.

## 1. Unit Tests

Run the full test suite, including the new legacy wrapper tests:

```powershell
py -m pytest tests/test_enhanced_features.py tests/test_legacy_wrappers.py
```

**Expected Result:** All tests passed.

## 2. CLI Flag Verification

### 2.1. New Flag (`--analyze-impact`)

Run a share analysis using the new flag:

```powershell
py benchmark.py share --csv data/test.csv --entity "Target" --metric txn_cnt --dimensions dim1 --analyze-impact
```

**Expected Result:**
*   Output log should mention "Computing Impact Analysis".
*   Analysis Excel file should contain a sheet named "Impact Analysis".
*   Columns should be named `Impact_PP`.

### 2.2. Legacy Flag (`--analyze-distortion`)

Run a share analysis using the deprecated flag:

```powershell
py benchmark.py share --csv data/test.csv --entity "Target" --metric txn_cnt --dimensions dim1 --analyze-distortion
```

**Expected Result:**
*   It should run successfully (aliased to impact analysis).
*   Output log/sheets will likely use the new "Impact" terminology (this is intended behavior).

## 3. Performance Check (Optimization Loop)

For a large dataset (or many dimensions), the optimization phase should be slightly faster or neutral compared to before. The key correctness check is that `PrivacyValidator` logic is still applied.

*   Run with `log_level: DEBUG` in config or CLI (`--log-level DEBUG`).
*   Verify logs do **not** show hundreds of "sorting..." or casting operations if you profile it, but functionally, ensure "Global weights validation" log block appears and shows `[OK]` or `[VIOLATION]`.

## 4. API Backward Compatibility

Scripts using `DimensionalAnalyzer` directly (e.g., custom notebooks) calling `calculate_share_distortion` should still work but receive a deprecation warning in the logs.

```python
from core.dimensional_analyzer import DimensionalAnalyzer
# ... setup ...
df = analyzer.calculate_share_distortion(...)
# Check df['Distortion_PP'] exists
```
