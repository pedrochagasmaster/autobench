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
    values_series = pd.Series(values)
    return float(values_series.mean()), float(values_series.max())


def _build_analyzer_for_preset(
    *,
    preset_name: str,
    consistent_weights: bool,
    entity_col: str,
    target_entity: Optional[str],
    time_col: Optional[str],
    analyzer_factory: Optional[Any],
    logger: logging.Logger,
):
    from utils.config_manager import ConfigManager

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
        return analyzer

    from core.dimensional_analyzer import DimensionalAnalyzer

    linear_programming = opt_config.get("linear_programming", {})
    bounds = opt_config.get("bounds", {})
    constraints = opt_config.get("constraints", {})
    subset_search = opt_config.get("subset_search", {})
    bayesian = opt_config.get("bayesian", {})
    return DimensionalAnalyzer(
        target_entity=target_entity,
        entity_column=entity_col,
        bic_percentile=analysis_config.get("best_in_class_percentile", 0.85),
        debug_mode=False,
        consistent_weights=consistent_weights,
        time_column=time_col,
        tolerance=linear_programming.get("tolerance", 1.0),
        max_weight=bounds.get("max_weight", 10.0),
        min_weight=bounds.get("min_weight", 0.01),
        volume_preservation_strength=constraints.get("volume_preservation", 0.5),
        auto_subset_search=subset_search.get("enabled", True),
        subset_search_max_tests=subset_search.get("max_attempts", 200),
        greedy_subset_search=(subset_search.get("strategy", "greedy") == "greedy"),
        trigger_subset_on_slack=subset_search.get("trigger_on_slack", True),
        max_cap_slack=subset_search.get("max_slack_threshold", 0.0),
        volume_weighted_penalties=linear_programming.get("volume_weighted_penalties", False),
        volume_weighting_exponent=linear_programming.get("volume_weighting_exponent", 1.0),
        merchant_mode=analysis_config.get("merchant_mode", False),
        bayesian_max_iterations=bayesian.get("max_iterations", 500),
        bayesian_learning_rate=bayesian.get("learning_rate", 0.01),
        violation_penalty_weight=bayesian.get("violation_penalty_weight", 1000.0),
        enforce_single_weight_set=constraints.get("enforce_single_weight_set", False),
        enforce_additional_constraints=constraints.get("enforce_additional_constraints", True),
        dynamic_constraints_enabled=constraints.get("dynamic_constraints", {}).get("enabled", True),
        lambda_penalty=linear_programming.get("lambda_penalty"),
        rank_constraint_mode=linear_programming.get("rank_constraints", {}).get("mode", "all"),
        rank_constraint_k=linear_programming.get("rank_constraints", {}).get("neighbor_k", 1),
    )


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
    analyzer_factory: Optional[Any],
    logger: logging.Logger,
) -> Dict[str, Any]:
    analyzer = _build_analyzer_for_preset(
        preset_name=preset_name,
        consistent_weights=consistent_weights,
        entity_col=entity_col,
        target_entity=target_entity,
        time_col=time_col,
        analyzer_factory=analyzer_factory,
        logger=logger,
    )

    optimization_metric = total_col if analysis_type == "rate" and total_col else metric_col
    if consistent_weights:
        analyzer.calculate_global_privacy_weights(df, optimization_metric, dimensions)
    else:
        _, _, peers = analyzer._build_categories(df, optimization_metric, dimensions)
        rule_name, max_concentration = analyzer._get_privacy_rule(len(peers))
        analyzer._solve_per_dimension_weights(
            df,
            optimization_metric,
            dimensions,
            peers,
            max_concentration,
            None,
            rule_name,
        )

    if analysis_type == "rate":
        impact_df = analyzer.calculate_rate_impact(
            df=df,
            total_col=total_col or metric_col,
            numerator_cols=numerator_cols or {},
            dimensions=dimensions,
        )
    else:
        impact_df = analyzer.calculate_share_impact(
            df=df,
            metric_col=metric_col,
            dimensions=dimensions,
            target_entity=target_entity,
        )
    mean_impact, max_impact = _mean_abs_impact(impact_df)
    return {
        "Preset": variant_name,
        "Mode": "global" if consistent_weights else "per_dimension",
        "Mean_Impact_PP": round(mean_impact, 4),
        "Max_Impact_PP": round(max_impact, 4),
        "Status": "ok",
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

    analysis_type = str(kwargs.get("analysis_type", "share"))
    total_col = kwargs.get("total_col")
    numerator_cols = kwargs.get("numerator_cols")
    analyzer_factory = kwargs.get("analyzer_factory")

    if not dimensions:
        return pd.DataFrame(
            columns=["Preset", "Mode", "Mean_Impact_PP", "Max_Impact_PP", "Status"]
        )

    try:
        from utils.preset_manager import PresetManager

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
                try:
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
                            logger=logger,
                        )
                    )
                except Exception as exc:
                    logger.debug("Preset %s variant %s failed: %s", preset_name, variant_name, exc)
                    rows.append(
                        {
                            "Preset": variant_name,
                            "Mode": "global" if consistent_weights else "per_dimension",
                            "Mean_Impact_PP": None,
                            "Max_Impact_PP": None,
                            "Status": f"failed: {exc}",
                        }
                    )

        comparison_df = pd.DataFrame(rows) if rows else None
        if comparison_df is not None and not comparison_df.empty:
            comparison_df["Mean_Distortion_PP"] = comparison_df["Mean_Impact_PP"]
        return comparison_df
    except Exception as exc:
        logger.warning("Preset comparison failed: %s", exc)
        return None
