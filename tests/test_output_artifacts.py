from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
from openpyxl import load_workbook

from benchmark import run_share_analysis
from core.analysis_run import write_outputs as analysis_write_outputs
from core.output_artifacts import OutputArtifactWriter


def test_core_modules_import_without_benchmark() -> None:
    import importlib
    import sys

    saved = {name: sys.modules.pop(name) for name in list(sys.modules) if name in {"benchmark", "core.analysis_run", "core.output_artifacts"}}
    try:
        importlib.import_module("core.analysis_run")
        importlib.import_module("core.output_artifacts")
        assert "benchmark" not in sys.modules
    finally:
        sys.modules.update(saved)


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


def _gate_demo_df() -> pd.DataFrame:
    return pd.read_csv(Path("tests/fixtures/gate_demo.csv"))


def test_output_format_both_writes_analysis_and_publication(tmp_path: Path) -> None:
    output = tmp_path / "share.xlsx"

    result = run_share_analysis(_share_args(output, _share_df()), __import__("logging").getLogger("test_output"))

    assert result == 0
    assert output.exists()
    assert (tmp_path / "share_publication.xlsx").exists()


def test_output_writer_receives_report_model(tmp_path: Path) -> None:
    output = tmp_path / "share.xlsx"
    writer_cls = MagicMock(side_effect=OutputArtifactWriter)

    with patch.dict(
        analysis_write_outputs.__globals__,
        {"OutputArtifactWriter": writer_cls},
    ):
        result = run_share_analysis(
            _share_args(output, _share_df(), output_format="analysis"),
            __import__("logging").getLogger("test_report_model_boundary"),
        )

    assert result == 0
    assert writer_cls.call_args.args[0].__class__.__name__ == "ReportModel"


def test_no_validate_input_cannot_emit_fully_compliant_audit(tmp_path: Path) -> None:
    output = tmp_path / "share.xlsx"

    result = run_share_analysis(
        _share_args(output, _share_df(), output_format="analysis"),
        __import__("logging").getLogger("test_no_validate_verdict"),
    )

    assert result == 0
    audit_log = tmp_path / "share_audit.log"
    assert audit_log.exists()
    audit_text = audit_log.read_text(encoding="utf-8")
    assert "compliance_verdict: not_publishable_input" in audit_text
    assert "data_quality_checked: False" in audit_text


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


def test_analysis_workbook_keeps_weight_methods_when_privacy_sheet_disabled(tmp_path: Path) -> None:
    output = tmp_path / "share.xlsx"
    config_path = tmp_path / "no_privacy_sheet.yaml"
    config_path.write_text(
        '\n'.join(
            [
                'version: "3.0"',
                'compliance_posture: strict',
                'output:',
                '  include_debug_sheets: false',
                '  include_privacy_validation: false',
            ]
        ),
        encoding="utf-8",
    )
    args = _share_args(output, _gate_demo_df(), output_format="analysis")
    args.config = str(config_path)
    args.debug = False
    args.dimensions = ["card_type", "channel"]
    args.time_col = "year_month"

    result = run_share_analysis(args, __import__("logging").getLogger("test_privacy_sheet_disabled"))

    assert result == 0
    workbook = load_workbook(output, read_only=True)
    try:
        assert "Weight Methods" in workbook.sheetnames
        assert "Privacy Validation" not in workbook.sheetnames
    finally:
        workbook.close()


def test_subset_search_diagnostics_with_dimension_lists_write_to_workbook(tmp_path: Path) -> None:
    output = tmp_path / "share.xlsx"
    config_path = tmp_path / "subset_search.yaml"
    config_path.write_text(
        '\n'.join(
            [
                'version: "3.0"',
                'compliance_posture: strict',
                'optimization:',
                '  bounds:',
                '    max_weight: 1.0',
                '    min_weight: 0.9',
                '  linear_programming:',
                '    tolerance: 50.0',
                '  subset_search:',
                '    enabled: false',
                'output:',
                '  include_debug_sheets: false',
                '  include_privacy_validation: false',
            ]
        ),
        encoding="utf-8",
    )
    args = _share_args(output, _gate_demo_df(), output_format="analysis")
    args.config = str(config_path)
    args.debug = False
    args.dimensions = ["card_type", "channel"]
    args.time_col = "year_month"

    result = run_share_analysis(args, __import__("logging").getLogger("test_subset_lists"))

    assert result == 0
    workbook = load_workbook(output, read_only=True)
    try:
        assert "Subset Search" in workbook.sheetnames
        headers = [cell.value for cell in next(workbook["Subset Search"].iter_rows(max_row=1))]
        assert "Dimensions" in headers
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
