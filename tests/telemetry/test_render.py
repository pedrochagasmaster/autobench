"""Tests for terminal-safe deterministic telemetry rendering."""

from __future__ import annotations

from datetime import datetime, timezone

from core.telemetry.reader import Summary, WhoRow
from core.telemetry.render import format_summary, format_who, sanitize_terminal

FIXED = datetime(2026, 7, 12, 22, 0, 0, tzinfo=timezone.utc)


def test_sanitize_removes_ansi_csi_and_osc() -> None:
    text = "hi\x1b[31mRED\x1b[0m\x1b]0;title\x07done"
    assert sanitize_terminal(text) == "hiREDdone"


def test_sanitize_preserves_printable_tab_newline_replaces_other() -> None:
    text = "ok\tline\n\x00\x1f\x7f café \u2022"
    assert sanitize_terminal(text) == "ok\tline\n??? caf? ?"


def test_format_who_empty_has_header_and_message() -> None:
    assert format_who([]) == (
        "USER\tSESSIONS\tLAST_SEEN\tCOMPLETED\n"
        "No telemetry events.\n"
    )


def test_format_who_golden_sorted_rows() -> None:
    rows = [
        WhoRow(user="alice", sessions=2, last_seen=FIXED, completed=3),
        WhoRow(
            user="bob",
            sessions=1,
            last_seen=datetime(2026, 7, 11, 8, 30, 15, tzinfo=timezone.utc),
            completed=0,
        ),
    ]
    assert format_who(rows) == (
        "USER\tSESSIONS\tLAST_SEEN\tCOMPLETED\n"
        "alice\t2\t2026-07-12T22:00:00Z\t3\n"
        "bob\t1\t2026-07-11T08:30:15Z\t0\n"
    )


def test_format_who_sanitizes_username() -> None:
    rows = [
        WhoRow(user="al\x1b[31mice", sessions=1, last_seen=FIXED, completed=0),
    ]
    out = format_who(rows)
    assert "\x1b" not in out
    assert out == (
        "USER\tSESSIONS\tLAST_SEEN\tCOMPLETED\n"
        "alice\t1\t2026-07-12T22:00:00Z\t0\n"
    )


def test_format_who_username_with_spaces_stays_one_column() -> None:
    rows = [
        WhoRow(user="svc account", sessions=1, last_seen=FIXED, completed=2),
    ]
    out = format_who(rows)
    row = out.splitlines()[1]
    assert row.split("\t") == ["svc account", "1", "2026-07-12T22:00:00Z", "2"]


def test_format_who_username_tab_newline_never_forge_columns() -> None:
    rows = [
        WhoRow(user="a\tb\nc", sessions=1, last_seen=FIXED, completed=0),
    ]
    out = format_who(rows)
    lines = out.splitlines()
    assert len(lines) == 2
    assert lines[1].split("\t") == ["a?b?c", "1", "2026-07-12T22:00:00Z", "0"]


def test_format_summary_golden_sections_and_order() -> None:
    summary = Summary(
        surfaces={"share": 2, "rate": 1},
        actions={"share_analysis": 4, "rate_analysis": 0},
        outcomes={"completed": 3, "cancelled": 1, "refused": 0, "failed": 2},
    )
    assert format_summary(summary) == (
        "Surfaces\n"
        "share  2\n"
        "rate  1\n"
        "\n"
        "Actions\n"
        "share_analysis  4\n"
        "rate_analysis  0\n"
        "\n"
        "Outcomes\n"
        "completed  3\n"
        "cancelled  1\n"
        "refused  0\n"
        "failed  2\n"
    )


def test_format_summary_zero_filled_empty() -> None:
    summary = Summary(
        surfaces={"share": 0, "rate": 0},
        actions={"share_analysis": 0, "rate_analysis": 0},
        outcomes={"completed": 0, "cancelled": 0, "refused": 0, "failed": 0},
    )
    assert format_summary(summary) == (
        "Surfaces\n"
        "share  0\n"
        "rate  0\n"
        "\n"
        "Actions\n"
        "share_analysis  0\n"
        "rate_analysis  0\n"
        "\n"
        "Outcomes\n"
        "completed  0\n"
        "cancelled  0\n"
        "refused  0\n"
        "failed  0\n"
    )
