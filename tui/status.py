"""Status language (TUI redesign 02 §2).

Twelve run and readiness states. Each has an UPPER-CASE word, a one-cell
glyph, an ASCII fallback and a colour role. Glyph and word always appear
together, so meaning never depends on colour. WITHHELD, BLOCKED and FAILED
are filled badges (reverse video under NO_COLOR); ``tui.styles`` holds the
CSS for every state.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Mapping, Optional


@dataclass(frozen=True)
class StatusSpec:
    word: str
    glyph: str
    ascii: str
    role: str
    filled: bool = False


STATUS: Mapping[str, StatusSpec] = {
    "ready": StatusSpec("READY", "●", "(*)", "success"),
    "notready": StatusSpec("NOT READY", "!", "(!)", "warning"),
    "loading": StatusSpec("LOADING", "◌", "(~)", "info"),
    "running": StatusSpec("RUNNING", "▸", "(>)", "info"),
    "awaiting": StatusSpec("WAITING FOR YOU", "?", "(?)", "warning"),
    "success": StatusSpec("DONE", "✓", "(+)", "success"),
    "compliant": StatusSpec("COMPLIANT", "◆", "(=)", "success"),
    "warning": StatusSpec("WARNING", "▲", "(^)", "warning"),
    "withheld": StatusSpec("WITHHELD", "◐", "(-)", "warning", filled=True),
    "blocked": StatusSpec("BLOCKED", "⊘", "(/)", "danger", filled=True),
    "error": StatusSpec("FAILED", "✗", "(x)", "danger", filled=True),
    "cancelled": StatusSpec("CANCELLED", "■", "(#)", "muted"),
}

FILLED_STATES = frozenset(name for name, spec in STATUS.items() if spec.filled)

_ascii_override: Optional[bool] = None


def use_ascii_glyphs(environ: Optional[Mapping[str, str]] = None, encoding: Optional[str] = None) -> bool:
    """True when the ASCII glyph set should be used.

    ``AUTOBENCH_GLYPHS=ascii`` (or ``unicode``) forces a set. Otherwise ASCII
    is used on the Linux console (``TERM=linux``) and when the real stdout is
    not UTF-8. Only glyphs change; words and styles stay the same.
    """
    if environ is None and encoding is None and _ascii_override is not None:
        return _ascii_override
    env = os.environ if environ is None else environ
    forced = env.get("AUTOBENCH_GLYPHS", "").strip().lower()
    if forced == "ascii":
        return True
    if forced == "unicode":
        return False
    if env.get("TERM") == "linux":
        return True
    if encoding is None:
        # sys.__stdout__: Textual replaces sys.stdout while the app runs.
        encoding = getattr(sys.__stdout__, "encoding", None)
    if not encoding:
        return False
    return encoding.lower().replace("-", "").replace("_", "") not in ("utf8", "utf8sig")


def set_ascii_glyphs(value: Optional[bool]) -> None:
    """Pin the glyph set for this process (``None`` re-enables detection)."""
    global _ascii_override
    _ascii_override = value


def glyph(state: str) -> str:
    spec = STATUS[state]
    return spec.ascii if use_ascii_glyphs() else spec.glyph


def status_text(state: str, detail: str = "") -> str:
    """``"<glyph> <WORD>"`` plus an optional ``" · detail"``.

    Unknown states render as the ``error`` glyph with ``UNKNOWN``, never as a
    bare code.
    """
    spec = STATUS.get(state)
    if spec is None:
        mark = STATUS["error"].ascii if use_ascii_glyphs() else STATUS["error"].glyph
        text = f"{mark} UNKNOWN"
    else:
        text = f"{glyph(state)} {spec.word}"
    if detail:
        text = f"{text} · {detail}"
    return text
