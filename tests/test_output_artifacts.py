from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from openpyxl import load_workbook

from benchmark import run_rate_analysis, run_share_analysis
from tests.fixtures.mock_benchmark_data import build_mock_benchmark_df


def _share_args(output: Path, df: pd.DataFrame, output_format: str = "both") -> SimpleNamespace:
    return SimpleNamespace(
        csv="",
        df=df,
        metric="txn_cnt",
        secondary_metrics=None,
        entity="Target",
        entity_col="issuer_name",
        output=str(output),
        dimensions=["card_type", "channel"],
        auto=False,
        time_col="year_month",
        config=None,
        preset=None,
        debug=True,
        log_level="INFO",
        per_dimension_weights=False,
        export_balanced_csv=False,
        validate_input=False,
        compare_presets=False,
        analyze_distortion=False,
        output_format=output_format,
        include_calculated=False,
        auto_subset_search=None,
        subset_search_max_tests=None,
        trigger_subset_on_slack=None,
        max_cap_slack=None,
        compliance_posture=None,
        acknowledge_accuracy_first=False,
    )


def _rate_args(output: Path, df: pd.DataFrame, output_format: str = "both") -> SimpleNamespace:
    return SimpleNamespace(
        csv="",
        df=df,
        total_col="total",
        approved_col="approved",
        fraud_col="fraud",
        secondary_metrics=None,
        entity="Target",
        entity_col="issuer_name",
        output=str(output),
        dimensions=["card_type", "channel"],
        auto=False,
        time_col="year_month",
        config=None,
        preset=None,
        debug=True,
        log_level="INFO",
        per_dimension_weights=False,
        export_balanced_csv=False,
        validate_input=False,
        compare_presets=False,
        analyze_distortion=False,
        output_format=output_format,
        include_calculated=False,
        fraud_in_bps=True,
        auto_subset_search=None,
        subset_search_max_tests=None,
        trigger_subset_on_slack=None,
        max_cap_slack=None,
        compliance_posture=None,
        acknowledge_accuracy_first=False,
    )


def test_output_format_both_writes_analysis_and_publication(tmp_path: Path) -> None:
    df = build_mock_benchmark_df()
    output = tmp_path / "share.xlsx"

    result = run_share_analysis(_share_args(output, df), __import__("logging").getLogger("test_output"))

    assert result == 0
    assert output.exists()
    assert (tmp_path / "share_publication.xlsx").exists()


def test_debug_workbook_contains_diagnostic_sheets(tmp_path: Path) -> None:
    df = build_mock_benchmark_df()
    output = tmp_path / "share.xlsx"

    result = run_share_analysis(_share_args(output, df, output_format="analysis"), __import__("logging").getLogger("test_sheets"))

    assert result == 0
    workbook = load_workbook(output, read_only=True)
    try:
        assert "Peer Weights" in workbook.sheetnames
        assert "Weight Methods" in workbook.sheetnames
        assert "Privacy Validation" in workbook.sheetnames
    finally:
        workbook.close()


def test_publication_only_writes_publication_workbook(tmp_path: Path) -> None:
    df = build_mock_benchmark_df()
    output = tmp_path / "rate.xlsx"

    result = run_rate_analysis(_rate_args(output, df, output_format="publication"), __import__("logging").getLogger("test_pub_only"))

    assert result == 0
    assert not output.exists()
    assert (tmp_path / "rate_publication.xlsx").exists()
