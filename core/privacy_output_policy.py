"""Control 3 publication boundary for analysis artifacts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

from core.contracts import (
    APPROVED_PRIVACY_RULE_NAMES,
    CONTROL3_NUMERIC_POLICY_SOURCE,
    CONTROL3_NUMERIC_POLICY_VERSION,
    PrivacyEvaluationStatus,
    PrivacyOutputDecision,
    PrivacyRuleStrategy,
    PrivacyRuleStrategyEvaluation,
    PrivacyRuleStrategyResult,
    PrivacySweepStatus,
)
from core.privacy_policy import PrivacyPolicy


CONTROL3_INVALID_EVIDENCE = "control3_invalid_privacy_evidence"
CONTROL3_MANDATORY_OVERLAY_BLOCKED = "control3_mandatory_overlay_blocked"
CONTROL3_NUMERIC_POLICY_BLOCKED = "control3_numeric_policy_blocked"
CONTROL3_POLICY_VERSION = CONTROL3_NUMERIC_POLICY_VERSION
CONTROL3_POLICY_SOURCE = CONTROL3_NUMERIC_POLICY_SOURCE
_CANONICAL_RULES = frozenset(APPROVED_PRIVACY_RULE_NAMES)
_CANONICAL_EVALUATION_RULES = _CANONICAL_RULES | {"insufficient"}
_CANONICAL_OVERLAYS = frozenset({"citibank_maximum_25_percent"})
_CANONICAL_FAILURE_CODES = frozenset(
    {
        "applicability_not_determinable",
        "citibank_concentration_exceeded",
        "citibank_maximum_share_exceeded",
        "contradictory_evidence",
        "emitted_output_rule_failed",
        "incorrect_concentration_basis",
        "maximum_share_exceeded",
        "minimum_entities_not_met",
        "missing_evidence",
        "negative_evidence",
        "no_applicable_rule_passed",
        "nonfinite_evidence",
        "nonnumeric_evidence",
        "not_subject_to_benchmark_numeric_rules",
        "optimization_failed",
        "over_100_evidence",
        "rule_not_applicable",
        "strict_optimization_not_compliant",
        "threshold_count_not_met",
    }
)
_ATTESTATION_NONCE = object()


@dataclass(frozen=True)
class _PrivacyOutputAttestation:
    nonce: object
    result: PrivacyRuleStrategyResult
    decision: PrivacyOutputDecision


def _strategy_result_is_coherent(result: PrivacyRuleStrategyResult) -> bool:
    """Validate every duplicate summary against canonical exact evidence."""
    if (
        not isinstance(result.strategy, PrivacyRuleStrategy)
        or not isinstance(
            result.is_anonymized_aggregated_merchant_spend,
            bool,
        )
        or result.policy_version != CONTROL3_POLICY_VERSION
        or result.policy_source != CONTROL3_POLICY_SOURCE
        or result.rule_set_digest != PrivacyPolicy.rule_set_digest()
        or not re.fullmatch(r"[0-9a-f]{64}", result.rule_set_digest)
        or not result.candidate_attempt_evaluations
        or not result.emitted_output_evaluations
        or len(result.mandatory_overlay_evaluations) != 1
    ):
        return False
    candidate_names = [
        evaluation.rule_name
        for evaluation in result.candidate_attempt_evaluations
    ]
    emitted_names = [
        evaluation.rule_name
        for evaluation in result.emitted_output_evaluations
    ]
    if result.strategy == PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE:
        expected_names = list(PrivacyPolicy.sweep_rule_order())
        if (
            candidate_names != expected_names
            or emitted_names != expected_names
            or result.display_rule not in _CANONICAL_RULES
        ):
            return False
    elif result.strategy == PrivacyRuleStrategy.SELECT_BY_PEER_COUNT:
        if (
            len(candidate_names) != 1
            or candidate_names != emitted_names
            or candidate_names[0] != result.display_rule
        ):
            return False
    else:
        return False
    merchant_evaluations = [
        evaluation
        for evaluation in result.emitted_output_evaluations
        if evaluation.rule_name == "4/35"
    ]
    if (
        merchant_evaluations
        and merchant_evaluations[0].status
        != PrivacyEvaluationStatus.NOT_APPLICABLE
        and not result.is_anonymized_aggregated_merchant_spend
    ):
        return False
    if any(
        evaluation.rule_name not in _CANONICAL_EVALUATION_RULES
        or not isinstance(evaluation.status, PrivacyEvaluationStatus)
        for evaluation in (
            *result.candidate_attempt_evaluations,
            *result.emitted_output_evaluations,
        )
    ):
        return False
    for evaluation in (
        *result.candidate_attempt_evaluations,
        *result.emitted_output_evaluations,
    ):
        if (
            evaluation.status == PrivacyEvaluationStatus.PASSED
            and evaluation.failure_reasons
        ):
            return False
        if (
            evaluation.status != PrivacyEvaluationStatus.PASSED
            and not evaluation.failure_reasons
        ):
            return False
        if any(
            reason.code not in _CANONICAL_FAILURE_CODES
            for reason in evaluation.failure_reasons
        ):
            return False
    if any(
        evaluation.overlay_name not in _CANONICAL_OVERLAYS
        or not isinstance(evaluation.status, PrivacyEvaluationStatus)
        for evaluation in result.mandatory_overlay_evaluations
    ):
        return False
    for overlay_evaluation in result.mandatory_overlay_evaluations:
        if overlay_evaluation.maximum_share_percentage != 25.0:
            return False
        if (
            overlay_evaluation.status == PrivacyEvaluationStatus.FAILED
            and not overlay_evaluation.failure_reasons
        ):
            return False
        if (
            overlay_evaluation.status != PrivacyEvaluationStatus.FAILED
            and overlay_evaluation.failure_reasons
        ):
            return False
        if any(
            reason.code not in _CANONICAL_FAILURE_CODES
            for reason in overlay_evaluation.failure_reasons
        ):
            return False

    passed_attempts = {
        evaluation.rule_name
        for evaluation in result.candidate_attempt_evaluations
        if evaluation.status == PrivacyEvaluationStatus.PASSED
    }
    passed_emitted = {
        evaluation.rule_name
        for evaluation in result.emitted_output_evaluations
        if evaluation.status == PrivacyEvaluationStatus.PASSED
    }
    overlays_passed = all(
        evaluation.status != PrivacyEvaluationStatus.FAILED
        for evaluation in result.mandatory_overlay_evaluations
    )
    expected_authorizers = (
        tuple(
            rule
            for rule in PrivacyPolicy.sweep_rule_order()
            if rule in passed_emitted
        )
        if passed_emitted and overlays_passed
        else ()
    )
    expected_status = (
        PrivacySweepStatus.NUMERICALLY_COMPLIANT
        if expected_authorizers
        else (
            PrivacySweepStatus.BLOCKED_BY_MANDATORY_OVERLAY
            if passed_emitted and not overlays_passed
            else PrivacySweepStatus.NUMERICALLY_NONCOMPLIANT
        )
    )
    return bool(
        len(set(result.feasible_candidate_rules))
        == len(result.feasible_candidate_rules)
        and len(set(result.authorizing_rules))
        == len(result.authorizing_rules)
        and
        set(result.feasible_candidate_rules) == passed_attempts
        and set(result.feasible_candidate_rules) <= _CANONICAL_RULES
        and result.authorizing_rules == expected_authorizers
        and result.numeric_rules_passed == bool(passed_emitted)
        and result.mandatory_overlays_passed == overlays_passed
        and result.publication_authorized_by_numeric_policy
        == bool(expected_authorizers)
        and result.status == expected_status
    )


def _attest_privacy_output(
    result: PrivacyRuleStrategyResult,
    decision: PrivacyOutputDecision,
) -> _PrivacyOutputAttestation | None:
    """Issue an internal sink capability only for verified authorization."""
    if not _strategy_result_is_coherent(result):
        return None
    if decision != decide_privacy_output(result):
        return None
    if not is_privacy_publication_authorized(decision):
        return None
    return _PrivacyOutputAttestation(_ATTESTATION_NONCE, result, decision)


def is_privacy_publication_authorized(
    decision: PrivacyOutputDecision | None,
) -> bool:
    """Return true only for a complete, internally consistent authorization."""
    return bool(
        decision is not None
        and decision.privacy_publication_authorized is True
        and decision.hard_privacy_block is False
        and decision.withholding_reason is None
    )


def decide_privacy_output(result: PrivacyRuleStrategyResult) -> PrivacyOutputDecision:
    """Derive the single hard publication decision from emitted-output evidence."""
    authorized = (
        result.status == PrivacySweepStatus.NUMERICALLY_COMPLIANT
        and result.numeric_rules_passed
        and result.publication_authorized_by_numeric_policy
        and bool(result.authorizing_rules)
        and result.mandatory_overlays_passed
    )
    if authorized:
        return PrivacyOutputDecision(
            privacy_publication_authorized=True,
            hard_privacy_block=False,
        )

    if result.status == PrivacySweepStatus.INVALID_EVIDENCE:
        reason = CONTROL3_INVALID_EVIDENCE
    elif not result.mandatory_overlays_passed:
        reason = CONTROL3_MANDATORY_OVERLAY_BLOCKED
    else:
        reason = CONTROL3_NUMERIC_POLICY_BLOCKED
    return PrivacyOutputDecision(
        privacy_publication_authorized=False,
        hard_privacy_block=True,
        withholding_reason=reason,
    )


def is_verified_privacy_publication_authorized(
    result: PrivacyRuleStrategyResult | None,
    artifact_decision: PrivacyOutputDecision | None,
    supplied_decision: PrivacyOutputDecision | None,
    attestation: _PrivacyOutputAttestation | None = None,
) -> bool:
    """Verify sink authorization against immutable emitted-output evidence."""
    if result is None:
        return False
    if not _strategy_result_is_coherent(result):
        return False
    expected = decide_privacy_output(result)
    return bool(
        is_privacy_publication_authorized(expected)
        and artifact_decision == expected
        and supplied_decision == expected
        and isinstance(attestation, _PrivacyOutputAttestation)
        and attestation.nonce is _ATTESTATION_NONCE
        and attestation.result is result
        and attestation.decision == expected
    )


def _safe_rule_evaluation(
    evaluation: PrivacyRuleStrategyEvaluation,
) -> Dict[str, Any]:
    return {
        "rule_name": (
            evaluation.rule_name
            if evaluation.rule_name in _CANONICAL_EVALUATION_RULES
            else "unknown"
        ),
        "status": (
            evaluation.status.value
            if isinstance(evaluation.status, PrivacyEvaluationStatus)
            else "unknown"
        ),
        "failure_codes": [
            (
                reason.code
                if reason.code in _CANONICAL_FAILURE_CODES
                else "unknown"
            )
            for reason in evaluation.failure_reasons
        ],
    }


def build_non_publishable_privacy_audit(
    result: PrivacyRuleStrategyResult,
    decision: PrivacyOutputDecision,
) -> Dict[str, Any]:
    """Build an allow-listed audit record without benchmark-bearing evidence."""
    applicable_rules = [
        evaluation.rule_name
        for evaluation in result.emitted_output_evaluations
        if evaluation.rule_name in _CANONICAL_RULES
        if evaluation.status != PrivacyEvaluationStatus.NOT_APPLICABLE
    ]
    trusted_digest = PrivacyPolicy.rule_set_digest()
    if not re.fullmatch(r"[0-9a-f]{64}", trusted_digest):
        trusted_digest = "unknown"
    withholding_reason = (
        decision.withholding_reason
        if decision.withholding_reason
        in {
            CONTROL3_INVALID_EVIDENCE,
            CONTROL3_MANDATORY_OVERLAY_BLOCKED,
            CONTROL3_NUMERIC_POLICY_BLOCKED,
        }
        else CONTROL3_INVALID_EVIDENCE
    )
    return {
        "artifact_type": "non_publishable_control3_privacy_audit",
        "publishable": False,
        "run_status": "withheld",
        "withholding_reason": withholding_reason,
        "strategy": (
            result.strategy.value
            if isinstance(result.strategy, PrivacyRuleStrategy)
            else "unknown"
        ),
        "policy_provenance": {
            "policy_version": CONTROL3_POLICY_VERSION,
            "policy_source": CONTROL3_POLICY_SOURCE,
            "rule_set_digest": trusted_digest,
        },
        "applicable_rules": applicable_rules,
        "feasible_candidate_rules": [
            rule
            for rule in result.feasible_candidate_rules
            if rule in _CANONICAL_RULES
        ],
        "authorizing_rules": [
            rule
            for rule in result.authorizing_rules
            if rule in _CANONICAL_RULES
        ],
        "candidate_attempt_evaluations": [
            _safe_rule_evaluation(evaluation)
            for evaluation in result.candidate_attempt_evaluations
        ],
        "emitted_output_evaluations": [
            _safe_rule_evaluation(evaluation)
            for evaluation in result.emitted_output_evaluations
        ],
        "mandatory_overlay_evaluations": [
            {
                "overlay_name": (
                    evaluation.overlay_name
                    if evaluation.overlay_name in _CANONICAL_OVERLAYS
                    else "unknown"
                ),
                "status": (
                    evaluation.status.value
                    if isinstance(
                        evaluation.status,
                        PrivacyEvaluationStatus,
                    )
                    else "unknown"
                ),
                "failure_codes": [
                    (
                        reason.code
                        if reason.code in _CANONICAL_FAILURE_CODES
                        else "unknown"
                    )
                    for reason in evaluation.failure_reasons
                ],
            }
            for evaluation in result.mandatory_overlay_evaluations
        ],
    }


def write_non_publishable_privacy_audit(
    analysis_output_file: str,
    result: PrivacyRuleStrategyResult,
    decision: PrivacyOutputDecision,
) -> str:
    """Atomically persist the safe denial audit beside the requested output."""
    requested = Path(analysis_output_file)
    audit_path = requested.with_name(
        "autobench_NON_PUBLISHABLE_control3_"
        f"{uuid4().hex}.json"
    )
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = audit_path.with_suffix(f"{audit_path.suffix}.tmp")
    payload = build_non_publishable_privacy_audit(result, decision)
    temporary_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(audit_path)
    return str(audit_path)
