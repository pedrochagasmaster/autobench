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


def _share_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "issuer_name": ["Target", "P1", "P2", "P3", "P4", "P5", "P6"],
            "card_type": ["A", "A", "A", "A", "A", "A", "A"],
            "txn_cnt": [100, 200, 180, 160, 140, 120, 110],
        }
    )


def test_output_format_both_writes_analysis_and_publication(tmp_path: Path) -> None:
    output = tmp_path / "share.xlsx"

    result = run_share_analysis(_share_args(output, _share_df()), __import__("logging").getLogger("test_output"))

    assert result == 0
    assert output.exists()
    assert (tmp_path / "share_publication.xlsx").exists()


def test_debug_workbook_contains_diagnostic_sheets(tmp_path: Path) -> None:
    output = tmp_path / "share.xlsx"

    result = run_share_analysis(
        _share_args(output, _share_df(), output_format="analysis"),
        __import__("logging").getLogger("test_sheets"),
    )

    assert result == 0
    workbook = load_workbook(output, read_only=True)
    try:
        assert "Peer Weights" in workbook.sheetnames
        assert "Weight Methods" in workbook.sheetnames
        assert "Privacy Validation" in workbook.sheetnames
        assert "Rank Changes" in workbook.sheetnames
    finally:
        workbook.close()


def test_output_format_publication_only_writes_publication_workbook(tmp_path: Path) -> None:
    """§2.6: --output-format publication must actually create the publication workbook
    (`generate_publication_workbook` was dead code on `main`).
    """
    output = tmp_path / "share.xlsx"

    result = run_share_analysis(
        _share_args(output, _share_df(), output_format="publication"),
        __import__("logging").getLogger("test_pub_only"),
    )

    assert result == 0
    assert (tmp_path / "share_publication.xlsx").exists()


def test_metric_sheet_names_use_plain_dimension_names(tmp_path: Path) -> None:
    """Q3: sheets are named after the dimension (`card_type`) not `Metric_1_card_type`,
    so the workbook matches pre-refactor archives and the CSV validator's Dimension
    column join.
    """
    output = tmp_path / "share.xlsx"

    result = run_share_analysis(
        _share_args(output, _share_df(), output_format="analysis"),
        __import__("logging").getLogger("test_sheet_names"),
    )

    assert result == 0
    workbook = load_workbook(output, read_only=True)
    try:
        assert "card_type" in workbook.sheetnames
        assert not any(name.startswith("Metric_") for name in workbook.sheetnames)
    finally:
        workbook.close()


def test_publication_workbook_includes_compliance_evidence_sheets(tmp_path: Path) -> None:
    """Q9: the publication workbook contains stakeholder-facing privacy evidence
    (Peer Weights, Privacy Validation, Rank Changes) but excludes solver-internal
    diagnostics (Weight Methods, Subset Search, Structural Diagnostics).
    """
    output = tmp_path / "share.xlsx"

    result = run_share_analysis(
        _share_args(output, _share_df(), output_format="both"),
        __import__("logging").getLogger("test_pub_scope"),
    )

    assert result == 0
    pub_path = tmp_path / "share_publication.xlsx"
    assert pub_path.exists()
    workbook = load_workbook(pub_path, read_only=True)
    try:
        sheetnames = workbook.sheetnames
        # Allow-list (Q9): stakeholder evidence belongs in publication.
        assert "Peer Weights" in sheetnames
        assert "Privacy Validation" in sheetnames
        # Solver internals stay analysis-only.
        assert "Weight Methods" not in sheetnames
        assert "Subset Search" not in sheetnames
        assert "Structural Detail" not in sheetnames
        assert "Data Quality" not in sheetnames
    finally:
        workbook.close()
