"""Tests for the PrivacyValidator DataFrame-level enforcement path."""

from typing import Dict

import pandas as pd

from core.privacy_validator import PrivacyValidator


def _peer_group(volumes: Dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        {"issuer_name": list(volumes), "transaction_count": list(volumes.values())}
    )


def test_validate_peer_group_passes_balanced_group_under_5_25() -> None:
    validator = PrivacyValidator(rule_name="5/25")
    df = _peer_group(
        {"PEER_A": 20.0, "PEER_B": 20.0, "PEER_C": 20.0, "PEER_D": 20.0, "PEER_E": 20.0}
    )

    is_compliant, warnings = validator.validate_peer_group(
        df, metrics=["transaction_count"], entity_column="issuer_name"
    )

    assert is_compliant is True
    assert warnings == []


def test_validate_peer_group_fails_when_one_peer_exceeds_cap() -> None:
    validator = PrivacyValidator(rule_name="5/25")
    df = _peer_group(
        {"PEER_A": 30.0, "PEER_B": 20.0, "PEER_C": 20.0, "PEER_D": 15.0, "PEER_E": 15.0}
    )

    is_compliant, warnings = validator.validate_peer_group(
        df, metrics=["transaction_count"], entity_column="issuer_name"
    )

    assert is_compliant is False
    assert any("PEER_A" in warning for warning in warnings)


def test_validate_peer_group_fails_below_min_participants() -> None:
    validator = PrivacyValidator(rule_name="5/25")
    df = _peer_group(
        {"PEER_A": 25.0, "PEER_B": 25.0, "PEER_C": 25.0, "PEER_D": 25.0}
    )

    is_compliant, warnings = validator.validate_peer_group(
        df, metrics=["transaction_count"], entity_column="issuer_name"
    )

    assert is_compliant is False
    assert warnings == ["Insufficient entities: 4 < 5"]


def test_calculate_concentration_returns_correct_percentages() -> None:
    validator = PrivacyValidator(rule_name="5/25")
    df = _peer_group({"PEER_A": 50.0, "PEER_B": 30.0, "PEER_C": 20.0})

    result = validator.calculate_concentration(
        df, metric="transaction_count", entity_column="issuer_name"
    )

    by_entity = result.set_index("issuer_name")["concentration"]
    assert by_entity["PEER_A"] == 50.0
    assert by_entity["PEER_B"] == 30.0
    assert by_entity["PEER_C"] == 20.0
    assert abs(result["concentration"].sum() - 100.0) < 1e-9


def test_apply_weighting_caps_dominant_peer_at_threshold() -> None:
    validator = PrivacyValidator(rule_name="5/25")
    df = _peer_group(
        {"PEER_A": 70.0, "PEER_B": 10.0, "PEER_C": 10.0, "PEER_D": 5.0, "PEER_E": 5.0}
    )
    threshold = 25.0

    weighted = validator.apply_weighting(
        df,
        metric="transaction_count",
        threshold_percentage=threshold,
        entity_column="issuer_name",
    )

    concentrations = validator.calculate_concentration(
        weighted, metric="transaction_count", entity_column="issuer_name"
    )
    assert concentrations["concentration"].max() <= threshold
    dominant_factor = weighted.set_index("issuer_name").loc["PEER_A", "adjustment_factor"]
    assert dominant_factor < 1.0


def test_zero_total_metric_does_not_flip_compliance() -> None:
    # Characterization of current behavior: a metric whose total is zero is
    # skipped (warning only, `continue` in validate_peer_group) and does NOT
    # mark the peer group non-compliant. Do not "fix" without a deliberate
    # product decision.
    validator = PrivacyValidator(rule_name="5/25")
    df = pd.DataFrame(
        {
            "issuer_name": ["PEER_A", "PEER_B", "PEER_C", "PEER_D", "PEER_E"],
            "transaction_count": [20.0, 20.0, 20.0, 20.0, 20.0],
            "zero_metric": [0.0, 0.0, 0.0, 0.0, 0.0],
        }
    )

    with_zero, zero_warnings = validator.validate_peer_group(
        df, metrics=["transaction_count", "zero_metric"], entity_column="issuer_name"
    )
    without_zero, _ = validator.validate_peer_group(
        df, metrics=["transaction_count"], entity_column="issuer_name"
    )

    assert with_zero == without_zero
    assert with_zero is True
    assert "Total for metric 'zero_metric' is zero" in zero_warnings


def test_protected_entity_uses_stricter_concentration_limit() -> None:
    validator = PrivacyValidator(
        protected_entities=["PEER_A"], protected_max_concentration=10.0
    )
    df = _peer_group(
        {"PEER_A": 15.0, "PEER_B": 25.0, "PEER_C": 25.0, "PEER_D": 20.0, "PEER_E": 15.0}
    )

    is_compliant, warnings = validator.validate_peer_group(
        df, metrics=["transaction_count"], entity_column="issuer_name"
    )

    assert is_compliant is False
    assert any(
        "Protected entity 'PEER_A'" in warning and "10.0%" in warning
        for warning in warnings
    )
