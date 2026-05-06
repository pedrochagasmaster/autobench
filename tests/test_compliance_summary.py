import pandas as pd

from core.compliance import (
    build_blocked_compliance_summary,
    build_compliance_summary,
)
from core.dimensional_analyzer import DimensionalAnalyzer


def test_compliance_summary_counts_title_case_validation_column() -> None:
    privacy_validation_df = pd.DataFrame({"Compliant": ["Yes", "No", "No"]})

    summary = build_compliance_summary(
        posture="strict",
        privacy_validation_df=privacy_validation_df,
    )

    assert summary.violations == 2
    assert summary.to_dict()["compliance_verdict"] in {
        "violations_detected",
        "non_compliant",
        "structural_infeasibility",
    }


def test_compliance_summary_ignores_truthy_structural_summary_without_flag() -> None:
    summary = build_compliance_summary(
        posture="strict",
        privacy_validation_df=pd.DataFrame(),
        structural_infeasibility={
            "has_structural_infeasibility": False,
            "infeasible_dimensions": 0,
        },
    ).to_dict()

    assert summary["compliance_verdict"] == "fully_compliant"


def test_blocked_compliance_summary_reports_blocked_state() -> None:
    summary = build_blocked_compliance_summary(
        posture="accuracy_first",
        acknowledgement_given=False,
    ).to_dict()

    assert summary["blocked"] is True
    assert summary["reason"] == "acknowledgement required"
    assert summary["compliance_verdict"] != "fully_compliant"
    assert summary["run_status"] != "completed_accuracy_first"


def test_time_aware_privacy_validation_includes_time_total_rows() -> None:
    df = pd.DataFrame(
        {
            "issuer_name": ["Target", "P1", "P2", "P3", "P4", "P5", "P6"] * 2,
            "month": ["2024-01"] * 7 + ["2024-02"] * 7,
            "card_type": ["A", "A", "A", "A", "A", "A", "A"] * 2,
            "txn_cnt": [
                100,
                200,
                180,
                160,
                140,
                120,
                110,
                90,
                190,
                170,
                150,
                130,
                115,
                105,
            ],
        }
    )
    analyzer = DimensionalAnalyzer(
        target_entity="Target",
        entity_column="issuer_name",
        time_column="month",
        debug_mode=True,
    )
    analyzer.calculate_global_privacy_weights(df, "txn_cnt", ["card_type"])

    validation_df = analyzer.build_privacy_validation_dataframe(
        df,
        "txn_cnt",
        ["card_type"],
    )

    assert "_TIME_TOTAL_" in set(validation_df["Dimension"])
