"""Privacy policy facade wrapping PrivacyValidator rule selection."""

from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .constants import COMPARISON_EPSILON
from .contracts import (
    PrivacyConcentrationBasis,
    PrivacyEvaluationStatus,
    PrivacyFailureReason,
    PrivacyMandatoryOverlayEvaluation,
    PrivacyMetricContext,
    PrivacyRuleSweepEvaluation,
    PrivacySweepAuditMetadata,
    PrivacySweepRequest,
    PrivacySweepResult,
    PrivacySweepStatus,
    PrivacyThresholdEvaluation,
)
from .privacy_rules import privacy_rule_from_config
from .privacy_validator import PrivacyValidator

logger = logging.getLogger(__name__)

__all__ = ["evaluate_privacy_rule_sweep"]

_SWEEP_RULES = ("5/25", "6/30", "7/35", "10/40", "4/35")
_THRESHOLD_FIELDS = (
    (7.0, "count_at_or_above_7_percent"),
    (8.0, "count_at_or_above_8_percent"),
    (10.0, "count_at_or_above_10_percent"),
    (15.0, "count_at_or_above_15_percent"),
    (20.0, "count_at_or_above_20_percent"),
)
_CITIBANK_MAXIMUM_SHARE = 25.0


@dataclass
class PrivacyPolicySettings:
    """Settings bundle for dynamic constraint evaluation."""

    enforce_additional_constraints: bool = False
    dynamic_constraints_enabled: bool = False
    min_peer_count_for_constraints: int = 6
    # Effective peer count is a weighted (fractional) measure, hence float.
    min_effective_peer_count: float = 3.0
    min_category_volume_share: float = 0.01
    min_overall_volume_share: float = 0.01
    min_representativeness: float = 0.5
    dynamic_threshold_scale_floor: float = 0.5
    dynamic_count_scale_floor: float = 0.5


@dataclass
class ConstraintDecision:
    """Result of additional constraint applicability assessment."""

    enforce: bool = False
    reason: Optional[str] = None
    thresholds: Optional[Dict[str, Any]] = None
    relaxed: bool = False


class PrivacyPolicy:
    """High-level policy facade over PrivacyValidator rules."""

    def __init__(
        self,
        merchant_mode: bool = False,
        time_column: Optional[str] = None,
    ) -> None:
        self.merchant_mode = merchant_mode
        self.time_column = time_column
        self.rule_override: Optional[str] = None

    def select_rule(self, peer_count: int) -> Tuple[str, Dict[str, Any]]:
        rule_name = self.rule_override or PrivacyValidator.select_rule(
            peer_count, merchant_mode=self.merchant_mode
        )
        rule_cfg = PrivacyValidator.get_rule_config(rule_name)
        return rule_name, rule_cfg

    @staticmethod
    def applicable_sweep_rules(
        peer_count: int,
        *,
        is_anonymized_aggregated_merchant_spend: bool,
    ) -> Tuple[str, ...]:
        """Return Control 3 rules applicable to one governed peer population."""
        return tuple(
            rule_name
            for rule_name in _SWEEP_RULES
            if peer_count >= privacy_rule_from_config(rule_name).min_entities
            and (
                rule_name != "4/35"
                or is_anonymized_aggregated_merchant_spend
            )
        )

    @staticmethod
    def sweep_rule_order() -> Tuple[str, ...]:
        """Return the stable evaluation and compatibility tie-break order."""
        return _SWEEP_RULES

    @staticmethod
    def rule_set_digest() -> str:
        """Return the machine-readable digest of the active numeric rules."""
        return _rule_set_digest()

    @staticmethod
    def select_sweep_candidate(
        peer_count: int,
        *,
        merchant_spend_scope: bool,
        publication_safe_rules: Tuple[str, ...],
    ) -> Optional[str]:
        """Choose one whole-run candidate using a compatibility-first tie-break.

        The fallback order is stable implementation behavior, not a policy
        ranking of the approved Control 3 rules.
        """
        legacy_rule = PrivacyValidator.select_rule(
            peer_count,
            merchant_mode=merchant_spend_scope,
        )
        if legacy_rule in publication_safe_rules:
            return legacy_rule
        return next(
            (
                rule_name
                for rule_name in _SWEEP_RULES
                if rule_name in publication_safe_rules
            ),
            None,
        )

    def _dynamic_thresholds(
        self,
        *,
        rule_name: str,
        participants: int,
        representativeness: float,
        settings: Optional[PrivacyPolicySettings] = None,
    ) -> Optional[Dict[str, Any]]:
        if settings is None:
            settings = PrivacyPolicySettings()

        if not settings.enforce_additional_constraints:
            return None
        if not settings.dynamic_constraints_enabled:
            thresholds = PrivacyValidator.get_penalty_thresholds(rule_name)
            return thresholds if thresholds else None

        base_thresholds = PrivacyValidator.get_penalty_thresholds(rule_name)
        if not base_thresholds:
            return None

        if participants < settings.min_peer_count_for_constraints:
            return None

        scale = max(
            settings.dynamic_threshold_scale_floor,
            min(1.0, representativeness / max(settings.min_representativeness, 1e-9)),
        )
        count_scale = max(
            settings.dynamic_count_scale_floor,
            min(1.0, representativeness / max(settings.min_representativeness, 1e-9)),
        )

        adjusted: Dict[str, Any] = {}
        for tier, (count, threshold) in base_thresholds.items():
            adj_count = max(1, int(round(count * count_scale)))
            adj_threshold = threshold * scale
            adjusted[tier] = (adj_count, adj_threshold)
        return adjusted

    def assess_additional_constraints(
        self,
        *,
        rule_name: Optional[str],
        dimension: Optional[str],
        peers: List[str],
        peer_volumes: Dict[str, float],
        stats: Optional[Dict[str, float]] = None,
        settings: Optional[PrivacyPolicySettings] = None,
    ) -> ConstraintDecision:
        if settings is None:
            settings = PrivacyPolicySettings()

        if not settings.enforce_additional_constraints:
            return ConstraintDecision(enforce=False, reason="additional constraints disabled")

        if not rule_name or rule_name == "insufficient":
            return ConstraintDecision(enforce=False, reason=f"rule {rule_name!r} has no additional constraints")

        base_thresholds = PrivacyValidator.get_penalty_thresholds(rule_name)
        if not base_thresholds:
            return ConstraintDecision(enforce=False, reason=f"rule {rule_name!r} has no additional constraints")

        peer_count = len(peers)
        if peer_count < settings.min_peer_count_for_constraints:
            return ConstraintDecision(
                enforce=False,
                reason=f"peer count {peer_count} below minimum {settings.min_peer_count_for_constraints}",
            )

        total_volume = sum(peer_volumes.values()) if peer_volumes else 0.0
        if total_volume <= 0:
            return ConstraintDecision(enforce=False, reason="zero total volume")

        representativeness = 1.0
        if stats:
            representativeness = stats.get("representativeness", 1.0)

        thresholds = self._dynamic_thresholds(
            rule_name=rule_name,
            participants=peer_count,
            representativeness=representativeness,
            settings=settings,
        )

        relaxed = settings.dynamic_constraints_enabled and thresholds != base_thresholds
        return ConstraintDecision(
            enforce=True,
            thresholds=thresholds,
            relaxed=relaxed,
        )


def _failure(code: str, message: str, field: Optional[str] = None) -> PrivacyFailureReason:
    return PrivacyFailureReason(code=code, message=message, field=field)


def _validate_integer(
    value: object,
    field_name: str,
    failures: List[PrivacyFailureReason],
    *,
    positive: bool = False,
) -> Optional[int]:
    if value is None:
        failures.append(_failure("missing_evidence", f"{field_name} is required", field_name))
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        failures.append(_failure("nonnumeric_evidence", f"{field_name} must be an integer", field_name))
        return None
    if value < (1 if positive else 0):
        failures.append(_failure("negative_evidence", f"{field_name} is outside its valid range", field_name))
        return None
    return value


def _validate_percentage(
    value: object,
    field_name: str,
    failures: List[PrivacyFailureReason],
    *,
    required: bool,
) -> Optional[float]:
    if value is None:
        if required:
            failures.append(_failure("missing_evidence", f"{field_name} is required", field_name))
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        failures.append(_failure("nonnumeric_evidence", f"{field_name} must be numeric", field_name))
        return None
    normalized = float(value)
    if not math.isfinite(normalized):
        failures.append(_failure("nonfinite_evidence", f"{field_name} must be finite", field_name))
        return None
    if normalized < 0:
        failures.append(_failure("negative_evidence", f"{field_name} cannot be negative", field_name))
        return None
    if normalized > 100:
        failures.append(_failure("over_100_evidence", f"{field_name} cannot exceed 100 percent", field_name))
        return None
    return normalized


def _validated_evidence(
    request: PrivacySweepRequest,
) -> Tuple[List[PrivacyFailureReason], Optional[int], Optional[float], Dict[float, int], Optional[float]]:
    failures: List[PrivacyFailureReason] = []
    if not isinstance(request.contains_peer_benchmark_data, bool):
        code = "missing_evidence" if request.contains_peer_benchmark_data is None else "invalid_evidence"
        failures.append(
            _failure(
                code,
                "contains_peer_benchmark_data must be explicitly true or false",
                "contains_peer_benchmark_data",
            )
        )
        return failures, None, None, {}, None
    if not request.contains_peer_benchmark_data:
        return failures, None, None, {}, None

    if not isinstance(request.is_anonymized_aggregated_merchant_spend, bool):
        code = (
            "missing_evidence"
            if request.is_anonymized_aggregated_merchant_spend is None
            else "invalid_evidence"
        )
        failures.append(
            _failure(
                code,
                "is_anonymized_aggregated_merchant_spend must be explicitly true or false",
                "is_anonymized_aggregated_merchant_spend",
            )
        )
    if not isinstance(request.metric_context, PrivacyMetricContext):
        code = "missing_evidence" if request.metric_context is None else "invalid_evidence"
        failures.append(_failure(code, "metric_context must use PrivacyMetricContext", "metric_context"))
    if not isinstance(request.concentration_basis, PrivacyConcentrationBasis):
        code = "missing_evidence" if request.concentration_basis is None else "invalid_evidence"
        failures.append(
            _failure(code, "concentration_basis must use PrivacyConcentrationBasis", "concentration_basis")
        )
    elif request.metric_context in (
        PrivacyMetricContext.ISSUER_FRAUD,
        PrivacyMetricContext.ISSUER_CHARGEBACK,
    ) and request.concentration_basis != PrivacyConcentrationBasis.CLEARING_SPEND:
        failures.append(
            _failure(
                "incorrect_concentration_basis",
                "Issuer fraud and chargeback concentration evidence must be computed from clearing spend",
                "concentration_basis",
            )
        )

    participant_count = _validate_integer(
        request.participant_count,
        "participant_count",
        failures,
        positive=True,
    )
    maximum_share = _validate_percentage(
        request.maximum_share_percentage,
        "maximum_share_percentage",
        failures,
        required=True,
    )

    threshold_counts: Dict[float, int] = {}
    for threshold, field_name in _THRESHOLD_FIELDS:
        count = _validate_integer(getattr(request, field_name), field_name, failures)
        if count is not None:
            threshold_counts[threshold] = count

    for field_name in ("citibank_included", "citi_competitor_receives_output"):
        value = getattr(request, field_name)
        if not isinstance(value, bool):
            code = "missing_evidence" if value is None else "invalid_evidence"
            failures.append(_failure(code, f"{field_name} must be explicitly true or false", field_name))
    citi_overlay_applies = (
        request.citibank_included is True
        and request.citi_competitor_receives_output is True
    )
    citibank_share = _validate_percentage(
        request.citibank_share_percentage,
        "citibank_share_percentage",
        failures,
        required=citi_overlay_applies,
    )
    if request.citi_competitor_receives_output is True and request.citibank_included is False:
        failures.append(
            _failure(
                "contradictory_evidence",
                "A Citi competitor recipient cannot trigger the Citi overlay when Citibank is not included",
                "citi_competitor_receives_output",
            )
        )
    if request.citibank_included is False and citibank_share is not None:
        failures.append(
            _failure(
                "contradictory_evidence",
                "citibank_share_percentage was supplied although Citibank is not included",
                "citibank_share_percentage",
            )
        )

    if participant_count is not None:
        for threshold, field_name in _THRESHOLD_FIELDS:
            count = threshold_counts.get(threshold)
            if count is not None and count > participant_count:
                failures.append(
                    _failure(
                        "contradictory_evidence",
                        f"{field_name} cannot exceed participant_count",
                        field_name,
                    )
                )
        if maximum_share is not None and maximum_share * participant_count + COMPARISON_EPSILON < 100.0:
            failures.append(
                _failure(
                    "contradictory_evidence",
                    "participant_count and maximum_share_percentage cannot represent shares totaling 100 percent",
                    "maximum_share_percentage",
                )
            )

    ordered_counts = [threshold_counts.get(threshold) for threshold, _field in _THRESHOLD_FIELDS]
    if all(count is not None for count in ordered_counts):
        concrete_counts = [int(count) for count in ordered_counts if count is not None]
        counts_are_monotonic = not any(
            lower < higher for lower, higher in zip(concrete_counts, concrete_counts[1:])
        )
        if not counts_are_monotonic:
            failures.append(
                _failure(
                    "contradictory_evidence",
                    "threshold counts must be cumulative and nonincreasing as thresholds rise",
                )
            )
        minimum_accounted_share = (
            concrete_counts[4] * 20.0
            + (concrete_counts[3] - concrete_counts[4]) * 15.0
            + (concrete_counts[2] - concrete_counts[3]) * 10.0
            + (concrete_counts[1] - concrete_counts[2]) * 8.0
            + (concrete_counts[0] - concrete_counts[1]) * 7.0
        )
        exact_maximum_floor = 0.0
        if maximum_share is not None:
            attained_band_floor = max(
                (
                    threshold
                    for threshold, count in zip(
                        (7.0, 8.0, 10.0, 15.0, 20.0),
                        concrete_counts,
                    )
                    if count > 0 and maximum_share + COMPARISON_EPSILON >= threshold
                ),
                default=0.0,
            )
            exact_maximum_floor = maximum_share - attained_band_floor
        if minimum_accounted_share + exact_maximum_floor > 100.0 + COMPARISON_EPSILON:
            failures.append(
                _failure(
                    "contradictory_evidence",
                    "threshold counts and the exact maximum imply more than 100 percent total share",
                )
            )
        if counts_are_monotonic and participant_count is not None and maximum_share is not None:
            # At least one participant must attain the declared maximum.
            top_band_count = concrete_counts[4]
            maximum_possible_share = (
                (maximum_share if top_band_count else 0.0)
                + max(top_band_count - 1, 0) * maximum_share
                + (concrete_counts[3] - concrete_counts[4]) * min(maximum_share, 20.0)
                + (concrete_counts[2] - concrete_counts[3]) * min(maximum_share, 15.0)
                + (concrete_counts[1] - concrete_counts[2]) * min(maximum_share, 10.0)
                + (concrete_counts[0] - concrete_counts[1]) * min(maximum_share, 8.0)
                + (participant_count - concrete_counts[0]) * min(maximum_share, 7.0)
            )
            if maximum_possible_share + COMPARISON_EPSILON < 100.0:
                failures.append(
                    _failure(
                        "contradictory_evidence",
                        "threshold counts and maximum share cannot represent shares totaling 100 percent",
                    )
                )

    if maximum_share is not None:
        for threshold, field_name in _THRESHOLD_FIELDS:
            count = threshold_counts.get(threshold)
            if count is None:
                continue
            maximum_reaches_threshold = maximum_share + COMPARISON_EPSILON >= threshold
            if maximum_reaches_threshold != (count > 0):
                failures.append(
                    _failure(
                        "contradictory_evidence",
                        f"{field_name} conflicts with maximum_share_percentage",
                        field_name,
                    )
                )

    if citibank_share is not None and maximum_share is not None:
        if citibank_share > maximum_share + COMPARISON_EPSILON:
            failures.append(
                _failure(
                    "contradictory_evidence",
                    "Citibank share cannot exceed the overall maximum share",
                    "citibank_share_percentage",
                )
            )

    return failures, participant_count, maximum_share, threshold_counts, citibank_share


def _rule_set_digest() -> str:
    active_rules = PrivacyValidator.get_rules()
    serialized = json.dumps(active_rules, sort_keys=True, separators=(",", ":"), default=list)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _evaluate_sweep_rule(
    rule_name: str,
    *,
    participant_count: Optional[int],
    maximum_share: Optional[float],
    threshold_counts: Dict[float, int],
    merchant_spend_scope: Optional[bool],
    evidence_failures: List[PrivacyFailureReason],
) -> PrivacyRuleSweepEvaluation:
    rule = privacy_rule_from_config(rule_name)
    inapplicability_reasons: List[PrivacyFailureReason] = []
    reasons: List[PrivacyFailureReason] = []
    applicable = (
        participant_count is not None
        and participant_count >= rule.min_entities
        and (rule_name != "4/35" or merchant_spend_scope is True)
    )
    if participant_count is None:
        inapplicability_reasons.append(
            _failure(
                "applicability_not_determinable",
                f"{rule_name} applicability requires a valid participant count",
                "participant_count",
            )
        )
    if rule_name == "4/35" and merchant_spend_scope is False:
        inapplicability_reasons.append(
            _failure(
                "rule_not_applicable",
                "4/35 applies only to anonymized and aggregated merchant-spend reports",
                "is_anonymized_aggregated_merchant_spend",
            )
        )
    elif rule_name == "4/35" and merchant_spend_scope is None:
        inapplicability_reasons.append(
            _failure(
                "applicability_not_determinable",
                "4/35 applicability requires explicit merchant-spend scope evidence",
                "is_anonymized_aggregated_merchant_spend",
            )
        )
    if participant_count is not None and participant_count < rule.min_entities:
        inapplicability_reasons.append(
            _failure(
                "minimum_entities_not_met",
                f"{rule_name} requires at least {rule.min_entities} participants",
                "participant_count",
            )
        )

    if evidence_failures and applicable:
        reasons.extend(evidence_failures)
    elif applicable:
        if maximum_share is not None and maximum_share > rule.max_concentration + COMPARISON_EPSILON:
            reasons.append(
                _failure(
                    "maximum_share_exceeded",
                    f"{rule_name} limits every participant to {rule.max_concentration:g} percent",
                    "maximum_share_percentage",
                )
            )
    threshold_evaluations: List[PrivacyThresholdEvaluation] = []
    for _tier, (required_count, threshold) in rule.secondary_requirements.items():
        observed_count = threshold_counts.get(float(threshold), 0)
        compliant = observed_count >= required_count
        threshold_evaluations.append(
            PrivacyThresholdEvaluation(
                threshold_percentage=float(threshold),
                required_count=required_count,
                observed_count=observed_count,
                compliant=compliant,
            )
        )
        if applicable and not evidence_failures and not compliant:
            reasons.append(
                _failure(
                    "threshold_count_not_met",
                    (
                        f"{rule_name} requires {required_count} participants at or above "
                        f"{threshold:g} percent; observed {observed_count}"
                    ),
                    f"count_at_or_above_{threshold:g}_percent",
                )
            )

    status = PrivacyEvaluationStatus.NOT_APPLICABLE
    if applicable:
        status = PrivacyEvaluationStatus.FAILED if reasons else PrivacyEvaluationStatus.PASSED
    return PrivacyRuleSweepEvaluation(
        rule_name=rule_name,
        status=status,
        minimum_entities=rule.min_entities,
        maximum_share_percentage=rule.max_concentration,
        threshold_evaluations=tuple(threshold_evaluations),
        inapplicability_reasons=tuple(inapplicability_reasons),
        failure_reasons=tuple(reasons),
    )


def _evaluate_citibank_overlay(
    request: PrivacySweepRequest,
    citibank_share: Optional[float],
    evidence_failures: List[PrivacyFailureReason],
) -> PrivacyMandatoryOverlayEvaluation:
    overlay_failures: List[PrivacyFailureReason] = []
    applies = request.citibank_included is True and request.citi_competitor_receives_output is True
    if applies:
        if evidence_failures:
            overlay_failures.extend(evidence_failures)
        elif citibank_share is not None and citibank_share > _CITIBANK_MAXIMUM_SHARE + COMPARISON_EPSILON:
            overlay_failures.append(
                _failure(
                    "citibank_maximum_share_exceeded",
                    f"Citibank may represent at most {_CITIBANK_MAXIMUM_SHARE:g} percent",
                    "citibank_share_percentage",
                )
            )
    status = PrivacyEvaluationStatus.NOT_APPLICABLE
    if applies:
        status = PrivacyEvaluationStatus.FAILED if overlay_failures else PrivacyEvaluationStatus.PASSED
    return PrivacyMandatoryOverlayEvaluation(
        overlay_name="citibank_competitor_recipient_25_percent_cap",
        status=status,
        maximum_share_percentage=_CITIBANK_MAXIMUM_SHARE,
        failure_reasons=tuple(overlay_failures),
    )


def _not_subject_evaluations() -> Tuple[PrivacyRuleSweepEvaluation, ...]:
    reason = _failure(
        "not_subject_to_benchmark_numeric_rules",
        "The deliverable contains no peer benchmark data",
        "contains_peer_benchmark_data",
    )
    return tuple(
        PrivacyRuleSweepEvaluation(
            rule_name=rule_name,
            status=PrivacyEvaluationStatus.NOT_APPLICABLE,
            minimum_entities=privacy_rule_from_config(rule_name).min_entities,
            maximum_share_percentage=privacy_rule_from_config(rule_name).max_concentration,
            threshold_evaluations=(),
            inapplicability_reasons=(reason,),
            failure_reasons=(),
        )
        for rule_name in _SWEEP_RULES
    )


def evaluate_privacy_rule_sweep(request: PrivacySweepRequest) -> PrivacySweepResult:
    """Evaluate all rules and authorize when any applicable rule passes.

    A pass covers only the benchmark numeric rules and mandatory Citi overlay.
    Other Control 3 gates and periodic re-check obligations remain external.
    """

    evidence_failures, participant_count, maximum_share, threshold_counts, citibank_share = (
        _validated_evidence(request)
    )

    if request.contains_peer_benchmark_data is False:
        evaluations = _not_subject_evaluations()
    else:
        evaluations = tuple(
            _evaluate_sweep_rule(
                rule_name,
                participant_count=participant_count,
                maximum_share=maximum_share,
                threshold_counts=threshold_counts,
                merchant_spend_scope=request.is_anonymized_aggregated_merchant_spend,
                evidence_failures=evidence_failures,
            )
            for rule_name in _SWEEP_RULES
        )
    citi_overlay = _evaluate_citibank_overlay(request, citibank_share, evidence_failures)
    overlays = (citi_overlay,)
    passing_rules = tuple(
        evaluation.rule_name
        for evaluation in evaluations
        if evaluation.strict_passed
    )
    numeric_rules_passed = bool(passing_rules)
    overlays_passed = citi_overlay.status != PrivacyEvaluationStatus.FAILED
    authorizing_rules = passing_rules if overlays_passed else ()

    if request.contains_peer_benchmark_data is False and not evidence_failures:
        status = PrivacySweepStatus.NOT_SUBJECT
        numeric_result: Optional[bool] = None
        overlay_result: Optional[bool] = None
        numeric_policy_result: Optional[bool] = None
        overall_failures: Tuple[PrivacyFailureReason, ...] = ()
    elif evidence_failures:
        status = PrivacySweepStatus.INVALID_EVIDENCE
        numeric_result = None
        overlay_result = None
        numeric_policy_result = None
        overall_failures = tuple(evidence_failures)
    elif not numeric_rules_passed:
        status = PrivacySweepStatus.NUMERICALLY_NONCOMPLIANT
        numeric_result = False
        overlay_result = overlays_passed
        numeric_policy_result = False
        overall_failures = (
            _failure(
                "no_applicable_rule_passed",
                "None of the applicable Control 3.2 privacy rules passed",
            ),
        )
    elif not overlays_passed:
        status = PrivacySweepStatus.BLOCKED_BY_MANDATORY_OVERLAY
        numeric_result = True
        overlay_result = False
        numeric_policy_result = False
        overall_failures = citi_overlay.failure_reasons
    else:
        status = PrivacySweepStatus.NUMERICALLY_COMPLIANT
        numeric_result = True
        overlay_result = True
        numeric_policy_result = True
        overall_failures = ()

    return PrivacySweepResult(
        status=status,
        numeric_rules_passed=numeric_result,
        mandatory_overlays_passed=overlay_result,
        numeric_policy_passed=numeric_policy_result,
        authorizing_rules=authorizing_rules,
        failure_reasons=overall_failures,
        rule_evaluations=evaluations,
        mandatory_overlays=overlays,
        audit=PrivacySweepAuditMetadata(
            policy_name="Mastercard Control 3.2",
            policy_version="v5 (2026-06-03)",
            policy_source="docs/control-3-customer-merchant-performance-v5-20260603.md",
            rule_set_digest=_rule_set_digest(),
            decision_method="any_applicable_rule_passes",
            evidence_valid=not evidence_failures,
            evaluated_rules=_SWEEP_RULES,
            other_control_review_required=True,
            recheck_after_peer_group_change_required=True,
            annual_recheck_required=True,
        ),
    )
