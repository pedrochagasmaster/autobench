from core.privacy_validation import PrivacyValidationResult, PrivacyValidationRow


def test_privacy_validation_result_renders_legacy_dataframe_columns() -> None:
    result = PrivacyValidationResult(
        rows=[
            PrivacyValidationRow(
                dimension="card_type",
                category="Credit",
                time_period=None,
                peer="P1",
                rule_name="10/40",
                original_volume=100.0,
                original_share_pct=50.0,
                balanced_volume=40.0,
                balanced_share_pct=40.0,
                primary_cap_pct=40.0,
                primary_cap_passed=True,
                secondary_rule_passed=True,
                relaxation_used=False,
                strict_compliant=True,
            )
        ]
    )

    df = result.to_dataframe()

    assert "Compliant" in df.columns
    assert "Additional_Constraints_Relaxed" in df.columns
    assert df.loc[0, "Compliant"] == "Yes"
    assert result.strict_failures() == []
