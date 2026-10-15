"""Form controls for the step bodies (TUI redesign 01 §2.2, §4.2; Phase 2 PR 5).

- ``ColumnSelect``: a Select whose options come in two groups split by a
  disabled separator row, e.g. numeric columns first for Metric and Total
  (non-numeric ones stay selectable below the line).
- ``ModeSwitch``: one focus stop for Share/Rate; ←/→ switch at once.
- ``EntityChooser``: a Select over a column's distinct values, or, above the
  Select limit, the large-list filter (an Input plus a capped OptionList).
  Used for the target entity and for the Citibank entity of the Citi
  competitor declaration. Only an exact value is ever chosen.

``ColumnSelect`` overrides the private ``Select._setup_options_renderables``
(Textual 7.5) to disable the separator; ``tests/test_tui_steps.py`` fails if a
Textual upgrade stops honouring it.
"""

from __future__ import annotations

import bisect
from typing import Any, Iterable, List, Optional, Sequence, Tuple

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.content import Content
from textual.css.query import NoMatches
from textual.message import Message
from textual.reactive import reactive
from textual.suggester import SuggestFromList, Suggester
from textual.widget import Widget
from textual.widgets import Collapsible, Input, OptionList, Select, Static
from textual.widgets._select import SelectOverlay
from textual.widgets.option_list import Option

from tui.status import glyph as status_glyph, use_ascii_glyphs

SELECT_BLANK = getattr(Select, "NULL", getattr(Select, "BLANK", None))

# Separator row value: never a column name (CSV headers cannot hold NUL).
SEPARATOR = "\x00separator"
# No letters, so Select type-ahead can never land on it.
SEPARATOR_PROMPT = "─" * 24
NUMERIC_MARK = " #"

ENTITY_SELECT_PROMPT = "None: peer group only"
ENTITY_LOADING_PROMPT = "Loading entities…"
ENTITY_FILTER_PLACEHOLDER = "Type to filter entities…"
NO_FILE_PROMPT = "Load a CSV first"
# Above this many distinct values the stock Select (one option per value,
# opened as an overlay) gets slow: 0.28 s to open at 5,000 and 2.6 s at 100k.
# Larger lists use the filter + capped OptionList picker instead (03 §6).
ENTITY_SELECT_MAX = 2000
ENTITY_MATCH_LIMIT = 200
PEER_ONLY_OPTION_ID = "peer-only"
VALUE_OPTION_ID_PREFIX = "v:"


class EntityIndex:
    """All distinct values of an entity column, searchable without a widget.

    Built on the entity worker thread. Matching is a ``bisect`` prefix search
    over the casefolded values, with a substring scan as the fallback when
    nothing starts with the typed text. ``value_set`` is the full set used to
    validate a typed target entity: only an exact value ever becomes one.
    """

    def __init__(self, values: List[str]) -> None:
        self.values = values
        self.value_set = frozenset(values)
        pairs = sorted((value.casefold(), value) for value in values)
        self.folded = [folded for folded, _ in pairs]
        self.ordered = [value for _, value in pairs]

    def __len__(self) -> int:
        return len(self.values)

    def _prefix_range(self, needle: str) -> tuple:
        lo = bisect.bisect_left(self.folded, needle)
        hi = bisect.bisect_left(self.folded, needle + "\U0010ffff", lo)
        return lo, hi

    def first_with_prefix(self, needle: str) -> Optional[str]:
        """First value (casefolded order) starting with casefolded ``needle``."""
        lo, hi = self._prefix_range(needle)
        return self.ordered[lo] if lo < hi else None

    def matches(self, text: str, limit: int = ENTITY_MATCH_LIMIT) -> tuple:
        """Return (up to ``limit`` matching values, total number of matches)."""
        needle = text.casefold()
        if not needle:
            return self.values[:limit], len(self.values)
        lo, hi = self._prefix_range(needle)
        if lo < hi:
            return self.ordered[lo:min(hi, lo + limit)], hi - lo
        found = [value for folded, value in zip(self.folded, self.ordered) if needle in folded]
        return found[:limit], len(found)


class EntitySuggester(SuggestFromList):
    """``SuggestFromList`` over an ``EntityIndex``: O(log n) prefix lookups.

    The stock implementation scans its list linearly on every keystroke and
    casefolds the whole list up front on the UI thread; the index has already
    done that work on the worker thread.
    """

    def __init__(self, index: EntityIndex) -> None:
        Suggester.__init__(self, case_sensitive=False)
        self._index = index
        self._suggestions = index.ordered
        self._for_comparison = index.folded

    async def get_suggestion(self, value: str) -> Optional[str]:
        return self._index.first_with_prefix(value)


def column_options(primary: Sequence[str], secondary: Sequence[str], *, mark: Iterable[str] = ()) -> List[Tuple[Any, str]]:
    """Select options: ``primary`` columns, a separator, then ``secondary``."""
    marked = frozenset(mark)

    def prompt(column: str) -> Text:
        return Text(column + (NUMERIC_MARK if column in marked else ""))

    options: List[Tuple[Any, str]] = [(prompt(c), c) for c in primary]
    if primary and secondary:
        options.append((Text(SEPARATOR_PROMPT, style="dim"), SEPARATOR))
    options.extend((prompt(c), c) for c in secondary)
    return options


class SafeSelect(Select):
    """``Select`` that tolerates being torn down while it mounts.

    Steps 2 and 3 mount in the background after a CSV load; if the app
    closes at that moment the stock mount handler would query an overlay
    that is already gone.
    """

    def _on_mount(self, event: events.Mount) -> None:  # Select, Textual 7.5
        # Textual runs every class's own handler along the MRO; preventing
        # the default skips Select._on_mount when the overlay is gone.
        if not self.query(SelectOverlay):
            event.prevent_default()


class ColumnSelect(SafeSelect):
    """Select with an optional disabled separator between two column groups."""

    def __init__(
        self,
        primary: Sequence[str] = (),
        secondary: Sequence[str] = (),
        *,
        value: Optional[str] = None,
        mark: Iterable[str] = (),
        **kwargs: Any,
    ) -> None:
        options = column_options(primary, secondary, mark=mark)
        legal = {v for _, v in options}
        kwargs.setdefault("allow_blank", True)
        kwargs.setdefault("compact", True)
        super().__init__(options, value=value if value in legal and value != SEPARATOR else SELECT_BLANK, **kwargs)
        self._columns_key: Tuple[Tuple[str, ...], Tuple[str, ...]] = (tuple(primary), tuple(secondary))

    def set_columns(
        self, primary: Sequence[str], secondary: Sequence[str], value: Optional[str], *, mark: Iterable[str] = ()
    ) -> None:
        """Replace the options only when the column groups changed, then select ``value``."""
        key = (tuple(primary), tuple(secondary))
        if key != self._columns_key:
            self._columns_key = key
            self.set_options(column_options(primary, secondary, mark=mark))
        self.set_value(value)

    def set_value(self, value: Optional[str]) -> None:
        target = value if value in self._legal_values and value != SEPARATOR else SELECT_BLANK
        if self.value != target:
            self.value = target

    @property
    def column(self) -> Optional[str]:
        value = self.value
        return None if value == SELECT_BLANK or value == SEPARATOR or value is None else str(value)

    def _setup_options_renderables(self) -> None:  # Select, Textual 7.5
        overlays = self.query(SelectOverlay)
        if not overlays:
            # Torn down mid-mount (the app is closing while a step mounts in
            # the background): there is nothing left to fill.
            return
        super()._setup_options_renderables()
        overlay = overlays.first()
        for index, (_, value) in enumerate(self._options):
            if value == SEPARATOR:
                overlay.disable_option_at_index(index)


class Disclosure(Collapsible, inherit_css=False):
    """A ``Collapsible`` without the stock ``&:focus-within`` tint.

    ``:focus-within`` makes every focus move inside the disclosure restyle
    its whole subtree (the reason PR 3 banned it); the title's own focus
    style is enough to show where focus is.
    """

    DEFAULT_CSS = """
    Disclosure {
        width: 1fr;
        height: auto;
        background: $surface;
        border-top: hkey $background;
        padding-bottom: 1;
        padding-left: 1;

        &.-collapsed > Contents {
            display: none;
        }
    }
    """


class ModeSwitch(Widget, can_focus=True):
    """``(●) Share  ( ) Rate`` — one Tab stop; ←/→ or Space switch the mode."""

    BINDINGS = [
        Binding("left", "set_mode('share')", "Share", show=False),
        Binding("right", "set_mode('rate')", "Rate", show=False),
        Binding("space", "toggle", "Switch", show=False),
    ]

    DEFAULT_CSS = """
    ModeSwitch { height: 1; width: 1fr; }
    """

    mode: reactive[str] = reactive("share")

    class Changed(Message):
        def __init__(self, switch: "ModeSwitch", mode: str) -> None:
            super().__init__()
            self.switch = switch
            self.mode = mode

        @property
        def control(self) -> "ModeSwitch":
            return self.switch

    def __init__(self, mode: str = "share", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.set_reactive(ModeSwitch.mode, mode)

    def _choice(self, name: str, label: str) -> str:
        on, off = ("(*)", "( )") if use_ascii_glyphs() else ("(●)", "( )")
        return f"{on if self.mode == name else off} {label}"

    @property
    def visible_text(self) -> str:
        return f"{self._choice('share', 'Share')}   {self._choice('rate', 'Rate')}    ←→ to switch"

    def render(self) -> Content:
        share = self._choice("share", "Share")
        rate = self._choice("rate", "Rate")
        focus_style = "bold reverse" if self.has_focus else "bold"
        return Content.assemble(
            (share, focus_style if self.mode == "share" else ""),
            "   ",
            (rate, focus_style if self.mode == "rate" else ""),
            ("    ←→ to switch", "dim"),
        )

    def watch_mode(self, mode: str) -> None:
        self.post_message(self.Changed(self, mode))

    def action_set_mode(self, mode: str) -> None:
        if not self.disabled:
            self.mode = mode

    def action_toggle(self) -> None:
        if not self.disabled:
            self.mode = "rate" if self.mode == "share" else "share"

    def on_click(self, event: events.Click) -> None:
        event.stop()
        self.focus()
        self.action_set_mode("share" if event.x < len(self._choice("share", "Share")) + 2 else "rate")

    def _on_focus(self, event: events.Focus) -> None:
        self.refresh()

    def _on_blur(self, event: events.Blur) -> None:
        self.refresh()


class EntityChooser(Vertical):
    """Target or Citibank entity: a Select, or the large-list filter.

    Ids: the Select is ``select_id``; the large-list widgets are
    ``<base>_picker``, ``<base>_filter``, ``<base>_match_count`` and
    ``<base>_matches``. ``Changed`` carries the chosen exact value (or None)
    and the filter text as typed.
    """

    DEFAULT_CSS = """
    EntityChooser { height: auto; }
    """

    class Changed(Message):
        def __init__(self, chooser: "EntityChooser", choice: Optional[str], text: str) -> None:
            super().__init__()
            self.chooser = chooser
            self.choice = choice
            self.text = text

        @property
        def control(self) -> "EntityChooser":
            return self.chooser

    def __init__(
        self,
        select_id: str,
        base: str,
        *,
        values: Sequence[str] = (),
        index: Optional[EntityIndex] = None,
        choice: Optional[str] = None,
        text: str = "",
        loaded: bool = False,
        loading: bool = False,
        enabled: bool = True,
        subject: str = "Target entity",
        blank_prompt: str = ENTITY_SELECT_PROMPT,
        blank_hint: str = "Leave blank to compare with the peer group only.",
        casefold_match: bool = False,
        no_match_hint: str = "Pick from the list, or clear the filter for peer group only.",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.no_match_hint = no_match_hint
        self.select_id = select_id
        self.base = base
        self.subject = subject
        self.blank_prompt = blank_prompt
        self.blank_hint = blank_hint
        self.casefold_match = casefold_match
        self._index = index
        self._values: List[str] = [] if index is not None else list(values)
        self._choice = choice
        self._text = text
        self._loaded = loaded
        self._loading = loading
        # Called synchronously on every operator change (the app binds it);
        # without it, ``Changed`` is posted instead.
        self.change_callback: Any = None
        # Off (e.g. the Citi box unticked): every inner field is disabled
        # itself, so none is a Tab stop.
        self._enabled = enabled

    # ── State ──────────────────────────────────────────────────────────

    @property
    def large(self) -> bool:
        return self._index is not None

    @property
    def values(self) -> List[str]:
        return list(self._index.values) if self._index is not None else list(self._values)

    @property
    def choice(self) -> Optional[str]:
        return self._choice

    def _prompt(self) -> str:
        if self._loading:
            return ENTITY_LOADING_PROMPT
        return self.blank_prompt if self._loaded else NO_FILE_PROMPT

    def compose(self) -> ComposeResult:
        # Above the Select limit the Select never holds the big list.
        options = [] if self._index is not None else [(Text(v), v) for v in self._values]
        value = self._choice if (self._index is None and self._choice in set(self._values)) else SELECT_BLANK
        select = SafeSelect(options, prompt=self._prompt(), id=self.select_id, allow_blank=True, compact=True, value=value)
        select.set_class(self.large, "hidden")
        select.disabled = self._loading or not self._enabled
        yield select
        picker = Vertical(id=f"{self.base}_picker", classes="entity-picker")
        picker.set_class(not self.large, "hidden")
        with picker:
            entity_filter = Input(
                value=self._text,
                placeholder=ENTITY_LOADING_PROMPT if self._loading else ENTITY_FILTER_PLACEHOLDER,
                id=f"{self.base}_filter",
                compact=True,
                disabled=self._loading or not self._enabled,
            )
            if self._index is not None:
                entity_filter.suggester = EntitySuggester(self._index)
            yield entity_filter
            yield Static("", id=f"{self.base}_match_count", classes="field-hint")
            yield OptionList(
                id=f"{self.base}_matches", classes="ab-list entity-matches", disabled=not self._enabled
            )

    def on_mount(self) -> None:
        try:
            select, filter_input = self.select, self._q("filter", Input)
        except NoMatches:
            return  # torn down mid-mount: the app is closing
        if self.large:
            self._refresh_matches(post=False)
        # Synchronous: the form never lags what the operator picked or typed.
        self.watch(select, "value", self._select_value_changed, init=False)
        self.watch(filter_input, "value", self._filter_value_changed, init=False)

    def _emit(self, choice: Optional[str], text: str) -> None:
        if self.change_callback is not None:
            self.change_callback(self, choice, text)
        else:
            self.post_message(self.Changed(self, choice, text))

    def _select_value_changed(self, value: Any) -> None:
        if self.large or not self._loaded or self._loading:
            # Options being replaced; the transient BLANK is not a choice.
            return
        choice = None if value == SELECT_BLANK or value is None else str(value)
        self._choice = choice
        self._emit(choice, "")

    def _filter_value_changed(self, value: str) -> None:
        if self.large:
            self._refresh_matches()

    def _q(self, suffix: str, kind: Any = None) -> Any:
        return self.query_one(f"#{self.base}_{suffix}", kind) if kind else self.query_one(f"#{self.base}_{suffix}")

    @property
    def select(self) -> Select:
        return self.query_one(f"#{self.select_id}", Select)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        if enabled == self._enabled:
            return
        self._enabled = enabled
        self._apply_disabled()

    def _apply_disabled(self) -> None:
        if not self.is_mounted:
            return
        off = self._loading or not self._enabled
        self.select.disabled = off
        self._q("filter", Input).disabled = off
        self._q("matches", OptionList).disabled = not self._enabled

    def set_loading(self, loading: bool) -> None:
        self._loading = loading
        if not self.is_mounted:
            return
        select = self.select
        select.prompt = self._prompt()
        entity_filter = self._q("filter", Input)
        entity_filter.placeholder = ENTITY_LOADING_PROMPT if loading else ENTITY_FILTER_PLACEHOLDER
        self._apply_disabled()

    def set_values(
        self,
        values: Optional[Sequence[str]],
        index: Optional[EntityIndex],
        *,
        choice: Optional[str],
        text: str = "",
        loaded: bool = True,
    ) -> None:
        """Show ``values`` (Select) or ``index`` (large-list filter) and re-select ``choice``."""
        self._loaded = loaded
        self._index = index
        self._values = [] if index is not None else list(values or [])
        self._choice = choice
        self._text = text
        if not self.is_mounted:
            return
        focused = self.app.focused
        had_focus = focused is not None and self in focused.ancestors
        select = self.select
        picker = self._q("picker")
        entity_filter = self._q("filter", Input)
        select.set_class(self.large, "hidden")
        picker.set_class(not self.large, "hidden")
        select.prompt = self._prompt()
        if index is None:
            entity_filter.suggester = None
            if entity_filter.value:
                entity_filter.value = ""
            self._q("matches", OptionList).clear_options()
            self._q("match_count", Static).update("")
            select.set_options([(Text(v), v) for v in self._values])
            if choice is not None and choice in set(self._values):
                select.value = choice
        else:
            entity_filter.suggester = EntitySuggester(index)
            if entity_filter.value != text:
                entity_filter.value = text
            self._refresh_matches(post=False)
        if had_focus:
            (entity_filter if self.large else select).focus()

    def set_choice(self, choice: Optional[str], text: str = "") -> None:
        """Programmatic choice (FormState sync): never posts ``Changed``."""
        self._choice = choice
        self._text = text
        if not self.is_mounted:
            return
        if self.large:
            entity_filter = self._q("filter", Input)
            if entity_filter.value != text:
                entity_filter.value = text
        else:
            select = self.select
            target = choice if choice in select._legal_values else SELECT_BLANK
            if select.value != target:
                select.value = target

    def resolve(self, text: str) -> Optional[str]:
        """The exact value ``text`` names in the large list, or None."""
        index = self._index
        if index is None or not text.strip():
            return None
        if text in index.value_set:
            return text
        if self.casefold_match:
            needle = text.strip().casefold()
            found = [v for v in index.values if v.casefold() == needle]
            if len(found) == 1:
                return found[0]
        return None

    def _refresh_matches(self, *, post: bool = True) -> None:
        index = self._index
        try:
            text = self._q("filter", Input).value
            matches = self._q("matches", OptionList)
            count = self._q("match_count", Static)
        except Exception:
            return
        if index is None:
            matches.clear_options()
            count.update("")
            return
        self._text = text
        self._choice = self.resolve(text)
        shown, total = index.matches(text.strip())
        options = [Option(self.blank_prompt, id=PEER_ONLY_OPTION_ID)]
        options.extend(Option(Text(value), id=f"{VALUE_OPTION_ID_PREFIX}{value}") for value in shown)
        matches.set_options(options)
        typed = text.strip()
        count.update(Text(self.match_message(typed, len(index), len(shown), total)))
        count.set_class(bool(typed) and not total, "-error")
        if post:
            self._emit(self._choice, text)

    def match_message(self, typed: str, size: int, shown: int, total: int) -> str:
        """One-line hint under the filter (02 §4.1, §5.1 copy rules)."""
        if self._choice is not None:
            return f"{status_glyph('success')} {self.subject}: {self._choice}"
        if not typed:
            return f"{size:,} entities. {self.blank_hint}"
        if not total:
            return f"{status_glyph('error')} No match. {self.no_match_hint}"
        noun = "match" if total == 1 else "matches"
        counted = f"{total:,} {noun}" if shown >= total else f"Showing {shown:,} of {total:,} {noun}"
        return f"{counted}. Pick one: typed text must match exactly."

    # ── Events from the inner widgets ─────────────────────────────────

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == self.select_id:
            event.stop()  # Handled synchronously by the value watcher.

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == f"{self.base}_filter":
            event.stop()  # Handled synchronously by the value watcher.

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != f"{self.base}_filter":
            return
        event.stop()
        self._q("matches", OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id != f"{self.base}_matches":
            return
        event.stop()
        option_id = event.option.id or ""
        entity_filter = self._q("filter", Input)
        if option_id == PEER_ONLY_OPTION_ID:
            entity_filter.value = ""
        elif option_id.startswith(VALUE_OPTION_ID_PREFIX):
            entity_filter.value = option_id[len(VALUE_OPTION_ID_PREFIX):]
        entity_filter.focus()
