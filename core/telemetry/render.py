"""Terminal-safe deterministic telemetry report rendering."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from collections.abc import Sequence

from core.telemetry.constants import ACTIONS, OUTCOMES, SURFACES
from core.telemetry.reader import Summary, WhoRow
from core.telemetry.report import (
    MIN_RATIO_DENOMINATOR,
    Breakdown,
    Durations,
    Friction,
    FunnelRow,
    ReportHeader,
    SurfaceUsage,
    TimingStats,
)

# CSI: ESC [ params final; OSC: ESC ] ... BEL or ST (ESC \)
_ANSI_RE = re.compile(
    r"(?:"
    r"\x1b\[[0-?]*[ -/]*[@-~]"  # CSI
    r"|"
    r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC
    r")"
)


def sanitize_terminal(text: str) -> str:
    """Remove ANSI CSI/OSC, keep printable ASCII plus tab/newline; else '?'."""
    if not isinstance(text, str):
        text = str(text)
    cleaned = _ANSI_RE.sub("", text)
    out: list[str] = []
    for ch in cleaned:
        code = ord(ch)
        if ch in {"\n", "\t"}:
            out.append(ch)
        elif 32 <= code <= 126:
            out.append(ch)
        else:
            out.append("?")
    return "".join(out)


def _format_ts(ts: datetime) -> str:
    utc = ts.astimezone(timezone.utc).replace(microsecond=0)
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def _user_cell(user: str) -> str:
    """Sanitize a username cell; tab/newline would forge column structure."""
    cleaned = sanitize_terminal(user)
    return cleaned.replace("\t", "?").replace("\n", "?")


def format_who(rows: list[WhoRow]) -> str:
    # Tab-separated: validated usernames may contain spaces but never tabs,
    # so rows stay unambiguously parseable (e.g. cut -f1).
    lines = ["USER\tSESSIONS\tLAST_SEEN\tCOMPLETED"]
    if not rows:
        lines.append("No telemetry events.")
    else:
        for row in rows:
            lines.append(
                f"{_user_cell(row.user)}\t{row.sessions}"
                f"\t{_format_ts(row.last_seen)}\t{row.completed}"
            )
    return "\n".join(lines) + "\n"


def format_summary(summary: Summary) -> str:
    sections: list[str] = []

    surface_lines = ["Surfaces"]
    for key in SURFACES:
        surface_lines.append(f"{key}  {int(summary.surfaces.get(key, 0))}")
    sections.append("\n".join(surface_lines))

    action_lines = ["Actions (run intents)"]
    for key in ACTIONS:
        action_lines.append(f"{key}  {int(summary.actions.get(key, 0))}")
    sections.append("\n".join(action_lines))

    outcome_lines = ["Outcomes"]
    for key in OUTCOMES:
        outcome_lines.append(f"{key}  {int(summary.outcomes.get(key, 0))}")
    sections.append("\n".join(outcome_lines))

    return "\n\n".join(sections) + "\n"


# ------------------------------------------------------- breakdown reports
#
# Every cell below is an int, a closed vocabulary value or a fixed label. The
# only operator-supplied values (header filters) are sanitized.


def _ratio(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "-"
    flag = "*" if denominator < MIN_RATIO_DENOMINATOR else ""
    return f"{numerator / denominator:.0%}{flag}"


def _table(header: Sequence[str], rows: Sequence[Sequence[object]]) -> list[str]:
    cells = [list(header)] + [[str(cell) for cell in row] for row in rows]
    widths = [max(len(row[i]) for row in cells) for i in range(len(header))]
    lines = []
    for row in cells:
        first = row[0].ljust(widths[0])
        rest = [cell.rjust(widths[i + 1]) for i, cell in enumerate(row[1:])]
        lines.append("  ".join([first, *rest]).rstrip())
    return lines


def format_report_header(header: ReportHeader) -> str:
    window = "all" if header.days is None else f"{int(header.days)}d"
    parts = [
        f"window={window}",
        f"source={header.source}",
        f"users={header.scope.users}",
        f"sessions={header.scope.sessions}",
        f"events={header.scope.events}",
    ]
    for key, value in header.filters.items():
        parts.append(f"{key}={_user_cell(str(value)).replace(' ', '?')}")
    return "  ".join(parts) + "\n"


def format_funnel(rows: Sequence[FunnelRow]) -> str:
    table_rows = []
    totals = [0] * 10
    for row in rows:
        values = [
            row.intents,
            row.blocked,
            row.cancelled_before_run,
            row.attempted,
            row.completed,
            row.withheld,
            row.refused,
            row.failed,
            row.cancelled_during_run,
            row.open,
        ]
        totals = [a + b for a, b in zip(totals, values)]
        table_rows.append(
            [row.action, *values, _ratio(row.completed, row.intents), _ratio(row.completed, row.attempted)]
        )
    table_rows.append(["all", *totals, _ratio(totals[4], totals[0]), _ratio(totals[4], totals[3])])
    lines = ["Funnel per action (intents = blocked + cancelled + attempted)"]
    lines += _table(
        (
            "ACTION",
            "INTENTS",
            "BLOCKED",
            "CANCELLED",
            "ATTEMPTED",
            "COMPLETED",
            "WITHHELD",
            "REFUSED",
            "FAILED",
            "QUIT_IN_RUN",
            "OPEN",
            "SUCCESS",
            "PER_ATTEMPT",
        ),
        table_rows,
    )
    unflagged = sum(row.unflagged for row in rows)
    lines.append("")
    lines.append(
        "BLOCKED and CANCELLED happen before any attempt; WITHHELD is the part of "
        "COMPLETED whose publication a strict posture withheld."
    )
    lines.append(
        "SUCCESS = COMPLETED / INTENTS; PER_ATTEMPT = COMPLETED / ATTEMPTED; "
        f"* marks a denominator under {MIN_RATIO_DENOMINATOR}."
    )
    if unflagged:
        lines.append(
            f"{unflagged} completion(s) predate schema v2 and carry no "
            "publication_withheld flag (counted in COMPLETED, not in WITHHELD)."
        )
    return "\n".join(lines) + "\n"


def format_breakdown(title: str, breakdown: Breakdown, *, label: str = "REASON") -> str:
    rows = []
    for key in breakdown.keys:
        counts = [breakdown.counts.get((key, action), 0) for action in ACTIONS]
        rows.append([key, *counts, sum(counts)])
    totals = [sum(breakdown.counts.get((k, a), 0) for k in breakdown.keys) for a in ACTIONS]
    rows.append(["total", *totals, sum(totals)])
    lines = [title, *_table((label, *[a.upper() for a in ACTIONS], "TOTAL"), rows)]
    return "\n".join(lines) + "\n"


def format_surfaces(usage: SurfaceUsage) -> str:
    rows = [
        [key, usage.views.get(key, 0), f"{usage.tui_sessions_viewing.get(key, 0)}/{usage.tui_sessions}"]
        for key in SURFACES
    ]
    lines = ["Surface usage", *_table(("SURFACE", "VIEWS", "TUI_SESSIONS_VIEWING"), rows)]
    lines.append("")
    lines.append(
        f"TUI sessions viewing both tabs: {usage.tui_sessions_both_tabs}/{usage.tui_sessions}"
    )
    contexts = "  ".join(f"{key}={count}" for key, count in usage.launch_contexts.items())
    lines.append(f"Launch contexts: {contexts}  unknown={usage.unknown_context_sessions}")
    return "\n".join(lines) + "\n"


def _seconds(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}"


def format_durations(result: Durations) -> str:
    rows = [
        [r.label, r.n, _seconds(r.p10), _seconds(r.p50), _seconds(r.p90), _seconds(r.max)]
        for r in result.rows
    ]
    lines = [
        "Session duration (session_end.duration_s, seconds)",
        *_table(("CONTEXT", "N", "P10", "P50", "P90", "MAX"), rows),
        "",
    ]
    for label, bins in result.histogram.items():
        cells = "  ".join(f"{name}={count}" for name, count in bins)
        lines.append(f"{label} histogram: {cells}")
    lines.append(f"Sessions without session_end (crash, kill or drop): {result.without_end}")
    return "\n".join(lines) + "\n"


def _timing_line(label: str, stats: TimingStats) -> str:
    if stats.n == 0:
        return f"{label}: n=0"
    return f"{label}: n={stats.n} p50={stats.p50:.0f}s p90={stats.p90:.0f}s"


def format_friction(result: Friction) -> str:
    n = result.tui_sessions
    lines = [
        "TUI friction",
        f"TUI sessions: {n}",
        f"Sessions with no run intent: {result.no_intent_sessions}/{n}"
        f" ({_ratio(result.no_intent_sessions, n)})",
        f"Sessions with an attempt but no completion: "
        f"{result.attempt_without_completion_sessions}/{n}",
        f"Sessions restored from a saved form: {result.restored_sessions}/{n}",
        f"Sessions recovering after a bad outcome: {result.recovered_sessions}/"
        f"{result.sessions_with_bad_outcome}",
        _timing_line("Time to first run intent", result.time_to_first_intent),
        _timing_line("Time to first attempt", result.time_to_first_attempt),
        _timing_line("Time to first completion", result.time_to_first_completion),
        _timing_line("Time in validation review", result.validation_review_dwell),
        "Validation review outcomes: "
        + "  ".join(f"{k}={v}" for k, v in result.validation_review_outcomes.items()),
        "Dataset loads: " + "  ".join(f"{k}={v}" for k, v in result.dataset_loads.items()),
        "Advanced overrides: "
        + "  ".join(f"{k}={v}" for k, v in result.advanced_overrides.items()),
    ]
    return "\n".join(lines) + "\n"
