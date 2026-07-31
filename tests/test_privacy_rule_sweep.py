from __future__ import annotations

import dataclasses
import math
from typing import Iterable, Optional

import pytest

import core
import benchmark
from core import (
    PrivacyConcentrationBasis,
    PrivacyEvaluationStatus,
    PrivacyMetricContext,
    PrivacySweepRequest,
    PrivacySweepStatus,
    evaluate_privacy_rule_sweep,
)
from core.contracts import PrivacySweepResult
from core.privacy_validator import PrivacyValidator
from core.privacy_policy import PrivacyPolicy


def _request(
    shares: Iterable[float],
    *,
    merchant_spend_scope: bool = False,
    metric_context: PrivacyMetricContext = PrivacyMetricContext.OTHER,
    concentration_basis: PrivacyConcentrationBasis = PrivacyConcentrationBasis.BENCHMARK_METRIC,
    citibank_share: Optional[float] = None,
) -> PrivacySweepRequest:
    values = tuple(float(value) for value in shares)
    return PrivacySweepRequest(
        contains_peer_benchmark_data=True,
        is_anonymized_aggregated_merchant_spend=merchant_spend_scope,
        metric_context=metric_context,
        concentration_basis=concentration_basis,
        participant_count=len(values),
        maximum_share_percentage=max(values),
        count_at_or_above_7_percent=sum(value >= 7 for value in values),
        count_at_or_above_8_percent=sum(value >= 8 for value in values),
        count_at_or_above_10_percent=sum(value >= 10 for value in values),
        count_at_or_above_15_percent=sum(value >= 15 for value in values),
        count_at_or_above_20_percent=sum(value >= 20 for value in values),
        citibank_included=citibank_share is not None,
        citi_competitor_receives_output=citibank_share is not None,
        citibank_share_percentage=citibank_share,
    )


def _evaluation(result: PrivacySweepResult, rule_name: str):
    return next(item for item in result.rule_evaluations if item.rule_name == rule_name)


def _reason_codes(result: PrivacySweepResult) -> set[str]:
    return {reason.code for reason in result.failure_reasons}


def test_10_40_failure_is_authorized_by_other_applicable_rules() -> None:
    result = evaluate_privacy_rule_sweep(_request([22, 12, 10, 9, 9, 8, 8, 8, 7, 7]))

    assert result.status == PrivacySweepStatus.NUMERICALLY_COMPLIANT
    assert result.numeric_rules_passed
    assert result.numeric_policy_passed
    assert result.authorizing_rules == ("5/25", "6/30")
    assert _evaluation(result, "5/25").strict_passed
    assert not _evaluation(result, "10/40").strict_passed
    assert {
        reason.code for reason in _evaluation(result, "10/40").failure_reasons
    } == {"threshold_count_not_met"}


def test_merchant_4_35_can_authorize_more_than_four_participants() -> None:
    result = evaluate_privacy_rule_sweep(
        _request([34, 12, 12, 8, 7, 7, 6, 5, 5, 4], merchant_spend_scope=True)
    )

    assert result.status == PrivacySweepStatus.NUMERICALLY_COMPLIANT
    assert result.numeric_policy_passed
    assert result.authorizing_rules == ("4/35",)
    four_rule = _evaluation(result, "4/35")
    assert four_rule.applicable
    assert four_rule.strict_passed


def test_same_10_peer_evidence_cannot_use_4_35_outside_merchant_spend_scope() -> None:
    result = evaluate_privacy_rule_sweep(
        _request([34, 12, 12, 8, 7, 7, 6, 5, 5, 4], merchant_spend_scope=False)
    )

    assert result.status == PrivacySweepStatus.NUMERICALLY_NONCOMPLIANT
    assert not result.numeric_policy_passed
    assert not result.authorizing_rules
    assert _evaluation(result, "4/35").status == PrivacyEvaluationStatus.NOT_APPLICABLE


def test_4_35_is_valid_for_four_merchants() -> None:
    result = evaluate_privacy_rule_sweep(_request([35, 25, 20, 20], merchant_spend_scope=True))

    assert result.numeric_policy_passed
    assert result.authorizing_rules == ("4/35",)
    assert _evaluation(result, "4/35").applicable
    assert _evaluation(result, "4/35").strict_passed


def test_4_35_is_inapplicable_without_merchant_spend_scope() -> None:
    result = evaluate_privacy_rule_sweep(_request([35, 25, 20, 20], merchant_spend_scope=False))

    assert result.status == PrivacySweepStatus.NUMERICALLY_NONCOMPLIANT
    assert not _evaluation(result, "4/35").applicable
    assert _evaluation(result, "4/35").inapplicability_reasons


@pytest.mark.parametrize("participant_count", [1, 2, 3])
def test_4_35_is_inapplicable_below_four_participants(participant_count: int) -> None:
    equal_share = 100.0 / participant_count
    result = evaluate_privacy_rule_sweep(
        _request([equal_share] * participant_count, merchant_spend_scope=True)
    )

    assert not _evaluation(result, "4/35").applicable
    assert not _evaluation(result, "4/35").strict_passed


@pytest.mark.parametrize(
    ("shares", "target_rule"),
    [
        ([25, 25, 20, 15, 15], "5/25"),
        ([30, 24, 18, 10, 10, 8], "6/30"),
        ([35, 20, 15, 10, 8, 7, 5], "7/35"),
        ([22, 20, 12, 10, 8, 7, 6, 5, 5, 5], "10/40"),
    ],
)
def test_each_standard_rule_has_a_passing_case(shares: list[float], target_rule: str) -> None:
    result = evaluate_privacy_rule_sweep(_request(shares))

    assert _evaluation(result, target_rule).strict_passed
    assert result.numeric_policy_passed


@pytest.mark.parametrize(
    ("shares", "target_rule", "failure_code"),
    [
        ([26, 24, 20, 15, 15], "5/25", "maximum_share_exceeded"),
        ([31, 23, 18, 10, 10, 8], "6/30", "maximum_share_exceeded"),
        ([36, 19, 15, 10, 8, 7, 5], "7/35", "maximum_share_exceeded"),
        ([41, 20, 10, 7, 5, 5, 4, 3, 3, 2], "10/40", "maximum_share_exceeded"),
    ],
)
def test_each_standard_rule_has_a_failing_cap_case(
    shares: list[float],
    target_rule: str,
    failure_code: str,
) -> None:
    result = evaluate_privacy_rule_sweep(_request(shares))

    target_evaluation = _evaluation(result, target_rule)
    assert not target_evaluation.strict_passed
    assert failure_code in {reason.code for reason in target_evaluation.failure_reasons}


@pytest.mark.parametrize(
    ("shares", "rule_name", "threshold", "required", "observed"),
    [
        ([30, 30, 6, 6, 6, 22], "6/30", 7.0, 3, 3),
        ([35, 14, 14, 14, 10, 7, 6], "7/35", 15.0, 2, 1),
        ([35, 35, 6, 6, 6, 6, 6], "7/35", 8.0, 3, 2),
        ([22, 12, 10, 9, 9, 8, 8, 8, 7, 7], "10/40", 20.0, 2, 1),
        ([40, 25, 9, 6, 5, 4, 4, 3, 2, 2], "10/40", 10.0, 3, 2),
    ],
)
def test_all_additional_threshold_counts_are_evaluated(
    shares: list[float],
    rule_name: str,
    threshold: float,
    required: int,
    observed: int,
) -> None:
    result = evaluate_privacy_rule_sweep(_request(shares))
    threshold_result = next(
        item
        for item in _evaluation(result, rule_name).threshold_evaluations
        if item.threshold_percentage == threshold
    )

    assert threshold_result.required_count == required
    assert threshold_result.observed_count == observed
    assert threshold_result.compliant is (observed >= required)


def test_all_general_rules_at_or_below_participant_count_are_applicable() -> None:
    result = evaluate_privacy_rule_sweep(_request([22, 12, 10, 9, 9, 8, 8, 8, 7, 7]))

    assert {
        evaluation.rule_name
        for evaluation in result.rule_evaluations
        if evaluation.applicable
    } == {"5/25", "6/30", "7/35", "10/40"}
    assert _evaluation(result, "4/35").status == PrivacyEvaluationStatus.NOT_APPLICABLE


def test_citibank_overlay_blocks_even_when_a_base_rule_passes() -> None:
    result = evaluate_privacy_rule_sweep(
        _request(
            [30, 24, 18, 10, 10, 8],
            citibank_share=30,
        )
    )

    assert result.numeric_rules_passed
    assert not result.mandatory_overlays_passed
    assert not result.numeric_policy_passed
    assert not result.authorizing_rules
    assert result.status == PrivacySweepStatus.BLOCKED_BY_MANDATORY_OVERLAY
    assert {reason.code for reason in result.mandatory_overlays[0].failure_reasons} == {
        "citibank_maximum_share_exceeded"
    }


def test_missing_citibank_concentration_fails_closed_when_overlay_applies() -> None:
    request = dataclasses.replace(
        _request([25, 25, 20, 15, 15]),
        citibank_included=True,
        citi_competitor_receives_output=True,
        citibank_share_percentage=None,
    )

    result = evaluate_privacy_rule_sweep(request)

    assert result.status == PrivacySweepStatus.INVALID_EVIDENCE
    assert not result.audit.evidence_valid
    assert "missing_evidence" in _reason_codes(result)


def test_citibank_overlay_passes_at_25_percent() -> None:
    result = evaluate_privacy_rule_sweep(
        _request([25, 25, 20, 15, 15], citibank_share=25)
    )

    assert result.numeric_policy_passed
    assert result.mandatory_overlays[0].status == PrivacyEvaluationStatus.PASSED


@pytest.mark.parametrize(
    (
        "citibank_included",
        "competitor_receives",
        "citibank_share",
        "expected_status",
        "expected_overlay_status",
        "expected_evidence_valid",
    ),
    [
        (
            False,
            False,
            None,
            PrivacySweepStatus.NUMERICALLY_COMPLIANT,
            PrivacyEvaluationStatus.NOT_APPLICABLE,
            True,
        ),
        (
            False,
            False,
            20,
            PrivacySweepStatus.INVALID_EVIDENCE,
            PrivacyEvaluationStatus.NOT_APPLICABLE,
            False,
        ),
        (
            False,
            True,
            None,
            PrivacySweepStatus.NUMERICALLY_COMPLIANT,
            PrivacyEvaluationStatus.NOT_APPLICABLE,
            True,
        ),
        (
            False,
            True,
            20,
            PrivacySweepStatus.INVALID_EVIDENCE,
            PrivacyEvaluationStatus.NOT_APPLICABLE,
            False,
        ),
        (
            True,
            False,
            None,
            PrivacySweepStatus.NUMERICALLY_COMPLIANT,
            PrivacyEvaluationStatus.NOT_APPLICABLE,
            True,
        ),
        (
            True,
            False,
            20,
            PrivacySweepStatus.NUMERICALLY_COMPLIANT,
            PrivacyEvaluationStatus.NOT_APPLICABLE,
            True,
        ),
        (
            True,
            False,
            31,
            PrivacySweepStatus.INVALID_EVIDENCE,
            PrivacyEvaluationStatus.NOT_APPLICABLE,
            False,
        ),
        (
            True,
            True,
            None,
            PrivacySweepStatus.INVALID_EVIDENCE,
            PrivacyEvaluationStatus.FAILED,
            False,
        ),
        (
            True,
            True,
            25,
            PrivacySweepStatus.NUMERICALLY_COMPLIANT,
            PrivacyEvaluationStatus.PASSED,
            True,
        ),
        (
            True,
            True,
            26,
            PrivacySweepStatus.BLOCKED_BY_MANDATORY_OVERLAY,
            PrivacyEvaluationStatus.FAILED,
            True,
        ),
    ],
)
def test_citibank_overlay_truth_table_is_explicit_and_immutable(
    citibank_included: bool,
    competitor_receives: bool,
    citibank_share: Optional[float],
    expected_status: PrivacySweepStatus,
    expected_overlay_status: PrivacyEvaluationStatus,
    expected_evidence_valid: bool,
) -> None:
    request = dataclasses.replace(
        _request([30, 24, 18, 10, 10, 8]),
        citibank_included=citibank_included,
        citi_competitor_receives_output=competitor_receives,
        citibank_share_percentage=citibank_share,
    )

    result = evaluate_privacy_rule_sweep(request)

    assert result.status == expected_status
    assert result.audit.evidence_valid is expected_evidence_valid
    assert result.mandatory_overlays[0].status == expected_overlay_status
    with pytest.raises(dataclasses.FrozenInstanceError):
        request.citibank_included = True  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.mandatory_overlays[0].status = (  # type: ignore[misc]
            PrivacyEvaluationStatus.PASSED
        )


@pytest.mark.parametrize(
    ("citibank_included", "competitor_receives"),
    [(None, False), (False, None), (None, None)],
)
def test_missing_citibank_trigger_facts_are_invalid(
    citibank_included: Optional[bool],
    competitor_receives: Optional[bool],
) -> None:
    request = dataclasses.replace(
        _request([30, 24, 18, 10, 10, 8]),
        citibank_included=citibank_included,
        citi_competitor_receives_output=competitor_receives,
        citibank_share_percentage=None,
    )

    result = evaluate_privacy_rule_sweep(request)

    assert result.status == PrivacySweepStatus.INVALID_EVIDENCE
    assert "missing_evidence" in _reason_codes(result)


@pytest.mark.parametrize(
    "metric_context",
    [PrivacyMetricContext.ISSUER_FRAUD, PrivacyMetricContext.ISSUER_CHARGEBACK],
)
def test_issuer_fraud_and_chargeback_require_clearing_spend_basis(
    metric_context: PrivacyMetricContext,
) -> None:
    invalid = evaluate_privacy_rule_sweep(
        _request(
            [25, 25, 20, 15, 15],
            metric_context=metric_context,
            concentration_basis=PrivacyConcentrationBasis.BENCHMARK_METRIC,
        )
    )
    valid = evaluate_privacy_rule_sweep(
        _request(
            [25, 25, 20, 15, 15],
            metric_context=metric_context,
            concentration_basis=PrivacyConcentrationBasis.CLEARING_SPEND,
        )
    )

    assert invalid.status == PrivacySweepStatus.INVALID_EVIDENCE
    assert "incorrect_concentration_basis" in _reason_codes(invalid)
    assert valid.numeric_policy_passed


def test_deliverable_without_peer_data_is_not_subject() -> None:
    result = evaluate_privacy_rule_sweep(
        PrivacySweepRequest(
            contains_peer_benchmark_data=False,
            is_anonymized_aggregated_merchant_spend=None,
            metric_context=None,
            concentration_basis=None,
        )
    )

    assert result.status == PrivacySweepStatus.NOT_SUBJECT
    assert result.numeric_rules_passed is None
    assert result.numeric_policy_passed is None
    assert not result.authorizing_rules
    assert all(
        evaluation.status == PrivacyEvaluationStatus.NOT_APPLICABLE
        for evaluation in result.rule_evaluations
    )


@pytest.mark.parametrize(
    ("field_name", "bad_value", "failure_code"),
    [
        ("maximum_share_percentage", None, "missing_evidence"),
        ("maximum_share_percentage", "25", "nonnumeric_evidence"),
        ("maximum_share_percentage", math.nan, "nonfinite_evidence"),
        ("maximum_share_percentage", math.inf, "nonfinite_evidence"),
        ("maximum_share_percentage", -1, "negative_evidence"),
        ("maximum_share_percentage", 101, "over_100_evidence"),
        ("count_at_or_above_7_percent", None, "missing_evidence"),
        ("count_at_or_above_7_percent", "5", "nonnumeric_evidence"),
        ("count_at_or_above_7_percent", -1, "negative_evidence"),
        ("participant_count", None, "missing_evidence"),
        ("participant_count", 5.5, "nonnumeric_evidence"),
        ("contains_peer_benchmark_data", None, "missing_evidence"),
        ("is_anonymized_aggregated_merchant_spend", None, "missing_evidence"),
        ("metric_context", None, "missing_evidence"),
        ("metric_context", "other", "invalid_evidence"),
        ("concentration_basis", None, "missing_evidence"),
        ("concentration_basis", "benchmark_metric", "invalid_evidence"),
        ("citibank_included", None, "missing_evidence"),
        ("citibank_included", 0, "invalid_evidence"),
        ("citi_competitor_receives_output", None, "missing_evidence"),
        ("citi_competitor_receives_output", "true", "invalid_evidence"),
    ],
)
def test_malformed_compact_evidence_fails_closed(
    field_name: str,
    bad_value: object,
    failure_code: str,
) -> None:
    request = dataclasses.replace(
        _request([25, 25, 20, 15, 15]),
        **{field_name: bad_value},
    )

    result = evaluate_privacy_rule_sweep(request)

    assert result.status == PrivacySweepStatus.INVALID_EVIDENCE
    assert not result.audit.evidence_valid
    assert failure_code in _reason_codes(result)


@pytest.mark.parametrize(
    "updates",
    [
        {"count_at_or_above_7_percent": 4, "count_at_or_above_8_percent": 5},
        {"count_at_or_above_20_percent": 6},
        {"maximum_share_percentage": 19, "count_at_or_above_20_percent": 1},
        {"citibank_included": False, "citibank_share_percentage": 10},
    ],
)
def test_contradictory_compact_evidence_fails_closed(updates: dict[str, object]) -> None:
    request = dataclasses.replace(_request([25, 25, 20, 15, 15]), **updates)

    result = evaluate_privacy_rule_sweep(request)

    assert result.status == PrivacySweepStatus.INVALID_EVIDENCE
    assert not result.audit.evidence_valid
    assert "contradictory_evidence" in _reason_codes(result)


def test_result_and_nested_public_contracts_are_immutable() -> None:
    result = evaluate_privacy_rule_sweep(_request([25, 25, 20, 15, 15]))

    with pytest.raises(dataclasses.FrozenInstanceError):
        result.status = PrivacySweepStatus.INVALID_EVIDENCE  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.rule_evaluations[0].status = PrivacyEvaluationStatus.FAILED  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.rule_evaluations[1].threshold_evaluations[0].compliant = False  # type: ignore[misc]


def test_exact_maximum_makes_compact_evidence_infeasible() -> None:
    result = evaluate_privacy_rule_sweep(
        PrivacySweepRequest(
            contains_peer_benchmark_data=True,
            is_anonymized_aggregated_merchant_spend=False,
            metric_context=PrivacyMetricContext.OTHER,
            concentration_basis=PrivacyConcentrationBasis.BENCHMARK_METRIC,
            participant_count=5,
            maximum_share_percentage=100,
            count_at_or_above_7_percent=5,
            count_at_or_above_8_percent=5,
            count_at_or_above_10_percent=5,
            count_at_or_above_15_percent=5,
            count_at_or_above_20_percent=5,
            citibank_included=False,
            citi_competitor_receives_output=False,
        )
    )
    assert result.status == PrivacySweepStatus.INVALID_EVIDENCE
    assert "contradictory_evidence" in _reason_codes(result)


def test_public_facade_adds_sweep_without_breaking_legacy_exports() -> None:
    assert "PrivacySweepRequest" in core.__all__
    assert "PrivacySweepResult" in core.__all__
    assert "evaluate_privacy_rule_sweep" in core.__all__
    assert "PrivacyValidator" in core.__all__
    assert "PrivacyPolicy" not in core.__all__
    assert "DataLoader" in core.__all__
    assert hasattr(core, "PrivacyValidator")
    assert not hasattr(core, "PrivacyPolicy")
    assert hasattr(core, "DataLoader")


def test_cli_flag_selects_sweep_strategy_on_normal_analysis() -> None:
    args = benchmark.create_parser().parse_args(
        [
            "share",
            "--csv",
            "input.csv",
            "--metric",
            "amount",
            "--privacy-rule-sweep",
        ]
    )
    request = benchmark.build_run_request("share", args)
    assert request.privacy_rule_strategy.value == "sweep_any_applicable"


def test_cli_sweep_mode_is_off_by_default() -> None:
    args = benchmark.create_parser().parse_args(
        [
            "share",
            "--csv",
            "input.csv",
            "--metric",
            "amount",
        ]
    )

    assert not args.privacy_rule_sweep


def test_candidate_selection_prefers_legacy_rule_then_fixed_fallback() -> None:
    assert PrivacyPolicy.select_sweep_candidate(
        10, merchant_spend_scope=False, publication_safe_rules=("5/25", "10/40")
    ) == "10/40"
    assert PrivacyPolicy.select_sweep_candidate(
        10, merchant_spend_scope=False, publication_safe_rules=("5/25", "6/30")
    ) == "5/25"
    assert PrivacyPolicy.select_sweep_candidate(
        4, merchant_spend_scope=True, publication_safe_rules=("4/35",)
    ) == "4/35"


@pytest.mark.parametrize(
    ("participant_count", "merchant_mode", "expected"),
    [
        (3, False, "insufficient"),
        (4, False, "insufficient"),
        (4, True, "4/35"),
        (5, False, "5/25"),
        (6, False, "6/30"),
        (7, False, "7/35"),
        (9, True, "7/35"),
        (10, False, "10/40"),
        (100, True, "10/40"),
    ],
)
def test_legacy_single_rule_compatibility_selector_remains_unchanged(
    participant_count: int,
    merchant_mode: bool,
    expected: str,
) -> None:
    assert PrivacyValidator.select_rule(participant_count, merchant_mode) == expected
