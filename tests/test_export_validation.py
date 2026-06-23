"""Tests for automatic balanced CSV export validation."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from core.analysis_run import _validate_balanced_export, execute_rate_run, execute_share_run
from core.contracts import AnalysisRunRequest

FIXTURE = Path(__file__).parent / "fixtures" / "gate_demo.csv"
SHARE_DIMENSIONS = ["card_type", "channel"]


def _rate_request(tmp_path: Path, **overrides: object) -> AnalysisRunRequest:
    out = tmp_path / "rate_it.xlsx"
    kwargs: dict = {
        "mode": "rate",
        "csv": str(FIXTURE),
        "entity": "Target",
        "total_col": "total",
        "approved_col": "approved",
        "fraud_col": "fraud",
        "dimensions": SHARE_DIMENSIONS,
        "time_col": "year_month",
        "preset": "balanced_default",
        "compliance_posture": "strict",
        "control3_overrides": {"privacy_basis": "clearing_spend"},
        "output": str(out),
        "export_balanced_csv": True,
    }
    kwargs.update(overrides)
    return AnalysisRunRequest(**kwargs)


def test_rate_export_validation_passes(tmp_path: Path) -> None:
    request = _rate_request(tmp_path)
    artifacts = execute_rate_run(request, logging.getLogger("test"))

    export_validation = artifacts.metadata["export_validation"]
    assert export_validation["checked"] is True
    assert export_validation["passed"] is True
    assert export_validation["mode"] == "full"


def test_share_export_validation_schema_passes(tmp_path: Path) -> None:
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
        export_balanced_csv=True,
    )
    artifacts = execute_share_run(request, logging.getLogger("test"))

    export_validation = artifacts.metadata["export_validation"]
    assert export_validation["checked"] is True
    assert export_validation["passed"] is True
    assert export_validation["mode"] == "schema"


def test_tampered_csv_fails_validation(tmp_path: Path) -> None:
    request = _rate_request(tmp_path)
    artifacts = execute_rate_run(request, logging.getLogger("test"))
    csv_path = Path(artifacts.csv_output)
    assert csv_path.exists()

    df = pd.read_csv(csv_path)
    numeric_cols = [c for c in df.columns if c not in {"Dimension", "Category", "year_month"}]
    assert numeric_cols
    df.loc[0, numeric_cols[0]] = float(df.loc[0, numeric_cols[0]]) * 10
    df.to_csv(csv_path, index=False)

    workbook_path = request.output
    assert workbook_path is not None
    result = _validate_balanced_export(
        analysis_output_file=workbook_path,
        csv_output=str(csv_path),
        is_rate=True,
        compliance_posture="best_effort",
        logger=logging.getLogger("test"),
    )
    assert result["checked"] is True
    assert result["passed"] is False
    assert result["mode"] == "full"


def test_no_validate_export_skips_validation(tmp_path: Path) -> None:
    request = _rate_request(tmp_path, validate_export=False)
    artifacts = execute_rate_run(request, logging.getLogger("test"))

    export_validation = (artifacts.metadata or {}).get("export_validation")
    assert export_validation is None or export_validation.get("checked") is False


def test_lean_mode_skips_export_validation(tmp_path: Path) -> None:
    request = _rate_request(tmp_path, lean=True)
    artifacts = execute_rate_run(request, logging.getLogger("test"))

    export_validation = (artifacts.metadata or {}).get("export_validation")
    assert export_validation is None or export_validation.get("checked") is False
