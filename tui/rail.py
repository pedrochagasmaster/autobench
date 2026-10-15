"""Step rail (TUI redesign 01 §2.1, §3.1; Phase 2 PR 4).

One horizontal row at every width:
``1 Data · 2 Entity · 3 Analysis & mode · 4 Privacy & compliance · 5 Review & run``.
Each step carries a glyph from the status language (done ``✓``, attention
``!``) plus ``↺`` for restored values and ``○`` for not started. The current
step is drawn bold reverse with a ``▸`` marker, so it reads under NO_COLOR.
Steps are not gated. The rail is not focusable (no dead Tab stop); a click on
a step goes to it, like the command palette's "Go to step" entries.
"""

from __future__ import annotations

from typing import Any, Dict, List, NamedTuple, Tuple

from textual import events
from textual.content import Content
from textual.message import Message
from textual.widget import Widget

from tui.status import glyph as status_glyph, use_ascii_glyphs


class Step(NamedTuple):
    id: str
    number: int
    title: str
    short: str

    @property
    def container_id(self) -> str:
        return f"step_{self.id}"


STEPS: Tuple[Step, ...] = (
    Step("data", 1, "Data", "Data"),
    Step("entity", 2, "Entity", "Entity"),
    Step("analysis", 3, "Analysis & mode", "Analysis"),
    Step("privacy", 4, "Privacy & compliance", "Privacy"),
    Step("review", 5, "Review & run", "Review"),
)
STEP_IDS: Tuple[str, ...] = tuple(step.id for step in STEPS)
STEP_BY_ID: Dict[str, Step] = {step.id: step for step in STEPS}

# Rail states. done/attention reuse the status language glyphs.
DONE = "done"
ATTENTION = "attention"
RESTORED = "restored"
PENDING = "pending"
RAIL_STATES = (DONE, ATTENTION, RESTORED, PENDING)

_OWN_GLYPHS = {RESTORED: ("↺", "(r)"), PENDING: ("○", "( )")}


def rail_glyph(state: str) -> str:
    if state == DONE:
        return status_glyph("success")
    if state == ATTENTION:
        return status_glyph("notready")
    unicode, ascii_ = _OWN_GLYPHS[state]
    return ascii_ if use_ascii_glyphs() else unicode


class StepRail(Widget, can_focus=False):
    """The one-row step rail. ``set_states`` updates it; clicks post ``StepClicked``."""

    COMPONENT_CLASSES = {
        "rail--current",
        "rail--done",
        "rail--attention",
        "rail--restored",
        "rail--pending",
    }

    DEFAULT_CSS = """
    StepRail { height: 1; width: 1fr; }
    """

    class StepClicked(Message):
        def __init__(self, step_id: str) -> None:
            super().__init__()
            self.step_id = step_id

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._current = STEPS[0].id
        self._states: Dict[str, str] = {step.id: PENDING for step in STEPS}
        self._click_ranges: List[Tuple[int, int, str]] = []

    @property
    def current(self) -> str:
        return self._current

    @property
    def states(self) -> Dict[str, str]:
        return dict(self._states)

    def set_states(self, current: str, states: Dict[str, str]) -> None:
        merged = {step.id: states.get(step.id, PENDING) for step in STEPS}
        if current == self._current and merged == self._states:
            return
        self._current = current
        self._states = merged
        self.refresh()

    def _label(self, step: Step, short: bool) -> str:
        name = step.short if short else step.title
        return f"{rail_glyph(self._states[step.id])} {step.number} {name}"

    def _pieces(self, width: int) -> List[Tuple[Step, str]]:
        """Full titles when they fit, else short ones (current step first to stay full)."""
        for short_current, short_others in ((False, False), (False, True), (True, True)):
            pieces = []
            for step in STEPS:
                is_current = step.id == self._current
                short = short_current if is_current else short_others
                marker = "▸" if is_current else " "
                pieces.append((step, f"{marker}{self._label(step, short)} "))
            if sum(len(text) for _, text in pieces) <= width:
                return pieces
        return pieces

    @property
    def visible_text(self) -> str:
        return self._build(self.size.width or 80).plain

    def _build(self, width: int, styles: Dict[str, Any] | None = None) -> Content:
        styles = styles or {}
        parts: List[Content] = []
        ranges: List[Tuple[int, int, str]] = []
        used = 0
        for step, text in self._pieces(width):
            if step.id == self._current:
                style = styles.get("current", "")
            else:
                style = styles.get(self._states[step.id], "")
            parts.append(Content.assemble((text, style)))
            ranges.append((used, used + len(text), step.id))
            used += len(text)
        self._click_ranges = ranges
        return Content.assemble(*parts)

    def render(self) -> Content:
        styles = {
            "current": self.get_visual_style("rail--current"),
            DONE: self.get_visual_style("rail--done"),
            ATTENTION: self.get_visual_style("rail--attention"),
            RESTORED: self.get_visual_style("rail--restored"),
            PENDING: self.get_visual_style("rail--pending"),
        }
        return self._build(self.size.width, styles)

    def on_click(self, event: events.Click) -> None:
        for start, end, step_id in self._click_ranges:
            if start <= event.x < end:
                event.stop()
                self.post_message(self.StepClicked(step_id))
                return
