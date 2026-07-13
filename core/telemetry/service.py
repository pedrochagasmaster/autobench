"""Bounded best-effort telemetry service: queue, daemon consumer, shutdown."""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Mapping
from uuid import UUID

from core.telemetry.capability import shared_writer_supported
from core.telemetry.constants import (
    DATA_CAPACITY,
    DEFAULT_SHARED_DIR,
    DISABLED_VALUES,
    ENV_TELEMETRY,
    ENV_TELEMETRY_DIR,
    MAX_DURATION_S,
    SHUTDOWN_BUDGET_S,
    shared_dir_override,
)
from core.telemetry.events import build_record
from core.telemetry.fs_safety import LexicalAbsolutePath, lexical_absolute_path
from core.telemetry.identity import Identity
from core.telemetry.writer import WriterPaths, append_record, paths_for

logger = logging.getLogger(__name__)


class _State(Enum):
    ACCEPTING = "accepting"
    CLOSING = "closing"
    CLOSED = "closed"


class _ItemKind(Enum):
    DATA = "data"
    SESSION_END = "session_end"
    FLUSH = "flush"


@dataclass(frozen=True)
class _QueueItem:
    kind: _ItemKind
    payload: bytes | None = None


def _clamp_duration(seconds: float) -> float:
    if seconds < 0:
        return 0.0
    if seconds > MAX_DURATION_S:
        return float(MAX_DURATION_S)
    return round(float(seconds), 3)


def _env_enabled(environ: Mapping[str, str]) -> bool:
    raw = environ.get(ENV_TELEMETRY)
    if raw is None:
        return True
    return raw.strip().lower() not in DISABLED_VALUES


def _resolve_shared_dir(
    environ: Mapping[str, str],
    explicit: Path | None,
) -> tuple[Path | None, bool]:
    """Return (shared_dir, shared_config_ok).

    A present-but-blank ``AUTOBENCH_TELEMETRY_DIR`` fails shared writes closed
    while leaving private writes eligible (the reader, by contrast, falls back
    to the default shared parent).
    """
    if ENV_TELEMETRY_DIR in environ:
        override = shared_dir_override(environ)
        return override, override is not None
    if explicit is not None:
        return explicit, True
    return DEFAULT_SHARED_DIR, True


class TelemetryService:
    """Process-local bounded telemetry queue with a single daemon consumer."""

    def __init__(
        self,
        *,
        identity: Identity,
        session_id: UUID,
        app_version: str,
        utc_clock: Callable[[], datetime] | None = None,
        monotonic_clock: Callable[[], float] | None = None,
        environ: Mapping[str, str] | None = None,
        shared_dir: Path | None = None,
        storage_root: Path | None = None,
        writer: Callable[[bytes], None] | None = None,
        data_capacity: int = DATA_CAPACITY,
        shutdown_budget_s: float = SHUTDOWN_BUDGET_S,
    ) -> None:
        self._identity = identity
        self._session_id = session_id
        self._app_version = app_version
        self._utc_clock = utc_clock or (lambda: datetime.now(timezone.utc))
        self._monotonic_clock = monotonic_clock or time.monotonic
        self._environ = dict(environ) if environ is not None else dict(os.environ)
        self._storage_root = (
            Path("/ads_storage") if storage_root is None else storage_root
        )
        self._data_capacity = data_capacity
        self._shutdown_budget_s = shutdown_budget_s
        self._enabled = _env_enabled(self._environ)
        resolved, shared_ok = _resolve_shared_dir(self._environ, shared_dir)
        self._shared_dir: LexicalAbsolutePath | None = (
            lexical_absolute_path(resolved) if resolved is not None else None
        )
        self._shared_config_ok = shared_ok
        self._writer_override = writer
        # Write paths and host capability cannot change mid-process; resolved
        # once by the consumer thread on first write. None = not yet resolved.
        self._write_targets: tuple[WriterPaths, bool] | None = None

        physical = data_capacity + 2
        if physical < 2:
            physical = 2
        self._queue: queue.Queue[_QueueItem] = queue.Queue(maxsize=physical)
        self._lock = threading.Lock()
        self._state = _State.ACCEPTING
        self._queued_data = 0
        self._consumer: threading.Thread | None = None
        self._session_origin: float | None = None
        self._flush_done = threading.Event()
        self._shutdown_deadline: float | None = None

    @property
    def state(self) -> str:
        with self._lock:
            return self._state.value

    @property
    def consumer_thread(self) -> threading.Thread | None:
        with self._lock:
            return self._consumer

    def start_session(self, launch_context: str) -> None:
        if not self._enabled:
            return
        try:
            record = build_record(
                "session_start",
                {"launch_context": launch_context},
                user=self._identity.username,
                session_id=self._session_id,
                app_version=self._app_version,
                now=self._utc_clock(),
            )
        except Exception:
            logger.debug("telemetry session_start build failed", exc_info=True)
            return
        self._admit(record, session_origin=True)

    def end_session(self) -> None:
        self.shutdown()

    def surface_viewed(self, surface: str) -> None:
        self._emit("surface_viewed", {"surface": surface})

    def action_attempted(self, action: str) -> None:
        self._emit("action_attempted", {"action": action})

    def action_completed(self, action: str) -> None:
        self._emit("action_completed", {"action": action})

    def action_cancelled(self, action: str) -> None:
        self._emit("action_cancelled", {"action": action})

    def action_refused(self, action: str, reason: str) -> None:
        self._emit("action_refused", {"action": action, "reason": reason})

    def action_failed(self, action: str, category: str) -> None:
        self._emit("action_failed", {"action": action, "category": category})

    def shutdown(self) -> None:
        with self._lock:
            if self._state is _State.CLOSED:
                return
            if self._state is _State.CLOSING:
                # Another caller is shutting down; wait out remaining budget.
                deadline = self._shutdown_deadline
            else:
                self._state = _State.CLOSING
                deadline = self._monotonic_clock() + self._shutdown_budget_s
                self._shutdown_deadline = deadline
                origin = self._session_origin
                self._session_origin = None
                if origin is not None:
                    duration = _clamp_duration(self._monotonic_clock() - origin)
                    try:
                        record = build_record(
                            "session_end",
                            {"duration_s": duration},
                            user=self._identity.username,
                            session_id=self._session_id,
                            app_version=self._app_version,
                            now=self._utc_clock(),
                        )
                    except Exception:
                        logger.debug(
                            "telemetry session_end build failed", exc_info=True
                        )
                        record = None
                    if record is not None:
                        try:
                            self._queue.put_nowait(
                                _QueueItem(kind=_ItemKind.SESSION_END, payload=record)
                            )
                        except queue.Full:
                            logger.debug(
                                "telemetry session_end control enqueue failed",
                                exc_info=True,
                            )
                try:
                    self._queue.put_nowait(_QueueItem(kind=_ItemKind.FLUSH))
                except queue.Full:
                    logger.debug(
                        "telemetry flush marker enqueue failed",
                        exc_info=True,
                    )
                    self._flush_done.set()
                if self._consumer is None:
                    # No consumer will acknowledge the marker.
                    self._flush_done.set()

        remaining = 0.0
        if deadline is not None:
            remaining = max(0.0, deadline - self._monotonic_clock())
        if remaining > 0 and self._enabled:
            self._flush_done.wait(timeout=remaining)
        with self._lock:
            self._state = _State.CLOSED

    def _emit(self, event: str, props: Mapping[str, object]) -> None:
        if not self._enabled:
            return
        try:
            record = build_record(
                event,
                props,
                user=self._identity.username,
                session_id=self._session_id,
                app_version=self._app_version,
                now=self._utc_clock(),
            )
        except Exception:
            logger.debug("telemetry build_record failed", exc_info=True)
            return
        self._admit(record)

    def _admit(self, record: bytes, *, session_origin: bool = False) -> None:
        """Enqueue a data record; optionally mark the session origin atomically."""
        with self._lock:
            if self._state is not _State.ACCEPTING:
                logger.debug("telemetry drop: service not accepting")
                return
            if self._queued_data >= self._data_capacity:
                logger.debug("telemetry drop: data queue full")
                return
            item = _QueueItem(kind=_ItemKind.DATA, payload=record)
            try:
                self._queue.put_nowait(item)
            except queue.Full:
                logger.debug("telemetry drop: physical queue full", exc_info=True)
                return
            self._queued_data += 1
            if session_origin:
                self._session_origin = self._monotonic_clock()
            self._ensure_consumer_locked()

    def _ensure_consumer_locked(self) -> None:
        if not self._enabled:
            return
        if self._consumer is not None:
            return
        thread = threading.Thread(
            target=self._consumer_main,
            name="autobench-telemetry",
            daemon=True,
        )
        try:
            thread.start()
        except Exception:
            logger.debug("telemetry consumer start failed", exc_info=True)
            self._consumer = None
            return
        self._consumer = thread

    def _consumer_main(self) -> None:
        while True:
            try:
                item = self._queue.get(timeout=0.05)
            except queue.Empty:
                with self._lock:
                    if self._state is _State.CLOSED and self._queue.empty():
                        return
                continue
            try:
                if item.kind is _ItemKind.FLUSH:
                    self._flush_done.set()
                    continue
                if item.kind is _ItemKind.DATA:
                    with self._lock:
                        if self._queued_data > 0:
                            self._queued_data -= 1
                payload = item.payload
                if payload is None:
                    continue
                self._write_record(payload)
            except Exception:
                logger.debug("telemetry consumer item failed", exc_info=True)

    def _write_record(self, record: bytes) -> None:
        try:
            if self._writer_override is not None:
                self._writer_override(record)
                return
            self._default_write(record)
        except Exception:
            logger.debug("telemetry writer failed", exc_info=True)

    def _resolve_write_targets(self) -> tuple[WriterPaths, bool]:
        """Resolve (paths, shared_enabled) once; consumer-thread only."""
        if self._write_targets is None:
            shared_dir = (
                self._shared_dir if self._shared_dir is not None else DEFAULT_SHARED_DIR
            )
            paths = paths_for(
                self._identity,
                shared_dir,
                storage_root=self._storage_root,
            )
            shared_enabled = False
            if self._shared_config_ok and self._shared_dir is not None:
                try:
                    shared_enabled = bool(
                        shared_writer_supported(paths.shared_users_dir)
                    )
                except Exception:
                    logger.debug(
                        "telemetry shared capability check failed", exc_info=True
                    )
            self._write_targets = (paths, shared_enabled)
        return self._write_targets

    def _default_write(self, record: bytes) -> None:
        paths, shared_enabled = self._resolve_write_targets()
        append_record(
            record,
            identity=self._identity,
            paths=paths,
            shared_enabled=shared_enabled,
        )
