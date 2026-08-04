"""Shared data contracts for analysis orchestration."""

from __future__ import annotations

import argparse
import math
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Tuple

from core.control3_policy import CONTROL3_POLICY_KEYS


DEFAULT_PRESET_NAME = "compliance_strict"

APPROVED_PRIVACY_RULE_NAMES = ("5/25", "6/30", "7/35", "10/40", "4/35")
CONTROL3_NUMERIC_POLICY_VERSION = "v5 (2026-06-03)"
CONTROL3_NUMERIC_POLICY_SOURCE = (
    "docs/control-3-customer-merchant-performance-v5-20260603.md"
)
# Fixed versioned artifact_type for the client-safe CoverageCertificate. The
# version suffix is part of the client contract; changing it is a breaking
# change to downstream consumers of the certificate.
COVERAGE_CERTIFICATE_ARTIFACT_TYPE = "coverage_certificate.v1"


class PrivacyMetricContext(str, Enum):
    """Metric context needed to validate the concentration basis."""

    OTHER = "other"
    ISSUER_FRAUD = "issuer_fraud"
    ISSUER_CHARGEBACK = "issuer_chargeback"


class PrivacyConcentrationBasis(str, Enum):
    """Basis used to compute the supplied concentration evidence."""

    BENCHMARK_METRIC = "benchmark_metric"
    CLEARING_SPEND = "clearing_spend"


class PrivacyEvaluationStatus(str, Enum):
    """Outcome for a rule or mandatory overlay."""

    PASSED = "passed"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


class PrivacySweepStatus(str, Enum):
    """Scope-aware outcome of the numeric-rule sweep and its overlays."""

    NOT_SUBJECT = "not_subject_to_benchmark_numeric_rules"
    NUMERICALLY_COMPLIANT = "numerically_compliant"
    NUMERICALLY_NONCOMPLIANT = "numerically_noncompliant"
    INVALID_EVIDENCE = "invalid_or_incomplete_evidence"
    BLOCKED_BY_MANDATORY_OVERLAY = "blocked_by_mandatory_overlay"


class PrivacyRuleStrategy(str, Enum):
    """Rule-selection strategy used by the normal analysis pipeline."""

    SELECT_BY_PEER_COUNT = "select_by_peer_count"
    SWEEP_ANY_APPLICABLE = "sweep_any_applicable"


class PrivacyReleaseMode(str, Enum):
    """Which safe Publication Units can reach client output.

    The mode is orthogonal to ``PrivacyRuleStrategy`` and to
    ``compliance_posture``. ``COMPLETE_OUTPUT`` preserves current behavior
    exactly. ``MAXIMIZE_SAFE_COVERAGE`` releases the maximum proven-safe
    subset for share analysis without weakening any privacy rule.
    """

    COMPLETE_OUTPUT = "complete-output"
    MAXIMIZE_SAFE_COVERAGE = "maximize-safe-coverage"


@dataclass(frozen=True)
class PrivacyRuleStrategyEvaluation:
    """One rule-specific optimization attempt in an integrated analysis run."""

    rule_name: str
    status: PrivacyEvaluationStatus
    failure_reasons: Tuple[PrivacyFailureReason, ...] = ()


@dataclass(frozen=True)
class PrivacyRuleStrategyResult:
    """Immutable audit result for the normal pipeline's rule strategy."""

    strategy: PrivacyRuleStrategy
    is_anonymized_aggregated_merchant_spend: bool
    status: PrivacySweepStatus
    numeric_rules_passed: bool
    mandatory_overlays_passed: bool
    publication_authorized_by_numeric_policy: bool
    display_rule: Optional[str]
    feasible_candidate_rules: Tuple[str, ...]
    authorizing_rules: Tuple[str, ...]
    candidate_attempt_evaluations: Tuple[PrivacyRuleStrategyEvaluation, ...]
    emitted_output_evaluations: Tuple[PrivacyRuleStrategyEvaluation, ...]
    mandatory_overlay_evaluations: Tuple[PrivacyMandatoryOverlayEvaluation, ...]
    rule_set_digest: str
    policy_version: str = CONTROL3_NUMERIC_POLICY_VERSION
    policy_source: str = CONTROL3_NUMERIC_POLICY_SOURCE

    def __post_init__(self) -> None:
        """Reject contradictory strategy verdicts before they reach a sink."""
        canonical_rules = set(APPROVED_PRIVACY_RULE_NAMES)
        passed_attempts = {
            evaluation.rule_name
            for evaluation in self.candidate_attempt_evaluations
            if evaluation.status == PrivacyEvaluationStatus.PASSED
        }
        passed_emitted = {
            evaluation.rule_name
            for evaluation in self.emitted_output_evaluations
            if evaluation.status == PrivacyEvaluationStatus.PASSED
        }
        overlays_passed = bool(self.mandatory_overlay_evaluations) and all(
            evaluation.status != PrivacyEvaluationStatus.FAILED
            for evaluation in self.mandatory_overlay_evaluations
        )
        expected_authorizers = tuple(
            rule
            for rule in APPROVED_PRIVACY_RULE_NAMES
            if rule in passed_emitted
        )
        if not overlays_passed:
            expected_authorizers = ()
        expected_status = (
            PrivacySweepStatus.NUMERICALLY_COMPLIANT
            if expected_authorizers
            else (
                PrivacySweepStatus.BLOCKED_BY_MANDATORY_OVERLAY
                if passed_emitted and not overlays_passed
                else PrivacySweepStatus.NUMERICALLY_NONCOMPLIANT
            )
        )
        coherent = (
            isinstance(
                self.is_anonymized_aggregated_merchant_spend,
                bool,
            )
            and
            bool(self.candidate_attempt_evaluations)
            and bool(self.emitted_output_evaluations)
            and len(set(self.feasible_candidate_rules))
            == len(self.feasible_candidate_rules)
            and len(set(self.authorizing_rules))
            == len(self.authorizing_rules)
            and len(
                {
                    evaluation.rule_name
                    for evaluation in self.candidate_attempt_evaluations
                }
            )
            == len(self.candidate_attempt_evaluations)
            and len(
                {
                    evaluation.rule_name
                    for evaluation in self.emitted_output_evaluations
                }
            )
            == len(self.emitted_output_evaluations)
            and set(self.feasible_candidate_rules) == passed_attempts
            and set(self.feasible_candidate_rules) <= canonical_rules
            and passed_emitted <= canonical_rules
            and self.authorizing_rules == expected_authorizers
            and self.numeric_rules_passed == bool(passed_emitted)
            and self.mandatory_overlays_passed == overlays_passed
            and self.publication_authorized_by_numeric_policy
            == bool(expected_authorizers)
            and self.status == expected_status
            and len(self.rule_set_digest) == 64
            and all(
                character in "0123456789abcdef"
                for character in self.rule_set_digest
            )
        )
        if not coherent:
            raise ValueError(
                "PrivacyRuleStrategyResult contains contradictory publication fields"
            )


@dataclass(frozen=True)
class PrivacyOutputDecision:
    """Final non-overridable Control 3 decision for disk output."""

    privacy_publication_authorized: bool
    hard_privacy_block: bool
    withholding_reason: Optional[str] = None

    def __post_init__(self) -> None:
        """Reject contradictory publication decisions at the contract boundary."""
        authorized = (
            self.privacy_publication_authorized
            and not self.hard_privacy_block
            and self.withholding_reason is None
        )
        blocked = (
            not self.privacy_publication_authorized
            and self.hard_privacy_block
            and bool(self.withholding_reason)
        )
        if not (authorized or blocked):
            raise ValueError(
                "PrivacyOutputDecision must be either affirmatively authorized "
                "or hard-blocked with a withholding reason"
            )


@dataclass(frozen=True)
class PrivacySweepRequest:
    """Compact server-side evidence for a Control 3.2 privacy-rule sweep.

    Threshold counts are cumulative. For example, a participant counted at
    20 percent is also included in every lower-threshold count.
    """

    contains_peer_benchmark_data: Optional[bool]
    is_anonymized_aggregated_merchant_spend: Optional[bool]
    metric_context: Optional[PrivacyMetricContext]
    concentration_basis: Optional[PrivacyConcentrationBasis]
    participant_count: Optional[int] = None
    maximum_share_percentage: Optional[float] = None
    count_at_or_above_7_percent: Optional[int] = None
    count_at_or_above_8_percent: Optional[int] = None
    count_at_or_above_10_percent: Optional[int] = None
    count_at_or_above_15_percent: Optional[int] = None
    count_at_or_above_20_percent: Optional[int] = None
    citibank_included: Optional[bool] = None
    citi_competitor_receives_output: Optional[bool] = None
    citibank_share_percentage: Optional[float] = None


@dataclass(frozen=True)
class PrivacyFailureReason:
    """Machine-readable privacy failure without entity-level information."""

    code: str
    message: str
    field: Optional[str] = None


@dataclass(frozen=True)
class PrivacyThresholdEvaluation:
    """One normalized cumulative threshold-count requirement."""

    threshold_percentage: float
    required_count: int
    observed_count: int
    compliant: bool


@dataclass(frozen=True)
class PrivacyRuleSweepEvaluation:
    """Diagnostic evaluation of compact evidence against one privacy rule."""

    rule_name: str
    status: PrivacyEvaluationStatus
    minimum_entities: int
    maximum_share_percentage: float
    threshold_evaluations: Tuple[PrivacyThresholdEvaluation, ...]
    inapplicability_reasons: Tuple[PrivacyFailureReason, ...]
    failure_reasons: Tuple[PrivacyFailureReason, ...]

    @property
    def applicable(self) -> bool:
        return self.status != PrivacyEvaluationStatus.NOT_APPLICABLE

    @property
    def strict_passed(self) -> bool:
        return self.status == PrivacyEvaluationStatus.PASSED


@dataclass(frozen=True)
class PrivacyMandatoryOverlayEvaluation:
    """Mandatory condition applied after one or more base rules pass."""

    overlay_name: str
    status: PrivacyEvaluationStatus
    maximum_share_percentage: float
    failure_reasons: Tuple[PrivacyFailureReason, ...]


@dataclass(frozen=True)
class PrivacySweepAuditMetadata:
    """Stable policy metadata for audit consumers."""

    policy_name: str
    policy_version: str
    policy_source: str
    rule_set_digest: str
    decision_method: str
    evidence_valid: bool
    evaluated_rules: Tuple[str, ...]
    other_control_review_required: bool
    recheck_after_peer_group_change_required: bool
    annual_recheck_required: bool


@dataclass(frozen=True)
class PrivacySweepResult:
    """Scoped numeric-policy outcome; not a blanket Control 3 verdict."""

    status: PrivacySweepStatus
    numeric_rules_passed: Optional[bool]
    mandatory_overlays_passed: Optional[bool]
    numeric_policy_passed: Optional[bool]
    authorizing_rules: Tuple[str, ...]
    failure_reasons: Tuple[PrivacyFailureReason, ...]
    rule_evaluations: Tuple[PrivacyRuleSweepEvaluation, ...]
    mandatory_overlays: Tuple[PrivacyMandatoryOverlayEvaluation, ...]
    audit: PrivacySweepAuditMetadata


def _freeze_str_mapping(
    mapping: Mapping[str, Any],
    *,
    field_name: str,
    value_cast: Optional[Any] = None,
) -> Mapping[str, Any]:
    """Return a read-only Mapping copy with normalized string keys.

    ``field_name`` is the outer contract field name and is only used to
    produce clear error messages when validation fails.
    """
    if not isinstance(mapping, Mapping):
        raise TypeError(f"{field_name} must be a Mapping[str, ...] value")
    frozen: Dict[str, Any] = {}
    for key, value in mapping.items():
        if not isinstance(key, str):
            raise TypeError(
                f"{field_name} keys must be strings; got {type(key).__name__}"
            )
        if value_cast is not None:
            frozen[key] = value_cast(value)
        else:
            frozen[key] = value
    return MappingProxyType(frozen)


@dataclass(frozen=True)
class PublicationUnit:
    """One all-or-nothing client output cell for share analysis.

    A Publication Unit groups every governed metric record that shares the
    same canonical output key. It is the atomic unit that
    ``PrivacyReleaseMode.MAXIMIZE_SAFE_COVERAGE`` releases or suppresses.
    """

    internal_key: str
    dimension: str
    category: str
    time_period: Optional[str]
    output_scope: Optional[str]
    metric_records: Tuple[Mapping[str, Any], ...]
    applicable_rules: Tuple[str, ...]
    mandatory_overlays: Tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.internal_key, str) or not self.internal_key:
            raise ValueError("PublicationUnit.internal_key must be a non-empty string")
        if not isinstance(self.dimension, str) or not self.dimension:
            raise ValueError("PublicationUnit.dimension must be a non-empty string")
        if not isinstance(self.category, str) or not self.category:
            raise ValueError("PublicationUnit.category must be a non-empty string")
        if self.time_period is not None and not isinstance(self.time_period, str):
            raise TypeError("PublicationUnit.time_period must be a string or None")
        if self.output_scope is not None and not isinstance(self.output_scope, str):
            raise TypeError("PublicationUnit.output_scope must be a string or None")
        if not isinstance(self.metric_records, tuple):
            raise TypeError("PublicationUnit.metric_records must be a tuple")
        if not self.metric_records:
            raise ValueError("PublicationUnit.metric_records must not be empty")
        frozen_records: Tuple[Mapping[str, Any], ...] = tuple(
            _freeze_str_mapping(record, field_name="PublicationUnit.metric_records")
            for record in self.metric_records
        )
        object.__setattr__(self, "metric_records", frozen_records)
        if not isinstance(self.applicable_rules, tuple):
            raise TypeError("PublicationUnit.applicable_rules must be a tuple")
        if len(set(self.applicable_rules)) != len(self.applicable_rules):
            raise ValueError(
                "PublicationUnit.applicable_rules must not contain duplicates"
            )
        if not isinstance(self.mandatory_overlays, tuple):
            raise TypeError("PublicationUnit.mandatory_overlays must be a tuple")
        if len(set(self.mandatory_overlays)) != len(self.mandatory_overlays):
            raise ValueError(
                "PublicationUnit.mandatory_overlays must not contain duplicates"
            )


@dataclass(frozen=True)
class SafeCoverageResult:
    """Trusted internal result of the Maximum Safe Coverage optimization.

    This object can hold protected internal keys and must never reach a
    normal client sink. The client-safe view is ``CoverageCertificate``.
    """

    release_mode: PrivacyReleaseMode
    global_weights: Mapping[str, float]
    candidate_universe: Tuple[PublicationUnit, ...]
    release_set: Tuple[str, ...]
    suppression_set: Tuple[str, ...]
    authorizing_rules: Mapping[str, str]
    primary_objective_value: int
    later_objective_values: Tuple[float, ...]
    solver_state: str
    mip_dual_bound: float
    mip_gap: float
    solver_name: str
    solver_version: str
    input_digest: str
    configuration_digest: str
    policy_version: str
    policy_source: str
    rule_set_digest: str
    candidate_universe_digest: str
    release_mask_digest: str
    verifier_result: str

    def __post_init__(self) -> None:
        if not isinstance(self.release_mode, PrivacyReleaseMode):
            raise TypeError(
                "SafeCoverageResult.release_mode must be a PrivacyReleaseMode value"
            )
        if not isinstance(self.candidate_universe, tuple):
            raise TypeError("SafeCoverageResult.candidate_universe must be a tuple")
        for unit in self.candidate_universe:
            if not isinstance(unit, PublicationUnit):
                raise TypeError(
                    "SafeCoverageResult.candidate_universe must contain PublicationUnit values"
                )
        candidate_keys = tuple(unit.internal_key for unit in self.candidate_universe)
        candidate_key_set = set(candidate_keys)
        if len(candidate_key_set) != len(candidate_keys):
            raise ValueError(
                "SafeCoverageResult.candidate_universe must not contain duplicate keys"
            )
        if not isinstance(self.release_set, tuple):
            raise TypeError("SafeCoverageResult.release_set must be a tuple")
        if not isinstance(self.suppression_set, tuple):
            raise TypeError("SafeCoverageResult.suppression_set must be a tuple")
        release_key_set = set(self.release_set)
        suppression_key_set = set(self.suppression_set)
        if len(release_key_set) != len(self.release_set):
            raise ValueError(
                "SafeCoverageResult.release_set must not contain duplicates"
            )
        if len(suppression_key_set) != len(self.suppression_set):
            raise ValueError(
                "SafeCoverageResult.suppression_set must not contain duplicates"
            )
        if release_key_set & suppression_key_set:
            raise ValueError(
                "SafeCoverageResult release and suppression sets must not overlap"
            )
        if release_key_set | suppression_key_set != candidate_key_set:
            raise ValueError(
                "SafeCoverageResult release and suppression sets must partition "
                "the Candidate Universe"
            )
        frozen_weights = _freeze_str_mapping(
            self.global_weights,
            field_name="SafeCoverageResult.global_weights",
            value_cast=float,
        )
        for value in frozen_weights.values():
            if not math.isfinite(value):
                raise ValueError(
                    "SafeCoverageResult.global_weights values must be finite"
                )
        object.__setattr__(self, "global_weights", frozen_weights)
        frozen_authorizing = _freeze_str_mapping(
            self.authorizing_rules,
            field_name="SafeCoverageResult.authorizing_rules",
            value_cast=str,
        )
        if set(frozen_authorizing) != release_key_set:
            raise ValueError(
                "SafeCoverageResult.authorizing_rules must record exactly one "
                "authorizing rule for every released Publication Unit"
            )
        object.__setattr__(self, "authorizing_rules", frozen_authorizing)
        if not isinstance(self.primary_objective_value, int) or isinstance(
            self.primary_objective_value, bool
        ):
            raise TypeError(
                "SafeCoverageResult.primary_objective_value must be an integer"
            )
        if self.primary_objective_value != len(self.release_set):
            raise ValueError(
                "SafeCoverageResult.primary_objective_value must equal the "
                "released Publication Unit count"
            )
        if not isinstance(self.later_objective_values, tuple):
            raise TypeError(
                "SafeCoverageResult.later_objective_values must be a tuple"
            )
        for value in self.later_objective_values:
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(
                    "SafeCoverageResult.later_objective_values must be finite numbers"
                )
        if not math.isfinite(self.mip_dual_bound):
            raise ValueError(
                "SafeCoverageResult.mip_dual_bound must be a finite number"
            )
        if not math.isfinite(self.mip_gap) or self.mip_gap < 0.0:
            raise ValueError(
                "SafeCoverageResult.mip_gap must be finite and non-negative"
            )


@dataclass(frozen=True)
class CoverageCertificate:
    """Client-safe evidence for the exact released artifact.

    This contract must never contain a suppressed key, a per-suppressed-key
    digest, a suppressed category name, or protected source values.
    """

    privacy_release_mode: PrivacyReleaseMode
    candidate_unit_count: int
    released_unit_count: int
    suppressed_unit_count: int
    coverage_percentage: float
    visible_publication_unit_keys: Tuple[str, ...]
    authorizing_rules: Mapping[str, str]
    global_weights: Optional[Mapping[str, float]]
    policy_version: str
    policy_source: str
    rule_set_digest: str
    solver_name: str
    solver_version: str
    primary_objective_value: int
    mip_dual_bound: float
    mip_gap: float
    solver_state: str
    artifact_hashes: Mapping[str, str]
    certificate_digest: str
    artifact_type: str = COVERAGE_CERTIFICATE_ARTIFACT_TYPE

    def __post_init__(self) -> None:
        if self.artifact_type != COVERAGE_CERTIFICATE_ARTIFACT_TYPE:
            raise ValueError(
                "CoverageCertificate.artifact_type must be "
                f"{COVERAGE_CERTIFICATE_ARTIFACT_TYPE!r}"
            )
        if not isinstance(self.privacy_release_mode, PrivacyReleaseMode):
            raise TypeError(
                "CoverageCertificate.privacy_release_mode must be a PrivacyReleaseMode value"
            )
        counts = (
            self.candidate_unit_count,
            self.released_unit_count,
            self.suppressed_unit_count,
        )
        for count in counts:
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise ValueError(
                    "CoverageCertificate unit counts must be non-negative integers"
                )
        if self.released_unit_count + self.suppressed_unit_count != self.candidate_unit_count:
            raise ValueError(
                "CoverageCertificate released and suppressed counts must sum to "
                "the candidate count"
            )
        if not isinstance(self.visible_publication_unit_keys, tuple):
            raise TypeError(
                "CoverageCertificate.visible_publication_unit_keys must be a tuple"
            )
        if len(set(self.visible_publication_unit_keys)) != len(
            self.visible_publication_unit_keys
        ):
            raise ValueError(
                "CoverageCertificate.visible_publication_unit_keys must not contain duplicates"
            )
        if len(self.visible_publication_unit_keys) != self.released_unit_count:
            raise ValueError(
                "CoverageCertificate.visible_publication_unit_keys length must "
                "equal released_unit_count"
            )
        if not math.isfinite(self.coverage_percentage) or not 0.0 <= self.coverage_percentage <= 100.0:
            raise ValueError(
                "CoverageCertificate.coverage_percentage must be between 0.0 and 100.0"
            )
        if self.candidate_unit_count == 0:
            expected_pct = 0.0
        else:
            expected_pct = 100.0 * self.released_unit_count / self.candidate_unit_count
        if not math.isclose(
            self.coverage_percentage, expected_pct, rel_tol=1e-9, abs_tol=1e-9
        ):
            raise ValueError(
                "CoverageCertificate.coverage_percentage must match "
                "released_unit_count / candidate_unit_count"
            )
        frozen_authorizing = _freeze_str_mapping(
            self.authorizing_rules,
            field_name="CoverageCertificate.authorizing_rules",
            value_cast=str,
        )
        if set(frozen_authorizing) != set(self.visible_publication_unit_keys):
            raise ValueError(
                "CoverageCertificate.authorizing_rules keys must equal the "
                "visible Publication Unit keys"
            )
        object.__setattr__(self, "authorizing_rules", frozen_authorizing)
        if self.global_weights is not None:
            frozen_weights = _freeze_str_mapping(
                self.global_weights,
                field_name="CoverageCertificate.global_weights",
                value_cast=float,
            )
            for value in frozen_weights.values():
                if not math.isfinite(value):
                    raise ValueError(
                        "CoverageCertificate.global_weights values must be finite"
                    )
            object.__setattr__(self, "global_weights", frozen_weights)
        if not isinstance(self.primary_objective_value, int) or isinstance(
            self.primary_objective_value, bool
        ):
            raise TypeError(
                "CoverageCertificate.primary_objective_value must be an integer"
            )
        if self.primary_objective_value != self.released_unit_count:
            raise ValueError(
                "CoverageCertificate.primary_objective_value must equal released_unit_count"
            )
        if not math.isfinite(self.mip_dual_bound):
            raise ValueError(
                "CoverageCertificate.mip_dual_bound must be a finite number"
            )
        if not math.isfinite(self.mip_gap) or self.mip_gap < 0.0:
            raise ValueError(
                "CoverageCertificate.mip_gap must be finite and non-negative"
            )
        frozen_hashes = _freeze_str_mapping(
            self.artifact_hashes,
            field_name="CoverageCertificate.artifact_hashes",
            value_cast=str,
        )
        object.__setattr__(self, "artifact_hashes", frozen_hashes)


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
    protected_entity_caps: Dict[str, float] = field(default_factory=dict)
    enforce_additional_constraints: bool = False
    dynamic_constraints_enabled: bool = False
    time_column: Optional[str] = None
    min_peer_count_for_constraints: int = 4
    # Effective peer count is a weighted (fractional) measure, hence float.
    min_effective_peer_count: float = 3.0
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
    preset: Optional[str] = DEFAULT_PRESET_NAME
    config: Optional[str] = None
    output: Optional[str] = None
    time_col: Optional[str] = None
    log_level: str = "INFO"
    validate_input: bool = True
    validate_export: Optional[bool] = None
    analyze_distortion: bool = False
    compare_presets: bool = False
    include_calculated: bool = False
    audit_package: bool = False
    output_format: str = "analysis"
    report_format: Optional[str] = None
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
    privacy_rule_strategy: PrivacyRuleStrategy = PrivacyRuleStrategy.SELECT_BY_PEER_COUNT
    privacy_release_mode: Optional[PrivacyReleaseMode] = None
    is_anonymized_aggregated_merchant_spend: bool = False
    citibank_entity_name: Optional[str] = None
    citi_competitor_receives_output: bool = False
    control3_overrides: Dict[str, Any] = field(default_factory=dict)
    prepared_dataset: Optional["PreparedDataset"] = None

    def __post_init__(self) -> None:
        if not self.preset:
            self.preset = DEFAULT_PRESET_NAME
        # The Python Interface accepts enum values or None only. Reject bare
        # strings so a typo like "maximize-safe-coverage" cannot silently reach
        # the orchestration seam and bypass configuration precedence.
        if self.privacy_release_mode is not None and not isinstance(
            self.privacy_release_mode, PrivacyReleaseMode
        ):
            raise TypeError(
                "AnalysisRunRequest.privacy_release_mode must be a "
                "PrivacyReleaseMode value or None; got "
                f"{type(self.privacy_release_mode).__name__}"
            )

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
        if getattr(ns, "privacy_rule_sweep", False):
            kwargs["privacy_rule_strategy"] = PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE
        return cls(**kwargs)

    @classmethod
    def from_widget_values(cls, mode: str, values: Dict[str, Any]) -> "AnalysisRunRequest":
        """Build a request from a flat dict of TUI widget values.

        Keys mirror the dataclass field names. Missing keys take dataclass
        defaults, keeping TUI behavior aligned with CLI defaults.
        """
        field_names = {f.name for f in fields(cls)}
        unknown = set(values) - field_names
        if unknown:
            raise ValueError(f"Unknown request fields from TUI: {sorted(unknown)}")
        return cls(mode=mode, **{k: v for k, v in values.items() if k in field_names and k != "mode"})


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
    audit_log_output: Optional[str] = None
    audit_package_output: Optional[str] = None
    publication_output: Optional[str] = None
    report_model: Any = None
    json_output: Optional[str] = None
    privacy_rule_strategy_result: Optional[PrivacyRuleStrategyResult] = None
    privacy_output_decision: Optional[PrivacyOutputDecision] = None
    privacy_sink_authorized: bool = False
    privacy_log_authorized: bool = False
    safe_coverage_result: Optional[SafeCoverageResult] = None
    coverage_certificate: Optional[CoverageCertificate] = None
    coverage_certificate_output: Optional[str] = None


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
    include_audit_package: bool = False
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
