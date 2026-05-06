"""Output artifact writer for analysis runs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from .contracts import AnalysisArtifacts, AnalysisRunRequest
    from utils.config_manager import ConfigManager


def _resolve_output_format(
    request: "AnalysisRunRequest",
    config: Any,
) -> str:
    if config is not None:
        fmt = config.get("output", "output_format", default=None)
        if fmt:
            return str(fmt)
    return getattr(request, "output_format", "analysis") or "analysis"


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
    from core.report_generator import ReportGenerator
    from utils.config_manager import ConfigManager

    output_file = artifacts.analysis_output_file or "benchmark_output.xlsx"
    entity_name = request.entity or "PEER_ONLY"
    output_format = _resolve_output_format(request, config)

    write_analysis = output_format in {"analysis", "both"}
    write_publication = output_format in {"publication", "both"}

    def _write_report(
        target_file: str,
        publication: bool = False,
    ) -> None:
        if publication:
            rg_config = config if config is not None else ConfigManager()
            rg = ReportGenerator(rg_config)
            fraud_in_bps = getattr(request, "fraud_in_bps", True)
            rg.generate_publication_workbook(
                artifacts.results or {},
                target_file,
                analysis_type="share" if request.is_share else "rate",
                metadata=artifacts.metadata,
                fraud_in_bps=fraud_in_bps,
            )
            return

        if request.is_rate and isinstance(artifacts.results, dict) and all(
            isinstance(v, dict) for v in artifacts.results.values()
        ):
            generate_multi_rate_excel_report(
                artifacts.results,
                target_file,
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
            analysis_type = "share" if request.is_share else "rate"
            generate_excel_report(
                artifacts.results,
                target_file,
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
        publication_file = artifacts.publication_output or output_file
        _write_report(publication_file, publication=True)
        logger.info("Publication report written to %s", publication_file)

    report_paths = []
    if write_analysis:
        report_paths.append(output_file)
    if write_publication and artifacts.publication_output:
        report_paths.append(artifacts.publication_output)
    artifacts.report_paths = report_paths if report_paths else None

    return artifacts
