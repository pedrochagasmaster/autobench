"""These tests pin the documented public API (README → Programmatic use).

Breaking them requires updating the README, the example, and consumers.
"""

from __future__ import annotations

import dataclasses
import inspect
from collections.abc import Mapping

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
    "privacy_output_decision",
}


def test_public_api_imports() -> None:
    from core import (  # noqa: F401
        CoverageCertificate,
        PrivacyOutputDecision,
        PrivacyReleaseMode,
        SafeCoverageResult,
    )
    from core.analysis_run import execute_share_run, execute_rate_run  # noqa: F401
    from core.contracts import AnalysisArtifacts, AnalysisRunRequest  # noqa: F401


def test_privacy_release_mode_public_values() -> None:
    from core import PrivacyReleaseMode

    assert PrivacyReleaseMode.COMPLETE_OUTPUT.value == "complete-output"
    assert PrivacyReleaseMode.MAXIMIZE_SAFE_COVERAGE.value == "maximize-safe-coverage"


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


# --- Privacy-rule surface consumed in-process by governed pipelines ---------
# The Getnet dashboard feed binds these two directly instead of shelling out,
# so they are part of the compatible surface even though they sit outside the
# share/rate run entry points.


def test_privacy_validator_rule_config_is_importable() -> None:
    from core.privacy_validator import PrivacyValidator

    sig = inspect.signature(PrivacyValidator.get_rule_config)
    assert list(sig.parameters) == ["rule_name"]


def test_privacy_validator_rule_config_returns_mapping() -> None:
    from core.privacy_validator import PrivacyValidator

    config = PrivacyValidator.get_rule_config("5/25")
    assert isinstance(config, Mapping)


def test_data_loader_normalize_column_name_is_importable() -> None:
    from core.data_loader import DataLoader

    sig = inspect.signature(DataLoader.normalize_column_name)
    assert list(sig.parameters) == ["column_name"]
    assert DataLoader.normalize_column_name(" Merchant Name ") == "merchant_name"
