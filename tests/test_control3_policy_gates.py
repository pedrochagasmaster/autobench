from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from openpyxl import load_workbook

from benchmark import run_share_analysis
from core.analysis_run import RunBlocked, build_run_request, enforce_compliance_preconditions
from core.control3_policy import Control3PolicyInput, evaluate_control3_policy
from utils.config_manager import ConfigManager
from utils.validators import ConfigValidator


def test_fraud_and_chargeback_metrics_require_clearing_spend_privacy_basis() -> None:
    policy = evaluate_control3_policy(
        Control3PolicyInput(
            analysis_mode="rate",
            rate_types=["fraud"],
            privacy_basis=None,
        )
    )

    assert not policy.allowed
    assert policy.blocked_reason == "fraud_chargeback_requires_clearing_spend_basis"


def test_fraud_metrics_allow_explicit_clearing_spend_privacy_basis() -> None:
    policy = evaluate_control3_policy(
        Control3PolicyInput(
            analysis_mode="rate",
            rate_types=["fraud"],
            privacy_basis="clearing_spend",
        )
    )

    assert policy.allowed
    assert policy.requirements["fraud_chargeback_privacy_basis"] == "enforced"


def test_digital_wallet_metrics_require_privacy_review_approval() -> None:
    policy = evaluate_control3_policy(
        Control3PolicyInput(
            contains_digital_wallet_metrics=True,
            digital_wallet_review_approved=False,
        )
    )

    assert not policy.allowed
    assert policy.blocked_reason == "digital_wallet_metrics_require_privacy_review"


def test_top_merchant_output_is_hard_blocked() -> None:
    policy = evaluate_control3_policy(
        Control3PolicyInput(
            contains_top_merchant_output=True,
            digital_wallet_review_approved=True,
            dual_entity_axis_review_approved=True,
        )
    )

    assert not policy.allowed
    assert policy.blocked_reason == "top_merchant_lists_not_allowed"


def test_dual_entity_axis_requires_manual_privacy_review() -> None:
    policy = evaluate_control3_policy(
        Control3PolicyInput(
            dual_entity_axis=True,
            dual_entity_axis_review_approved=False,
        )
    )

    assert not policy.allowed
    assert policy.blocked_reason == "dual_entity_axis_requires_privacy_review"


def test_digital_wallet_review_does_not_approve_dual_entity_axis() -> None:
    policy = evaluate_control3_policy(
        Control3PolicyInput(
            contains_digital_wallet_metrics=True,
            digital_wallet_review_approved=True,
            dual_entity_axis=True,
            dual_entity_axis_review_approved=False,
        )
    )

    assert not policy.allowed
    assert policy.blocked_reason == "dual_entity_axis_requires_privacy_review"


def test_control3_config_recheck_date_must_be_iso_date() -> None:
    errors = ConfigValidator.validate(
        {
            "version": "3.0",
            "compliance_posture": "strict",
            "control3": {"last_privacy_recheck_date": "2026/06/03"},
        }
    )

    assert "control3.last_privacy_recheck_date must be a YYYY-MM-DD string or null" in errors


def test_control3_config_rejects_overloaded_privacy_review_approval() -> None:
    errors = ConfigValidator.validate(
        {
            "version": "3.0",
            "compliance_posture": "strict",
            "control3": {"privacy_review_approved": True},
        }
    )

    assert "Unknown control3 fields: privacy_review_approved" in errors


def test_recurring_deliverable_requires_recheck_when_peer_group_altered() -> None:
    policy = evaluate_control3_policy(
        Control3PolicyInput(
            recurring_deliverable=True,
            peer_group_altered=True,
            last_privacy_recheck_date="2026-01-15",
        ),
        today=date(2026, 6, 3),
    )

    assert not policy.allowed
    assert policy.blocked_reason == "recurring_deliverable_recheck_required"


def test_recurring_deliverable_requires_annual_recheck() -> None:
    policy = evaluate_control3_policy(
        Control3PolicyInput(
            recurring_deliverable=True,
            peer_group_altered=False,
            last_privacy_recheck_date="2025-06-02",
        ),
        today=date(2026, 6, 3),
    )

    assert not policy.allowed
    assert policy.blocked_reason == "recurring_deliverable_recheck_required"


def test_compliance_preconditions_block_declared_sensitive_run() -> None:
    request = build_run_request(
        "rate",
        SimpleNamespace(
            acknowledge_accuracy_first=False,
            approved_col=None,
            fraud_col="fraud",
            privacy_basis=None,
            contains_digital_wallet_metrics=False,
            contains_top_merchant_output=False,
            dual_entity_axis=False,
            recurring_deliverable=False,
            last_privacy_recheck_date=None,
            peer_group_altered=False,
        ),
    )
    config = ConfigManager()

    with pytest.raises(RunBlocked) as exc_info:
        enforce_compliance_preconditions(config, request)

    assert exc_info.value.compliance_summary["reason"] == "fraud_chargeback_requires_clearing_spend_basis"


def test_publication_peer_evidence_redacts_peer_composition(tmp_path: Path) -> None:
    output = tmp_path / "share.xlsx"
    df = pd.DataFrame(
        {
            "issuer_name": ["Target", "P1", "P2", "P3", "P4", "P5"],
            "card_type": ["A", "A", "A", "A", "A", "A"],
            "txn_cnt": [100, 100, 100, 100, 100, 100],
        }
    )
    args = SimpleNamespace(
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
        preset=None,
        debug=True,
        log_level="INFO",
        per_dimension_weights=False,
        export_balanced_csv=False,
        validate_input=False,
        compare_presets=False,
        analyze_distortion=False,
        output_format="both",
        include_calculated=False,
        auto_subset_search=None,
        subset_search_max_tests=None,
        trigger_subset_on_slack=None,
        max_cap_slack=None,
        compliance_posture=None,
        acknowledge_accuracy_first=False,
        privacy_basis=None,
        contains_digital_wallet_metrics=False,
        contains_top_merchant_output=False,
        dual_entity_axis=False,
        recurring_deliverable=False,
        last_privacy_recheck_date=None,
        peer_group_altered=False,
    )

    assert run_share_analysis(args, __import__("logging").getLogger("test_control3_publication")) == 0

    workbook = load_workbook(tmp_path / "share_publication.xlsx", read_only=True)
    try:
        assert "Peer Weights" in workbook.sheetnames
        values = [
            str(cell.value)
            for row in workbook["Peer Weights"].iter_rows()
            for cell in row
            if cell.value is not None
        ]
        assert "P1" not in values
        assert "P2" not in values
        assert any("Control 3.3" in value for value in values)
    finally:
        workbook.close()
