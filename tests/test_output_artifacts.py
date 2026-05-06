import logging
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from openpyxl import load_workbook

from benchmark import run_share_analysis


def _share_args(output: Path, df: pd.DataFrame, output_format: str = "both") -> SimpleNamespace:
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


def _simple_share_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "issuer_name": ["Target", "P1", "P2", "P3", "P4", "P5", "P6"],
            "card_type": ["A", "A", "A", "A", "A", "A", "A"],
            "txn_cnt": [100, 200, 180, 160, 140, 120, 110],
        }
    )


def test_output_format_both_writes_analysis_and_publication(tmp_path: Path) -> None:
    output = tmp_path / "share.xlsx"

    result = run_share_analysis(_share_args(output, _simple_share_df()), logging.getLogger("test_output"))

    assert result == 0
    assert output.exists()
    assert (tmp_path / "share_publication.xlsx").exists()


def test_output_format_publication_only_writes_publication_workbook(tmp_path: Path) -> None:
    output = tmp_path / "share.xlsx"

    result = run_share_analysis(
        _share_args(output, _simple_share_df(), output_format="publication"),
        logging.getLogger("test_publication_only"),
    )

    assert result == 0
    assert not output.exists()
    publication = tmp_path / "share_publication.xlsx"
    assert publication.exists()
    workbook = load_workbook(publication, read_only=True)
    try:
        assert "Executive Summary" in workbook.sheetnames
    finally:
        workbook.close()


def test_debug_workbook_contains_diagnostic_sheets(tmp_path: Path) -> None:
    output = tmp_path / "share.xlsx"

    result = run_share_analysis(
        _share_args(output, _simple_share_df(), output_format="analysis"),
        logging.getLogger("test_sheets"),
    )

    assert result == 0
    workbook = load_workbook(output, read_only=True)
    try:
        assert "Peer Weights" in workbook.sheetnames
        assert "Weight Methods" in workbook.sheetnames
        assert "Privacy Validation" in workbook.sheetnames
    finally:
        workbook.close()
