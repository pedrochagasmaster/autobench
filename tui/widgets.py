"""Small widget subclasses for the visual system (TUI redesign 02 §2-§3).

``BoxCheckbox`` and ``BoxSelectionList`` override private Textual 7.5 APIs
(``ToggleButton._button`` and ``SelectionList._selected``).
``tests/test_tui_visual_system.py`` renders both and fails loudly if a Textual
upgrade stops drawing ``[x]`` / ``[ ]``.
"""

from __future__ import annotations

from typing import Any

from rich.segment import Segment
from rich.style import Style as RichStyle
from textual.content import Content
from textual.strip import Strip
from textual.style import Style
from textual.widgets import Checkbox, SelectionList, Static
from textual.widgets.option_list import OptionDoesNotExist

from tui.status import STATUS, status_text


class StatusBadge(Static):
    """Glyph + WORD for one of the twelve states.

    Colour comes only from the ``-<state>`` CSS class in ``tui.styles``.
    The text is built without markup, so details from data cannot inject
    styles.
    """

    def __init__(self, state: str = "ready", detail: str = "", **kwargs: Any) -> None:
        super().__init__("", **kwargs)
        self._state = ""
        self._detail = ""
        self.set_status(state, detail)

    @property
    def state(self) -> str:
        return self._state

    @property
    def text(self) -> str:
        return status_text(self._state, self._detail)

    def set_status(self, state: str, detail: str = "") -> None:
        if state == self._state and detail == self._detail:
            return
        self._state = state
        self._detail = detail
        for name in STATUS:
            self.set_class(name == state, f"-{name}")
        self.update(Content(self.text))


class BoxCheckbox(Checkbox):
    """Checkbox that draws ``[x]`` / ``[ ]`` so its state never depends on colour."""

    @property
    def _button(self) -> Content:  # ToggleButton._button, Textual 7.5
        label_style = self.get_visual_style("toggle--label")
        mark = Style(foreground=label_style.foreground, bold=self.value)
        return Content.assemble(("[", mark), ("x" if self.value else " ", mark), ("]", mark))


class BoxSelectionList(SelectionList):
    """SelectionList with the same ``[x]`` / ``[ ]`` gutter (still 3 cells wide)."""

    def render_line(self, y: int) -> Strip:
        strip = super().render_line(y)
        segments = list(strip)
        if len(segments) < 4:
            return strip
        _, scroll_y = self.scroll_offset
        try:
            option = self.get_option_at_index(scroll_y + y)
        except OptionDoesNotExist:
            return strip
        base = segments[3].style or RichStyle()
        meta = segments[1].style.meta if segments[1].style else None
        mark = RichStyle(bold=True, color=base.color, bgcolor=base.bgcolor, meta=meta)
        box = "x" if option.value in self._selected else " "
        return Strip(
            [Segment("[", mark), Segment(box, mark), Segment("]", mark), *segments[3:]],
            strip.cell_length,
        )
