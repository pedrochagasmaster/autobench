"""Tests for typed public telemetry helpers and process singleton."""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import get_args
from uuid import UUID

import pytest

import core.telemetry as telemetry
from core.telemetry.events import build_record
from core.telemetry.identity import Identity, encode_user_token
from core.telemetry.service import TelemetryService

SESSION_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
FIXED_UTC = datetime(2026, 7, 12, 23, 0, 0, tzinfo=timezone.utc)


def _identity(username: str = "alice") -> Identity:
    return Identity(
        uid=os.geteuid(),
        username=username,
        token=encode_user_token(username),
    )


def _deadline(seconds: float = 3.0) -> float:
    return time.monotonic() + seconds


def _assert_before(deadline: float) -> None:
    assert time.monotonic() < deadline, "test exceeded deadline (possible hang)"


@pytest.fixture(autouse=True)
def _reset_telemetry() -> None:
    telemetry._reset_for_tests()
    yield
    telemetry._reset_for_tests()


def _inject_service(writer, **kwargs) -> TelemetryService:
    svc = TelemetryService(
        identity=kwargs.get("identity") or _identity(),
        session_id=kwargs.get("session_id", SESSION_ID),
        app_version=kwargs.get("app_version", "3.0"),
        utc_clock=kwargs.get("utc_clock", lambda: FIXED_UTC),
        monotonic_clock=kwargs.get("monotonic_clock", time.monotonic),
        environ=kwargs.get("environ", {}),
        writer=writer,
        data_capacity=kwargs.get("data_capacity", 32),
        shutdown_budget_s=kwargs.get("shutdown_budget_s", 1.0),
        shared_dir=kwargs.get("shared_dir"),
        storage_root=kwargs.get("storage_root"),
    )
    telemetry._reset_for_tests(svc)
    return svc


def test_public_surface_has_no_generic_emit() -> None:
    assert not hasattr(telemetry, "emit")
    assert not hasattr(telemetry, "emit_event")
    names = {
        "start_session",
        "end_session",
        "surface_viewed",
        "action_attempted",
        "action_completed",
        "action_cancelled",
        "action_refused",
        "action_failed",
        "LaunchContext",
        "Surface",
        "Action",
        "RefuseReason",
        "FailCategory",
    }
    for name in names:
        assert hasattr(telemetry, name)


def test_typed_aliases_match_catalog() -> None:
    assert set(get_args(telemetry.LaunchContext)) == {"cli_share", "cli_rate", "tui"}
    assert set(get_args(telemetry.Surface)) == {"share", "rate"}
    assert set(get_args(telemetry.Action)) == {"share_analysis", "rate_analysis"}
    assert set(get_args(telemetry.RefuseReason)) == {
        "configuration",
        "input_validation",
        "compliance_policy",
    }
    assert set(get_args(telemetry.FailCategory)) == {
        "input",
        "analysis",
        "output",
        "unexpected",
    }


def test_helpers_delegate_and_never_raise_on_invalid() -> None:
    written: list[bytes] = []
    done = threading.Event()

    def writer(record: bytes) -> None:
        written.append(record)
        if len(written) >= 7:
            done.set()

    _inject_service(writer)
    telemetry.start_session("tui")
    telemetry.surface_viewed("share")
    telemetry.action_attempted("share_analysis")
    telemetry.action_completed("share_analysis")
    telemetry.action_cancelled("rate_analysis")
    telemetry.action_refused("share_analysis", "configuration")
    telemetry.action_failed("rate_analysis", "unexpected")
    assert done.wait(timeout=2.0)
    names = [json.loads(r.decode("utf-8"))["event"] for r in written]
    assert names == [
        "session_start",
        "surface_viewed",
        "action_attempted",
        "action_completed",
        "action_cancelled",
        "action_refused",
        "action_failed",
    ]

    before = list(written)
    # Invalid arguments must not raise and must not enqueue.
    telemetry.start_session("not-a-context")  # type: ignore[arg-type]
    telemetry.surface_viewed("nope")  # type: ignore[arg-type]
    telemetry.action_attempted("nope")  # type: ignore[arg-type]
    telemetry.action_completed("")  # type: ignore[arg-type]
    telemetry.action_cancelled(None)  # type: ignore[arg-type]
    telemetry.action_refused("share_analysis", "bad")  # type: ignore[arg-type]
    telemetry.action_failed("share_analysis", "bad")  # type: ignore[arg-type]
    time.sleep(0.05)
    assert written == before
    telemetry.end_session()


def test_opt_out_spellings_via_public_helpers() -> None:
    for raw in ("0", " False", "OFF", "no"):
        telemetry._reset_for_tests()
        written: list[bytes] = []
        svc = TelemetryService(
            identity=_identity(),
            session_id=SESSION_ID,
            app_version="3.0",
            utc_clock=lambda: FIXED_UTC,
            monotonic_clock=time.monotonic,
            environ={"AUTOBENCH_TELEMETRY": raw},
            writer=written.append,
        )
        telemetry._reset_for_tests(svc)
        telemetry.start_session("tui")
        telemetry.surface_viewed("share")
        telemetry.end_session()
        assert written == []
        assert svc.consumer_thread is None


def test_helpers_swallow_all_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    class Boom(TelemetryService):
        def start_session(self, launch_context: str) -> None:
            raise RuntimeError("nope")

        def surface_viewed(self, surface: str) -> None:
            raise ValueError("nope")

        def end_session(self) -> None:
            raise OSError("nope")

    boom = Boom(
        identity=_identity(),
        session_id=SESSION_ID,
        app_version="3.0",
        utc_clock=lambda: FIXED_UTC,
        monotonic_clock=time.monotonic,
        environ={},
        writer=lambda _r: None,
    )
    telemetry._reset_for_tests(boom)
    telemetry.start_session("tui")
    telemetry.surface_viewed("share")
    telemetry.end_session()


def test_reset_for_tests_isolates_singleton() -> None:
    written_a: list[bytes] = []
    written_b: list[bytes] = []
    done_a = threading.Event()
    done_b = threading.Event()

    def writer_a(record: bytes) -> None:
        written_a.append(record)
        done_a.set()

    def writer_b(record: bytes) -> None:
        written_b.append(record)
        done_b.set()

    _inject_service(writer_a)
    telemetry.start_session("cli_share")
    assert done_a.wait(timeout=2.0)
    telemetry._reset_for_tests()
    _inject_service(writer_b)
    telemetry.start_session("cli_rate")
    assert done_b.wait(timeout=2.0)
    assert written_a and written_b
    assert all(
        json.loads(r.decode("utf-8"))["props"]["launch_context"] == "cli_share"
        for r in written_a
        if json.loads(r.decode("utf-8"))["event"] == "session_start"
    )
    assert any(
        json.loads(r.decode("utf-8"))["props"]["launch_context"] == "cli_rate"
        for r in written_b
    )


def test_import_does_not_start_consumer() -> None:
    telemetry._reset_for_tests()
    import importlib

    importlib.reload(telemetry)
    # Reloading clears singleton; no service thread should exist yet.
    assert getattr(telemetry, "_service", None) is None
    telemetry._reset_for_tests()


def test_app_version_from_repository_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Public singleton captures version at construction; force rebuild via reset.
    telemetry._reset_for_tests()
    version_path = Path(telemetry.__file__).resolve().parents[2] / "VERSION"
    assert version_path.is_file()
    expected = version_path.read_text(encoding="utf-8").strip()

    written: list[bytes] = []
    done = threading.Event()

    def writer(record: bytes) -> None:
        written.append(record)
        done.set()

    # Build the default singleton path by calling helpers after reset with a
    # patched factory that still uses real version resolution.
    real_factory = telemetry._build_default_service

    def factory() -> TelemetryService:
        svc = real_factory()
        svc._writer_override = writer
        return svc

    monkeypatch.setattr(telemetry, "_build_default_service", factory)
    telemetry.start_session("tui")
    assert done.wait(timeout=2.0)
    payload = json.loads(written[0].decode("utf-8"))
    assert payload["app_version"] == expected
    telemetry.end_session()


@pytest.mark.parametrize(
    "bad_version",
    [
        "3.0\x7f",  # DEL: category Cc but ord >= 32
        "3.0\u200b",  # zero-width space: category Cf
        "3.0\x01",  # C0 control
    ],
)
def test_read_app_version_falls_back_on_any_category_c_char(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad_version: str
) -> None:
    """A VERSION build_record would reject must fall back, not poison all events."""
    version_path = tmp_path / "VERSION"
    version_path.write_text(bad_version, encoding="utf-8")
    monkeypatch.setattr(telemetry, "_VERSION_PATH", version_path)
    resolved = telemetry._read_app_version()
    assert resolved == "0"
    # The fallback must itself be accepted by record building.
    build_record(
        "session_start",
        {"launch_context": "tui"},
        user="alice",
        session_id=SESSION_ID,
        app_version=resolved,
        now=FIXED_UTC,
    )


def test_end_session_public_is_idempotent() -> None:
    written: list[bytes] = []
    _inject_service(written.append)
    telemetry.start_session("tui")
    deadline = _deadline()
    while not written and time.monotonic() < deadline:
        time.sleep(0.001)
    _assert_before(deadline)
    telemetry.end_session()
    telemetry.end_session()
    ends = [
        r
        for r in written
        if json.loads(r.decode("utf-8"))["event"] == "session_end"
    ]
    assert len(ends) == 1
