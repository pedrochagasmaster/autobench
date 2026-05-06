"""Preset comparison runner shared between CLI and analysis_run."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from utils.config_manager import ConfigManager

logger = logging.getLogger(__name__)


def _mean_abs_impact(results: Dict[str, pd.DataFrame]) -> Tuple[float, float]:
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
    series = pd.Series(values)
    return float(series.mean()), float(series.max())


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
    analysis_type: str,
    logger: logging.Logger,
    analyzer_factory: Any = None,
    total_col: Optional[str] = None,
    numerator_cols: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    try:
        preset_config = ConfigManager(preset=preset_name)
        opt_config = preset_config.config["optimization"]
        analysis_config = preset_config.config["analysis"]

        if analyzer_factory is not None:
            analyzer, _ = analyzer_factory(
                target_entity=target_entity,
                entity_col=entity_col,
                analysis_config=analysis_config,
                opt_config=opt_config,
                time_col=time_col,
                debug_mode=False,
                bic_percentile=analysis_config.get("best_in_class_percentile", 0.85),
                logger=logger,
                consistent_weights=consistent_weights,
            )
        else:
            from core.dimensional_analyzer import DimensionalAnalyzer

            analyzer = DimensionalAnalyzer(
                target_entity=target_entity,
                entity_column=entity_col,
                time_column=time_col,
                consistent_weights=consistent_weights,
                tolerance=opt_config.get("linear_programming", {}).get("tolerance", 1.0),
                max_weight=opt_config.get("bounds", {}).get("max_weight", 10.0),
                min_weight=opt_config.get("bounds", {}).get("min_weight", 0.01),
            )

        if consistent_weights:
            analyzer.calculate_global_privacy_weights(df, metric_col, dimensions)
        else:
            _, _, peers = analyzer._build_categories(df, metric_col, dimensions)
            rule_name, max_concentration = analyzer._get_privacy_rule(len(peers))
            analyzer._solve_per_dimension_weights(
                df,
                metric_col,
                dimensions,
                peers,
                max_concentration,
                None,
                rule_name,
            )

        results: Dict[str, pd.DataFrame] = {}
        if analysis_type == "rate":
            numerators = numerator_cols or {}
            for rate_name, numerator_col in numerators.items():
                for dim in dimensions:
                    results[f"{rate_name}_{dim}"] = analyzer.analyze_dimension_rate(
                        df=df,
                        dimension_column=dim,
                        total_col=total_col or metric_col,
                        numerator_col=numerator_col,
                    )
        else:
            for dim in dimensions:
                results[dim] = analyzer.analyze_dimension_share(df=df, dimension_column=dim, metric_col=metric_col)

        mean_impact, max_impact = _mean_abs_impact(results)
        return {
            "Preset": variant_name,
            "Mode": "global" if consistent_weights else "per_dimension",
            "Mean_Impact_PP": round(mean_impact, 4),
            "Max_Impact_PP": round(max_impact, 4),
            "Status": "ok",
        }
    except Exception as exc:
        logger.debug("Preset variant %s failed: %s", variant_name, exc)
        return {
            "Preset": variant_name,
            "Mode": "global" if consistent_weights else "per_dimension",
            "Mean_Impact_PP": None,
            "Max_Impact_PP": None,
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
        return pd.DataFrame(columns=["Preset", "Mode", "Mean_Impact_PP", "Max_Impact_PP", "Status", "Mean_Distortion_PP"])

    try:
        from utils.preset_manager import PresetManager

        pm = PresetManager()
        presets = pm.list_presets()
        if not presets:
            logger.warning("No presets found for comparison")
            return None

        rows: List[Dict[str, Any]] = []
        for preset_name in presets:
            for variant_name, consistent_weights in [(preset_name, True), (f"{preset_name}+perdim", False)]:
                rows.append(
                    _run_single_preset_variant(
                        preset_name=preset_name,
                        variant_name=variant_name,
                        consistent_weights=consistent_weights,
                        df=df,
                        metric_col=metric_col,
                        dimensions=dimensions,
                        entity_col=entity_col,
                        target_entity=target_entity,
                        time_col=time_col,
                        analysis_type=kwargs.get("analysis_type", kwargs.get("mode", "share")),
                        logger=logger,
                        analyzer_factory=kwargs.get("analyzer_factory"),
                        total_col=kwargs.get("total_col"),
                        numerator_cols=kwargs.get("numerator_cols"),
                    )
                )

        comparison_df = pd.DataFrame(rows)
        if not comparison_df.empty:
            comparison_df["Mean_Distortion_PP"] = comparison_df["Mean_Impact_PP"]
        return comparison_df if rows else None
    except Exception as exc:
        logger.warning("Preset comparison failed: %s", exc)
        return None
