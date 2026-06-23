"""Typed report models used by rendering adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import pandas as pd

from core.contracts import AnalysisArtifacts, AnalysisResult, RunSummary


@dataclass(frozen=True)
class ReportModel:
    summary: RunSummary
    compliance_summary: Dict[str, Any]
    results: Any
    privacy_validation_df: Optional[pd.DataFrame] = None
    weights_df: Optional[pd.DataFrame] = None
    method_breakdown_df: Optional[pd.DataFrame] = None
    secondary_results_df: Optional[pd.DataFrame] = None
    preset_comparison_df: Optional[pd.DataFrame] = None
    impact_df: Optional[pd.DataFrame] = None
    impact_summary_df: Optional[pd.DataFrame] = None
    data_quality_df: Optional[pd.DataFrame] = None
    structural_summary_df: Optional[pd.DataFrame] = None
    structural_detail_df: Optional[pd.DataFrame] = None
    rank_changes_df: Optional[pd.DataFrame] = None
    subset_search_df: Optional[pd.DataFrame] = None
    validation_issues: Any = None

    @classmethod
    def from_analysis_result(
        cls,
        result: AnalysisResult,
        **frames: Any,
    ) -> "ReportModel":
        if not result.compliance_summary:
            raise ValueError("ReportModel requires compliance_summary")
        plan = result.plan
        summary = RunSummary(
            entity=plan.entity or "PEER-ONLY",
            entity_column=plan.entity_column,
            dimensions_analyzed=len(plan.dimensions),
            dimension_names=list(plan.dimensions),
            preset=plan.request.preset,
            compliance_posture=result.compliance_summary.get("posture"),
            output_format=plan.output_settings.output_format,
            privacy_rule=result.weighting.privacy_rule_name,
        )
        return cls(
            summary=summary,
            compliance_summary=dict(result.compliance_summary),
            results=result.results,
            privacy_validation_df=frames.get("privacy_validation_df"),
            weights_df=frames.get("weights_df"),
            method_breakdown_df=frames.get("method_breakdown_df"),
            secondary_results_df=frames.get("secondary_results_df"),
            preset_comparison_df=frames.get("preset_comparison_df"),
            impact_df=frames.get("impact_df"),
            impact_summary_df=frames.get("impact_summary_df"),
            data_quality_df=frames.get("data_quality_df"),
            structural_summary_df=frames.get("structural_summary_df"),
            structural_detail_df=frames.get("structural_detail_df"),
            rank_changes_df=frames.get("rank_changes_df"),
            subset_search_df=frames.get("subset_search_df"),
            validation_issues=frames.get("validation_issues"),
        )

    @classmethod
    def from_artifacts(cls, artifacts: AnalysisArtifacts) -> "ReportModel":
        compliance_summary = artifacts.compliance_summary or (artifacts.metadata or {}).get("compliance_summary")
        if not compliance_summary:
            raise ValueError("ReportModel requires compliance_summary")
        metadata = artifacts.metadata or {}
        summary = RunSummary(
            entity=str(metadata.get("entity", "PEER-ONLY")),
            entity_column=str(metadata.get("entity_column", "issuer_name")),
            total_records=int(metadata.get("total_records", 0) or 0),
            unique_entities=int(metadata.get("unique_entities", 0) or 0),
            peer_count=int(metadata.get("peer_count", 0) or 0),
            dimensions_analyzed=int(metadata.get("dimensions_analyzed", 0) or 0),
            dimension_names=list(metadata.get("dimension_names", []) or []),
            preset=metadata.get("preset"),
            compliance_posture=metadata.get("compliance_posture"),
            debug_mode=bool(metadata.get("debug_mode", False)),
            consistent_weights=bool(metadata.get("consistent_weights", True)),
            output_format=str(metadata.get("output_format", "analysis")),
            timestamp=metadata.get("timestamp"),
            privacy_rule=metadata.get("privacy_rule"),
        )
        return cls(
            summary=summary,
            compliance_summary=dict(compliance_summary),
            results=artifacts.results,
            privacy_validation_df=artifacts.privacy_validation_df,
            weights_df=artifacts.weights_df,
            method_breakdown_df=artifacts.method_breakdown_df,
            secondary_results_df=artifacts.secondary_results_df,
            preset_comparison_df=artifacts.preset_comparison_df,
            impact_df=artifacts.impact_df,
            impact_summary_df=artifacts.impact_summary_df,
            structural_summary_df=metadata.get("structural_summary_df"),
            structural_detail_df=metadata.get("structural_detail_df"),
            rank_changes_df=metadata.get("rank_changes_df"),
            subset_search_df=metadata.get("subset_search_df"),
            validation_issues=artifacts.validation_issues,
        )

    def to_metadata(self, base: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Render model fields into the legacy metadata keys used by workbooks."""
        metadata = dict(base or {})
        metadata.setdefault("compliance_summary", dict(self.compliance_summary))
        for key, value in self.summary.to_metadata_dict().items():
            if value not in (None, [], {}) and key not in metadata:
                metadata[key] = value

        optional_frames = {
            "privacy_validation_df": self.privacy_validation_df,
            "weights_df": self.weights_df,
            "method_breakdown_df": self.method_breakdown_df,
            "secondary_results": self.secondary_results_df,
            "secondary_results_df": self.secondary_results_df,
            "preset_comparison_df": self.preset_comparison_df,
            "impact_df": self.impact_df,
            "impact_summary_df": self.impact_summary_df,
            "structural_summary_df": self.structural_summary_df,
            "structural_detail_df": self.structural_detail_df,
            "rank_changes_df": self.rank_changes_df,
            "subset_search_df": self.subset_search_df,
        }
        for key, value in optional_frames.items():
            if value is not None and key not in metadata:
                metadata[key] = value
        if self.validation_issues is not None and "validation_issues" not in metadata:
            metadata["validation_issues"] = self.validation_issues
        return metadata
