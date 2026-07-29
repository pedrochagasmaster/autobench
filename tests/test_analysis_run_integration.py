"""In-process integration tests for core.analysis_run orchestration.

Minimal required fields (AnalysisRunRequest defaults cover the rest):

Share run:
  - csv (or pre-loaded df)
  - entity (target name in data)
  - metric (column present in data)
  - dimensions (list, or auto=True with auto-detect enabled in config)
  - output (workbook path)
  - compliance_posture when preset is set (see note below)

Rate run (mode defaults to "share"; must set mode="rate"):
  - csv (or df)
  - entity
  - total_col, and at least one of approved_col / fraud_col (columns in data)
  - dimensions
  - output
  - export_balanced_csv=True when asserting balanced CSV output
  - control3_overrides privacy_basis=clearing_spend when fraud_col is set

When preset is set, also pass compliance_posture explicitly (matches TUI; avoids
ConfigManager material-override guard on per_dimension_weights default).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import load_workbook

import benchmark
from core.analysis_run import execute_rate_run, execute_share_run
from core.analysis_run import RunBlocked
from core.contracts import AnalysisRunRequest, PrivacyRuleStrategy, PrivacySweepStatus
from core.dimensional_analyzer import DimensionalAnalyzer

FIXTURE = Path(__file__).parent / "fixtures" / "gate_demo.csv"
SHARE_DIMENSIONS = ["card_type", "channel"]


def _single_category_df(shares: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"issuer_name": f"P{index}", "segment": "all", "amount": share}
            for index, share in enumerate(shares, start=1)
        ]
    )


def test_share_run_end_to_end(tmp_path: Path) -> None:
    out = tmp_path / "share_it.xlsx"
    request = AnalysisRunRequest(
        csv=str(FIXTURE),
        entity="Target",
        metric="txn_cnt",
        dimensions=SHARE_DIMENSIONS,
        time_col="year_month",
        preset="balanced_default",
        compliance_posture="strict",
        output=str(out),
    )
    artifacts = execute_share_run(request, logging.getLogger("test"))

    assert out.exists()
    wb = load_workbook(out)
    sheet_names = set(wb.sheetnames)
    assert "Summary" in sheet_names
    assert "Weight Methods" in sheet_names
    assert "Rank Changes" in sheet_names
    for dim in SHARE_DIMENSIONS:
        assert dim in sheet_names

    assert artifacts.compliance_summary is not None
    assert artifacts.compliance_summary["compliance_verdict"] == "fully_compliant"
    assert artifacts.privacy_rule_strategy_result is not None
    assert (
        artifacts.privacy_rule_strategy_result.strategy
        == PrivacyRuleStrategy.SELECT_BY_PEER_COUNT
    )

    expected = {out.name, f"{out.stem}_audit.log"}
    assert {p.name for p in tmp_path.iterdir()} == expected


def test_share_run_sweep_optimizes_each_applicable_rule(tmp_path: Path) -> None:
    out = tmp_path / "share_sweep.xlsx"
    request = AnalysisRunRequest(
        csv=str(FIXTURE),
        entity="Target",
        metric="txn_cnt",
        dimensions=SHARE_DIMENSIONS,
        time_col="year_month",
        preset="balanced_default",
        compliance_posture="strict",
        output=str(out),
        privacy_rule_strategy=PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE,
    )
    artifacts = execute_share_run(request, logging.getLogger("test"))

    sweep = artifacts.privacy_rule_strategy_result
    assert sweep is not None
    assert sweep.strategy == PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE
    assert len(sweep.rule_set_digest) == 64
    assert tuple(e.rule_name for e in sweep.candidate_attempt_evaluations) == (
        "5/25", "6/30", "7/35", "10/40", "4/35"
    )
    assert sweep.display_rule == artifacts.analyzer.privacy_rule_name
    assert set(sweep.authorizing_rules).issubset({"5/25", "6/30", "7/35"})
    assert artifacts.compliance_summary is not None
    assert artifacts.compliance_summary["compliance_verdict"] == "fully_compliant"


def test_sweep_authorizers_are_recomputed_against_emitted_candidate(tmp_path: Path) -> None:
    request = AnalysisRunRequest(
        df=_single_category_df([34, 12, 12, 8, 7, 7, 6, 5, 5, 4]),
        csv="",
        metric="amount",
        dimensions=["segment"],
        output=str(tmp_path / "divergent.xlsx"),
        compliance_posture="strict",
        validate_input=False,
        privacy_rule_strategy=PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE,
    )

    artifacts = execute_share_run(request, logging.getLogger("test"))
    sweep = artifacts.privacy_rule_strategy_result

    assert sweep is not None
    assert sweep.display_rule == "10/40"
    assert "5/25" in sweep.feasible_candidate_rules
    assert "5/25" not in sweep.authorizing_rules
    assert "10/40" in sweep.authorizing_rules
    emitted = {
        evaluation.rule_name: evaluation.status.value
        for evaluation in sweep.emitted_output_evaluations
    }
    assert emitted["5/25"] == "failed"
    assert emitted["10/40"] == "passed"
    assert {
        evaluation.rule_name
        for evaluation in sweep.emitted_output_evaluations
        if evaluation.status.value != "not_applicable"
    } == {"5/25", "6/30", "7/35", "10/40"}
    assert artifacts.analyzer.privacy_rule_name == sweep.display_rule
    assert artifacts.metadata is not None
    assert artifacts.metadata["privacy_rule_strategy"]["display_rule"] == sweep.display_rule


def test_sweep_selects_only_feasible_merchant_4_35_candidate(tmp_path: Path) -> None:
    request = AnalysisRunRequest(
        df=_single_category_df([34, 22, 22, 22]),
        csv="",
        metric="amount",
        dimensions=["segment"],
        output=str(tmp_path / "merchant.xlsx"),
        compliance_posture="strict",
        validate_input=False,
        privacy_rule_strategy=PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE,
        is_anonymized_aggregated_merchant_spend=True,
    )

    artifacts = execute_share_run(request, logging.getLogger("test"))
    sweep = artifacts.privacy_rule_strategy_result

    assert sweep is not None
    assert sweep.feasible_candidate_rules == ("4/35",)
    assert sweep.authorizing_rules == ("4/35",)
    assert sweep.display_rule == "4/35"


def test_merchant_4_35_context_reaches_normal_input_validation(tmp_path: Path) -> None:
    request = AnalysisRunRequest(
        df=_single_category_df([34, 22, 22, 22]),
        csv="",
        metric="amount",
        dimensions=["segment"],
        output=str(tmp_path / "merchant_validated.xlsx"),
        compliance_posture="strict",
        privacy_rule_strategy=PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE,
        is_anonymized_aggregated_merchant_spend=True,
    )

    artifacts = execute_share_run(request, logging.getLogger("test"))

    assert artifacts.privacy_rule_strategy_result is not None
    assert artifacts.privacy_rule_strategy_result.authorizing_rules == ("4/35",)


def test_sweep_cannot_authorize_when_every_candidate_attempt_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_fit(*_args, **_kwargs):
        raise ValueError("forced optimizer failure")

    monkeypatch.setattr(DimensionalAnalyzer, "fit_privacy_weights", fail_fit)
    request = AnalysisRunRequest(
        df=_single_category_df([25, 25, 20, 15, 15]),
        csv="",
        metric="amount",
        dimensions=["segment"],
        output=str(tmp_path / "all_attempts_fail.xlsx"),
        compliance_posture="best_effort",
        validate_input=False,
        privacy_rule_strategy=PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE,
    )

    artifacts = execute_share_run(request, logging.getLogger("test"))
    sweep = artifacts.privacy_rule_strategy_result

    assert sweep is not None
    assert not sweep.feasible_candidate_rules
    assert not sweep.numeric_rules_passed
    assert not sweep.authorizing_rules
    assert sweep.status == PrivacySweepStatus.NUMERICALLY_NONCOMPLIANT
    assert all(
        evaluation.status.value != "passed"
        for evaluation in sweep.emitted_output_evaluations
    )


def test_citi_overlay_blocks_emitted_candidate_that_passes_base_rule(tmp_path: Path) -> None:
    primary = [20, 20, 10, 10, 10, 6, 6, 6, 6, 6]
    secondary = [30, 20, 10, 10, 10, 5, 5, 4, 3, 3]
    df = _single_category_df(primary)
    df["secondary"] = secondary
    request = AnalysisRunRequest(
        df=df,
        csv="",
        metric="amount",
        secondary_metrics=["secondary"],
        dimensions=["segment"],
        output=str(tmp_path / "citi_block.xlsx"),
        compliance_posture="strict",
        output_format="both",
        validate_input=False,
        privacy_rule_strategy=PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE,
        citibank_entity_name="P1",
        citi_competitor_receives_output=True,
    )

    artifacts = execute_share_run(request, logging.getLogger("test"))
    sweep = artifacts.privacy_rule_strategy_result

    assert sweep is not None
    assert sweep.numeric_rules_passed
    assert not sweep.mandatory_overlays_passed
    assert not sweep.authorizing_rules
    assert sweep.status == PrivacySweepStatus.BLOCKED_BY_MANDATORY_OVERLAY
    assert sweep.mandatory_overlay_evaluations[0].status.value == "failed"
    assert (
        sweep.mandatory_overlay_evaluations[0].failure_reasons[0].code
        == "citibank_concentration_exceeded"
    )
    assert artifacts.compliance_summary is not None
    assert artifacts.compliance_summary["compliance_verdict"] != "fully_compliant"
    assert artifacts.publication_output is None
    assert artifacts.audit_log_output is not None
    audit_text = Path(artifacts.audit_log_output).read_text(encoding="utf-8")
    assert "emitted_output_evaluations" in audit_text
    assert "authorizing_rules" in audit_text
    assert (
        benchmark._resolve_exit_code(
            "strict",
            artifacts.compliance_summary["compliance_verdict"],
        )
        == benchmark.EXIT_STRICT_NON_COMPLIANT
    )


def test_default_strategy_still_blocks_failed_citi_overlay(tmp_path: Path) -> None:
    primary = [20, 20, 10, 10, 10, 6, 6, 6, 6, 6]
    df = _single_category_df(primary)
    df["secondary"] = [30, 20, 10, 10, 10, 5, 5, 4, 3, 3]
    request = AnalysisRunRequest(
        df=df,
        csv="",
        metric="amount",
        secondary_metrics=["secondary"],
        dimensions=["segment"],
        output=str(tmp_path / "default_citi_block.xlsx"),
        compliance_posture="strict",
        validate_input=False,
        citibank_entity_name="P1",
        citi_competitor_receives_output=True,
    )

    artifacts = execute_share_run(request, logging.getLogger("test"))

    assert artifacts.privacy_rule_strategy_result is not None
    assert not artifacts.privacy_rule_strategy_result.mandatory_overlays_passed
    assert artifacts.compliance_summary is not None
    assert artifacts.compliance_summary["compliance_verdict"] != "fully_compliant"


def test_cli_sweep_exit_audit_and_publication_agree_when_citi_blocks(
    tmp_path: Path,
) -> None:
    df = _single_category_df([20, 20, 10, 10, 10, 6, 6, 6, 6, 6])
    df["secondary"] = [30, 20, 10, 10, 10, 5, 5, 4, 3, 3]
    csv_path = tmp_path / "citi_cli.csv"
    output = tmp_path / "citi_cli.xlsx"
    df.to_csv(csv_path, index=False)
    args = benchmark.create_parser().parse_args(
        [
            "share",
            "--csv",
            str(csv_path),
            "--metric",
            "amount",
            "--secondary-metrics",
            "secondary",
            "--dimensions",
            "segment",
            "--compliance-posture",
            "strict",
            "--output",
            str(output),
            "--output-format",
            "both",
            "--privacy-rule-sweep",
            "--citibank-entity-name",
            "P1",
            "--citi-competitor-receives-output",
        ]
    )

    exit_code = benchmark.run_share_analysis(args, logging.getLogger("test"))

    assert exit_code == benchmark.EXIT_STRICT_NON_COMPLIANT
    assert output.exists()
    assert not list(tmp_path.glob("*publication*.xlsx"))
    audit_text = (tmp_path / "citi_cli_audit.log").read_text(encoding="utf-8")
    assert "blocked_by_mandatory_overlay" in audit_text
    assert "'authorizing_rules': ()" in audit_text


@pytest.mark.parametrize(
    "citi_name",
    [None, "missing", "Citibank"],
)
def test_integrated_citi_identity_fails_closed(
    tmp_path: Path,
    citi_name: str | None,
) -> None:
    names = ["Citibank", "CITIBANK", "P3", "P4", "P5"]
    df = pd.DataFrame(
        [
            {"issuer_name": name, "segment": "all", "amount": 20}
            for name in names
        ]
    )
    request = AnalysisRunRequest(
        df=df,
        csv="",
        metric="amount",
        dimensions=["segment"],
        output=str(tmp_path / "citi_invalid.xlsx"),
        compliance_posture="strict",
        validate_input=False,
        privacy_rule_strategy=PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE,
        citibank_entity_name=citi_name,
        citi_competitor_receives_output=True,
    )

    with pytest.raises(RunBlocked):
        execute_share_run(request, logging.getLogger("test"))


def test_rate_run_end_to_end(tmp_path: Path) -> None:
    out = tmp_path / "rate_it.xlsx"
    request = AnalysisRunRequest(
        mode="rate",
        csv=str(FIXTURE),
        entity="Target",
        total_col="total",
        approved_col="approved",
        fraud_col="fraud",
        dimensions=SHARE_DIMENSIONS,
        time_col="year_month",
        preset="balanced_default",
        compliance_posture="strict",
        control3_overrides={"privacy_basis": "clearing_spend"},
        output=str(out),
        export_balanced_csv=True,
    )
    artifacts = execute_rate_run(request, logging.getLogger("test"))

    assert out.exists()
    csv_path = tmp_path / f"{out.stem}_balanced.csv"
    assert csv_path.exists()
    assert artifacts.csv_output == str(csv_path)

    df = pd.read_csv(csv_path)
    assert "Dimension" in df.columns
    assert "Category" in df.columns
    assert len(df) >= 1

    expected = {out.name, csv_path.name, f"{out.stem}_audit.log"}
    assert {p.name for p in tmp_path.iterdir()} == expected


def test_python_rate_sweep_runs_through_shared_executor(tmp_path: Path) -> None:
    request = AnalysisRunRequest(
        mode="rate",
        csv=str(FIXTURE),
        entity="Target",
        total_col="total",
        approved_col="approved",
        dimensions=SHARE_DIMENSIONS,
        time_col="year_month",
        preset="balanced_default",
        compliance_posture="strict",
        output=str(tmp_path / "rate_sweep.xlsx"),
        privacy_rule_strategy=PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE,
    )

    artifacts = execute_rate_run(request, logging.getLogger("test"))

    assert artifacts.privacy_rule_strategy_result is not None
    assert (
        artifacts.privacy_rule_strategy_result.strategy
        == PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE
    )


def test_fraud_rate_sweep_requires_explicit_concentration_column(tmp_path: Path) -> None:
    request = AnalysisRunRequest(
        mode="rate",
        csv=str(FIXTURE),
        entity="Target",
        total_col="total",
        fraud_col="fraud",
        dimensions=SHARE_DIMENSIONS,
        time_col="year_month",
        preset="balanced_default",
        compliance_posture="strict",
        control3_overrides={"privacy_basis": "clearing_spend"},
        output=str(tmp_path / "fraud_sweep.xlsx"),
        privacy_rule_strategy=PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE,
    )

    with pytest.raises(RunBlocked):
        execute_rate_run(request, logging.getLogger("test"))


def test_fraud_only_sweep_uses_clearing_spend_not_total_distribution(
    tmp_path: Path,
) -> None:
    df = pd.DataFrame(
        [
            {
                "issuer_name": f"P{index}",
                "segment": "all",
                "total": total,
                "fraud": 1,
                "clearing_spend": clearing,
            }
            for index, (total, clearing) in enumerate(
                zip([80, 5, 5, 5, 5], [20, 20, 20, 20, 20]),
                start=1,
            )
        ]
    )
    request = AnalysisRunRequest(
        mode="rate",
        df=df,
        csv="",
        total_col="total",
        fraud_col="fraud",
        privacy_concentration_col="clearing_spend",
        dimensions=["segment"],
        output=str(tmp_path / "fraud_basis.xlsx"),
        compliance_posture="strict",
        validate_input=False,
        control3_overrides={"privacy_basis": "clearing_spend"},
        privacy_rule_strategy=PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE,
    )

    artifacts = execute_rate_run(request, logging.getLogger("test"))

    assert artifacts.privacy_rule_strategy_result is not None
    assert artifacts.privacy_rule_strategy_result.authorizing_rules == ("5/25",)


def test_approval_and_fraud_sweep_governs_total_and_clearing_spend(
    tmp_path: Path,
) -> None:
    df = pd.DataFrame(
        [
            {
                "issuer_name": f"P{index}",
                "segment": "all",
                "total": total,
                "approved": total * 0.8,
                "fraud": 1,
                "clearing_spend": clearing,
            }
            for index, (total, clearing) in enumerate(
                zip([80, 5, 5, 5, 5], [20, 20, 20, 20, 20]),
                start=1,
            )
        ]
    )
    request = AnalysisRunRequest(
        mode="rate",
        df=df,
        csv="",
        total_col="total",
        approved_col="approved",
        fraud_col="fraud",
        privacy_concentration_col="clearing_spend",
        dimensions=["segment"],
        output=str(tmp_path / "approval_fraud_bases.xlsx"),
        compliance_posture="best_effort",
        validate_input=False,
        control3_overrides={"privacy_basis": "clearing_spend"},
        privacy_rule_strategy=PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE,
    )

    artifacts = execute_rate_run(request, logging.getLogger("test"))

    assert artifacts.privacy_rule_strategy_result is not None
    assert not artifacts.privacy_rule_strategy_result.numeric_rules_passed
    assert not artifacts.privacy_rule_strategy_result.authorizing_rules


@pytest.mark.parametrize("mode", ["share", "rate"])
def test_cli_sweep_executes_normal_analysis(
    tmp_path: Path,
    mode: str,
) -> None:
    output = tmp_path / f"cli_{mode}.xlsx"
    common = [
        mode,
        "--csv",
        str(FIXTURE),
        "--entity",
        "Target",
        "--dimensions",
        *SHARE_DIMENSIONS,
        "--preset",
        "balanced_default",
        "--compliance-posture",
        "strict",
        "--output",
        str(output),
        "--privacy-rule-sweep",
        "--time-col",
        "year_month",
    ]
    args = benchmark.create_parser().parse_args(
        common
        + (
            ["--metric", "txn_cnt"]
            if mode == "share"
            else ["--total-col", "total", "--approved-col", "approved"]
        )
    )

    exit_code = (
        benchmark.run_share_analysis(args, logging.getLogger("test"))
        if mode == "share"
        else benchmark.run_rate_analysis(args, logging.getLogger("test"))
    )

    assert exit_code == benchmark.EXIT_OK
    assert output.exists()
