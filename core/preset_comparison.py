"""Preset comparison runner shared between CLI and analysis_run."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


def _mean_max_abs_impact(results: Dict[str, pd.DataFrame]) -> Tuple[float, float]:
    """Compute mean and max of absolute impact / distortion values across results."""
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
    total_col: Optional[str],
    numerator_cols: Optional[Dict[str, str]],
    analyzer_factory: Optional[Callable[..., Tuple[Any, Dict[str, Any]]]],
    inner_logger: logging.Logger,
) -> Dict[str, Any]:
    """Execute one preset variant and return a comparison row."""
    mode = "global" if consistent_weights else "per_dimension"
    try:
        from utils.config_manager import ConfigManager
        from core.dimensional_analyzer import DimensionalAnalyzer

        preset_config = ConfigManager(preset=preset_name)
        opt_config = preset_config.config["optimization"]
        analysis_config = preset_config.config.get("analysis", {})
        bic_percentile = analysis_config.get("best_in_class_percentile", 0.85)

        if analyzer_factory is not None:
            analyzer, _ = analyzer_factory(
                target_entity=target_entity,
                entity_col=entity_col,
                analysis_config=analysis_config,
                opt_config=opt_config,
                time_col=time_col,
                debug_mode=False,
                bic_percentile=bic_percentile,
                logger=inner_logger,
                consistent_weights=consistent_weights,
            )
        else:
            lp = opt_config.get("linear_programming", {})
            bounds = opt_config.get("bounds", {})
            analyzer = DimensionalAnalyzer(
                target_entity=target_entity,
                entity_column=entity_col,
                bic_percentile=bic_percentile,
                consistent_weights=consistent_weights,
                tolerance=lp.get("tolerance", 1.0),
                max_iterations=lp.get("max_iterations", 1000),
                max_weight=bounds.get("max_weight", 10.0),
                min_weight=bounds.get("min_weight", 0.01),
                time_column=time_col,
            )

        analysis_metric = metric_col if analysis_type == "share" else (total_col or metric_col)
        if consistent_weights:
            analyzer.calculate_global_privacy_weights(df, analysis_metric, dimensions)
        else:
            _, _, peers = analyzer._build_categories(df, analysis_metric, dimensions)
            rule_name, max_concentration = analyzer._get_privacy_rule(len(peers))
            analyzer._solve_per_dimension_weights(
                df,
                analysis_metric,
                dimensions,
                peers,
                max_concentration,
                None,
                rule_name,
            )

        results: Dict[str, pd.DataFrame] = {}
        if analysis_type == "share":
            if target_entity:
                impact_df = analyzer.calculate_share_impact(df, metric_col, dimensions, target_entity)
                if impact_df is not None and not impact_df.empty:
                    results["impact"] = impact_df
            if not results:
                for dim in dimensions:
                    res = analyzer.analyze_dimension_share(df=df, dimension_column=dim, metric_col=metric_col)
                    if isinstance(res, pd.DataFrame) and not res.empty:
                        results[dim] = res
        else:
            if numerator_cols:
                impact_df = analyzer.calculate_rate_impact(df, total_col, numerator_cols, dimensions)
                if impact_df is not None and not impact_df.empty:
                    results["rate_impact"] = impact_df

        mean_impact, max_impact = _mean_max_abs_impact(results)
        return {
            "Preset": variant_name,
            "Mode": mode,
            "Mean_Impact_PP": round(mean_impact, 4),
            "Max_Impact_PP": round(max_impact, 4),
            "Status": "ok",
        }
    except Exception as exc:
        inner_logger.debug("Preset variant %s failed: %s", variant_name, exc, exc_info=True)
        return {
            "Preset": variant_name,
            "Mode": mode,
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
    analysis_type: str = "share",
    analyzer_factory: Optional[Callable[..., Tuple[Any, Dict[str, Any]]]] = None,
    total_col: Optional[str] = None,
    numerator_cols: Optional[Dict[str, str]] = None,
    **kwargs: Any,
) -> Optional[pd.DataFrame]:
    """Run analysis across all presets and return a comparison DataFrame.

    Empty dimensions short-circuit to an empty DataFrame so callers can render an empty
    sheet without raising.
    """
    inner_logger = logger or logging.getLogger(__name__)

    if not dimensions:
        return pd.DataFrame(
            columns=["Preset", "Mode", "Mean_Impact_PP", "Max_Impact_PP", "Status", "Mean_Distortion_PP"]
        )

    try:
        from utils.preset_manager import PresetManager

        pm = PresetManager()
        presets = pm.list_presets()
        if not presets:
            inner_logger.warning("No presets found for comparison")
            return None

        rows: List[Dict[str, Any]] = []
        for preset_name in presets:
            for variant_name, consistent_weights in [
                (preset_name, True),
                (f"{preset_name}+perdim", False),
            ]:
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
                        total_col=total_col,
                        numerator_cols=numerator_cols,
                        analyzer_factory=analyzer_factory,
                        inner_logger=inner_logger,
                    )
                )

        if not rows:
            return None
        comparison_df = pd.DataFrame(rows)
        comparison_df["Mean_Distortion_PP"] = comparison_df["Mean_Impact_PP"]
        return comparison_df
    except Exception as exc:
        inner_logger.warning("Preset comparison failed: %s", exc)
        return None
