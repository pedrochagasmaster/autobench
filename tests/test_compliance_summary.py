import pandas as pd

from core.compliance import build_blocked_compliance_summary, build_compliance_summary
from core.dimensional_analyzer import DimensionalAnalyzer


def test_compliance_summary_counts_title_case_validation_column() -> None:
    privacy_validation_df = pd.DataFrame({"Compliant": ["Yes", "No", "No"]})

    summary = build_compliance_summary(posture="strict", privacy_validation_df=privacy_validation_df)

    assert summary.violations == 2
    assert summary.to_dict()["compliance_verdict"] == "violations_detected"


def test_compliance_summary_ignores_structural_summary_without_infeasibility() -> None:
    structural = {
        "has_structural_infeasibility": False,
        "infeasible_dimensions": 0,
        "infeasible_categories": 0,
        "infeasible_peers": 0,
        "worst_margin_pp": 0.0,
    }

    summary = build_compliance_summary(posture="strict", structural_infeasibility=structural).to_dict()

    assert summary["run_status"] == "compliant"
    assert summary["compliance_verdict"] == "fully_compliant"


def test_blocked_compliance_summary_reports_blocked_state() -> None:
    summary = build_blocked_compliance_summary("accuracy_first", False).to_dict()

    assert summary["blocked"] is True
    assert summary["run_status"] == "blocked"
    assert summary["compliance_verdict"] == "blocked"
    assert summary["acknowledgement_state"] == "required_missing"


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
