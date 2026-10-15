"""App-owned key bar (TUI redesign 03 §2, content from 01 §4.4).

Replaces Textual's stock ``Footer``. The stock footer recomposes every
``FooterKey`` on each focus change (the Tab-latency tail in 03 §2) and, under
``textual-ansi``, draws its descriptions black on black (02 §1.5). The key bar
is one widget that re-renders only when its context changes, and its keys
stay clickable (``on_click`` maps the clicked cell to the key's action).

Contexts are adapted to today's bindings. There are no step keys (owner
decision 7: step jumps are command-palette entries, ``tui.commands``).
"""

from __future__ import annotations

from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from textual import events
from textual.content import Content
from textual.widget import Widget

from tui.status import use_ascii_glyphs


class KeyHint(NamedTuple):
    key: str
    label: str
    action: str = ""


_RUN = KeyHint("^R", "Run", "app.run_analysis")
_OPEN = KeyHint("^O", "Open CSV", "app.open_file")
_ADVANCED = KeyHint("F8", "Advanced", "app.toggle_advanced")
_EXPORT = KeyHint("F9", "Export advanced", "app.export_advanced")
_PRESETS = KeyHint("F1", "Preset guide", "app.show_help")
_CLEAR = KeyHint("^L", "Clear log", "app.clear_log")
_QUIT = KeyHint("^Q", "Quit", "app.quit")
_RESULTS = KeyHint("^T", "Results", "app.toggle_results")
_CANCEL = KeyHint("^G", "Cancel run", "app.cancel_run")
_COPY = KeyHint("^Y", "Copy path", "app.copy_path")
# Modal hints are display-only; each modal binds its own Escape action.
_ESC_CANCEL = KeyHint("Esc", "Cancel")

COMMANDS = KeyHint("^P", "Commands", "app.command_palette")

# Hints are in priority order: when the bar is narrow, trailing hints drop.
# "Enter", "Space" and arrow keys are written as tokens and drawn as glyphs
# (or as words in ASCII mode) by ``display_key``.
CONTEXTS: Dict[str, Tuple[KeyHint, ...]] = {
    "field": (_RUN, _OPEN, _ADVANCED, _RESULTS, _QUIT, _PRESETS, _CLEAR, _EXPORT),
    "select": (KeyHint("Enter", "Open"), _RUN, _OPEN, _ADVANCED, _RESULTS, _QUIT, _PRESETS, _CLEAR),
    "list": (KeyHint("Space", "Toggle"), KeyHint("Up/Down", "Move"), _RUN, _ADVANCED, _RESULTS, _QUIT, _PRESETS),
    # Single-choice list (the large-entity matches): Enter picks one row.
    "choose": (KeyHint("Enter", "Choose"), KeyHint("Up/Down", "Move"), _RUN, _ADVANCED, _RESULTS, _QUIT, _PRESETS),
    "toggle": (KeyHint("Space", "Toggle"), _RUN, _OPEN, _ADVANCED, _RESULTS, _QUIT, _PRESETS, _CLEAR),
    "button": (KeyHint("Enter", "Press"), _RUN, _OPEN, _ADVANCED, _RESULTS, _QUIT, _PRESETS, _CLEAR),
    "tabs": (KeyHint("Left/Right", "Switch mode"), _RUN, _OPEN, _ADVANCED, _RESULTS, _QUIT, _PRESETS),
    "results": (
        _COPY,
        KeyHint("^R", "Run again", "app.run_analysis"),
        _RESULTS,
        _OPEN,
        _ADVANCED,
        _QUIT,
        _PRESETS,
        _CLEAR,
    ),
    "running": (_CANCEL, _RESULTS, _QUIT, _CLEAR, _PRESETS),
    "confirm": (KeyHint("Tab", "Move"), KeyHint("Enter", "Choose"), _ESC_CANCEL),
    "validation": (
        KeyHint("Up/Down", "Read issues"),
        KeyHint("Tab", "Buttons"),
        KeyHint("Esc", "Cancel run"),
    ),
    "picker": (
        KeyHint("Up/Down", "Move"),
        KeyHint("Enter", "Open"),
        KeyHint("Tab", "Filter/lists"),
        _ESC_CANCEL,
    ),
    "help": (KeyHint("Up/Down", "Scroll"), KeyHint("Esc", "Close")),
}

# Contexts that show "^P Commands" on the right (the main screen).
_COMMAND_CONTEXTS = frozenset({"field", "select", "list", "choose", "toggle", "button", "tabs", "results", "running"})

_GLYPH_KEYS = {"Enter": "↵", "Space": "␣", "Up/Down": "↑↓", "Left/Right": "←→"}


def display_key(key: str) -> str:
    if use_ascii_glyphs():
        return key
    return _GLYPH_KEYS.get(key, key)


def context_text(context: str) -> str:
    """Plain text of a context, every hint included (tests and docs)."""
    hints = CONTEXTS[context]
    parts = [f"{display_key(h.key)} {h.label}" for h in hints]
    if context in _COMMAND_CONTEXTS:
        parts.append(f"{display_key(COMMANDS.key)} {COMMANDS.label}")
    return "  ".join(parts)


class KeyBar(Widget):
    """One-row key bar. Call ``set_context`` when the focus context changes."""

    COMPONENT_CLASSES = {"keybar--key", "keybar--label"}

    DEFAULT_CSS = """
    KeyBar {
        dock: bottom;
        height: 1;
        width: 1fr;
    }
    """

    def __init__(self, context: str = "field", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._bar_context = context
        # (start, end, action) cell ranges of the last render, for clicks.
        self._click_ranges: List[Tuple[int, int, str]] = []

    @property
    def context(self) -> str:
        return self._bar_context

    def set_context(self, context: str) -> None:
        if context not in CONTEXTS or context == self._bar_context:
            return
        self._bar_context = context
        self.refresh()

    @property
    def visible_text(self) -> str:
        """The text currently drawn (after narrow-width truncation)."""
        return self._build(self.size.width or 80).plain

    def _hint_content(self, hint: KeyHint, key_style: Any, label_style: Any) -> Content:
        key = Content.assemble((f" {display_key(hint.key)}", key_style))
        label = Content.assemble((f" {hint.label} ", label_style))
        return Content.assemble(key, label)

    def _build(self, width: int, key_style: Any = "", label_style: Any = "") -> Content:
        hints = CONTEXTS.get(self._bar_context, ())
        right: Optional[Content] = None
        if self._bar_context in _COMMAND_CONTEXTS:
            right = self._hint_content(COMMANDS, key_style, label_style)
        parts = []
        ranges: List[Tuple[int, int, str]] = []
        used = 0
        reserve = right.cell_length if right is not None else 0
        for hint in hints:
            piece = self._hint_content(hint, key_style, label_style)
            if used + piece.cell_length + reserve > width:
                if parts:
                    break
                reserve = 0  # Very narrow: drop the right-hand hint first.
                if piece.cell_length > width:
                    break
            parts.append(piece)
            if hint.action:
                ranges.append((used, used + piece.cell_length, hint.action))
            used += piece.cell_length
        if right is not None and used + right.cell_length <= width:
            gap = width - used - right.cell_length
            parts.append(Content(" " * gap))
            parts.append(right)
            ranges.append((width - right.cell_length, width, COMMANDS.action))
        self._click_ranges = ranges
        return Content.assemble(*parts) if parts else Content("")

    def render(self) -> Content:
        key_style = self.get_visual_style("keybar--key")
        label_style = self.get_visual_style("keybar--label")
        return self._build(self.size.width, key_style, label_style)

    async def on_click(self, event: events.Click) -> None:
        """Run the action of the clicked key (keys stay mouse-clickable)."""
        for start, end, action in self._click_ranges:
            if start <= event.x < end:
                event.stop()
                await self.run_action(action)
                return
