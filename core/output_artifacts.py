"""Output artifact writer for analysis runs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .contracts import AnalysisArtifacts, AnalysisRunRequest
    from .report_models import ReportModel
    from utils.config_manager import ConfigManager


class OutputArtifactWriter:
    """Adapter boundary for report artifact writing."""

    def __init__(
        self,
        report_model: "ReportModel",
        request: "AnalysisRunRequest",
        artifacts: "AnalysisArtifacts",
        config: Any = None,
    ) -> None:
        self.report_model = report_model
        self.request = request
        self.artifacts = artifacts
        self.config = config

    @property
    def output_file(self) -> str:
        return self.artifacts.analysis_output_file or "benchmark_output.xlsx"

    @property
    def publication_file(self) -> str:
        return self.artifacts.publication_output or self.output_file

    @property
    def output_format(self) -> str:
        if self.config is None:
            return self.request.output_format
        return self.config.get("output", "output_format", default=self.request.output_format)

    @property
    def write_analysis(self) -> bool:
        return self.output_format in {"analysis", "both"}

    @property
    def write_publication(self) -> bool:
        return self.output_format in {"publication", "both"}


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

    from core.excel_reports import generate_multi_rate_report_model_excel, generate_report_model_excel
    from core.report_models import ReportModel

    report_model = artifacts.report_model or ReportModel.from_artifacts(artifacts)
    writer = OutputArtifactWriter(report_model, request, artifacts, config)

    output_file = writer.output_file
    publication_file = writer.publication_file
    entity_name = request.entity or "PEER_ONLY"

    def _write_report(path: str, *, publication: bool) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        if publication:
            from core.report_generator import ReportGenerator

            fraud_in_bps = (
                config.get("output", "fraud_in_bps", default=getattr(request, "fraud_in_bps", True))
                if config is not None
                else getattr(request, "fraud_in_bps", True)
            )
            publication_results = artifacts.results
            if request.is_rate and isinstance(artifacts.results, dict):
                publication_results = {
                    f"{rate_type}_{dimension}": value
                    for rate_type, rate_results in artifacts.results.items()
                    for dimension, value in rate_results.items()
                }
            # Merge diagnostic DataFrames into the metadata bag so the
            # publication workbook's allow-list (Q9) can read them via
            # `_write_optional_dataframe_sheet`. The diagnostics live as
            # separate `artifacts.*_df` attributes for the analysis path; the
            # publication helper expects them inside `metadata`.
            publication_metadata = dict(artifacts.metadata or {})
            for key, value in {
                "weights_df": artifacts.weights_df,
                "method_breakdown_df": artifacts.method_breakdown_df,
                "privacy_validation_df": artifacts.privacy_validation_df,
                "preset_comparison_df": artifacts.preset_comparison_df,
                "impact_df": artifacts.impact_df,
                "impact_summary_df": artifacts.impact_summary_df,
                "secondary_results": artifacts.secondary_results_df,
                "rank_changes_df": getattr(artifacts, "rank_changes_df", None),
            }.items():
                if value is not None and key not in publication_metadata:
                    publication_metadata[key] = value

            ReportGenerator(config).generate_publication_workbook(
                publication_results,
                path,
                analysis_type="share" if request.is_share else "rate",
                metadata=publication_metadata,
                fraud_in_bps=fraud_in_bps,
            )
            return

        if request.is_rate and isinstance(artifacts.results, dict) and all(
            isinstance(v, dict) for v in artifacts.results.values()
        ):
            generate_multi_rate_report_model_excel(
                report_model,
                path,
                entity_name=entity_name,
                logger=logger,
                metadata=artifacts.metadata or {},
                numerator_cols=request.numerator_cols,
                config=config,
            )
            return

        analysis_type = "share" if request.is_share else "rate"
        generate_report_model_excel(
            report_model,
            path,
            entity_name=entity_name,
            analysis_type=analysis_type,
            logger=logger,
            metadata=artifacts.metadata,
            config=config,
        )

    if writer.write_analysis:
        _write_report(output_file, publication=False)
        logger.info("Analysis report written to %s", output_file)
    if writer.write_publication:
        _write_report(publication_file, publication=True)
        artifacts.publication_output = publication_file
        logger.info("Publication report written to %s", publication_file)
    return artifacts
