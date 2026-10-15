"""Step bodies, built from the form model (TUI redesign 01 §2.2, §3.2; PR 5).

Each ``build_*`` function returns the widgets of one step, with their initial
values taken from ``FormState``. ``BenchmarkApp`` mounts a step's widgets the
first time the step is shown (03 §1.1), so startup lays out step 1 only.

Field tiers (01 §2.2): every-run fields sit in the step body; "sometimes"
fields sit behind one **More options** disclosure on step 3; expert fields are
on the Expert settings screen (F8). Privacy and compliance fields are never
in either: they are all visible on step 4 and repeated in Review.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, Tuple

from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Input, Label, OptionList, Select, Static

from core import labels
from tui.form_state import COMPLETE_OUTPUT, FormState, VERIFIED_SAFE_COVERAGE
from tui.form_widgets import (
    ColumnSelect,
    Disclosure,
    EntityChooser,
    EntityIndex,
    ModeSwitch,
    SELECT_BLANK,
)
from tui.widgets import BoxCheckbox, BoxSelectionList

RELEASE_MODE_OPTIONS: Tuple[Tuple[str, str], ...] = (
    ("Complete output", COMPLETE_OUTPUT),
    ("Verified safe coverage", VERIFIED_SAFE_COVERAGE),
)
RELEASE_MODE_HINTS = {
    COMPLETE_OUTPUT: "Writes every output the privacy rules allow.",
    VERIFIED_SAFE_COVERAGE: (
        "Publishes only units verified safe; missing units are privacy-suppressed. "
        "Coverage is not a maximum claim. Rule sweep is forced on."
    ),
}
OUTPUT_FORMAT_CODES = ("analysis", "publication", "both")

# Widget id -> FormState field, for the bound controls of the main screen.
WIDGET_FIELDS = {
    "csv_path": "csv_path",
    "entity_col": "entity_col",
    "mode_switch": "mode",
    "share_metric": "metric",
    "rate_total": "total_col",
    "rate_approved": "approved_col",
    "rate_fraud": "fraud_col",
    "dims": "dimensions",
    "auto_dim": "auto_dims",
    "secondary": "secondary",
    "time_col": "time_col",
    "output_format": "output_format",
    "output_file": "output_file",
    "validate_input": "validate_input",
    "analyze_distortion": "analyze_distortion",
    "compare_presets": "compare_presets",
    "export_csv": "export_balanced_csv",
    "include_calculated": "include_calculated",
    "fraud_in_bps": "fraud_in_bps",
    "preset_select": "preset",
    "privacy_release_mode": "release_mode",
    "privacy_rule_sweep_mode": "rule_sweep",
    "privacy_merchant_spend_scope": "merchant_spend",
    "citi_competitor_receives_output": "citi_competitor",
}
FIELD_WIDGETS = {name: widget_id for widget_id, name in WIDGET_FIELDS.items()}
FIELD_WIDGETS["entity"] = "entity_chooser"
FIELD_WIDGETS["entity_filter"] = "entity_chooser"
FIELD_WIDGETS["citibank_entity"] = "citibank_chooser"
FIELD_WIDGETS["citibank_filter"] = "citibank_chooser"

# Widget id -> step, for every widget readiness or "jump to field" can name,
# whether or not its step is mounted yet.
WIDGET_STEPS = {
    "btn_browse_csv": "data",
    "csv_path": "data",
    "entity_col": "entity",
    "entity_name": "entity",
    "entity_filter": "entity",
    "entity_matches": "entity",
    "mode_switch": "analysis",
    "share_metric": "analysis",
    "rate_total": "analysis",
    "rate_approved": "analysis",
    "rate_fraud": "analysis",
    "dims": "analysis",
    "auto_dim": "analysis",
    "more_options": "analysis",
    "btn_expert": "analysis",
    "secondary": "analysis",
    "time_col": "analysis",
    "output_format": "analysis",
    "output_file": "analysis",
    "validate_input": "analysis",
    "analyze_distortion": "analysis",
    "compare_presets": "analysis",
    "export_csv": "analysis",
    "include_calculated": "analysis",
    "fraud_in_bps": "analysis",
    "preset_select": "privacy",
    "privacy_release_mode": "privacy",
    "privacy_rule_sweep_mode": "privacy",
    "privacy_merchant_spend_scope": "privacy",
    "citi_competitor_receives_output": "privacy",
    "citibank_entity_name": "privacy",
    "citibank_entity_filter": "privacy",
    "review_blockers": "review",
    "btn_run": "review",
    "btn_clear_restored": "review",
}
# Field labels that show ↺ when their value was restored (01 §8.1).
PAIR_LABELS = {
    "entity_col": ("lbl_entity_col", "Entity column"),
    "mode": ("lbl_mode_switch", "Mode"),
    "metric": ("lbl_share_metric", "Metric"),
    "total_col": ("lbl_rate_total", "Total column"),
    "approved_col": ("lbl_rate_approved", "Approved column"),
    "fraud_col": ("lbl_rate_fraud", "Fraud column"),
    "dimensions": ("dims_label", "Dimensions"),
    "time_col": ("lbl_time_col", "Time column"),
    "secondary": ("lbl_secondary", "Secondary metrics"),
    "output_format": ("lbl_output_format", "Output format"),
    "preset": ("lbl_preset_select", "Preset"),
    "release_mode": ("privacy_release_mode_label", "Release mode"),
    "rule_sweep": ("lbl_rule_sweep", "Rule strategy"),
}
# Display-only widgets the app updates, by step.
WIDGET_STEPS.update(
    {
        "csv_meta": "data",
        "entity_chooser": "entity",
        "entity_count": "entity",
        "share_fields": "analysis",
        "rate_fields": "analysis",
        "dims_label": "analysis",
        "dims_hint": "analysis",
        "fraud_in_bps_row": "analysis",
        "fraud_in_bps_hint": "analysis",
        "expert_summary": "analysis",
        "release_mode_row": "privacy",
        "release_mode_rate_note": "privacy",
        "privacy_release_mode_hint": "privacy",
        "sweep_lock_note": "privacy",
        "citibank_chooser": "privacy",
        "citibank_entity_hint": "privacy",
        "posture_line": "privacy",
        "preset_blurb": "privacy",
        "review_status": "review",
        "review_summary": "review",
        "review_blockers_hint": "review",
    }
)
for _field, (_label_id, _) in PAIR_LABELS.items():
    WIDGET_STEPS.setdefault(_label_id, "entity" if _field == "entity_col" else ("privacy" if _field in ("preset", "release_mode", "rule_sweep") else "analysis"))
# Fields inside the More options disclosure (it opens before they are focused).
MORE_OPTIONS_WIDGETS = frozenset(
    {
        "secondary",
        "time_col",
        "output_format",
        "output_file",
        "validate_input",
        "analyze_distortion",
        "compare_presets",
        "export_csv",
        "include_calculated",
        "fraud_in_bps",
    }
)


@dataclass(frozen=True)
class StepContext:
    """What the builders need besides the form: dataset and preset facts."""

    form: FormState
    loaded: bool
    entity_values: Sequence[str]
    entity_index: Optional[EntityIndex]
    entity_loading: bool
    preset_options: Sequence[Tuple[str, str]]
    launch_folder: str
    csv_meta: Any


def _pair(label: str, *widgets: Widget, label_id: Optional[str] = None, hint: Any = None, hint_id: Optional[str] = None) -> Vertical:
    """One compact field row: a label column, the field, then an indented hint (01 §3.2)."""
    if label_id is None and widgets and widgets[0].id:
        label_id = f"lbl_{widgets[0].id}"
    row = Horizontal(Label(label, classes="field-label", id=label_id), *widgets, classes="field-pair field-row")
    children: List[Widget] = [row]
    if hint is not None:
        children.append(Static(hint, classes="field-hint field-hint-indented", id=hint_id))
    return Vertical(*children, classes="field-block")


def build_data(ctx: StepContext) -> List[Widget]:
    form = ctx.form
    return [
        Label("1 · Data — which file?", classes="step-title"),
        Vertical(
            Horizontal(
                Button("Browse ^O", id="btn_browse_csv", variant="default", compact=True),
                Input(
                    value=form.csv_path,
                    placeholder="path/to/data.csv  (relative to the launch folder)",
                    id="csv_path",
                    classes="file-input",
                    compact=True,
                ),
                classes="ab-row",
            ),
            Static(ctx.csv_meta, id="csv_meta", classes="field-hint-indented"),
            id="section_data",
            classes="form-section",
        ),
        Static(
            f"Launch folder  {ctx.launch_folder}\n"
            "Relative paths and reports are resolved from here.",
            id="launch_folder",
            classes="field-hint",
        ),
    ]


def _column_select(
    widget_id: str, ctx: StepContext, value: Optional[str], *, numeric_first: bool, disabled: bool = False
) -> ColumnSelect:
    numeric, other = ctx.form.numeric_first()
    primary, secondary = (numeric, other) if numeric_first else (other, numeric)
    return ColumnSelect(
        primary,
        secondary,
        value=value,
        mark=ctx.form.numeric_columns,
        prompt="Select column…" if ctx.loaded else "Load a CSV first",
        id=widget_id,
        disabled=disabled,
    )


def build_entity(ctx: StepContext) -> List[Widget]:
    form = ctx.form
    chooser = EntityChooser(
        "entity_name",
        "entity",
        values=ctx.entity_values,
        index=ctx.entity_index,
        choice=form.entity,
        text=form.entity_filter,
        loaded=ctx.loaded,
        loading=ctx.entity_loading,
        id="entity_chooser",
    )
    return [
        Label("2 · Entity — who is benchmarked?", classes="step-title"),
        Vertical(
            _pair("Entity column", _column_select("entity_col", ctx, form.entity_col, numeric_first=False)),
            _pair(
                "Target entity",
                chooser,
                hint="↑↓ or type letters to jump · blank = peer-only benchmark\n"
                "Chosen fresh every run. Never restored from a session.",
            ),
            Static("", id="entity_count", classes="field-hint"),
            id="section_entity",
            classes="form-section",
        ),
    ]


def build_mode_fields(ctx: StepContext, mode: str) -> List[Widget]:
    """The share (metric) or rate (total, approved, fraud) fields of step 3."""
    form = ctx.form
    if mode == "share":
        return [_pair("Metric", _column_select("share_metric", ctx, form.metric, numeric_first=True))]
    return [
        _pair(
            "Total column",
            _column_select("rate_total", ctx, form.total_col, numeric_first=True),
            hint="The denominator. No default: pick the governed clearing-spend column.",
        ),
        _pair("Approved column", _column_select("rate_approved", ctx, form.approved_col, numeric_first=True)),
        _pair(
            "Fraud column",
            _column_select("rate_fraud", ctx, form.fraud_col, numeric_first=True),
            hint="Approved or fraud is required. Fraud asks you to confirm that "
            "Total is clearing spend on every run.",
        ),
    ]


# Fields that mount with their mode's group (BenchmarkApp._ensure_mode_fields).
MODE_FIELD_WIDGETS = {"share": frozenset({"share_metric"}), "rate": frozenset({"rate_total", "rate_approved", "rate_fraud"})}


def build_analysis(ctx: StepContext) -> List[Widget]:
    form = ctx.form
    # Only the active mode's fields mount with the step; the other mode's
    # mount the first time the mode is switched (step 3 shows one group).
    share = Vertical(
        *(build_mode_fields(ctx, "share") if form.mode == "share" else []),
        id="share_fields",
        classes="mode-fields",
    )
    share.display = form.mode == "share"
    rate = Vertical(
        *(build_mode_fields(ctx, "rate") if form.mode == "rate" else []),
        id="rate_fields",
        classes="mode-fields",
    )
    rate.display = form.mode == "rate"
    dims = BoxSelectionList(*dimension_selections(form), id="dims", classes="multi-select")
    dims.display = not form.auto_dims
    # Its fields mount when it is first opened (BenchmarkApp._ensure_more_options):
    # most runs never open it, so step 3's first show does not lay them out.
    more = Disclosure(
        title=more_options_title(form),
        id="more_options",
        collapsed=True,
    )
    return [
        Label("3 · Analysis & mode", classes="step-title"),
        Vertical(
            _pair("Mode", ModeSwitch(form.mode, id="mode_switch")),
            share,
            rate,
            Vertical(
                Horizontal(
                    Label("Dimensions", classes="field-label", id="dims_label"),
                    Static(
                        "␣ toggles · letters jump · # numeric · roles hidden",
                        classes="field-hint",
                        id="dims_hint",
                    ),
                    classes="field-pair field-row",
                ),
                dims,
                BoxCheckbox("Auto-detect dimensions instead", value=form.auto_dims, id="auto_dim", compact=True),
                classes="field-block dims-block",
            ),
            id="section_mode",
            classes="form-section",
        ),
        more,
        Horizontal(
            Button("Expert settings… F8", id="btn_expert", variant="default", compact=True),
            Static("", id="expert_summary", classes="field-hint"),
            classes="ab-row",
            id="expert_row",
        ),
    ]


def dimension_selections(form: FormState) -> List[Tuple[str, str, bool]]:
    chosen = set(form.dimensions)
    return [(label_with_mark(form, c), c, c in chosen) for c in form.dimension_options()]


def secondary_selections(form: FormState) -> List[Tuple[str, str, bool]]:
    chosen = set(form.secondary)
    return [(c, c, c in chosen) for c in form.secondary_options()]


def label_with_mark(form: FormState, column: str) -> str:
    return f"{column} #" if column in form.numeric_columns else column


def more_options_title(form: FormState) -> str:
    changed = form.more_options_changed()
    summary = "all default" if not changed else f"{changed} changed"
    return f"More options · time column, secondary metrics, outputs · {summary}"


def build_more_options(ctx: StepContext) -> List[Widget]:
    form = ctx.form
    fraud_bps = BoxCheckbox(
        "Fraud in basis points (publication workbook)", value=form.fraud_in_bps, id="fraud_in_bps", compact=True
    )
    include = BoxCheckbox(
        "Include calculated metrics in the CSV", value=form.include_calculated, id="include_calculated", compact=True
    )
    return [
        Vertical(
            _pair("Time column", _column_select("time_col", ctx, form.time_col, numeric_first=False)),
            _pair(
                "Secondary metrics",
                BoxSelectionList(*secondary_selections(form), id="secondary", classes="multi-select"),
            ),
            _pair(
                "Output format",
                Select(
                    [(labels.text_for(labels.OUTPUT_FORMAT, code), code) for code in OUTPUT_FORMAT_CODES],
                    id="output_format",
                    value=form.output_format,
                    allow_blank=False,
                    compact=True,
                ),
            ),
            Vertical(
                fraud_bps,
                Static("", id="fraud_in_bps_hint", classes="field-hint"),
                id="fraud_in_bps_row",
                classes="nested-option field-block",
            ),
            _pair(
                "Output file",
                Input(
                    value=form.output_file,
                    placeholder="auto: named after mode, entity and time",
                    id="output_file",
                    compact=True,
                ),
                hint="Written to the launch folder unless you give a path. Review shows the full path.",
            ),
            Vertical(
                BoxCheckbox(
                    "Validate input before running (recommended)",
                    value=form.validate_input,
                    id="validate_input",
                    compact=True,
                ),
                BoxCheckbox(
                    "Analyze impact (distortion summary)",
                    value=form.analyze_distortion,
                    id="analyze_distortion",
                    compact=True,
                ),
                BoxCheckbox(
                    "Compare all presets (slower: runs every preset)",
                    value=form.compare_presets,
                    id="compare_presets",
                    compact=True,
                ),
                BoxCheckbox(
                    "Export balanced CSV (written only if privacy allows)",
                    value=form.export_balanced_csv,
                    id="export_csv",
                    compact=True,
                ),
                Vertical(include, classes="nested-option"),
                classes="ab-checks",
            ),
            id="more_options_form",
        )
    ]


def build_privacy(ctx: StepContext) -> List[Widget]:
    form = ctx.form
    preset_values = {value for _, value in ctx.preset_options}
    preset = Select(
        list(ctx.preset_options),
        prompt="Select preset…",
        id="preset_select",
        value=form.preset if form.preset in preset_values else SELECT_BLANK,
        compact=True,
    )
    release = Select(
        list(RELEASE_MODE_OPTIONS),
        id="privacy_release_mode",
        value=form.release_mode,
        allow_blank=False,
        compact=True,
    )
    release_pair = _pair(
        "Release mode",
        release,
        label_id="privacy_release_mode_label",
        hint=RELEASE_MODE_HINTS.get(form.release_mode, ""),
        hint_id="privacy_release_mode_hint",
    )
    release_pair.id = "release_mode_row"
    release_pair.display = form.mode == "share"
    rate_note = Horizontal(
        Label("Release mode", classes="field-label"),
        Static("not used for rate analysis", classes="field-hint"),
        id="release_mode_rate_note",
        classes="field-pair field-row",
    )
    rate_note.display = form.mode != "share"
    sweep = BoxCheckbox(
        "Sweep every applicable privacy rule",
        value=form.effective_sweep,
        id="privacy_rule_sweep_mode",
        compact=True,
        disabled=form.sweep_locked,
    )
    citi_chooser = EntityChooser(
        "citibank_entity_name",
        "citibank_entity",
        values=ctx.entity_values,
        index=ctx.entity_index,
        choice=form.citibank_entity,
        text=form.citibank_filter,
        loaded=ctx.loaded,
        loading=ctx.entity_loading,
        subject="Citibank entity",
        blank_prompt="Pick the exact Citibank value",
        blank_hint="Pick the exact Citibank value.",
        no_match_hint="Pick the exact Citibank value from the list.",
        casefold_match=True,
        enabled=form.citi_competitor,
        id="citibank_chooser",
    )
    declarations = Vertical(
        BoxCheckbox(
            "Data is anonymized, aggregated merchant spend (enables rule 4/35)",
            value=form.merchant_spend,
            id="privacy_merchant_spend_scope",
            compact=True,
        ),
        BoxCheckbox(
            "A Citi competitor will receive this output (adds the 25% Citi cap)",
            value=form.citi_competitor,
            id="citi_competitor_receives_output",
            compact=True,
        ),
        Vertical(
            Horizontal(
                Label("Citibank entity", classes="field-label", id="citibank_entity_label"),
                citi_chooser,
                classes="field-pair field-row",
            ),
            Static("", id="citibank_entity_hint", classes="field-hint field-hint-indented"),
            classes="field-block nested-option",
        ),
        id="compliance_declarations",
        classes="ab-panel",
    )
    declarations.border_title = "Declarations · check before every run · never saved between sessions"
    return [
        Label("4 · Privacy & compliance", classes="step-title"),
        Vertical(
            _pair("Preset", preset),
            Vertical(
                Horizontal(
                    Label("Posture", classes="field-label"),
                    Static("", id="posture_line"),
                    classes="field-pair field-row",
                ),
                Static("", id="preset_blurb", classes="field-hint field-hint-indented"),
                classes="field-block",
            ),
            release_pair,
            rate_note,
            Vertical(
                Horizontal(
                    Label("Rule strategy", classes="field-label", id="lbl_rule_sweep"),
                    sweep,
                    classes="field-pair field-row",
                ),
                Static("", id="sweep_lock_note", classes="field-hint field-hint-indented"),
                classes="field-block",
            ),
            id="section_privacy",
            classes="form-section",
        ),
        declarations,
    ]


def build_review(ctx: StepContext) -> List[Widget]:
    blockers = OptionList(id="review_blockers", classes="review-blockers")
    blockers.display = False
    clear = Button("Clear restored values", id="btn_clear_restored", variant="default", compact=True)
    clear.display = bool(ctx.form.restored)
    return [
        Label("5 · Review & run", classes="step-title"),
        Static("", id="review_status"),
        blockers,
        Static("", id="review_blockers_hint", classes="field-hint"),
        Static("", id="review_summary"),
        Horizontal(
            Button("Run share analysis ^R", id="btn_run", variant="primary", compact=True),
            clear,
            classes="ab-row",
            id="review_buttons",
        ),
    ]


BUILDERS = {
    "data": build_data,
    "entity": build_entity,
    "analysis": build_analysis,
    "privacy": build_privacy,
    "review": build_review,
}
