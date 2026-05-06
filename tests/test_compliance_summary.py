"""Tests for compliance summary casing, violation counting, and structural verdict."""

import pandas as pd

from core.compliance import build_compliance_summary


def test_compliance_summary_counts_title_case_validation_column() -> None:
    privacy_validation_df = pd.DataFrame({"Compliant": ["Yes", "No", "No"]})

    summary = build_compliance_summary(posture="strict", privacy_validation_df=privacy_validation_df)

    assert summary.violations == 2
    assert summary.to_dict()["compliance_verdict"] in {"violations_detected"}


def test_compliance_summary_counts_lowercase_validation_column() -> None:
    privacy_validation_df = pd.DataFrame({"compliant": [True, False, False]})

    summary = build_compliance_summary(posture="strict", privacy_validation_df=privacy_validation_df)

    assert summary.violations == 2


def test_compliance_summary_zero_violations_fully_compliant() -> None:
    privacy_validation_df = pd.DataFrame({"Compliant": ["Yes", "Yes"]})

    summary = build_compliance_summary(posture="strict", privacy_validation_df=privacy_validation_df)

    assert summary.violations == 0
    assert summary.to_dict()["compliance_verdict"] == "fully_compliant"


def test_structural_infeasibility_false_positive_dict() -> None:
    """Audit complement §2.1: empty structural dict should not trigger structural_infeasibility verdict."""
    struct = {
        "has_structural_infeasibility": False,
        "infeasible_dimensions": 0,
        "infeasible_categories": 0,
        "infeasible_peers": 0,
        "worst_margin_pp": 0.0,
        "top_infeasible_dimension": None,
        "top_infeasible_category": None,
    }
    summary = build_compliance_summary(posture="strict", structural_infeasibility=struct)

    result = summary.to_dict()
    assert result["compliance_verdict"] == "fully_compliant"
    assert result["run_status"] == "compliant"


def test_structural_infeasibility_true_verdict() -> None:
    struct = {
        "has_structural_infeasibility": True,
        "infeasible_dimensions": 2,
    }
    summary = build_compliance_summary(posture="strict", structural_infeasibility=struct)

    result = summary.to_dict()
    assert result["compliance_verdict"] == "structural_infeasibility"


def test_time_aware_privacy_validation_includes_time_total_rows() -> None:
    from core.dimensional_analyzer import DimensionalAnalyzer

    df = pd.DataFrame(
        {
            "issuer_name": ["Target", "P1", "P2", "P3", "P4", "P5", "P6"] * 2,
            "month": ["2024-01"] * 7 + ["2024-02"] * 7,
            "card_type": ["A", "A", "A", "A", "A", "A", "A"] * 2,
            "txn_cnt": [100, 200, 180, 160, 140, 120, 110, 90, 190, 170, 150, 130, 115, 105],
        }
    )
    analyzer = DimensionalAnalyzer(
        target_entity="Target",
        entity_column="issuer_name",
        time_column="month",
        debug_mode=True,
    )
    analyzer.calculate_global_privacy_weights(df, "txn_cnt", ["card_type"])

    validation_df = analyzer.build_privacy_validation_dataframe(df, "txn_cnt", ["card_type"])

    assert "_TIME_TOTAL_" in set(validation_df["Dimension"])
