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
    result = evaluate_rule("10/40", [40.0, 20.0, 10.0, 5.0])

    assert result.primary_cap_passed is True
    assert result.secondary_rule_passed is True
    assert result.strict_passed is True


def test_10_40_fails_when_second_twenty_percent_participant_is_missing() -> None:
    result = evaluate_rule("10/40", [40.0, 19.0, 11.0, 10.0])

    assert result.primary_cap_passed is True
    assert result.secondary_rule_passed is False
    assert result.strict_passed is False


def test_4_35_primary_cap_for_merchant_rule() -> None:
    result = evaluate_rule("4/35", [35.0, 30.0, 20.0, 15.0])

    assert result.strict_passed is True


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
