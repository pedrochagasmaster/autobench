"""Reusable confirmation modal for safety-sensitive actions."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static


class ConfirmScreen(ModalScreen[bool]):
    """Modal confirmation that returns ``True`` for confirm, ``False`` otherwise."""

    BINDINGS = [
        ("enter", "confirm", "Confirm"),
        ("y", "confirm", "Yes"),
        ("n", "cancel", "No"),
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        title: str,
        body: str,
        *,
        danger: bool = False,
        confirm_label: str = "Confirm",
        cancel_label: str = "Cancel",
        required_confirmation_text: str | None = None,
    ) -> None:
        super().__init__()
        self.title = title
        self.body = body
        self.danger = danger
        self.confirm_label = confirm_label
        self.cancel_label = cancel_label
        self.required_confirmation_text = required_confirmation_text

    def compose(self) -> ComposeResult:
        classes = "danger" if self.danger else ""
        with Vertical(id="confirm-dialog", classes=classes):
            title_markup = (
                f"[bold red]{self.title}[/]"
                if self.danger
                else f"[bold]{self.title}[/]"
            )
            yield Static(title_markup, id="confirm-title")
            yield Static(self.body, id="confirm-body")
            if self.required_confirmation_text:
                yield Input(
                    placeholder=f"Type {self.required_confirmation_text} to confirm",
                    id="confirm-input",
                )
            help_text = (
                "Type the exact name, then [bold]Y[/] or [bold]Enter[/] to confirm; "
                "[bold]N[/] or [bold]Esc[/] cancels."
                if self.required_confirmation_text
                else "[bold]Y[/] or [bold]Enter[/] to confirm; "
                "[bold]N[/] or [bold]Esc[/] to cancel."
            )
            yield Static(help_text, id="confirm-help")
            with Horizontal(id="confirm-buttons"):
                variant = "error" if self.danger else "primary"
                yield Button(self.confirm_label, id="confirm-yes", variant=variant)
                yield Button(self.cancel_label, id="confirm-no", variant="default")

    def on_mount(self) -> None:
        if self.required_confirmation_text:
            self.query_one("#confirm-input", Input).focus()
        else:
            self.query_one("#confirm-yes", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-yes":
            self.action_confirm()
        else:
            self.action_cancel()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "confirm-input":
            self.action_confirm()

    def action_confirm(self) -> None:
        if self.required_confirmation_text:
            value = self.query_one("#confirm-input", Input).value.strip()
            if value != self.required_confirmation_text:
                self.query_one("#confirm-help", Static).update(
                    "[red]Type the exact resource name to confirm.[/]"
                )
                return
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)
