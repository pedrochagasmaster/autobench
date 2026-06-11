"""Privacy-Compliant Peer Benchmark Tool — Textual TUI.

Production layout: a scrollable configuration pane on the left and a live
activity pane (run status, last-run summary, execution log) on the right.
All analysis execution flows through the shared ``core.analysis_run`` seam,
so behaviour stays identical to the CLI.
"""

import os
import sys
import time
import logging
import threading
import glob
import pandas as pd
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
import yaml

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Header,
    Footer,
    Input,
    Button,
    Select,
    Checkbox,
    Label,
    TabbedContent,
    TabPane,
    Log,
    Static,
    ListView,
    ListItem,
    SelectionList,
    Markdown,
    Collapsible,
    DirectoryTree,
)
from datetime import datetime
from textual import work
from textual.css.query import NoMatches
from textual.screen import ModalScreen

# Import shared run orchestration and adapter dependencies.
sys.path.append(str(Path(__file__).parent))
try:
    from core.analysis_run import (
        RunAborted,
        RunBlocked,
        build_run_config,
        prepare_run_data,
        resolve_dimensions,
        validate_analysis_input,
        execute_run,
    )
    from core.contracts import AnalysisRunRequest, PreparedDataset
    from core.preset_workflow import PresetWorkflow
    from utils.logger import setup_logging
    from utils.config_manager import ConfigManager
    from utils.config_overrides import (
        ADVANCED_FIELD_MAP,
        ConfigOverrideBuilder,
        nested_get,
        nested_set,
        try_parse_number,
    )
    from core.data_loader import ValidationIssue, ValidationSeverity
except ImportError as e:
    # Fallback for when running in a different context or if imports fail
    print(f"Error importing benchmark modules: {e}")
    sys.exit(1)

# Textual >= 0.89 renamed the Select no-selection sentinel from BLANK to NULL;
# Select.BLANK now resolves to Widget.BLANK (False), so compare against the
# real sentinel to detect "nothing selected" reliably.
SELECT_BLANK = getattr(Select, "NULL", getattr(Select, "BLANK", None))

LOG_DIR = Path("outputs") / "logs"
SESSION_FILE = Path.home() / ".benchmark_tui" / "session.yaml"

SESSION_INPUT_IDS = ("csv_path", "output_file")
SESSION_SELECT_IDS = (
    "entity_col",
    "entity_name",
    "time_col",
    "preset_select",
    "output_format",
    "share_metric",
    "rate_total",
    "rate_approved",
    "rate_fraud",
)
SESSION_CHECKBOX_IDS = (
    "analyze_distortion",
    "compare_presets",
    "validate_input",
    "include_calculated",
    "share_auto_dim",
    "share_debug",
    "share_export_csv",
    "rate_auto_dim",
    "rate_debug",
    "rate_export_csv",
    "fraud_in_bps",
)
SESSION_SELECTION_LIST_IDS = ("share_dims", "share_secondary", "rate_dims", "rate_secondary")


def write_log_message(log_widget: Log, message: str) -> None:
    """Write to a Textual Log from the app thread or a worker thread."""
    try:
        app = log_widget.app
    except Exception:
        # Widget is no longer attached to a running app (e.g. after exit).
        return
    if app is None:
        return
    text = message if message.endswith("\n") else f"{message}\n"
    if getattr(app, "_thread_id", None) == threading.get_ident():
        log_widget.write(text)
    else:
        app.call_from_thread(log_widget.write, text)


class LogHandler(logging.Handler):
    """Custom logging handler to send logs to a Textual Log widget."""
    def __init__(self, log_widget: Log):
        super().__init__()
        self.log_widget = log_widget

    def emit(self, record):
        msg = self.format(record)
        write_log_message(self.log_widget, msg)


class FileListItem(ListItem):
    """Custom ListItem that stores the file path."""
    def __init__(self, file_path: str) -> None:
        super().__init__(Label(file_path))
        self.file_path = file_path


class CsvDirectoryTree(DirectoryTree):
    """Directory tree limited to directories and CSV files."""

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        keep = []
        for path in paths:
            name = path.name
            if name.startswith(".") or name == "__pycache__":
                continue
            if path.is_dir() or path.suffix.lower() == ".csv":
                keep.append(path)
        return keep


class CsvPickerScreen(ModalScreen[Optional[str]]):
    """Modal CSV picker: quick picks from known data folders plus a full tree."""

    BINDINGS = [("escape", "cancel_picker", "Cancel")]

    def __init__(self, quick_picks: List[str]) -> None:
        super().__init__()
        self.quick_picks = quick_picks

    def compose(self) -> ComposeResult:
        with Container(id="picker_container"):
            yield Label("Select a CSV file", id="picker_title")
            with Horizontal(id="picker_body"):
                with Vertical(id="picker_quick"):
                    yield Label("Quick picks", classes="picker-subtitle")
                    yield ListView(
                        *[FileListItem(path) for path in self.quick_picks],
                        id="picker_quick_list",
                    )
                with Vertical(id="picker_tree_pane"):
                    yield Label("Browse workspace", classes="picker-subtitle")
                    yield CsvDirectoryTree(os.getcwd(), id="picker_tree")
            yield Label(
                "Enter to select · Escape to cancel",
                classes="picker-hint",
            )
            yield Button("Cancel", id="btn_picker_cancel", variant="default")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, FileListItem):
            self.dismiss(event.item.file_path)

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        self.dismiss(str(event.path))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_picker_cancel":
            self.dismiss(None)

    def action_cancel_picker(self) -> None:
        self.dismiss(None)


class ConfirmScreen(ModalScreen[bool]):
    """Small yes/no confirmation dialog."""

    BINDINGS = [("escape", "cancel_confirm", "Cancel")]

    def __init__(self, message: str, confirm_label: str = "Confirm") -> None:
        super().__init__()
        self.message = message
        self.confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        with Container(id="confirm_container"):
            yield Label(self.message, id="confirm_message")
            with Horizontal(id="confirm_buttons"):
                yield Button(self.confirm_label, id="btn_confirm_yes", variant="error")
                yield Button("Cancel", id="btn_confirm_no", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn_confirm_yes")

    def action_cancel_confirm(self) -> None:
        self.dismiss(False)


class PresetHelpScreen(ModalScreen):
    """Screen to show preset help."""

    BINDINGS = [("escape", "close_help", "Close")]

    CSS = """
    PresetHelpScreen {
        align: center middle;
        background: rgba(0,0,0,0.7);
    }

    #help_container {
        width: 70%;
        max-width: 100;
        height: 80%;
        border: round $primary;
        background: $surface;
        padding: 1 2;
    }

    #help_text {
        height: 1fr;
        margin-top: 1;
        margin-bottom: 1;
        overflow-y: auto;
    }

    #btn_close_help {
        width: 100%;
        dock: bottom;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="help_container"):
            yield Label("Preset Guide", classes="section-title")
            yield Markdown(
                """
### compliance_strict
- **Intent:** "I cannot have any privacy violations."
- **Best For:** Regulatory reporting, external audits.
- **Trade-off:** May drop dimensions if they violate privacy rules.

### strategic_consistency
- **Intent:** "I need one set of weights for all dimensions."
- **Best For:** Strategic analysis, executive dashboards.
- **Trade-off:** Minimizes business impact of violations but may allow small ones.

### balanced_default
- **Intent:** "I want a good report with minimal fuss."
- **Best For:** Day-to-day analysis.
- **Trade-off:** Good balance, allows very small violations (2%).

### low_distortion
- **Intent:** "I want low distortion while keeping privacy constraints."
- **Best For:** Accuracy-focused analysis with modest consistency needs.
- **Trade-off:** Allows higher tolerance to keep results close to raw data.

### minimal_distortion
- **Intent:** "Maximize accuracy even if consistency suffers."
- **Best For:** Research or validation where raw fidelity matters most.
- **Trade-off:** Highest tolerance and volume-weighted penalties.

### research_exploratory
- **Intent:** "This dataset is difficult, just give me numbers."
- **Best For:** Data exploration, difficult datasets.
- **Trade-off:** Lower rank preservation, higher weight bounds.
                """,
                id="help_text"
            )
            yield Button("Close", id="btn_close_help", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_close_help":
            self.dismiss()

    def action_close_help(self) -> None:
        self.dismiss()


class ValidationModal(ModalScreen):
    """Modal to display validation issues and allow proceed/cancel."""

    BINDINGS = [("escape", "cancel_validation", "Cancel")]

    def __init__(self, issues: List[ValidationIssue]) -> None:
        super().__init__()
        self.issues = issues
        self.has_errors = any(i.severity == ValidationSeverity.ERROR for i in issues)

    def compose(self) -> ComposeResult:
        error_count = sum(1 for i in self.issues if i.severity == ValidationSeverity.ERROR)
        warning_count = sum(1 for i in self.issues if i.severity == ValidationSeverity.WARNING)

        with Container(id="validation_container"):
            yield Label("Data Validation Results", id="validation_title")

            with Horizontal(classes="field-pair"):
                yield Label(f"Errors: {error_count}", classes="issue-error" if error_count > 0 else "")
                yield Label(f"  Warnings: {warning_count}", classes="issue-warning" if warning_count > 0 else "")

            yield ListView(id="issue_list")

            with Horizontal(classes="input-group"):
                yield Button("Proceed", id="btn_proceed", variant="success", disabled=self.has_errors)
                yield Button("Cancel", id="btn_cancel", variant="error")

    def on_mount(self) -> None:
        """Populate the list view."""
        list_view = self.query_one("#issue_list")
        for issue in self.issues:
            severity_cls = "issue-error" if issue.severity == ValidationSeverity.ERROR else "issue-warning"
            label = Label(f"[{issue.severity.value}] {issue.message}", classes=severity_cls)
            if issue.row_indices:
                row_preview = ", ".join(str(i) for i in issue.row_indices[:10])
                sub_label = Label(f"  Rows: {row_preview}", classes="subsection-title")
                item = ListItem(Vertical(label, sub_label), classes="issue-item")
            else:
                item = ListItem(label, classes="issue-item")
            list_view.append(item)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_proceed":
            self.dismiss(True)  # Return True to proceed
        elif event.button.id == "btn_cancel":
            self.dismiss(False)  # Return False to cancel

    def action_cancel_validation(self) -> None:
        self.dismiss(False)


class BenchmarkApp(App):
    """Privacy-Compliant Peer Benchmark Tool TUI"""

    BINDINGS = [
        ("ctrl+o", "open_file", "Open CSV"),
        ("ctrl+r", "run_analysis", "Run"),
        ("f1", "show_help", "Preset Guide"),
        ("ctrl+a", "toggle_advanced", "Advanced"),
        ("ctrl+e", "export_advanced", "Export Adv"),
        ("ctrl+l", "clear_log", "Clear Log"),
    ]

    ADVANCED_FIELD_MAP: List[Dict[str, Any]] = ADVANCED_FIELD_MAP

    CSS = """
    #app_body {
        height: 1fr;
    }

    /* ── Left: configuration pane ─────────────────────────────── */
    #config_pane {
        width: 58%;
        min-width: 64;
        padding: 0 1;
        scrollbar-gutter: stable;
    }

    .form-section {
        border: round $primary 40%;
        border-title-color: $text-accent;
        border-title-style: bold;
        padding: 0 2;
        margin: 0 0 1 0;
        height: auto;
    }

    .form-section:focus-within {
        border: round $primary;
    }

    .section-title {
        text-style: bold;
        margin-top: 1;
        margin-bottom: 1;
    }

    .subsection-title {
        text-style: italic;
        color: $text-muted;
        margin-bottom: 0;
    }

    .field-label {
        color: $text;
        margin-top: 1;
    }

    .field-hint {
        color: $text-muted;
        margin-bottom: 1;
    }

    .field-pair {
        height: auto;
    }

    .input-group {
        height: auto;
        margin-bottom: 1;
    }

    .input-group Input, .input-group Select {
        width: 1fr;
        margin-right: 1;
    }

    .split-inputs {
        height: auto;
        margin-bottom: 1;
    }

    .split-inputs Input, .split-inputs Select {
        width: 1fr;
        margin-right: 1;
    }

    Input {
        margin-bottom: 1;
    }

    Select {
        margin-bottom: 1;
    }

    #csv_meta {
        color: $text-muted;
        margin-bottom: 1;
    }

    #btn_run {
        width: 100%;
        margin-top: 1;
        margin-bottom: 1;
    }

    TabbedContent {
        height: auto;
    }

    .multi-select {
        height: 7;
        border: round $primary 40%;
        margin-bottom: 1;
    }

    .multi-select:focus {
        border: round $primary;
    }

    .hidden {
        display: none;
    }

    #btn_preset_help {
        min-width: 16;
    }

    /* ── Right: activity pane ─────────────────────────────────── */
    #activity_pane {
        width: 1fr;
        min-width: 42;
        padding: 0 1;
    }

    #run_status {
        border: round $primary 40%;
        border-title-color: $text-accent;
        border-title-style: bold;
        padding: 0 2;
        height: auto;
        min-height: 5;
        margin-bottom: 1;
    }

    #results_panel {
        border: round $primary 40%;
        border-title-color: $text-accent;
        border-title-style: bold;
        padding: 0 2;
        height: auto;
        max-height: 14;
        margin-bottom: 1;
        overflow-y: auto;
    }

    #log_output {
        height: 1fr;
        min-height: 8;
        border: round $primary 40%;
        border-title-color: $text-accent;
        border-title-style: bold;
        background: $surface;
        padding: 0 1;
    }

    /* ── Advanced Optimization Section ────────────────────────── */
    #advanced_opt {
        border: round $accent 60%;
        padding: 0 1;
        margin-top: 0;
        margin-bottom: 1;
    }

    #advanced_form {
        height: auto;
    }

    .adv-group-title {
        text-style: bold;
        color: $warning;
        margin-top: 1;
        margin-bottom: 1;
    }

    .adv-field-label {
        color: $text;
        margin-bottom: 0;
    }

    #advanced_form .field-pair {
        margin-bottom: 0;
    }

    #advanced_form .input-group {
        margin-bottom: 0;
    }

    #advanced_form Input, #advanced_form Checkbox {
        margin-bottom: 1;
    }

    #advanced_form Button {
        margin-bottom: 0;
    }

    /* ── Validation modal ─────────────────────────────────────── */
    ValidationModal {
        align: center middle;
        background: rgba(0,0,0,0.7);
    }

    #validation_container {
        width: 80%;
        max-width: 110;
        height: 70%;
        background: $surface;
        border: round $primary;
        padding: 1 2;
    }

    #validation_title {
        text-style: bold;
        margin-bottom: 1;
        text-align: center;
        width: 100%;
    }

    #issue_list {
        height: 1fr;
        border: round $secondary;
        margin-bottom: 1;
        background: $boost;
    }

    .issue-item {
        height: auto;
        padding: 1;
        border-bottom: solid $primary 50%;
    }

    .issue-error {
        color: $error;
        text-style: bold;
    }

    .issue-warning {
        color: $warning;
    }

    /* ── CSV picker modal ─────────────────────────────────────── */
    CsvPickerScreen {
        align: center middle;
        background: rgba(0,0,0,0.7);
    }

    #picker_container {
        width: 84%;
        max-width: 120;
        height: 80%;
        background: $surface;
        border: round $primary;
        padding: 1 2;
    }

    #picker_title {
        text-style: bold;
        text-align: center;
        width: 100%;
        margin-bottom: 1;
    }

    #picker_body {
        height: 1fr;
    }

    #picker_quick {
        width: 40%;
        min-width: 28;
        margin-right: 2;
    }

    #picker_tree_pane {
        width: 1fr;
    }

    .picker-subtitle {
        text-style: bold;
        color: $text-accent;
        margin-bottom: 1;
    }

    .picker-hint {
        color: $text-muted;
        margin-top: 1;
    }

    #picker_quick_list, #picker_tree {
        height: 1fr;
        border: round $primary 40%;
        background: $boost;
    }

    #btn_picker_cancel {
        width: 100%;
        margin-top: 1;
    }

    /* ── Confirm modal ────────────────────────────────────────── */
    ConfirmScreen {
        align: center middle;
        background: rgba(0,0,0,0.7);
    }

    #confirm_container {
        width: 60;
        height: auto;
        background: $surface;
        border: round $error;
        padding: 1 2;
    }

    #confirm_message {
        width: 100%;
        margin-bottom: 1;
    }

    #confirm_buttons {
        height: auto;
        align-horizontal: center;
    }

    #confirm_buttons Button {
        margin-right: 2;
    }
    """

    TITLE = "Privacy-Compliant Peer Benchmark"
    SUB_TITLE = "Control 3.2 dimensional analysis"

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header(show_clock=True)

        with Horizontal(id="app_body"):
            # ═══════════════════════════════════════════════════════════
            # LEFT — CONFIGURATION
            # ═══════════════════════════════════════════════════════════
            with VerticalScroll(id="config_pane"):
                with Container(id="section_data", classes="form-section") as section:
                    section.border_title = "1 · Data Source"
                    yield Label("CSV file path", classes="field-label")
                    with Horizontal(classes="input-group"):
                        yield Button("Browse…", id="btn_browse_csv", variant="default")
                        yield Input(placeholder="path/to/data.csv", id="csv_path", classes="file-input")
                    yield Static("No file loaded.", id="csv_meta")

                with Container(id="section_entity", classes="form-section") as section:
                    section.border_title = "2 · Entity"
                    with Horizontal(classes="input-group"):
                        with Vertical(classes="field-pair"):
                            yield Label("Entity ID column", classes="field-label")
                            yield Select([], prompt="Select column…", id="entity_col")
                        with Vertical(classes="field-pair"):
                            yield Label("Target entity (blank = peer-only)", classes="field-label")
                            yield Select([], prompt="Select entity…", id="entity_name", allow_blank=True)

                with Container(id="section_analysis", classes="form-section") as section:
                    section.border_title = "3 · Analysis Options"
                    with Horizontal(classes="input-group"):
                        with Vertical(classes="field-pair"):
                            yield Label("Time period column (optional)", classes="field-label")
                            yield Select([], prompt="Select column…", id="time_col", allow_blank=True)
                        with Vertical(classes="field-pair"):
                            yield Label("Output filename", classes="field-label")
                            yield Input(placeholder="Auto-generated if blank", id="output_file")

                    yield Label("Optimization preset", classes="field-label")
                    with Horizontal(classes="input-group"):
                        yield Select([], prompt="Select preset…", id="preset_select")
                        yield Button("Preset Guide", id="btn_preset_help", variant="default")
                    yield Static("", id="preset_blurb", classes="field-hint")

                    with Horizontal(classes="input-group"):
                        yield Checkbox("Analyze impact", value=True, id="analyze_distortion")
                        yield Checkbox("Compare presets", id="compare_presets")
                        yield Checkbox("Validate input", id="validate_input", value=True)
                    with Horizontal(classes="input-group"):
                        yield Checkbox("Include calc. metrics (CSV)", id="include_calculated")
                        yield Checkbox("Acknowledge accuracy-first", id="acknowledge_accuracy_first")
                    with Horizontal(classes="input-group"):
                        with Vertical(classes="field-pair"):
                            yield Label("Output format", classes="field-label")
                            yield Select(
                                [("Analysis", "analysis"), ("Publication", "publication"), ("Both", "both")],
                                id="output_format",
                                value="analysis",
                                allow_blank=False,
                            )

                # ───────────────────────────────────────────────────────
                # ADVANCED OPTIMIZATION (collapsed by default)
                # ───────────────────────────────────────────────────────
                with Collapsible(title="Advanced Optimization Parameters", id="advanced_opt", collapsed=True):
                    with Vertical(id="advanced_form"):
                        yield Label("Linear Programming", classes="adv-group-title")
                        with Horizontal(classes="input-group"):
                            with Vertical(classes="field-pair"):
                                yield Label("Tolerance (pp)", classes="adv-field-label")
                                yield Input(placeholder="e.g., 2.0", id="adv_lp_tolerance")
                            with Vertical(classes="field-pair"):
                                yield Label("Max Iterations", classes="adv-field-label")
                                yield Input(placeholder="e.g., 1000", id="adv_lp_max_iterations")
                        with Horizontal(classes="input-group"):
                            with Vertical(classes="field-pair"):
                                yield Label("Lambda Penalty", classes="adv-field-label")
                                yield Input(placeholder="e.g., 100", id="adv_lp_lambda_penalty")
                            with Vertical(classes="field-pair"):
                                yield Label("Volume Weighting Exponent", classes="adv-field-label")
                                yield Input(placeholder="e.g., 1.5", id="adv_lp_volume_weighting_exponent")
                        with Horizontal(classes="input-group"):
                            yield Checkbox("Enable Volume-Weighted Penalties", id="adv_lp_volume_weighted_penalties")

                        yield Label("Constraints", classes="adv-group-title")
                        with Horizontal(classes="input-group"):
                            with Vertical(classes="field-pair"):
                                yield Label("Volume Preservation", classes="adv-field-label")
                                yield Input(placeholder="0.0 - 1.0", id="adv_constraints_volume_preservation")

                        yield Label("Weight Bounds", classes="adv-group-title")
                        with Horizontal(classes="input-group"):
                            with Vertical(classes="field-pair"):
                                yield Label("Min Weight", classes="adv-field-label")
                                yield Input(placeholder="e.g., 0.01", id="adv_bounds_min_weight")
                            with Vertical(classes="field-pair"):
                                yield Label("Max Weight", classes="adv-field-label")
                                yield Input(placeholder="e.g., 10.0", id="adv_bounds_max_weight")

                        yield Label("Subset Search", classes="adv-group-title")
                        with Horizontal(classes="input-group"):
                            yield Checkbox("Enable Subset Search", id="adv_subset_enabled")
                            with Vertical(classes="field-pair"):
                                yield Label("Strategy", classes="adv-field-label")
                                yield Input(placeholder="greedy / random", id="adv_subset_strategy")
                        with Horizontal(classes="input-group"):
                            with Vertical(classes="field-pair"):
                                yield Label("Max Attempts", classes="adv-field-label")
                                yield Input(placeholder="e.g., 200", id="adv_subset_max_attempts")
                            with Vertical(classes="field-pair"):
                                yield Label("Max Slack Threshold", classes="adv-field-label")
                                yield Input(placeholder="e.g., 0.05", id="adv_subset_max_slack_threshold")
                        with Horizontal(classes="input-group"):
                            yield Checkbox("Trigger on Slack", id="adv_subset_trigger_on_slack")
                            yield Checkbox("Prefer Slacks First", id="adv_subset_prefer_slacks_first")

                        yield Label("Bayesian Optimization (Fallback)", classes="adv-group-title")
                        with Horizontal(classes="input-group"):
                            with Vertical(classes="field-pair"):
                                yield Label("Max Iterations", classes="adv-field-label")
                                yield Input(placeholder="e.g., 100", id="adv_bayes_max_iterations")
                            with Vertical(classes="field-pair"):
                                yield Label("Learning Rate", classes="adv-field-label")
                                yield Input(placeholder="e.g., 0.01", id="adv_bayes_learning_rate")

                        yield Label("Analysis Settings", classes="adv-group-title")
                        with Horizontal(classes="input-group"):
                            with Vertical(classes="field-pair"):
                                yield Label("Best-in-Class Percentile", classes="adv-field-label")
                                yield Input(placeholder="0.0 - 1.0 (e.g., 0.85)", id="adv_analysis_bic_percentile")

                        yield Label("Output Settings", classes="adv-group-title")
                        with Horizontal(classes="input-group"):
                            yield Checkbox("Include Debug Sheets", id="adv_output_debug_sheets")
                            yield Checkbox("Include Privacy Validation", id="adv_output_privacy_validation")

                        with Horizontal(classes="input-group"):
                            yield Button("Apply Overrides", id="btn_apply_advanced", variant="primary")
                            yield Button("Export Config", id="btn_export_advanced", variant="default")
                        yield Label("Values override preset when applied.", classes="subsection-title")

                # ───────────────────────────────────────────────────────
                # ANALYSIS MODE TABS
                # ───────────────────────────────────────────────────────
                with Container(id="section_mode", classes="form-section") as section:
                    section.border_title = "4 · Analysis Mode"
                    with TabbedContent(initial="share_tab"):
                        with TabPane("Share Analysis", id="share_tab"):
                            with Vertical(classes="field-pair"):
                                yield Label("Primary metric column", classes="field-label")
                                yield Select([], prompt="Select column…", id="share_metric")

                            with Vertical(classes="field-pair"):
                                yield Label("Secondary metrics (optional)", classes="field-label")
                                yield SelectionList(id="share_secondary", classes="multi-select")

                            yield Label("Dimension options", classes="subsection-title")
                            with Horizontal(classes="input-group"):
                                yield Checkbox("Auto-detect dimensions", value=False, id="share_auto_dim")
                                yield Checkbox("Debug sheets", value=True, id="share_debug")
                                yield Checkbox("Export balanced CSV", value=True, id="share_export_csv")

                            yield Label("Manual dimension selection", id="share_dims_label", classes="field-label")
                            yield SelectionList(id="share_dims", classes="multi-select")

                        with TabPane("Rate Analysis", id="rate_tab"):
                            with Vertical(classes="field-pair"):
                                yield Label("Total column (denominator)", classes="field-label")
                                yield Select([], prompt="Select column…", id="rate_total")
                            with Horizontal(classes="split-inputs"):
                                with Vertical(classes="field-pair"):
                                    yield Label("Approved column", classes="field-label")
                                    yield Select([], prompt="Select column…", id="rate_approved", allow_blank=True)
                                with Vertical(classes="field-pair"):
                                    yield Label("Fraud column", classes="field-label")
                                    yield Select([], prompt="Select column…", id="rate_fraud", allow_blank=True)

                            with Vertical(classes="field-pair"):
                                yield Label("Secondary metrics (optional)", classes="field-label")
                                yield SelectionList(id="rate_secondary", classes="multi-select")

                            yield Label("Dimension options", classes="subsection-title")
                            with Horizontal(classes="input-group"):
                                yield Checkbox("Auto-detect dimensions", value=False, id="rate_auto_dim")
                                yield Checkbox("Debug sheets", value=True, id="rate_debug")
                                yield Checkbox("Export balanced CSV", value=False, id="rate_export_csv")
                                yield Checkbox("Fraud in BPS", value=True, id="fraud_in_bps")

                            yield Label("Manual dimension selection", id="rate_dims_label", classes="field-label")
                            yield SelectionList(id="rate_dims", classes="multi-select")

                yield Button("▶  Run Analysis", id="btn_run", variant="primary")

            # ═══════════════════════════════════════════════════════════
            # RIGHT — ACTIVITY
            # ═══════════════════════════════════════════════════════════
            with Vertical(id="activity_pane"):
                status = Static(id="run_status")
                status.border_title = "Run Status"
                yield status

                results = Static("No runs yet.", id="results_panel")
                results.border_title = "Last Run"
                yield results

                log = Log(id="log_output", highlight=True)
                log.border_title = "Execution Log"
                yield log

        yield Footer()

    # ──────────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        """Event handler called when widget is added to the app."""
        self.theme = "tokyo-night"
        self._run_state = "idle"
        self._run_started_at: Optional[float] = None
        self._run_mode: Optional[str] = None
        self._elapsed_timer = None
        self.load_presets()
        self.setup_logging_capture()
        self._refresh_run_status()
        self._restore_session()

        # Set initial focus
        self.query_one("#csv_path").focus()
        self.notify(
            "Ctrl+O browse · Ctrl+R run · Ctrl+A advanced · Ctrl+L clear log · F1 preset guide",
            title="Keyboard shortcuts",
            severity="information",
            timeout=6,
        )

    def on_unmount(self) -> None:
        """Detach this app's log handlers so logging never hits a dead widget."""
        root_logger = logging.getLogger()
        for handler in list(root_logger.handlers):
            if isinstance(handler, LogHandler):
                root_logger.removeHandler(handler)


    # ──────────────────────────────────────────────────────────────────
    # Session persistence
    # ──────────────────────────────────────────────────────────────────

    def _collect_session(self) -> Dict[str, Any]:
        session: Dict[str, Any] = {}
        for widget_id in SESSION_INPUT_IDS:
            try:
                session[widget_id] = self.query_one(f"#{widget_id}", Input).value
            except NoMatches:
                continue
        for widget_id in SESSION_SELECT_IDS:
            try:
                value = self.query_one(f"#{widget_id}", Select).value
            except NoMatches:
                continue
            session[widget_id] = None if value == SELECT_BLANK else value
        for widget_id in SESSION_CHECKBOX_IDS:
            try:
                session[widget_id] = self.query_one(f"#{widget_id}", Checkbox).value
            except NoMatches:
                continue
        for widget_id in SESSION_SELECTION_LIST_IDS:
            try:
                session[widget_id] = list(self.query_one(f"#{widget_id}", SelectionList).selected)
            except NoMatches:
                continue
        return session

    def _save_session(self) -> None:
        try:
            SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(SESSION_FILE, "w", encoding="utf-8") as handle:
                yaml.safe_dump(self._collect_session(), handle, sort_keys=False)
        except Exception:
            # Session persistence is best-effort; never block the user on it.
            logging.getLogger(__name__).debug("Could not save TUI session", exc_info=True)

    def _restore_session(self) -> None:
        if not SESSION_FILE.is_file():
            return
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as handle:
                session = yaml.safe_load(handle) or {}
        except Exception:
            logging.getLogger(__name__).debug("Could not load TUI session", exc_info=True)
            return
        if not isinstance(session, dict):
            return

        csv_path = session.get("csv_path") or ""
        if csv_path and os.path.isfile(csv_path):
            self.query_one("#csv_path", Input).value = csv_path
            self.load_csv_headers(csv_path, announce=False)
        # Entity options depend on the entity column, so populate them
        # synchronously before restoring the target-entity selection.
        entity_col = session.get("entity_col")
        if entity_col:
            try:
                self.query_one("#entity_col", Select).value = entity_col
                self.load_unique_entities(entity_col)
            except Exception:
                pass
        for widget_id in SESSION_SELECT_IDS:
            if widget_id == "entity_col":
                continue
            value = session.get(widget_id)
            if value is None:
                continue
            try:
                select = self.query_one(f"#{widget_id}", Select)
            except NoMatches:
                continue
            try:
                select.value = value
            except Exception:
                continue  # Stored value no longer valid for this dataset/presets.
        for widget_id in SESSION_CHECKBOX_IDS:
            if widget_id not in session:
                continue
            try:
                self.query_one(f"#{widget_id}", Checkbox).value = bool(session[widget_id])
            except NoMatches:
                continue
        for widget_id in SESSION_SELECTION_LIST_IDS:
            values = session.get(widget_id)
            if not isinstance(values, list):
                continue
            try:
                s_list = self.query_one(f"#{widget_id}", SelectionList)
            except NoMatches:
                continue
            available = {
                s_list.get_option_at_index(index).value
                for index in range(s_list.option_count)
            }
            for value in values:
                if value in available:
                    s_list.select(value)
        output_file = session.get("output_file")
        if output_file:
            self.query_one("#output_file", Input).value = str(output_file)

    # ──────────────────────────────────────────────────────────────────
    # Run status / results panels
    # ──────────────────────────────────────────────────────────────────

    _STATE_BADGES = {
        "idle": "[dim]●[/dim] [b]Ready[/b]",
        "running": "[yellow]●[/yellow] [b yellow]Running[/b yellow]",
        "success": "[green]●[/green] [b green]Success[/b green]",
        "error": "[red]●[/red] [b red]Failed[/b red]",
        "blocked": "[red]●[/red] [b red]Blocked[/b red]",
    }

    def _refresh_run_status(self) -> None:
        badge = self._STATE_BADGES.get(self._run_state, self._STATE_BADGES["idle"])
        lines = [badge]
        preset = None
        try:
            preset_val = self.query_one("#preset_select", Select).value
            preset = None if preset_val == SELECT_BLANK else preset_val
        except NoMatches:
            pass
        mode = self._run_mode or self._analysis_mode()
        lines.append(f"[dim]Mode[/dim]    {mode}")
        lines.append(f"[dim]Preset[/dim]  {preset or '—'}")
        if self._run_started_at is not None and self._run_state == "running":
            elapsed = time.monotonic() - self._run_started_at
            lines.append(f"[dim]Elapsed[/dim] {elapsed:.0f}s")
        try:
            self.query_one("#run_status", Static).update("\n".join(lines))
        except NoMatches:
            pass

    def _begin_run_ui(self) -> None:
        """Switch UI into the running state (app thread only)."""
        self._run_state = "running"
        self._run_started_at = time.monotonic()
        self._run_mode = self._analysis_mode()
        btn = self.query_one("#btn_run", Button)
        btn.disabled = True
        btn.label = "Running…"
        if self._elapsed_timer is not None:
            self._elapsed_timer.stop()
        self._elapsed_timer = self.set_interval(1.0, self._refresh_run_status)
        self._refresh_run_status()
        self._save_session()

    def _end_run_ui(self, state: str, summary_markup: str) -> None:
        """Restore UI after a run and publish the last-run summary (app thread only)."""
        self._run_state = state
        if self._elapsed_timer is not None:
            self._elapsed_timer.stop()
            self._elapsed_timer = None
        elapsed = None
        if self._run_started_at is not None:
            elapsed = time.monotonic() - self._run_started_at
        self._run_started_at = None
        btn = self.query_one("#btn_run", Button)
        btn.disabled = False
        btn.label = "▶  Run Analysis"
        self._refresh_run_status()

        header = self._STATE_BADGES.get(state, "")
        if elapsed is not None:
            header += f"  [dim]({elapsed:.1f}s · {datetime.now().strftime('%H:%M:%S')})[/dim]"
        self.query_one("#results_panel", Static).update(f"{header}\n{summary_markup}".strip())

    def _reset_run_ui(self) -> None:
        """Re-enable the run controls after an aborted launch (app thread only)."""
        self._run_state = "idle"
        if self._elapsed_timer is not None:
            self._elapsed_timer.stop()
            self._elapsed_timer = None
        self._run_started_at = None
        btn = self.query_one("#btn_run", Button)
        btn.disabled = False
        btn.label = "▶  Run Analysis"
        self._refresh_run_status()

    def _fail_launch(self, message: str, focus_id: Optional[str] = None) -> None:
        """Notify about an invalid launch and return UI to idle (worker-safe)."""
        log_widget = self.query_one("#log_output", Log)
        write_log_message(log_widget, f"ERROR: {message}")
        self.call_from_thread(self.notify, message, title="Cannot run", severity="error")
        self.call_from_thread(self._reset_run_ui)
        if focus_id:
            def _focus() -> None:
                try:
                    self.query_one(f"#{focus_id}").focus()
                except NoMatches:
                    pass
            self.call_from_thread(_focus)

    # ──────────────────────────────────────────────────────────────────
    # CSV loading
    # ──────────────────────────────────────────────────────────────────

    def _quick_pick_files(self) -> List[str]:
        """CSV files from the working directory and known data folders."""
        patterns = ("*.csv", "data/*.csv", "tests/fixtures/*.csv")
        seen: List[str] = []
        for pattern in patterns:
            for match in sorted(glob.glob(pattern)):
                if match not in seen:
                    seen.append(match)
        return seen

    def _resolve_csv_path(self, raw_path: str) -> Optional[str]:
        """Normalize and validate a CSV path from manual entry or browse."""
        csv_path = raw_path.strip()
        if not csv_path:
            return None
        if not os.path.isfile(csv_path):
            self.notify(
                f"CSV file not found: {csv_path}",
                title="Invalid Path",
                severity="error",
                timeout=6,
            )
            self.query_one("#log_output").write(f"CSV file not found: {csv_path}\n")
            return None
        return csv_path

    def _try_load_csv_from_path_input(self) -> None:
        """Load headers when the user submits or leaves the CSV path field."""
        csv_path = self._resolve_csv_path(self.query_one("#csv_path").value)
        if csv_path:
            self.load_csv_headers(csv_path)

    def load_csv_headers(self, file_path, announce: bool = True):
        """Load CSV headers and populate Select widgets."""
        try:
            resolved = self._resolve_csv_path(file_path)
            if not resolved:
                return
            file_path = resolved
            # Read only headers
            cols = pd.read_csv(file_path, nrows=0).columns.tolist()
            self.csv_columns = cols
            options = [(c, c) for c in cols]
            selection_options = [(c, c) for c in cols]

            # Update Select widgets, preserving still-valid selections
            for select_id in ("entity_col", "time_col", "share_metric", "rate_total", "rate_approved", "rate_fraud"):
                select = self.query_one(f"#{select_id}", Select)
                previous = select.value
                select.set_options(options)
                if previous != SELECT_BLANK and previous in cols:
                    select.value = previous

            # Update SelectionLists, preserving still-valid selections
            for list_id in ["#share_secondary", "#share_dims", "#rate_secondary", "#rate_dims"]:
                s_list = self.query_one(list_id, SelectionList)
                previously_selected = set(s_list.selected)
                s_list.clear_options()
                s_list.add_options(
                    [(label, value, value in previously_selected) for label, value in selection_options]
                )

            # Fill smart defaults for selects that are still empty
            defaults = {
                "entity_col": "issuer_name",
                "share_metric": "txn_cnt",
                "rate_total": "txn_cnt",
                "rate_approved": "app_cnt",
            }
            for select_id, column in defaults.items():
                select = self.query_one(f"#{select_id}", Select)
                if column in cols and select.value == SELECT_BLANK:
                    select.value = column

            self._update_csv_meta(file_path, cols)
            if announce:
                self.notify(
                    f"Loaded {len(cols)} columns from {os.path.basename(file_path)}",
                    title="CSV Loaded",
                    severity="information",
                    timeout=5,
                )

        except Exception as e:
            self.query_one("#log_output").write(f"Error reading CSV headers: {e}\n")
            self.notify(f"Failed to read CSV: {e}", title="CSV Error", severity="error")

    def _update_csv_meta(self, file_path: str, cols: List[str]) -> None:
        """Show a compact summary of the loaded file under the path field."""
        try:
            size_bytes = os.path.getsize(file_path)
            if size_bytes >= 1024 * 1024:
                size_text = f"{size_bytes / (1024 * 1024):.1f} MB"
            elif size_bytes >= 1024:
                size_text = f"{size_bytes / 1024:.1f} KB"
            else:
                size_text = f"{size_bytes} B"
        except OSError:
            size_text = "?"
        preview = ", ".join(cols[:6]) + ("…" if len(cols) > 6 else "")
        self.query_one("#csv_meta", Static).update(
            f"[green]✓[/green] {os.path.basename(file_path)} · {len(cols)} columns · {size_text}\n[dim]{preview}[/dim]"
        )

    def update_secondary_options(self, list_id, exclude=None):
        """Update options in a SelectionList, excluding specified values."""
        if not hasattr(self, 'csv_columns'):
            return

        if exclude is None:
            exclude = []

        s_list = self.query_one(list_id, SelectionList)
        current_selected = set(s_list.selected)

        s_list.clear_options()

        options = []
        for col in self.csv_columns:
            if col in exclude:
                continue
            # Preserve selection state if possible
            is_selected = col in current_selected
            options.append((col, col, is_selected))

        s_list.add_options(options)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter in text inputs."""
        if event.input.id == "csv_path":
            self._try_load_csv_from_path_input()

    def on_input_blurred(self, event: Input.Blurred) -> None:
        """Handle focus leaving text inputs."""
        if event.input.id == "csv_path":
            self._try_load_csv_from_path_input()

    # ──────────────────────────────────────────────────────────────────
    # Presets / advanced overrides
    # ──────────────────────────────────────────────────────────────────

    def load_presets(self):
        """Load available presets through the shared preset workflow."""
        self.preset_workflow = PresetWorkflow()
        presets = self.preset_workflow.list_presets()
        options = [(preset, preset) for preset in presets] or [("standard", "standard")]
        self.query_one("#preset_select").set_options(options)
        self.query_one("#preset_select").value = options[0][0] if options else None
        if options:
            self.update_advanced_parameters(options[0][0])
            self._update_preset_blurb(options[0][0])
        self.advanced_config_path = None

    def _update_preset_blurb(self, preset_name: str) -> None:
        """Show the preset's own description under the selector."""
        description = ""
        try:
            data = self.preset_workflow.load_preset_data(preset_name)
            if isinstance(data, dict):
                description = str(data.get("description") or "")
        except Exception:
            description = ""
        try:
            self.query_one("#preset_blurb", Static).update(description)
        except NoMatches:
            pass

    @staticmethod
    def _nested_get(data: Dict[str, Any], keys: Tuple[str, ...]) -> Any:
        return nested_get(data, keys)

    @staticmethod
    def _nested_set(data: Dict[str, Any], keys: Tuple[str, ...], value: Any) -> None:
        nested_set(data, keys, value)

    @staticmethod
    def _try_parse_number(value: str) -> Any:
        return try_parse_number(value)

    def _warn_missing_widget(self, widget_id: str) -> None:
        logging.getLogger(__name__).warning("Advanced widget not found: %s", widget_id)
        self.notify(
            f"Advanced widget missing: {widget_id}",
            title="Advanced Optimization",
            severity="warning",
            timeout=4,
        )

    def _safe_set_input(self, field_id: str, value: Any) -> None:
        try:
            self.query_one(f"#{field_id}", Input).value = str(value)
        except NoMatches:
            self._warn_missing_widget(field_id)

    def _safe_set_checkbox(self, field_id: str, value: Any) -> None:
        try:
            self.query_one(f"#{field_id}", Checkbox).value = bool(value)
        except NoMatches:
            self._warn_missing_widget(field_id)

    def _get_input(self, field_id: str) -> str:
        try:
            return self.query_one(f"#{field_id}", Input).value.strip()
        except NoMatches:
            self._warn_missing_widget(field_id)
            return ""

    def _get_bool(self, checkbox_id: str) -> bool:
        try:
            return self.query_one(f"#{checkbox_id}", Checkbox).value
        except NoMatches:
            self._warn_missing_widget(checkbox_id)
            return False

    def _read_field_value_from_preset(self, data: Dict[str, Any], spec: Dict[str, Any]) -> Any:
        specs_by_widget = {field.widget_id: field for field in ConfigOverrideBuilder().specs}
        field_spec = specs_by_widget.get(spec["widget_id"])
        if field_spec is None:
            return None
        return ConfigOverrideBuilder().read_field(data, field_spec)

    def _load_advanced_parameter_data(self, preset_name: str) -> Dict[str, Any]:
        if not hasattr(self, 'preset_workflow'):
            self.preset_workflow = PresetWorkflow()

        raw_data = self.preset_workflow.load_preset_data(preset_name)
        if not raw_data:
            return {}

        try:
            return ConfigManager(preset=preset_name).config
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Falling back to raw preset data for advanced parameters: %s",
                exc,
            )
            return raw_data

    def update_advanced_parameters(self, preset_name: str) -> None:
        """Populate editable advanced optimization inputs from preset YAML."""
        for inp in self.query("Input"):
            if inp.id and inp.id.startswith("adv_"):
                inp.value = ""
        for cb in self.query("Checkbox"):
            if cb.id and cb.id.startswith("adv_"):
                cb.value = False

        data = self._load_advanced_parameter_data(preset_name)
        if not data:
            return

        for spec in self.ADVANCED_FIELD_MAP:
            value = self._read_field_value_from_preset(data, spec)
            if value is None:
                continue
            if spec["kind"] == "input":
                self._safe_set_input(spec["widget_id"], value)
            else:
                self._safe_set_checkbox(spec["widget_id"], value)

    def _collect_advanced_override_data(self) -> Dict[str, Any]:
        values: Dict[str, Any] = {}
        for spec in self.ADVANCED_FIELD_MAP:
            widget_id = spec["widget_id"]
            values[widget_id] = self._get_bool(widget_id) if spec["kind"] == "checkbox" else self._get_input(widget_id)
        return ConfigOverrideBuilder().read_from_mapping(values)

    def apply_advanced_overrides(self) -> None:
        """Generate a temporary YAML config file from advanced inputs and set path for analysis."""
        yaml_data = self._collect_advanced_override_data()
        if not yaml_data:
            self.notify("No advanced values provided", title="Advanced Overrides", severity="warning", timeout=4)
            return

        posture = "strict"
        preset_val = self.query_one("#preset_select").value
        if preset_val and preset_val != SELECT_BLANK:
            if not hasattr(self, 'preset_workflow'):
                self.preset_workflow = PresetWorkflow()
            preset_data = self.preset_workflow.load_preset_data(str(preset_val))
            if isinstance(preset_data, dict):
                posture = preset_data.get("compliance_posture", posture)

        try:
            if not hasattr(self, 'preset_workflow'):
                self.preset_workflow = PresetWorkflow()
            tmp_path = self.preset_workflow.write_override_file(yaml_data, posture=posture)
            self.advanced_config_path = str(tmp_path)
            self.notify(
                f"Advanced overrides applied (file: {tmp_path.name})",
                title="Advanced Overrides",
                severity="information",
                timeout=6,
            )
        except Exception as e:
            self.notify(f"Failed to write overrides: {e}", title="Advanced Overrides", severity="error", timeout=6)

    def setup_logging_capture(self):
        """Redirect logging to the TUI Log widget."""
        log_widget = self.query_one("#log_output")
        handler = LogHandler(log_widget)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

        # Attach to root logger only (propagation will handle the rest)
        root_logger = logging.getLogger()
        for existing in list(root_logger.handlers):
            if isinstance(existing, LogHandler):
                root_logger.removeHandler(existing)
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)

        # Clear specific loggers to prevent duplication if they have handlers
        logging.getLogger("benchmark").handlers.clear()
        logging.getLogger("core").handlers.clear()

    # ──────────────────────────────────────────────────────────────────
    # Events / actions
    # ──────────────────────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn_browse_csv":
            self.action_open_file()

        elif event.button.id == "btn_run":
            self.run_analysis()

        elif event.button.id == "btn_preset_help":
            self.push_screen(PresetHelpScreen())
        elif event.button.id == "btn_apply_advanced":
            self.apply_advanced_overrides()
        elif event.button.id == "btn_export_advanced":
            self.export_advanced_overrides()

    def action_open_file(self) -> None:
        """Open the CSV picker modal (Ctrl+O)."""

        def on_picked(path: Optional[str]) -> None:
            if not path:
                return
            self.query_one("#csv_path", Input).value = path
            self.load_csv_headers(path)

        self.push_screen(CsvPickerScreen(self._quick_pick_files()), on_picked)

    def action_run_analysis(self) -> None:
        """Run analysis (Ctrl+R)."""
        self.run_analysis()

    def action_clear_log(self) -> None:
        """Clear the execution log (Ctrl+L)."""
        self.query_one("#log_output", Log).clear()

    def action_quit(self) -> None:
        """Quit, confirming first when an analysis is still running."""
        if self._run_state == "running":
            def on_confirm(confirmed: Optional[bool]) -> None:
                if confirmed:
                    self._save_session()
                    self.exit()

            self.push_screen(
                ConfirmScreen("An analysis is still running. Quit anyway?", confirm_label="Quit"),
                on_confirm,
            )
            return
        self._save_session()
        self.exit()

    def _analysis_mode(self) -> str:
        try:
            active = str(self.query_one(TabbedContent).active)
        except NoMatches:
            return "share"
        return "share" if active == "share_tab" else "rate"

    def action_show_help(self) -> None:
        """Show preset help (F1)."""
        self.push_screen(PresetHelpScreen())

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Handle checkbox toggles."""
        if event.checkbox.id == "share_auto_dim":
            if event.value:
                self.query_one("#share_dims").add_class("hidden")
                self.query_one("#share_dims_label").add_class("hidden")
            else:
                self.query_one("#share_dims").remove_class("hidden")
                self.query_one("#share_dims_label").remove_class("hidden")

        elif event.checkbox.id == "rate_auto_dim":
            if event.value:
                self.query_one("#rate_dims").add_class("hidden")
                self.query_one("#rate_dims_label").add_class("hidden")
            else:
                self.query_one("#rate_dims").remove_class("hidden")
                self.query_one("#rate_dims_label").remove_class("hidden")

    def load_unique_entities(self, column_name):
        """Load unique values from the specified column."""
        csv_path = self.query_one("#csv_path").value
        if not csv_path or not os.path.exists(csv_path):
            return

        try:
            # Read unique values from the column
            df = pd.read_csv(csv_path, usecols=[column_name])
            unique_vals = sorted(df[column_name].dropna().unique().astype(str).tolist())

            options = [(val, val) for val in unique_vals]
            entity_select = self.query_one("#entity_name", Select)
            previous = entity_select.value
            entity_select.set_options(options)
            if previous != SELECT_BLANK and previous in unique_vals:
                entity_select.value = previous

        except Exception as e:
            self.query_one("#log_output").write(f"Error loading entities: {e}\n")

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle select widget changes."""
        if event.select.id == "entity_col":
            if event.value != SELECT_BLANK:
                self.load_unique_entities(event.value)

        elif event.select.id == "share_metric":
            self.update_secondary_options("#share_secondary", exclude=[event.value])

        elif event.select.id == "rate_total":
            self.update_secondary_options("#rate_secondary", exclude=[event.value])

        elif event.select.id == "preset_select":
            if event.value != SELECT_BLANK:
                self.update_advanced_parameters(event.value)
                self._update_preset_blurb(str(event.value))
                self._refresh_run_status()
                if not self.query_one("#advanced_opt").collapsed:
                    self.notify(f"Preset '{event.value}' parameters refreshed", title="Advanced Optimization", severity="information", timeout=4)

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Keep the status panel's mode line current."""
        self._refresh_run_status()

    def action_toggle_advanced(self) -> None:
        """Toggle the advanced optimization collapsible (Ctrl+A)."""
        collapsible = self.query_one("#advanced_opt")
        collapsible.collapsed = not collapsible.collapsed
        if not collapsible.collapsed:
            preset_val = self.query_one("#preset_select").value
            if preset_val and preset_val != SELECT_BLANK:
                self.update_advanced_parameters(preset_val)
            self.notify("Advanced parameters visible", title="Advanced Optimization", severity="information", timeout=3)
        else:
            self.notify("Advanced parameters hidden", title="Advanced Optimization", severity="information", timeout=3)

    def action_export_advanced(self) -> None:
        """Keyboard shortcut to export advanced overrides (Ctrl+E)."""
        # Ensure overrides exist
        if self.query_one("#advanced_opt").collapsed:
            self.notify("Expanding advanced section to ensure values are current", title="Export Adv", severity="information", timeout=3)
            self.query_one("#advanced_opt").collapsed = False
            preset_val = self.query_one("#preset_select").value
            if preset_val and preset_val != SELECT_BLANK:
                self.update_advanced_parameters(preset_val)
        # Apply then export
        self.apply_advanced_overrides()
        self.export_advanced_overrides()

    def export_advanced_overrides(self) -> None:
        """Export current advanced override values to a timestamped YAML file (persistent)."""
        # Reuse apply collection logic without setting temporary file name
        if not getattr(self, 'advanced_config_path', None):
            # Create a temporary first if user hasn't applied
            self.apply_advanced_overrides()
            if not getattr(self, 'advanced_config_path', None):
                return
        preset_val = self.query_one("#preset_select").value or 'custom'
        try:
            tmp_path = Path(self.advanced_config_path)
            with open(tmp_path, 'r', encoding='utf-8') as f:
                content = yaml.safe_load(f) or {}
            if not hasattr(self, 'preset_workflow'):
                self.preset_workflow = PresetWorkflow()
            export_path = self.preset_workflow.export_override_file(content, preset_name=str(preset_val))
            self.notify(f"Exported advanced config: {export_path.name}", title="Advanced Export", severity="information", timeout=6)
        except Exception as e:
            self.notify(f"Failed export: {e}", title="Advanced Export", severity="error", timeout=6)

    # ──────────────────────────────────────────────────────────────────
    # Analysis execution
    # ──────────────────────────────────────────────────────────────────

    @work(thread=True)
    def run_analysis(self, confirmed: bool = False, saved_request: AnalysisRunRequest | None = None, saved_df: pd.DataFrame | None = None) -> None:
        """Execute the analysis in a background thread via the shared run seam."""
        log_widget = self.query_one("#log_output")

        if not confirmed and not saved_request:
            if hasattr(self.query_one("#btn_run"), "disabled") and self.query_one("#btn_run").disabled:
                return

            self.call_from_thread(log_widget.clear)
            self.call_from_thread(log_widget.write, "Starting analysis sequence...\n")
            self.call_from_thread(self._begin_run_ui)

            try:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                LOG_DIR.mkdir(parents=True, exist_ok=True)
                log_file = str(LOG_DIR / f"benchmark_log_{timestamp}.txt")
                setup_logging(log_level="INFO", log_file=log_file, console_output=False)

                logging.getLogger("benchmark").handlers.clear()
                logging.getLogger("core").handlers.clear()
                handler = LogHandler(log_widget)
                handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
                logging.getLogger().addHandler(handler)
                self.call_from_thread(log_widget.write, f"Log file created: {log_file}\n")

                csv_path = self.query_one("#csv_path").value
                if not csv_path:
                    self._fail_launch("CSV path is required.", focus_id="csv_path")
                    return

                entity_val = self.query_one("#entity_name").value
                entity = entity_val if entity_val != SELECT_BLANK else None
                entity_col_val = self.query_one("#entity_col").value
                entity_col = entity_col_val if entity_col_val != SELECT_BLANK else "issuer_name"
                preset_val = self.query_one("#preset_select").value
                preset = preset_val if preset_val != SELECT_BLANK else None
                output_file = self.query_one("#output_file").value or None
                time_col_val = self.query_one("#time_col").value
                time_col = time_col_val if time_col_val != SELECT_BLANK else None

                mode = self._analysis_mode()

                request = AnalysisRunRequest(
                    mode=mode,
                    csv=csv_path,
                    entity=entity,
                    entity_col=entity_col,
                    preset=preset,
                    config=self.advanced_config_path if getattr(self, 'advanced_config_path', None) else None,
                    output=output_file,
                    time_col=time_col,
                    log_level="INFO",
                    validate_input=getattr(self.query_one("#validate_input"), 'value', True),
                    analyze_distortion=getattr(self.query_one("#analyze_distortion"), 'value', False),
                    compare_presets=getattr(self.query_one("#compare_presets"), 'value', False),
                    include_calculated=getattr(self.query_one("#include_calculated"), 'value', False),
                    output_format=getattr(self.query_one("#output_format"), 'value', 'analysis'),
                )
                if preset and not request.config:
                    posture = None
                    if not hasattr(self, 'preset_workflow'):
                        self.preset_workflow = PresetWorkflow()
                    preset_data = self.preset_workflow.load_preset_data(preset)
                    posture = preset_data.get('compliance_posture') if isinstance(preset_data, dict) else None
                    request.compliance_posture = posture
                    if posture == 'best_effort':
                        self.call_from_thread(log_widget.write, "WARNING: best_effort posture may complete with labeled non-compliant outputs.\n")
                    if posture == 'accuracy_first':
                        request.acknowledge_accuracy_first = getattr(self.query_one("#acknowledge_accuracy_first"), 'value', False)
                        if not request.acknowledge_accuracy_first:
                            self._fail_launch(
                                "accuracy_first posture requires acknowledgement. Check the box before running.",
                                focus_id="acknowledge_accuracy_first",
                            )
                            return

                if request.is_share:
                    metric_val = self.query_one("#share_metric").value
                    request.metric = metric_val if metric_val != SELECT_BLANK else None
                    if not request.metric:
                        self._fail_launch("Primary metric is required for share analysis.", focus_id="share_metric")
                        return
                    sec_metrics = self.query_one("#share_secondary", SelectionList).selected
                    request.secondary_metrics = list(sec_metrics) if sec_metrics else None
                    request.auto = self.query_one("#share_auto_dim").value
                    dims = self.query_one("#share_dims", SelectionList).selected
                    if not request.auto and not dims:
                        self._fail_launch(
                            "Select at least one dimension or enable auto-detect.",
                            focus_id="share_dims",
                        )
                        return
                    request.dimensions = list(dims) if dims and not request.auto else None
                    request.debug = self.query_one("#share_debug").value
                    request.export_balanced_csv = self.query_one("#share_export_csv").value
                    request.per_dimension_weights = False
                else:
                    total_val = self.query_one("#rate_total").value
                    request.total_col = total_val if total_val != SELECT_BLANK else None
                    if not request.total_col:
                        self._fail_launch("Total column is required for rate analysis.", focus_id="rate_total")
                        return
                    approved = self.query_one("#rate_approved").value
                    request.approved_col = approved if approved != SELECT_BLANK else None
                    fraud = self.query_one("#rate_fraud").value
                    request.fraud_col = fraud if fraud != SELECT_BLANK else None
                    if not request.approved_col and not request.fraud_col:
                        self._fail_launch("At least one rate column (approved or fraud) is required.", focus_id="rate_approved")
                        return
                    sec_metrics = self.query_one("#rate_secondary", SelectionList).selected
                    request.secondary_metrics = list(sec_metrics) if sec_metrics else None
                    request.auto = self.query_one("#rate_auto_dim").value
                    dims = self.query_one("#rate_dims", SelectionList).selected
                    if not request.auto and not dims:
                        self._fail_launch(
                            "Select at least one dimension or enable auto-detect.",
                            focus_id="rate_dims",
                        )
                        return
                    request.dimensions = list(dims) if dims and not request.auto else None
                    request.debug = self.query_one("#rate_debug").value
                    request.export_balanced_csv = self.query_one("#rate_export_csv").value
                    request.fraud_in_bps = getattr(self.query_one("#fraud_in_bps"), 'value', True)

                df = None
                if request.validate_input and request.csv and os.path.exists(request.csv):
                    self.call_from_thread(log_widget.write, "Loading data for validation...\n")
                    try:
                        ns = request.to_namespace()
                        config = build_run_config(ns, extra_overrides={'fraud_in_bps': request.fraud_in_bps} if request.is_rate else None)
                        loader, df, resolved_entity_col, resolved_time_col = prepare_run_data(
                            ns,
                            config,
                            logging.getLogger("benchmark"),
                            preferred_entity_col=request.entity_col,
                        )
                        dimensions = resolve_dimensions(ns, config, loader, df, logging.getLogger("benchmark"))
                        issues, should_abort = validate_analysis_input(
                            df=df,
                            config=config,
                            data_loader=loader,
                            analysis_type=request.mode,
                            entity_col=resolved_entity_col,
                            time_col=resolved_time_col,
                            target_entity=request.entity,
                            dimensions=dimensions,
                            metric_col=request.metric,
                            total_col=request.total_col,
                            numerator_cols=request.numerator_cols,
                        )
                        request.prepared_dataset = PreparedDataset(
                            df=df,
                            entity_col=resolved_entity_col,
                            time_col=resolved_time_col,
                            data_loader=loader,
                            validation_issues=issues if issues is not None else [],
                        )
                        if issues:
                            has_errors = any(issue.severity == ValidationSeverity.ERROR for issue in issues)

                            def on_modal_closed(result: bool) -> None:
                                # Runs on the app thread (screen-dismiss callback).
                                if result and not has_errors and not should_abort:
                                    self.run_analysis(confirmed=True, saved_request=request, saved_df=df)
                                    return
                                write_log_message(log_widget, "Analysis cancelled by user.")
                                self._reset_run_ui()

                            self.call_from_thread(self.push_screen, ValidationModal(issues), on_modal_closed)
                            return
                    except Exception as exc:
                        self.call_from_thread(log_widget.write, f"Validation error: {exc}\n")
                        self.call_from_thread(self.notify, "Validation failed. Fix the data and retry.", severity="error")
                        self.call_from_thread(self._end_run_ui, "error", f"Validation error: {exc}")
                        return

                self.call_from_thread(self.run_analysis, True, request, df)
                return

            except Exception as exc:
                self.call_from_thread(log_widget.write, f"Initialization Error: {exc}\n")
                self.call_from_thread(self._end_run_ui, "error", f"Initialization error: {exc}")
                return

        if confirmed and saved_request:
            request = saved_request
            logger = logging.getLogger("benchmark")
            # Restart the run clock so the elapsed time reflects execution,
            # not how long a validation modal sat open.
            self.call_from_thread(self._begin_run_ui)
            try:
                # NOTE (audit complement §2.10): `saved_df` is the raw input
                # DataFrame and does not carry preset/posture state. If a future
                # change starts caching preset-derived state in `saved_df`,
                # invalidate the cache when `request.preset` or
                # `request.compliance_posture` changes between the
                # validate-and-confirm callback. Today this is a no-op because
                # the DataFrame is preset-agnostic.
                request.df = saved_df
                if saved_df is not None and request.prepared_dataset is None:
                    request.prepared_dataset = PreparedDataset(df=saved_df)
                artifacts = execute_run(request, logger)
                self.call_from_thread(log_widget.write, "Analysis completed successfully.\n")
                summary = artifacts.compliance_summary or artifacts.metadata.get('compliance_summary', {})
                posture = summary.get('posture') or summary.get('compliance_posture')
                self.call_from_thread(
                    log_widget.write,
                    f"Compliance: posture={posture} verdict={summary.get('compliance_verdict')} acknowledgement={summary.get('acknowledgement_state')}\n",
                )
                report_paths = [str(p) for p in (artifacts.report_paths or [artifacts.analysis_output_file]) if p]
                verdict = str(summary.get('compliance_verdict'))
                if verdict == 'fully_compliant':
                    verdict_markup = f"[green]{verdict}[/green]"
                elif verdict in ('violations_detected', 'not_publishable_input', 'structural_infeasibility', 'blocked'):
                    verdict_markup = f"[red]{verdict}[/red]"
                else:
                    verdict_markup = verdict
                summary_lines = [
                    f"[dim]Mode[/dim]     {request.mode} · {request.preset or 'default'}",
                    f"[dim]Verdict[/dim]  {verdict_markup} [dim](posture={posture})[/dim]",
                ]
                for path in report_paths:
                    summary_lines.append(f"[dim]Report[/dim]   {path}")
                self.call_from_thread(self._end_run_ui, "success", "\n".join(summary_lines))
                self.call_from_thread(
                    self.notify,
                    f"Report saved: {report_paths[0] if report_paths else 'n/a'}",
                    title="Analysis Complete",
                    severity="information",
                    timeout=10,
                )
            except RunBlocked as exc:
                self.call_from_thread(log_widget.write, f"Execution Blocked: {exc}\n")
                self.call_from_thread(self._end_run_ui, "blocked", f"[red]{exc}[/red]")
                self.call_from_thread(self.notify, str(exc), title="Blocked", severity="error", timeout=10)
            except RunAborted as exc:
                self.call_from_thread(log_widget.write, f"Execution Error: {exc}\n")
                self.call_from_thread(self._end_run_ui, "error", f"[red]{exc}[/red]")
                self.call_from_thread(self.notify, str(exc), title="Failed", severity="error", timeout=10)
            except Exception as exc:
                self.call_from_thread(log_widget.write, f"Execution Error: {exc}\n")
                import traceback
                self.call_from_thread(log_widget.write, traceback.format_exc())
                self.call_from_thread(self._end_run_ui, "error", f"[red]{exc}[/red]")


if __name__ == "__main__":
    app = BenchmarkApp()
    app.run()
