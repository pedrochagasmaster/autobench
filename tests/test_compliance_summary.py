"""Tests for compliance summary verdict and time-aware privacy validation."""

from __future__ import annotations

import pandas as pd

from core.compliance import ComplianceSummary, build_compliance_summary
from core.dimensional_analyzer import DimensionalAnalyzer


def test_compliance_summary_counts_title_case_validation_column() -> None:
    privacy_validation_df = pd.DataFrame({"Compliant": ["Yes", "No", "No"]})

    summary = build_compliance_summary(posture="strict", privacy_validation_df=privacy_validation_df)

    assert summary.violations == 2
    assert summary.to_dict()["compliance_verdict"] in {"violations_detected"}


def test_compliance_summary_counts_lower_case_validation_column() -> None:
    privacy_validation_df = pd.DataFrame({"compliant": [True, False, False]})

    summary = build_compliance_summary(posture="strict", privacy_validation_df=privacy_validation_df)

    assert summary.violations == 2


def test_compliance_summary_does_not_flag_structural_when_dict_is_truthy_but_clean() -> None:
    """A non-empty diagnostic dict with has_structural_infeasibility=False must not be flagged."""
    structural = {
        "has_structural_infeasibility": False,
        "infeasible_dimensions": 0,
        "infeasible_categories": 0,
        "infeasible_peers": 0,
        "worst_margin_pp": 0.0,
        "top_infeasible_dimension": None,
        "top_infeasible_category": None,
    }

    summary = ComplianceSummary(
        posture="strict",
        violations=0,
        structural_infeasibility=structural,
    ).to_dict()

    assert summary["compliance_verdict"] == "fully_compliant"
    assert summary["run_status"] == "compliant"


def test_compliance_summary_flags_structural_when_marker_true() -> None:
    structural = {
        "has_structural_infeasibility": True,
        "infeasible_dimensions": 1,
        "infeasible_categories": 1,
        "infeasible_peers": 1,
        "worst_margin_pp": 5.0,
        "top_infeasible_dimension": "card_type",
        "top_infeasible_category": "CREDIT",
    }

    summary = ComplianceSummary(
        posture="strict",
        violations=0,
        structural_infeasibility=structural,
    ).to_dict()

    assert summary["compliance_verdict"] == "structural_infeasibility"


def test_blocked_compliance_summary_short_circuits_to_blocked_verdict() -> None:
    from core.compliance import build_blocked_compliance_summary

    summary = build_blocked_compliance_summary(posture="accuracy_first", acknowledgement_given=False).to_dict()

    assert summary["compliance_verdict"] == "blocked"
    assert summary["run_status"] == "blocked"
    assert summary["blocked"] is True


def test_time_aware_privacy_validation_includes_time_total_rows() -> None:
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
        consistent_weights=True,
    )
    analyzer.calculate_global_privacy_weights(df, "txn_cnt", ["card_type"])

    validation_df = analyzer.build_privacy_validation_dataframe(df, "txn_cnt", ["card_type"])

    assert "_TIME_TOTAL_" in set(validation_df["Dimension"])
