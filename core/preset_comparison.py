"""Preset comparison runner shared between CLI and analysis_run."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


def _mean_abs_impact(results: Dict[str, Any]) -> tuple:
    """Compute mean and max absolute impact from analysis results."""
    values: List[float] = []
    for result_df in results.values():
        if not isinstance(result_df, pd.DataFrame):
            continue
        for column in result_df.columns:
            if column in {"Impact_PP", "Distortion_PP"} or "Impact" in column or "Distortion" in column:
                numeric = pd.to_numeric(result_df[column], errors="coerce").dropna().abs()
                values.extend(numeric.tolist())
    if not values:
        return 0.0, 0.0
    return float(pd.Series(values).mean()), float(pd.Series(values).max())


def _run_single_preset_variant(
    *,
    preset_name: str,
    variant_name: str,
    consistent_weights: bool,
    df: pd.DataFrame,
    metric_col: str,
    dimensions: List[str],
    entity_col: str,
    target_entity: Optional[str],
    time_col: Optional[str],
) -> Dict[str, Any]:
    """Run a single preset variant and return a result row."""
    try:
        from utils.config_manager import ConfigManager
        from core.dimensional_analyzer import DimensionalAnalyzer

        preset_config = ConfigManager(preset=preset_name)
        opt_config = preset_config.config.get("optimization", {})
        lp = opt_config.get("linear_programming", {})
        bounds = opt_config.get("bounds", {})

        analyzer = DimensionalAnalyzer(
            target_entity=target_entity,
            entity_column=entity_col,
            consistent_weights=consistent_weights,
            tolerance=lp.get("tolerance", 1.0),
            max_weight=bounds.get("max_weight", 10.0),
            min_weight=bounds.get("min_weight", 0.01),
            time_column=time_col,
        )
        analyzer.calculate_global_privacy_weights(df, metric_col, dimensions)

        if target_entity:
            results = analyzer.calculate_share_impact(df, metric_col, dimensions)
        else:
            results = {}

        mean_impact, max_impact = _mean_abs_impact(results)

        return {
            "Preset": variant_name,
            "Mode": "global" if consistent_weights else "per_dimension",
            "Mean_Impact_PP": round(mean_impact, 4),
            "Max_Impact_PP": round(max_impact, 4),
            "Mean_Distortion_PP": round(mean_impact, 4),
            "Status": "ok",
        }
    except Exception as exc:
        return {
            "Preset": variant_name,
            "Mode": "global" if consistent_weights else "per_dimension",
            "Mean_Impact_PP": None,
            "Max_Impact_PP": None,
            "Mean_Distortion_PP": None,
            "Status": f"failed: {exc}",
        }


def run_preset_comparison(
    df: pd.DataFrame,
    metric_col: str,
    dimensions: List[str],
    entity_col: str,
    target_entity: Optional[str],
    time_col: Optional[str] = None,
    config: Any = None,
    logger: Optional[logging.Logger] = None,
    **kwargs: Any,
) -> Optional[pd.DataFrame]:
    """Run analysis across all presets and return a comparison DataFrame."""
    if logger is None:
        logger = logging.getLogger(__name__)

    if not dimensions:
        return pd.DataFrame(columns=["Preset", "Mode", "Mean_Impact_PP", "Max_Impact_PP", "Mean_Distortion_PP", "Status"])

    try:
        from utils.preset_manager import PresetManager

        pm = PresetManager()
        presets = pm.list_presets()
        if not presets:
            logger.warning("No presets found for comparison")
            return None

        rows: List[Dict[str, Any]] = []
        for preset_name in presets:
            for variant_name, cw in [(preset_name, True), (f"{preset_name}+perdim", False)]:
                rows.append(
                    _run_single_preset_variant(
                        preset_name=preset_name,
                        variant_name=variant_name,
                        consistent_weights=cw,
                        df=df,
                        metric_col=metric_col,
                        dimensions=dimensions,
                        entity_col=entity_col,
                        target_entity=target_entity,
                        time_col=time_col,
                    )
                )

        return pd.DataFrame(rows) if rows else None
    except Exception as exc:
        logger.warning("Preset comparison failed: %s", exc)
        return None
