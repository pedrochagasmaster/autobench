"""Tests for JSON sidecar output (output.format: json)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from core.analysis_run import execute_rate_run, execute_share_run
from core.contracts import AnalysisRunRequest
from core.report_generator import ReportGenerator

FIXTURE = Path(__file__).parent / "fixtures" / "gate_demo.csv"
SHARE_DIMENSIONS = ["card_type", "channel"]


def _share_request(tmp_path: Path, **overrides: object) -> AnalysisRunRequest:
    out = tmp_path / "share_it.xlsx"
    kwargs: dict = {
        "csv": str(FIXTURE),
        "entity": "Target",
        "metric": "txn_cnt",
        "dimensions": SHARE_DIMENSIONS,
        "time_col": "year_month",
        "preset": "balanced_default",
        "compliance_posture": "strict",
        "output": str(out),
    }
    kwargs.update(overrides)
    return AnalysisRunRequest(**kwargs)


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
    }
    kwargs.update(overrides)
    return AnalysisRunRequest(**kwargs)


def test_share_run_writes_json_sidecar(tmp_path: Path) -> None:
    request = _share_request(tmp_path, report_format="json")
    artifacts = execute_share_run(request, logging.getLogger("test"))

    out = Path(request.output)
    json_path = out.with_suffix(".json")
    assert out.exists()
    assert json_path.exists()
    assert artifacts.json_output == str(json_path)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["analysis_type"] == "share"
    assert "metadata" in payload
    assert "results" in payload
    assert payload["run_status"] is not None
    assert payload["compliance_verdict"] is not None
    assert payload["publication_safe"] is False
    assert set(payload["results"].keys()) == set(SHARE_DIMENSIONS)


def test_rate_run_flattens_json_result_keys(tmp_path: Path) -> None:
    request = _rate_request(tmp_path, report_format="json")
    artifacts = execute_rate_run(request, logging.getLogger("test"))

    json_path = Path(artifacts.json_output)
    assert json_path.exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["analysis_type"] == "rate"
    result_keys = set(payload["results"].keys())
    for rate_type in ("approval", "fraud"):
        for dim in SHARE_DIMENSIONS:
            assert f"{rate_type}_{dim}" in result_keys


def test_default_run_writes_no_json_sidecar(tmp_path: Path) -> None:
    request = _share_request(tmp_path)
    artifacts = execute_share_run(request, logging.getLogger("test"))

    json_path = Path(request.output).with_suffix(".json")
    assert not json_path.exists()
    assert artifacts.json_output is None


def test_json_safe_metadata_serializes_dataframes() -> None:
    generator = ReportGenerator(config=None)
    safe = generator._json_safe_metadata({"x_df": pd.DataFrame({"a": [1, 2]})})
    assert isinstance(safe["x_df"], list)
    assert safe["x_df"] == [{"a": 1}, {"a": 2}]
    assert not isinstance(safe["x_df"], str)
