"""Output artifact writer for analysis runs."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .contracts import AnalysisArtifacts, AnalysisRunRequest


def _resolve_output_format(request: "AnalysisRunRequest", config: Any) -> str:
    """Resolve output_format from merged config or request."""
    if config is not None:
        try:
            value = config.get("output", "output_format", default=None)
            if value:
                return str(value)
        except Exception:
            pass
    return getattr(request, "output_format", None) or "analysis"


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

    output_file = artifacts.analysis_output_file or "benchmark_output.xlsx"
    publication_file = artifacts.publication_output or output_file
    entity_name = request.entity or "PEER_ONLY"
    output_format = _resolve_output_format(request, config)
    write_analysis = output_format in {"analysis", "both"}
    write_publication = output_format in {"publication", "both"}

    is_multi_rate = request.is_rate and isinstance(artifacts.results, dict) and all(
        isinstance(v, dict) for v in artifacts.results.values()
    )

    if write_analysis:
        if is_multi_rate:
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
        logger.info("Analysis report written to %s", output_file)

    if write_publication:
        rg = ReportGenerator(config)
        analysis_type = "share" if request.is_share else "rate"
        publication_metadata = dict(artifacts.metadata or {})
        publication_metadata["entity_name"] = entity_name
        if is_multi_rate:
            combined: dict = {}
            for rate_type, rate_results in artifacts.results.items():
                for dim_key, dim_results in rate_results.items():
                    combined[f"{rate_type}_{dim_key}"] = dim_results
            publication_results: Any = combined
        else:
            publication_results = artifacts.results
        fraud_in_bps = bool(publication_metadata.get("fraud_in_bps", True))
        rg.generate_publication_workbook(
            publication_results,
            publication_file,
            analysis_type=analysis_type,
            metadata=publication_metadata,
            fraud_in_bps=fraud_in_bps,
        )
        logger.info("Publication report written to %s", publication_file)

    if not write_analysis and not write_publication:
        logger.warning("Output format '%s' produced no reports", output_format)

    return artifacts
