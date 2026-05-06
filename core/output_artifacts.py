"""Output artifact writer for analysis runs."""

from __future__ import annotations

import logging
from pathlib import Path
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
    publication_file = artifacts.publication_output or output_file
    entity_name = request.entity or "PEER_ONLY"
    output_format = (
        config.get("output", "output_format", default=request.output_format)
        if config is not None
        else request.output_format
    )
    write_analysis = output_format in {"analysis", "both"}
    write_publication = output_format in {"publication", "both"}

    def _write_report(path: str, publication: bool) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        analysis_type = "share" if request.is_share else "rate"
        if publication:
            from core.report_generator import ReportGenerator

            ReportGenerator(config).generate_publication_workbook(
                artifacts.results,
                path,
                analysis_type=analysis_type,
                metadata=artifacts.metadata,
                fraud_in_bps=request.fraud_in_bps,
            )
            return

        if request.is_rate and isinstance(artifacts.results, dict) and all(
            isinstance(v, dict) for v in artifacts.results.values()
        ):
            generate_multi_rate_excel_report(
                artifacts.results,
                path,
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
                config=config,
            )
        else:
            generate_excel_report(
                artifacts.results,
                path,
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
                config=config,
            )

    if write_analysis:
        _write_report(output_file, publication=False)
        logger.info("Analysis report written to %s", output_file)

    if write_publication:
        artifacts.publication_output = publication_file
        _write_report(publication_file, publication=True)
        logger.info("Publication report written to %s", publication_file)

    return artifacts
