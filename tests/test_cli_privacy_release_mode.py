"""CLI tests for --privacy-release-mode (Plan 002 Commit 7).

Covers parsing/coupling plus runtime success summary, empty Release Set
denial, and suppressed-marker absence in captured CLI output.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import benchmark
from core.contracts import PrivacyReleaseMode, PrivacyRuleStrategy
from core.privacy_output_policy import CONTROL3_SAFE_COVERAGE_EMPTY
from tests.fixtures.safe_coverage_fixture import (
    build_safe_coverage_getnet_shaped_df,
    write_safe_coverage_bounds_config,
)
from tests.test_privacy_coverage_outputs import SUPPRESSED_MARKER, _seed_suppressed_marker
from utils.config_manager import ConfigManager


def _share_argv(*extra: str) -> list[str]:
    return ["share", "--csv", "data.csv", "--metric", "txn_cnt", *extra]


def _share_parser() -> argparse.ArgumentParser:
    parser = benchmark.create_parser()
    share = parser._subparsers._group_actions[0].choices["share"]
    assert isinstance(share, argparse.ArgumentParser)
    return share


def test_help_text_and_exact_choices() -> None:
    share = _share_parser()
    action = next(
        a for a in share._actions if a.dest == "privacy_release_mode"
    )
    assert action.default is None
    assert action.type is PrivacyReleaseMode
    assert list(action.choices) == [
        PrivacyReleaseMode.COMPLETE_OUTPUT.value,
        PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE.value,
    ]
    help_text = share.format_help()
    assert "--privacy-release-mode {complete-output,verified-safe-coverage}" in help_text
    assert "effective default: complete-output" in help_text
    assert "complete authorized output" in help_text
    assert "incomplete safe view" in help_text
    assert "global weights" in help_text
    assert "rule sweep" in help_text
    assert "privacy-suppressed" in help_text


def test_omitted_flag_with_no_yaml_leaves_request_none() -> None:
    args = benchmark.create_parser().parse_args(_share_argv())
    assert args.privacy_release_mode is None
    request = benchmark.build_run_request("share", args)
    assert request.privacy_release_mode is None


def test_omitted_flag_with_yaml_verified_safe_coverage(tmp_path: Path) -> None:
    path = tmp_path / "release.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": "3.0",
                "compliance_posture": "strict",
                "privacy_release_mode": "verified-safe-coverage",
            }
        ),
        encoding="utf-8",
    )
    args = benchmark.create_parser().parse_args(
        _share_argv("--config", str(path))
    )
    assert args.privacy_release_mode is None
    config = ConfigManager(
        config_file=str(path),
        cli_overrides={"privacy_release_mode": args.privacy_release_mode},
    )
    assert config.get("privacy_release_mode") == "verified-safe-coverage"
    assert (
        config.resolve().privacy_release_mode
        is PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE
    )


def test_explicit_cli_overrides_yaml(tmp_path: Path) -> None:
    path = tmp_path / "release.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": "3.0",
                "compliance_posture": "strict",
                "privacy_release_mode": "complete-output",
            }
        ),
        encoding="utf-8",
    )
    args = benchmark.create_parser().parse_args(
        _share_argv(
            "--config",
            str(path),
            "--privacy-release-mode",
            "verified-safe-coverage",
        )
    )
    assert args.privacy_release_mode is PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE
    request = benchmark.build_run_request("share", args)
    assert request.privacy_release_mode is PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE
    config = ConfigManager(
        config_file=str(path),
        cli_overrides={"privacy_release_mode": args.privacy_release_mode},
    )
    assert config.get("privacy_release_mode") == "verified-safe-coverage"


def test_invalid_value_rejected() -> None:
    parser = benchmark.create_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            _share_argv("--privacy-release-mode", "weaken-privacy")
        )


def test_rate_parser_rejects_privacy_release_mode_flag() -> None:
    parser = benchmark.create_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "rate",
                "--csv",
                "data.csv",
                "--total-col",
                "txn_cnt",
                "--privacy-release-mode",
                "verified-safe-coverage",
            ]
        )
    rate_parser = parser._subparsers._group_actions[0].choices["rate"]
    assert isinstance(rate_parser, argparse.ArgumentParser)
    rate_dests = {action.dest for action in rate_parser._actions}
    assert "privacy_release_mode" not in rate_dests


def test_per_dimension_rejection() -> None:
    args = benchmark.create_parser().parse_args(
        _share_argv(
            "--privacy-release-mode",
            "verified-safe-coverage",
            "--per-dimension-weights",
        )
    )
    with pytest.raises(ValueError, match="per-dimension-weights"):
        benchmark.build_run_request("share", args)


def test_compatible_rule_sweep_auto_selection() -> None:
    args = benchmark.create_parser().parse_args(
        _share_argv("--privacy-release-mode", "verified-safe-coverage")
    )
    assert not args.privacy_rule_sweep
    request = benchmark.build_run_request("share", args)
    assert request.privacy_release_mode is PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE
    assert (
        request.privacy_rule_strategy
        is PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE
    )
    assert args.privacy_rule_sweep is True


def test_copyable_cli_example_parses() -> None:
    args = benchmark.create_parser().parse_args(
        list(benchmark.VERIFIED_SAFE_COVERAGE_CLI_EXAMPLE)
    )
    assert args.privacy_release_mode is PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE
    assert args.privacy_rule_sweep is True
    assert args.metric == "transaction_amount"
    assert args.secondary_metrics == ["transaction_count", "merchant_count"]
    assert args.dimensions == ["quarter", "region", "sector"]
    request = benchmark.build_run_request("share", args)
    assert request.privacy_release_mode is PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE
    assert (
        request.privacy_rule_strategy
        is PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE
    )


def test_flag_not_registered_in_common_run_flags() -> None:
    parser = argparse.ArgumentParser()
    benchmark.add_common_run_flags(parser, preset_choices=[])
    dests = {action.dest for action in parser._actions}
    assert "privacy_release_mode" not in dests


def _msc_cli_args(
    tmp_path: Path,
    *,
    df,
    output_name: str = "cli_msc.xlsx",
    config_extra: dict | None = None,
    min_weight: float = 0.5,
    max_weight: float = 2.0,
) -> SimpleNamespace:
    config_path = write_safe_coverage_bounds_config(
        tmp_path / "bounds.yaml",
        min_weight=min_weight,
        max_weight=max_weight,
        extra=config_extra,
    )
    return SimpleNamespace(
        csv="",
        df=df,
        metric="transaction_amount",
        secondary_metrics=["transaction_count", "merchant_count"],
        entity=None,
        entity_col="issuer_name",
        output=str(tmp_path / output_name),
        dimensions=["region", "sector"],
        auto=False,
        time_col="quarter",
        config=str(config_path),
        preset=None,
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
        compliance_posture="best_effort",
        acknowledge_accuracy_first=False,
        validate_export=False,
        report_format=None,
        audit_package=False,
        lean=False,
        privacy_basis=None,
        privacy_rule_sweep=True,
        privacy_release_mode=PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE,
    )


def test_cli_safe_success_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    df = build_safe_coverage_getnet_shaped_df()
    args = _msc_cli_args(tmp_path, df=df)
    code = benchmark.run_share_analysis(
        args, logging.getLogger("test_cli_msc_success")
    )
    captured = capsys.readouterr().out

    assert code == benchmark.EXIT_OK
    assert "Privacy release mode: Verified safe coverage" in captured
    assert "Candidate units: 9" in captured
    assert "Released units: 4" in captured
    assert "Suppressed units: 5" in captured
    assert "Coverage:" in captured
    assert "Independent privacy verification: passed" in captured
    assert "Coverage is not a maximum claim." in captured
    cert_files = list(tmp_path.glob("*_coverage_certificate.json"))
    assert len(cert_files) == 1
    assert f"Coverage Certificate: {cert_files[0]}" in captured
    # Client summary must not dump suppressed identity or failure detail.
    assert "SectorX" not in captured
    assert "SectorZ" not in captured
    assert "suppression_set" not in captured


def test_cli_empty_release_set_denial(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    df = build_safe_coverage_getnet_shaped_df()
    df = df[df["sector"].isin(["SectorX", "SectorZ"])].reset_index(drop=True)
    args = _msc_cli_args(
        tmp_path,
        df=df,
        output_name="cli_empty.xlsx",
        min_weight=1.0,
        max_weight=1.01,
    )
    code = benchmark.run_share_analysis(
        args, logging.getLogger("test_cli_msc_empty")
    )
    captured = capsys.readouterr().out

    assert code == benchmark.EXIT_STRICT_NON_COMPLIANT
    assert "PUBLICATION WITHHELD" in captured
    assert CONTROL3_SAFE_COVERAGE_EMPTY in captured
    assert "SHARE ANALYSIS BLOCKED" in captured
    assert "Candidate units:" not in captured
    assert "maximum claim" not in captured
    assert not list(tmp_path.glob("*_coverage_certificate.json"))


def test_cli_no_suppressed_marker_in_captured_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    df = _seed_suppressed_marker(build_safe_coverage_getnet_shaped_df())
    args = _msc_cli_args(tmp_path, df=df, output_name="cli_marker.xlsx")
    code = benchmark.run_share_analysis(
        args, logging.getLogger("test_cli_msc_marker")
    )
    captured = capsys.readouterr()
    combined = captured.out + captured.err

    assert code == benchmark.EXIT_OK
    assert SUPPRESSED_MARKER not in combined
