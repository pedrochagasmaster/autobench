"""Tests for telemetry who/summary aggregation models."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest

from core.telemetry.events import build_record
from core.telemetry.identity import Identity, encode_user_token
from core.telemetry.reader import Summary, TelemetryReader, WhoRow

SESSION_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SESSION_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
SESSION_C = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
FIXED_NOW = datetime(2026, 7, 12, 22, 0, 0, tzinfo=timezone.utc)
APP_VERSION = "3.0"


def _identity(username: str = "alice", uid: int | None = None) -> Identity:
    return Identity(
        uid=os.geteuid() if uid is None else uid,
        username=username,
        token=encode_user_token(username),
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


def _write_shared(shared_dir: Path, username: str, *records: bytes) -> Path:
    users = shared_dir / "users"
    users.mkdir(parents=True, exist_ok=True)
    path = users / f"{encode_user_token(username)}.jsonl"
    path.write_bytes(b"".join(records))
    return path


def _reader(
    tmp_path: Path,
    *,
    identity: Identity | None = None,
    shared_dir: Path | None = None,
) -> TelemetryReader:
    return TelemetryReader(
        shared_dir=shared_dir if shared_dir is not None else tmp_path / "shared",
        identity=identity if identity is not None else _identity(),
        storage_root=tmp_path / "ads",
        now=FIXED_NOW,
    )


@pytest.fixture
def patch_uid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "core.telemetry.reader.lookup_uid",
        lambda _u: os.geteuid(),
    )


def test_who_sessions_distinct_on_session_start_only(
    tmp_path: Path, patch_uid: None
) -> None:
    shared = tmp_path / "shared"
    t1 = FIXED_NOW - timedelta(hours=2)
    t2 = FIXED_NOW - timedelta(hours=1)
    payload = (
        _record("session_start", {"launch_context": "tui"}, session_id=SESSION_A, now=t1)
        + _record("session_start", {"launch_context": "cli_share"}, session_id=SESSION_A, now=t1)
        + _record("session_start", {"launch_context": "tui"}, session_id=SESSION_B, now=t2)
        + _record(
            "surface_viewed",
            {"surface": "share"},
            session_id=SESSION_C,
            now=FIXED_NOW,
        )
        + _record(
            "action_completed",
            {"action": "share_analysis"},
            session_id=SESSION_A,
            now=FIXED_NOW,
        )
    )
    _write_shared(shared, "alice", payload)

    rows = _reader(tmp_path).who(days=None)

    assert len(rows) == 1
    assert rows[0] == WhoRow(
        user="alice",
        sessions=2,
        last_seen=FIXED_NOW,
        completed=1,
    )


def test_who_last_seen_max_and_completions(
    tmp_path: Path, patch_uid: None
) -> None:
    shared = tmp_path / "shared"
    early = FIXED_NOW - timedelta(days=1)
    late = FIXED_NOW - timedelta(minutes=5)
    payload = (
        _record("session_start", {"launch_context": "tui"}, now=early)
        + _record(
            "action_completed",
            {"action": "share_analysis"},
            now=early,
        )
        + _record(
            "action_completed",
            {"action": "rate_analysis"},
            now=late,
        )
        + _record(
            "action_attempted",
            {"action": "share_analysis"},
            now=late,
        )
    )
    _write_shared(shared, "alice", payload)

    rows = _reader(tmp_path).who(days=None)
    assert rows[0].last_seen == late
    assert rows[0].completed == 2


def test_who_sorted_by_username(tmp_path: Path, patch_uid: None) -> None:
    shared = tmp_path / "shared"
    _write_shared(
        shared,
        "carol",
        _record("session_start", {"launch_context": "tui"}, user="carol"),
    )
    _write_shared(
        shared,
        "alice",
        _record("session_start", {"launch_context": "tui"}, user="alice"),
    )
    _write_shared(
        shared,
        "bob",
        _record("session_start", {"launch_context": "tui"}, user="bob"),
    )

    rows = _reader(tmp_path).who(days=None)
    assert [r.user for r in rows] == ["alice", "bob", "carol"]


def test_who_empty(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    (shared / "users").mkdir(parents=True)
    assert _reader(tmp_path).who(days=None) == []


def test_summary_zero_filled_and_fixed_key_order(
    tmp_path: Path, patch_uid: None
) -> None:
    shared = tmp_path / "shared"
    (shared / "users").mkdir(parents=True)
    summary = _reader(tmp_path).summary(days=None)

    assert isinstance(summary, Summary)
    assert list(summary.surfaces) == ["share", "rate"]
    assert list(summary.actions) == ["share_analysis", "rate_analysis"]
    assert list(summary.outcomes) == ["completed", "cancelled", "refused", "failed"]
    assert dict(summary.surfaces) == {"share": 0, "rate": 0}
    assert dict(summary.actions) == {"share_analysis": 0, "rate_analysis": 0}
    assert dict(summary.outcomes) == {
        "completed": 0,
        "cancelled": 0,
        "refused": 0,
        "failed": 0,
    }


def test_summary_counts_surfaces_actions_outcomes(
    tmp_path: Path, patch_uid: None
) -> None:
    shared = tmp_path / "shared"
    payload = (
        _record("session_start", {"launch_context": "tui"})
        + _record("surface_viewed", {"surface": "share"})
        + _record("surface_viewed", {"surface": "share"})
        + _record("surface_viewed", {"surface": "rate"})
        + _record("action_attempted", {"action": "share_analysis"})
        + _record("action_completed", {"action": "share_analysis"})
        + _record("action_cancelled", {"action": "rate_analysis"})
        + _record(
            "action_refused",
            {"action": "share_analysis", "reason": "configuration"},
        )
        + _record(
            "action_failed",
            {"action": "rate_analysis", "category": "input"},
        )
        + _record("action_attempted", {"action": "rate_analysis"})
    )
    _write_shared(shared, "alice", payload)

    summary = _reader(tmp_path).summary(days=None)

    assert dict(summary.surfaces) == {"share": 2, "rate": 1}
    # Every action_* event counted by action name.
    assert dict(summary.actions) == {"share_analysis": 3, "rate_analysis": 3}
    # attempted is not an outcome.
    assert dict(summary.outcomes) == {
        "completed": 1,
        "cancelled": 1,
        "refused": 1,
        "failed": 1,
    }


def test_summary_user_filter(tmp_path: Path, patch_uid: None) -> None:
    shared = tmp_path / "shared"
    _write_shared(
        shared,
        "alice",
        _record("surface_viewed", {"surface": "share"}, user="alice"),
    )
    _write_shared(
        shared,
        "bob",
        _record("surface_viewed", {"surface": "rate"}, user="bob"),
    )

    summary = _reader(tmp_path).summary(days=None, user="bob")
    assert dict(summary.surfaces) == {"share": 0, "rate": 1}
