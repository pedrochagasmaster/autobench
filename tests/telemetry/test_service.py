"""Tests for bounded telemetry service lifecycle and queue admission."""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import UUID

import pytest

from core.telemetry.constants import (
    DATA_CAPACITY,
    DISABLED_VALUES,
    PHYSICAL_QUEUE_CAPACITY,
    SHUTDOWN_BUDGET_S,
)
from core.telemetry.identity import Identity, encode_user_token
from core.telemetry.service import TelemetryService

SESSION_ID = UUID("12345678-1234-5678-1234-567812345678")
APP_VERSION = "3.0"
FIXED_UTC = datetime(2026, 7, 12, 22, 0, 0, tzinfo=timezone.utc)


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


def _make_service(
    *,
    writer: Callable[[bytes], None] | None = None,
    data_capacity: int = 8,
    shutdown_budget_s: float = SHUTDOWN_BUDGET_S,
    environ: dict[str, str] | None = None,
    shared_dir: Path | None = None,
    storage_root: Path | None = None,
    utc_clock: Callable[[], datetime] | None = None,
    monotonic_clock: Callable[[], float] | None = None,
    identity: Identity | None = None,
    session_id: UUID = SESSION_ID,
    app_version: str = APP_VERSION,
) -> TelemetryService:
    mono = {"t": 1000.0}

    def default_mono() -> float:
        return mono["t"]

    kwargs: dict[str, object] = {
        "identity": identity or _identity(),
        "session_id": session_id,
        "app_version": app_version,
        "utc_clock": utc_clock or (lambda: FIXED_UTC),
        "monotonic_clock": monotonic_clock or default_mono,
        "environ": environ if environ is not None else {},
        "data_capacity": data_capacity,
        "shutdown_budget_s": shutdown_budget_s,
    }
    if writer is not None:
        kwargs["writer"] = writer
    if shared_dir is not None:
        kwargs["shared_dir"] = shared_dir
    if storage_root is not None:
        kwargs["storage_root"] = storage_root
    svc = TelemetryService(**kwargs)  # type: ignore[arg-type]
    svc._test_mono = mono  # type: ignore[attr-defined]
    return svc


def _event_name(record: bytes) -> str:
    return json.loads(record.decode("utf-8"))["event"]


def test_physical_queue_capacity_constant() -> None:
    assert PHYSICAL_QUEUE_CAPACITY == DATA_CAPACITY + 2
    assert SHUTDOWN_BUDGET_S == 0.250


def test_lazy_no_consumer_before_first_accepted_event() -> None:
    written: list[bytes] = []
    svc = _make_service(writer=written.append)
    assert svc.state == "accepting"
    assert svc.consumer_thread is None
    assert written == []


def test_disabled_prevents_thread_start_and_writes() -> None:
    written: list[bytes] = []
    for raw in ("0", "FALSE", " Off ", "No", "false"):
        written.clear()
        svc = _make_service(
            writer=written.append,
            environ={"AUTOBENCH_TELEMETRY": raw},
        )
        svc.start_session("tui")
        svc.surface_viewed("share")
        assert svc.consumer_thread is None
        assert written == []
        svc.shutdown()
        assert svc.state == "closed"
        assert written == []


def test_enabled_by_default_and_unknown_env_values() -> None:
    for environ in ({}, {"AUTOBENCH_TELEMETRY": "yes"}, {"AUTOBENCH_TELEMETRY": "1"}):
        written: list[bytes] = []
        done = threading.Event()

        def writer(record: bytes) -> None:
            written.append(record)
            done.set()

        svc = _make_service(writer=writer, environ=environ)
        svc.start_session("cli_share")
        assert done.wait(timeout=2.0)
        assert svc.consumer_thread is not None
        assert svc.consumer_thread.daemon is True
        assert any(_event_name(r) == "session_start" for r in written)
        svc.shutdown()


def test_fifo_order_preserved() -> None:
    written: list[bytes] = []
    order_done = threading.Event()

    def writer(record: bytes) -> None:
        written.append(record)
        if len(written) >= 4:
            order_done.set()

    svc = _make_service(writer=writer, data_capacity=16)
    svc.start_session("tui")
    svc.surface_viewed("share")
    svc.action_attempted("share_analysis")
    svc.action_completed("share_analysis")
    assert order_done.wait(timeout=2.0)
    names = [_event_name(r) for r in written]
    assert names[:4] == [
        "session_start",
        "surface_viewed",
        "action_attempted",
        "action_completed",
    ]
    svc.shutdown()


def test_drop_newest_when_data_capacity_full_with_blocking_writer(
    caplog: pytest.LogCaptureFixture,
) -> None:
    entered = threading.Event()
    release = threading.Event()
    written: list[bytes] = []

    def writer(record: bytes) -> None:
        written.append(record)
        entered.set()
        assert release.wait(timeout=2.0)

    capacity = 4
    svc = _make_service(writer=writer, data_capacity=capacity)
    with caplog.at_level(logging.DEBUG, logger="core.telemetry.service"):
        svc.start_session("tui")
        assert entered.wait(timeout=2.0)
        # Consumer holds one record in the writer; fill data capacity in the queue.
        for _ in range(capacity):
            svc.surface_viewed("share")
        # Newest must drop without blocking.
        before = time.monotonic()
        svc.surface_viewed("rate")
        assert time.monotonic() - before < 0.05
        assert any("drop" in r.message.lower() or "full" in r.message.lower() for r in caplog.records)
    release.set()
    svc.shutdown()
    names = [_event_name(r) for r in written]
    assert names.count("surface_viewed") == capacity
    assert "session_start" in names


def test_physical_reserved_controls_when_data_queue_full() -> None:
    """Reserved slots must accept session_end + flush while data capacity is full.

    Writer stays blocked so queued data is not drained. Shutdown runs on another
    thread; observing ``closing`` under the admission lock means control puts
    already completed. This fails if the queue maxsize is only ``data_capacity``.
    """
    entered = threading.Event()
    release = threading.Event()
    written: list[bytes] = []

    def writer(record: bytes) -> None:
        written.append(record)
        entered.set()
        assert release.wait(timeout=2.0)

    capacity = 3
    svc = _make_service(writer=writer, data_capacity=capacity, shutdown_budget_s=2.0)
    assert svc._queue.maxsize == capacity + 2

    svc.start_session("cli_rate")
    assert entered.wait(timeout=2.0)
    for _ in range(capacity):
        svc.surface_viewed("rate")

    finished = threading.Event()

    def shut() -> None:
        svc.shutdown()
        finished.set()

    shutting = threading.Thread(target=shut)
    shutting.start()

    deadline = _deadline()
    saw_closing = False
    poll = threading.Event()
    while time.monotonic() < deadline:
        with svc._lock:
            # Acquiring the lock after shutdown entered closing means the
            # session_end/flush puts under that critical section have finished.
            if svc._state in {"closing", "closed"}:
                saw_closing = True
                break
        poll.wait(timeout=0.01)
    _assert_before(deadline)
    assert saw_closing

    release.set()
    assert finished.wait(timeout=2.0)
    shutting.join(timeout=2.0)
    assert svc.state == "closed"

    names = [_event_name(r) for r in written]
    assert "session_end" in names
    assert names.index("session_start") < names.index("session_end")
    end_at = names.index("session_end")
    assert all(i < end_at for i, n in enumerate(names) if n != "session_end")
    assert svc._flush_done.is_set()


def test_consumer_thread_start_failure_clears_and_retries(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    starts = {"n": 0}
    real_start = threading.Thread.start

    def flaky_start(self: threading.Thread) -> None:
        starts["n"] += 1
        if starts["n"] == 1:
            raise RuntimeError("simulated thread start failure")
        real_start(self)

    monkeypatch.setattr(threading.Thread, "start", flaky_start)

    written: list[bytes] = []
    drained = threading.Event()

    def writer(record: bytes) -> None:
        written.append(record)
        if len(written) >= 2:
            drained.set()

    svc = _make_service(writer=writer, data_capacity=8, shutdown_budget_s=1.0)
    with caplog.at_level(logging.DEBUG, logger="core.telemetry.service"):
        svc.start_session("tui")
    assert svc.consumer_thread is None
    assert getattr(svc, "_consumer", None) is None
    assert any("start" in r.message.lower() for r in caplog.records)

    svc.surface_viewed("share")
    assert drained.wait(timeout=2.0)
    assert svc.consumer_thread is not None
    assert starts["n"] >= 2
    names = [_event_name(r) for r in written]
    assert names[:2] == ["session_start", "surface_viewed"]
    svc.shutdown()


def test_state_transitions_and_rejection_during_closing_closed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    block = threading.Event()
    in_write = threading.Event()

    def writer(record: bytes) -> None:
        in_write.set()
        assert block.wait(timeout=2.0)

    svc = _make_service(writer=writer, shutdown_budget_s=1.0)
    svc.start_session("tui")
    assert in_write.wait(timeout=2.0)
    assert svc.state == "accepting"

    shutting = threading.Thread(target=svc.shutdown)
    shutting.start()
    deadline = _deadline()
    while svc.state == "accepting" and time.monotonic() < deadline:
        time.sleep(0.001)
    _assert_before(deadline)
    assert svc.state in {"closing", "closed"}
    with caplog.at_level(logging.DEBUG, logger="core.telemetry.service"):
        svc.surface_viewed("share")
    block.set()
    shutting.join(timeout=2.0)
    assert svc.state == "closed"
    svc.action_attempted("share_analysis")
    assert svc.state == "closed"


def test_writer_exception_does_not_stop_consumer() -> None:
    written: list[bytes] = []
    calls = {"n": 0}
    done = threading.Event()

    def writer(record: bytes) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        written.append(record)
        if _event_name(record) == "action_completed":
            done.set()

    svc = _make_service(writer=writer)
    svc.start_session("tui")
    svc.action_attempted("share_analysis")
    svc.action_completed("share_analysis")
    assert done.wait(timeout=2.0)
    assert any(_event_name(r) == "action_completed" for r in written)
    svc.shutdown()


def test_single_daemon_consumer_started_once() -> None:
    written: list[bytes] = []
    saw = threading.Event()

    def writer(record: bytes) -> None:
        written.append(record)
        saw.set()

    svc = _make_service(writer=writer)
    svc.start_session("tui")
    assert saw.wait(timeout=2.0)
    thread1 = svc.consumer_thread
    assert thread1 is not None
    svc.surface_viewed("share")
    svc.action_attempted("rate_analysis")
    deadline = _deadline()
    while len(written) < 3 and time.monotonic() < deadline:
        time.sleep(0.001)
    _assert_before(deadline)
    assert svc.consumer_thread is thread1
    svc.shutdown()


def test_admission_lock_not_held_during_writer_io() -> None:
    in_write = threading.Event()
    release = threading.Event()
    lock_free = {"ok": False}

    def writer(record: bytes) -> None:
        # If admission lock were held, this would fail.
        acquired = svc._lock.acquire(blocking=False)
        lock_free["ok"] = acquired
        if acquired:
            svc._lock.release()
        in_write.set()
        assert release.wait(timeout=2.0)

    svc = _make_service(writer=writer)
    svc.start_session("tui")
    assert in_write.wait(timeout=2.0)
    assert lock_free["ok"] is True
    release.set()
    svc.shutdown()


def test_same_lock_concurrent_admission_and_shutdown() -> None:
    barrier = threading.Barrier(3, timeout=2.0)
    written: list[bytes] = []
    errors: list[BaseException] = []

    def writer(record: bytes) -> None:
        written.append(record)

    svc = _make_service(writer=writer, data_capacity=64, shutdown_budget_s=1.0)
    svc.start_session("tui")

    def admit() -> None:
        try:
            barrier.wait()
            for _ in range(50):
                svc.surface_viewed("share")
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    def shut() -> None:
        try:
            barrier.wait()
            svc.shutdown()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t1 = threading.Thread(target=admit)
    t2 = threading.Thread(target=shut)
    t1.start()
    t2.start()
    barrier.wait()
    t1.join(timeout=2.0)
    t2.join(timeout=2.0)
    assert errors == []
    assert svc.state == "closed"


def test_session_end_order_and_clamped_duration() -> None:
    written: list[bytes] = []
    done = threading.Event()

    def writer(record: bytes) -> None:
        written.append(record)
        if _event_name(record) == "session_end":
            done.set()

    mono = {"t": 10.0}

    def monotonic_clock() -> float:
        return mono["t"]

    svc = _make_service(
        writer=writer,
        monotonic_clock=monotonic_clock,
        shutdown_budget_s=1.0,
    )
    svc.start_session("cli_share")
    mono["t"] = 10.0 + 12.3456
    svc.surface_viewed("share")
    svc.shutdown()
    assert done.wait(timeout=2.0)
    names = [_event_name(r) for r in written]
    assert names.index("surface_viewed") < names.index("session_end")
    end = json.loads(written[names.index("session_end")].decode("utf-8"))
    assert end["props"]["duration_s"] == 12.346

    # Clamp below zero and above max via injected clocks on a fresh service.
    written.clear()
    mono["t"] = 100.0
    svc2 = _make_service(writer=writer, monotonic_clock=monotonic_clock)
    svc2.start_session("tui")
    mono["t"] = 50.0  # elapsed negative -> clamp 0
    svc2.shutdown()
    deadline = _deadline()
    while not any(_event_name(r) == "session_end" for r in written) and time.monotonic() < deadline:
        time.sleep(0.001)
    _assert_before(deadline)
    end2 = next(r for r in written if _event_name(r) == "session_end")
    assert json.loads(end2.decode("utf-8"))["props"]["duration_s"] == 0.0

    written.clear()
    mono["t"] = 0.0
    svc3 = _make_service(writer=writer, monotonic_clock=monotonic_clock)
    svc3.start_session("tui")
    mono["t"] = 40_000_000.0
    svc3.shutdown()
    deadline = _deadline()
    while not any(_event_name(r) == "session_end" for r in written) and time.monotonic() < deadline:
        time.sleep(0.001)
    _assert_before(deadline)
    end3 = next(r for r in written if _event_name(r) == "session_end")
    assert json.loads(end3.decode("utf-8"))["props"]["duration_s"] == 31_536_000


def test_shutdown_without_active_session_skips_session_end_but_flushes() -> None:
    written: list[bytes] = []
    done = threading.Event()

    def writer(record: bytes) -> None:
        written.append(record)
        done.set()

    svc = _make_service(writer=writer, shutdown_budget_s=1.0)
    svc.surface_viewed("share")
    assert done.wait(timeout=2.0)
    svc.shutdown()
    names = [_event_name(r) for r in written]
    assert "surface_viewed" in names
    assert "session_end" not in names


def test_marker_ack_only_after_prior_writer_calls_return() -> None:
    release = threading.Event()
    in_first = threading.Event()
    write_count = {"n": 0}

    def writer(record: bytes) -> None:
        write_count["n"] += 1
        if write_count["n"] == 1:
            in_first.set()
            assert release.wait(timeout=2.0)

    svc = _make_service(writer=writer, shutdown_budget_s=2.0)
    svc.start_session("tui")
    assert in_first.wait(timeout=2.0)
    assert not svc._flush_done.is_set()

    finished = threading.Event()

    def shut() -> None:
        svc.shutdown()
        finished.set()

    t = threading.Thread(target=shut)
    t.start()
    deadline = _deadline()
    while svc.state == "accepting" and time.monotonic() < deadline:
        time.sleep(0.001)
    _assert_before(deadline)
    # Still blocked in first write: flush must not be acknowledged yet.
    time.sleep(0.02)
    assert not svc._flush_done.is_set()
    release.set()
    assert finished.wait(timeout=2.0)
    assert svc._flush_done.is_set()
    assert svc.state == "closed"


def test_control_overflow_tolerance_continues_shutdown() -> None:
    written: list[bytes] = []
    saw = threading.Event()

    def writer(record: bytes) -> None:
        written.append(record)
        saw.set()

    svc = _make_service(writer=writer, data_capacity=2, shutdown_budget_s=0.5)
    svc.start_session("tui")
    assert saw.wait(timeout=2.0)

    real_put = svc._queue.put_nowait
    fail_kinds = {"session_end", "flush"}

    def flaky_put(item: object) -> None:
        kind = getattr(item, "kind", None)
        if kind in fail_kinds:
            raise queue.Full
        real_put(item)

    svc._queue.put_nowait = flaky_put  # type: ignore[method-assign]
    svc.shutdown()
    assert svc.state == "closed"


def test_idempotent_shutdown() -> None:
    written: list[bytes] = []
    svc = _make_service(writer=written.append, shutdown_budget_s=1.0)
    svc.start_session("tui")
    svc.shutdown()
    assert svc.state == "closed"
    first_end_count = sum(1 for r in written if _event_name(r) == "session_end")
    svc.shutdown()
    svc.end_session()
    assert svc.state == "closed"
    assert sum(1 for r in written if _event_name(r) == "session_end") == first_end_count


def test_shutdown_wall_bound_with_blocking_writer_released_in_finally() -> None:
    block = threading.Event()
    in_write = threading.Event()

    def writer(record: bytes) -> None:
        in_write.set()
        assert block.wait(timeout=5.0)

    svc = _make_service(writer=writer, shutdown_budget_s=0.250)
    svc.start_session("tui")
    assert in_write.wait(timeout=2.0)
    try:
        t0 = time.monotonic()
        svc.shutdown()
        elapsed = time.monotonic() - t0
        assert elapsed <= 0.300
        assert svc.state == "closed"
    finally:
        block.set()


def test_no_restart_after_closed() -> None:
    written: list[bytes] = []
    svc = _make_service(writer=written.append)
    svc.start_session("tui")
    deadline = _deadline()
    while not written and time.monotonic() < deadline:
        time.sleep(0.001)
    _assert_before(deadline)
    thread = svc.consumer_thread
    svc.shutdown()
    assert svc.state == "closed"
    before = list(written)
    svc.start_session("tui")
    svc.surface_viewed("share")
    time.sleep(0.05)
    assert written == before
    assert svc.consumer_thread is thread or svc.consumer_thread is None
    assert svc.state == "closed"


def test_default_shared_gate_runs_on_consumer_and_private_persists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate_threads: list[str] = []

    def fake_gate(users_dir: Path, **kwargs: object) -> bool:
        gate_threads.append(threading.current_thread().name)
        return False

    monkeypatch.setattr(
        "core.telemetry.service.shared_writer_supported",
        fake_gate,
    )
    storage_root = tmp_path / "ads"
    shared_dir = tmp_path / "shared"
    (shared_dir / "users").mkdir(parents=True)
    home = storage_root / "alice"
    home.mkdir(parents=True)

    svc = TelemetryService(
        identity=_identity("alice"),
        session_id=SESSION_ID,
        app_version=APP_VERSION,
        utc_clock=lambda: FIXED_UTC,
        monotonic_clock=time.monotonic,
        environ={},
        shared_dir=shared_dir,
        storage_root=storage_root,
        shutdown_budget_s=1.0,
    )
    main_name = threading.current_thread().name
    svc.start_session("tui")
    private = storage_root / "alice" / ".autobench" / "telemetry" / "events.jsonl"
    deadline = _deadline()
    while not private.exists() and time.monotonic() < deadline:
        time.sleep(0.001)
    _assert_before(deadline)
    svc.shutdown()
    assert private.exists()
    assert private.read_bytes()
    assert gate_threads
    assert all(t != main_name for t in gate_threads)
    shared_files = list((shared_dir / "users").glob("*.jsonl"))
    assert shared_files == []


def test_producer_path_does_not_touch_filesystem_or_capability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fs_hits: list[str] = []
    main = threading.current_thread()

    def track(name: str) -> Callable[..., object]:
        def _wrapper(*args: object, **kwargs: object) -> object:
            if threading.current_thread() is main:
                fs_hits.append(name)
            raise RuntimeError(f"producer must not call {name}")

        return _wrapper

    monkeypatch.setattr("core.telemetry.service.paths_for", track("paths_for"))
    monkeypatch.setattr("core.telemetry.service.append_record", track("append_record"))
    monkeypatch.setattr(
        "core.telemetry.service.shared_writer_supported",
        track("shared_writer_supported"),
    )

    entered = threading.Event()
    release = threading.Event()

    def writer(record: bytes) -> None:
        entered.set()
        assert release.wait(timeout=2.0)

    svc = _make_service(
        writer=writer,
        shared_dir=tmp_path / "shared",
        storage_root=tmp_path / "ads",
    )
    svc.start_session("tui")
    svc.surface_viewed("share")
    assert fs_hits == []
    assert entered.wait(timeout=2.0)
    assert fs_hits == []
    release.set()
    svc.shutdown()


def test_invalid_override_disables_shared_preserves_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "core.telemetry.service.shared_writer_supported",
        lambda *a, **k: True,
    )
    storage_root = tmp_path / "ads"
    (storage_root / "alice").mkdir(parents=True)
    default_shared = tmp_path / "default_shared"
    (default_shared / "users").mkdir(parents=True)

    svc = TelemetryService(
        identity=_identity("alice"),
        session_id=SESSION_ID,
        app_version=APP_VERSION,
        utc_clock=lambda: FIXED_UTC,
        monotonic_clock=time.monotonic,
        environ={"AUTOBENCH_TELEMETRY_DIR": "   "},
        shared_dir=default_shared,
        storage_root=storage_root,
        shutdown_budget_s=1.0,
    )
    svc.start_session("tui")
    private = storage_root / "alice" / ".autobench" / "telemetry" / "events.jsonl"
    deadline = _deadline()
    while not private.exists() and time.monotonic() < deadline:
        time.sleep(0.001)
    _assert_before(deadline)
    svc.shutdown()
    assert private.read_bytes()
    assert list((default_shared / "users").glob("*.jsonl")) == []


def test_override_path_used_exactly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Path] = []

    def fake_gate(users_dir: Path, **kwargs: object) -> bool:
        seen.append(users_dir)
        return False

    monkeypatch.setattr("core.telemetry.service.shared_writer_supported", fake_gate)
    storage_root = tmp_path / "ads"
    (storage_root / "alice").mkdir(parents=True)
    override = tmp_path / "override_shared"
    (override / "users").mkdir(parents=True)

    svc = TelemetryService(
        identity=_identity("alice"),
        session_id=SESSION_ID,
        app_version=APP_VERSION,
        utc_clock=lambda: FIXED_UTC,
        monotonic_clock=time.monotonic,
        environ={"AUTOBENCH_TELEMETRY_DIR": str(override)},
        storage_root=storage_root,
        shutdown_budget_s=1.0,
    )
    svc.start_session("tui")
    private = storage_root / "alice" / ".autobench" / "telemetry" / "events.jsonl"
    deadline = _deadline()
    while not private.exists() and time.monotonic() < deadline:
        time.sleep(0.001)
    _assert_before(deadline)
    svc.shutdown()
    assert seen
    assert all(p == override / "users" for p in seen)


def test_shared_capability_gate_evaluated_once_per_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Host capability is static; the gate must not be re-probed per record."""
    calls: list[Path] = []

    def fake_gate(users_dir: Path, **kwargs: object) -> bool:
        calls.append(users_dir)
        return False

    monkeypatch.setattr("core.telemetry.service.shared_writer_supported", fake_gate)
    storage_root = tmp_path / "ads"
    (storage_root / "alice").mkdir(parents=True)
    shared_dir = tmp_path / "shared"
    (shared_dir / "users").mkdir(parents=True)

    svc = TelemetryService(
        identity=_identity("alice"),
        session_id=SESSION_ID,
        app_version=APP_VERSION,
        utc_clock=lambda: FIXED_UTC,
        monotonic_clock=time.monotonic,
        environ={},
        shared_dir=shared_dir,
        storage_root=storage_root,
        shutdown_budget_s=1.0,
    )
    svc.start_session("tui")
    svc.surface_viewed("share")
    svc.action_attempted("share_analysis")
    svc.action_completed("share_analysis")
    private = storage_root / "alice" / ".autobench" / "telemetry" / "events.jsonl"
    deadline = _deadline()
    while (
        not private.exists() or private.read_bytes().count(b"\n") < 4
    ) and time.monotonic() < deadline:
        time.sleep(0.001)
    _assert_before(deadline)
    svc.shutdown()
    assert private.read_bytes().count(b"\n") >= 4
    assert len(calls) == 1


@pytest.mark.parametrize("value", sorted(DISABLED_VALUES))
def test_disabled_values_constant_covers_opt_out(value: str) -> None:
    assert value in {"0", "false", "off", "no"}
