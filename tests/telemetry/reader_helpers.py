"""Shared fixtures/helpers for the telemetry reader test modules."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID


from core.telemetry.events import build_record
from core.telemetry.identity import Identity, encode_user_token
from core.telemetry.reader import (
    TelemetryReader,
)

SESSION_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SESSION_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
FIXED_NOW = datetime(2026, 7, 12, 22, 0, 0, tzinfo=timezone.utc)
APP_VERSION = "3.0"
READ_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK | os.O_NOFOLLOW


def _identity(username: str = "alice", uid: int | None = None) -> Identity:
    return Identity(
        uid=os.geteuid() if uid is None else uid,
        username=username,
        token=encode_user_token(username),
    )


def _deadline(seconds: float = 2.0) -> float:
    return time.monotonic() + seconds


def _assert_before(deadline: float) -> None:
    assert time.monotonic() < deadline, "test exceeded deadline (possible hang)"


def _stat_standin(st: os.stat_result, *, uid: int | None = None, nlink: int | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        st_mode=st.st_mode,
        st_uid=st.st_uid if uid is None else uid,
        st_nlink=st.st_nlink if nlink is None else nlink,
        st_gid=st.st_gid,
        st_ino=st.st_ino,
        st_dev=st.st_dev,
        st_size=st.st_size,
    )


def _record(
    event: str,
    props: dict[str, object],
    *,
    user: str = "alice",
    session_id: UUID = SESSION_A,
    now: datetime = FIXED_NOW,
) -> bytes:
    return build_record(
        event,
        props,
        user=user,
        session_id=session_id,
        app_version=APP_VERSION,
        now=now,
    )


def _session_start(
    *,
    user: str = "alice",
    session_id: UUID = SESSION_A,
    now: datetime = FIXED_NOW,
) -> bytes:
    return _record(
        "session_start",
        {"launch_context": "tui"},
        user=user,
        session_id=session_id,
        now=now,
    )


def _write_shared(shared_dir: Path, username: str, *records: bytes) -> Path:
    users = shared_dir / "users"
    users.mkdir(parents=True, exist_ok=True)
    path = users / f"{encode_user_token(username)}.jsonl"
    path.write_bytes(b"".join(records))
    return path


def _write_private(storage_root: Path, identity: Identity, *records: bytes) -> Path:
    path = (
        storage_root
        / identity.username
        / ".autobench"
        / "telemetry"
        / "events.jsonl"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(records))
    return path


def _reader(
    tmp_path: Path,
    *,
    identity: Identity | None = None,
    shared_dir: Path | None = None,
    storage_root: Path | None = None,
    now: datetime | None = FIXED_NOW,
    warn: Any = None,
) -> TelemetryReader:
    ident = identity if identity is not None else _identity()
    return TelemetryReader(
        shared_dir=shared_dir if shared_dir is not None else tmp_path / "shared",
        identity=ident,
        storage_root=storage_root if storage_root is not None else tmp_path / "ads",
        now=now,
        warn=warn,
    )
