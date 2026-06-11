"""Excel report generation helpers shared across CLI and analysis_run."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import pandas as pd

from .report_models import ReportModel
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


def generate_report_model_excel(
    report_model: ReportModel,
    output_file: str,
    *,
    entity_name: str,
    analysis_type: str,
    logger: logging.Logger,
    metadata: Optional[Dict[str, Any]] = None,
    config: Any = None,
) -> None:
    from utils.config_manager import ConfigManager

    if config is None:
        config = ConfigManager()
    full_metadata = report_model.to_metadata(metadata)
    full_metadata["entity_name"] = entity_name
    ReportGenerator(config).generate_report_model(
        report_model,
        output_file,
        analysis_type=analysis_type,
        metadata=full_metadata,
    )
    logger.info("Excel report written to %s", output_file)


def generate_multi_rate_report_model_excel(
    report_model: ReportModel,
    output_file: str,
    *,
    entity_name: str,
    logger: logging.Logger,
    metadata: Optional[Dict[str, Any]] = None,
    numerator_cols: Optional[Dict[str, str]] = None,
    bic_percentiles: Optional[Dict[str, float]] = None,
    config: Any = None,
) -> None:
    from dataclasses import replace

    combined_results: Dict[str, Any] = {}
    for rate_type, rate_results in report_model.results.items():
        for dim_key, dim_results in rate_results.items():
            combined_results[f"{rate_type}_{dim_key}"] = dim_results

    full_metadata = report_model.to_metadata(metadata)
    full_metadata["entity_name"] = entity_name
    if numerator_cols is not None:
        full_metadata["numerator_cols"] = numerator_cols
    if bic_percentiles is not None:
        full_metadata["bic_percentiles"] = bic_percentiles

    generate_report_model_excel(
        replace(report_model, results=combined_results),
        output_file,
        entity_name=entity_name,
        analysis_type="rate",
        logger=logger,
        metadata=full_metadata,
        config=config,
    )
