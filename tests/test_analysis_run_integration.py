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
from openpyxl import load_workbook

from core.analysis_run import execute_rate_run, execute_share_run
from core.contracts import AnalysisRunRequest

FIXTURE = Path(__file__).parent / "fixtures" / "gate_demo.csv"
SHARE_DIMENSIONS = ["card_type", "channel"]


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

    expected = {out.name, f"{out.stem}_audit.log"}
    assert {p.name for p in tmp_path.iterdir()} == expected


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
