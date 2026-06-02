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
    impact_df: Optional[pd.DataFrame] = None
    data_quality_df: Optional[pd.DataFrame] = None

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
            impact_df=frames.get("impact_df"),
            data_quality_df=frames.get("data_quality_df"),
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
            impact_df=artifacts.impact_df,
        )
