"""Best-effort error classification from orchestrator logs."""

from __future__ import annotations

import re
from pathlib import Path

PATTERNS: list[tuple[str, str]] = [
    ("SYNTAX", r"AnalysisException.*Syntax error|Erro mapeado: SYNTAX_ERROR|\bSYNTAX_ERROR\b"),
    ("TABLE_NOT_FOUND", r"Table.*does not exist|TableNotFoundException|\bTABLE_NOT_FOUND\b"),
    ("MEMORY", r"Memory limit exceeded|MEMORY_LIMIT_EXCEEDED"),
    ("AUTH", r"AuthorizationException|AuthenticationException|Kerberos.*expired|\bAUTH_ERROR\b"),
    ("QUEUE", r"Rejected.*pool|All pools busy|queue timeout|exceeded timeout: queue is full"),
]

SUGGESTIONS: dict[str, str] = {
    "SYNTAX": "Review the SQL file for syntax errors and re-run Preview SQL.",
    "TABLE_NOT_FOUND": "Verify the source table or schema exists in Impala.",
    "MEMORY": "Reduce query scope or ask your platform team about memory limits.",
    "AUTH": "Refresh your Kerberos ticket with kinit and retry.",
    "QUEUE": "Wait for cluster capacity or try again during off-peak hours.",
}


_TAIL_READ_BYTES = 65536


def _tail_lines_of(log_path: Path, tail_lines: int) -> list[str] | None:
    """Read at most the last ``_TAIL_READ_BYTES`` of the log and return its
    trailing lines. Avoids loading multi-MB orchestrator logs into memory."""
    try:
        size = log_path.stat().st_size
        with log_path.open("r", encoding="utf-8", errors="replace") as handle:
            if size > _TAIL_READ_BYTES:
                handle.seek(size - _TAIL_READ_BYTES)
                handle.readline()  # drop the partial first line
            lines = handle.read().splitlines()
    except OSError:
        return None
    return lines[-tail_lines:]


def classify(log_path: Path, *, tail_lines: int = 50) -> str | None:
    """Return a short error code if a known pattern matches recent log lines."""
    if not log_path.is_file():
        return None
    lines = _tail_lines_of(log_path, tail_lines)
    if lines is None:
        return None
    blob = "\n".join(lines)
    for code, pattern in PATTERNS:
        if re.search(pattern, blob, re.IGNORECASE):
            return code
    return None


def suggestion(code: str | None) -> str:
    if code is None:
        return "Check the log for details."
    return SUGGESTIONS.get(code, "Check the log for details.")


def first_matching_line(log_path: Path, code: str | None, *, tail_lines: int = 50) -> str:
    if code is None or not log_path.is_file():
        return ""
    pattern = next((p for c, p in PATTERNS if c == code), None)
    if pattern is None:
        return ""
    lines = _tail_lines_of(log_path, tail_lines)
    if lines is None:
        return ""
    compiled = re.compile(pattern, re.IGNORECASE)
    for line in reversed(lines):
        if compiled.search(line):
            return line.strip()[:120]
    return ""
