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
