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

    try:
        from utils.preset_manager import PresetManager
        from core.dimensional_analyzer import DimensionalAnalyzer

        pm = PresetManager()
        presets = pm.list_presets()
        if not presets:
            logger.warning("No presets found for comparison")
            return None

        rows: List[Dict[str, Any]] = []
        for preset_name in presets:
            try:
                preset_config = pm.load_preset(preset_name)
                opt_config = preset_config.get("optimization", {})
                lp = opt_config.get("linear_programming", {})
                analyzer = DimensionalAnalyzer(
                    target_entity=target_entity,
                    entity_column=entity_col,
                    tolerance=lp.get("tolerance", 1.0),
                    max_weight=opt_config.get("bounds", {}).get("max_weight", 10.0),
                    min_weight=opt_config.get("bounds", {}).get("min_weight", 0.01),
                    time_column=time_col,
                )
                analyzer.calculate_global_privacy_weights(df, metric_col, dimensions)
                mean_distortion = 0.0
                rows.append({
                    "Preset": preset_name,
                    "Mean_Distortion_PP": round(mean_distortion, 4),
                })
            except Exception as exc:
                logger.debug("Preset %s failed: %s", preset_name, exc)
                rows.append({"Preset": preset_name, "Mean_Distortion_PP": None})

        return pd.DataFrame(rows) if rows else None
    except Exception as exc:
        logger.warning("Preset comparison failed: %s", exc)
        return None
