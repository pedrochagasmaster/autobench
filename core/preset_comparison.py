"""Preset comparison runner shared between CLI and analysis_run."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

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
    **kwargs: Any,
) -> Optional[pd.DataFrame]:
    """Run analysis across all presets and return a comparison DataFrame."""
    if logger is None:
        logger = logging.getLogger(__name__)

    if not dimensions:
        return pd.DataFrame(columns=["Preset", "Mode", "Mean_Impact_PP", "Max_Impact_PP", "Status", "Mean_Distortion_PP"])

    try:
        from utils.preset_manager import PresetManager
        from utils.config_manager import ConfigManager
        from core.analysis_run import build_dimensional_analyzer

        pm = PresetManager()
        presets = pm.list_presets()
        if not presets:
            logger.warning("No presets found for comparison")
            return None

        def _mean_abs_impact(results: Dict[str, pd.DataFrame]) -> tuple[float, float]:
            values: List[float] = []
            for result_df in results.values():
                for column in result_df.columns:
                    if column in {"Impact_PP", "Distortion_PP"} or "Impact" in column or "Distortion" in column:
                        numeric = pd.to_numeric(result_df[column], errors="coerce").dropna().abs()
                        values.extend(numeric.tolist())
            if not values:
                return 0.0, 0.0
            series = pd.Series(values, dtype=float)
            return float(series.mean()), float(series.max())

        rows: List[Dict[str, Any]] = []
        for preset_name in presets:
            for variant_name, consistent_weights in ((preset_name, True), (f"{preset_name}+perdim", False)):
                try:
                    preset_config = ConfigManager(preset=preset_name)
                    opt_config = preset_config.config["optimization"]
                    analysis_config = preset_config.config["analysis"]
                    analyzer, _settings = build_dimensional_analyzer(
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

                    results = {
                        dimension: analyzer.analyze_dimension_share(df=df, dimension_column=dimension, metric_col=metric_col)
                        for dimension in dimensions
                    }
                    mean_impact, max_impact = _mean_abs_impact(results)
                    rows.append(
                        {
                            "Preset": variant_name,
                            "Mode": "global" if consistent_weights else "per_dimension",
                            "Mean_Impact_PP": round(mean_impact, 4),
                            "Max_Impact_PP": round(max_impact, 4),
                            "Status": "ok",
                        }
                    )
                except Exception as exc:
                    logger.debug("Preset %s failed: %s", variant_name, exc)
                    rows.append(
                        {
                            "Preset": variant_name,
                            "Mode": "global" if consistent_weights else "per_dimension",
                            "Mean_Impact_PP": None,
                            "Max_Impact_PP": None,
                            "Status": f"failed: {exc}",
                        }
                    )

        if not rows:
            return None
        comparison_df = pd.DataFrame(rows)
        comparison_df["Mean_Distortion_PP"] = comparison_df["Mean_Impact_PP"]
        return comparison_df
    except Exception as exc:
        logger.warning("Preset comparison failed: %s", exc)
        return None
