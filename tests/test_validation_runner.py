"""Direct tests for core/validation_runner.py."""

from __future__ import annotations

import pandas as pd

from core.data_loader import DataLoader, ValidationSeverity
from core.validation_runner import run_input_validation
from utils.config_manager import ConfigManager


def test_insufficient_peers_aborts(insufficient_peer_csv) -> None:
    df = pd.read_csv(insufficient_peer_csv)
    config = ConfigManager()
    loader = DataLoader(config)

    issues, should_abort = run_input_validation(
        df=df,
        config=config,
        data_loader=loader,
        analysis_type="share",
        metric_col="txn_cnt",
        entity_col="issuer_name",
        dimensions=["card_type", "channel"],
        target_entity="Target",
    )

    assert issues is not None
    assert should_abort is True
    assert any(issue.severity == ValidationSeverity.ERROR for issue in issues)


def test_warnings_only_do_not_abort(mock_benchmark_csv) -> None:
    df = pd.read_csv(mock_benchmark_csv)
    config = ConfigManager()
    loader = DataLoader(config)

    issues, should_abort = run_input_validation(
        df=df,
        config=config,
        data_loader=loader,
        analysis_type="share",
        metric_col="txn_cnt",
        entity_col="issuer_name",
        dimensions=["card_type", "channel"],
        target_entity="Target",
    )

    assert issues is not None
    assert should_abort is False


def test_disabled_input_validation_marks_data_quality_unchecked(mock_benchmark_csv) -> None:
    df = pd.read_csv(mock_benchmark_csv)
    config = ConfigManager()
    config.config["input"]["validate_input"] = False
    loader = DataLoader(config)

    result = run_input_validation(
        df=df,
        config=config,
        data_loader=loader,
        analysis_type="share",
        metric_col="txn_cnt",
        entity_col="issuer_name",
        dimensions=["card_type", "channel"],
        target_entity="Target",
    )

    assert result.checked is False
    assert result.publishable is False
    assert tuple(result) == (None, False)
