"""Terminal-safe deterministic telemetry report rendering."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from core.telemetry.reader import Summary, WhoRow

# CSI: ESC [ params final; OSC: ESC ] ... BEL or ST (ESC \)
_ANSI_RE = re.compile(
    r"(?:"
    r"\x1b\[[0-?]*[ -/]*[@-~]"  # CSI
    r"|"
    r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC
    r")"
)

_SURFACE_ORDER = ("share", "rate")
_ACTION_ORDER = ("share_analysis", "rate_analysis")
_OUTCOME_ORDER = ("completed", "cancelled", "refused", "failed")


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


def format_who(rows: list[WhoRow]) -> str:
    lines = ["USER  SESSIONS  LAST_SEEN  COMPLETED"]
    if not rows:
        lines.append("No telemetry events.")
    else:
        for row in rows:
            user = sanitize_terminal(row.user)
            lines.append(
                f"{user}  {row.sessions}  {_format_ts(row.last_seen)}  {row.completed}"
            )
    return "\n".join(lines) + "\n"


def format_summary(summary: Summary) -> str:
    sections: list[str] = []

    surface_lines = ["Surfaces"]
    for key in _SURFACE_ORDER:
        surface_lines.append(f"{key}  {int(summary.surfaces.get(key, 0))}")
    sections.append("\n".join(surface_lines))

    action_lines = ["Actions"]
    for key in _ACTION_ORDER:
        action_lines.append(f"{key}  {int(summary.actions.get(key, 0))}")
    sections.append("\n".join(action_lines))

    outcome_lines = ["Outcomes"]
    for key in _OUTCOME_ORDER:
        outcome_lines.append(f"{key}  {int(summary.outcomes.get(key, 0))}")
    sections.append("\n".join(outcome_lines))

    return "\n\n".join(sections) + "\n"
