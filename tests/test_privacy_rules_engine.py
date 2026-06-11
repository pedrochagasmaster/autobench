import pytest

from core.privacy_rules import RuleMode, evaluate_rule


def test_5_25_requires_primary_cap() -> None:
    result = evaluate_rule("5/25", [26.0, 20.0, 20.0, 19.0, 15.0])

    assert result.primary_cap_passed is False
    assert result.secondary_rule_passed is True
    assert result.strict_passed is False


def test_6_30_requires_three_seven_percent_participants() -> None:
    result = evaluate_rule("6/30", [30.0, 6.0, 6.0, 6.0, 5.0, 4.0])

    assert result.primary_cap_passed is True
    assert result.secondary_rule_passed is False


def test_7_35_requires_two_fifteen_and_one_additional_eight() -> None:
    result = evaluate_rule("7/35", [35.0, 15.0, 8.0, 7.0, 7.0, 7.0, 7.0])

    assert result.primary_cap_passed is True
    assert result.secondary_rule_passed is True
    assert result.strict_passed is True


def test_10_40_requires_primary_cap_and_secondary_counts() -> None:
    result = evaluate_rule("10/40", [40.0, 20.0, 10.0, 5.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0])

    assert result.primary_cap_passed is True
    assert result.secondary_rule_passed is True
    assert result.participant_count_passed is True
    assert result.strict_passed is True


def test_10_40_fails_when_minimum_participant_count_is_missing() -> None:
    result = evaluate_rule("10/40", [40.0, 20.0, 10.0, 5.0])

    assert result.primary_cap_passed is True
    assert result.secondary_rule_passed is True
    assert result.participant_count_passed is False
    assert result.strict_passed is False
    assert result.participant_failures == ["Rule 10/40: Need at least 10 participants, found 4"]


def test_5_25_fails_when_minimum_participant_count_is_missing() -> None:
    result = evaluate_rule("5/25", [25.0, 25.0, 25.0, 25.0])

    assert result.primary_cap_passed is True
    assert result.secondary_rule_passed is True
    assert result.participant_count_passed is False
    assert result.strict_passed is False


def test_10_40_fails_when_second_twenty_percent_participant_is_missing() -> None:
    result = evaluate_rule("10/40", [40.0, 19.0, 11.0, 10.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0])

    assert result.primary_cap_passed is True
    assert result.secondary_rule_passed is False
    assert result.participant_count_passed is True
    assert result.strict_passed is False


def test_4_35_primary_cap_for_merchant_rule() -> None:
    result = evaluate_rule("4/35", [35.0, 30.0, 20.0, 15.0])

    assert result.strict_passed is True


# ---------------------------------------------------------------------------
# Boundary-value coverage (plan 001).
#
# These cases freeze the epsilon semantics around COMPARISON_EPSILON = 1e-6:
# a share exactly at the cap passes, a share within epsilon of the cap
# (cap + 1e-8) still passes, and a share clearly above (cap + 0.001) fails.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rule_name", "shares", "expected_passed", "expected_failures"),
    [
        # Exactly at cap -> passes (epsilon makes exact-cap compliant).
        ("5/25", [25.0, 25.0, 25.0, 24.0, 1.0], True, 0),
        ("6/30", [30.0, 24.0, 22.0, 8.0, 8.0, 8.0], True, 0),
        ("7/35", [35.0, 15.0, 15.0, 10.0, 9.0, 8.0, 8.0], True, 0),
        ("10/40", [40.0, 20.0, 10.0, 6.0, 5.0, 5.0, 4.0, 4.0, 3.0, 3.0], True, 0),
        ("4/35", [35.0, 30.0, 20.0, 15.0], True, 0),
        # Clearly above cap (cap + 0.001, beyond epsilon) -> fails with one violation.
        ("5/25", [25.001, 25.0, 25.0, 23.999, 1.0], False, 1),
        ("6/30", [30.001, 23.999, 22.0, 8.0, 8.0, 8.0], False, 1),
        ("7/35", [35.001, 15.0, 15.0, 9.999, 9.0, 8.0, 8.0], False, 1),
        ("10/40", [40.001, 20.0, 10.0, 5.999, 5.0, 5.0, 4.0, 4.0, 3.0, 3.0], False, 1),
        ("4/35", [35.001, 29.999, 20.0, 15.0], False, 1),
        # Within epsilon of cap (cap + 1e-8) -> still passes (characterization).
        ("5/25", [25.0 + 1e-8, 25.0, 24.0, 24.0, 1.0], True, 0),
        ("6/30", [30.0 + 1e-8, 24.0, 22.0, 8.0, 8.0, 7.0], True, 0),
        ("7/35", [35.0 + 1e-8, 15.0, 15.0, 10.0, 9.0, 8.0, 7.0], True, 0),
        ("10/40", [40.0 + 1e-8, 20.0, 10.0, 6.0, 5.0, 5.0, 4.0, 4.0, 3.0, 2.0], True, 0),
        ("4/35", [35.0 + 1e-8, 30.0, 20.0, 14.0], True, 0),
    ],
)
def test_primary_cap_boundaries(
    rule_name: str,
    shares: list,
    expected_passed: bool,
    expected_failures: int,
) -> None:
    result = evaluate_rule(rule_name, shares)

    assert result.primary_cap_passed is expected_passed
    assert result.primary_cap_failures == expected_failures


@pytest.mark.parametrize(
    ("rule_name", "shares", "expected_passed"),
    [
        # 6/30: at least 3 participants >= 7%.
        ("6/30", [7.0, 7.0, 7.0, 6.0, 6.0, 6.0], True),
        ("6/30", [6.999, 6.999, 6.999, 6.0, 6.0, 6.0], False),
        # 7/35: at least 2 >= 15% plus 1 additional >= 8% (tiers (2, 15.0)/(3, 8.0)).
        ("7/35", [15.0, 15.0, 8.0, 7.0, 7.0, 7.0, 7.0], True),
        ("7/35", [14.999, 14.999, 8.0, 7.0, 7.0, 7.0, 7.0], False),
        # 10/40: at least 2 >= 20% plus 1 additional >= 10% (tiers (2, 20.0)/(3, 10.0)).
        ("10/40", [20.0, 20.0, 10.0, 9.0, 9.0, 8.0, 8.0, 6.0, 5.0, 5.0], True),
        ("10/40", [19.999, 19.999, 10.0, 9.0, 9.0, 8.0, 8.0, 6.0, 5.0, 5.0], False),
    ],
)
def test_secondary_tier_boundaries(
    rule_name: str,
    shares: list,
    expected_passed: bool,
) -> None:
    result = evaluate_rule(rule_name, shares)

    assert result.secondary_rule_passed is expected_passed


@pytest.mark.parametrize(
    ("rule_name", "shares", "expected_passed"),
    [
        # Exactly min_entities participants -> passes.
        ("5/25", [20.0, 20.0, 20.0, 20.0, 20.0], True),
        ("6/30", [20.0, 20.0, 20.0, 14.0, 13.0, 13.0], True),
        ("7/35", [16.0, 15.0, 15.0, 14.0, 14.0, 13.0, 13.0], True),
        ("10/40", [20.0, 20.0, 10.0, 8.0, 8.0, 8.0, 8.0, 6.0, 6.0, 6.0], True),
        ("4/35", [35.0, 30.0, 20.0, 15.0], True),
        # min_entities - 1 participants -> fails.
        ("5/25", [25.0, 25.0, 25.0, 25.0], False),
        ("6/30", [20.0, 20.0, 20.0, 20.0, 20.0], False),
        ("7/35", [17.0, 17.0, 17.0, 17.0, 16.0, 16.0], False),
        ("10/40", [20.0, 20.0, 10.0, 9.0, 9.0, 8.0, 8.0, 8.0, 8.0], False),
        ("4/35", [35.0, 35.0, 30.0], False),
    ],
)
def test_participant_count_boundaries(
    rule_name: str,
    shares: list,
    expected_passed: bool,
) -> None:
    result = evaluate_rule(rule_name, shares)

    assert result.participant_count_passed is expected_passed


def test_adaptive_relaxation_never_counts_as_strict_passed() -> None:
    result = evaluate_rule(
        "10/40",
        [40.0, 15.0, 8.0, 7.0],
        thresholds={"tier_1": (1, 15.0), "tier_2": (1, 8.0)},
        mode=RuleMode.ADAPTIVE,
        relaxation_used=True,
    )

    assert result.secondary_rule_passed is True
    assert result.relaxation_used is True
    assert result.strict_passed is False
