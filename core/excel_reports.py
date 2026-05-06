"""Excel report generation helpers shared across CLI and analysis_run."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import pandas as pd

from .report_generator import ReportGenerator

logger = logging.getLogger(__name__)


def _save_workbook_with_retries(
    wb: Any,
    output_file: str,
    logger: logging.Logger,
    max_attempts: int = 3,
) -> None:
    for attempt in range(1, max_attempts + 1):
        try:
            wb.save(output_file)
            return
        except PermissionError:
            if attempt < max_attempts:
                logger.warning(
                    "File %s is locked, retrying (%d/%d)...",
                    output_file, attempt, max_attempts,
                )
                time.sleep(1)
            else:
                raise


def generate_excel_report(
    results: Dict[str, Any],
    output_file: str,
    entity_name: str,
    analysis_type: str,
    logger: logging.Logger,
    metadata: Optional[Dict[str, Any]] = None,
    weights_df: Optional[Any] = None,
    method_breakdown_df: Optional[pd.DataFrame] = None,
    privacy_validation_df: Optional[pd.DataFrame] = None,
    secondary_results: Optional[Dict[str, Any]] = None,
    preset_comparison_df: Optional[pd.DataFrame] = None,
    impact_df: Optional[pd.DataFrame] = None,
    impact_summary_df: Optional[pd.DataFrame] = None,
    validation_issues: Optional[Any] = None,
    config: Any = None,
) -> None:
    from utils.config_manager import ConfigManager

    if config is None:
        config = ConfigManager()
    rg = ReportGenerator(config)

    full_metadata = dict(metadata or {})
    full_metadata["entity_name"] = entity_name
    if weights_df is not None:
        full_metadata["weights_df"] = weights_df
    if method_breakdown_df is not None:
        full_metadata["method_breakdown_df"] = method_breakdown_df
    if privacy_validation_df is not None:
        full_metadata["privacy_validation_df"] = privacy_validation_df
    if secondary_results is not None:
        full_metadata["secondary_results"] = secondary_results
        full_metadata["secondary_results_df"] = secondary_results
    if preset_comparison_df is not None:
        full_metadata["preset_comparison_df"] = preset_comparison_df
    if impact_df is not None:
        full_metadata["impact_df"] = impact_df
    if impact_summary_df is not None:
        full_metadata["impact_summary_df"] = impact_summary_df
    if validation_issues is not None:
        full_metadata["validation_issues"] = validation_issues

    rg.generate_report(results, output_file, format="excel", analysis_type=analysis_type, metadata=full_metadata)
    logger.info("Excel report written to %s", output_file)


def generate_multi_rate_excel_report(
    all_results: Dict[str, Dict[str, Any]],
    output_file: str,
    entity_name: str,
    logger: logging.Logger,
    metadata: Dict[str, Any],
    weights_df: Optional[Any] = None,
    numerator_cols: Optional[Dict[str, str]] = None,
    bic_percentiles: Optional[Dict[str, float]] = None,
    privacy_validation_df: Optional[pd.DataFrame] = None,
    method_breakdown_df: Optional[pd.DataFrame] = None,
    secondary_results: Optional[Dict[str, Any]] = None,
    preset_comparison_df: Optional[pd.DataFrame] = None,
    impact_df: Optional[pd.DataFrame] = None,
    impact_summary_df: Optional[pd.DataFrame] = None,
    validation_issues: Optional[Any] = None,
    config: Any = None,
) -> None:
    from utils.config_manager import ConfigManager

    if config is None:
        config = ConfigManager()
    rg = ReportGenerator(config)

    full_metadata = dict(metadata or {})
    full_metadata["entity_name"] = entity_name
    if weights_df is not None:
        full_metadata["weights_df"] = weights_df
    if numerator_cols is not None:
        full_metadata["numerator_cols"] = numerator_cols
    if bic_percentiles is not None:
        full_metadata["bic_percentiles"] = bic_percentiles
    if privacy_validation_df is not None:
        full_metadata["privacy_validation_df"] = privacy_validation_df
    if method_breakdown_df is not None:
        full_metadata["method_breakdown_df"] = method_breakdown_df
    if secondary_results is not None:
        full_metadata["secondary_results"] = secondary_results
        full_metadata["secondary_results_df"] = secondary_results
    if preset_comparison_df is not None:
        full_metadata["preset_comparison_df"] = preset_comparison_df
    if impact_df is not None:
        full_metadata["impact_df"] = impact_df
    if impact_summary_df is not None:
        full_metadata["impact_summary_df"] = impact_summary_df
    if validation_issues is not None:
        full_metadata["validation_issues"] = validation_issues

    combined_results: Dict[str, Any] = {}
    for rate_type, rate_results in all_results.items():
        for dim_key, dim_results in rate_results.items():
            combined_results[f"{rate_type}_{dim_key}"] = dim_results

    rg.generate_report(combined_results, output_file, format="excel", analysis_type="rate", metadata=full_metadata)
    logger.info("Multi-rate Excel report written to %s", output_file)
