"""Preset comparison runner shared between CLI and analysis_run."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


def run_preset_comparison(
    df: pd.DataFrame,
    metric_col: str,
    dimensions: List[str],
    entity_col: str,
    target_entity: Optional[str],
    time_col: Optional[str] = None,
    config: Any = None,
    logger: Optional[logging.Logger] = None,
    analyzer_factory: Optional[Callable] = None,
    **kwargs: Any,
) -> Optional[pd.DataFrame]:
    """Run analysis across all presets and return a comparison DataFrame."""
    if logger is None:
        logger = logging.getLogger(__name__)

    if not dimensions:
        return pd.DataFrame(columns=["Preset", "Mode", "Mean_Impact_PP", "Max_Impact_PP", "Mean_Distortion_PP", "Status"])

    try:
        from utils.preset_manager import PresetManager
        from utils.config_manager import ConfigManager
        from core.dimensional_analyzer import DimensionalAnalyzer

        pm = PresetManager()
        presets = pm.list_presets()
        if not presets:
            logger.warning("No presets found for comparison")
            return None

        rows: List[Dict[str, Any]] = []
        for preset_name in presets:
            for variant_name, consistent_weights in [(preset_name, True), (f"{preset_name}+perdim", False)]:
                row = _run_single_preset_variant(
                    preset_name=preset_name,
                    variant_name=variant_name,
                    consistent_weights=consistent_weights,
                    df=df,
                    metric_col=metric_col,
                    dimensions=dimensions,
                    entity_col=entity_col,
                    target_entity=target_entity,
                    time_col=time_col,
                    analyzer_factory=analyzer_factory,
                    logger=logger,
                )
                rows.append(row)

        if not rows:
            return None

        comparison_df = pd.DataFrame(rows)
        comparison_df["Mean_Distortion_PP"] = comparison_df["Mean_Impact_PP"]
        return comparison_df
    except Exception as exc:
        logger.warning("Preset comparison failed: %s", exc)
        return None


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
    analyzer_factory: Optional[Callable],
    logger: logging.Logger,
) -> Dict[str, Any]:
    """Run a single preset variant and return a result row."""
    mode = "global" if consistent_weights else "per_dimension"
    try:
        from utils.config_manager import ConfigManager
        from core.dimensional_analyzer import DimensionalAnalyzer

        preset_config = ConfigManager(preset=preset_name)
        opt_config = preset_config.config["optimization"]
        lp = opt_config.get("linear_programming", {})

        analyzer = DimensionalAnalyzer(
            target_entity=target_entity,
            entity_column=entity_col,
            tolerance=lp.get("tolerance", 1.0),
            max_weight=opt_config.get("bounds", {}).get("max_weight", 10.0),
            min_weight=opt_config.get("bounds", {}).get("min_weight", 0.01),
            time_column=time_col,
            consistent_weights=consistent_weights,
            volume_weighted_penalties=lp.get("volume_weighted_penalties", False),
            volume_weighting_exponent=lp.get("volume_weighting_exponent", 1.0),
        )

        if consistent_weights:
            analyzer.calculate_global_privacy_weights(df, metric_col, dimensions)
        else:
            _, _, peers = analyzer._build_categories(df, metric_col, dimensions)
            rule_name, max_concentration = analyzer._get_privacy_rule(len(peers))
            analyzer._solve_per_dimension_weights(
                df, metric_col, dimensions, peers, max_concentration, None, rule_name,
            )

        results: Dict[str, Any] = {}
        for dim in dimensions:
            result_df = analyzer.analyze_dimension_share(df=df, dimension_column=dim, metric_col=metric_col)
            results[dim] = result_df

        mean_impact, max_impact = _mean_abs_impact(results)

        return {
            "Preset": variant_name,
            "Mode": mode,
            "Mean_Impact_PP": round(mean_impact, 4),
            "Max_Impact_PP": round(max_impact, 4),
            "Status": "ok",
        }
    except Exception as exc:
        logger.debug("Preset %s (%s) failed: %s", preset_name, mode, exc)
        return {
            "Preset": variant_name,
            "Mode": mode,
            "Mean_Impact_PP": None,
            "Max_Impact_PP": None,
            "Status": f"failed: {exc}",
        }


def _mean_abs_impact(results: Dict[str, Any]) -> tuple:
    """Compute mean and max absolute impact from analysis results."""
    values: List[float] = []
    for result_df in results.values():
        if not isinstance(result_df, pd.DataFrame):
            continue
        for column in result_df.columns:
            if "Impact" in column or "Distortion" in column:
                numeric = pd.to_numeric(result_df[column], errors="coerce").dropna().abs()
                values.extend(numeric.tolist())
    if not values:
        return 0.0, 0.0
    return float(pd.Series(values).mean()), float(pd.Series(values).max())
