"""Shared data contracts for analysis orchestration."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional

from core.control3_policy import CONTROL3_POLICY_KEYS


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
    min_peer_count_for_constraints: int = 4
    min_effective_peer_count: int = 3
    min_category_volume_share: float = 0.01
    min_overall_volume_share: float = 0.01
    min_representativeness: float = 0.5
    dynamic_threshold_scale_floor: float = 0.5
    dynamic_count_scale_floor: float = 0.5
    representativeness_penalty_floor: float = 0.1
    representativeness_penalty_power: float = 2.0


@dataclass
class DataQualityResult:
    """Input validation status for an analysis run."""

    checked: bool
    errors: int = 0
    warnings: int = 0
    infos: int = 0
    issues: Optional[List[Any]] = None
    should_abort: bool = False

    @property
    def publishable(self) -> bool:
        return self.checked and self.errors == 0

    def __iter__(self):
        yield self.issues
        yield self.should_abort


@dataclass
class WeightingComplianceState:
    """Compliance facts produced by the weighting workflow."""

    rule_name: Optional[str] = None
    primary_cap_passed: bool = False
    secondary_rule_passed: bool = False
    relaxation_used: bool = False
    heuristic_converged: Optional[bool] = None
    residual_violations: int = 0
    verdict: str = "unknown"


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
    lean: bool = False
    per_dimension_weights: bool = False
    total_col: Optional[str] = None
    approved_col: Optional[str] = None
    fraud_col: Optional[str] = None
    fraud_in_bps: bool = True
    compliance_posture: Optional[str] = None
    acknowledge_accuracy_first: bool = False
    control3_overrides: Dict[str, Any] = field(default_factory=dict)
    prepared_dataset: Optional["PreparedDataset"] = None

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
        kwargs["control3_overrides"] = {
            key: getattr(ns, key)
            for key in CONTROL3_POLICY_KEYS
            if getattr(ns, key, None) is not None
        }
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
    report_model: Any = None


@dataclass
class PreparedDataset:
    """Holds a loaded and validated dataset ready for analysis."""

    df: Any = None
    entity_col: str = "issuer_name"
    time_col: Optional[str] = None
    data_loader: Any = None
    validation_issues: Optional[List[Any]] = None


@dataclass
class WeightingResult:
    """Immutable snapshot of global/per-dimension weight optimization output."""

    global_weights: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    per_dimension_weights: Dict[str, Dict[str, float]] = field(default_factory=dict)
    weight_methods: Dict[str, str] = field(default_factory=dict)
    last_lp_stats: Dict[str, Any] = field(default_factory=dict)
    privacy_rule_name: Optional[str] = None
    removed_dimensions: List[str] = field(default_factory=list)
    global_dimensions_used: List[str] = field(default_factory=list)
    rank_changes_df: Any = None
    structural_summary_df: Any = None
    structural_detail_df: Any = None
    subset_search_results: List[Dict[str, Any]] = field(default_factory=list)
    compliance_blocked_reason: Optional[str] = None
    compliance_blocked_peer_count: Optional[int] = None
    additional_constraint_violations: List[Dict[str, Any]] = field(default_factory=list)
    slack_subset_triggered: bool = False
    compliance_state: WeightingComplianceState = field(default_factory=WeightingComplianceState)


@dataclass(frozen=True)
class WeightLookup:
    """Typed view over privacy multipliers used by downstream readers.

    Per-dimension multipliers intentionally override global multipliers because
    fallback solving can produce dimension-specific feasible weights.
    """

    global_weights: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    per_dimension_weights: Mapping[str, Mapping[str, float]] = field(default_factory=dict)

    @classmethod
    def from_weighting_result(cls, result: WeightingResult) -> "WeightLookup":
        return cls(
            global_weights=result.global_weights,
            per_dimension_weights=result.per_dimension_weights,
        )

    @classmethod
    def from_analyzer(cls, analyzer: Any) -> "WeightLookup":
        return cls(
            global_weights=getattr(analyzer, "global_weights", {}) or {},
            per_dimension_weights=getattr(analyzer, "per_dimension_weights", {}) or {},
        )

    def multiplier(self, peer: str, dimension: Optional[str] = None) -> float:
        if dimension is not None:
            dim_weights = self.per_dimension_weights.get(dimension, {})
            if peer in dim_weights:
                return float(dim_weights[peer])

        peer_weight = self.global_weights.get(peer, {})
        if isinstance(peer_weight, Mapping):
            return float(peer_weight.get("multiplier", 1.0))
        return float(peer_weight or 1.0)

    def map_for_dimension(self, dimension: str) -> Dict[str, float]:
        weight_map: Dict[str, float] = {}
        for peer in self.global_weights:
            weight_map[peer] = self.multiplier(peer)
        for peer in self.per_dimension_weights.get(dimension, {}):
            weight_map[peer] = self.multiplier(peer, dimension)
        return weight_map


@dataclass
class OutputSettings:
    """Resolved output/report flags for a completed analysis run."""

    include_preset_comparison: bool = False
    include_impact_summary: bool = False
    include_calculated_metrics: bool = False
    include_privacy_validation: bool = False
    include_audit_log: bool = True
    output_format: str = "analysis"
    fraud_in_bps: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]


@dataclass
class RunSummary:
    """Core run facts shared by share and rate analysis."""

    entity: str = "PEER-ONLY"
    entity_column: str = "issuer_name"
    total_records: int = 0
    unique_entities: int = 0
    peer_count: int = 0
    dimensions_analyzed: int = 0
    dimension_names: List[str] = field(default_factory=list)
    preset: Optional[str] = None
    compliance_posture: Optional[str] = None
    debug_mode: bool = False
    consistent_weights: bool = True
    output_format: str = "analysis"
    timestamp: Optional[datetime] = None
    privacy_rule: Optional[str] = None

    def to_metadata_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AnalysisPlan:
    """Typed analysis lifecycle plan derived from a request and resolved config."""

    request: AnalysisRunRequest
    resolved_config: Any
    entity: Optional[str]
    entity_column: str
    dimensions: List[str]
    metric_columns: Dict[str, str]
    output_settings: OutputSettings


@dataclass
class AnalysisResult:
    """Typed domain result before rendering to reports/audit artifacts."""

    plan: AnalysisPlan
    weighting: WeightingResult
    privacy_validation: Any
    data_quality: Any
    results: Any
    compliance_summary: Dict[str, Any]


@dataclass
class DiagnosticFrames:
    """Diagnostic DataFrames collected after weight optimization."""

    structural_summary_df: Any = None
    structural_detail_df: Any = None
    rank_changes_df: Any = None
    subset_search_df: Any = None
    weights_df: Any = None
    privacy_validation_df: Any = None
    method_breakdown_df: Any = None

    def metadata_updates(self) -> Dict[str, Any]:
        updates: Dict[str, Any] = {}
        if self.structural_summary_df is not None and hasattr(self.structural_summary_df, "empty"):
            if not self.structural_summary_df.empty:
                updates["structural_summary_df"] = self.structural_summary_df
        if self.structural_detail_df is not None and hasattr(self.structural_detail_df, "empty"):
            if not self.structural_detail_df.empty:
                updates["structural_detail_df"] = self.structural_detail_df
        if self.rank_changes_df is not None and hasattr(self.rank_changes_df, "empty"):
            if not self.rank_changes_df.empty:
                updates["rank_changes_df"] = self.rank_changes_df
        if self.subset_search_df is not None and hasattr(self.subset_search_df, "empty"):
            if not self.subset_search_df.empty:
                updates["subset_search_df"] = self.subset_search_df
        return updates


def weighting_result_from_analyzer(analyzer: Any) -> WeightingResult:
    """Build a WeightingResult snapshot from analyzer side-effect fields."""
    return WeightingResult(
        global_weights=dict(getattr(analyzer, "global_weights", {}) or {}),
        per_dimension_weights={
            dim: dict(weights)
            for dim, weights in (getattr(analyzer, "per_dimension_weights", {}) or {}).items()
        },
        weight_methods=dict(getattr(analyzer, "weight_methods", {}) or {}),
        last_lp_stats=dict(getattr(analyzer, "last_lp_stats", {}) or {}),
        privacy_rule_name=getattr(analyzer, "privacy_rule_name", None),
        removed_dimensions=list(getattr(analyzer, "removed_dimensions", []) or []),
        global_dimensions_used=list(getattr(analyzer, "global_dimensions_used", []) or []),
        rank_changes_df=getattr(analyzer, "rank_changes_df", None),
        structural_summary_df=getattr(analyzer, "structural_summary_df", None),
        structural_detail_df=getattr(analyzer, "structural_detail_df", None),
        subset_search_results=list(getattr(analyzer, "subset_search_results", []) or []),
        compliance_blocked_reason=getattr(analyzer, "compliance_blocked_reason", None),
        compliance_blocked_peer_count=getattr(analyzer, "compliance_blocked_peer_count", None),
        additional_constraint_violations=list(
            getattr(analyzer, "additional_constraint_violations", []) or []
        ),
        slack_subset_triggered=bool(getattr(analyzer, "slack_subset_triggered", False)),
        compliance_state=getattr(
            analyzer,
            "weighting_compliance_state",
            WeightingComplianceState(
                rule_name=getattr(analyzer, "privacy_rule_name", None),
                secondary_rule_passed=not bool(getattr(analyzer, "additional_constraint_violations", []) or []),
                relaxation_used=bool(getattr(analyzer, "dynamic_constraints_enabled", False)),
                residual_violations=len(getattr(analyzer, "additional_constraint_violations", []) or []),
            ),
        ),
    )


def apply_weighting_result_to_analyzer(analyzer: Any, result: WeightingResult) -> None:
    """Apply WeightingResult fields onto analyzer for backward-compatible readers."""
    analyzer.global_weights = dict(result.global_weights)
    analyzer.per_dimension_weights = {
        dim: dict(weights) for dim, weights in result.per_dimension_weights.items()
    }
    analyzer.weight_methods = dict(result.weight_methods)
    analyzer.last_lp_stats = dict(result.last_lp_stats)
    analyzer.privacy_rule_name = result.privacy_rule_name
    analyzer.removed_dimensions = list(result.removed_dimensions)
    analyzer.global_dimensions_used = list(result.global_dimensions_used)
    analyzer.rank_changes_df = result.rank_changes_df
    analyzer.structural_summary_df = result.structural_summary_df
    analyzer.structural_detail_df = result.structural_detail_df
    analyzer.subset_search_results = list(result.subset_search_results)
    analyzer.compliance_blocked_reason = result.compliance_blocked_reason
    analyzer.compliance_blocked_peer_count = result.compliance_blocked_peer_count
    analyzer.additional_constraint_violations = list(result.additional_constraint_violations)
    analyzer.slack_subset_triggered = result.slack_subset_triggered
    analyzer.weighting_compliance_state = result.compliance_state
