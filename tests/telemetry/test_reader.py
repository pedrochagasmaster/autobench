"""Tests for safe streaming telemetry reader source selection and validation."""

from __future__ import annotations

import json
import os
import socket
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from core.telemetry.constants import DEFAULT_DAYS, MAX_RECORD_BYTES
from core.telemetry.events import build_record
from core.telemetry.identity import Identity, encode_user_token
from core.telemetry.reader import (
    SourceKind,
    SourceSelection,
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


# ---------------------------------------------------------------------------
# Source selection
# ---------------------------------------------------------------------------


def test_select_sources_private_only_when_no_shared_jsonl(tmp_path: Path) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    (shared / "users").mkdir(parents=True)
    (shared / "users" / "subdir").mkdir()
    (shared / "users" / "notes.txt").write_text("x")
    storage = tmp_path / "ads"
    private = _write_private(storage, identity, _session_start())

    selection = _reader(tmp_path, identity=identity, shared_dir=shared, storage_root=storage).select_sources()

    assert selection == SourceSelection(kind=SourceKind.PRIVATE, paths=(private,))


def test_select_sources_prefers_shared_and_never_combines_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    storage = tmp_path / "ads"
    shared_path = _write_shared(shared, "alice", _session_start())
    _write_private(storage, identity, _session_start(session_id=SESSION_B))
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    selection = _reader(tmp_path, identity=identity, shared_dir=shared, storage_root=storage).select_sources()

    assert selection.kind is SourceKind.SHARED
    assert selection.paths == (shared_path,)
    events = list(
        _reader(tmp_path, identity=identity, shared_dir=shared, storage_root=storage).iter_events(
            days=None
        )
    )
    assert len(events) == 1
    assert events[0].session_id == str(SESSION_A)


def test_select_sources_falls_back_private_when_intermediate_ancestor_is_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    storage = tmp_path / "ads"
    private = _write_private(storage, identity, _session_start(session_id=SESSION_B))

    victim = tmp_path / "victim"
    victim.mkdir(mode=0o0755)
    link = tmp_path / "autobench"
    link.symlink_to(victim)
    shared = link / "telemetry"
    shared_path = _write_shared(shared, "alice", _session_start())
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    reader = _reader(
        tmp_path, identity=identity, shared_dir=shared, storage_root=storage
    )
    selection = reader.select_sources()

    assert selection.kind is SourceKind.PRIVATE
    assert selection.paths == (private,)
    events = list(reader.iter_events(days=None))
    assert len(events) == 1
    assert events[0].session_id == str(SESSION_B)
    # Shared content must not be selected/read via the intermediate symlink path.
    assert shared_path.exists()
    assert all(p != shared_path for p in selection.paths)


def test_select_sources_hostile_only_falls_back_to_private(
    tmp_path: Path,
) -> None:
    """Junk *.jsonl alone must not suppress private fallback (DoS)."""
    identity = _identity()
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    hostile = users / "not-a-valid-token.jsonl"
    hostile.write_bytes(_session_start())
    storage = tmp_path / "ads"
    private = _write_private(storage, identity, _session_start(session_id=SESSION_B))

    reader = _reader(
        tmp_path, identity=identity, shared_dir=shared, storage_root=storage
    )
    selection = reader.select_sources()

    assert selection.kind is SourceKind.PRIVATE
    assert selection.paths == (private,)
    events = list(reader.iter_events(days=None))
    assert len(events) == 1
    assert events[0].session_id == str(SESSION_B)


def test_select_sources_mixed_valid_and_hostile_shared_only_no_double_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    (users / "junk.jsonl").write_bytes(b"{not-json\n")
    valid = _write_shared(shared, "alice", _session_start())
    storage = tmp_path / "ads"
    _write_private(storage, identity, _session_start(session_id=SESSION_B))
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    reader = _reader(
        tmp_path, identity=identity, shared_dir=shared, storage_root=storage
    )
    selection = reader.select_sources()

    assert selection.kind is SourceKind.SHARED
    assert selection.paths == (valid,)
    events = list(reader.iter_events(days=None))
    assert len(events) == 1
    assert events[0].session_id == str(SESSION_A)


def test_select_sources_owner_token_mismatch_alone_falls_back_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    # Filename token for bob, record user alice → fails qualification.
    path = users / f"{encode_user_token('bob')}.jsonl"
    path.write_bytes(_session_start(user="alice"))
    storage = tmp_path / "ads"
    private = _write_private(storage, identity, _session_start(session_id=SESSION_B))
    monkeypatch.setattr(
        "core.telemetry.reader.lookup_uid",
        lambda username: identity.uid if username == "alice" else identity.uid + 1,
    )

    selection = _reader(
        tmp_path, identity=identity, shared_dir=shared, storage_root=storage
    ).select_sources()

    assert selection.kind is SourceKind.PRIVATE
    assert selection.paths == (private,)


def test_select_sources_sorted_qualifying_shared_excludes_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    bob = _write_shared(shared, "bob", _session_start(user="bob"))
    alice = _write_shared(shared, "alice", _session_start())
    link = users / "zzzz_link.jsonl"
    link.symlink_to(alice)
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    selection = _reader(tmp_path, identity=identity, shared_dir=shared).select_sources()

    assert selection.kind is SourceKind.SHARED
    assert selection.paths == tuple(sorted((alice, bob)))
    assert link not in selection.paths


def test_select_sources_user_absent_in_valid_fleet_returns_empty_shared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    storage = tmp_path / "ads"
    _write_shared(shared, "bob", _session_start(user="bob"))
    _write_private(storage, identity, _session_start(session_id=SESSION_B))
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    selection = _reader(
        tmp_path, identity=identity, shared_dir=shared, storage_root=storage
    ).select_sources(user="alice")

    assert selection.kind is SourceKind.SHARED
    assert selection.paths == ()
    events = list(
        _reader(
            tmp_path, identity=identity, shared_dir=shared, storage_root=storage
        ).iter_events(days=None, user="alice")
    )
    assert events == []


def test_select_sources_user_filter_only_if_qualifying_not_raw_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    # Raw username filename must never be selected by grammar alone.
    (users / "alice.jsonl").write_bytes(_session_start())
    expected = _write_shared(shared, "alice", _session_start())
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    selection = _reader(tmp_path, identity=identity, shared_dir=shared).select_sources(
        user="alice"
    )

    assert selection.kind is SourceKind.SHARED
    assert selection.paths == (expected,)
    assert (users / "alice.jsonl") not in selection.paths


def test_select_sources_user_with_only_raw_name_decoy_falls_back_private(
    tmp_path: Path,
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    (users / "alice.jsonl").write_bytes(_session_start())
    storage = tmp_path / "ads"
    private = _write_private(storage, identity, _session_start(session_id=SESSION_B))

    selection = _reader(
        tmp_path, identity=identity, shared_dir=shared, storage_root=storage
    ).select_sources(user="alice")

    assert selection.kind is SourceKind.PRIVATE
    assert selection.paths == (private,)


def test_qualification_closes_descriptors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    _write_shared(shared, "alice", _session_start())
    opened: list[int] = []
    closed: list[int] = []
    real_open = os.open
    real_close = os.close

    def spy_open(
        p: str | bytes | os.PathLike[str],
        flags: int,
        mode: int = 0o777,
        *args: Any,
        **kwargs: Any,
    ) -> int:
        fd = real_open(p, flags, mode, *args, **kwargs)
        opened.append(fd)
        return fd

    def spy_close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)
    monkeypatch.setattr("core.telemetry.reader.os.open", spy_open)
    monkeypatch.setattr("core.telemetry.reader.os.close", spy_close)

    _reader(tmp_path, identity=identity, shared_dir=shared).select_sources()

    assert opened
    assert closed == opened


def test_qualification_fifo_does_not_block(tmp_path: Path) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    fifo = users / "junk.jsonl"
    os.mkfifo(fifo)
    storage = tmp_path / "ads"
    private = _write_private(storage, identity, _session_start(session_id=SESSION_B))

    deadline = _deadline()
    selection = _reader(
        tmp_path, identity=identity, shared_dir=shared, storage_root=storage
    ).select_sources()
    _assert_before(deadline)

    assert selection.kind is SourceKind.PRIVATE
    assert selection.paths == (private,)


def test_select_sources_explicit_shared_dir_overrides_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    env_dir = tmp_path / "env_shared"
    _write_shared(env_dir, "alice", _session_start())
    explicit = tmp_path / "explicit"
    (explicit / "users").mkdir(parents=True)
    monkeypatch.setenv("AUTOBENCH_TELEMETRY_DIR", str(env_dir))

    selection = TelemetryReader(
        shared_dir=explicit,
        identity=identity,
        storage_root=tmp_path / "ads",
        now=FIXED_NOW,
    ).select_sources()

    assert selection.kind is SourceKind.PRIVATE


def test_select_sources_uses_env_when_shared_dir_omitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    env_dir = tmp_path / "env_shared"
    path = _write_shared(env_dir, "alice", _session_start())
    monkeypatch.setenv("AUTOBENCH_TELEMETRY_DIR", str(env_dir))
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    selection = TelemetryReader(
        identity=identity,
        storage_root=tmp_path / "ads",
        now=FIXED_NOW,
    ).select_sources()

    assert selection == SourceSelection(kind=SourceKind.SHARED, paths=(path,))


def test_select_sources_empty_env_falls_back_to_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    monkeypatch.setenv("AUTOBENCH_TELEMETRY_DIR", "   ")
    isolated_default = tmp_path / "isolated_default_shared"
    (isolated_default / "users").mkdir(parents=True)
    monkeypatch.setattr(
        "core.telemetry.reader.DEFAULT_SHARED_DIR", isolated_default
    )
    storage = tmp_path / "ads"
    private = _write_private(storage, identity, _session_start())

    selection = TelemetryReader(
        identity=identity,
        storage_root=storage,
        now=FIXED_NOW,
    ).select_sources()

    # Isolated empty default shared → private only; never touches real /ads_storage.
    assert selection.kind is SourceKind.PRIVATE
    assert selection.paths == (private,)


def test_select_sources_rejects_invalid_user(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _reader(tmp_path).select_sources(user="bad/name")


# ---------------------------------------------------------------------------
# Safe open
# ---------------------------------------------------------------------------


def test_required_open_flags_all_available() -> None:
    assert hasattr(os, "O_RDONLY")
    assert hasattr(os, "O_CLOEXEC")
    assert hasattr(os, "O_NONBLOCK")
    assert hasattr(os, "O_NOFOLLOW")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK | os.O_NOFOLLOW
    assert flags == READ_FLAGS


def test_open_uses_exact_flags_and_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    path = _write_shared(shared, "alice", _session_start())
    seen: dict[str, Any] = {}
    opened: list[int] = []
    closed: list[int] = []
    real_open = os.open
    real_close = os.close

    def spy_open(
        p: str | bytes | os.PathLike[str],
        flags: int,
        mode: int = 0o777,
        *args: Any,
        **kwargs: Any,
    ) -> int:
        seen["path"] = Path(os.fsdecode(p))
        seen["flags"] = flags
        fd = real_open(p, flags, mode, *args, **kwargs)
        opened.append(fd)
        return fd

    def spy_close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)
    monkeypatch.setattr("core.telemetry.reader.os.open", spy_open)
    monkeypatch.setattr("core.telemetry.reader.os.close", spy_close)

    events = list(
        _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(days=None)
    )

    assert len(events) == 1
    assert seen["path"] == path
    assert seen["flags"] == READ_FLAGS
    assert opened
    assert closed == opened


def test_rejects_symlink_under_deadline(tmp_path: Path) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    real = users / f"{encode_user_token('alice')}.jsonl"
    real.write_bytes(_session_start())
    link = users / "link.jsonl"
    link.symlink_to(real)
    # Only the symlink entry present as selection via user path override style:
    # list dir has both; force single symlink by user token path that is a symlink.
    link.unlink()
    token_link = users / f"{encode_user_token('alice')}.jsonl"
    real_file = tmp_path / "real.jsonl"
    real_file.write_bytes(_session_start())
    token_link.unlink()
    token_link.symlink_to(real_file)

    deadline = _deadline()
    events = list(
        _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(days=None)
    )
    _assert_before(deadline)
    assert events == []


def test_rejects_fifo_under_deadline(tmp_path: Path) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    fifo = users / f"{encode_user_token('alice')}.jsonl"
    os.mkfifo(fifo)

    deadline = _deadline()
    events = list(
        _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(days=None)
    )
    _assert_before(deadline)
    assert events == []


def test_rejects_directory_entry(tmp_path: Path) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    # A .jsonl-named directory should appear in selection then fail open/fstat.
    bad = users / "dir.jsonl"
    bad.mkdir()

    deadline = _deadline()
    events = list(
        _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(days=None)
    )
    _assert_before(deadline)
    assert events == []


def test_rejects_hardlink_nlink_gt_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    path = _write_shared(shared, "alice", _session_start())
    other = tmp_path / "other.jsonl"
    os.link(path, other)
    assert path.stat().st_nlink > 1

    deadline = _deadline()
    events = list(
        _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(days=None)
    )
    _assert_before(deadline)
    assert events == []

    # Also force via fstat stand-in when nlink cannot be created.
    path.unlink()
    other.unlink()
    path = _write_shared(shared, "alice", _session_start())
    real_fstat = os.fstat

    def fake_fstat(fd: int) -> SimpleNamespace:
        return _stat_standin(real_fstat(fd), nlink=2)

    monkeypatch.setattr("core.telemetry.reader.os.fstat", fake_fstat)
    assert list(
        _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(days=None)
    ) == []


def test_private_rejects_foreign_uid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    (shared / "users").mkdir(parents=True)
    storage = tmp_path / "ads"
    _write_private(storage, identity, _session_start())
    real_fstat = os.fstat
    opened: list[int] = []
    closed: list[int] = []
    real_open = os.open
    real_close = os.close

    def fake_fstat(fd: int) -> SimpleNamespace:
        return _stat_standin(real_fstat(fd), uid=identity.uid + 1)

    def spy_open(
        p: str | bytes | os.PathLike[str],
        flags: int,
        mode: int = 0o777,
        *args: Any,
        **kwargs: Any,
    ) -> int:
        fd = real_open(p, flags, mode, *args, **kwargs)
        opened.append(fd)
        return fd

    def spy_close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    monkeypatch.setattr("core.telemetry.reader.os.fstat", fake_fstat)
    monkeypatch.setattr("core.telemetry.reader.os.open", spy_open)
    monkeypatch.setattr("core.telemetry.reader.os.close", spy_close)

    events = list(
        _reader(
            tmp_path, identity=identity, shared_dir=shared, storage_root=storage
        ).iter_events(days=None)
    )
    assert events == []
    assert opened
    assert closed == opened


def test_close_errors_are_swallowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    _write_shared(shared, "alice", _session_start())
    real_close = os.close

    def boom_close(fd: int) -> None:
        real_close(fd)
        raise OSError(9, "bad")

    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)
    monkeypatch.setattr("core.telemetry.reader.os.close", boom_close)
    events = list(
        _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(days=None)
    )
    assert len(events) == 1


# ---------------------------------------------------------------------------
# Streaming / line isolation
# ---------------------------------------------------------------------------


def test_skips_oversized_line_and_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    good = _session_start(session_id=SESSION_B)
    oversized = (b"x" * MAX_RECORD_BYTES) + b"\n"
    path_bytes = oversized + good
    _write_shared(shared, "alice", path_bytes)
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    events = list(
        _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(days=None)
    )
    assert len(events) == 1
    assert events[0].session_id == str(SESSION_B)


def test_accepts_exact_max_record_bytes_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Splitter must accept an LF-terminated line of exactly MAX_RECORD_BYTES."""
    identity = _identity()
    shared = tmp_path / "shared"
    compact = _session_start(session_id=SESSION_A)
    body = compact[:-1]  # drop LF
    pad = MAX_RECORD_BYTES - 1 - len(body)
    assert pad > 0
    # JSON allows insignificant whitespace before the closing brace.
    exact = body[:-1] + (b" " * pad) + b"}\n"
    assert len(exact) == MAX_RECORD_BYTES
    _write_shared(shared, "alice", exact)
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    events = list(
        _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(days=None)
    )
    assert len(events) == 1
    assert events[0].session_id == str(SESSION_A)


def test_skips_multi_megabyte_incomplete_line_without_unbounded_buffers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Multi-MiB trailing bytes with no LF are discarded; prior valid event remains."""
    identity = _identity()
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    path = users / f"{encode_user_token('alice')}.jsonl"
    good = _session_start(session_id=SESSION_A)
    chunk = b"x" * 65_536
    megabytes = 2
    with path.open("wb") as fh:
        fh.write(good)
        for _ in range((megabytes * 1024 * 1024) // len(chunk)):
            fh.write(chunk)
        # Intentionally no trailing LF: incomplete multi-megabyte tail.
    assert path.stat().st_size > megabytes * 1024 * 1024
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    events = list(
        _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(days=None)
    )
    assert len(events) == 1
    assert events[0].session_id == str(SESSION_A)


def test_discards_incomplete_final_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    good = _session_start()
    # First complete event, then incomplete trailing bytes without LF.
    payload = good + b'{"schema_version":1,"ts":"2026-07-12T22:00:00Z"'
    _write_shared(shared, "alice", payload)
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    events = list(
        _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(days=None)
    )
    assert len(events) == 1


def test_malformed_lines_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    good = _session_start()
    payload = (
        b"\xff\xfe not utf8\n"
        + b"{not-json\n"
        + b'{"schema_version":1}\n'
        + good
    )
    _write_shared(shared, "alice", payload)
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    events = list(
        _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(days=None)
    )
    assert len(events) == 1


def test_unsupported_schema_warns_and_skips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    warnings: list[str] = []
    bad_obj = {
        "schema_version": 99,
        "ts": "2026-07-12T22:00:00Z",
        "event": "session_start",
        "user": "alice",
        "session_id": str(SESSION_A),
        "app_version": APP_VERSION,
        "props": {"launch_context": "tui"},
    }
    bad = (json.dumps(bad_obj, separators=(",", ":")) + "\n").encode("utf-8")
    good = _session_start(session_id=SESSION_B)
    _write_shared(shared, "alice", bad + good)
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    events = list(
        _reader(
            tmp_path, identity=identity, shared_dir=shared, warn=warnings.append
        ).iter_events(days=None)
    )
    assert len(events) == 1
    assert events[0].session_id == str(SESSION_B)
    assert len(warnings) == 1
    assert "schema" in warnings[0].lower() or "99" in warnings[0]


# ---------------------------------------------------------------------------
# Shared owner / token gate and private identity gate
# ---------------------------------------------------------------------------


def test_token_mismatch_rejects_whole_file_before_any_yield(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    # Filename token for bob, but record user is alice.
    path = users / f"{encode_user_token('bob')}.jsonl"
    path.write_bytes(_session_start(user="alice"))
    monkeypatch.setattr(
        "core.telemetry.reader.lookup_uid",
        lambda username: identity.uid if username == "alice" else identity.uid + 1,
    )
    yielded: list[Any] = []

    for event in _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(
        days=None
    ):
        yielded.append(event)

    assert yielded == []


def test_nss_owner_mismatch_rejects_whole_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    _write_shared(shared, "alice", _session_start())
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid + 99)

    assert list(
        _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(days=None)
    ) == []


def test_unresolvable_nss_rejects_whole_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    _write_shared(shared, "alice", _session_start())

    def boom(_username: str) -> int:
        raise KeyError("no such user")

    monkeypatch.setattr("core.telemetry.reader.lookup_uid", boom)
    assert list(
        _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(days=None)
    ) == []


def test_st_uid_mismatch_via_fstat_rejects_shared_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    _write_shared(shared, "alice", _session_start())
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)
    real_fstat = os.fstat

    def fake_fstat(fd: int) -> SimpleNamespace:
        return _stat_standin(real_fstat(fd), uid=identity.uid + 1)

    monkeypatch.setattr("core.telemetry.reader.os.fstat", fake_fstat)
    assert list(
        _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(days=None)
    ) == []


def test_old_first_record_can_validate_owner_before_date_filter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    old = FIXED_NOW - timedelta(days=100)
    recent = FIXED_NOW - timedelta(days=1)
    payload = _session_start(now=old) + _session_start(session_id=SESSION_B, now=recent)
    _write_shared(shared, "alice", payload)
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    events = list(
        _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(days=30)
    )
    assert len(events) == 1
    assert events[0].session_id == str(SESSION_B)


def test_later_forged_user_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    payload = _session_start(user="alice") + _session_start(
        user="mallory", session_id=SESSION_B
    )
    _write_shared(shared, "alice", payload)
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    events = list(
        _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(days=None)
    )
    assert len(events) == 1
    assert events[0].user == "alice"


def test_private_rejects_foreign_username_record(tmp_path: Path) -> None:
    identity = _identity("alice")
    shared = tmp_path / "shared"
    (shared / "users").mkdir(parents=True)
    storage = tmp_path / "ads"
    _write_private(storage, identity, _session_start(user="bob"))

    events = list(
        _reader(
            tmp_path, identity=identity, shared_dir=shared, storage_root=storage
        ).iter_events(days=None)
    )
    assert events == []


# ---------------------------------------------------------------------------
# Date / user filters
# ---------------------------------------------------------------------------


def test_inclusive_lower_bound_and_future_skew(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    boundary = FIXED_NOW - timedelta(days=30)
    inside = boundary
    just_outside = boundary - timedelta(seconds=1)
    future_ok = FIXED_NOW + timedelta(seconds=300)
    future_bad = FIXED_NOW + timedelta(seconds=301)
    payload = (
        _session_start(session_id=SESSION_A, now=just_outside)
        + _session_start(session_id=SESSION_B, now=inside)
        + _record(
            "surface_viewed",
            {"surface": "share"},
            session_id=SESSION_B,
            now=future_ok,
        )
        + _record(
            "surface_viewed",
            {"surface": "rate"},
            session_id=SESSION_B,
            now=future_bad,
        )
    )
    _write_shared(shared, "alice", payload)
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    events = list(
        _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(days=30)
    )
    assert [e.event for e in events] == ["session_start", "surface_viewed"]
    assert events[0].session_id == str(SESSION_B)
    assert events[1].props["surface"] == "share"


def test_days_none_has_no_lower_bound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    old = FIXED_NOW - timedelta(days=400)
    _write_shared(shared, "alice", _session_start(now=old))
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    events = list(
        _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(days=None)
    )
    assert len(events) == 1


def test_invalid_days_rejected(tmp_path: Path) -> None:
    reader = _reader(tmp_path)
    with pytest.raises(ValueError):
        list(reader.iter_events(days=-1))
    with pytest.raises(ValueError):
        list(reader.iter_events(days=1.5))  # type: ignore[arg-type]


def test_now_must_be_aware_utc(tmp_path: Path) -> None:
    identity = _identity()
    with pytest.raises(ValueError):
        TelemetryReader(
            shared_dir=tmp_path / "shared",
            identity=identity,
            storage_root=tmp_path / "ads",
            now=datetime(2026, 7, 12, 22, 0, 0),  # naive
        )
    with pytest.raises(ValueError):
        TelemetryReader(
            shared_dir=tmp_path / "shared",
            identity=identity,
            storage_root=tmp_path / "ads",
            now=datetime(2026, 7, 12, 22, 0, 0, tzinfo=timezone(timedelta(hours=1))),
        )


def test_user_filter_after_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    alice_path = users / f"{encode_user_token('alice')}.jsonl"
    bob_path = users / f"{encode_user_token('bob')}.jsonl"
    alice_path.write_bytes(_session_start(user="alice"))
    bob_path.write_bytes(_session_start(user="bob", session_id=SESSION_B))
    monkeypatch.setattr(
        "core.telemetry.reader.lookup_uid",
        lambda username: identity.uid,
    )

    events = list(
        _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(
            days=None, user="bob"
        )
    )
    assert len(events) == 1
    assert events[0].user == "bob"


def test_default_days_constant() -> None:
    assert DEFAULT_DAYS == 30


def test_socket_rejected_under_deadline(tmp_path: Path) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    sock_path = users / f"{encode_user_token('alice')}.jsonl"
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.bind(str(sock_path))
        deadline = _deadline()
        events = list(
            _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(days=None)
        )
        _assert_before(deadline)
        assert events == []
    finally:
        sock.close()
        if sock_path.exists():
            sock_path.unlink()
