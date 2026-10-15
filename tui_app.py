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
import traceback
import glob
import contextlib
import collections
import io
import pandas as pd
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, NamedTuple, Optional, Tuple
import yaml

# Remote-friendly renderer defaults (must be set before Textual is imported).
# The TUI is typically used over SSH/VPN where smooth scrolling and animations
# multiply the number of frames (and therefore bytes) sent down the wire.
# `setdefault` keeps these overridable from the environment.
os.environ.setdefault("TEXTUAL_SMOOTH_SCROLL", "0")
os.environ.setdefault("TEXTUAL_ANIMATIONS", "none")
os.environ.setdefault("TEXTUAL_FPS", "20")

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.markup import escape as escape_markup
from textual.widgets import (
    Header,
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
    Tabs,
)
from textual.widgets._collapsible import CollapsibleTitle
from datetime import datetime
from textual import work
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.worker import get_current_worker
from rich.text import Text

# Import shared run orchestration and adapter dependencies.
sys.path.append(str(Path(__file__).parent))
try:
    from core.analysis_run import (
        RunAborted,
        RunBlocked,
        RunCancelled,
        build_run_config,
        prepare_run_data,
        resolve_dimensions,
        validate_analysis_input,
        execute_run,
    )
    from core.contracts import (
        AnalysisArtifacts,
        AnalysisRunRequest,
        DEFAULT_PRESET_NAME,
        PreparedDataset,
        PrivacyReleaseMode,
        PrivacyRuleStrategy,
    )
    from core.preset_workflow import PresetWorkflow
    from core.telemetry import (
        action_cancelled,
        advanced_override,
        dataset_load,
        end_session,
        launch_blocked,
        session_restored,
        start_session,
        surface_viewed,
    )
    from utils.logger import finalize_deferred_logging, setup_deferred_logging
    from utils.runtime_environment import warn_if_personal_runtime
    from utils.config_manager import ConfigManager
    from utils.config_overrides import (
        ADVANCED_FIELD_SPECS,
        ConfigFieldSpec,
        ConfigOverrideBuilder,
    )
    from core.data_loader import ValidationIssue, ValidationSeverity
    from core import labels
    from tui.keybar import KeyBar
    from tui.status import glyph as status_glyph, status_text
    from tui.styles import AUTOBENCH_TCSS
    from tui.widgets import BoxCheckbox, BoxSelectionList, StatusBadge
except ImportError as e:
    # Fallback for when running in a different context or if imports fail
    print(f"Error importing benchmark modules: {e}")
    sys.exit(1)

# Textual >= 0.89 renamed the Select no-selection sentinel from BLANK to NULL;
# Select.BLANK now resolves to Widget.BLANK (False), so compare against the
# real sentinel to detect "nothing selected" reliably.
SELECT_BLANK = getattr(Select, "NULL", getattr(Select, "BLANK", None))

SESSION_FILE = Path.home() / ".benchmark_tui" / "session.yaml"


def _resolve_log_dir() -> Path:
    """Resolve the log directory at run time so test/process isolation applies."""
    return Path(
        os.getenv("AUTOBENCH_LOG_DIR", str(Path("outputs") / "logs"))
    )


SESSION_INPUT_IDS: tuple[str, ...] = ()
SESSION_SELECT_IDS = (
    "entity_col",
    "time_col",
    "preset_select",
    "output_format",
    "privacy_release_mode",
    "share_metric",
    "rate_total",
    "rate_approved",
    "rate_fraud",
)
# Compliance attestations and consent acknowledgements are deliberately
# excluded: they are per-run declarations and must not be restored from a
# previous session (acknowledge_accuracy_first, privacy_merchant_spend_scope,
# citi_competitor_receives_output).
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
    "privacy_rule_sweep_mode",
)
SESSION_SELECTION_LIST_IDS = ("share_dims", "share_secondary", "rate_dims", "rate_secondary")

ENTITY_SELECT_PROMPT = "None: peer group only"
ENTITY_LOADING_PROMPT = "Loading entities…"


def read_unique_entity_values(csv_path: str, column_name: str) -> List[str]:
    """Return the sorted distinct non-null values of one CSV column as strings.

    Runs on a worker thread (see ``BenchmarkApp._load_unique_entities_worker``)
    so it must not touch widgets. The column is read with pandas' default type
    inference on purpose: ``dtype=str`` was measured slower on 1M rows and would
    change the rendered value of numeric IDs (``5.0`` vs ``5`` when the column
    has nulls), which must keep matching what the analysis run filters on.
    """
    df = pd.read_csv(csv_path, usecols=[column_name])
    return sorted(df[column_name].dropna().unique().astype(str).tolist())


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
        try:
            app.call_from_thread(log_widget.write, text)
        except RuntimeError:
            pass  # App loop already gone (e.g. a run cancelled by Quit).


class LogHandler(logging.Handler):
    """Logging handler that batches records into a Textual Log widget.

    Records go into a bounded, thread-safe buffer. The first record after a
    drain posts one wake (``Log.call_later``, which is thread-safe and never
    waits for the UI); the drain then writes everything pending in a single
    ``Log.write`` on the UI thread. An emitting worker therefore never blocks
    on the UI, and if the UI stalls the buffer keeps only the newest
    ``max_pending`` lines plus a count of the ones it dropped. The full record
    is the deferred log file on disk, not this view.
    """

    MAX_PENDING = 2000  # matches the Log widget's max_lines

    def __init__(self, log_widget: Log, max_pending: int = MAX_PENDING):
        super().__init__()
        self.log_widget = log_widget
        self._pending: "collections.deque[str]" = collections.deque(maxlen=max_pending)
        self._dropped = 0
        self._buffer_lock = threading.Lock()
        self._wake_posted = False

    def emit(self, record):
        try:
            msg = self.format(record)
        except Exception:
            self.handleError(record)
            return
        try:
            app = self.log_widget.app
        except Exception:
            # Widget is no longer attached to a running app (e.g. after exit).
            return
        if app is None:
            return
        text = msg if msg.endswith("\n") else f"{msg}\n"
        with self._buffer_lock:
            if len(self._pending) == self._pending.maxlen:
                self._dropped += 1
            self._pending.append(text)
            if self._wake_posted:
                return
            self._wake_posted = True
        if getattr(app, "_thread_id", None) == threading.get_ident():
            self._flush()
            return
        try:
            posted = bool(self.log_widget.call_later(self._flush))
        except Exception:
            posted = False
        if not posted:
            # App is shutting down; the next record may try again.
            with self._buffer_lock:
                self._wake_posted = False

    def _flush(self) -> None:
        """Drain the buffer into one Log.write (app thread only)."""
        with self._buffer_lock:
            pending = list(self._pending)
            self._pending.clear()
            dropped, self._dropped = self._dropped, 0
            self._wake_posted = False
        if dropped:
            pending.insert(
                0, f"… {dropped} earlier log lines not shown (full log on disk)\n"
            )
        if pending:
            self.log_widget.write("".join(pending))


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
        with Container(id="picker_container", classes="ab-modal"):
            yield Label("Open a CSV file", id="picker_title")
            with Horizontal(id="picker_body"):
                with Vertical(id="picker_quick"):
                    yield Label("Quick picks", classes="picker-subtitle")
                    yield ListView(
                        *[FileListItem(path) for path in self.quick_picks],
                        id="picker_quick_list",
                        classes="ab-list",
                    )
                with Vertical(id="picker_tree_pane"):
                    yield Label("Browse workspace", classes="picker-subtitle")
                    yield CsvDirectoryTree(os.getcwd(), id="picker_tree", classes="ab-list")
            yield Label(
                "Enter opens the file · Esc cancels",
                classes="picker-hint",
            )
            yield Button("Cancel", id="btn_picker_cancel", variant="default", compact=True)
        yield KeyBar("picker")

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
        with Container(id="confirm_container", classes="ab-modal"):
            # Literal text: messages can carry column names from the CSV.
            yield Label(Text(self.message), id="confirm_message")
            with Horizontal(id="confirm_buttons"):
                yield Button(self.confirm_label, id="btn_confirm_yes", variant="error", compact=True)
                yield Button("Cancel", id="btn_confirm_no", variant="default", compact=True)
        yield KeyBar("confirm")

    def on_mount(self) -> None:
        # D3: a single stray Enter must never consent, attest or quit.
        # Affirming takes a deliberate move to the confirm button.
        self.query_one("#btn_confirm_no", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn_confirm_yes")

    def action_cancel_confirm(self) -> None:
        self.dismiss(False)

    def on_screen_resume(self) -> None:
        _refresh_app_status(self.app)

    def on_unmount(self) -> None:
        _refresh_app_status(self.app)


def _refresh_app_status(app: Any) -> None:
    """Let the run-status badge show WAITING FOR YOU while a dialog is open."""
    refresh = getattr(app, "_refresh_run_status", None)
    if refresh is None or not getattr(app, "is_running", False):
        return
    try:
        app.call_later(refresh)
    except Exception:
        pass  # App is shutting down.


class ClearingSpendConfirmScreen(ConfirmScreen):
    """Confirm that the selected Total column contains clearing spend."""

    def __init__(self, total_col: str) -> None:
        super().__init__(
            "Confirm clearing-spend basis\n\n"
            f'Fraud analysis requires Total column "{total_col}" to contain '
            "clearing-spend amounts. Continue?",
            confirm_label="Yes, it is clearing spend",
        )


class PresetHelpScreen(ModalScreen):
    """Screen to show preset help."""

    BINDINGS = [("escape", "close_help", "Close")]

    # Styled by tui.styles (TCSS variables are file-scoped, so screens carry
    # no CSS of their own).

    def compose(self) -> ComposeResult:
        with Container(id="help_container", classes="ab-modal"):
            yield Label("Preset guide", classes="section-title")
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

### Keyboard
- **Ctrl+R** run · **Ctrl+O** open a CSV · **Ctrl+L** clear the log
- **F8** show or hide Advanced optimization · **F9** export the advanced settings
- **F1** this guide · **Ctrl+P** commands · **Ctrl+Q** or **Ctrl+C** quit
                """,
                id="help_text"
            )
            yield Button("Close", id="btn_close_help", variant="primary", compact=True)
        yield KeyBar("help")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_close_help":
            self.dismiss()

    def action_close_help(self) -> None:
        self.dismiss()


class ValidationModal(ModalScreen):
    """Modal to display validation issues and allow proceed/cancel.

    Every issue gets its own content-sized row with a text severity badge
    (``ERROR`` / ``WARNING``) so the outcome stays legible without colour.
    Issue text comes from user data (CSV column names and values), so it is
    rendered as literal ``rich.text.Text`` and never parsed as markup.
    """

    BINDINGS = [("escape", "cancel_validation", "Cancel")]

    _BADGE_WIDTH = max(len(s.value) for s in ValidationSeverity)
    # Status-language glyph per severity (02 §5.2): ✗ ERROR, ▲ WARNING, INFO.
    _SEVERITY_STATE = {
        ValidationSeverity.ERROR: "error",
        ValidationSeverity.WARNING: "warning",
    }

    def __init__(self, issues: List[ValidationIssue]) -> None:
        super().__init__()
        self.issues = issues
        self.has_errors = any(i.severity == ValidationSeverity.ERROR for i in issues)

    @staticmethod
    def _counts_text(error_count: int, warning_count: int) -> str:
        """``2 errors must be fixed · 1 warning to review`` (02 §5.4 #33)."""
        parts: List[str] = []
        if error_count:
            noun = "error" if error_count == 1 else "errors"
            parts.append(f"{error_count} {noun} must be fixed")
        if warning_count:
            noun = "warning" if warning_count == 1 else "warnings"
            parts.append(f"{warning_count} {noun} to review")
        return " · ".join(parts) or "No errors or warnings"

    def compose(self) -> ComposeResult:
        error_count = sum(1 for i in self.issues if i.severity == ValidationSeverity.ERROR)
        warning_count = sum(1 for i in self.issues if i.severity == ValidationSeverity.WARNING)

        with Container(id="validation_container", classes="ab-modal"):
            yield Label("Check your data", id="validation_title")
            yield Label(
                self._counts_text(error_count, warning_count),
                id="validation_counts",
                classes="issue-error" if error_count else ("issue-warning" if warning_count else ""),
            )

            yield Label("", id="validation_hint")

            yield ListView(id="issue_list", classes="ab-list")

            with Horizontal(id="validation_buttons"):
                yield Button("Proceed", id="btn_proceed", variant="success", disabled=self.has_errors, compact=True)
                yield Button("Cancel", id="btn_cancel", variant="error", compact=True)
        yield KeyBar("validation")

    @classmethod
    def _issue_text(cls, issue: ValidationIssue) -> Text:
        """Build a literal (markup-free) row: severity badge, message, rows."""
        state = cls._SEVERITY_STATE.get(issue.severity)
        mark = status_glyph(state) if state else " " * len(status_glyph("error"))
        badge = f" {mark} {issue.severity.value.upper():<{cls._BADGE_WIDTH}} "
        text = Text.assemble((badge, "bold reverse"), " ", str(issue.message))
        if issue.row_indices:
            row_preview = ", ".join(str(i) for i in issue.row_indices[:10])
            if len(issue.row_indices) > 10:
                row_preview += f", … ({len(issue.row_indices)} rows in total)"
            text.append(f"\n{' ' * (len(badge) + 1)}Rows: {row_preview}", style="italic")
        return text

    def on_mount(self) -> None:
        """Populate the list view and move focus off Proceed."""
        list_view = self.query_one("#issue_list", ListView)
        for issue in self.issues:
            if issue.severity == ValidationSeverity.ERROR:
                severity_cls = "issue-error"
            elif issue.severity == ValidationSeverity.WARNING:
                severity_cls = "issue-warning"
            else:
                severity_cls = "issue-info"
            row = Static(self._issue_text(issue), classes=f"issue-text {severity_cls}")
            list_view.append(ListItem(row, classes="issue-item"))
        # One stray Enter must never proceed past issues the operator has not seen.
        if self.has_errors:
            self.query_one("#btn_cancel", Button).focus()
        else:
            list_view.focus()
        self.call_after_refresh(self._update_hint)

    def on_resize(self) -> None:
        self.call_after_refresh(self._update_hint)

    def on_screen_resume(self) -> None:
        _refresh_app_status(self.app)

    def on_unmount(self) -> None:
        _refresh_app_status(self.app)

    def _update_hint(self) -> None:
        """Say when the list overflows and why Proceed is unavailable."""
        try:
            list_view = self.query_one("#issue_list", ListView)
            hint = self.query_one("#validation_hint", Label)
        except NoMatches:
            return
        parts: List[str] = []
        count = len(self.issues)
        noun = "issue" if count == 1 else "issues"
        if list_view.max_scroll_y > 0:
            parts.append(f"{count} {noun}, scroll to review")
        else:
            parts.append(f"{count} {noun}")
        if self.has_errors:
            parts.append("Proceed is disabled until errors are fixed")
        hint.update(Text(". ".join(parts) + "."))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_proceed":
            self.dismiss(True)  # Return True to proceed
        elif event.button.id == "btn_cancel":
            self.dismiss(False)  # Return False to cancel

    def action_cancel_validation(self) -> None:
        self.dismiss(False)


# Fields populated by the TUI widget-values builder (union of common + mode-specific keys).
TUI_REQUEST_FIELDS = frozenset({
    "csv",
    "entity",
    "entity_col",
    "preset",
    "config",
    "output",
    "time_col",
    "log_level",
    "validate_input",
    "analyze_distortion",
    "compare_presets",
    "include_calculated",
    "output_format",
    "compliance_posture",
    "acknowledge_accuracy_first",
    "metric",
    "secondary_metrics",
    "auto",
    "dimensions",
    "debug",
    "export_balanced_csv",
    "per_dimension_weights",
    "total_col",
    "approved_col",
    "fraud_col",
    "fraud_in_bps",
    "privacy_rule_strategy",
    "privacy_release_mode",
    "is_anonymized_aggregated_merchant_spend",
    "citibank_entity_name",
    "citi_competitor_receives_output",
})

# CLI fields with no TUI widget yet; post-assembly fields are set after validation modal.
TUI_UNSUPPORTED_FIELDS = frozenset({
    "df",
    "prepared_dataset",
    "lean",
    "audit_package",
    "validate_export",
    "report_format",
})

_PRIVACY_RELEASE_MODE_OPTIONS = (
    ("Complete output", PrivacyReleaseMode.COMPLETE_OUTPUT.value),
    ("Verified safe coverage", PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE.value),
)
_PRIVACY_RELEASE_MODE_VALUES = frozenset(
    value for _, value in _PRIVACY_RELEASE_MODE_OPTIONS
)

# D5: advanced fields whose value is owned by a Share/Rate tab control.
TUI_TAB_OWNED_ADVANCED_FIELDS = frozenset({"adv_output_debug_sheets"})

# D4: session keys that name CSV columns. They are applied only after a CSV
# header load, and only where the column exists in that file.
SESSION_COLUMN_SELECT_IDS = frozenset({
    "entity_col",
    "time_col",
    "share_metric",
    "rate_total",
    "rate_approved",
    "rate_fraud",
})
SESSION_TAB_KEY = "analysis_mode"
_SESSION_TABS = {"share": "share_tab", "rate": "rate_tab"}

# Owner decision 1: plain-language names for core's run phases.
_RUN_STAGE_LABELS = {
    "configuration": "Checking configuration",
    "input": "Loading data",
    "analysis": "Optimizing and checking privacy",
    "output": "Writing outputs",
}


@dataclass(frozen=True)
class RunInputs:
    """Every form value one run attempt needs, read on the UI thread (D7).

    The analysis worker reads only this snapshot, never a widget. Consent and
    the clearing-spend attestation are not part of it: they are still asked
    per run attempt, from the worker, after the snapshot is taken.
    """

    mode: str
    csv_path: str
    entity_selection_pending: bool
    entity: Optional[str]
    entity_col: str
    preset: Optional[str]
    config: Optional[str]
    # Effective posture of preset + override file, as core will resolve it.
    compliance_posture: Optional[str]
    output: Optional[str]
    time_col: Optional[str]
    validate_input: bool
    analyze_distortion: bool
    compare_presets: bool
    include_calculated: bool
    output_format: str
    privacy_values: Tuple[Tuple[str, Any], ...]
    metric: Optional[str] = None
    total_col: Optional[str] = None
    approved_col: Optional[str] = None
    fraud_col: Optional[str] = None
    secondary_metrics: Tuple[str, ...] = ()
    auto: bool = False
    dimensions: Tuple[str, ...] = ()
    debug: bool = True
    export_balanced_csv: bool = False
    fraud_in_bps: bool = True


class RunBadge(NamedTuple):
    """Status-language state (tui.status) plus an optional detail word."""

    state: str
    detail: str = ""


def _preset_display(preset: Optional[str]) -> str:
    """Plain preset name for display; unknown (custom) presets keep their name."""
    if not preset:
        return "—"
    label = labels.label_for(labels.PRESET, preset)
    return preset if label.primary == labels.UNRECOGNISED else label.primary


class BenchmarkApp(App):
    """Privacy-Compliant Peer Benchmark Tool TUI"""

    # F8/F9 replace Ctrl+A/Ctrl+E: a focused Input binds Ctrl+A/Ctrl+E to
    # Home/End, so those never reached the app from a text field (and Ctrl+A
    # is the GNU screen prefix). No widget binds F8/F9, so they work in any
    # field. The old keys stay as hidden aliases for muscle memory and the
    # perf probe. The key bar (tui.keybar) shows the keys; no Footer.
    BINDINGS = [
        Binding("ctrl+o", "open_file", "Open CSV"),
        Binding("ctrl+r", "run_analysis", "Run"),
        Binding("f1", "show_help", "Preset guide"),
        Binding("f8", "toggle_advanced", "Advanced"),
        Binding("f9", "export_advanced", "Export advanced"),
        Binding("ctrl+a", "toggle_advanced", "Advanced", show=False),
        Binding("ctrl+e", "export_advanced", "Export advanced", show=False),
        Binding("ctrl+l", "clear_log", "Clear log"),
        # Release tooling exits with Escape then Ctrl+C (edge_deploy.yaml
        # tui_exit: ctrl_c). Textual 7.5 binds Ctrl+C to copy (Input, Screen)
        # and only *hints* at quitting, so the app owns it: copy when there is
        # a selection, otherwise quit like Ctrl+Q.
        Binding("ctrl+c", "copy_or_quit", "Quit", show=False, priority=True),
    ]

    # D5: output.include_debug_sheets is driven only by the tab-level "Debug
    # sheets" checkbox (request field ``debug``). The shared spec stays in
    # utils.config_overrides for other adapters; the TUI has no second,
    # silently overridden control for it.
    ADVANCED_FIELD_SPECS: List[ConfigFieldSpec] = [
        spec for spec in ADVANCED_FIELD_SPECS if spec.widget_id not in TUI_TAB_OWNED_ADVANCED_FIELDS
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Confirmations the analysis worker is blocked on (see _await_confirmation).
        self._confirmation_lock = threading.Lock()
        self._pending_confirmations: set[threading.Event] = set()
        self._confirmations_abandoned = False
        # Owner decision 1: set by request_cancel(); core checks it at phase
        # boundaries and before output writing starts (never during it).
        self._cancel_event = threading.Event()
        self._run_stage: Optional[str] = None
        # D4: restored column choices wait here for the first CSV header load.
        self._pending_session_selects: Dict[str, Any] = {}
        self._pending_session_lists: Dict[str, List[Any]] = {}
        # D2: the preset an applied advanced-override file was written for.
        self._advanced_config_preset: Optional[str] = None

    # One token stylesheet for every screen (tui/styles.py, 02 §1).
    CSS = AUTOBENCH_TCSS

    # Release tooling matches the title (edge_deploy.yaml tui_chrome_regex).
    TITLE = "Privacy-Compliant Peer Benchmark"
    SUB_TITLE = ""

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        # No clock: it would repaint the header (and push bytes over SSH)
        # every second for the lifetime of the app.
        yield Header(show_clock=False)

        with Horizontal(id="app_body"):
            # ═══════════════════════════════════════════════════════════
            # LEFT — CONFIGURATION
            # ═══════════════════════════════════════════════════════════
            with VerticalScroll(id="config_pane"):
                with Container(id="section_data", classes="form-section"):
                    yield Label("1 · Data source", classes="ab-section")
                    yield Label("CSV file path", classes="field-label")
                    with Horizontal(classes="ab-row"):
                        yield Button("Browse…", id="btn_browse_csv", variant="default", compact=True)
                        yield Input(placeholder="path/to/data.csv", id="csv_path", classes="file-input", compact=True)
                    yield Static("No file loaded.", id="csv_meta")

                with Container(id="section_entity", classes="form-section"):
                    yield Label("2 · Entity", classes="ab-section")
                    with Horizontal(classes="input-group"):
                        with Vertical(classes="field-pair"):
                            yield Label("Entity ID column", classes="field-label")
                            yield Select([], prompt="Select column…", id="entity_col", compact=True)
                        with Vertical(classes="field-pair"):
                            yield Label("Target entity", classes="field-label")
                            yield Select(
                                [], prompt=ENTITY_SELECT_PROMPT, id="entity_name", allow_blank=True, compact=True
                            )

                with Container(id="section_analysis", classes="form-section"):
                    yield Label("3 · Analysis options", classes="ab-section")
                    with Horizontal(classes="input-group"):
                        with Vertical(classes="field-pair"):
                            yield Label("Time period column", classes="field-label")
                            yield Select([], prompt="Select column…", id="time_col", allow_blank=True, compact=True)
                        with Vertical(classes="field-pair"):
                            yield Label("Output file name", classes="field-label")
                            yield Input(placeholder="Leave blank to name it automatically", id="output_file", compact=True)

                    yield Label("Optimization preset", classes="field-label")
                    with Horizontal(classes="ab-row"):
                        yield Select([], prompt="Select preset…", id="preset_select", compact=True)
                        yield Button("Preset guide", id="btn_preset_help", variant="default", compact=True)
                    yield Static("", id="preset_blurb", classes="field-hint")

                    with Vertical(classes="ab-checks"):
                        yield BoxCheckbox("Show how the weighting changed results", value=True, id="analyze_distortion", compact=True)
                        yield BoxCheckbox("Compare presets", id="compare_presets", compact=True)
                        yield BoxCheckbox("Validate input", id="validate_input", value=True, compact=True)
                        yield BoxCheckbox("Add calculated metrics to the balanced CSV", id="include_calculated", compact=True)
                    with Horizontal(classes="input-group"):
                        with Vertical(classes="field-pair"):
                            yield Label("Output format", classes="field-label")
                            yield Select(
                                [
                                    (labels.text_for(labels.OUTPUT_FORMAT, "analysis"), "analysis"),
                                    (labels.text_for(labels.OUTPUT_FORMAT, "publication"), "publication"),
                                    (labels.text_for(labels.OUTPUT_FORMAT, "both"), "both"),
                                ],
                                id="output_format",
                                value="analysis",
                                allow_blank=False,
                                compact=True,
                            )
                    yield Label(
                        "Privacy release mode",
                        classes="field-label",
                        id="privacy_release_mode_label",
                    )
                    yield Select(
                        list(_PRIVACY_RELEASE_MODE_OPTIONS),
                        id="privacy_release_mode",
                        value=PrivacyReleaseMode.COMPLETE_OUTPUT.value,
                        allow_blank=False,
                        compact=True,
                    )
                    yield Static(
                        "Verified safe coverage publishes only verified safe units. "
                        "Missing units are privacy-suppressed. "
                        "Coverage is not a maximum claim.",
                        id="privacy_release_mode_hint",
                        classes="field-hint",
                    )
                    with Vertical(classes="ab-checks"):
                        yield BoxCheckbox(
                            "Privacy rule sweep: try every applicable rule",
                            id="privacy_rule_sweep_mode",
                            value=False,
                            compact=True,
                        )
                        yield BoxCheckbox(
                            "Anonymized aggregated merchant-spend context (enables 4/35)",
                            id="privacy_merchant_spend_scope",
                            compact=True,
                        )

                # ───────────────────────────────────────────────────────
                # COMPLIANCE DECLARATIONS (collapsed by default)
                # ───────────────────────────────────────────────────────
                with Collapsible(title="Compliance declarations", id="compliance_declarations", collapsed=True):
                    with Vertical(id="compliance_form"):
                        yield Label("Citi privacy overlay", classes="adv-group-title")
                        yield BoxCheckbox(
                            "A Citi competitor receives the output",
                            id="citi_competitor_receives_output",
                            compact=True,
                        )
                        yield Label("Citibank entity name", classes="field-label")
                        yield Input(
                            placeholder="Exact Citibank entity name (required for Citi overlay)",
                            id="citibank_entity_name",
                            compact=True,
                        )

                # ───────────────────────────────────────────────────────
                # ADVANCED OPTIMIZATION (collapsed by default)
                # ───────────────────────────────────────────────────────
                with Collapsible(title="Advanced optimization (F8)", id="advanced_opt", collapsed=True):
                    with Vertical(id="advanced_form"):
                        yield Label("Linear programming", classes="adv-group-title")
                        with Horizontal(classes="input-group"):
                            with Vertical(classes="field-pair"):
                                yield Label("Tolerance (pp)", classes="adv-field-label")
                                yield Input(placeholder="e.g., 2.0", id="adv_lp_tolerance", compact=True)
                            with Vertical(classes="field-pair"):
                                yield Label("Max iterations", classes="adv-field-label")
                                yield Input(placeholder="e.g., 1000", id="adv_lp_max_iterations", compact=True)
                        with Horizontal(classes="input-group"):
                            with Vertical(classes="field-pair"):
                                yield Label("Lambda penalty", classes="adv-field-label")
                                yield Input(placeholder="e.g., 100", id="adv_lp_lambda_penalty", compact=True)
                            with Vertical(classes="field-pair"):
                                yield Label("Volume weighting exponent", classes="adv-field-label")
                                yield Input(placeholder="e.g., 1.5", id="adv_lp_volume_weighting_exponent", compact=True)
                        with Vertical(classes="ab-checks"):
                            yield BoxCheckbox(
                                "Enable volume-weighted penalties", id="adv_lp_volume_weighted_penalties", compact=True
                            )

                        yield Label("Constraints", classes="adv-group-title")
                        with Horizontal(classes="input-group"):
                            with Vertical(classes="field-pair"):
                                yield Label("Volume preservation", classes="adv-field-label")
                                yield Input(placeholder="0.0 - 1.0", id="adv_constraints_volume_preservation", compact=True)

                        yield Label("Weight bounds", classes="adv-group-title")
                        with Horizontal(classes="input-group"):
                            with Vertical(classes="field-pair"):
                                yield Label("Min weight", classes="adv-field-label")
                                yield Input(placeholder="e.g., 0.01", id="adv_bounds_min_weight", compact=True)
                            with Vertical(classes="field-pair"):
                                yield Label("Max weight", classes="adv-field-label")
                                yield Input(placeholder="e.g., 10.0", id="adv_bounds_max_weight", compact=True)

                        yield Label("Subset search", classes="adv-group-title")
                        with Horizontal(classes="input-group"):
                            yield BoxCheckbox("Enable subset search", id="adv_subset_enabled", compact=True)
                            with Vertical(classes="field-pair"):
                                yield Label("Strategy", classes="adv-field-label")
                                yield Input(placeholder="greedy / random", id="adv_subset_strategy", compact=True)
                        with Horizontal(classes="input-group"):
                            with Vertical(classes="field-pair"):
                                yield Label("Max attempts", classes="adv-field-label")
                                yield Input(placeholder="e.g., 200", id="adv_subset_max_attempts", compact=True)
                            with Vertical(classes="field-pair"):
                                yield Label("Max slack threshold", classes="adv-field-label")
                                yield Input(placeholder="e.g., 0.05", id="adv_subset_max_slack_threshold", compact=True)
                        with Vertical(classes="ab-checks"):
                            yield BoxCheckbox("Trigger on slack", id="adv_subset_trigger_on_slack", compact=True)
                            yield BoxCheckbox("Prefer slacks first", id="adv_subset_prefer_slacks_first", compact=True)

                        yield Label("Bayesian optimization (fallback)", classes="adv-group-title")
                        with Horizontal(classes="input-group"):
                            with Vertical(classes="field-pair"):
                                yield Label("Max iterations", classes="adv-field-label")
                                yield Input(placeholder="e.g., 100", id="adv_bayes_max_iterations", compact=True)
                            with Vertical(classes="field-pair"):
                                yield Label("Learning rate", classes="adv-field-label")
                                yield Input(placeholder="e.g., 0.01", id="adv_bayes_learning_rate", compact=True)

                        yield Label("Analysis settings", classes="adv-group-title")
                        with Horizontal(classes="input-group"):
                            with Vertical(classes="field-pair"):
                                yield Label("Best-in-class percentile", classes="adv-field-label")
                                yield Input(
                                    placeholder="0.0 - 1.0 (e.g., 0.85)", id="adv_analysis_bic_percentile", compact=True
                                )

                        yield Label("Output settings", classes="adv-group-title")
                        with Vertical(classes="ab-checks"):
                            yield BoxCheckbox(
                                "Include privacy validation", id="adv_output_privacy_validation", compact=True
                            )
                        # D5: debug sheets have one control, the "Debug sheets"
                        # checkbox on the Share/Rate tab (the ``debug`` request
                        # field, which wins over the preset as on the CLI).
                        yield Label("Debug sheets are set on the Share/Rate tab.", classes="ab-hint")

                        with Horizontal(classes="ab-row ab-checks"):
                            yield Button("Apply overrides", id="btn_apply_advanced", variant="primary", compact=True)
                            yield Button("Export settings (F9)", id="btn_export_advanced", variant="default", compact=True)
                        yield Label(
                            "Applied values override the preset for the next runs.", classes="subsection-title"
                        )

                # ───────────────────────────────────────────────────────
                # ANALYSIS MODE TABS
                # ───────────────────────────────────────────────────────
                with Container(id="section_mode", classes="form-section"):
                    yield Label("4 · Analysis mode", classes="ab-section")
                    with TabbedContent(initial="share_tab"):
                        with TabPane("Share analysis", id="share_tab"):
                            with Vertical(classes="field-pair"):
                                yield Label("Primary metric column", classes="field-label")
                                yield Select([], prompt="Select column…", id="share_metric", compact=True)

                            with Vertical(classes="field-pair"):
                                yield Label("Secondary metrics", classes="field-label")
                                yield BoxSelectionList(id="share_secondary", classes="multi-select")

                            yield Label("Dimension options", classes="subsection-title")
                            with Vertical(classes="ab-checks"):
                                yield BoxCheckbox("Auto-detect dimensions", value=False, id="share_auto_dim", compact=True)
                                yield BoxCheckbox("Debug sheets", value=True, id="share_debug", compact=True)
                                # Owner decision 5: off by default, as for rate and the CLI.
                                yield BoxCheckbox(
                                    "Export balanced CSV", value=False, id="share_export_csv", compact=True
                                )

                            yield Label("Dimensions", id="share_dims_label", classes="field-label")
                            yield BoxSelectionList(id="share_dims", classes="multi-select")

                        with TabPane("Rate analysis", id="rate_tab"):
                            with Vertical(classes="field-pair"):
                                yield Label("Total column (denominator)", classes="field-label")
                                yield Select([], prompt="Select column…", id="rate_total", compact=True)
                            with Horizontal(classes="split-inputs"):
                                with Vertical(classes="field-pair"):
                                    yield Label("Approved column", classes="field-label")
                                    yield Select(
                                        [], prompt="Select column…", id="rate_approved", allow_blank=True, compact=True
                                    )
                                with Vertical(classes="field-pair"):
                                    yield Label("Fraud column", classes="field-label")
                                    yield Select(
                                        [], prompt="Select column…", id="rate_fraud", allow_blank=True, compact=True
                                    )

                            with Vertical(classes="field-pair"):
                                yield Label("Secondary metrics", classes="field-label")
                                yield BoxSelectionList(id="rate_secondary", classes="multi-select")

                            yield Label("Dimension options", classes="subsection-title")
                            with Vertical(classes="ab-checks"):
                                yield BoxCheckbox("Auto-detect dimensions", value=False, id="rate_auto_dim", compact=True)
                                yield BoxCheckbox("Debug sheets", value=True, id="rate_debug", compact=True)
                                yield BoxCheckbox("Export balanced CSV", value=False, id="rate_export_csv", compact=True)
                                yield BoxCheckbox(
                                    "Show fraud in basis points (publication workbook)",
                                    value=True,
                                    id="fraud_in_bps",
                                    compact=True,
                                )

                            yield Label("Dimensions", id="rate_dims_label", classes="field-label")
                            yield BoxSelectionList(id="rate_dims", classes="multi-select")

                yield Button("▶  Run Analysis", id="btn_run", variant="primary", compact=True)

            # ═══════════════════════════════════════════════════════════
            # RIGHT — ACTIVITY
            # ═══════════════════════════════════════════════════════════
            with Vertical(id="activity_pane"):
                status = Vertical(id="run_status", classes="ab-panel")
                status.border_title = "Run status"
                with status:
                    yield StatusBadge("ready", id="run_status_badge")
                    yield Static("", id="run_status_detail")

                last_run = Vertical(id="last_run", classes="ab-panel")
                last_run.border_title = "Last run"
                with last_run:
                    with Horizontal(id="results_badges", classes="hidden"):
                        yield StatusBadge("success", id="results_badge")
                        yield StatusBadge("compliant", id="results_verdict_badge", classes="hidden")
                    yield Static("No runs yet.", id="results_panel")

                # highlight=False: per-line regex highlighting is CPU-costly on
                # busy logs. max_lines bounds memory and re-render cost on
                # long sessions.
                log = Log(id="log_output", highlight=False, max_lines=2000, classes="ab-panel")
                log.border_title = "Execution log"
                yield log

        yield KeyBar("field", id="key_bar")

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
        self._last_status_text: Optional[tuple] = None
        self._outcome_badge: Optional[str] = None
        self._last_telemetry_surface: Optional[str] = None
        self._telemetry_session_started = False
        # Prior privacy-rule-sweep checkbox value while Verified Safe Coverage
        # locks the control; restored when the operator returns to Complete output.
        self._privacy_sweep_before_lock: Optional[bool] = None
        self._restored_privacy_release_mode: Optional[str] = None
        # Suppress preset-driven release-mode refresh until after session restore
        # and any deferred Select.Changed messages from load_presets settle.
        self._tui_bootstrapping = True
        self.load_presets()
        self.setup_logging_capture()
        self._refresh_run_status()
        self._restore_session()
        self._tui_bootstrapping = False
        self.call_after_refresh(self._finalize_privacy_release_mode_bootstrap)

        # Set initial focus
        self.query_one("#csv_path").focus()
        self.notify(
            "Ctrl+O open CSV · Ctrl+R run · F8 advanced · F9 export advanced · Ctrl+L clear log · F1 preset guide",
            title="Keyboard shortcuts",
            severity="information",
            timeout=6,
        )
        # Session starts once the TUI is mounted and usable.
        start_session("tui")
        self._telemetry_session_started = True
        if getattr(self, "_telemetry_session_restored", False):
            session_restored()
        self._emit_surface_if_changed(self._analysis_mode())

    def on_unmount(self) -> None:
        """End telemetry session, then detach log handlers from dead widgets."""
        self._abandon_pending_confirmations()
        finalize_deferred_logging(
            logging.getLogger(),
            privacy_authorized=False,
        )
        if getattr(self, "_telemetry_session_started", False):
            end_session()
            self._telemetry_session_started = False
        root_logger = logging.getLogger()
        for handler in list(root_logger.handlers):
            if isinstance(handler, LogHandler):
                root_logger.removeHandler(handler)

    def _emit_surface_if_changed(self, surface: str) -> None:
        """Emit surface_viewed only when the active share/rate surface changes."""
        if surface not in ("share", "rate"):
            return
        if surface == getattr(self, "_last_telemetry_surface", None):
            return
        surface_viewed(surface)
        self._last_telemetry_surface = surface

    def _handle_validation_modal_result(
        self,
        result: Optional[bool],
        *,
        has_errors: bool,
        should_abort: bool,
        request: AnalysisRunRequest,
        saved_df: Any,
        log_widget: Log,
    ) -> None:
        """Handle ValidationModal dismiss.

        Telemetry: a dismissal that could not have proceeded (errors, so
        Proceed is disabled, or should_abort) is a forced exit, recorded as
        launch_blocked(validation_errors); an explicit Cancel on a modal that
        could proceed is the operator's choice, recorded as
        action_cancelled(validation_review). A None result records nothing.
        """
        if result and not has_errors and not should_abort:
            self.run_analysis(confirmed=True, saved_request=request, saved_df=saved_df)
            return
        action = "share_analysis" if request.is_share else "rate_analysis"
        if result is not None and (has_errors or should_abort):
            launch_blocked(action, "validation_errors")
        elif result is False:
            action_cancelled(action, "validation_review")
        finalize_deferred_logging(
            logging.getLogger(),
            privacy_authorized=False,
        )
        write_log_message(log_widget, "Analysis cancelled by user.")
        self._reset_run_ui()


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
        # Column choices restored from the last session but never applied
        # (no CSV loaded since) are kept, so a quit before loading a file
        # does not erase them.
        for widget_id, value in self._pending_session_selects.items():
            if session.get(widget_id) is None:
                session[widget_id] = value
        for widget_id, values in self._pending_session_lists.items():
            if not session.get(widget_id):
                session[widget_id] = list(values)
        session[SESSION_TAB_KEY] = self._analysis_mode()
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
        with self.batch_update():
            self._apply_session(session)
        # Reported as session_restored once the telemetry session starts.
        self._telemetry_session_restored = bool(session)

    def _apply_session(self, session: Dict[str, Any]) -> None:
        # Legacy sessions may contain governed dataset/output paths and entity
        # selections. Never restore those values; the operator must choose the
        # dataset afresh for each process.
        tab = _SESSION_TABS.get(str(session.get(SESSION_TAB_KEY)))
        if tab is not None:
            try:
                self.query_one(TabbedContent).active = tab
            except NoMatches:
                pass
        for widget_id in SESSION_SELECT_IDS:
            if widget_id == "privacy_release_mode":
                continue  # Restored after checkboxes so sweep coupling sees prior value.
            value = session.get(widget_id)
            if value is None:
                continue
            if widget_id in SESSION_COLUMN_SELECT_IDS:
                # D4: no CSV is loaded yet, so these Selects have no options.
                # Keep the choice until a header load offers the column.
                self._pending_session_selects[widget_id] = value
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
        # Restore release mode after the sweep checkbox so locking preserves the
        # operator's prior sweep preference from the session.
        if "privacy_release_mode" in session:
            self._restore_privacy_release_mode(session.get("privacy_release_mode"))
        for widget_id in SESSION_SELECTION_LIST_IDS:
            values = session.get(widget_id)
            if not isinstance(values, list) or not values:
                continue
            # D4: dims and secondary metrics are column names too; they are
            # applied by the first header load (see _apply_pending_session_columns).
            self._pending_session_lists[widget_id] = list(values)

    def _apply_pending_session_columns(self, cols: List[str]) -> None:
        """Apply restored column choices once a CSV header load offers them.

        Runs inside ``load_csv_headers``' batch update, after the options are
        set and before smart defaults. A stored column missing from this file
        is dropped silently. Pending choices are used by the first header load
        only; a later file never resurrects them.
        """
        selects, self._pending_session_selects = self._pending_session_selects, {}
        lists, self._pending_session_lists = self._pending_session_lists, {}
        available = set(cols)
        for widget_id, value in selects.items():
            if value not in available:
                continue
            try:
                self.query_one(f"#{widget_id}", Select).value = value
            except Exception:
                continue  # Widget gone, or the value is no longer an option.
        for widget_id, values in lists.items():
            try:
                s_list = self.query_one(f"#{widget_id}", SelectionList)
            except NoMatches:
                continue
            for value in values:
                if value in available:
                    s_list.select(value)

    def _restore_privacy_release_mode(self, value: Any) -> None:
        """Restore a session release mode; unknown values fall back safely."""
        try:
            select = self.query_one("#privacy_release_mode", Select)
        except NoMatches:
            return
        if value in _PRIVACY_RELEASE_MODE_VALUES:
            try:
                select.value = value
                self._restored_privacy_release_mode = str(value)
            except Exception:
                select.value = PrivacyReleaseMode.COMPLETE_OUTPUT.value
                self._restored_privacy_release_mode = (
                    PrivacyReleaseMode.COMPLETE_OUTPUT.value
                )
            return
        select.value = PrivacyReleaseMode.COMPLETE_OUTPUT.value
        self._restored_privacy_release_mode = PrivacyReleaseMode.COMPLETE_OUTPUT.value
        self.notify(
            "The saved release mode is no longer available, so the release "
            "fell back to Complete output.",
            title="Session restore",
            severity="warning",
            timeout=6,
        )

    def _finalize_privacy_release_mode_bootstrap(self) -> None:
        """Re-assert session release mode after deferred preset events settle."""
        restored = getattr(self, "_restored_privacy_release_mode", None)
        if restored is not None:
            try:
                select = self.query_one("#privacy_release_mode", Select)
                if select.value != restored:
                    select.value = restored
            except NoMatches:
                pass
        self._sync_privacy_release_mode_visibility()
        self._apply_privacy_release_mode_coupling(
            self._privacy_release_mode_value_from_widget()
        )

    # ──────────────────────────────────────────────────────────────────
    # Run status / results panels
    # ──────────────────────────────────────────────────────────────────

    # App run state -> status-language badge (tui.status). "validating" is
    # its own app state (a ValidationModal may still be open), shown as
    # RUNNING with a "Validating" detail.
    _STATE_BADGES: Dict[str, "RunBadge"] = {
        "idle": RunBadge("ready"),
        "validating": RunBadge("running", "Validating"),
        "running": RunBadge("running"),
        "success": RunBadge("success"),
        "error": RunBadge("error"),
        "blocked": RunBadge("blocked"),
        "cancelled": RunBadge("cancelled"),
    }

    def _current_run_badge(self) -> "RunBadge":
        state = getattr(self, "_run_state", "idle")
        if state == "validating" and isinstance(self.screen, ModalScreen):
            return RunBadge("awaiting")
        if state == "blocked" and getattr(self, "_outcome_badge", None):
            return RunBadge(self._outcome_badge)
        return self._STATE_BADGES.get(state, self._STATE_BADGES["idle"])

    def _refresh_run_status(self) -> None:
        badge = self._current_run_badge()
        preset = None
        try:
            preset_val = self.query_one("#preset_select", Select).value
            preset = None if preset_val == SELECT_BLANK else preset_val
        except NoMatches:
            pass
        mode = self._run_mode or self._analysis_mode()
        lines = [
            f"[$text-muted]Mode[/]    {escape_markup(labels.text_for(labels.ANALYSIS_MODE, mode))}",
            f"[$text-muted]Preset[/]  {escape_markup(_preset_display(preset))}",
        ]
        if self._run_started_at is not None and self._run_state == "running":
            elapsed = time.monotonic() - self._run_started_at
            lines.append(f"[$text-muted]Elapsed[/] {elapsed:.0f} s")
            stage = _RUN_STAGE_LABELS.get(self._run_stage or "")
            if stage:
                lines.append(f"[$text-muted]Stage[/]   {escape_markup(stage)}")
        text = "\n".join(lines)
        key = (badge, text)
        if key == self._last_status_text:
            return  # Nothing changed; skip the repaint.
        try:
            self.query_one("#run_status_badge", StatusBadge).set_status(badge.state, badge.detail)
            self.query_one("#run_status_detail", Static).update(text)
            self._last_status_text = key
        except NoMatches:
            pass
        self._update_key_bar()

    # ── Key bar context (tui.keybar) ──────────────────────────────────────

    def _key_bar_context(self) -> str:
        if getattr(self, "_run_state", "idle") in ("running", "validating"):
            return "running"
        focused = self.focused
        context = "field"
        if focused is not None:
            chain = list(focused.ancestors_with_self)
            if any(isinstance(node, Select) for node in chain):
                context = "select"
            elif isinstance(focused, SelectionList):
                context = "list"
            elif isinstance(focused, Checkbox):
                context = "toggle"
            elif isinstance(focused, (Button, CollapsibleTitle)):
                context = "button"
            elif isinstance(focused, Tabs):
                context = "tabs"
        if context == "field" and getattr(self, "_run_state", "idle") in ("success", "error", "blocked", "cancelled"):
            return "results"
        return context

    def _update_key_bar(self) -> None:
        try:
            bar = self.query_one("#key_bar", KeyBar)
        except NoMatches:
            return
        bar.set_context(self._key_bar_context())

    def on_descendant_focus(self, event: Any) -> None:
        self._update_key_bar()

    def on_descendant_blur(self, event: Any) -> None:
        self._update_key_bar()

    def action_copy_or_quit(self) -> None:
        """Ctrl+C: copy a text selection if there is one, otherwise quit."""
        focused = self.focused
        if isinstance(focused, Input) and not focused.selection.is_empty:
            focused.action_copy()
            return
        try:
            selected = self.screen.get_selected_text()
        except Exception:
            selected = None
        if selected:
            self.copy_to_clipboard(selected)
            return
        if isinstance(self.screen, ConfirmScreen) and self.screen.confirm_label == "Quit":
            return  # The quit question is already open.
        self.action_quit()

    def _begin_validation_ui(self) -> None:
        """Switch UI into the pre-run validation state (app thread only).

        Disables the run button (to block double launches) and shows a
        distinct ``Validating`` badge, but deliberately does NOT start the
        elapsed clock or the ``running`` badge: execution has not begun yet,
        and a ``ValidationModal`` may still be awaiting the user's decision.
        """
        self._run_state = "validating"
        self._run_started_at = None
        self._run_mode = "privacy-sweep" if self._privacy_sweep_enabled() else self._analysis_mode()
        btn = self.query_one("#btn_run", Button)
        btn.disabled = True
        btn.label = "Validating…"
        if self._elapsed_timer is not None:
            self._elapsed_timer.stop()
            self._elapsed_timer = None
        self._refresh_run_status()
        self._save_session()

    def _begin_run_ui(self) -> None:
        """Switch UI into the running state (app thread only)."""
        self._run_state = "running"
        self._run_started_at = time.monotonic()
        self._run_stage = None
        self._run_mode = "privacy-sweep" if self._privacy_sweep_enabled() else self._analysis_mode()
        btn = self.query_one("#btn_run", Button)
        btn.disabled = True
        btn.label = "Running…"
        if self._elapsed_timer is not None:
            self._elapsed_timer.stop()
        self._elapsed_timer = self.set_interval(1.0, self._refresh_run_status)
        self._refresh_run_status()
        self._save_session()

    def _end_run_ui(
        self,
        state: str,
        summary_markup: str,
        badge: Optional[str] = None,
        verdict: Optional[str] = None,
    ) -> None:
        """Restore UI after a run and publish the last-run summary (app thread only).

        ``state`` is the app run state (success/error/blocked). ``badge``
        overrides its status-language badge (``withheld`` for a privacy
        denial) and ``verdict`` adds a second badge (``compliant`` or
        ``warning``) next to DONE.
        """
        self._run_state = state
        self._outcome_badge = badge
        self._run_stage = None
        if self._elapsed_timer is not None:
            self._elapsed_timer.stop()
            self._elapsed_timer = None
        elapsed = None
        if self._run_started_at is not None:
            elapsed = time.monotonic() - self._run_started_at
        self._run_started_at = None
        btn = self.query_one("#btn_run", Button)
        btn.disabled = False
        btn.label = "▶  Run Privacy Sweep" if self._privacy_sweep_enabled() else "▶  Run Analysis"
        self._refresh_run_status()

        header = f"Finished {datetime.now().strftime('%H:%M:%S')}"
        if elapsed is not None:
            header += f" · {elapsed:.1f} s"
        self.query_one("#results_panel", Static).update(f"[$text-muted]{header}[/]\n{summary_markup}".strip())
        try:
            self.query_one("#results_badges").remove_class("hidden")
            self.query_one("#results_badge", StatusBadge).set_status(self._current_run_badge().state)
            verdict_badge = self.query_one("#results_verdict_badge", StatusBadge)
            if verdict:
                verdict_badge.set_status(verdict)
            verdict_badge.set_class(not verdict, "hidden")
        except NoMatches:
            pass

    def _reset_run_ui(self) -> None:
        """Re-enable the run controls after an aborted launch (app thread only)."""
        self._run_state = "idle"
        self._outcome_badge = None
        if self._elapsed_timer is not None:
            self._elapsed_timer.stop()
            self._elapsed_timer = None
        self._run_started_at = None
        btn = self.query_one("#btn_run", Button)
        btn.disabled = False
        btn.label = "▶  Run Privacy Sweep" if self._privacy_sweep_enabled() else "▶  Run Analysis"
        self._refresh_run_status()

    def _telemetry_action(self) -> str:
        """Telemetry action of the current launch (closed: share/rate_analysis)."""
        action = getattr(self, "_run_action", None)
        if action in ("share_analysis", "rate_analysis"):
            # Set from the RunInputs snapshot, so worker threads never query
            # the tabs (D7).
            return action
        mode = getattr(self, "_run_mode", None)
        if mode not in ("share", "rate"):
            try:
                mode = self._analysis_mode()
            except Exception:
                # Telemetry must never break an error path (e.g. teardown).
                mode = "share"
        return "share_analysis" if mode == "share" else "rate_analysis"

    def _fail_launch(
        self,
        message: str,
        focus_id: Optional[str] = None,
        *,
        block_reason: Optional[str] = None,
        title_state: str = "notready",
    ) -> None:
        """Notify about an invalid launch and return UI to idle (worker-safe).

        ``block_reason`` is a closed LAUNCH_BLOCK_REASONS value recorded as
        ``launch_blocked``; ``message`` never reaches telemetry.
        ``title_state`` picks the status-language toast title (tui.status).
        """
        if block_reason is not None:
            launch_blocked(self._telemetry_action(), block_reason)
        finalize_deferred_logging(
            logging.getLogger(),
            privacy_authorized=False,
        )
        # Resolved on the UI thread at mount; workers must not query the DOM.
        log_widget = getattr(self, "_log_widget", None) or self.query_one("#log_output", Log)
        write_log_message(log_widget, f"ERROR: {message}")
        self.call_from_thread(
            self.notify, message, title=status_text(title_state), severity="error", markup=False
        )
        self.call_from_thread(self._reset_run_ui)
        if focus_id:
            def _focus() -> None:
                try:
                    self.query_one(f"#{focus_id}").focus()
                except NoMatches:
                    pass
            self.call_from_thread(_focus)

    def _confirm_accuracy_first_consent(self) -> bool:
        """Ask for explicit per-run consent to the accuracy_first posture.

        Runs on the analysis worker thread; blocks until the operator answers
        the modal on the app thread. Consent is never persisted or restored.
        """
        return self._await_confirmation(
            ConfirmScreen(
                "Consent needed for this run\n\n"
                "This preset uses the Accuracy first compliance posture "
                "(accuracy_first): it prioritizes analytical fidelity over "
                "strict compliance and may produce a NON-PUBLISHABLE "
                "diagnostic report. Consent applies to this run only.\n\n"
                "Proceed with this run?",
                confirm_label="I understand — proceed",
            )
        )

    def _confirm_clearing_spend_basis(self, total_col: str) -> bool:
        """Ask for the fraud clearing-spend attestation for this run attempt."""
        return self._await_confirmation(ClearingSpendConfirmScreen(total_col))

    def _await_confirmation(self, screen: ModalScreen) -> bool:
        """Show ``screen`` from the worker thread and block until it is answered.

        A quit or unmount abandons every pending confirmation as declined (see
        ``_abandon_pending_confirmations``); without that, the worker would
        wait forever and keep the process alive after the UI has gone.
        """
        decision: Dict[str, bool] = {}
        answered = threading.Event()

        def _on_dismiss(result: Optional[bool]) -> None:
            decision["value"] = bool(result)
            answered.set()

        with self._confirmation_lock:
            if self._confirmations_abandoned:
                return False
            self._pending_confirmations.add(answered)
        try:
            self.call_from_thread(self.push_screen, screen, _on_dismiss)
            answered.wait()
        finally:
            with self._confirmation_lock:
                self._pending_confirmations.discard(answered)
        if self._confirmations_abandoned:
            return False
        return decision.get("value", False)

    def _abandon_pending_confirmations(self) -> None:
        """Release worker threads blocked on a confirmation, as declined."""
        with self._confirmation_lock:
            self._confirmations_abandoned = True
            pending = list(self._pending_confirmations)
            self._pending_confirmations.clear()
        for answered in pending:
            answered.set()

    def _execute_run_for_tui(self, request: AnalysisRunRequest, logger: logging.Logger, log_widget: Log):
        """Run analysis while keeping library print output inside the TUI log.

        Textual captures process stdout while the app is running. In some Windows
        headless/release runners, forwarding captured prints back to the original
        console can raise ``OSError: [WinError 6] The handle is invalid``. Console
        output from the shared CLI seam is useful context, not a reason to fail
        the TUI run, so capture it and append it to the Log widget instead.
        """
        stdout = io.StringIO()
        stderr = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                # Owner decision 1: core stops at its next phase boundary once
                # request_cancel() is called, never after output has started.
                artifacts = execute_run(
                    request,
                    logger,
                    cancel_requested=self._cancel_event.is_set,
                    on_stage=self._report_run_stage,
                )
        finally:
            output = "\n".join(part.strip() for part in (stdout.getvalue(), stderr.getvalue()) if part.strip())
            if output:
                write_log_message(log_widget, output)
        return artifacts

    def _report_run_stage(self, stage: str) -> None:
        """Engine stage callback (worker thread): never waits for the UI."""
        try:
            self.call_later(self._set_run_stage, stage)
        except Exception:
            pass  # Progress display only; the run must not depend on it.

    def _set_run_stage(self, stage: Optional[str]) -> None:
        """Show the engine stage in the run-status text (app thread only)."""
        self._run_stage = stage
        self._refresh_run_status()

    @staticmethod
    def _safe_coverage_summary_facts(artifacts: AnalysisArtifacts) -> Optional[Dict[str, Any]]:
        """Return client-safe Verified Safe Coverage facts, or None.

        Reads only ``CoverageCertificate`` and ``coverage_certificate_output``.
        Never surfaces suppressed keys, category names, or failure details.
        """
        certificate = artifacts.coverage_certificate
        if certificate is None:
            return None
        if certificate.privacy_release_mode is not PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE:
            return None
        return {
            "mode": "Verified safe coverage",
            "candidate_unit_count": certificate.candidate_unit_count,
            "released_unit_count": certificate.released_unit_count,
            "suppressed_unit_count": certificate.suppressed_unit_count,
            "coverage_percentage": certificate.coverage_percentage,
            "coverage_certificate_output": artifacts.coverage_certificate_output,
            "independent_verification_passed": True,
        }

    @classmethod
    def _format_safe_coverage_summary_markup(
        cls, artifacts: AnalysisArtifacts
    ) -> List[str]:
        """Markup lines for the Last Run panel (client-safe facts only)."""
        facts = cls._safe_coverage_summary_facts(artifacts)
        if facts is None:
            return []
        lines = [
            f"[$text-muted]Release[/]  {facts['mode']}",
            (
                f"[$text-muted]Coverage[/] "
                f"{facts['released_unit_count']}/{facts['candidate_unit_count']} "
                f"released · {facts['suppressed_unit_count']} suppressed · "
                f"{facts['coverage_percentage']:.4g}%"
            ),
        ]
        cert_path = facts["coverage_certificate_output"]
        if cert_path:
            lines.append(f"[$text-muted]Certificate[/] {escape_markup(str(cert_path))}")
        if facts["independent_verification_passed"]:
            lines.append("[$text-muted]Status[/]  Independent privacy verification passed")
        return lines

    @classmethod
    def _format_safe_coverage_summary_plain(
        cls, artifacts: AnalysisArtifacts
    ) -> List[str]:
        """Plain lines for the execution log (client-safe facts only)."""
        facts = cls._safe_coverage_summary_facts(artifacts)
        if facts is None:
            return []
        lines = [
            f"Privacy release mode: {facts['mode']}",
            f"Candidate units: {facts['candidate_unit_count']}",
            f"Released units: {facts['released_unit_count']}",
            f"Suppressed units: {facts['suppressed_unit_count']}",
            f"Coverage: {facts['coverage_percentage']:.4g}%",
        ]
        cert_path = facts["coverage_certificate_output"]
        if cert_path:
            lines.append(f"Coverage Certificate: {cert_path}")
        if facts["independent_verification_passed"]:
            lines.append("Independent privacy verification: passed")
            lines.append("Coverage is not a maximum claim.")
        return lines

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

    def _resolve_csv_path(self, raw_path: str, *, quiet: bool = False) -> Optional[str]:
        """Normalize and validate a CSV path from manual entry or browse.

        ``quiet`` skips the not-found notice, log line and telemetry; callers
        that only need the same normalization as the header load (entity
        loading, D8) use it so one bad path is reported once.
        """
        csv_path = raw_path.strip()
        if not csv_path:
            return None
        if not os.path.isfile(csv_path):
            if quiet:
                return None
            self._emit_dataset_load("not_found", csv_path)
            self.notify(
                f"Not found: {csv_path}. Check the folder, or press Ctrl+O to browse.",
                title="CSV file not found",
                severity="error",
                timeout=6,
                markup=False,
            )
            self.query_one("#log_output").write(f"CSV file not found: {csv_path}\n")
            return None
        return csv_path

    def _try_load_csv_from_path_input(self, raw_path: Optional[str] = None) -> None:
        """Load headers when the user submits or leaves the CSV path field."""
        if raw_path is None:
            raw_path = self.query_one("#csv_path", Input).value
        csv_path = self._resolve_csv_path(raw_path)
        if csv_path:
            self.load_csv_headers(csv_path)

    def load_csv_headers(self, file_path, announce: bool = True):
        """Load CSV headers and populate Select widgets."""
        headers_read = False
        try:
            resolved = self._resolve_csv_path(file_path)
            if not resolved:
                return
            file_path = resolved
            # Read only headers
            cols = pd.read_csv(file_path, nrows=0).columns.tolist()
            headers_read = True
            self._emit_dataset_load("loaded", file_path)
            self.csv_columns = cols
            options = [(c, c) for c in cols]
            selection_options = [(c, c) for c in cols]

            # Repopulating ten widgets repaints once, not ten times.
            with self.batch_update():
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

                # D4: restored session column choices win over smart defaults.
                self._apply_pending_session_columns(cols)

                # Fill smart defaults for selects that are still empty. The
                # rate Total column has none (owner decision 4): it is the
                # clearing-spend basis and must always be an explicit choice.
                defaults = {
                    "entity_col": "issuer_name",
                    "share_metric": "txn_cnt",
                    "rate_approved": "app_cnt",
                }
                for select_id, column in defaults.items():
                    select = self.query_one(f"#{select_id}", Select)
                    if column in cols and select.value == SELECT_BLANK:
                        select.value = column

                self._update_csv_meta(file_path, cols)

            # A new file with an unchanged entity column posts no
            # Select.Changed, so refresh the entity values explicitly. Requests
            # for values already loaded or in flight are no-ops.
            entity_col_value = self.query_one("#entity_col", Select).value
            if entity_col_value != SELECT_BLANK:
                self.load_unique_entities(entity_col_value)
            if announce:
                self.notify(
                    f"Loaded {len(cols)} columns from {os.path.basename(file_path)}",
                    title="CSV loaded",
                    severity="information",
                    timeout=5,
                    markup=False,
                )

        except Exception as e:
            if not headers_read:
                self._emit_dataset_load("header_read_failed", file_path)
            self.query_one("#log_output").write(f"Error reading CSV headers: {e}\n")
            first_line = str(e).splitlines()[0] if str(e) else type(e).__name__
            self.notify(
                f"Can't read this file as CSV: {first_line}. Check that it is comma-separated text.",
                title="CSV not loaded",
                severity="error",
                markup=False,
            )

    def _emit_dataset_load(self, outcome: str, file_path: Any) -> None:
        """Record a closed dataset_load outcome once per (outcome, file).

        Blur and Enter both reload the same path, so repeats are dropped. The
        path is only compared in memory; telemetry receives ``outcome`` alone.
        """
        key = (outcome, str(file_path))
        if key == getattr(self, "_last_dataset_telemetry", None):
            return
        self._last_dataset_telemetry = key
        dataset_load(outcome)

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
        # Literal text: file and column names come from the operator's data.
        self.query_one("#csv_meta", Static).update(
            Text(
                f"{status_glyph('success')} {os.path.basename(file_path)} · "
                f"{len(cols)} columns · {size_text}\n{preview}"
            )
        )

    def update_secondary_options(self, list_id, exclude=None):
        """Update options in a SelectionList, excluding specified values."""
        if not hasattr(self, 'csv_columns'):
            return

        if exclude is None:
            exclude = []

        try:
            s_list = self.query_one(list_id, SelectionList)
        except NoMatches:
            return
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
            self._try_load_csv_from_path_input(event.input.value)

    def on_input_blurred(self, event: Input.Blurred) -> None:
        """Handle focus leaving text inputs."""
        if getattr(self, "_exit", False):
            # The focused input blurs during app teardown; reloading the CSV
            # then would post Changed messages into a dying message pump.
            return
        if event.input.id == "csv_path":
            try:
                self._try_load_csv_from_path_input(event.input.value)
            except NoMatches:
                # Blur fires for the focused input while the app is tearing
                # down (e.g. on exit); the rest of the form may already be
                # unmounted, so there is nothing left to populate.
                pass

    # ──────────────────────────────────────────────────────────────────
    # Presets / advanced overrides
    # ──────────────────────────────────────────────────────────────────

    def load_presets(self):
        """Load available presets through the shared preset workflow."""
        self.preset_workflow = PresetWorkflow()
        presets = self.preset_workflow.list_presets()
        options = [(preset, preset) for preset in presets] or [("standard", "standard")]
        self.query_one("#preset_select").set_options(options)
        default_preset = (
            DEFAULT_PRESET_NAME
            if DEFAULT_PRESET_NAME in presets
            else (options[0][0] if options else None)
        )
        self.query_one("#preset_select").value = default_preset
        if default_preset:
            self.update_advanced_parameters(default_preset)
            self._update_preset_blurb(default_preset)
        self.advanced_config_path = None
        # Do not refresh privacy_release_mode here: load_presets runs before
        # session restore, and a deferred preset Select.Changed must not wipe
        # a restored Verified Safe Coverage selection. User-driven preset
        # changes refresh via on_select_changed.

    def _update_preset_blurb(self, preset_name: str) -> None:
        """Show the preset's description and privacy posture under the selector.

        The posture is shown before the run (02 §5.4 #11), so a Best effort or
        Accuracy first run is never a surprise in the log afterwards.
        """
        description = ""
        posture = None
        try:
            data = self.preset_workflow.load_preset_data(preset_name)
            if isinstance(data, dict):
                description = labels.strip_preset_description(str(data.get("description") or ""))
                posture = data.get("compliance_posture")
        except Exception:
            description = ""
        lines = [description] if description else []
        if posture:
            posture_label = labels.label_for(labels.POSTURE, posture)
            mark = f"{status_glyph('warning')} " if posture in ("best_effort", "accuracy_first") else ""
            lines.append(f"{mark}Privacy posture: {posture_label.primary}. {posture_label.why}".rstrip())
        try:
            self.query_one("#preset_blurb", Static).update(Text("\n".join(lines)))
        except NoMatches:
            pass

    def _warn_missing_widget(self, widget_id: str) -> None:
        logging.getLogger(__name__).warning("Advanced widget not found: %s", widget_id)
        self.notify(
            f"Couldn't show the advanced setting {widget_id}; the preset value is used.",
            title="Advanced optimization",
            severity="warning",
            timeout=4,
            markup=False,
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

    @property
    def _override_builder(self) -> ConfigOverrideBuilder:
        """Shared builder; rebuilding its spec table per field is wasteful."""
        builder = getattr(self, "_override_builder_cache", None)
        if builder is None:
            builder = ConfigOverrideBuilder()
            self._override_builder_cache = builder
        return builder

    def _read_field_value_from_preset(self, data: Dict[str, Any], spec: ConfigFieldSpec) -> Any:
        return self._override_builder.read_field(data, spec)

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
        data = self._load_advanced_parameter_data(preset_name)

        # ~20 widgets get reset and rewritten; one repaint instead of dozens.
        with self.batch_update():
            for inp in self.query(Input):
                if inp.id and inp.id.startswith("adv_"):
                    inp.value = ""
            for cb in self.query(Checkbox):
                if cb.id and cb.id.startswith("adv_"):
                    cb.value = False

            if not data:
                return

            for spec in self.ADVANCED_FIELD_SPECS:
                value = self._read_field_value_from_preset(data, spec)
                if value is None:
                    continue
                if spec.kind == "input":
                    self._safe_set_input(spec.widget_id, value)
                else:
                    self._safe_set_checkbox(spec.widget_id, value)

    def _collect_advanced_override_data(self) -> Dict[str, Any]:
        values: Dict[str, Any] = {}
        for spec in self.ADVANCED_FIELD_SPECS:
            widget_id = spec.widget_id
            values[widget_id] = self._get_bool(widget_id) if spec.kind == "checkbox" else self._get_input(widget_id)
        return self._override_builder.read_from_mapping(values)

    def apply_advanced_overrides(self) -> None:
        """Generate a temporary YAML config file from advanced inputs and set path for analysis."""
        yaml_data = self._collect_advanced_override_data()
        if not yaml_data:
            advanced_override("empty")
            self.notify(
                "No advanced values to apply. Enter at least one value, then apply again.",
                title="Advanced overrides",
                severity="warning",
                timeout=4,
            )
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
            self._advanced_config_preset = (
                str(preset_val) if preset_val and preset_val != SELECT_BLANK else None
            )
            # Optimization override files usually omit privacy_release_mode; only
            # refresh the Select when the loaded YAML declares the field.
            if self._config_file_declares_privacy_release_mode(str(tmp_path)):
                self._refresh_privacy_release_mode_from_config()
            self.notify(
                f"Advanced overrides apply to the next runs. File: {tmp_path}",
                title="Advanced overrides",
                severity="information",
                timeout=6,
                markup=False,
            )
            advanced_override("applied")
        except Exception as e:
            advanced_override("failed")
            self.notify(
                f"Couldn't save the advanced overrides for this run. Why: {e}. "
                "Next: check that the working folder is writable, then apply again.",
                title=status_text("error"),
                severity="error",
                timeout=6,
                markup=False,
            )

    def _invalidate_stale_advanced_override(self, preset: Optional[str]) -> bool:
        """Drop an applied override file written for a different preset (D2).

        The file carries the old preset's ``compliance_posture`` and values;
        sending it with the new preset would run the old posture and skip
        the new preset's consent. The file itself stays in the launch folder
        (owner decision 2); it is simply no longer sent. Returns True when an
        override was dropped.
        """
        if not getattr(self, "advanced_config_path", None):
            return False
        if self._advanced_config_preset == preset:
            return False
        self.advanced_config_path = None
        self._advanced_config_preset = None
        self.notify(
            "The preset changed, so the advanced overrides applied for the "
            "previous preset will not be used. Review the values and press "
            "Apply overrides again to use them with this preset.",
            title="Advanced overrides cleared",
            severity="warning",
            timeout=8,
            markup=False,
        )
        return True

    def _effective_compliance_posture(
        self, preset: Optional[str], config_path: Optional[str]
    ) -> Optional[str]:
        """The posture core will run with for this preset and override file.

        With an override file, the posture comes from resolving preset + file
        exactly as ``build_run_config`` does (the file declares the posture
        it was written with). Without one, it is the preset's posture.
        """
        if not hasattr(self, "preset_workflow"):
            self.preset_workflow = PresetWorkflow()
        if config_path:
            try:
                posture = ConfigManager(config_file=config_path, preset=preset).config.get(
                    "compliance_posture"
                )
                if posture:
                    return str(posture)
            except Exception:
                logging.getLogger(__name__).warning(
                    "Could not resolve the effective compliance posture of the "
                    "advanced override; falling back to the declared values",
                    exc_info=True,
                )
            try:
                with open(config_path, encoding="utf-8") as handle:
                    declared = yaml.safe_load(handle) or {}
                if isinstance(declared, dict) and declared.get("compliance_posture"):
                    return str(declared["compliance_posture"])
            except Exception:
                pass
        if preset:
            preset_data = self.preset_workflow.load_preset_data(preset)
            if isinstance(preset_data, dict):
                posture = preset_data.get("compliance_posture")
                return str(posture) if posture else None
        return None

    def setup_logging_capture(self):
        """Redirect logging to the TUI Log widget."""
        log_widget = self.query_one("#log_output", Log)
        self._log_widget = log_widget
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
            surface_viewed("preset_help")
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
        if self._run_state in ("running", "validating"):
            def on_confirm(confirmed: Optional[bool]) -> None:
                if confirmed:
                    # G15: name the abandoned intent; "running" means the run
                    # already emitted action_attempted.
                    if self._run_state == "running":
                        action_cancelled(self._telemetry_action(), "quit_during_run")
                    elif self._run_state == "validating":
                        action_cancelled(self._telemetry_action(), "quit_before_run")
                    # Owner decision 1: stop the run at its next safe
                    # checkpoint instead of letting the engine finish (and
                    # keep the process alive) after the UI is gone.
                    self.request_cancel()
                    self._abandon_pending_confirmations()
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

    def _privacy_sweep_enabled(self) -> bool:
        try:
            return bool(self.query_one("#privacy_rule_sweep_mode", Checkbox).value)
        except NoMatches:
            return False

    def _privacy_release_mode_value_from_widget(self) -> str:
        """Return the stored Select value, defaulting to complete-output."""
        try:
            value = self.query_one("#privacy_release_mode", Select).value
        except NoMatches:
            return PrivacyReleaseMode.COMPLETE_OUTPUT.value
        if value == SELECT_BLANK or value is None:
            return PrivacyReleaseMode.COMPLETE_OUTPUT.value
        return str(value)

    def _privacy_release_mode_from_widget(self) -> PrivacyReleaseMode:
        """Return the selected PrivacyReleaseMode enum for share requests."""
        value = self._privacy_release_mode_value_from_widget()
        try:
            return PrivacyReleaseMode(value)
        except ValueError:
            return PrivacyReleaseMode.COMPLETE_OUTPUT

    def _privacy_values_from_widgets(self) -> Dict[str, Any]:
        """Return privacy request fields from TUI widgets.

        Includes rule strategy, release mode (share only), and compliance
        attestations. Rate analysis never receives a hidden Maximum Safe
        Coverage selection from the release-mode widget.
        """
        values: Dict[str, Any] = {
            "privacy_rule_strategy": (
                PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE
                if self._privacy_sweep_enabled()
                else PrivacyRuleStrategy.SELECT_BY_PEER_COUNT
            ),
            "is_anonymized_aggregated_merchant_spend": self.query_one(
                "#privacy_merchant_spend_scope",
                Checkbox,
            ).value,
            "citibank_entity_name": (
                self.query_one("#citibank_entity_name", Input).value.strip()
                or None
            ),
            "citi_competitor_receives_output": self.query_one(
                "#citi_competitor_receives_output",
                Checkbox,
            ).value,
        }
        if self._analysis_mode() == "share":
            values["privacy_release_mode"] = self._privacy_release_mode_from_widget()
        else:
            # Do not let a hidden verified-safe-coverage widget value reach a
            # rate request. Leave None so configuration resolution stays clear.
            values["privacy_release_mode"] = None
        return values

    def _sync_privacy_release_mode_visibility(self) -> None:
        """Show the release-mode control for share; hide it for rate."""
        hide = self._analysis_mode() != "share"
        for widget_id in (
            "privacy_release_mode_label",
            "privacy_release_mode",
            "privacy_release_mode_hint",
        ):
            try:
                widget = self.query_one(f"#{widget_id}")
            except NoMatches:
                continue
            if hide:
                widget.add_class("hidden")
            else:
                widget.remove_class("hidden")

    def _apply_privacy_release_mode_coupling(self, mode_value: str) -> None:
        """Enable and lock rule sweep while Verified Safe Coverage is active.

        Owner decision 6: the lock applies only while VSC is selected *and*
        the Share tab is active. Rate requests never carry a release mode, so
        on the Rate tab the checkbox is unlocked, shows the operator's own
        value again, and the request sends exactly that value.
        """
        try:
            sweep = self.query_one("#privacy_rule_sweep_mode", Checkbox)
        except NoMatches:
            return
        if (
            mode_value == PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE.value
            and self._analysis_mode() == "share"
        ):
            if getattr(self, "_privacy_sweep_before_lock", None) is None:
                self._privacy_sweep_before_lock = bool(sweep.value)
            sweep.value = True
            sweep.disabled = True
            return
        was_locked = sweep.disabled
        sweep.disabled = False
        prior = getattr(self, "_privacy_sweep_before_lock", None)
        if was_locked and prior is not None:
            sweep.value = prior
        self._privacy_sweep_before_lock = None

    def _config_file_declares_privacy_release_mode(self, path: str) -> bool:
        """Return True when a YAML/JSON config file sets privacy_release_mode."""
        try:
            with open(path, encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
        except Exception:
            return False
        return isinstance(data, dict) and "privacy_release_mode" in data

    def _refresh_privacy_release_mode_from_config(self) -> None:
        """Refresh the Select from the resolved preset/YAML configuration."""
        try:
            preset_val = self.query_one("#preset_select", Select).value
        except NoMatches:
            return
        preset = None if preset_val == SELECT_BLANK else str(preset_val)
        config_file = getattr(self, "advanced_config_path", None)
        try:
            resolved = ConfigManager(
                config_file=config_file,
                preset=preset,
            ).resolve()
            mode_value = resolved.privacy_release_mode.value
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Could not resolve privacy_release_mode from configuration: %s",
                exc,
            )
            return
        try:
            select = self.query_one("#privacy_release_mode", Select)
        except NoMatches:
            return
        if select.value != mode_value:
            select.value = mode_value
        self._apply_privacy_release_mode_coupling(mode_value)

    def action_show_help(self) -> None:
        """Show preset help (F1)."""
        surface_viewed("preset_help")
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

    # Entity value loading runs in a background worker. These track, on the UI
    # thread only, which (csv_path, column) is in flight, which one the current
    # #entity_name options were built from, and the entity the operator had
    # chosen so it can be re-selected once the matching load completes.
    _entity_load_key: Optional[tuple] = None
    _entity_options_key: Optional[tuple] = None
    _pending_entity_value: Any = SELECT_BLANK

    def _entity_source_key(self) -> Optional[tuple]:
        """The (csv_path, entity column) the form currently points at."""
        try:
            raw_path = self.query_one("#csv_path", Input).value
            column = self.query_one("#entity_col", Select).value
        except NoMatches:
            return None
        csv_path = self._resolve_csv_path(raw_path, quiet=True)
        if not csv_path or column == SELECT_BLANK:
            return None
        return (csv_path, column)

    def load_unique_entities(self, column_name) -> None:
        """Populate ``#entity_name`` with the column's values, off the UI thread.

        The CSV read happens in ``_load_unique_entities_worker``; this method
        only flips the Select into its loading state and starts the worker. A
        request for the (path, column) that is already loading or already shown
        is a no-op, so the explicit call and the ``Select.Changed`` it causes
        do not read the file twice.
        """
        try:
            raw_path = self.query_one("#csv_path", Input).value
            entity_select = self.query_one("#entity_name", Select)
        except NoMatches:
            # Deferred Select.Changed arriving while the app tears down.
            return
        # D8: the same normalization as the header load, so a path with
        # surrounding spaces loads entities as well as headers.
        csv_path = self._resolve_csv_path(raw_path, quiet=True)
        if not csv_path:
            return
        key = (csv_path, column_name)
        if key == self._entity_load_key:
            return
        if self._entity_load_key is None and key == self._entity_options_key:
            return

        # Remember the operator's choice before the options are replaced; it is
        # re-applied when this load lands if the value exists in the new column.
        if entity_select.value != SELECT_BLANK:
            self._pending_entity_value = entity_select.value
        if key != self._entity_options_key:
            # Options from another file/column are meaningless for this one.
            entity_select.set_options([])
            self._entity_options_key = None
        entity_select.prompt = ENTITY_LOADING_PROMPT
        entity_select.disabled = True
        self._entity_load_key = key
        self._load_unique_entities_worker(csv_path, column_name)

    @work(thread=True, exclusive=True, group="entity_values", exit_on_error=False)
    def _load_unique_entities_worker(self, csv_path: str, column_name: str) -> None:
        """Read the entity column on a worker thread and hand results back."""
        worker = get_current_worker()
        values: Optional[List[str]] = None
        error: Optional[Exception] = None
        try:
            values = read_unique_entity_values(csv_path, column_name)
        except Exception as exc:  # reported on the UI thread like before
            error = exc
        if worker.is_cancelled:
            return  # superseded by a newer request (exclusive group) or exit
        try:
            self.call_from_thread(
                self._apply_unique_entities, (csv_path, column_name), values, error
            )
        except RuntimeError:
            pass  # App loop already gone (shutdown); nothing to update.

    def _apply_unique_entities(
        self,
        key: tuple,
        values: Optional[List[str]],
        error: Optional[Exception],
    ) -> None:
        """Apply a finished entity load on the UI thread, unless it is stale."""
        if getattr(self, "_exit", False):
            return
        if key != self._entity_load_key:
            return  # A newer request owns the loading state.
        self._entity_load_key = None
        try:
            entity_select = self.query_one("#entity_name", Select)
            log_output = self.query_one("#log_output", Log)
        except NoMatches:
            return
        try:
            if key != self._entity_source_key():
                # CSV path or entity column changed while reading without a
                # replacement load (e.g. column cleared): drop the old values.
                return
            if error is not None:
                dataset_load("entity_list_failed")
                log_output.write(f"Error loading entities: {error}\n")
                return
            values = values or []
            desired = self._pending_entity_value
            self._pending_entity_value = SELECT_BLANK
            with self.batch_update():
                entity_select.set_options([(val, val) for val in values])
                if desired != SELECT_BLANK and desired in set(values):
                    entity_select.value = desired
            self._entity_options_key = key
        finally:
            # Loaded, failed or dropped: the Select must be usable again.
            entity_select.prompt = ENTITY_SELECT_PROMPT
            entity_select.disabled = False

    def _cancel_entity_load(self) -> None:
        """Abandon an in-flight entity load and leave the Select usable."""
        if self._entity_load_key is None:
            return
        self._entity_load_key = None
        self.workers.cancel_group(self, "entity_values")
        try:
            entity_select = self.query_one("#entity_name", Select)
        except NoMatches:
            return
        entity_select.prompt = ENTITY_SELECT_PROMPT
        entity_select.disabled = False

    @property
    def entity_values_loading(self) -> bool:
        """True while a background entity load has not been applied yet."""
        return self._entity_load_key is not None

    @property
    def entity_selection_pending(self) -> bool:
        """True while a chosen entity waits for its reload to be re-applied."""
        return self.entity_values_loading and self._pending_entity_value != SELECT_BLANK

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle select widget changes."""
        if getattr(self, "_exit", False):
            # A queued Changed message can land after exit() while the DOM is
            # being unmounted; reacting to it would query dead widgets.
            return
        if event.select.id == "entity_col":
            # Act on the widget's current value, not the message's: repopulating
            # the column options posts a transient BLANK Changed that is already
            # stale when handled, and must not cancel the load for the real value.
            current = event.select.value
            if current != SELECT_BLANK:
                self.load_unique_entities(current)
            else:
                self._cancel_entity_load()

        elif event.select.id == "share_metric":
            self.update_secondary_options("#share_secondary", exclude=[event.value])

        elif event.select.id == "rate_total":
            self.update_secondary_options("#rate_secondary", exclude=[event.value])

        elif event.select.id == "preset_select":
            if event.value != SELECT_BLANK:
                self._invalidate_stale_advanced_override(str(event.value))
                self.update_advanced_parameters(event.value)
                self._update_preset_blurb(str(event.value))
                if not getattr(self, "_tui_bootstrapping", False):
                    self._refresh_privacy_release_mode_from_config()
                self._refresh_run_status()
                if not self.query_one("#advanced_opt").collapsed:
                    self.notify(
                        f"Advanced values reloaded from the preset {event.value}.",
                        title="Advanced optimization",
                        severity="information",
                        timeout=4,
                        markup=False,
                    )

        elif event.select.id == "privacy_release_mode":
            if event.value != SELECT_BLANK and event.value is not None:
                self._apply_privacy_release_mode_coupling(str(event.value))

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Keep the status panel's mode line current; emit surface on real changes."""
        self._sync_privacy_release_mode_visibility()
        if not getattr(self, "_tui_bootstrapping", False):
            # Owner decision 6: the VSC sweep lock follows the active tab.
            self._apply_privacy_release_mode_coupling(
                self._privacy_release_mode_value_from_widget()
            )
        self._refresh_run_status()
        self._emit_surface_if_changed(self._analysis_mode())

    def on_collapsible_expanded(self, event: Collapsible.Expanded) -> None:
        """Record the advanced panel being opened (Ctrl+A, Ctrl+E or click)."""
        if event.collapsible.id == "advanced_opt":
            surface_viewed("advanced")

    def action_toggle_advanced(self) -> None:
        """Toggle the advanced optimization collapsible (Ctrl+A)."""
        collapsible = self.query_one("#advanced_opt")
        collapsible.collapsed = not collapsible.collapsed
        if not collapsible.collapsed:
            preset_val = self.query_one("#preset_select").value
            if preset_val and preset_val != SELECT_BLANK:
                self.update_advanced_parameters(preset_val)
            self.notify("Advanced optimization shown (F8 hides it)", title="Advanced optimization", severity="information", timeout=3)
        else:
            self.notify("Advanced optimization hidden (F8 shows it)", title="Advanced optimization", severity="information", timeout=3)

    def action_export_advanced(self) -> None:
        """Keyboard shortcut to export advanced overrides (Ctrl+E)."""
        # Ensure overrides exist
        if self.query_one("#advanced_opt").collapsed:
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
            self.notify(
                f"Advanced settings exported to {export_path}",
                title="Advanced settings exported",
                severity="information",
                timeout=6,
                markup=False,
            )
            advanced_override("exported")
        except Exception as e:
            advanced_override("export_failed")
            self.notify(
                f"Couldn't export the advanced settings. Why: {e}. "
                "Next: check that the folder is writable, then export again (F9).",
                title=status_text("error"),
                severity="error",
                timeout=6,
                markup=False,
            )

    # ──────────────────────────────────────────────────────────────────
    # Analysis execution
    # ──────────────────────────────────────────────────────────────────

    def _collect_run_inputs(self) -> RunInputs:
        """Read every form value a run attempt needs (UI thread only, D7)."""

        def select_value(widget_id: str) -> Any:
            value = self.query_one(f"#{widget_id}", Select).value
            return None if value == SELECT_BLANK else value

        def checked(widget_id: str, default: bool = False) -> bool:
            return bool(getattr(self.query_one(f"#{widget_id}"), "value", default))

        preset_value = select_value("preset_select")
        preset = str(preset_value) if preset_value is not None else None
        # D2: an override written for another preset is never sent with this one.
        self._invalidate_stale_advanced_override(preset)
        config = getattr(self, "advanced_config_path", None) or None
        posture = (
            self._effective_compliance_posture(preset, config)
            if (preset or config)
            else None
        )
        mode = self._analysis_mode()
        output_format = select_value("output_format") or "analysis"
        common: Dict[str, Any] = {
            "mode": mode,
            "csv_path": self.query_one("#csv_path", Input).value,
            "entity_selection_pending": self.entity_selection_pending,
            "entity": select_value("entity_name"),
            "entity_col": select_value("entity_col") or "issuer_name",
            "preset": preset,
            "config": config,
            "compliance_posture": posture,
            "output": self.query_one("#output_file", Input).value or None,
            "time_col": select_value("time_col"),
            "validate_input": checked("validate_input", True),
            "analyze_distortion": checked("analyze_distortion"),
            "compare_presets": checked("compare_presets"),
            "include_calculated": checked("include_calculated"),
            "output_format": str(output_format),
            "privacy_values": tuple(self._privacy_values_from_widgets().items()),
        }
        prefix = "share" if mode == "share" else "rate"
        per_mode: Dict[str, Any] = {
            "secondary_metrics": tuple(
                self.query_one(f"#{prefix}_secondary", SelectionList).selected
            ),
            "auto": checked(f"{prefix}_auto_dim"),
            "dimensions": tuple(self.query_one(f"#{prefix}_dims", SelectionList).selected),
            "debug": checked(f"{prefix}_debug"),
            "export_balanced_csv": checked(f"{prefix}_export_csv"),
        }
        if mode == "share":
            per_mode["metric"] = select_value("share_metric")
        else:
            per_mode["total_col"] = select_value("rate_total")
            per_mode["approved_col"] = select_value("rate_approved")
            per_mode["fraud_col"] = select_value("rate_fraud")
            per_mode["fraud_in_bps"] = checked("fraud_in_bps", True)
        return RunInputs(**common, **per_mode)

    def run_analysis(
        self,
        confirmed: bool = False,
        saved_request: AnalysisRunRequest | None = None,
        saved_df: pd.DataFrame | None = None,
    ) -> None:
        """Start a run attempt (UI thread) via the shared run seam.

        A fresh attempt snapshots the form into ``RunInputs`` here, before the
        worker starts (D7); the worker never reads a widget. A confirmed
        attempt (after the validation modal) reuses the request it built.
        """
        log_widget = self.query_one("#log_output", Log)
        if confirmed and saved_request is not None:
            self._run_confirmed_worker(saved_request, saved_df, log_widget)
            return
        if self.query_one("#btn_run", Button).disabled:
            return
        try:
            inputs = self._collect_run_inputs()
        except Exception as exc:
            launch_blocked(self._telemetry_action(), "initialization_error")
            log_widget.write(f"Run could not start: {exc}\n")
            self._end_run_ui(
                "error",
                _outcome_markup(labels.START_FAILED, why=str(exc), code=type(exc).__name__),
            )
            return
        self._cancel_event.clear()
        self._run_action = "share_analysis" if inputs.mode == "share" else "rate_analysis"
        log_widget.clear()
        started = datetime.now().strftime("%H:%M:%S")
        mode_text = labels.text_for(labels.ANALYSIS_MODE, inputs.mode)
        log_widget.write(f"Run started · {mode_text} · {started}\n")
        self._begin_validation_ui()
        self._launch_run_worker(inputs, log_widget)

    def request_cancel(self) -> None:
        """Ask the current run to stop at its next safe checkpoint.

        Before the engine starts, the worker stops before opening a dialog or
        calling the engine. Inside the engine, core stops at the next phase
        boundary and never once output writing has started, so a cancelled
        run writes nothing. A run already writing outputs finishes normally.
        Telemetry is recorded by whoever asks for the cancel (Quit records
        ``quit_during_run``/``quit_before_run``).
        """
        self._cancel_event.set()

    @property
    def cancel_requested(self) -> bool:
        return self._cancel_event.is_set()

    def _call_ui_if_running(self, callback: Any, *args: Any) -> None:
        """``call_from_thread`` that tolerates an app that has already exited."""
        try:
            self.call_from_thread(callback, *args)
        except RuntimeError:
            pass  # Quit already tore the app down; nothing left to update.

    def _stop_cancelled_launch(self, log_widget: Log) -> None:
        """End a run attempt cancelled before the engine started (worker thread)."""
        finalize_deferred_logging(
            logging.getLogger(),
            privacy_authorized=False,
        )
        write_log_message(log_widget, "Run cancelled before the engine started. Nothing was written.")
        self._call_ui_if_running(
            self._end_run_ui,
            "cancelled",
            _outcome_markup(labels.RUN_CANCELLED_BEFORE_START, code="RunCancelled"),
        )

    @work(thread=True, group="run_analysis")
    def _run_confirmed_worker(
        self,
        request: AnalysisRunRequest,
        saved_df: Any,
        log_widget: Log,
    ) -> None:
        """Execute a confirmed request in a background thread."""
        # Restart the run clock so the elapsed time reflects execution,
        # not how long a validation modal sat open.
        self.call_from_thread(self._begin_run_ui)
        self._execute_confirmed_analysis(request, saved_df, log_widget)

    @work(thread=True, group="run_analysis")
    def _launch_run_worker(self, inputs: RunInputs, log_widget: Log) -> None:
        """Preflight, prompts and input validation for one attempt (worker thread).

        Reads only ``inputs``; launch checks keep today's order and messages.
        """
        action = "share_analysis" if inputs.mode == "share" else "rate_analysis"
        try:
            if not inputs.csv_path:
                self._fail_launch(
                    "CSV path is required.", focus_id="csv_path", block_reason="csv_missing"
                )
                return
            if inputs.entity_selection_pending:
                # The operator's target entity is cleared while the values
                # reload and is re-applied when they land; launching now
                # would silently run peer-only instead.
                self._fail_launch(
                    "Target entity values are still loading; wait for the list to finish.",
                    focus_id="entity_name",
                    block_reason="entity_loading",
                )
                return

            values: Dict[str, Any] = {
                "csv": inputs.csv_path,
                "entity": inputs.entity,
                "entity_col": inputs.entity_col,
                "preset": inputs.preset,
                "config": inputs.config,
                "output": inputs.output,
                "time_col": inputs.time_col,
                "log_level": "INFO",
                "validate_input": inputs.validate_input,
                "analyze_distortion": inputs.analyze_distortion,
                "compare_presets": inputs.compare_presets,
                "include_calculated": inputs.include_calculated,
                "output_format": inputs.output_format,
                **dict(inputs.privacy_values),
            }
            posture = inputs.compliance_posture
            if inputs.preset and not inputs.config:
                # Unchanged: without an override the preset posture is sent.
                values["compliance_posture"] = posture
            # D2: consent follows the *effective* posture, including when an
            # override file sets it; core would otherwise block the run with
            # no way to consent.
            if posture == 'best_effort':
                write_log_message(log_widget, "WARNING: best_effort posture may complete with labeled non-compliant outputs.")
            if posture == 'accuracy_first':
                if self.cancel_requested:
                    self._stop_cancelled_launch(log_widget)
                    return
                if not self._confirm_accuracy_first_consent():
                    if self._confirmations_abandoned:
                        return  # App is quitting; the quit is already recorded.
                    if self.cancel_requested:
                        self._stop_cancelled_launch(log_widget)
                        return
                    action_cancelled(action, "accuracy_first_consent")
                    self._fail_launch(
                        "Run cancelled: consent was not given. Nothing was written.",
                        title_state="cancelled",
                    )
                    return
                values["acknowledge_accuracy_first"] = True

            if inputs.mode == "share":
                values["metric"] = inputs.metric
                if not values["metric"]:
                    self._fail_launch("Primary metric is required for share analysis.", focus_id="share_metric", block_reason="metric_missing")
                    return
            else:
                values["total_col"] = inputs.total_col
                if not values["total_col"]:
                    self._fail_launch("Total column is required for rate analysis.", focus_id="rate_total", block_reason="total_missing")
                    return
                values["approved_col"] = inputs.approved_col
                values["fraud_col"] = inputs.fraud_col
                if not values["approved_col"] and not values["fraud_col"]:
                    self._fail_launch("At least one rate column (approved or fraud) is required.", focus_id="rate_approved", block_reason="rate_column_missing")
                    return
            values["secondary_metrics"] = list(inputs.secondary_metrics) or None
            values["auto"] = inputs.auto
            if not inputs.auto and not inputs.dimensions:
                self._fail_launch(
                    "Select at least one dimension or enable auto-detect.",
                    focus_id=f"{'share' if inputs.mode == 'share' else 'rate'}_dims",
                    block_reason="dimensions_missing",
                )
                return
            values["dimensions"] = list(inputs.dimensions) if inputs.dimensions and not inputs.auto else None
            values["debug"] = inputs.debug
            values["export_balanced_csv"] = inputs.export_balanced_csv
            if inputs.mode == "share":
                # Share analysis uses one global weight vector. Maximum Safe
                # Coverage also requires global weights; keep this explicit.
                values["per_dimension_weights"] = False
                assert values["per_dimension_weights"] is False, (
                    "share analysis requires global weights "
                    "(per_dimension_weights must be False)"
                )
            else:
                values["fraud_in_bps"] = inputs.fraud_in_bps

            request = AnalysisRunRequest.from_widget_values(inputs.mode, values)
            if request.fraud_col:
                assert request.total_col is not None
                if self.cancel_requested:
                    self._stop_cancelled_launch(log_widget)
                    return
                if not self._confirm_clearing_spend_basis(request.total_col):
                    if self._confirmations_abandoned:
                        return  # App is quitting; the quit is already recorded.
                    if self.cancel_requested:
                        self._stop_cancelled_launch(log_widget)
                        return
                    action_cancelled("rate_analysis", "clearing_spend")
                    write_log_message(log_widget, "Analysis cancelled by user.")
                    self.call_from_thread(self._reset_run_ui)
                    return
                request._fraud_confirmation_source = "tui_modal"

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_dir = _resolve_log_dir()
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = str(
                log_dir / f"benchmark_log_{timestamp}.txt"
            )
            setup_deferred_logging(
                log_level="INFO",
                log_file=log_file,
                console_output=False,
            )

            logging.getLogger("benchmark").handlers.clear()
            logging.getLogger("core").handlers.clear()
            handler = LogHandler(log_widget)
            handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            logging.getLogger().addHandler(handler)

            df = None
            if request.validate_input and request.csv and os.path.exists(request.csv):
                write_log_message(log_widget, "Loading data for validation...")
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
                    if self.cancel_requested:
                        # Cancelled while the file was read: no dialog, no engine.
                        self._stop_cancelled_launch(log_widget)
                        return
                    if issues:
                        has_errors = any(issue.severity == ValidationSeverity.ERROR for issue in issues)

                        def on_modal_closed(result: bool) -> None:
                            # Runs on the app thread (screen-dismiss callback).
                            self._handle_validation_modal_result(
                                result,
                                has_errors=has_errors,
                                should_abort=should_abort,
                                request=request,
                                saved_df=df,
                                log_widget=log_widget,
                            )

                        # Timestamp for the time-in-review metric (G12).
                        surface_viewed("validation_review")
                        self.call_from_thread(self.push_screen, ValidationModal(issues), on_modal_closed)
                        return
                except Exception as exc:
                    launch_blocked(
                        "share_analysis" if request.is_share else "rate_analysis",
                        "data_preparation_error",
                    )
                    finalize_deferred_logging(
                        logging.getLogger(),
                        privacy_authorized=False,
                    )
                    write_log_message(log_widget, f"Data check failed: {exc}")
                    self.call_from_thread(
                        self.notify,
                        "The data check couldn't finish. Details are in Last run.",
                        title=status_text("error"),
                        severity="error",
                    )
                    self.call_from_thread(
                        self._end_run_ui,
                        "error",
                        _outcome_markup(labels.DATA_CHECK_FAILED, why=str(exc), code=type(exc).__name__),
                    )
                    return

            self.call_from_thread(self.run_analysis, True, request, df)
            return

        except Exception as exc:
            launch_blocked(action, "initialization_error")
            finalize_deferred_logging(
                logging.getLogger(),
                privacy_authorized=False,
            )
            write_log_message(log_widget, f"Run could not start: {exc}")
            self.call_from_thread(
                self._end_run_ui,
                "error",
                _outcome_markup(labels.START_FAILED, why=str(exc), code=type(exc).__name__),
            )
            return

    def _execute_confirmed_analysis(
        self,
        request: AnalysisRunRequest,
        saved_df: Any,
        log_widget: Log,
    ) -> None:
        """Run a confirmed analysis request and map outcomes to TUI UI only.

        Telemetry attempt/refuse/fail/complete events stay in shared
        ``core.analysis_run`` orchestration; this method must not emit them.
        """
        logger = logging.getLogger("benchmark")
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
            artifacts = self._execute_run_for_tui(request, logger, log_widget)
            privacy_decision = artifacts.privacy_output_decision
            hard_privacy_block = artifacts.privacy_sink_authorized is not True
            if hard_privacy_block:
                quarantine_path = finalize_deferred_logging(
                    logger,
                    privacy_authorized=False,
                )
                if (
                    (artifacts.metadata or {}).get("non_publishable_diagnostic")
                    and artifacts.analysis_output_file
                ):
                    self.call_from_thread(
                        log_widget.write,
                        "Control 3 privacy denial: publication withheld "
                        f"({privacy_decision.withholding_reason}). A consented "
                        "accuracy_first diagnostic report was written; it is "
                        "NON-PUBLISHABLE.\n",
                    )
                else:
                    self.call_from_thread(
                        log_widget.write,
                        "Control 3 privacy denial: all benchmark-bearing outputs "
                        f"withheld ({privacy_decision.withholding_reason}).\n",
                    )
                if quarantine_path:
                    self.call_from_thread(
                        log_widget.write,
                        "Internal run log (do not share):\n"
                        f"{quarantine_path}\n",
                    )
            else:
                log_file = finalize_deferred_logging(
                    logger,
                    privacy_authorized=artifacts.privacy_log_authorized,
                )
                if log_file:
                    self.call_from_thread(
                        log_widget.write,
                        f"Log file created: {log_file}\n",
                    )
                self.call_from_thread(
                    log_widget.write,
                    "Analysis completed successfully.\n",
                )
            summary = artifacts.compliance_summary or artifacts.metadata.get('compliance_summary', {})
            posture = summary.get('posture') or summary.get('compliance_posture')
            verdict = str(summary.get('compliance_verdict'))
            posture_text = labels.text_for(labels.POSTURE, posture) if posture else "—"
            consent_state = summary.get('acknowledgement_state')
            consent_text = labels.text_for(labels.CONSENT_STATE, consent_state) if consent_state else "—"
            self.call_from_thread(
                log_widget.write,
                f"Compliance: {posture_text} posture · verdict {verdict} · consent: {consent_text}\n",
            )
            for line in self._format_safe_coverage_summary_plain(artifacts):
                self.call_from_thread(log_widget.write, f"{line}\n")
            report_paths = [str(p) for p in (artifacts.report_paths or [artifacts.analysis_output_file]) if p]
            mode_text = labels.text_for(labels.ANALYSIS_MODE, request.mode)
            details = [
                _summary_field("Mode", f"{mode_text} · {_preset_display(request.preset or 'default')}"),
                _summary_field("Verdict", labels.text_for(labels.COMPLIANCE_VERDICT, verdict)),
                _summary_field("Posture", f"{posture_text} · Consent: {consent_text}"),
            ]
            for path in report_paths:
                details.append(_summary_field("Report", path))
            details.extend(self._format_safe_coverage_summary_markup(artifacts))
            if hard_privacy_block:
                reason = privacy_decision.withholding_reason
                diagnostic = bool(
                    (artifacts.metadata or {}).get("non_publishable_diagnostic")
                    and artifacts.analysis_output_file
                )
                headline = labels.label_for(labels.WITHHOLDING_REASON, reason)
                if diagnostic:
                    headline = labels.Label(
                        "Publication withheld. A consented diagnostic report was "
                        "written; it is NON-PUBLISHABLE (do not share).",
                        headline.why,
                    )
                elif headline.primary == labels.UNRECOGNISED:
                    headline = labels.Label("Results were withheld to protect peer privacy.")
                if (
                    request.privacy_release_mode
                    is PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE
                ):
                    details.append(_summary_field("Release", "Verified safe coverage"))
                details.append(_summary_field("Status", labels.text_for(labels.RUN_STATUS, "withheld")))
                if diagnostic:
                    details.append(
                        _summary_field(
                            "Non-publishable diagnostic report (do not share)",
                            str(artifacts.analysis_output_file),
                        )
                    )
                if artifacts.audit_log_output:
                    details.append(_summary_field("Non-publishable audit", str(artifacts.audit_log_output)))
                if quarantine_path:
                    details.append(_summary_field("Internal run log (do not share)", str(quarantine_path)))
                self.call_from_thread(
                    self._end_run_ui,
                    "blocked",
                    _outcome_markup(headline, details, code=f"{reason} · {verdict}"),
                    badge="withheld",
                )
                self.call_from_thread(
                    self.notify,
                    f"Publication withheld: {headline.primary} Details are in Last run.",
                    title=status_text("withheld"),
                    severity="error",
                    timeout=10,
                    markup=False,
                )
            else:
                verdict_state = labels.VERDICT_STATUS.get(verdict)
                if verdict_state not in ("compliant", "warning"):
                    verdict_state = None
                self.call_from_thread(
                    self._end_run_ui,
                    "success",
                    _outcome_markup(
                        labels.Label("The run finished and the report was written."),
                        details,
                        code=verdict,
                    ),
                    verdict=verdict_state,
                )
                self.call_from_thread(
                    self.notify,
                    f"Report saved: {report_paths[0] if report_paths else 'n/a'}",
                    title=status_text("success"),
                    severity="information",
                    timeout=10,
                    markup=False,
                )
        except RunCancelled:
            # Core stopped before output writing started: nothing was written.
            # The deferred log is finalised unauthorised; the canceller (Quit)
            # has already recorded action_cancelled.
            log_path = self._quarantine_run_logging(logger, log_widget)
            write_log_message(log_widget, "Run cancelled before any output was written.")
            self._call_ui_if_running(
                self._end_run_ui,
                "cancelled",
                _outcome_markup(labels.RUN_CANCELLED, _log_details(log_path), code="RunCancelled"),
            )
        except RunBlocked as exc:
            log_path = self._quarantine_run_logging(logger, log_widget)
            self.call_from_thread(log_widget.write, f"Run blocked: {exc}\n")
            label = labels.blocked_label(str(exc))
            self.call_from_thread(
                self._end_run_ui,
                "blocked",
                _outcome_markup(label, _log_details(log_path), why=str(exc), code="RunBlocked"),
            )
            self.call_from_thread(
                self.notify, label.primary, title=status_text("blocked"), severity="error", timeout=10, markup=False
            )
        except RunAborted as exc:
            log_path = self._quarantine_run_logging(logger, log_widget)
            self.call_from_thread(log_widget.write, f"Run failed: {exc}\n")
            label = labels.aborted_label(str(exc))
            self.call_from_thread(
                self._end_run_ui,
                "error",
                _outcome_markup(label, _log_details(log_path), why=str(exc), code="RunAborted"),
            )
            self.call_from_thread(
                self.notify, label.primary, title=status_text("error"), severity="error", timeout=10, markup=False
            )
        except Exception as exc:
            log_path = self._quarantine_run_logging(logger, log_widget)
            self.call_from_thread(log_widget.write, f"Run failed: {exc}\n")
            self.call_from_thread(log_widget.write, traceback.format_exc())
            label = labels.UNEXPECTED_ERROR
            self.call_from_thread(
                self._end_run_ui,
                "error",
                _outcome_markup(
                    label,
                    _log_details(log_path),
                    why=f"An unexpected error ({type(exc).__name__}) stopped the run. The input file was not changed.",
                    code=f"{type(exc).__name__}: {exc}",
                ),
            )

    def _quarantine_run_logging(
        self,
        logger: logging.Logger,
        log_widget: Log,
    ) -> Optional[str]:
        """Quarantine deferred diagnostics for a denied or failed run.

        Returns the quarantined log path (or None) so the outcome card can
        show it in full.
        """
        quarantine_path = finalize_deferred_logging(
            logger,
            privacy_authorized=False,
        )
        if quarantine_path:
            self._call_ui_if_running(
                log_widget.write,
                f"Internal run log (do not share):\n{quarantine_path}\n",
            )
        return str(quarantine_path) if quarantine_path else None


def _summary_field(name: str, value: str) -> str:
    """One ``Name  value`` line of the Last run card; the value is escaped."""
    return f"[$text-muted]{escape_markup(name)}[/]  {escape_markup(str(value))}"


def _log_details(log_path: Optional[str]) -> List[str]:
    if not log_path:
        return []
    return [_summary_field("Internal run log (do not share)", log_path)]


def _outcome_markup(
    label: "labels.Label",
    details: Iterable[str] = (),
    *,
    why: Optional[str] = None,
    code: Optional[str] = None,
) -> str:
    """Last run card body: what happened, why, what to do, details, code (02 §5.3).

    ``details`` lines are already-escaped markup (``_summary_field``); every
    other value here is escaped.
    """
    lines = [f"[b]{escape_markup(label.primary)}[/b]"]
    cause = why if why is not None else label.why
    if cause:
        lines.append(f"[$text-muted]Why[/]   {escape_markup(cause)}")
    if label.next:
        lines.append(f"[$text-muted]Next[/]  {escape_markup(label.next)}")
    lines.extend(details)
    if code:
        lines.append(f"[$text-muted i]Code: {escape_markup(code)}[/]")
    return "\n".join(lines)


if __name__ == "__main__":
    warn_if_personal_runtime()
    app = BenchmarkApp()
    app.run()
