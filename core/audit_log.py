"""Audit log model construction for analysis outputs."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

import pandas as pd


def _compact_audit_value(value: Any) -> Any:
    if hasattr(value, "shape") and hasattr(value, "columns"):
        return f"DataFrame rows={value.shape[0]} cols={value.shape[1]}"
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return f"List[Dict] entries={len(value)} keys={sorted(value[0].keys())}"
    return value


def compact_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: _compact_audit_value(value)
        for key, value in metadata.items()
    }


def build_audit_log_model(
    *,
    metadata: Dict[str, Any],
    report_paths: Iterable[str],
    dimensions_analyzed: int,
    csv_output: Optional[str] = None,
    impact_df: Optional[pd.DataFrame] = None,
    privacy_validation_df: Optional[pd.DataFrame] = None,
    validation_summary: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    impact_summary = metadata.get("impact_summary", {}) if isinstance(metadata, dict) else {}
    results_summary = {
        "dimensions_analyzed": dimensions_analyzed,
        "categories_analyzed": len(impact_df) if impact_df is not None else None,
        "impact_mean_abs_pp": impact_summary.get("mean_abs_impact_pp"),
        "privacy_rule": metadata.get("privacy_rule"),
        "additional_constraint_violations_count": metadata.get("additional_constraint_violations_count"),
        "privacy_validation_rows": len(privacy_validation_df) if privacy_validation_df is not None else 0,
        "outputs": list(report_paths),
        "balanced_csv": csv_output,
    }
    if validation_summary:
        results_summary.update(validation_summary)
    return {
        "metadata": compact_metadata(metadata),
        "results_summary": results_summary,
    }
