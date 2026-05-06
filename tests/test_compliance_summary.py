import pandas as pd

from core.compliance import build_blocked_compliance_summary, build_compliance_summary
from core.dimensional_analyzer import DimensionalAnalyzer
from tests.fixtures.mock_benchmark_data import build_mock_benchmark_df


def test_compliance_summary_counts_title_case_validation_column() -> None:
    privacy_validation_df = pd.DataFrame({"Compliant": ["Yes", "No", "No"]})

    summary = build_compliance_summary(posture="strict", privacy_validation_df=privacy_validation_df)

    assert summary.violations == 2
    assert summary.to_dict()["compliance_verdict"] in {"violations_detected", "structural_infeasibility"}


def test_compliance_summary_ignores_false_structural_dict() -> None:
    struct = {
        "has_structural_infeasibility": False,
        "infeasible_dimensions": 0,
        "infeasible_categories": 0,
        "infeasible_peers": 0,
        "worst_margin_pp": 0.0,
    }

    summary = build_compliance_summary(posture="strict", structural_infeasibility=struct).to_dict()

    assert summary["run_status"] == "compliant"
    assert summary["compliance_verdict"] == "fully_compliant"


def test_blocked_compliance_summary_reports_blocked_state() -> None:
    summary = build_blocked_compliance_summary("accuracy_first", False).to_dict()

    assert summary["blocked"] is True
    assert summary["reason"] == "acknowledgement required"
    assert summary["run_status"] == "blocked"
    assert summary["compliance_verdict"] == "blocked"


def test_time_aware_privacy_validation_includes_time_total_rows() -> None:
    df = build_mock_benchmark_df()
    analyzer = DimensionalAnalyzer(
        target_entity="Target",
        entity_column="issuer_name",
        time_column="year_month",
        debug_mode=True,
        consistent_weights=True,
    )
    analyzer.calculate_global_privacy_weights(df, "txn_cnt", ["card_type", "channel"])

    validation_df = analyzer.build_privacy_validation_dataframe(df, "txn_cnt", ["card_type", "channel"])

    assert "_TIME_TOTAL_" in set(validation_df["Dimension"])
