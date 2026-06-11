"""These tests pin the documented public API (README → Programmatic use).

Breaking them requires updating the README, the example, and consumers.
"""

from __future__ import annotations

import dataclasses
import inspect

from core.analysis_run import execute_rate_run, execute_share_run
from core.contracts import AnalysisArtifacts, AnalysisRunRequest

# Fields used by examples/run_from_python.py and documented in README.
_EXAMPLE_REQUEST_FIELDS = {
    "csv",
    "entity",
    "metric",
    "dimensions",
    "time_col",
    "preset",
    "compliance_posture",
    "output",
}

# Minimum return-contract fields documented for consumers.
_ARTIFACTS_FIELDS = {
    "analysis_output_file",
    "csv_output",
    "report_paths",
}


def test_public_api_imports() -> None:
    from core.analysis_run import execute_share_run, execute_rate_run  # noqa: F401
    from core.contracts import AnalysisArtifacts, AnalysisRunRequest  # noqa: F401


def test_execute_share_run_signature() -> None:
    sig = inspect.signature(execute_share_run)
    assert list(sig.parameters) == ["request", "logger"]


def test_execute_rate_run_signature() -> None:
    sig = inspect.signature(execute_rate_run)
    assert list(sig.parameters) == ["request", "logger"]


def test_analysis_run_request_has_documented_fields() -> None:
    names = {f.name for f in dataclasses.fields(AnalysisRunRequest)}
    missing = _EXAMPLE_REQUEST_FIELDS - names
    assert not missing, f"AnalysisRunRequest missing documented fields: {sorted(missing)}"


def test_analysis_artifacts_has_documented_fields() -> None:
    names = {f.name for f in dataclasses.fields(AnalysisArtifacts)}
    missing = _ARTIFACTS_FIELDS - names
    assert not missing, f"AnalysisArtifacts missing documented fields: {sorted(missing)}"
