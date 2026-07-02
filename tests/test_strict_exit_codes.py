"""Tests for strict-posture exit codes (F2) and epsilon in strict validation (F3)."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from benchmark import (
    EXIT_OK,
    EXIT_STRICT_NON_COMPLIANT,
    run_share_analysis,
)
from core.compliance import build_strict_final_validation
from core.constants import COMPARISON_EPSILON
from core.privacy_validation import PrivacyValidationRow, PrivacyValidationResult


def _share_args(
    output: Path,
    df: pd.DataFrame,
    *,
    compliance_posture: str | None = "strict",
    preset: str | None = "compliance_strict",
) -> SimpleNamespace:
    return SimpleNamespace(
        csv="",
        df=df,
        metric="txn_cnt",
        secondary_metrics=None,
        entity="Target",
        entity_col="issuer_name",
        output=str(output),
        dimensions=["card_type"],
        auto=False,
        time_col=None,
        config=None,
        preset=preset,
        debug=False,
        log_level="INFO",
        per_dimension_weights=False,
        export_balanced_csv=False,
        validate_input=False,
        compare_presets=False,
        analyze_distortion=False,
        analyze_impact=False,
        output_format="analysis",
        include_calculated=False,
        auto_subset_search=None,
        subset_search_max_tests=None,
        trigger_subset_on_slack=None,
        max_cap_slack=None,
        compliance_posture=compliance_posture,
        acknowledge_accuracy_first=False,
        validate_export=False,
        report_format=None,
        audit_package=False,
        lean=False,
        privacy_basis=None,
        contains_digital_wallet_metrics=None,
        digital_wallet_review_approved=None,
        contains_top_merchant_output=None,
        dual_entity_axis=None,
        dual_entity_axis_review_approved=None,
        recurring_deliverable=None,
        last_privacy_recheck_date=None,
        peer_group_altered=None,
    )


def _violating_share_df() -> pd.DataFrame:
    """Dataset with an exclusive PREPAID category (single peer) under 6 peers."""
    rows: list[dict[str, object]] = []
    for entity in ["Target", "P1", "P2", "P3", "P4", "P5", "P6"]:
        rows.append({"issuer_name": entity, "card_type": "CREDIT", "txn_cnt": 100})
    rows.append({"issuer_name": "P1", "card_type": "PREPAID", "txn_cnt": 5000})
    return pd.DataFrame(rows)


def _compliant_share_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "issuer_name": ["Target", "P1", "P2", "P3", "P4", "P5", "P6"],
            "card_type": ["A", "A", "A", "A", "A", "A", "A"],
            "txn_cnt": [100, 200, 180, 160, 140, 120, 110],
        }
    )


@pytest.mark.parametrize("epsilon_offset", [5e-7, COMPARISON_EPSILON / 2])
def test_build_strict_final_validation_dataframe_ignores_epsilon_noise(
    epsilon_offset: float,
) -> None:
    cap = 25.0
    privacy_validation_df = pd.DataFrame(
        {
            "Dimension": ["card_type"],
            "Category": ["Credit"],
            "Rule_Name": ["5/25"],
            "Balanced_Share_%": [cap + epsilon_offset],
            "Privacy_Cap_%": [cap],
        }
    )

    result = build_strict_final_validation(privacy_validation_df)

    assert result["primary_cap_fail_rows"] == 0


def test_build_strict_final_validation_dataframe_flags_material_cap_excess() -> None:
    cap = 25.0
    privacy_validation_df = pd.DataFrame(
        {
            "Dimension": ["card_type"],
            "Category": ["Credit"],
            "Rule_Name": ["5/25"],
            "Balanced_Share_%": [cap + 1e-3],
            "Privacy_Cap_%": [cap],
        }
    )

    result = build_strict_final_validation(privacy_validation_df)

    assert result["primary_cap_fail_rows"] == 1


@pytest.mark.parametrize("epsilon_offset", [5e-7, COMPARISON_EPSILON / 2])
def test_build_strict_final_validation_typed_rows_ignores_epsilon_noise(
    epsilon_offset: float,
) -> None:
    cap = 25.0
    rows = [
        PrivacyValidationRow(
            dimension="card_type",
            category="Credit",
            time_period=None,
            peer="P1",
            rule_name="5/25",
            original_volume=100.0,
            original_share_pct=cap + epsilon_offset,
            balanced_volume=100.0,
            balanced_share_pct=cap + epsilon_offset,
            primary_cap_pct=cap,
            primary_cap_passed=True,
            secondary_rule_passed=True,
            relaxation_used=False,
            strict_compliant=True,
        )
    ]

    result = build_strict_final_validation(PrivacyValidationResult(rows=rows))

    assert result["primary_cap_fail_rows"] == 0


def test_build_strict_final_validation_typed_rows_flags_material_cap_excess() -> None:
    cap = 25.0
    rows = [
        PrivacyValidationRow(
            dimension="card_type",
            category="Credit",
            time_period=None,
            peer="P1",
            rule_name="5/25",
            original_volume=100.0,
            original_share_pct=cap + 1e-3,
            balanced_volume=100.0,
            balanced_share_pct=cap + 1e-3,
            primary_cap_pct=cap,
            primary_cap_passed=False,
            secondary_rule_passed=True,
            relaxation_used=False,
            strict_compliant=False,
        )
    ]

    result = build_strict_final_validation(PrivacyValidationResult(rows=rows))

    assert result["primary_cap_fail_rows"] == 1


def test_strict_posture_non_compliant_share_run_returns_exit_2(tmp_path: Path) -> None:
    output = tmp_path / "strict_violation.xlsx"
    logger = logging.getLogger("test_strict_exit_codes")

    result = run_share_analysis(
        _share_args(output, _violating_share_df(), compliance_posture="strict"),
        logger,
    )

    assert result == EXIT_STRICT_NON_COMPLIANT
    assert output.exists()


def test_best_effort_same_data_returns_exit_0(tmp_path: Path) -> None:
    output = tmp_path / "best_effort_violation.xlsx"
    logger = logging.getLogger("test_strict_exit_codes")

    result = run_share_analysis(
        _share_args(
            output,
            _violating_share_df(),
            compliance_posture="best_effort",
            preset="balanced_default",
        ),
        logger,
    )

    assert result == EXIT_OK
    assert output.exists()


def test_compliant_strict_share_run_returns_exit_0(tmp_path: Path) -> None:
    output = tmp_path / "strict_compliant.xlsx"
    logger = logging.getLogger("test_strict_exit_codes")
    args = _share_args(output, _compliant_share_df(), compliance_posture="strict")
    args.validate_input = True

    result = run_share_analysis(args, logger)

    assert result == EXIT_OK
    assert output.exists()


def test_insufficient_peers_message_includes_peer_detail(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    df = pd.DataFrame(
        [
            {"issuer_name": "Target", "card_type": "A", "txn_cnt": 100},
            {"issuer_name": "P1", "card_type": "A", "txn_cnt": 900},
            {"issuer_name": "P2", "card_type": "A", "txn_cnt": 50},
            {"issuer_name": "P3", "card_type": "A", "txn_cnt": 50},
        ]
    )
    args = _share_args(tmp_path / "insufficient.xlsx", df, compliance_posture="strict")
    args.validate_input = False

    result = run_share_analysis(args, logging.getLogger("test_strict_exit_codes"))

    captured = capsys.readouterr()
    combined = captured.out + captured.err

    assert result == 1
    assert "Minimum" in combined or "peer entities found" in combined.lower()
