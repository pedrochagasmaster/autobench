"""Shared constants for core privacy benchmarking logic."""

COMPARISON_EPSILON = 1e-6

# Tiny threshold used to decide whether post-LP nudging is worthwhile.
BORDERLINE_CAP_EXCESS_TOLERANCE_PP = 1e-3

# Numerical floor to avoid no-op floating-point updates.
MIN_WEIGHT_DELTA_EPSILON = 1e-9

# Default penalty multiplier for heuristic constraint violations.
DEFAULT_HEURISTIC_VIOLATION_PENALTY_WEIGHT = 1000.0
