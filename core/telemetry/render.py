"""Terminal-safe deterministic telemetry report rendering."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from core.telemetry.constants import ACTIONS, OUTCOMES, SURFACES
from core.telemetry.reader import Summary, WhoRow

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

    action_lines = ["Actions"]
    for key in ACTIONS:
        action_lines.append(f"{key}  {int(summary.actions.get(key, 0))}")
    sections.append("\n".join(action_lines))

    outcome_lines = ["Outcomes"]
    for key in OUTCOMES:
        outcome_lines.append(f"{key}  {int(summary.outcomes.get(key, 0))}")
    sections.append("\n".join(outcome_lines))

    return "\n\n".join(sections) + "\n"
