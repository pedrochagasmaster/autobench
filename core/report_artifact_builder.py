"""Build report/output artifacts from completed analysis results."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from core.contracts import AnalysisArtifacts, AnalysisResult
from core.representativeness import compute_representativeness
from core.report_models import ReportModel


def build_analysis_artifacts(
    *,
    analysis_result: AnalysisResult,
    metadata: Dict[str, Any],
    diagnostics: Dict[str, Any],
    secondary_results_df: Optional[pd.DataFrame],
    preset_comparison_df: Optional[pd.DataFrame],
    impact_df: Optional[pd.DataFrame],
    impact_summary_df: Optional[pd.DataFrame],
    validation_issues: Optional[List[Any]],
    analysis_output_file: str,
    analyzer: Any,
    compliance_summary: Dict[str, Any],
) -> AnalysisArtifacts:
    """Assemble the reporting payload used by output writers."""
    output_path = Path(analysis_output_file)
    metadata = dict(metadata)
    if diagnostics.get("weights_df") is not None and "weights_df" not in metadata:
        metadata["weights_df"] = diagnostics["weights_df"]
    if diagnostics.get("method_breakdown_df") is not None and "method_breakdown_df" not in metadata:
        metadata["method_breakdown_df"] = diagnostics["method_breakdown_df"]

    representativeness = compute_representativeness(metadata)
    metadata["representativeness"] = representativeness
    for warning in representativeness.get("warnings", []):
        run_warnings = metadata.setdefault("run_warnings", [])
        if warning not in run_warnings:
            run_warnings.append(warning)

    return AnalysisArtifacts(
        results=analysis_result.results,
        metadata=metadata,
        weights_df=diagnostics["weights_df"],
        method_breakdown_df=diagnostics["method_breakdown_df"],
        privacy_validation_df=diagnostics["privacy_validation_df"],
        secondary_results_df=secondary_results_df,
        preset_comparison_df=preset_comparison_df,
        impact_df=impact_df,
        impact_summary_df=impact_summary_df,
        validation_issues=validation_issues,
        analysis_output_file=str(output_path),
        publication_output=str(output_path.with_name(f"{output_path.stem}_publication{output_path.suffix}")),
        analyzer=analyzer,
        compliance_summary=compliance_summary,
        report_model=ReportModel.from_analysis_result(
            analysis_result,
            privacy_validation_df=diagnostics["privacy_validation_df"],
            weights_df=diagnostics["weights_df"],
            method_breakdown_df=diagnostics["method_breakdown_df"],
            secondary_results_df=secondary_results_df,
            preset_comparison_df=preset_comparison_df,
            impact_df=impact_df,
            impact_summary_df=impact_summary_df,
            structural_summary_df=metadata.get("structural_summary_df"),
            structural_detail_df=metadata.get("structural_detail_df"),
            rank_changes_df=metadata.get("rank_changes_df"),
            subset_search_df=metadata.get("subset_search_df"),
            validation_issues=validation_issues,
        ),
    )
