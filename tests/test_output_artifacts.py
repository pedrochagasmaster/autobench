from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from openpyxl import load_workbook

from benchmark import run_share_analysis
from core.report_generator import ReportGenerator
from utils.config_manager import ConfigManager


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


def test_output_format_both_writes_analysis_and_publication(tmp_path: Path) -> None:
    df = pd.DataFrame(
        {
            "issuer_name": ["Target", "P1", "P2", "P3", "P4", "P5", "P6"],
            "card_type": ["A", "A", "A", "A", "A", "A", "A"],
            "txn_cnt": [100, 200, 180, 160, 140, 120, 110],
        }
    )
    output = tmp_path / "share.xlsx"

    result = run_share_analysis(_share_args(output, df), __import__("logging").getLogger("test_output"))

    assert result == 0
    assert output.exists()
    assert (tmp_path / "share_publication.xlsx").exists()


def test_debug_workbook_contains_diagnostic_sheets(tmp_path: Path) -> None:
    df = pd.DataFrame(
        {
            "issuer_name": ["Target", "P1", "P2", "P3", "P4", "P5", "P6"],
            "card_type": ["A", "A", "A", "A", "A", "A", "A"],
            "txn_cnt": [100, 200, 180, 160, 140, 120, 110],
        }
    )
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


def test_report_generator_writes_extended_diagnostic_sheets(tmp_path: Path) -> None:
    output = tmp_path / "diagnostics.xlsx"
    generator = ReportGenerator(ConfigManager())
    results = {
        "card_type": pd.DataFrame(
            {
                "Category": ["A"],
                "Balanced Peer Average (%)": [50.0],
                "Target Rate (%)": [45.0],
            }
        )
    }
    metadata = {
        "weights_df": pd.DataFrame({"Peer": ["P1"], "Multiplier": [1.0]}),
        "method_breakdown_df": pd.DataFrame({"Dimension": ["card_type"], "Method": ["Global-LP"]}),
        "privacy_validation_df": pd.DataFrame({"Dimension": ["card_type"], "Compliant": ["Yes"]}),
        "structural_summary_df": pd.DataFrame({"Dimension": ["card_type"], "infeasible_categories": [0]}),
        "structural_detail_df": pd.DataFrame({"dimension": ["card_type"], "category": ["A"], "margin_over_cap_pp": [0.0]}),
        "rank_changes_df": pd.DataFrame({"Peer": ["P1"], "Adjusted_Rank": [1]}),
        "subset_search_df": pd.DataFrame({"selected_dimensions": [["card_type"]], "success": [True]}),
        "secondary_results_df": pd.DataFrame({"Dimension": ["card_type"], "Category": ["A"], "secondary_metric": [12.0]}),
    }

    generator.generate_report(results, str(output), format="excel", analysis_type="share", metadata=metadata)

    workbook = load_workbook(output, read_only=True)
    try:
        expected = {
            "Peer Weights",
            "Weight Methods",
            "Privacy Validation",
            "Structural Summary",
            "Structural Detail",
            "Rank Changes",
            "Subset Search",
            "Secondary Metrics",
        }
        assert expected.issubset(set(workbook.sheetnames))
    finally:
        workbook.close()
