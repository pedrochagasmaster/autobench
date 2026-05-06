import pandas as pd

from core.compliance import build_compliance_summary


def test_compliance_summary_counts_title_case_validation_column() -> None:
    privacy_validation_df = pd.DataFrame({"Compliant": ["Yes", "No", "No"]})

    summary = build_compliance_summary(posture="strict", privacy_validation_df=privacy_validation_df)

    assert summary.violations == 2
    assert summary.to_dict()["compliance_verdict"] in {"violations_detected"}


def test_compliance_summary_structural_false_positive_empty_dict() -> None:
    summary = build_compliance_summary(
        posture="strict",
        structural_infeasibility={"has_structural_infeasibility": False, "infeasible_dimensions": 0},
    )

    result = summary.to_dict()
    assert result["compliance_verdict"] == "fully_compliant"


def test_compliance_summary_structural_true_positive() -> None:
    summary = build_compliance_summary(
        posture="strict",
        structural_infeasibility={"has_structural_infeasibility": True, "infeasible_dimensions": 2},
    )

    result = summary.to_dict()
    assert result["compliance_verdict"] == "structural_infeasibility"
