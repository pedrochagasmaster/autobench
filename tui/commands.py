"""Command palette entries (Ctrl+P; TUI redesign 01 §4.5, owner decision 7).

The palette is the only way to jump straight to a step: there are no F2–F6
or Alt+digit step keys. Tab still flows from one step into the next.
"""

from __future__ import annotations

from typing import Any, Iterator, Tuple

from textual.command import DiscoveryHit, Hit, Hits, Provider

from tui.rail import STEPS


def _entries(app: Any) -> Iterator[Tuple[str, Any, str]]:
    for step in STEPS:
        yield (
            f"Go to step: {step.number} {step.title}",
            (lambda step_id=step.id: app.action_go_to_step(step_id)),
            "Show this step; focus its first blocker, else its first field",
        )
    yield ("Run analysis", app.action_run_analysis, "Same as Ctrl+R")
    yield ("Cancel run", app.action_cancel_run, "Same as Ctrl+G; only before output writing starts")
    yield ("Toggle results view", app.action_toggle_results, "Same as Ctrl+T")
    yield ("Copy report path", app.action_copy_path, "Same as Ctrl+Y")


class AutobenchCommands(Provider):
    """Steps and run actions for the command palette."""

    async def discover(self) -> Hits:
        for name, callback, help_text in _entries(self.app):
            yield DiscoveryHit(name, callback, help=help_text)

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        for name, callback, help_text in _entries(self.app):
            score = matcher.match(name)
            if score > 0:
                yield Hit(score, matcher.highlight(name), callback, help=help_text)
