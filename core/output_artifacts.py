"""Output artifact writer for analysis runs."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .contracts import AnalysisArtifacts, AnalysisRunRequest
    from utils.config_manager import ConfigManager


def write_outputs(
    request: "AnalysisRunRequest",
    artifacts: "AnalysisArtifacts",
    *,
    config: Any = None,
    logger: logging.Logger | None = None,
) -> "AnalysisArtifacts":
    """Write Excel (and optionally publication) reports, returning updated artifacts."""
    if logger is None:
        logger = logging.getLogger(__name__)

    from benchmark import generate_excel_report, generate_multi_rate_excel_report

    output_file = artifacts.analysis_output_file or "benchmark_output.xlsx"
    entity_name = request.entity or "PEER_ONLY"

    if request.is_rate and isinstance(artifacts.results, dict) and all(
        isinstance(v, dict) for v in artifacts.results.values()
    ):
        generate_multi_rate_excel_report(
            artifacts.results,
            output_file,
            entity_name,
            logger,
            artifacts.metadata or {},
            weights_df=artifacts.weights_df,
            numerator_cols=request.numerator_cols,
            privacy_validation_df=artifacts.privacy_validation_df,
            method_breakdown_df=artifacts.method_breakdown_df,
            secondary_results=artifacts.secondary_results_df,
            preset_comparison_df=artifacts.preset_comparison_df,
            impact_df=artifacts.impact_df,
            impact_summary_df=artifacts.impact_summary_df,
            validation_issues=artifacts.validation_issues,
        )
    else:
        analysis_type = "share" if request.is_share else "rate"
        generate_excel_report(
            artifacts.results,
            output_file,
            entity_name,
            analysis_type,
            logger,
            metadata=artifacts.metadata,
            weights_df=artifacts.weights_df,
            method_breakdown_df=artifacts.method_breakdown_df,
            privacy_validation_df=artifacts.privacy_validation_df,
            secondary_results=artifacts.secondary_results_df,
            preset_comparison_df=artifacts.preset_comparison_df,
            impact_df=artifacts.impact_df,
            impact_summary_df=artifacts.impact_summary_df,
            validation_issues=artifacts.validation_issues,
        )

    logger.info("Report written to %s", output_file)
    return artifacts
