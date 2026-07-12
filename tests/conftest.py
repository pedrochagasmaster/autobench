"""Shared pytest fixtures for benchmark tests."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from tests.fixtures.mock_benchmark_data import (
    build_mock_benchmark_df,
    write_insufficient_peer_csv,
    write_mock_benchmark_csv,
)

_TELEMETRY_TESTS_DIR = Path(__file__).resolve().parent / "telemetry"


def is_telemetry_test_path(path: Path) -> bool:
    """Return True when ``path`` lives under ``tests/telemetry``."""
    try:
        Path(path).resolve().relative_to(_TELEMETRY_TESTS_DIR)
        return True
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def _opt_out_telemetry_outside_telemetry_tests(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    """Prevent legacy/full-suite tests from writing telemetry under /ads_storage.

    Focused tests under ``tests/telemetry`` keep the default enabled path so
    instrumentation and helper suites can exercise real writers.
    """
    if not is_telemetry_test_path(Path(str(request.path))):
        monkeypatch.setenv("AUTOBENCH_TELEMETRY", "0")


@pytest.fixture
def mock_benchmark_df():
    return build_mock_benchmark_df()


@pytest.fixture
def mock_benchmark_csv(tmp_path: Path):
    path = tmp_path / "mock.csv"
    write_mock_benchmark_csv(path)
    return path


@pytest.fixture
def insufficient_peer_csv(tmp_path: Path):
    path = tmp_path / "insufficient.csv"
    write_insufficient_peer_csv(path)
    return path


def make_run_args(**overrides):
    """Build a namespace matching common CLI run arguments."""
    defaults = {
        "csv": "data/mock.csv",
        "entity": "Target",
        "entity_col": "issuer_name",
        "preset": None,
        "config": None,
        "output": None,
        "time_col": "year_month",
        "log_level": "INFO",
        "validate_input": True,
        "analyze_impact": False,
        "analyze_distortion": False,
        "compare_presets": False,
        "include_calculated": False,
        "output_format": "analysis",
        "metric": "txn_cnt",
        "secondary_metrics": None,
        "auto": False,
        "dimensions": ["card_type", "channel"],
        "debug": False,
        "export_balanced_csv": False,
        "per_dimension_weights": False,
        "total_col": "total",
        "approved_col": "approved",
        "fraud_col": "fraud",
        "fraud_in_bps": True,
        "compliance_posture": None,
        "acknowledge_accuracy_first": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)
