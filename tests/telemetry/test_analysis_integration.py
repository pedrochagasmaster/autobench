"""Shared analysis-run telemetry instrumentation integration tests."""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Callable, List, Tuple
from uuid import UUID

import pytest

import core.analysis_run as analysis_run
import core.telemetry as telemetry
from core.analysis_run import RunAborted, RunBlocked, execute_rate_run, execute_share_run
from core.contracts import AnalysisRunRequest
from core.observability import RunObservability
from core.telemetry.identity import Identity, encode_user_token
from core.telemetry.service import TelemetryService
from tests.conftest import is_telemetry_test_path

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "gate_demo.csv"
SHARE_DIMENSIONS = ["card_type", "channel"]
SESSION_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
SENSITIVE_MARKERS = (
    str(FIXTURE),
    "Target",
    "issuer_name",
    "txn_cnt",
    "card_type",
    "balanced_default",
    "gate_demo",
    "/ads_storage",
)


@pytest.fixture(autouse=True)
def _reset_telemetry() -> None:
    telemetry._reset_for_tests()
    yield
    telemetry._reset_for_tests()


def _capture(calls: List[Tuple[str, tuple]]) -> dict[str, Callable[..., None]]:
    def make(name: str) -> Callable[..., None]:
        def _fn(*args: Any) -> None:
            calls.append((name, args))

        return _fn

    return {
        "action_attempted": make("attempted"),
        "action_completed": make("completed"),
        "action_refused": make("refused"),
        "action_failed": make("failed"),
    }


def _patch_helpers(monkeypatch: pytest.MonkeyPatch, calls: List[Tuple[str, tuple]]) -> None:
    for attr, fn in _capture(calls).items():
        monkeypatch.setattr(analysis_run, attr, fn)


def _share_request(tmp_path: Path, **overrides: Any) -> AnalysisRunRequest:
    data = {
        "csv": str(FIXTURE),
        "entity": "Target",
        "metric": "txn_cnt",
        "dimensions": list(SHARE_DIMENSIONS),
        "time_col": "year_month",
        "preset": "balanced_default",
        "compliance_posture": "strict",
        "output": str(tmp_path / "share.xlsx"),
        "validate_input": False,
    }
    data.update(overrides)
    return AnalysisRunRequest(**data)


def _rate_request(tmp_path: Path, **overrides: Any) -> AnalysisRunRequest:
    data = {
        "mode": "rate",
        "csv": str(FIXTURE),
        "entity": "Target",
        "total_col": "total",
        "approved_col": "approved",
        "fraud_col": "fraud",
        "dimensions": list(SHARE_DIMENSIONS),
        "time_col": "year_month",
        "preset": "balanced_default",
        "compliance_posture": "strict",
        "control3_overrides": {"privacy_basis": "clearing_spend"},
        "output": str(tmp_path / "rate.xlsx"),
        "validate_input": False,
        "export_balanced_csv": False,
    }
    data.update(overrides)
    return AnalysisRunRequest(**data)


def test_conftest_path_helper_opts_out_legacy_not_telemetry() -> None:
    root = Path(__file__).resolve().parents[1]
    assert is_telemetry_test_path(Path(__file__)) is True
    assert is_telemetry_test_path(root / "test_analysis_run_integration.py") is False
    assert is_telemetry_test_path(root / "telemetry" / "test_cli_session.py") is True


def test_legacy_analysis_opt_out_prevents_writer_thread_and_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulate root conftest opt-out applied to legacy analysis tests."""
    monkeypatch.setenv("AUTOBENCH_TELEMETRY", "0")
    telemetry._reset_for_tests()
    ads = tmp_path / "ads_storage"
    ads.mkdir()
    monkeypatch.setattr(
        telemetry,
        "_build_default_service",
        lambda: TelemetryService(
            identity=Identity(uid=os.geteuid(), username="legacy", token=encode_user_token("legacy")),
            session_id=SESSION_ID,
            app_version="3.0",
            storage_root=ads,
            environ={"AUTOBENCH_TELEMETRY": "0"},
        ),
    )
    logger = logging.getLogger("test_legacy_opt_out")
    artifacts = execute_share_run(_share_request(tmp_path), logger)
    assert artifacts.analysis_output_file
    svc = telemetry._get_service()
    assert svc.consumer_thread is None or not svc.consumer_thread.is_alive()
    assert list(ads.rglob("*.jsonl")) == []


def test_share_attempt_then_complete_ordering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: List[Tuple[str, tuple]] = []
    _patch_helpers(monkeypatch, calls)
    execute_share_run(_share_request(tmp_path), logging.getLogger("test"))
    assert calls == [
        ("attempted", ("share_analysis",)),
        ("completed", ("share_analysis",)),
    ]


def test_rate_attempt_then_complete_ordering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: List[Tuple[str, tuple]] = []
    _patch_helpers(monkeypatch, calls)
    execute_rate_run(_rate_request(tmp_path), logging.getLogger("test"))
    assert calls == [
        ("attempted", ("rate_analysis",)),
        ("completed", ("rate_analysis",)),
    ]


def test_run_blocked_refuses_compliance_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: List[Tuple[str, tuple]] = []
    _patch_helpers(monkeypatch, calls)
    request = _share_request(
        tmp_path,
        compliance_posture="accuracy_first",
        acknowledge_accuracy_first=False,
        preset=None,
    )
    with pytest.raises(RunBlocked):
        execute_share_run(request, logging.getLogger("test"))
    assert calls == [
        ("attempted", ("share_analysis",)),
        ("refused", ("share_analysis", "compliance_policy")),
    ]


def test_run_aborted_refuses_input_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: List[Tuple[str, tuple]] = []
    _patch_helpers(monkeypatch, calls)
    request = _share_request(tmp_path, metric="column_that_does_not_exist")
    with pytest.raises(RunAborted) as exc_info:
        execute_share_run(request, logging.getLogger("test"))
    assert not isinstance(exc_info.value, RunBlocked)
    assert calls == [
        ("attempted", ("share_analysis",)),
        ("refused", ("share_analysis", "input_validation")),
    ]


def test_configuration_value_error_refuses_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: List[Tuple[str, tuple]] = []
    _patch_helpers(monkeypatch, calls)
    request = _share_request(tmp_path, preset="definitely_not_a_real_preset")
    with pytest.raises(ValueError, match="not found"):
        execute_share_run(request, logging.getLogger("test"))
    assert calls == [
        ("attempted", ("share_analysis",)),
        ("refused", ("share_analysis", "configuration")),
    ]


@pytest.mark.parametrize(
    ("phase", "patch_target", "category"),
    [
        ("input", "prepare_run_data", "input"),
        ("analysis", "build_dimensional_analyzer", "analysis"),
        ("output", "write_outputs", "output"),
    ],
)
def test_phase_failure_emits_failed_category(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
    patch_target: str,
    category: str,
) -> None:
    calls: List[Tuple[str, tuple]] = []
    _patch_helpers(monkeypatch, calls)

    def boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError(f"boom-{phase}")

    monkeypatch.setattr(analysis_run, patch_target, boom)
    with pytest.raises(RuntimeError, match=f"boom-{phase}"):
        execute_share_run(_share_request(tmp_path), logging.getLogger("test"))
    assert calls == [
        ("attempted", ("share_analysis",)),
        ("failed", ("share_analysis", category)),
    ]


def test_configuration_non_value_error_is_unexpected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: List[Tuple[str, tuple]] = []
    _patch_helpers(monkeypatch, calls)

    def boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("config-boom")

    monkeypatch.setattr(analysis_run, "build_run_config", boom)
    with pytest.raises(RuntimeError, match="config-boom"):
        execute_share_run(_share_request(tmp_path), logging.getLogger("test"))
    assert calls == [
        ("attempted", ("share_analysis",)),
        ("failed", ("share_analysis", "unexpected")),
    ]


def test_telemetry_service_failure_does_not_alter_successful_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The helpers' own never-raise guarantee must protect the analysis run."""

    def raise_always(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("telemetry service boom")

    monkeypatch.setattr("core.telemetry._get_service", raise_always)

    artifacts = execute_share_run(_share_request(tmp_path), logging.getLogger("test"))
    assert Path(artifacts.analysis_output_file).exists()


def test_only_closed_enum_args_and_no_sensitive_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: List[Tuple[str, tuple]] = []
    _patch_helpers(monkeypatch, calls)
    written: list[bytes] = []
    done = threading.Event()

    def writer(record: bytes) -> None:
        written.append(record)
        if len(written) >= 2:
            done.set()

    svc = TelemetryService(
        identity=Identity(uid=os.geteuid(), username="alice", token=encode_user_token("alice")),
        session_id=SESSION_ID,
        app_version="3.0",
        environ={},
        writer=writer,
        storage_root=tmp_path / "ads",
    )
    telemetry._reset_for_tests(svc)

    # Also exercise real helpers for serialization (separate from call capture).
    real_attempted = telemetry.action_attempted
    real_completed = telemetry.action_completed

    def attempted(action: str) -> None:
        calls.append(("attempted", (action,)))
        real_attempted(action)

    def completed(action: str) -> None:
        calls.append(("completed", (action,)))
        real_completed(action)

    monkeypatch.setattr(analysis_run, "action_attempted", attempted)
    monkeypatch.setattr(analysis_run, "action_completed", completed)
    monkeypatch.setattr(analysis_run, "action_refused", lambda *a: calls.append(("refused", a)))
    monkeypatch.setattr(analysis_run, "action_failed", lambda *a: calls.append(("failed", a)))

    execute_share_run(_share_request(tmp_path), logging.getLogger("test"))
    assert done.wait(timeout=2.0)
    assert calls[0][0] == "attempted"
    assert calls[-1][0] == "completed"
    for _name, args in calls:
        blob = json.dumps(args)
        for marker in SENSITIVE_MARKERS:
            assert marker not in blob
        for arg in args:
            assert isinstance(arg, str)
            assert arg in {
                "share_analysis",
                "rate_analysis",
                "configuration",
                "input_validation",
                "compliance_policy",
                "input",
                "analysis",
                "output",
                "unexpected",
            }
    for record in written:
        text = record.decode("utf-8")
        payload = json.loads(text)
        assert set(payload["props"]) <= {"action"}
        for marker in SENSITIVE_MARKERS:
            assert marker not in text


def test_observability_unchanged_on_instrumented_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: list[tuple] = []
    original_record = RunObservability.record

    def spy(self: RunObservability, *args: Any, **kwargs: Any) -> None:
        recorded.append((args, kwargs))
        return original_record(self, *args, **kwargs)

    monkeypatch.setattr(RunObservability, "record", spy)
    calls: List[Tuple[str, tuple]] = []
    _patch_helpers(monkeypatch, calls)
    execute_share_run(_share_request(tmp_path), logging.getLogger("test"))
    assert recorded  # start_event still recorded with entity/csv kwargs
    assert any("entity" in kwargs for _args, kwargs in recorded)
    assert calls[0][0] == "attempted"
    assert calls[-1][0] == "completed"


def test_never_double_terminal_on_refusal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: List[Tuple[str, tuple]] = []
    _patch_helpers(monkeypatch, calls)
    with pytest.raises(RunBlocked):
        execute_share_run(
            _share_request(
                tmp_path,
                compliance_posture="accuracy_first",
                acknowledge_accuracy_first=False,
                preset=None,
            ),
            logging.getLogger("test"),
        )
    terminal = [c for c in calls if c[0] in {"completed", "refused", "failed"}]
    assert len(terminal) == 1
    assert terminal[0][0] == "refused"
