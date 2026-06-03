"""Golden output regression tests for business-visible report invariants."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "gate_demo.csv"
PY = sys.executable


def _run_benchmark(args: list[str], cwd: Path, output_xlsx: Path) -> subprocess.CompletedProcess[str]:
    cmd = [
        PY,
        str(ROOT / "benchmark.py"),
        *args,
        "--csv",
        str(FIXTURE),
        "--entity",
        "Target",
        "--dimensions",
        "card_type",
        "channel",
        "--time-col",
        "year_month",
        "--preset",
        "balanced_default",
        "--no-validate-input",
        "--output",
        str(output_xlsx),
    ]
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)


def _assert_core_workbook_invariants(path: Path) -> None:
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        assert "Summary" in wb.sheetnames
        assert "Weight Methods" in wb.sheetnames
        assert "Rank Changes" in wb.sheetnames
        reserved = {
            "Summary",
            "Metadata",
            "Weight Methods",
            "Rank Changes",
            "Peer Weights",
            "Privacy Validation",
            "Preset Comparison",
            "Impact Summary",
            "Impact Detail",
            "Subset Search",
            "Structural Summary",
            "Structural Detail",
        }
        dim_sheets = [name for name in wb.sheetnames if name not in reserved]
        assert dim_sheets, "expected at least one dimension sheet"
    finally:
        wb.close()


@pytest.mark.parametrize(
    "mode,extra_args,csv_suffix",
    [
        ("share", ["share", "--metric", "txn_cnt"], ""),
        (
            "rate",
            [
                "rate",
                "--total-col",
                "total",
                "--approved-col",
                "approved",
                "--fraud-col",
                "fraud",
                "--privacy-basis",
                "clearing_spend",
            ],
            "_balanced.csv",
        ),
    ],
)
def test_golden_cli_outputs(tmp_path: Path, mode: str, extra_args: list[str], csv_suffix: str) -> None:
    output_xlsx = tmp_path / f"golden_{mode}.xlsx"
    result = _run_benchmark(extra_args, tmp_path, output_xlsx)
    assert result.returncode == 0, result.stderr or result.stdout
    assert output_xlsx.exists()
    _assert_core_workbook_invariants(output_xlsx)

    if csv_suffix:
        csv_path = tmp_path / f"golden_{mode}{csv_suffix}"
        export_cmd = [
            PY,
            str(ROOT / "benchmark.py"),
            *extra_args,
            "--csv",
            str(FIXTURE),
            "--entity",
            "Target",
            "--dimensions",
            "card_type",
            "channel",
            "--time-col",
            "year_month",
            "--preset",
            "balanced_default",
            "--no-validate-input",
            "--output",
            str(tmp_path / f"golden_{mode}_csv.xlsx"),
            "--export-balanced-csv",
        ]
        export_result = subprocess.run(export_cmd, cwd=tmp_path, capture_output=True, text=True, check=False)
        assert export_result.returncode == 0, export_result.stderr or export_result.stdout
        exported = list(tmp_path.glob(f"*_balanced.csv"))
        assert exported, "expected balanced CSV export"
        csv_df = pd.read_csv(exported[0])
        assert {"Dimension", "Category"}.issubset(csv_df.columns)


def test_golden_peer_only_share(tmp_path: Path) -> None:
    output_xlsx = tmp_path / "golden_peer_only.xlsx"
    cmd = [
        PY,
        str(ROOT / "benchmark.py"),
        "share",
        "--csv",
        str(FIXTURE),
        "--metric",
        "txn_cnt",
        "--dimensions",
        "card_type",
        "channel",
        "--time-col",
        "year_month",
        "--preset",
        "balanced_default",
        "--no-validate-input",
        "--output",
        str(output_xlsx),
    ]
    result = subprocess.run(cmd, cwd=tmp_path, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr or result.stdout
    _assert_core_workbook_invariants(output_xlsx)
