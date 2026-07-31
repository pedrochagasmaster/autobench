"""Write analysis, publication, and JSON artifacts."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Mapping

from core.contracts import (
    AnalysisArtifacts,
    AnalysisRunRequest,
    PrivacyOutputDecision,
)
from core.privacy_output_policy import (
    _PrivacyOutputAttestation,
    is_verified_privacy_publication_authorized,
)
from core.excel_reports import generate_multi_rate_report_model_excel, generate_report_model_excel
from core.report_generator import ReportGenerator
from core.report_models import ReportModel


NON_PUBLISHABLE_REPORT_PREFIX = "autobench_NON_PUBLISHABLE_"


def _flatten_rate_results(
    results: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    return {
        f"{rate_type}_{dimension}": value
        for rate_type, rate_results in results.items()
        for dimension, value in rate_results.items()
    }


def write_accuracy_first_diagnostic_report(
    request: AnalysisRunRequest,
    artifacts: AnalysisArtifacts,
    analysis_output_file: str,
    *,
    config: Any = None,
    logger: logging.Logger | None = None,
) -> str:
    """Write the consented accuracy_first analysis workbook, clearly marked.

    This is the only sanctioned exception to the Control 3 hard output block:
    the operator explicitly acknowledged the accuracy_first posture, the
    denial is numeric-only, and the workbook is written under a
    non-publishable filename prefix with matching metadata. Publication
    workbooks, balanced CSVs, JSON reports, and audit packages stay withheld.
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    requested = Path(analysis_output_file)
    diagnostic_path = requested.with_name(
        f"{NON_PUBLISHABLE_REPORT_PREFIX}{requested.name}"
    )
    diagnostic_path.parent.mkdir(parents=True, exist_ok=True)
    report_model = artifacts.report_model or ReportModel.from_artifacts(artifacts)
    entity_name = request.entity or "PEER_ONLY"
    if request.is_rate and isinstance(artifacts.results, dict) and all(
        isinstance(v, dict) for v in artifacts.results.values()
    ):
        generate_multi_rate_report_model_excel(
            report_model,
            str(diagnostic_path),
            entity_name=entity_name,
            logger=logger,
            metadata=artifacts.metadata or {},
            numerator_cols=request.numerator_cols,
            config=config,
        )
    else:
        generate_report_model_excel(
            report_model,
            str(diagnostic_path),
            entity_name=entity_name,
            analysis_type="share" if request.is_share else "rate",
            logger=logger,
            metadata=artifacts.metadata,
            config=config,
        )
    logger.warning(
        "Non-publishable accuracy_first diagnostic report written to %s",
        diagnostic_path,
    )
    return str(diagnostic_path)


def write_outputs(
    request: AnalysisRunRequest,
    artifacts: AnalysisArtifacts,
    *,
    config: Any = None,
    logger: logging.Logger | None = None,
    privacy_output_decision: PrivacyOutputDecision,
    privacy_output_attestation: _PrivacyOutputAttestation | None,
) -> AnalysisArtifacts:
    """Write Excel (and optionally publication) reports, returning updated artifacts."""
    if logger is None:
        logger = logging.getLogger(__name__)

    if not is_verified_privacy_publication_authorized(
        artifacts.privacy_rule_strategy_result,
        artifacts.privacy_output_decision,
        privacy_output_decision,
        privacy_output_attestation,
    ):
        artifacts.analysis_output_file = None
        artifacts.publication_output = None
        artifacts.csv_output = None
        artifacts.json_output = None
        artifacts.audit_log_output = None
        artifacts.audit_package_output = None
        artifacts.report_paths = []
        logger.error(
            "All benchmark-bearing outputs withheld by Control 3 (%s)",
            privacy_output_decision.withholding_reason,
        )
        return artifacts

    posture = (artifacts.compliance_summary or {}).get("posture")
    verdict = (artifacts.compliance_summary or {}).get("compliance_verdict")
    violations = int((artifacts.compliance_summary or {}).get("violations", 0) or 0)
    block_publication = (
        posture == "strict"
        and (
            violations > 0
            or (verdict is not None and verdict != "fully_compliant")
        )
    )

    if block_publication:
        if artifacts.metadata is None:
            artifacts.metadata = {}
        artifacts.metadata["publication_withheld_reason"] = (
            "strict_posture_violations"
            if violations > 0
            else "strict_posture_noncompliant_verdict"
        )

    report_model = artifacts.report_model or ReportModel.from_artifacts(artifacts)
    output_file = artifacts.analysis_output_file or "benchmark_output.xlsx"
    publication_file = artifacts.publication_output or output_file
    output_format = (
        request.output_format
        if config is None
        else config.get("output", "output_format", default=request.output_format)
    )
    write_analysis = output_format in {"analysis", "both"}
    write_publication = output_format in {"publication", "both"}
    entity_name = request.entity or "PEER_ONLY"

    def _write_report(path: str, *, publication: bool) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        if publication:
            fraud_in_bps = (
                config.get("output", "fraud_in_bps", default=getattr(request, "fraud_in_bps", True))
                if config is not None
                else getattr(request, "fraud_in_bps", True)
            )
            publication_results = artifacts.results
            if request.is_rate and isinstance(artifacts.results, dict):
                publication_results = _flatten_rate_results(artifacts.results)
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

    if write_analysis:
        _write_report(output_file, publication=False)
        logger.info("Analysis report written to %s", output_file)

        report_format = (
            config.get("output", "format", default="xlsx") if config is not None else "xlsx"
        )
        if report_format == "json":
            json_path = str(Path(output_file).with_suffix(".json"))
            json_results = artifacts.results
            if request.is_rate and isinstance(artifacts.results, dict) and all(
                isinstance(v, dict) for v in artifacts.results.values()
            ):
                json_results = _flatten_rate_results(artifacts.results)
            ReportGenerator(config).generate_report(
                json_results,
                json_path,
                format="json",
                analysis_type="share" if request.is_share else "rate",
                metadata=artifacts.metadata,
            )
            artifacts.json_output = json_path
            logger.info("JSON report written to %s", json_path)
    else:
        artifacts.analysis_output_file = None
    if write_publication:
        if block_publication:
            artifacts.publication_output = None
            logger.error(
                "Strict posture: publication output withheld (violations=%d). "
                "Analysis workbook written for debugging only.",
                violations,
            )
        else:
            _write_report(publication_file, publication=True)
            artifacts.publication_output = publication_file
            logger.info("Publication report written to %s", publication_file)
    else:
        artifacts.publication_output = None
    return artifacts
