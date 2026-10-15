"""Tests for telemetry who/summary aggregation models."""

from __future__ import annotations

import json
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
            {"action": "share_analysis", "publication_withheld": False},
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
            {"action": "share_analysis", "publication_withheld": False},
            now=early,
        )
        + _record(
            "action_completed",
            {"action": "rate_analysis", "publication_withheld": True},
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
    assert list(summary.surfaces) == [
        "share",
        "rate",
        "validation_review",
        "preset_help",
        "advanced",
    ]
    assert list(summary.actions) == ["share_analysis", "rate_analysis"]
    assert list(summary.outcomes) == ["completed", "cancelled", "refused", "failed"]
    assert set(summary.surfaces.values()) == {0}
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
        + _record(
            "action_completed",
            {"action": "share_analysis", "publication_withheld": False},
        )
        + _record(
            "action_cancelled",
            {"action": "rate_analysis", "prompt": "clearing_spend"},
        )
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

    assert summary.surfaces["share"] == 2
    assert summary.surfaces["rate"] == 1
    # Run intents, not raw action_* events: share = 1 attempt (its completed
    # and refused outcomes are not re-counted); rate = 1 pre-attempt cancel +
    # 1 attempt.
    assert dict(summary.actions) == {"share_analysis": 1, "rate_analysis": 2}
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
    assert summary.surfaces["share"] == 0
    assert summary.surfaces["rate"] == 1


def _legacy_v1(
    event: str,
    props: dict[str, object],
    *,
    user: str = "alice",
    session_id: UUID = SESSION_A,
    now: datetime = FIXED_NOW,
    schema_version: int = 1,
) -> bytes:
    """A record exactly as a schema-v1 (or, with ``schema_version``, v2) writer produced it."""
    payload = {
        "schema_version": schema_version,
        "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event": event,
        "user": user,
        "session_id": str(session_id),
        "app_version": "2.9",
        "props": props,
    }
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")


def test_new_reader_reads_mixed_v1_to_v4_file(tmp_path: Path, patch_uid: None) -> None:
    """An upgraded node appends v2, v3, then v4 records after its v1 history."""
    shared = tmp_path / "shared"
    early = FIXED_NOW - timedelta(days=3)
    middle = FIXED_NOW - timedelta(days=2)
    later = FIXED_NOW - timedelta(days=1)
    session_c = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    session_d = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

    def v2(event: str, props: dict[str, object]) -> bytes:
        return _legacy_v1(event, props, session_id=SESSION_B, now=middle, schema_version=2)

    def v3(event: str, props: dict[str, object]) -> bytes:
        return _legacy_v1(event, props, session_id=session_c, now=later, schema_version=3)

    payload = (
        _legacy_v1("session_start", {"launch_context": "tui"}, now=early)
        + _legacy_v1("action_cancelled", {"action": "share_analysis"}, now=early)
        + _legacy_v1("action_attempted", {"action": "share_analysis"}, now=early)
        + _legacy_v1("action_completed", {"action": "share_analysis"}, now=early)
        # A v2 writer also stamped session_start as v1 (LEGACY_WRITE_EVENTS).
        + _legacy_v1("session_start", {"launch_context": "tui"}, session_id=SESSION_B, now=middle)
        + v2("launch_blocked", {"action": "share_analysis", "reason": "metric_missing"})
        + v2("action_attempted", {"action": "share_analysis"})
        + v2("action_completed", {"action": "share_analysis", "publication_withheld": True})
        + _legacy_v1("session_start", {"launch_context": "tui"}, session_id=session_c, now=later)
        + v3("launch_blocked", {"action": "share_analysis", "reason": "entity_not_found"})
        + v3("action_cancelled", {"action": "share_analysis", "prompt": "cancel_before_run"})
        + v3("action_attempted", {"action": "share_analysis"})
        + v3("action_cancelled", {"action": "share_analysis", "prompt": "cancel_during_run"})
        + _record("session_start", {"launch_context": "tui"}, session_id=session_d)
        + _record(
            "launch_blocked",
            {"action": "rate_analysis", "reason": "citi_entity_missing"},
            session_id=session_d,
        )
        + _record("action_attempted", {"action": "rate_analysis"}, session_id=session_d)
        + _record(
            "action_completed",
            {"action": "rate_analysis", "publication_withheld": False},
            session_id=session_d,
        )
    )
    _write_shared(shared, "alice", payload)
    warnings: list[str] = []
    reader = TelemetryReader(
        shared_dir=shared,
        identity=_identity(),
        storage_root=tmp_path / "ads",
        now=FIXED_NOW,
        warn=warnings.append,
    )

    events = list(reader.iter_events(days=None))
    # session_start is still written as v1 (LEGACY_WRITE_EVENTS).
    assert [e.schema_version for e in events] == [1, 1, 1, 1, 1, 2, 2, 2, 1, 3, 3, 3, 3, 1, 4, 4, 4]
    assert warnings == []

    summary = reader.summary(days=None)
    # v1: cancel (pre-attempt) + attempt; v2: block + attempt; v3: block +
    # pre-attempt cancel + attempt. The in-run cancel ends an attempt.
    assert summary.actions["share_analysis"] == 7
    # v4: the Citibank readiness block + attempt.
    assert summary.actions["rate_analysis"] == 2
    assert summary.outcomes["completed"] == 3
    assert reader.who(days=None)[0].completed == 3
