from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import logging
import threading

import pandas as pd
import pytest

from core.analysis_run import apply_prepared_dataset, build_run_config
from core.contracts import AnalysisRunRequest, PreparedDataset
from tui_app import BenchmarkApp, LogHandler, write_log_message
from utils.config_manager import ConfigManager, ResolvedConfig
from utils.config_overrides import ADVANCED_FIELD_SPECS, ConfigOverrideBuilder
from textual.widgets import Log


def test_analysis_run_request_preserves_preloaded_dataframe() -> None:
    df = pd.DataFrame({"issuer_name": ["Target", "P1"], "metric": [1, 2]})
    request = AnalysisRunRequest(mode="share", csv="", metric="metric")
    request.df = df

    namespace = request.to_namespace()

    assert namespace.df is df


def test_analysis_run_request_from_namespace_copies_dataframe() -> None:
    df = pd.DataFrame({"issuer_name": ["Target"], "metric": [1]})
    namespace = SimpleNamespace(mode="share", csv="", df=df, metric="metric", ignored_flag=True)

    request = AnalysisRunRequest.from_namespace("share", namespace)

    assert request.df is df
    assert not hasattr(request, "ignored_flag")


def test_build_run_config_accepts_request_namespace_after_dataframe_fix() -> None:
    request = AnalysisRunRequest(mode="share", csv="", df=object(), metric="metric", validate_input=False)

    config = build_run_config(request.to_namespace())

    assert config.get("input", "validate_input") is False


def test_prepared_dataset_carries_validation_issues() -> None:
    issues = [SimpleNamespace(severity="WARNING", message="sample")]
    prepared = PreparedDataset(
        df=pd.DataFrame({"issuer_name": ["A"], "metric": [1]}),
        entity_col="issuer_name",
        validation_issues=issues,
    )
    request = AnalysisRunRequest(mode="share", csv="data.csv", metric="metric", prepared_dataset=prepared)

    assert request.prepared_dataset.validation_issues is issues


def test_config_manager_resolve_returns_typed_sections() -> None:
    config = ConfigManager(preset="balanced_default")
    resolved = config.resolve()

    assert isinstance(resolved, ResolvedConfig)
    assert resolved.bounds.max_weight == 10.0
    assert resolved.linear_programming.tolerance == 2.0
    assert resolved.subset_search.max_attempts == 200
    assert resolved.compliance_posture == "strict"


def test_apply_prepared_dataset_skips_reload() -> None:
    df = pd.DataFrame({"issuer_name": ["Target"], "metric": [1]})
    loader = MagicMock()
    prepared = PreparedDataset(
        df=df,
        entity_col="issuer_name",
        time_col="year_month",
        data_loader=loader,
        validation_issues=[],
    )
    request = AnalysisRunRequest(mode="share", csv="data.csv", metric="metric", prepared_dataset=prepared)
    config = ConfigManager()

    _, out_df, entity_col, time_col, used = apply_prepared_dataset(
        request,
        config,
        __import__("logging").getLogger("test"),
        preferred_entity_col="issuer_name",
    )

    assert used is True
    assert out_df is df
    assert entity_col == "issuer_name"
    assert time_col == "year_month"


def test_benchmark_app_advanced_field_map_covers_load_and_save_keys() -> None:
    widget_ids = {spec["widget_id"] for spec in BenchmarkApp.ADVANCED_FIELD_MAP}
    assert "adv_lp_tolerance" in widget_ids
    assert "adv_subset_max_attempts" in widget_ids

    max_attempts_spec = next(
        spec for spec in BenchmarkApp.ADVANCED_FIELD_MAP if spec["widget_id"] == "adv_subset_max_attempts"
    )
    assert ("optimization", "subset_search", "max_tests") in max_attempts_spec.get("read_keys", [])


def test_config_override_specs_contain_required_widget_ids() -> None:
    widget_ids = {spec.widget_id for spec in ADVANCED_FIELD_SPECS}

    assert "adv_lp_tolerance" in widget_ids
    assert "adv_output_privacy_validation" in widget_ids


def test_config_override_builder_writes_nested_values() -> None:
    builder = ConfigOverrideBuilder()
    values = {
        "adv_lp_tolerance": "2.5",
        "adv_output_privacy_validation": True,
    }

    data = builder.read_from_mapping(values)

    assert data["optimization"]["linear_programming"]["tolerance"] == 2.5
    assert data["output"]["include_privacy_validation"] is True


def test_advanced_parameters_use_effective_preset_defaults() -> None:
    app = BenchmarkApp()

    data = app._load_advanced_parameter_data("balanced_default")
    privacy_spec = next(
        spec for spec in BenchmarkApp.ADVANCED_FIELD_MAP if spec["widget_id"] == "adv_output_privacy_validation"
    )

    assert app._read_field_value_from_preset(data, privacy_spec) is True


def test_missing_advanced_widget_is_surfaced_not_swallowed() -> None:
    app = BenchmarkApp()
    app.notify = MagicMock()

    with patch("tui_app.logging.getLogger") as mock_get_logger:
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        app._warn_missing_widget("adv_missing_widget")

    mock_logger.warning.assert_called_once()
    app.notify.assert_called_once()
    assert "adv_missing_widget" in str(app.notify.call_args)


def test_write_log_message_writes_directly_on_app_thread() -> None:
    log_widget = MagicMock(spec=Log)
    app = MagicMock()
    app._thread_id = threading.get_ident()
    log_widget.app = app

    write_log_message(log_widget, "app-thread message")

    log_widget.write.assert_called_once_with("app-thread message\n")
    app.call_from_thread.assert_not_called()


def test_write_log_message_uses_call_from_thread_on_worker_thread() -> None:
    log_widget = MagicMock(spec=Log)
    app = MagicMock()
    app._thread_id = threading.get_ident() + 1
    log_widget.app = app

    write_log_message(log_widget, "worker message")

    app.call_from_thread.assert_called_once_with(log_widget.write, "worker message\n")
    log_widget.write.assert_not_called()


def test_log_handler_emit_uses_thread_safe_helper() -> None:
    log_widget = MagicMock(spec=Log)
    app = MagicMock()
    app._thread_id = threading.get_ident()
    log_widget.app = app
    handler = LogHandler(log_widget)
    handler.setFormatter(logging.Formatter("%(message)s"))

    handler.emit(logging.LogRecord("test", logging.INFO, "", 0, "hello", (), None))

    log_widget.write.assert_called_once_with("hello\n")
