"""Write analysis, publication, and JSON artifacts."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Set, Tuple

import pandas as pd

from core.contracts import (
    AnalysisArtifacts,
    AnalysisRunRequest,
    PrivacyOutputDecision,
    PublicationUnit,
)
from core.privacy_output_policy import (
    _PrivacyOutputAttestation,
    _SafeCoverageOutputAttestation,
    is_verified_privacy_publication_authorized,
    is_verified_safe_coverage_publication_authorized,
)
from core.excel_reports import generate_multi_rate_report_model_excel, generate_report_model_excel
from core.report_generator import ReportGenerator
from core.report_models import ReportModel


NON_PUBLISHABLE_REPORT_PREFIX = "autobench_NON_PUBLISHABLE_"
SUPPRESSED_PUBLICATION_VIEW_NAME = "Suppressed Publication View"
SUPPRESSED_PUBLICATION_VIEW_NOTICE = (
    "This artifact is a Suppressed Publication View. "
    "Missing units were privacy-suppressed."
)


def _flatten_rate_results(
    results: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    return {
        f"{rate_type}_{dimension}": value
        for rate_type, rate_results in results.items()
        for dimension, value in rate_results.items()
    }


def _original_dimension_name(unit_dimension: str, time_col: Optional[str]) -> str:
    if time_col and unit_dimension.endswith(f"_{time_col}"):
        return unit_dimension[: -(len(time_col) + 1)]
    return unit_dimension


def _original_category_name(unit_category: str, time_period: Optional[str]) -> str:
    if time_period and unit_category.endswith(f"_{time_period}"):
        return unit_category[: -(len(str(time_period)) + 1)]
    return unit_category


def release_row_allowlist(
    release_units: Sequence[PublicationUnit],
    *,
    time_col: Optional[str],
) -> Set[Tuple[str, str, Optional[str]]]:
    """Return (original_dimension, original_category, time_period) allow-list keys."""
    allowed: Set[Tuple[str, str, Optional[str]]] = set()
    for unit in release_units:
        original_dimension = _original_dimension_name(unit.dimension, time_col)
        original_category = _original_category_name(unit.category, unit.time_period)
        allowed.add((original_dimension, original_category, unit.time_period))
    return allowed


def _time_value(row: Mapping[str, Any] | pd.Series, time_col: Optional[str]) -> Optional[str]:
    if time_col and time_col in row and row[time_col] is not None:
        text = str(row[time_col]).strip()
        if text and text != "General":
            return text
        return None
    for candidate in ("Time_Period", "time_period", "Time"):
        if candidate in row and row[candidate] is not None:
            text = str(row[candidate]).strip()
            if text and text != "General":
                return text
    return None


def _filter_share_result_frame(
    frame: Any,
    *,
    dimension: str,
    allowed: Set[Tuple[str, str, Optional[str]]],
    time_col: Optional[str],
) -> Any:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return frame
    if "Category" not in frame.columns:
        return frame.iloc[0:0].copy()

    def _keep(row: pd.Series) -> bool:
        category = str(row["Category"])
        period = _time_value(row, time_col)
        return (dimension, category, period) in allowed

    return frame.loc[frame.apply(_keep, axis=1)].reset_index(drop=True)


def _filter_dataframe_by_release(
    frame: Any,
    *,
    allowed: Set[Tuple[str, str, Optional[str]]],
    time_col: Optional[str],
    default_dimension: Optional[str] = None,
) -> Any:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return frame
    dimension_col = next(
        (
            column
            for column in ("Dimension", "dimension")
            if column in frame.columns
        ),
        None,
    )
    category_col = next(
        (
            column
            for column in ("Category", "category")
            if column in frame.columns
        ),
        None,
    )
    if category_col is None:
        return frame

    def _keep(row: pd.Series) -> bool:
        if dimension_col is not None:
            dimension = str(row[dimension_col])
            # Diagnostic frames may store time-aware dimension names.
            original = _original_dimension_name(dimension, time_col)
        elif default_dimension is not None:
            original = default_dimension
        else:
            return False
        category = str(row[category_col])
        # Prefer bare category; also accept composite category forms.
        period = _time_value(row, time_col)
        bare_category = _original_category_name(category, period)
        return (
            (original, bare_category, period) in allowed
            or (original, category, period) in allowed
            or (dimension if dimension_col else original, bare_category, period)
            in allowed
            or (dimension if dimension_col else original, category, period) in allowed
        )

    return frame.loc[frame.apply(_keep, axis=1)].reset_index(drop=True)


def filter_results_to_release_set(
    results: Mapping[str, Any],
    release_units: Sequence[PublicationUnit],
    *,
    time_col: Optional[str],
) -> Dict[str, Any]:
    """Filter share-analysis result frames to the exact Release Set."""
    allowed = release_row_allowlist(release_units, time_col=time_col)
    return {
        dimension: _filter_share_result_frame(
            frame,
            dimension=str(dimension),
            allowed=allowed,
            time_col=time_col,
        )
        for dimension, frame in results.items()
    }


def apply_release_set_filter(
    artifacts: AnalysisArtifacts,
    *,
    release_units: Sequence[PublicationUnit],
    time_col: Optional[str],
) -> AnalysisArtifacts:
    """Filter every client-bound artifact payload through the Release Set.

    This is the deep client-artifact seam. Callers must invoke it once before
    any sink formatting. Suppressed category names and Suppression Set keys must
    not remain in client-visible metadata after filtering.
    """
    allowed = release_row_allowlist(release_units, time_col=time_col)
    if isinstance(artifacts.results, dict):
        artifacts.results = filter_results_to_release_set(
            artifacts.results,
            release_units,
            time_col=time_col,
        )
    artifacts.secondary_results_df = _filter_dataframe_by_release(
        artifacts.secondary_results_df,
        allowed=allowed,
        time_col=time_col,
    )
    artifacts.privacy_validation_df = _filter_dataframe_by_release(
        artifacts.privacy_validation_df,
        allowed=allowed,
        time_col=time_col,
    )
    artifacts.impact_df = _filter_dataframe_by_release(
        artifacts.impact_df,
        allowed=allowed,
        time_col=time_col,
    )
    artifacts.preset_comparison_df = _filter_dataframe_by_release(
        artifacts.preset_comparison_df,
        allowed=allowed,
        time_col=time_col,
    )
    if artifacts.metadata is not None:
        metadata = dict(artifacts.metadata)
        for key, value in list(metadata.items()):
            if isinstance(value, pd.DataFrame):
                metadata[key] = _filter_dataframe_by_release(
                    value,
                    allowed=allowed,
                    time_col=time_col,
                )
        # Never expose structural suppression category names for privacy-
        # suppressed Publication Units in the client view.
        metadata["suppressed_categories"] = []
        metadata["suppressed_metric_categories"] = []
        metadata["suppressed_output_categories"] = {}
        run_warnings = [
            warning
            for warning in list(metadata.get("run_warnings") or [])
            if not str(warning).startswith("Suppressed ")
        ]
        if SUPPRESSED_PUBLICATION_VIEW_NOTICE not in run_warnings:
            run_warnings.append(SUPPRESSED_PUBLICATION_VIEW_NOTICE)
        metadata["run_warnings"] = run_warnings
        metadata["artifact_name"] = SUPPRESSED_PUBLICATION_VIEW_NAME
        metadata["suppressed_publication_view"] = True
        metadata["privacy_suppressed_missing_units"] = True
        # Strip any accidental trusted coverage dump from client metadata.
        metadata.pop("safe_coverage_result", None)
        metadata.pop("suppression_set", None)
        artifacts.metadata = metadata
    # Rebuild the report model from the filtered payloads so no sink can read
    # an unfiltered model object.
    artifacts.report_model = ReportModel.from_artifacts(artifacts)
    return artifacts


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
    privacy_output_attestation: _PrivacyOutputAttestation | None = None,
    safe_coverage_attestation: _SafeCoverageOutputAttestation | None = None,
) -> AnalysisArtifacts:
    """Write Excel (and optionally publication) reports, returning updated artifacts."""
    if logger is None:
        logger = logging.getLogger(__name__)

    complete_authorized = is_verified_privacy_publication_authorized(
        artifacts.privacy_rule_strategy_result,
        artifacts.privacy_output_decision,
        privacy_output_decision,
        privacy_output_attestation,
    )
    coverage_authorized = is_verified_safe_coverage_publication_authorized(
        artifacts.safe_coverage_result,
        artifacts.privacy_output_decision,
        privacy_output_decision,
        safe_coverage_attestation,
    )
    if not complete_authorized and not coverage_authorized:
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

    if coverage_authorized:
        # Defense in depth: never write coverage artifacts without the
        # Suppressed Publication View marker on client metadata.
        if artifacts.metadata is None:
            artifacts.metadata = {}
        artifacts.metadata.setdefault(
            "artifact_name",
            SUPPRESSED_PUBLICATION_VIEW_NAME,
        )
        artifacts.metadata.setdefault(
            "privacy_suppressed_missing_units",
            True,
        )
        run_warnings = list(artifacts.metadata.get("run_warnings") or [])
        if SUPPRESSED_PUBLICATION_VIEW_NOTICE not in run_warnings:
            run_warnings.append(SUPPRESSED_PUBLICATION_VIEW_NOTICE)
        artifacts.metadata["run_warnings"] = run_warnings

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
