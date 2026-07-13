"""Reader streaming, line isolation, and scan-budget tests."""

from __future__ import annotations

import json
import os
from datetime import timedelta
from pathlib import Path

import pytest

from core.telemetry.constants import (
    MAX_RECORD_BYTES,
    SHARED_GATE_SCAN_MAX_BYTES,
)
from core.telemetry.identity import encode_user_token
from core.telemetry.reader import (
    SourceKind,
)

from tests.telemetry.reader_helpers import (
    APP_VERSION,
    FIXED_NOW,
    SESSION_A,
    SESSION_B,
    _assert_before,
    _deadline,
    _identity,
    _reader,
    _session_start,
    _write_private,
    _write_shared,
)

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


def test_pre_gate_budget_stops_multi_mib_invalid_lf_and_falls_back_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    # Token-shaped name but only invalid LF lines (never a schema-valid gate event).
    path = users / f"{encode_user_token('alice')}.jsonl"
    junk_line = b"x" * 100 + b"\n"
    with path.open("wb") as fh:
        for _ in range((2 * 1024 * 1024) // len(junk_line)):
            fh.write(junk_line)
    storage = tmp_path / "ads"
    private = _write_private(storage, identity, _session_start(session_id=SESSION_B))

    read_total = {"n": 0}
    real_read = os.read

    def spy_read(fd: int, n: int) -> bytes:
        data = real_read(fd, n)
        read_total["n"] += len(data)
        return data

    monkeypatch.setattr("core.telemetry.reader.os.read", spy_read)
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    deadline = _deadline(2.0)
    reader = _reader(
        tmp_path, identity=identity, shared_dir=shared, storage_root=storage
    )
    selection = reader.select_sources()
    _assert_before(deadline)

    assert selection.kind is SourceKind.PRIVATE
    assert selection.paths == (private,)
    assert read_total["n"] <= SHARED_GATE_SCAN_MAX_BYTES
    assert path.stat().st_size > 2 * SHARED_GATE_SCAN_MAX_BYTES


def test_pre_gate_budget_stops_multi_mib_no_lf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    path = users / f"{encode_user_token('alice')}.jsonl"
    chunk = b"y" * 65_536
    with path.open("wb") as fh:
        for _ in range((2 * 1024 * 1024) // len(chunk)):
            fh.write(chunk)
    storage = tmp_path / "ads"
    private = _write_private(storage, identity, _session_start(session_id=SESSION_B))

    read_total = {"n": 0}
    real_read = os.read

    def spy_read(fd: int, n: int) -> bytes:
        data = real_read(fd, n)
        read_total["n"] += len(data)
        return data

    monkeypatch.setattr("core.telemetry.reader.os.read", spy_read)

    deadline = _deadline(2.0)
    selection = _reader(
        tmp_path, identity=identity, shared_dir=shared, storage_root=storage
    ).select_sources()
    _assert_before(deadline)

    assert selection.kind is SourceKind.PRIVATE
    assert selection.paths == (private,)
    assert read_total["n"] <= SHARED_GATE_SCAN_MAX_BYTES


def test_iter_path_pre_gate_budget_on_replaced_junk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-gate after reopen must also stop within the physical byte budget."""
    identity = _identity()
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    path = users / f"{encode_user_token('alice')}.jsonl"
    junk_line = b"z" * 80 + b"\n"
    with path.open("wb") as fh:
        for _ in range((3 * 1024 * 1024) // len(junk_line)):
            fh.write(junk_line)

    read_total = {"n": 0}
    real_read = os.read

    def spy_read(fd: int, n: int) -> bytes:
        data = real_read(fd, n)
        read_total["n"] += len(data)
        return data

    monkeypatch.setattr("core.telemetry.reader.os.read", spy_read)
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    reader = _reader(tmp_path, identity=identity, shared_dir=shared)
    deadline = _deadline(2.0)
    events = list(
        reader._iter_path(
            path,
            kind=SourceKind.SHARED,
            lower=None,
            upper=FIXED_NOW + timedelta(seconds=300),
            user_filter=None,
        )
    )
    _assert_before(deadline)

    assert events == []
    assert read_total["n"] <= SHARED_GATE_SCAN_MAX_BYTES


def test_gate_budget_lifts_after_valid_event_preserves_later_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Valid gate near (but inside) budget; later events beyond budget still yield."""
    identity = _identity()
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    path = users / f"{encode_user_token('alice')}.jsonl"

    pad_line = b"{not-json}\n"
    pad_count = (SHARED_GATE_SCAN_MAX_BYTES - 512) // len(pad_line)
    assert pad_count > 0
    gate = _session_start(session_id=SESSION_A)
    later = _session_start(session_id=SESSION_B)
    # Extra padding after gate so post-gate content exceeds the original budget.
    post_pad = pad_line * ((SHARED_GATE_SCAN_MAX_BYTES // len(pad_line)) + 10)

    with path.open("wb") as fh:
        for _ in range(pad_count):
            fh.write(pad_line)
        fh.write(gate)
        fh.write(post_pad)
        fh.write(later)

    pre_gate_bytes = pad_count * len(pad_line) + len(gate)
    assert pre_gate_bytes <= SHARED_GATE_SCAN_MAX_BYTES
    assert path.stat().st_size > SHARED_GATE_SCAN_MAX_BYTES

    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    events = list(
        _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(days=None)
    )
    assert [e.session_id for e in events] == [str(SESSION_A), str(SESSION_B)]


def test_shared_gate_scan_max_bytes_constant() -> None:
    assert SHARED_GATE_SCAN_MAX_BYTES == 64 * 1024


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


