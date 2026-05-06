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
    entity_name = request.entity or "PEER_ONLY"

    if config:
        output_format = config.get("output", "output_format", default=request.output_format)
    else:
        output_format = request.output_format

    output_path = Path(output_file)
    publication_file = str(output_path.with_name(f"{output_path.stem}_publication{output_path.suffix}"))
    artifacts.publication_output = publication_file

    write_analysis = output_format in {"analysis", "both"}
    write_publication = output_format in {"publication", "both"}

    def _write_report(target_file: str, publication: bool = False) -> None:
        if publication:
            from core.report_generator import ReportGenerator
            from utils.config_manager import ConfigManager as CM
            rg_config = config if config else CM()
            rg = ReportGenerator(rg_config)
            fraud_in_bps = True
            if artifacts.metadata:
                fraud_in_bps = artifacts.metadata.get("fraud_in_bps", True)
            analysis_type = "share" if request.is_share else "rate"
            rg.generate_publication_workbook(
                artifacts.results if not (request.is_rate and isinstance(artifacts.results, dict) and all(isinstance(v, dict) for v in artifacts.results.values())) else _flatten_rate_results(artifacts.results),
                target_file,
                analysis_type=analysis_type,
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
            )

    if write_analysis:
        _write_report(output_file, publication=False)
        logger.info("Analysis report written to %s", output_file)

    if write_publication:
        _write_report(publication_file, publication=True)
        logger.info("Publication report written to %s", publication_file)

    if not write_analysis and not write_publication:
        _write_report(output_file, publication=False)
        logger.info("Report written to %s", output_file)

    return artifacts


def _flatten_rate_results(all_results: dict) -> dict:
    """Flatten nested rate results dict for publication workbook."""
    combined = {}
    for rate_type, rate_results in all_results.items():
        if isinstance(rate_results, dict):
            for dim_key, dim_results in rate_results.items():
                combined[f"{rate_type}_{dim_key}"] = dim_results
        else:
            combined[rate_type] = rate_results
    return combined
