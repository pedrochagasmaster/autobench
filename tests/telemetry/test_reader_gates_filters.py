"""Reader owner/token gates, identity gates, and date/user filter tests."""

from __future__ import annotations

import os
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from core.telemetry.constants import (
    DEFAULT_DAYS,
)
from core.telemetry.identity import encode_user_token
from core.telemetry.reader import (
    TelemetryReader,
)

from tests.telemetry.reader_helpers import (
    FIXED_NOW,
    SESSION_A,
    SESSION_B,
    _assert_before,
    _deadline,
    _identity,
    _reader,
    _record,
    _session_start,
    _stat_standin,
    _write_private,
    _write_shared,
)

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


@pytest.mark.parametrize(
    "huge_days",
    [
        999_999_999,  # timedelta accepts it; datetime subtraction overflows
        999_999_999_999,  # timedelta construction itself overflows
    ],
)
def test_huge_days_treated_as_unlimited(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, huge_days: int
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    old = FIXED_NOW - timedelta(days=400)
    _write_shared(shared, "alice", _session_start(now=old))
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    events = list(
        _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(
            days=huge_days
        )
    )
    assert len(events) == 1


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
