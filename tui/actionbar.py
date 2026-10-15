"""Action bar (TUI redesign 01 §3.1, §5.2; Phase 2 PR 4).

One row, always visible above the key bar. Left: a status-language badge and
one line of detail (readiness, the first blocker, the run stage or the
outcome). Right: the key that acts on it (``^R Run share analysis``,
``^G Cancel run``, ``^Y Copy path``) or a plain reason it cannot
("Cancel unavailable: writing outputs"). The right-hand key is clickable.
"""

from __future__ import annotations

from typing import Any, Optional

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.content import Content
from textual.widgets import Static

from tui.widgets import StatusBadge


class ActionKey(Static):
    """Right-hand key of the action bar; a click runs its action."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__("", **kwargs)
        self.action: str = ""

    async def on_click(self, event: events.Click) -> None:
        if self.action:
            event.stop()
            await self.run_action(self.action)


class ActionBar(Horizontal):
    """``set_state`` renders one state; repeated identical calls do nothing."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._last: Optional[tuple] = None

    def compose(self) -> ComposeResult:
        yield StatusBadge("ready", id="action_badge")
        yield Static("", id="action_message")
        yield ActionKey(id="action_key")

    def set_state(
        self,
        state: str,
        message: str,
        key_text: str = "",
        key_action: str = "",
        *,
        detail: str = "",
        dim_key: bool = False,
    ) -> None:
        key = (state, detail, message, key_text, key_action, dim_key)
        if key == self._last:
            return
        self._last = key
        self.query_one("#action_badge", StatusBadge).set_status(state, detail)
        # Literal text: entity, file and column names come from the data.
        self.query_one("#action_message", Static).update(Content(message))
        action_key = self.query_one("#action_key", ActionKey)
        action_key.update(Content(key_text))
        action_key.action = key_action
        action_key.set_class(dim_key, "-dim")
        action_key.display = bool(key_text)

    @property
    def message(self) -> str:
        return str(self.query_one("#action_message", Static).content)

    @property
    def key_text(self) -> str:
        return str(self.query_one("#action_key", ActionKey).content)

    @property
    def state(self) -> str:
        return self.query_one("#action_badge", StatusBadge).state
