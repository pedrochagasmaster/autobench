"""Compute representativeness warnings from analysis metadata."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

import pandas as pd

MULTIPLIER_RATIO_WARN = 20.0
MEAN_ABS_IMPACT_WARN_PP = 10.0
MIN_WEIGHT_FLOOR_EPS = 1e-3


def _extract_multipliers(metadata: Dict[str, Any]) -> List[float]:
    multipliers: List[float] = []
    for key in ("weights_df", "method_breakdown_df"):
        frame = metadata.get(key)
        if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
            continue
        if "Multiplier" not in frame.columns:
            continue
        values = pd.to_numeric(frame["Multiplier"], errors="coerce").dropna()
        multipliers.extend(float(value) for value in values if float(value) > 0)
    return multipliers


def _count_peers_at_min_floor(metadata: Dict[str, Any]) -> int:
    min_weight = metadata.get("min_weight")
    if min_weight is None or not isinstance(min_weight, (int, float)):
        return 0

    floor = float(min_weight)
    peers_at_floor: Set[str] = set()
    for key in ("weights_df", "method_breakdown_df"):
        frame = metadata.get(key)
        if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
            continue
        if "Multiplier" not in frame.columns or "Peer" not in frame.columns:
            continue
        for _, row in frame.iterrows():
            multiplier = pd.to_numeric(row.get("Multiplier"), errors="coerce")
            if pd.isna(multiplier):
                continue
            if float(multiplier) <= floor + MIN_WEIGHT_FLOOR_EPS:
                peers_at_floor.add(str(row["Peer"]))
    return len(peers_at_floor)


def compute_representativeness(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Derive representativeness metrics and human-readable warnings from metadata."""
    multipliers = _extract_multipliers(metadata)
    if multipliers:
        multiplier_min = min(multipliers)
        multiplier_max = max(multipliers)
        multiplier_ratio = multiplier_max / multiplier_min if multiplier_min > 0 else 0.0
    else:
        multiplier_min = 0.0
        multiplier_max = 0.0
        multiplier_ratio = 0.0

    peers_at_min_floor = _count_peers_at_min_floor(metadata)

    mean_abs_impact_pp: Optional[float] = None
    impact_summary = metadata.get("impact_summary")
    if isinstance(impact_summary, dict):
        raw = impact_summary.get("mean_abs_impact_pp")
        if isinstance(raw, (int, float)):
            mean_abs_impact_pp = float(raw)

    warnings: List[str] = []
    if multiplier_ratio > MULTIPLIER_RATIO_WARN:
        warnings.append(
            f"Peer weight ratio max/min is {multiplier_ratio:.0f}x — "
            "balanced averages may not represent the raw peer market"
        )
    if peers_at_min_floor > 0:
        warnings.append(f"{peers_at_min_floor} peer(s) forced to the minimum weight floor")
    if mean_abs_impact_pp is not None and mean_abs_impact_pp > MEAN_ABS_IMPACT_WARN_PP:
        warnings.append(f"Mean absolute impact of weighting is {mean_abs_impact_pp:.1f}pp")

    return {
        "multiplier_min": multiplier_min,
        "multiplier_max": multiplier_max,
        "multiplier_ratio": multiplier_ratio,
        "peers_at_min_floor": peers_at_min_floor,
        "mean_abs_impact_pp": mean_abs_impact_pp,
        "warnings": warnings,
    }
