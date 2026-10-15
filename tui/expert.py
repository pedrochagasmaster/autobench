"""Expert settings screen (F8) and the expert diff (TUI redesign 01 §2.2, §8.2).

Replaces the Advanced collapsible. Expert edits are an **in-memory diff
against the current preset**, held in ``FormState.expert`` and keyed by
``ConfigFieldSpec.widget_id``. There is no Apply button and no override file
between runs: at run time a non-empty diff is written once through
``PresetWorkflow.write_override_file`` with the current preset's posture
(``BenchmarkApp._collect_run_inputs``). Owner decision 2: that file is
written to the launch folder and left there.

A blank field means "inherit the preset"; the source column says ``preset``,
``engine default`` or ``● changed · preset <value>``.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, Static

from tui.keybar import KeyBar
from tui.widgets import BoxCheckbox
from utils.config_overrides import ConfigFieldSpec, try_parse_number

# (group title, [(widget id, label, placeholder)]). Labels say which value
# they are (01 E.9): "LP max iterations" vs "Bayesian max iterations".
EXPERT_GROUPS: Tuple[Tuple[str, Tuple[Tuple[str, str, str], ...]], ...] = (
    (
        "Linear programming",
        (
            ("adv_lp_tolerance", "Tolerance (pp)", "e.g. 2.0"),
            ("adv_lp_max_iterations", "LP max iterations", "e.g. 1000"),
            ("adv_lp_lambda_penalty", "Lambda penalty", "e.g. 100"),
            ("adv_lp_volume_weighting_exponent", "Volume weighting exponent", "e.g. 1.5"),
            ("adv_lp_volume_weighted_penalties", "Volume-weighted penalties", ""),
        ),
    ),
    (
        "Constraints and bounds",
        (
            ("adv_constraints_volume_preservation", "Volume preservation (0–1)", "0.0 - 1.0"),
            ("adv_bounds_min_weight", "Min weight", "e.g. 0.01"),
            ("adv_bounds_max_weight", "Max weight", "e.g. 10.0"),
        ),
    ),
    (
        "Subset search",
        (
            ("adv_subset_enabled", "Subset search enabled", ""),
            ("adv_subset_strategy", "Strategy (greedy / random)", "greedy / random"),
            ("adv_subset_max_attempts", "Max attempts", "e.g. 200"),
            ("adv_subset_max_slack_threshold", "Max slack threshold", "e.g. 0.05"),
            ("adv_subset_trigger_on_slack", "Trigger on slack", ""),
            ("adv_subset_prefer_slacks_first", "Prefer slacks first", ""),
        ),
    ),
    (
        "Bayesian optimization (fallback)",
        (
            ("adv_bayes_max_iterations", "Bayesian max iterations", "e.g. 100"),
            ("adv_bayes_learning_rate", "Learning rate", "e.g. 0.01"),
        ),
    ),
    (
        "Analysis",
        (("adv_analysis_bic_percentile", "Best-in-class percentile (0–1)", "e.g. 0.85"),),
    ),
    (
        "Output sheets",
        (("adv_output_privacy_validation", "Privacy validation sheet", ""),),
    ),
)
EXPERT_LABELS: Dict[str, str] = {wid: label for _, rows in EXPERT_GROUPS for wid, label, _ in rows}


def _same(spec: ConfigFieldSpec, value: Any, preset_value: Any) -> bool:
    if spec.kind == "checkbox":
        return bool(value) == bool(preset_value)
    if preset_value is None:
        return False
    parsed = try_parse_number(str(value).strip())
    if parsed == preset_value:
        return True
    return str(value).strip() == str(preset_value)


def diff_with(
    specs: Sequence[ConfigFieldSpec],
    diff: Mapping[str, Any],
    widget_id: str,
    value: Any,
    preset_values: Mapping[str, Any],
) -> Dict[str, Any]:
    """``diff`` with one field set to ``value`` (blank or equal to the preset drops it)."""
    spec = next(s for s in specs if s.widget_id == widget_id)
    out = dict(diff)
    out.pop(widget_id, None)
    if spec.kind == "input":
        text = "" if value is None else str(value).strip()
        if text and not _same(spec, text, preset_values.get(widget_id)):
            out[widget_id] = text
    elif not _same(spec, value, preset_values.get(widget_id)):
        out[widget_id] = bool(value)
    return out


def rebase_diff(
    specs: Sequence[ConfigFieldSpec], diff: Mapping[str, Any], preset_values: Mapping[str, Any]
) -> Dict[str, Any]:
    """Drop the entries a new preset already holds (a programmatic preset change)."""
    known = {spec.widget_id for spec in specs}
    out: Dict[str, Any] = {}
    for widget_id, value in diff.items():
        if widget_id in known:
            out = diff_with(specs, out, widget_id, value, preset_values)
    return out


def effective_values(
    specs: Sequence[ConfigFieldSpec], diff: Mapping[str, Any], preset_values: Mapping[str, Any]
) -> Dict[str, Any]:
    """Preset values with the diff on top, keyed by widget id (export, display)."""
    values: Dict[str, Any] = {}
    for spec in specs:
        if spec.widget_id in diff:
            values[spec.widget_id] = diff[spec.widget_id]
        else:
            preset_value = preset_values.get(spec.widget_id)
            if spec.kind == "checkbox":
                values[spec.widget_id] = bool(preset_value)
            else:
                values[spec.widget_id] = "" if preset_value is None else str(preset_value)
    return values


def source_text(spec: ConfigFieldSpec, diff: Mapping[str, Any], preset_values: Mapping[str, Any]) -> str:
    preset_value = preset_values.get(spec.widget_id)
    if spec.widget_id in diff:
        shown = "off" if spec.kind == "checkbox" and not preset_value else (
            "on" if spec.kind == "checkbox" else ("·" if preset_value is None else str(preset_value))
        )
        return f"● changed · preset {shown}"
    return "preset" if preset_value is not None else "engine default"


def expert_changes_text(count: int, *, short: bool = False) -> str:
    """``3 changes from preset`` (``short``: ``3 expert changes``)."""
    plural = "s" if count != 1 else ""
    if short:
        return f"{count} expert change{plural}"
    return "no changes from preset" if not count else f"{count} change{plural} from preset"


changes_text = expert_changes_text


class ExpertScreen(ModalScreen[None]):
    """Full-screen Expert settings over the main screen. Esc returns."""

    BINDINGS = [
        Binding("escape", "close_expert", "Done"),
        # F8 again closes it (modal screens do not see the app's F8).
        Binding("f8", "close_expert", "Done", show=False),
        Binding("f9", "export", "Export", show=False),
    ]
    # The app's -narrow/-wide breakpoints style the main screen only; setting
    # them here would restyle the whole Expert screen right after it composes.
    HORIZONTAL_BREAKPOINTS: list = []

    def __init__(
        self,
        *,
        specs: Sequence[ConfigFieldSpec],
        preset: Optional[str],
        preset_values: Mapping[str, Any],
        diff: Mapping[str, Any],
        debug: bool,
        posture_text: str,
    ) -> None:
        super().__init__()
        self.specs = list(specs)
        self._specs_by_id = {spec.widget_id: spec for spec in self.specs}
        self.preset = preset
        self.preset_values = dict(preset_values)
        self.diff = dict(diff)
        self.debug = debug
        self.posture_text = posture_text

    # ── Layout ─────────────────────────────────────────────────────────

    def _header(self) -> str:
        # Fits one line at 80 columns for the shipped preset names.
        count = len(self.diff)
        changes = "no changes" if not count else f"{count} change{'s' if count != 1 else ''}"
        return f"Expert settings · {self.preset or '—'} · {changes} · posture stays {self.posture_text}"

    def compose(self) -> ComposeResult:
        values = effective_values(self.specs, self.diff, self.preset_values)
        with Vertical(id="expert_container", classes="ab-modal"):
            yield Static(self._header(), id="expert_header", classes="ab-title")
            yield Static(
                "On top of the preset, for this session's runs. Blank = inherit the preset. "
                "A preset change asks before resetting these. Esc = done.",
                id="expert_hint",
                classes="field-hint",
            )
            with Horizontal(id="expert_buttons", classes="ab-row"):
                yield Button("Reset all to preset", id="btn_expert_reset", compact=True)
                yield Button("Export to file… F9", id="btn_expert_export", compact=True)
            export_path = Static("", id="expert_export_path", classes="ab-path")
            export_path.display = False
            yield export_path
            with VerticalScroll(id="expert_body"):
                for title, rows in EXPERT_GROUPS:
                    yield Label(title, classes="adv-group-title")
                    # One 3-column grid per group (label · value · source):
                    # far fewer containers than a row widget per field.
                    cells: list = []
                    if title == "Output sheets":
                        cells += self._row(
                            "Debug sheets",
                            BoxCheckbox("", value=self.debug, id="debug_sheets", compact=True),
                            Static("sent as the debug request field", classes="expert-source"),
                        )
                    for widget_id, label, placeholder in rows:
                        spec = self._specs_by_id.get(widget_id)
                        if spec is None:
                            continue
                        if spec.kind == "checkbox":
                            control: Any = BoxCheckbox(
                                "", value=bool(values[widget_id]), id=widget_id, compact=True
                            )
                        else:
                            control = Input(
                                value=str(values[widget_id]),
                                placeholder=placeholder or "·",
                                id=widget_id,
                                compact=True,
                            )
                        cells += self._row(
                            label,
                            control,
                            Static(
                                source_text(spec, self.diff, self.preset_values),
                                id=f"{widget_id}_source",
                                classes="expert-source",
                            ),
                        )
                    yield Grid(*cells, classes="expert-grid")
                yield Static("", id="privacy_validation_note", classes="field-hint")
        yield KeyBar("expert")

    @staticmethod
    def _row(label: str, control: Any, source: Static) -> list:
        return [Label(label, classes="expert-label"), control, source]

    def on_mount(self) -> None:
        self._sync_privacy_validation()
        # Synchronous binding: the diff never lags an edit.
        for spec in self.specs:
            try:
                control = self.query_one(f"#{spec.widget_id}")
            except Exception:
                continue
            self.watch(control, "value", self._watcher(spec.widget_id), init=False)
        self.watch(self.query_one("#debug_sheets", Checkbox), "value", self._debug_changed, init=False)
        first = self.query("#expert_body Input")
        if first:
            first.first().focus()

    def _watcher(self, widget_id: str) -> Any:
        def changed(value: Any) -> None:
            self._set(widget_id, value)

        return changed

    def _debug_changed(self, value: bool) -> None:
        self.app.form.debug = bool(value)  # type: ignore[attr-defined]
        self._sync_privacy_validation()

    def _sync_privacy_validation(self) -> None:
        """Privacy validation is always included while debug sheets are on (01 E.2)."""
        try:
            box = self.query_one("#adv_output_privacy_validation", Checkbox)
            note = self.query_one("#privacy_validation_note", Static)
        except Exception:
            return
        debug = bool(self.query_one("#debug_sheets", Checkbox).value)
        box.disabled = debug
        note.update("Privacy validation sheet: always included while debug sheets are on." if debug else "")

    # ── Edits ──────────────────────────────────────────────────────────

    def _set(self, widget_id: str, value: Any) -> None:
        if widget_id not in self._specs_by_id:
            return
        self.diff = self.app.set_expert_value(widget_id, value)  # type: ignore[attr-defined]
        self._refresh_sources()

    def _refresh_sources(self) -> None:
        for spec in self.specs:
            try:
                self.query_one(f"#{spec.widget_id}_source", Static).update(
                    source_text(spec, self.diff, self.preset_values)
                )
            except Exception:
                continue
        self.query_one("#expert_header", Static).update(self._header())

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()  # Handled synchronously by the value watchers.

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        event.stop()  # Handled synchronously by the value watchers.

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "btn_expert_reset":
            self.action_reset()
        elif event.button.id == "btn_expert_export":
            self.action_export()

    def action_reset(self) -> None:
        self.app.reset_expert()  # type: ignore[attr-defined]
        self.diff = {}
        values = effective_values(self.specs, self.diff, self.preset_values)
        with self.app.batch_update():
            for spec in self.specs:
                try:
                    widget = self.query_one(f"#{spec.widget_id}")
                except Exception:
                    continue
                widget.value = values[spec.widget_id]
        self._refresh_sources()

    def action_export(self) -> None:
        path = self.app.export_advanced_overrides()  # type: ignore[attr-defined]
        if path:
            line = self.query_one("#expert_export_path", Static)
            line.update(f"Exported to {path}")
            line.display = True

    def action_close_expert(self) -> None:
        self.dismiss(None)

