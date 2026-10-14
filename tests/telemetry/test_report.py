"""Tests for the read-only breakdown reports (funnel, reasons, surfaces, durations)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest

import benchmark
from core.telemetry import report
from core.telemetry.events import build_record, decode_record
from core.telemetry.identity import encode_user_token
from core.telemetry.reader import TelemetryReader
from core.telemetry.render import (
    format_breakdown,
    format_durations,
    format_friction,
    format_funnel,
    format_surfaces,
)

FIXED_NOW = datetime(2026, 7, 12, 22, 0, 0, tzinfo=timezone.utc)
S1 = UUID("11111111-1111-1111-1111-111111111111")
S2 = UUID("22222222-2222-2222-2222-222222222222")
S3 = UUID("33333333-3333-3333-3333-333333333333")


def _rec(
    event: str,
    props: dict[str, object],
    *,
    session: UUID = S1,
    at: float = 0.0,
    user: str = "alice",
    app_version: str = "3.0",
) -> bytes:
    return build_record(
        event,
        props,
        user=user,
        session_id=session,
        app_version=app_version,
        now=FIXED_NOW - timedelta(hours=1) + timedelta(seconds=at),
    )


def _v1(event: str, props: dict[str, object], *, session: UUID, at: float = 0.0) -> bytes:
    ts = FIXED_NOW - timedelta(hours=2) + timedelta(seconds=at)
    payload = {
        "schema_version": 1,
        "ts": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event": event,
        "user": "alice",
        "session_id": str(session),
        "app_version": "2.9",
        "props": props,
    }
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")


SHARE = {"action": "share_analysis"}
RATE = {"action": "rate_analysis"}


def _tui_session() -> list[bytes]:
    """One TUI session exercising every pre-attempt and post-attempt path."""
    return [
        _rec("session_start", {"launch_context": "tui"}, at=0),
        _rec("session_restored", {}, at=0.1),
        _rec("surface_viewed", {"surface": "share"}, at=0.2),
        _rec("dataset_load", {"outcome": "not_found"}, at=5),
        _rec("dataset_load", {"outcome": "loaded"}, at=10),
        _rec("launch_blocked", {**SHARE, "reason": "metric_missing"}, at=20),
        _rec("surface_viewed", {"surface": "validation_review"}, at=30),
        _rec("launch_blocked", {**SHARE, "reason": "validation_errors"}, at=42),
        _rec("surface_viewed", {"surface": "validation_review"}, at=50),
        _rec("action_cancelled", {**SHARE, "prompt": "validation_review"}, at=53),
        _rec("surface_viewed", {"surface": "validation_review"}, at=60),
        _rec("action_attempted", SHARE, at=70),
        _rec("action_completed", {**SHARE, "publication_withheld": True}, at=80),
        _rec("action_attempted", SHARE, at=90),
        _rec("action_refused", {**SHARE, "reason": "input_validation"}, at=95),
        _rec("surface_viewed", {"surface": "rate"}, at=100),
        _rec("action_cancelled", {**RATE, "prompt": "clearing_spend"}, at=110),
        _rec("action_attempted", RATE, at=120),
        _rec("action_failed", {**RATE, "category": "analysis"}, at=130),
        _rec("action_attempted", RATE, at=140),
        _rec("action_cancelled", {**RATE, "prompt": "quit_during_run"}, at=150),
        _rec("advanced_override", {"outcome": "applied"}, at=155),
        _rec("session_end", {"duration_s": 160.0}, at=160),
    ]


def _cli_session() -> list[bytes]:
    return [
        _rec("session_start", {"launch_context": "cli_share"}, session=S2, at=0),
        _rec("action_attempted", SHARE, session=S2, at=1),
        _rec("action_completed", {**SHARE, "publication_withheld": False}, session=S2, at=9),
        _rec("session_end", {"duration_s": 10.0}, session=S2, at=10),
    ]


def _legacy_session() -> list[bytes]:
    return [
        _v1("session_start", {"launch_context": "tui"}, session=S3, at=0),
        _v1("action_cancelled", SHARE, session=S3, at=5),
        _v1("action_attempted", SHARE, session=S3, at=10),
        _v1("action_completed", SHARE, session=S3, at=20),
        _v1("action_attempted", SHARE, session=S3, at=30),  # open: process died
    ]


def _sessions(*chunks: list[bytes]) -> list[report.Session]:
    return report.group_sessions(decode_record(raw) for chunk in chunks for raw in chunk)


def test_funnel_counts_every_intent_once_and_ends_each_attempt() -> None:
    rows = {r.action: r for r in report.funnel(_sessions(_tui_session(), _cli_session()))}
    share, rate = rows["share_analysis"], rows["rate_analysis"]
    assert (share.blocked, share.cancelled_before_run, share.attempted) == (2, 1, 3)
    assert share.intents == 6
    assert (share.completed, share.withheld, share.unflagged) == (2, 1, 0)
    assert (share.refused, share.failed, share.cancelled_during_run, share.open) == (1, 0, 0, 0)
    assert (rate.blocked, rate.cancelled_before_run, rate.attempted) == (0, 1, 2)
    assert rate.intents == 3
    assert (rate.failed, rate.cancelled_during_run, rate.open) == (1, 1, 0)


def test_funnel_on_v1_data_treats_cancels_as_pre_attempt_and_flags_unflagged() -> None:
    (share, _rate) = report.funnel(_sessions(_legacy_session()))
    assert share.cancelled_before_run == 1
    assert share.attempted == 2
    assert share.intents == 3
    assert share.completed == 1
    assert share.unflagged == 1
    assert share.withheld == 0
    assert share.open == 1
    text = format_funnel([share, _rate])
    assert "1 completion(s) predate schema v2" in text


def test_reason_breakdowns() -> None:
    sessions = _sessions(_tui_session())
    refused = report.refusals(sessions)
    assert refused.total("input_validation") == 1
    assert refused.total("compliance_policy") == 0
    failed = report.failures(sessions)
    assert failed.counts == {("analysis", "rate_analysis"): 1}
    blocks = report.launch_blocks(sessions)
    assert blocks.total("metric_missing") == 1
    assert blocks.total("validation_errors") == 1
    cancels = report.cancels(_sessions(_tui_session(), _legacy_session()))
    assert cancels.total("validation_review") == 1
    assert cancels.total("clearing_spend") == 1
    assert cancels.total("quit_during_run") == 1
    assert cancels.total(report.UNRECORDED_PROMPT) == 1
    text = format_breakdown("Launch blocks", blocks)
    assert "metric_missing" in text and "total" in text


def test_surfaces_and_durations() -> None:
    sessions = _sessions(_tui_session(), _cli_session(), _legacy_session())
    usage = report.surfaces(sessions)
    assert usage.views["validation_review"] == 3
    assert usage.tui_sessions == 2
    assert usage.tui_sessions_viewing["share"] == 1
    assert usage.tui_sessions_both_tabs == 1
    assert usage.launch_contexts == {"cli_share": 1, "cli_rate": 0, "tui": 2}
    assert "validation_review" in format_surfaces(usage)

    result = report.durations(sessions)
    by_label = {row.label: row for row in result.rows}
    assert by_label["all"].n == 2
    assert by_label["tui"].p50 == 160.0
    assert by_label["cli_rate"].n == 0
    assert result.without_end == 1
    text = format_durations(result)
    assert "Sessions without session_end (crash, kill or drop): 1" in text


def test_friction_derived_metrics() -> None:
    sessions = _sessions(_tui_session(), _legacy_session())
    result = report.friction(sessions)
    assert result.tui_sessions == 2
    assert result.no_intent_sessions == 0
    assert result.restored_sessions == 1
    assert result.validation_review_outcomes == {
        "proceeded": 1,
        "cancelled": 1,
        "blocked": 1,
        "no_decision": 0,
    }
    assert result.validation_review_dwell.n == 3
    assert result.validation_review_dwell.p50 == 10.0
    assert result.dataset_loads["not_found"] == 1
    assert result.advanced_overrides["applied"] == 1
    assert result.time_to_first_intent.n == 2
    assert result.recovered_sessions == 2
    assert "Time in validation review: n=3" in format_friction(result)


def test_context_and_app_version_filters() -> None:
    sessions = _sessions(_tui_session(), _cli_session(), _legacy_session())
    assert len(report.filter_sessions(sessions, context="tui")) == 2
    assert len(report.filter_sessions(sessions, context="tui", app_version="2.9")) == 1
    assert len(report.filter_sessions(sessions, app_version="3.0")) == 2


def test_ratio_flags_small_denominators() -> None:
    rows = report.funnel(_sessions(_cli_session()))
    text = format_funnel(rows)
    assert "100%*" in text  # 1/1, flagged: denominator under 30


# --------------------------------------------------------------------- CLI


def _write_store(tmp_path: Path) -> Path:
    users = tmp_path / "store" / "users"
    users.mkdir(parents=True)
    path = users / f"{encode_user_token('alice')}.jsonl"
    path.write_bytes(b"".join(_legacy_session() + _tui_session() + _cli_session()))
    return tmp_path / "store"


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv("AUTOBENCH_TELEMETRY_DIR", raising=False)
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: os.geteuid())
    ads = tmp_path / "ads"
    ads.mkdir()
    real_cls = TelemetryReader

    def factory(*args: object, **kwargs: object) -> TelemetryReader:
        kwargs.setdefault("storage_root", ads)
        kwargs.setdefault("now", FIXED_NOW)
        return real_cls(*args, **kwargs)

    monkeypatch.setattr(benchmark, "TelemetryReader", factory)
    return _write_store(tmp_path)


@pytest.mark.parametrize("command", sorted(benchmark.TELEMETRY_BREAKDOWN_COMMANDS))
def test_cli_breakdown_commands_run_read_only(
    store: Path,
    command: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    started: list[object] = []
    monkeypatch.setattr(benchmark, "start_session", lambda *a: started.append(a))
    monkeypatch.setattr("sys.argv", ["benchmark.py", "telemetry", command, "--dir", str(store)])
    code = benchmark.main()
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert captured.out.startswith("window=30d  source=shared  users=1  sessions=3")
    assert started == []
    # Breakdown output never names users, paths or anything outside the vocab.
    assert "alice" not in captured.out
    assert str(store) not in captured.out
    assert captured.err == ""


def test_cli_funnel_context_filter_and_header(
    store: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "benchmark.py", "telemetry", "funnel", "--dir", str(store),
            "--context", "cli_share", "--app-version", "3.0",
        ],
    )
    assert benchmark.main() == 0
    out = capsys.readouterr().out
    assert "sessions=1" in out
    assert "context=cli_share" in out and "app_version=3.0" in out
    share_line = next(line for line in out.splitlines() if line.startswith("share_analysis"))
    assert share_line.split()[1:5] == ["1", "0", "0", "1"]


@pytest.mark.parametrize("command", ["who", "summary", "funnel"])
def test_cli_copied_store_warns_and_reports_private_source(
    store: Path,
    command: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The silent private fallback is now an explicit stderr warning."""
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: os.geteuid() + 1)
    monkeypatch.setattr("sys.argv", ["benchmark.py", "telemetry", command, "--dir", str(store)])
    assert benchmark.main() == 0
    captured = capsys.readouterr()
    assert captured.err.startswith("WARNING: no shared telemetry file in ")
    assert "owner_mismatch=1" in captured.err
    assert "alice" not in captured.err
    if command == "funnel":
        assert "source=private" in captured.out


def test_cli_rejects_bad_app_version_and_context(
    store: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["benchmark.py", "telemetry", "funnel", "--dir", str(store), "--app-version", "bad\x1bversion"],
    )
    assert benchmark.main() == 1
    assert "app-version" in capsys.readouterr().err
    monkeypatch.setattr(
        "sys.argv",
        ["benchmark.py", "telemetry", "funnel", "--dir", str(store), "--context", "web"],
    )
    with pytest.raises(SystemExit):
        benchmark.main()
