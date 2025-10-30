# File Recovery and Bug Fix Summary

**Date**: October 30, 2025

## Problem Identified

The user reported that "the peer unweighted average is the same for almost all dimensions" when using `--consistent-weights` mode. Investigation showed all unweighted averages were 16.67% (100% / 6 peers) regardless of dimension or category.

## Root Cause

When `--consistent-weights` was enabled:
1. The improved `calculate_global_privacy_weights()` method (with iterative algorithm and parameters) was missing from `dimensional_analyzer.py`
2. Each dimension analysis was calling the deprecated `calculate_global_weights()` which overwrote the global weights with simple volume-based calculations
3. This caused the weighted balanced average calculation to behave incorrectly, and as a side effect, the unweighted averages appeared constant

## Files Recovered/Fixed

### 1. `core/dimensional_analyzer.py`
**Added:**
- **New `__init__` parameters**:
  - `max_iterations` (default: 1000)
  - `tolerance` (default: 1.0%)
  - `max_weight` (default: 10.0x)
  - `min_weight` (default: 0.01x)
  - `volume_preservation_strength` (default: 0.5)

- **`calculate_global_privacy_weights()` method**: Improved iterative weight algorithm that:
  - Checks privacy constraints across ALL dimension/category combinations
  - Uses adaptive step size with stagnation detection
  - Implements three-phase approach:
    1. Reduce violators gradually
    2. Boost compliant peers (first 60% of iterations)
    3. Apply partial volume preservation
  - Enforces min/max weight limits after rescaling
  - Converges to satisfy privacy rules globally

**Fixed:**
- Removed deprecated `calculate_global_weights()` calls from `analyze_dimension_share()` and `analyze_dimension_rate()`
- Added deprecation warning to old `calculate_global_weights()` method
- Global weights now calculated once in `benchmark.py` before dimension loop

### 2. `benchmark.py`
**Already had** (confirmed working):
- CLI arguments for all weight parameters
- Calls to `analyzer.calculate_global_privacy_weights()` before dimension analysis loop
- Proper parameter passing to `DimensionalAnalyzer.__init__()`

## Test Results

### Before Fix (with consistent_weights):
```
tipo_compra:
  A Vista:    Peer_Unweighted_Avg_% = 16.67%
  Parcelado:  Peer_Unweighted_Avg_% = 16.67%

flg_recurring:
  0: Peer_Unweighted_Avg_% = 16.67%
  1: Peer_Unweighted_Avg_% = 16.67%
```

### After Fix (with consistent_weights):
```
tipo_compra:
  A Vista:    Peer_Unweighted_Avg_% = 81.97%
  Parcelado:  Peer_Unweighted_Avg_% = 18.03%

flg_recurring:
  0: Peer_Unweighted_Avg_% = 81.14%
  1: Peer_Unweighted_Avg_% = 18.86%
```

## Command Line Usage

Full command with all parameters:
```powershell
py benchmark.py share `
  --csv "data/e176097_nubank_pj_peer_cube_digital.csv" `
  --entity "NU PAGAMENTOS SA" `
  --metric transaction_amount `
  --dimensions tipo_compra flg_recurring flag_domestic cp_cnp `
  --entity-col entity_identifier `
  --bic-percentile 0.85 `
  --consistent-weights `
  --debug `
  --max-iterations 1000 `
  --tolerance 1.0 `
  --max-weight 10.0 `
  --min-weight 0.01 `
  --volume-preservation 0.5 `
  --output my_analysis.xlsx
```

## Files Backed Up

- `core/dimensional_analyzer_backup_20251030_110237.py` - Original version before recovery

## Status

✅ **FIXED**: Unweighted averages now correctly vary by dimension and category
✅ **RECOVERED**: All weight algorithm parameters functional
✅ **TESTED**: Confirmed working with multiple dimension combinations
