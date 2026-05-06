"""Preset comparison runner shared between CLI and analysis_run."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


def _mean_abs_impact(results: pd.DataFrame) -> Tuple[float, float]:
    values: List[float] = []
    for column in results.columns:
        if column in {"Impact_PP", "Distortion_PP"} or "Impact" in column or "Distortion" in column:
            numeric = pd.to_numeric(results[column], errors="coerce").dropna().abs()
            values.extend(numeric.tolist())
    if not values:
        return 0.0, 0.0
    series = pd.Series(values, dtype="float64")
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
    analyzer_factory: Any,
    total_col: Optional[str],
    numerator_cols: Optional[Dict[str, str]],
    logger: logging.Logger,
) -> Dict[str, Any]:
    from utils.config_manager import ConfigManager

    try:
        preset_config = ConfigManager(preset=preset_name)
        opt_config = preset_config.config["optimization"]
        analysis_config = preset_config.config["analysis"]
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
        if analysis_type == "rate":
            if not total_col or not numerator_cols:
                raise ValueError("Rate preset comparison requires total_col and numerator_cols")
            if consistent_weights:
                analyzer.calculate_global_privacy_weights(df, total_col, dimensions)
            else:
                _, _, peers = analyzer._build_categories(df, total_col, dimensions)
                rule_name, max_concentration = analyzer._get_privacy_rule(len(peers))
                analyzer._solve_per_dimension_weights(
                    df,
                    total_col,
                    dimensions,
                    peers,
                    max_concentration,
                    None,
                    rule_name,
                )
            impact_df = analyzer.calculate_rate_impact(df, total_col, numerator_cols, dimensions)
        else:
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
            impact_df = analyzer.calculate_share_impact(df, metric_col, dimensions, target_entity)

        mean_impact, max_impact = _mean_abs_impact(impact_df)
        return {
            "Preset": variant_name,
            "Mode": "global" if consistent_weights else "per_dimension",
            "Mean_Impact_PP": round(mean_impact, 4),
            "Max_Impact_PP": round(max_impact, 4),
            "Status": "ok",
        }
    except Exception as exc:
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
        from benchmark import _build_dimensional_analyzer
        from utils.preset_manager import PresetManager

        analysis_type = str(kwargs.get("analysis_type", "share"))
        total_col = kwargs.get("total_col")
        numerator_cols = kwargs.get("numerator_cols")
        analyzer_factory = kwargs.get("analyzer_factory") or _build_dimensional_analyzer

        pm = PresetManager()
        presets = pm.list_presets()
        if not presets:
            logger.warning("No presets found for comparison")
            return None

        rows: List[Dict[str, Any]] = []
        for preset_name in presets:
            for variant_name, consistent_weights in (
                (preset_name, True),
                (f"{preset_name}+perdim", False),
            ):
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
                        analysis_type=analysis_type,
                        analyzer_factory=analyzer_factory,
                        total_col=total_col,
                        numerator_cols=numerator_cols,
                        logger=logger,
                    )
                )

        comparison_df = pd.DataFrame(rows)
        comparison_df["Mean_Distortion_PP"] = comparison_df["Mean_Impact_PP"]
        return comparison_df
    except Exception as exc:
        logger.warning("Preset comparison failed: %s", exc)
        return None
