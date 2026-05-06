"""Shared data contracts for analysis orchestration."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field, fields
from typing import Any, Dict, List, Optional


@dataclass
class SolverRequest:
    """Request payload for privacy weight solvers."""

    peers: List[str] = field(default_factory=list)
    categories: List[Dict[str, Any]] = field(default_factory=list)
    max_concentration: float = 0.0
    peer_volumes: Dict[str, float] = field(default_factory=dict)
    rank_preservation_strength: float = 0.0
    rank_constraint_mode: str = "all"
    rank_constraint_k: int = 1
    tolerance: float = 1.0
    volume_weighted_penalties: bool = False
    volume_weighting_exponent: float = 1.0
    lambda_penalty: Optional[float] = None
    max_iterations: int = 1000
    min_weight: float = 0.01
    max_weight: float = 10.0
    target_weights: Optional[Dict[str, float]] = None
    rule_name: Optional[str] = None
    learning_rate: float = 0.01
    violation_penalty_weight: float = 1000.0
    merchant_mode: bool = False
    enforce_additional_constraints: bool = False
    dynamic_constraints_enabled: bool = False
    time_column: Optional[str] = None
    min_peer_count_for_constraints: int = 6
    min_effective_peer_count: int = 3
    min_category_volume_share: float = 0.01
    min_overall_volume_share: float = 0.01
    min_representativeness: float = 0.5
    dynamic_threshold_scale_floor: float = 0.5
    dynamic_count_scale_floor: float = 0.5
    representativeness_penalty_floor: float = 0.1
    representativeness_penalty_power: float = 2.0


@dataclass
class AnalysisRunRequest:
    """Unified request object for share and rate analysis runs."""

    mode: str = "share"
    csv: Optional[str] = None
    df: Any = None
    entity: Optional[str] = None
    entity_col: str = "issuer_name"
    preset: Optional[str] = None
    config: Optional[str] = None
    output: Optional[str] = None
    time_col: Optional[str] = None
    log_level: str = "INFO"
    validate_input: bool = True
    analyze_distortion: bool = False
    compare_presets: bool = False
    include_calculated: bool = False
    output_format: str = "analysis"
    metric: Optional[str] = None
    secondary_metrics: Optional[List[str]] = None
    auto: bool = False
    dimensions: Optional[List[str]] = None
    debug: bool = False
    export_balanced_csv: bool = False
    per_dimension_weights: bool = False
    total_col: Optional[str] = None
    approved_col: Optional[str] = None
    fraud_col: Optional[str] = None
    fraud_in_bps: bool = True
    compliance_posture: Optional[str] = None
    acknowledge_accuracy_first: bool = False

    @property
    def is_share(self) -> bool:
        return self.mode == "share"

    @property
    def is_rate(self) -> bool:
        return self.mode == "rate"

    @property
    def rate_types(self) -> List[str]:
        types: List[str] = []
        if self.approved_col:
            types.append("approval")
        if self.fraud_col:
            types.append("fraud")
        return types or ["approval"]

    @property
    def numerator_cols(self) -> Dict[str, str]:
        cols: Dict[str, str] = {}
        if self.approved_col:
            cols["approval"] = self.approved_col
        if self.fraud_col:
            cols["fraud"] = self.fraud_col
        return cols

    def to_namespace(self) -> argparse.Namespace:
        data: Dict[str, Any] = {f.name: getattr(self, f.name) for f in fields(self)}
        return argparse.Namespace(**data)

    @classmethod
    def from_namespace(cls, mode: str, ns: argparse.Namespace) -> "AnalysisRunRequest":
        valid_keys = {f.name for f in fields(cls)}
        kwargs: Dict[str, Any] = {"mode": mode}
        for key in valid_keys:
            if hasattr(ns, key) and key != "mode":
                kwargs[key] = getattr(ns, key)
        return cls(**kwargs)


@dataclass
class AnalysisArtifacts:
    """Collected outputs from a completed analysis run."""

    results: Any = None
    metadata: Optional[Dict[str, Any]] = None
    weights_df: Any = None
    method_breakdown_df: Any = None
    privacy_validation_df: Any = None
    secondary_results_df: Any = None
    preset_comparison_df: Any = None
    impact_df: Any = None
    impact_summary_df: Any = None
    validation_issues: Optional[List[Any]] = None
    analysis_output_file: Optional[str] = None
    analyzer: Any = None
    compliance_summary: Optional[Dict[str, Any]] = None
    report_paths: Optional[List[str]] = None
    csv_output: Optional[str] = None
    publication_output: Optional[str] = None


@dataclass
class PreparedDataset:
    """Holds a loaded and validated dataset ready for analysis."""

    df: Any = None
    entity_col: str = "issuer_name"
    time_col: Optional[str] = None
    data_loader: Any = None
