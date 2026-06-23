import pandas as pd
from unittest.mock import patch

from core.compliance import build_blocked_compliance_summary, build_compliance_summary
from core.contracts import DataQualityResult
from core.dimensional_analyzer import DimensionalAnalyzer
from core.privacy_validation import PrivacyValidationResult, PrivacyValidationRow


def test_compliance_summary_counts_title_case_validation_column() -> None:
    privacy_validation_df = pd.DataFrame({"Compliant": ["Yes", "No", "No"]})

    summary = build_compliance_summary(posture="strict", privacy_validation_df=privacy_validation_df)

    assert summary.violations == 2
    assert summary.to_dict()["compliance_verdict"] in {"violations_detected", "structural_infeasibility"}


def test_compliance_summary_ignores_non_infeasible_structural_summary() -> None:
    summary = build_compliance_summary(
        posture="strict",
        structural_infeasibility={
            "has_structural_infeasibility": False,
            "infeasible_dimensions": 0,
        },
    )

    as_dict = summary.to_dict()

    assert as_dict["run_status"] == "compliant"
    assert as_dict["compliance_verdict"] == "fully_compliant"


def test_blocked_compliance_summary_reports_blocked_verdict() -> None:
    summary = build_blocked_compliance_summary("accuracy_first", acknowledgement_given=False).to_dict()

    assert summary["blocked"] is True
    assert summary["reason"] == "acknowledgement required"
    assert summary["run_status"] == "blocked"
    assert summary["compliance_verdict"] == "blocked"
    assert summary["acknowledgement_state"] == "required_missing"
    assert summary["posture_consistent"] is False
    # Decision Q6: no `compliance_posture` alias — `posture` is the single field.
    assert "compliance_posture" not in summary


def test_compliance_summary_threads_insufficient_peers_block_reason() -> None:
    summary = build_compliance_summary(
        posture="strict",
        blocked_reason="insufficient_peers",
        blocked_details={"peer_count": 3},
    ).to_dict()

    assert summary["run_status"] == "blocked"
    assert summary["compliance_verdict"] == "blocked"
    assert summary["blocked"] is True
    assert summary["reason"] == "insufficient_peers"
    assert summary["peer_count"] == 3


def test_compliance_summary_lowercase_compliant_column() -> None:
    """§2.5: ``compliant`` (lowercase) must also be counted, not just title-case."""
    privacy_validation_df = pd.DataFrame({"compliant": [True, False, False, True]})

    summary = build_compliance_summary(
        posture="strict", privacy_validation_df=privacy_validation_df
    )

    assert summary.violations == 2


def test_compliance_summary_rejects_relaxed_additional_constraints() -> None:
    privacy_validation_df = pd.DataFrame(
        {
            "Dimension": ["card_type"] * 3,
            "Category": ["Credit"] * 3,
            "Rule_Name": ["10/40"] * 3,
            "Balanced_Share_%": [40.0, 20.0, 10.0],
            "Privacy_Cap_%": [40.0, 40.0, 40.0],
            "Additional_Constraints_Relaxed": ["No", "Yes", "No"],
            "Compliant": ["Yes", "Yes", "Yes"],
        }
    )

    summary = build_compliance_summary(
        posture="strict", privacy_validation_df=privacy_validation_df
    ).to_dict()

    assert summary["run_status"] == "non_compliant"
    assert summary["compliance_verdict"] == "violations_detected"
    assert summary["strict_final_validation"]["relaxed_rows"] == 1


def test_compliance_summary_rechecks_strict_10_40_secondary_rule() -> None:
    privacy_validation_df = pd.DataFrame(
        {
            "Dimension": ["card_type"] * 4,
            "Category": ["Credit"] * 4,
            "Rule_Name": ["10/40"] * 4,
            "Balanced_Share_%": [40.0, 19.0, 11.0, 10.0],
            "Privacy_Cap_%": [40.0] * 4,
            "Additional_Constraints_Relaxed": ["No"] * 4,
            "Compliant": ["Yes"] * 4,
        }
    )

    summary = build_compliance_summary(
        posture="strict", privacy_validation_df=privacy_validation_df
    ).to_dict()

    assert summary["run_status"] == "non_compliant"
    assert summary["strict_final_validation"]["secondary_rule_fail_categories"] == 1
    evaluation = summary["strict_final_validation"]["rule_evaluations"][0]
    assert evaluation["rule_name"] == "10/40"
    assert evaluation["secondary_rule_passed"] is False


def test_compliance_summary_rejects_strict_10_40_with_too_few_participants() -> None:
    privacy_validation_df = pd.DataFrame(
        {
            "Dimension": ["card_type"] * 4,
            "Category": ["Credit"] * 4,
            "Rule_Name": ["10/40"] * 4,
            "Balanced_Share_%": [40.0, 20.0, 10.0, 5.0],
            "Privacy_Cap_%": [40.0] * 4,
            "Additional_Constraints_Relaxed": ["No"] * 4,
            "Compliant": ["Yes"] * 4,
        }
    )

    summary = build_compliance_summary(
        posture="strict", privacy_validation_df=privacy_validation_df
    ).to_dict()

    assert summary["run_status"] == "non_compliant"
    assert summary["compliance_verdict"] == "violations_detected"
    assert summary["strict_final_validation"]["participant_count_fail_categories"] == 1
    assert summary["strict_final_validation"]["total_violations"] == 1
    evaluation = summary["strict_final_validation"]["rule_evaluations"][0]
    assert evaluation["participant_count_passed"] is False


def test_compliance_summary_accepts_strict_10_40_primary_secondary_and_participant_rules() -> None:
    privacy_validation_df = pd.DataFrame(
        {
            "Dimension": ["card_type"] * 10,
            "Category": ["Credit"] * 10,
            "Rule_Name": ["10/40"] * 10,
            "Balanced_Share_%": [40.0, 20.0, 10.0, 5.0, 5.0, 4.0, 4.0, 4.0, 4.0, 4.0],
            "Privacy_Cap_%": [40.0] * 10,
            "Additional_Constraints_Relaxed": ["No"] * 10,
            "Compliant": ["Yes"] * 10,
        }
    )

    summary = build_compliance_summary(
        posture="strict", privacy_validation_df=privacy_validation_df
    ).to_dict()

    assert summary["run_status"] == "compliant"
    assert summary["compliance_verdict"] == "fully_compliant"
    assert summary["strict_final_validation"]["total_violations"] == 0


def test_compliance_summary_counts_single_primary_cap_violation_once() -> None:
    """One strict_compliant=False row must not inflate violations via strict recount."""
    compliant_rows = [
        PrivacyValidationRow(
            dimension="card_type",
            category="Credit",
            time_period=None,
            peer=f"P{idx}",
            rule_name="5/25",
            original_volume=100.0,
            original_share_pct=share,
            balanced_volume=100.0,
            balanced_share_pct=share,
            primary_cap_pct=25.0,
            primary_cap_passed=True,
            secondary_rule_passed=True,
            relaxation_used=False,
            strict_compliant=True,
        )
        for idx, share in enumerate([20.0, 20.0, 20.0, 10.0], start=1)
    ]
    violating_row = PrivacyValidationRow(
        dimension="card_type",
        category="Credit",
        time_period=None,
        peer="P5",
        rule_name="5/25",
        original_volume=100.0,
        original_share_pct=30.0,
        balanced_volume=100.0,
        balanced_share_pct=30.0,
        primary_cap_pct=25.0,
        primary_cap_passed=False,
        secondary_rule_passed=True,
        relaxation_used=False,
        strict_compliant=False,
    )
    privacy_validation = PrivacyValidationResult(rows=[*compliant_rows, violating_row])

    summary = build_compliance_summary(
        posture="strict",
        privacy_validation_df=privacy_validation,
    )

    assert summary.violations == 1


def test_compliance_summary_counts_cap_and_secondary_failures_distinctly() -> None:
    """Primary-cap row failures and category secondary failures each count once."""
    # 10/40: one row at 41% (primary cap fail); only one peer >= 20% (secondary fail).
    remaining = (100.0 - 41.0) / 9.0
    shares = [41.0] + [remaining] * 9
    rows = [
        PrivacyValidationRow(
            dimension="card_type",
            category="Credit",
            time_period=None,
            peer=f"P{idx}",
            rule_name="10/40",
            original_volume=100.0,
            original_share_pct=share,
            balanced_volume=100.0,
            balanced_share_pct=share,
            primary_cap_pct=40.0,
            primary_cap_passed=share <= 40.0,
            secondary_rule_passed=False,
            relaxation_used=False,
            strict_compliant=share <= 40.0,
        )
        for idx, share in enumerate(shares, start=1)
    ]
    privacy_validation = PrivacyValidationResult(rows=rows)

    summary = build_compliance_summary(
        posture="strict",
        privacy_validation_df=privacy_validation,
    )

    assert summary.violations == 2
    strict = summary.details["strict_final_validation"]
    assert strict["primary_cap_fail_rows"] == 1
    assert strict["secondary_rule_fail_categories"] == 1


def test_compliance_summary_accepts_typed_validation_without_dataframe_render() -> None:
    privacy_validation = PrivacyValidationResult(
        rows=[
            PrivacyValidationRow(
                dimension="card_type",
                category="Credit",
                time_period=None,
                peer=f"P{idx}",
                rule_name="5/25",
                original_volume=100.0,
                original_share_pct=20.0,
                balanced_volume=100.0,
                balanced_share_pct=20.0,
                primary_cap_pct=25.0,
                primary_cap_passed=True,
                secondary_rule_passed=True,
                relaxation_used=False,
                strict_compliant=True,
            )
            for idx in range(1, 6)
        ]
    )

    with patch.object(
        PrivacyValidationResult,
        "to_dataframe",
        side_effect=AssertionError("typed validation should not be rendered for compliance summary"),
    ):
        summary = build_compliance_summary(
            posture="strict",
            privacy_validation_df=privacy_validation,
            data_quality=DataQualityResult(checked=True),
        ).to_dict()

    assert summary["run_status"] == "compliant"
    assert summary["strict_final_validation"]["checked"] is True
    assert summary["strict_final_validation"]["rows"] == 5


def test_strict_compliance_requires_publishable_data_quality() -> None:
    summary = build_compliance_summary(
        posture="strict",
        data_quality=DataQualityResult(checked=False),
    ).to_dict()

    assert summary["compliance_verdict"] == "not_publishable_input"
    assert summary["data_quality_checked"] is False
    assert summary["data_quality_publishable"] is False


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
    )
    analyzer.calculate_global_privacy_weights(df, "txn_cnt", ["card_type"])

    validation_df = analyzer.build_privacy_validation_dataframe(df, "txn_cnt", ["card_type"])

    assert "_TIME_TOTAL_" in set(validation_df["Dimension"])
