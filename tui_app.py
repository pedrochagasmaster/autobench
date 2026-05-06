import os
import sys
import logging
import threading
import glob
import pandas as pd
from pathlib import Path
from typing import List
import yaml

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
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
    Collapsible
)
from textual.worker import Worker, WorkerState
from textual import work
from textual.logging import TextualHandler
from datetime import datetime
from textual.screen import ModalScreen

# Import shared run orchestration and adapter dependencies.
sys.path.append(str(Path(__file__).parent))
try:
    from core.analysis_run import (
        RunAborted,
        RunBlocked,
        build_run_config,
        execute_run,
        prepare_run_data,
        resolve_dimensions,
        validate_analysis_input,
    )
    from core.contracts import AnalysisRunRequest
    from core.preset_workflow import PresetWorkflow
    from utils.logger import setup_logging
    from core.data_loader import ValidationIssue, ValidationSeverity
except ImportError as e:
    # Fallback for when running in a different context or if imports fail
    print(f"Error importing benchmark modules: {e}")
    sys.exit(1)

class LogHandler(logging.Handler):
    """Custom logging handler to send logs to a Textual Log widget."""
    def __init__(self, log_widget: Log):
        super().__init__()
        self.log_widget = log_widget

    def emit(self, record):
        msg = self.format(record)
        # Schedule the write on the main thread
        self.log_widget.app.call_from_thread(self.log_widget.write, msg + "\n")

class FileListItem(ListItem):
    """Custom ListItem that stores the file path."""
    def __init__(self, file_path: str) -> None:
        super().__init__(Label(file_path))
        self.file_path = file_path

class PresetHelpScreen(ModalScreen):
    """Screen to show preset help."""
    
    CSS = """
    PresetHelpScreen {
        align: center middle;
        background: rgba(0,0,0,0.7);
    }
    
    #help_container {
        width: 60%;
        height: 80%;
        border: thick $primary;
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

class ValidationModal(ModalScreen):
    """Modal to display validation issues and allow proceed/cancel."""
    
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
            self.dismiss(True) # Return True to proceed
        elif event.button.id == "btn_cancel":
            self.dismiss(False) # Return False to cancel

class BenchmarkApp(App):
    """Privacy-Compliant Peer Benchmark Tool TUI"""

    BINDINGS = [
        ("ctrl+o", "open_file", "Open CSV"),
        ("ctrl+r", "run_analysis", "Run"),
        ("f1", "show_help", "Help"),
        ("escape", "close_browser", "Close"),
        ("ctrl+a", "toggle_advanced", "Advanced"),
        ("ctrl+e", "export_advanced", "Export Adv"),
    ]

    CSS = """
    Screen {
        align: center middle;
    }

    .main-container {
        width: 90%;
        height: 95%;
        border: solid green;
        padding: 1 2;
        overflow-y: auto;
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
        margin-bottom: 1;
    }

    .field-pair {
        height: auto;
        margin-bottom: 1;
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

    #btn_run {
        width: 100%;
        margin-top: 2;
        margin-bottom: 1;
    }

    Log {
        height: 20;
        min-height: 10;
        border: solid gray;
        background: $surface;
        margin-top: 1;
    }
    
    .file-browser {
        height: 20;
        border: solid blue;
        display: none;
    }
    
    .file-browser.-visible {
        display: block;
    }

    .multi-select {
        height: 8;
        border: solid gray;
        margin-bottom: 1;
    }

    .hidden {
        display: none;
    }

    #btn_preset_help {
        min-width: 10;
    }

    /* Advanced Optimization Section */
    #advanced_opt {
        border: solid $accent;
        padding: 1 1;
        margin-top: 1;
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

    /* Textual CSS does not support fractional spacing; use whole numbers */
    #advanced_form Input, #advanced_form Checkbox {
        margin-bottom: 1;
    }

    #advanced_form Button {
        margin-bottom: 0;
    }

    /* flex-wrap not supported in textual; rely on vertical containers for narrow terminals */
    /* Validation Modal */
    #validation_container {
        width: 80%;
        height: 70%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    
    #validation_title {
        text-style: bold;
        margin-bottom: 1;
        text-align: center;
    }
    
    #issue_list {
        height: 1fr;
        border: solid $secondary;
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
    
    .rate-only {
        display: none;
    }
    
    BenchmarkApp.rate-mode .rate-only {
        display: block;
    }
    """

    TITLE = "Privacy-Compliant Peer Benchmark Tool"
    SUB_TITLE = "TUI Wrapper"

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        
        with Container(classes="main-container"):
            # ═══════════════════════════════════════════════════════════════
            # DATA SOURCE
            # ═══════════════════════════════════════════════════════════════
            yield Label("Data Source", classes="section-title")
            yield Label("CSV File Path", classes="field-label")
            with Horizontal(classes="input-group"):
                yield Button("Browse...", id="btn_browse_csv", variant="default")
                yield Input(id="csv_path", classes="file-input")
            
            # File Browser (Hidden by default)
            yield ListView(id="file_list", classes="file-browser")

            # ═══════════════════════════════════════════════════════════════
            # ENTITY CONFIGURATION
            # ═══════════════════════════════════════════════════════════════
            yield Label("Entity Configuration", classes="section-title")
            with Horizontal(classes="input-group"):
                with Vertical(classes="field-pair"):
                    yield Label("Entity ID Column", classes="field-label")
                    yield Select([], prompt="Select column...", id="entity_col")
                with Vertical(classes="field-pair"):
                    yield Label("Target Entity (blank = peer-only)", classes="field-label")
                    yield Select([], prompt="Select entity...", id="entity_name", allow_blank=True)
            
            # ═══════════════════════════════════════════════════════════════
            # ANALYSIS OPTIONS
            # ═══════════════════════════════════════════════════════════════
            yield Label("Analysis Options", classes="section-title")
            with Horizontal(classes="input-group"):
                with Vertical(classes="field-pair"):
                    yield Label("Time Period Column (optional)", classes="field-label")
                    yield Select([], prompt="Select column...", id="time_col", allow_blank=True)
                with Vertical(classes="field-pair"):
                    yield Label("Output Filename", classes="field-label")
                    yield Input(placeholder="Auto-generated if blank", id="output_file")

            with Vertical(classes="field-pair"):
                yield Label("Optimization Preset", classes="field-label")
                with Horizontal(classes="input-group"):
                    yield Select([], prompt="Select preset...", id="preset_select")
                    yield Button("Preset Guide", id="btn_preset_help", variant="default")
            
            # ═══════════════════════════════════════════════════════════════
            # ADVANCED ANALYSIS FEATURES
            # ═══════════════════════════════════════════════════════════════
            yield Label("Advanced Analysis Features", classes="section-title")
            with Horizontal(classes="input-group"):
                yield Checkbox("Analyze impact", value=True, id="analyze_distortion")
                yield Checkbox("Compare presets", id="compare_presets")
            
            with Horizontal(classes="input-group"):
                yield Checkbox("Validate input", id="validate_input", value=True)
                # yield Checkbox("Include calculated metrics in CSV", id="include_calculated") 
                # ^ moved to per-tab or careful global? Let's use global for now.
                yield Checkbox("Include calc. metrics (CSV)", id="include_calculated")
                yield Checkbox("Acknowledge accuracy-first", id="acknowledge_accuracy_first")

            with Horizontal(classes="input-group"):
                with Vertical(classes="field-pair"):
                    yield Label("Output Format", classes="field-label")
                    yield Select([("Analysis", "analysis"), ("Publication", "publication"), ("Both", "both")], id="output_format", value="analysis", allow_blank=False)

            # ═══════════════════════════════════════════════════════════════
            # ADVANCED OPTIMIZATION (collapsed by default)
            # ═══════════════════════════════════════════════════════════════
            with Collapsible(title="Advanced Optimization Parameters", id="advanced_opt", collapsed=True):
                with Vertical(id="advanced_form"):
                    # ───────────────────────────────────────────
                    # LINEAR PROGRAMMING
                    # ───────────────────────────────────────────
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

                    # ───────────────────────────────────────────
                    # CONSTRAINTS
                    # ───────────────────────────────────────────
                    yield Label("Constraints", classes="adv-group-title")
                    with Horizontal(classes="input-group"):
                        with Vertical(classes="field-pair"):
                            yield Label("Volume Preservation", classes="adv-field-label")
                            yield Input(placeholder="0.0 - 1.0", id="adv_constraints_volume_preservation")

                    # ───────────────────────────────────────────
                    # BOUNDS
                    # ───────────────────────────────────────────
                    yield Label("Weight Bounds", classes="adv-group-title")
                    with Horizontal(classes="input-group"):
                        with Vertical(classes="field-pair"):
                            yield Label("Min Weight", classes="adv-field-label")
                            yield Input(placeholder="e.g., 0.01", id="adv_bounds_min_weight")
                        with Vertical(classes="field-pair"):
                            yield Label("Max Weight", classes="adv-field-label")
                            yield Input(placeholder="e.g., 10.0", id="adv_bounds_max_weight")

                    # ───────────────────────────────────────────
                    # SUBSET SEARCH
                    # ───────────────────────────────────────────
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

                    # ───────────────────────────────────────────
                    # BAYESIAN FALLBACK
                    # ───────────────────────────────────────────
                    yield Label("Bayesian Optimization (Fallback)", classes="adv-group-title")
                    with Horizontal(classes="input-group"):
                        with Vertical(classes="field-pair"):
                            yield Label("Max Iterations", classes="adv-field-label")
                            yield Input(placeholder="e.g., 100", id="adv_bayes_max_iterations")
                        with Vertical(classes="field-pair"):
                            yield Label("Learning Rate", classes="adv-field-label")
                            yield Input(placeholder="e.g., 0.01", id="adv_bayes_learning_rate")

                    # ───────────────────────────────────────────
                    # ANALYSIS SETTINGS
                    # ───────────────────────────────────────────
                    yield Label("Analysis Settings", classes="adv-group-title")
                    with Horizontal(classes="input-group"):
                        with Vertical(classes="field-pair"):
                            yield Label("Best-in-Class Percentile", classes="adv-field-label")
                            yield Input(placeholder="0.0 - 1.0 (e.g., 0.85)", id="adv_analysis_bic_percentile")

                    # ───────────────────────────────────────────
                    # OUTPUT SETTINGS
                    # ───────────────────────────────────────────
                    yield Label("Output Settings", classes="adv-group-title")
                    with Horizontal(classes="input-group"):
                        yield Checkbox("Include Debug Sheets", id="adv_output_debug_sheets")
                        yield Checkbox("Include Privacy Validation", id="adv_output_privacy_validation")

                    # ───────────────────────────────────────────
                    # ACTIONS
                    # ───────────────────────────────────────────
                    with Horizontal(classes="input-group"):
                        yield Button("Apply Overrides", id="btn_apply_advanced", variant="primary")
                        yield Button("Export Config", id="btn_export_advanced", variant="default")
                    yield Label("Values override preset when applied.", classes="subsection-title")

            # ═══════════════════════════════════════════════════════════════
            # ANALYSIS MODE TABS
            # ═══════════════════════════════════════════════════════════════
            with TabbedContent(initial="share_tab"):
                # ───────────────────────────────────────────
                # SHARE ANALYSIS TAB
                # ───────────────────────────────────────────
                with TabPane("Share Analysis", id="share_tab"):
                    with Vertical(classes="field-pair"):
                        yield Label("Primary Metric Column", classes="field-label")
                        yield Select([], prompt="Select column...", id="share_metric")
                    
                    with Vertical(classes="field-pair"):
                        yield Label("Secondary Metrics (Optional)", classes="field-label")
                        yield SelectionList(id="share_secondary", classes="multi-select")
                    
                    yield Label("Dimension Options", classes="subsection-title")
                    with Horizontal(classes="input-group"):
                        yield Checkbox("Auto-detect Dimensions", value=False, id="share_auto_dim")
                        yield Checkbox("Include Debug Sheets", value=True, id="share_debug")
                        yield Checkbox("Export Balanced CSV", value=True, id="share_export_csv")
                    
                    yield Label("Manual Dimension Selection", id="share_dims_label", classes="hidden")
                    yield SelectionList(id="share_dims", classes="multi-select hidden")

                # ───────────────────────────────────────────
                # RATE ANALYSIS TAB
                # ───────────────────────────────────────────
                with TabPane("Rate Analysis", id="rate_tab"):
                    with Vertical(classes="field-pair"):
                        yield Label("Total Column (denominator)", classes="field-label")
                        yield Select([], prompt="Select column...", id="rate_total")
                    with Horizontal(classes="split-inputs"):
                        with Vertical(classes="field-pair"):
                            yield Label("Approved Column", classes="field-label")
                            yield Select([], prompt="Select column...", id="rate_approved", allow_blank=True)
                        with Vertical(classes="field-pair"):
                            yield Label("Fraud Column", classes="field-label")
                            yield Select([], prompt="Select column...", id="rate_fraud", allow_blank=True)
                    
                    with Vertical(classes="field-pair"):
                        yield Label("Secondary Metrics (Optional)", classes="field-label")
                        yield SelectionList(id="rate_secondary", classes="multi-select")

                    yield Label("Dimension Options", classes="subsection-title")
                    with Horizontal(classes="input-group"):
                        yield Checkbox("Auto-detect Dimensions", value=False, id="rate_auto_dim")
                        yield Checkbox("Include Debug Sheets", value=True, id="rate_debug")
                        yield Checkbox("Export Balanced CSV", value=False, id="rate_export_csv")
                        yield Checkbox("Fraud in BPS", value=True, id="fraud_in_bps")
                    
                    yield Label("Manual Dimension Selection", id="rate_dims_label", classes="hidden")
                    yield SelectionList(id="rate_dims", classes="multi-select hidden")

            # Action
            yield Button("Run Analysis", id="btn_run", variant="primary")
            
            # Output
            yield Label("Execution Log", classes="section-title")
            yield Log(id="log_output", highlight=True)

        yield Footer()

    def on_mount(self) -> None:
        """Event handler called when widget is added to the app."""
        self.load_presets()
        self.setup_logging_capture()
        self.populate_file_list()
        
        # Set initial focus
        self.query_one("#csv_path").focus()
        # Quick guidance notify
        self.notify("Ctrl+A: toggle advanced | Ctrl+E: export overrides", title="Shortcuts", severity="information", timeout=5)

    def populate_file_list(self):
        """Populate the file list with CSV files from current directory and data/."""
        # Scan for CSV files
        csv_files = glob.glob("*.csv") + glob.glob("data/*.csv")
        items = [FileListItem(f) for f in csv_files]
        file_list = self.query_one("#file_list")
        file_list.clear()
        file_list.extend(items)

    def load_csv_headers(self, file_path):
        """Load CSV headers and populate Select widgets."""
        try:
            # Read only headers
            cols = pd.read_csv(file_path, nrows=0).columns.tolist()
            self.csv_columns = cols
            options = [(c, c) for c in cols]
            selection_options = [(c, c) for c in cols]
            
            # Update Select widgets
            self.query_one("#entity_col").set_options(options)
            self.query_one("#time_col").set_options(options)
            self.query_one("#share_metric").set_options(options)
            self.query_one("#rate_total").set_options(options)
            self.query_one("#rate_approved").set_options(options)
            self.query_one("#rate_fraud").set_options(options)
            
            # Update SelectionLists
            for list_id in ["#share_secondary", "#share_dims", "#rate_secondary", "#rate_dims"]:
                s_list = self.query_one(list_id, SelectionList)
                s_list.clear_options()
                s_list.add_options(selection_options)
            
            # Try to set defaults if they exist
            if "issuer_name" in cols:
                self.query_one("#entity_col").value = "issuer_name"
            if "txn_cnt" in cols:
                self.query_one("#share_metric").value = "txn_cnt"
                self.query_one("#rate_total").value = "txn_cnt"
            if "app_cnt" in cols:
                self.query_one("#rate_approved").value = "app_cnt"
            
            # Notify user
            self.notify(f"Loaded {len(cols)} columns from CSV", title="CSV Loaded", severity="information", timeout=5)
                
        except Exception as e:
            self.query_one("#log_output").write(f"Error reading CSV headers: {e}\n")
            self.notify(f"Failed to read CSV: {e}", title="CSV Error", severity="error")

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

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle file selection from the list."""
        if event.item and isinstance(event.item, FileListItem):
            file_path = event.item.file_path
            self.query_one("#csv_path").value = str(file_path)
            self.query_one("#file_list").remove_class("-visible")
            self.load_csv_headers(file_path)

    def load_presets(self):
        """Load available presets through the shared preset workflow."""
        self.preset_workflow = PresetWorkflow()
        presets = self.preset_workflow.list_presets()
        options = [(preset, preset) for preset in presets] or [("standard", "standard")]
        self.query_one("#preset_select").set_options(options)
        self.query_one("#preset_select").value = options[0][0] if options else None
        if options:
            self.update_advanced_parameters(options[0][0])
        self.advanced_config_path = None

    def update_advanced_parameters(self, preset_name: str) -> None:
        """Populate editable advanced optimization inputs from preset YAML."""
        if not hasattr(self, 'preset_workflow'):
            self.preset_workflow = PresetWorkflow()

        for inp in self.query("Input"):
            if inp.id and inp.id.startswith("adv_"):
                inp.value = ""
        for cb in self.query("Checkbox"):
            if cb.id and cb.id.startswith("adv_"):
                cb.value = False

        data = self.preset_workflow.load_preset_data(preset_name)
        if not data:
            return

        opt = data.get("optimization", {})
        lp = opt.get("linear_programming", {})
        bounds = opt.get("bounds", {})
        subset = opt.get("subset_search", {})
        constraints = opt.get("constraints", {})
        bayes = opt.get("bayesian", {})
        analysis = data.get("analysis", {})
        output = data.get("output", {})
        
        # Helper to safely set Input value
        def safe_set_input(field_id, value):
            try:
                self.query_one(f"#{field_id}", Input).value = str(value)
            except Exception:
                pass
        
        # Helper to safely set Checkbox value
        def safe_set_checkbox(field_id, value):
            try:
                self.query_one(f"#{field_id}", Checkbox).value = bool(value)
            except Exception:
                pass

        # LINEAR PROGRAMMING
        if "tolerance" in lp:
            safe_set_input("adv_lp_tolerance", lp["tolerance"])
        if "max_iterations" in lp:
            safe_set_input("adv_lp_max_iterations", lp["max_iterations"])
        if "lambda_penalty" in lp:
            safe_set_input("adv_lp_lambda_penalty", lp["lambda_penalty"])
        if "volume_weighting_exponent" in lp:
            safe_set_input("adv_lp_volume_weighting_exponent", lp["volume_weighting_exponent"])
        if "volume_weighted_penalties" in lp:
            safe_set_checkbox("adv_lp_volume_weighted_penalties", lp["volume_weighted_penalties"])
        
        # CONSTRAINTS
        if "volume_preservation" in constraints:
            safe_set_input("adv_constraints_volume_preservation", constraints["volume_preservation"])
        
        # BOUNDS
        if "min_weight" in bounds:
            safe_set_input("adv_bounds_min_weight", bounds["min_weight"])
        if "max_weight" in bounds:
            safe_set_input("adv_bounds_max_weight", bounds["max_weight"])
        
        # SUBSET SEARCH
        if subset.get("enabled") is not None:
            safe_set_checkbox("adv_subset_enabled", subset["enabled"])
        if subset.get("strategy"):
            safe_set_input("adv_subset_strategy", subset["strategy"])
        # max_attempts or max_tests (alias)
        max_att = subset.get("max_attempts") or subset.get("max_tests")
        if max_att is not None:
            safe_set_input("adv_subset_max_attempts", max_att)
        if subset.get("max_slack_threshold") is not None:
            safe_set_input("adv_subset_max_slack_threshold", subset["max_slack_threshold"])
        if subset.get("trigger_on_slack") is not None:
            safe_set_checkbox("adv_subset_trigger_on_slack", subset["trigger_on_slack"])
        if subset.get("prefer_slacks_first") is not None:
            safe_set_checkbox("adv_subset_prefer_slacks_first", subset["prefer_slacks_first"])
        
        # BAYESIAN
        if "max_iterations" in bayes:
            safe_set_input("adv_bayes_max_iterations", bayes["max_iterations"])
        if "learning_rate" in bayes:
            safe_set_input("adv_bayes_learning_rate", bayes["learning_rate"])
        
        # ANALYSIS
        if "best_in_class_percentile" in analysis:
            safe_set_input("adv_analysis_bic_percentile", analysis["best_in_class_percentile"])
        
        # OUTPUT
        if "include_debug_sheets" in output:
            safe_set_checkbox("adv_output_debug_sheets", output["include_debug_sheets"])
        if "include_privacy_validation" in output:
            safe_set_checkbox("adv_output_privacy_validation", output["include_privacy_validation"])

    def setup_logging_capture(self):
        """Redirect logging to the TUI Log widget."""
        log_widget = self.query_one("#log_output")
        handler = LogHandler(log_widget)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        
        # Attach to root logger only (propagation will handle the rest)
        root_logger = logging.getLogger()
        for existing_handler in list(root_logger.handlers):
            if isinstance(existing_handler, LogHandler):
                root_logger.removeHandler(existing_handler)
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)
        
        # Clear specific loggers to prevent duplication if they have handlers
        logging.getLogger("benchmark").handlers.clear()
        logging.getLogger("core").handlers.clear()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn_browse_csv":
            self.action_open_file()
                
        elif event.button.id == "btn_run":
            self.run_analysis()
            
        elif event.button.id == "btn_preset_help":
            self.push_screen(PresetHelpScreen())
            
        elif event.button.id == "btn_help_presets":
            self.push_screen(PresetHelpScreen())
        elif event.button.id == "btn_apply_advanced":
            self.apply_advanced_overrides()
        elif event.button.id == "btn_export_advanced":
            self.export_advanced_overrides()

    def action_open_file(self) -> None:
        """Open file browser (Ctrl+O)."""
        file_list = self.query_one("#file_list")
        file_list.add_class("-visible")
        file_list.focus()

    def action_run_analysis(self) -> None:
        """Run analysis (Ctrl+R)."""
        self.run_analysis()

    def _current_mode(self) -> str:
        active = str(self.query_one(TabbedContent).active)
        return "share" if active == "share_tab" else "rate"

    def action_show_help(self) -> None:
        """Show preset help (F1)."""
        self.push_screen(PresetHelpScreen())

    def action_close_browser(self) -> None:
        """Close file browser (Escape)."""
        file_list = self.query_one("#file_list")
        if "-visible" in file_list.classes:
            file_list.remove_class("-visible")
            self.query_one("#csv_path").focus()

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
            # Use pandas to read just that column
            df = pd.read_csv(csv_path, usecols=[column_name])
            unique_vals = sorted(df[column_name].dropna().unique().astype(str).tolist())
            
            options = [(val, val) for val in unique_vals]
            self.query_one("#entity_name").set_options(options)
            
        except Exception as e:
            self.query_one("#log_output").write(f"Error loading entities: {e}\n")

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle select widget changes."""
        if event.select.id == "entity_col":
            if event.value != Select.BLANK:
                self.load_unique_entities(event.value)
        
        elif event.select.id == "share_metric":
             self.update_secondary_options("#share_secondary", exclude=[event.value])
             
        elif event.select.id == "rate_total":
             self.update_secondary_options("#rate_secondary", exclude=[event.value])

        elif event.select.id == "preset_select":
            if event.value != Select.BLANK:
                self.update_advanced_parameters(event.value)
                if not self.query_one("#advanced_opt").collapsed:
                    self.notify(f"Preset '{event.value}' parameters refreshed", title="Advanced Optimization", severity="information", timeout=4)

    def action_toggle_advanced(self) -> None:
        """Toggle the advanced optimization collapsible (Ctrl+A)."""
        collapsible = self.query_one("#advanced_opt")
        collapsible.collapsed = not collapsible.collapsed
        if not collapsible.collapsed:
            preset_val = self.query_one("#preset_select").value
            if preset_val and preset_val != Select.BLANK:
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
            if preset_val and preset_val != Select.BLANK:
                self.update_advanced_parameters(preset_val)
        # Apply then export
        self.apply_advanced_overrides()
        self.export_advanced_overrides()

    def apply_advanced_overrides(self) -> None:
        """Generate a temporary YAML config file from advanced inputs and set path for analysis."""
        
        def get_input(fid):
            try:
                return self.query_one(f"#{fid}", Input).value.strip()
            except Exception:
                return ""
        
        def try_number(v):
            if v == "":
                return None
            try:
                return float(v) if '.' in v else int(v)
            except ValueError:
                return v
        
        def get_bool(cid):
            try:
                return self.query_one(f"#{cid}", Checkbox).value
            except Exception:
                return False

        # LINEAR PROGRAMMING
        lp = {}
        val = try_number(get_input("adv_lp_tolerance"))
        if val is not None:
            lp["tolerance"] = val
        val = try_number(get_input("adv_lp_max_iterations"))
        if val is not None:
            lp["max_iterations"] = val
        val = try_number(get_input("adv_lp_lambda_penalty"))
        if val is not None:
            lp["lambda_penalty"] = val
        val = try_number(get_input("adv_lp_volume_weighting_exponent"))
        if val is not None:
            lp["volume_weighting_exponent"] = val
        lp["volume_weighted_penalties"] = get_bool("adv_lp_volume_weighted_penalties")

        # CONSTRAINTS
        constraints = {}
        val = try_number(get_input("adv_constraints_volume_preservation"))
        if val is not None:
            constraints["volume_preservation"] = val

        # BOUNDS
        bounds = {}
        val = try_number(get_input("adv_bounds_min_weight"))
        if val is not None:
            bounds["min_weight"] = val
        val = try_number(get_input("adv_bounds_max_weight"))
        if val is not None:
            bounds["max_weight"] = val

        # SUBSET SEARCH
        subset = {}
        subset["enabled"] = get_bool("adv_subset_enabled")
        val = get_input("adv_subset_strategy")
        if val:
            subset["strategy"] = val
        val = try_number(get_input("adv_subset_max_attempts"))
        if val is not None:
            subset["max_attempts"] = val
        val = try_number(get_input("adv_subset_max_slack_threshold"))
        if val is not None:
            subset["max_slack_threshold"] = val
        subset["trigger_on_slack"] = get_bool("adv_subset_trigger_on_slack")
        subset["prefer_slacks_first"] = get_bool("adv_subset_prefer_slacks_first")

        # BAYESIAN
        bayesian = {}
        val = try_number(get_input("adv_bayes_max_iterations"))
        if val is not None:
            bayesian["max_iterations"] = val
        val = try_number(get_input("adv_bayes_learning_rate"))
        if val is not None:
            bayesian["learning_rate"] = val

        # ANALYSIS
        analysis = {}
        val = try_number(get_input("adv_analysis_bic_percentile"))
        if val is not None:
            analysis["best_in_class_percentile"] = val

        # OUTPUT
        output = {}
        output["include_debug_sheets"] = get_bool("adv_output_debug_sheets")
        output["include_privacy_validation"] = get_bool("adv_output_privacy_validation")

        # Build config
        optimization = {}
        if lp:
            optimization["linear_programming"] = lp
        if constraints:
            optimization["constraints"] = constraints
        if bounds:
            optimization["bounds"] = bounds
        if subset:
            optimization["subset_search"] = subset
        if bayesian:
            optimization["bayesian"] = bayesian

        yaml_data = {"version": "tui-override"}
        if optimization:
            yaml_data["optimization"] = optimization
        if analysis:
            yaml_data["analysis"] = analysis
        if output:
            yaml_data["output"] = output

        if len(yaml_data) == 1:  # only version key
            self.notify("No advanced values provided", title="Advanced Overrides", severity="warning", timeout=4)
            return

        try:
            if not hasattr(self, 'preset_workflow'):
                self.preset_workflow = PresetWorkflow()
            tmp_path = self.preset_workflow.write_override_file(yaml_data)
            self.advanced_config_path = str(tmp_path)
            self.notify(f"Advanced overrides applied (file: {tmp_path.name})", title="Advanced Overrides", severity="information", timeout=6)
        except Exception as e:
            self.notify(f"Failed to write overrides: {e}", title="Advanced Overrides", severity="error", timeout=6)

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

    @work(thread=True)
    def run_analysis(self, confirmed: bool = False, saved_request: AnalysisRunRequest | None = None, saved_df: pd.DataFrame | None = None) -> None:
        """Execute the analysis in a background thread via the shared run seam."""
        log_widget = self.query_one("#log_output")

        if not confirmed and not saved_request:
            if hasattr(self.query_one("#btn_run"), "disabled") and self.query_one("#btn_run").disabled:
                return

            self.call_from_thread(log_widget.clear)
            self.call_from_thread(log_widget.write, "Starting analysis sequence...\n")
            self.call_from_thread(self.query_one(".main-container").scroll_end, animate=True)
            self.call_from_thread(lambda: setattr(self.query_one("#btn_run"), "disabled", True))

            try:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                log_file = f"benchmark_log_{timestamp}.txt"
                setup_logging(log_level="INFO", log_file=log_file, console_output=False)

                logging.getLogger("benchmark").handlers.clear()
                logging.getLogger("core").handlers.clear()
                handler = LogHandler(log_widget)
                handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
                logging.getLogger().addHandler(handler)
                self.call_from_thread(log_widget.write, f"Log file created: {log_file}\n")

                csv_path = self.query_one("#csv_path").value
                if not csv_path:
                    self.call_from_thread(log_widget.write, "ERROR: CSV path is required.\n")
                    self.call_from_thread(self.notify, "CSV path is required", severity="error")
                    self.call_from_thread(lambda: setattr(self.query_one("#btn_run"), "disabled", False))
                    return

                entity_val = self.query_one("#entity_name").value
                entity = entity_val if entity_val != Select.BLANK else None
                entity_col_val = self.query_one("#entity_col").value
                entity_col = entity_col_val if entity_col_val != Select.BLANK else "issuer_name"
                if entity_col == "issuer_name" and self.current_file:
                    headers = list(pd.read_csv(self.current_file, nrows=0).columns)
                    normalized_headers = [h.lower().replace(" ", "_") for h in headers]
                    if "issuer_name" not in normalized_headers:
                        self.call_from_thread(self.notify, "Select the entity column before running.", severity="error")
                        self.call_from_thread(lambda: setattr(self.query_one("#btn_run"), "disabled", False))
                        return
                preset_val = self.query_one("#preset_select").value
                preset = preset_val if preset_val != Select.BLANK else None
                output_file = self.query_one("#output_file").value or None
                time_col_val = self.query_one("#time_col").value
                time_col = time_col_val if time_col_val != Select.BLANK else None

                mode = self._current_mode()

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
                            self.call_from_thread(log_widget.write, "ERROR: accuracy_first posture requires acknowledgement.\n")
                            self.call_from_thread(self.notify, "Check acknowledgement before running accuracy_first.", severity="error")
                            self.call_from_thread(lambda: setattr(self.query_one("#btn_run"), "disabled", False))
                            return

                if request.is_share:
                    metric_val = self.query_one("#share_metric").value
                    request.metric = metric_val if metric_val != Select.BLANK else None
                    if not request.metric:
                        self.call_from_thread(self.notify, "Metric is required", severity="error")
                        self.call_from_thread(lambda: setattr(self.query_one("#btn_run"), "disabled", False))
                        return
                    sec_metrics = self.query_one("#share_secondary", SelectionList).selected
                    request.secondary_metrics = list(sec_metrics) if sec_metrics else None
                    request.auto = self.query_one("#share_auto_dim").value
                    dims = self.query_one("#share_dims", SelectionList).selected
                    request.dimensions = list(dims) if dims and not request.auto else None
                    request.debug = self.query_one("#share_debug").value
                    request.export_balanced_csv = self.query_one("#share_export_csv").value
                    request.per_dimension_weights = False
                else:
                    total_val = self.query_one("#rate_total").value
                    request.total_col = total_val if total_val != Select.BLANK else None
                    if not request.total_col:
                        self.call_from_thread(self.notify, "Total Column is required", severity="error")
                        self.call_from_thread(lambda: setattr(self.query_one("#btn_run"), "disabled", False))
                        return
                    approved = self.query_one("#rate_approved").value
                    request.approved_col = approved if approved != Select.BLANK else None
                    fraud = self.query_one("#rate_fraud").value
                    request.fraud_col = fraud if fraud != Select.BLANK else None
                    if not request.approved_col and not request.fraud_col:
                        self.call_from_thread(self.notify, "At least one rate column is required", severity="error")
                        self.call_from_thread(lambda: setattr(self.query_one("#btn_run"), "disabled", False))
                        return
                    sec_metrics = self.query_one("#rate_secondary", SelectionList).selected
                    request.secondary_metrics = list(sec_metrics) if sec_metrics else None
                    request.auto = self.query_one("#rate_auto_dim").value
                    dims = self.query_one("#rate_dims", SelectionList).selected
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
                        if issues:
                            has_errors = any(issue.severity == ValidationSeverity.ERROR for issue in issues)

                            def on_modal_closed(result: bool) -> None:
                                if result and not has_errors and not should_abort:
                                    self.run_analysis(confirmed=True, saved_request=request, saved_df=df)
                                    return
                                self.call_from_thread(log_widget.write, "Analysis cancelled by user.\n")
                                self.call_from_thread(lambda: setattr(self.query_one("#btn_run"), "disabled", False))

                            self.call_from_thread(self.push_screen, ValidationModal(issues), on_modal_closed)
                            return
                    except Exception as exc:
                        self.call_from_thread(log_widget.write, f"Validation error: {exc}\n")
                        self.call_from_thread(self.notify, "Validation failed. Fix the data and retry.", severity="error")
                        self.call_from_thread(lambda: setattr(self.query_one("#btn_run"), "disabled", False))
                        return

                self.call_from_thread(self.run_analysis, True, request, df)
                return

            except Exception as exc:
                self.call_from_thread(log_widget.write, f"Initialization Error: {exc}\n")
                self.call_from_thread(lambda: setattr(self.query_one("#btn_run"), "disabled", False))
                return

        if confirmed and saved_request:
            request = saved_request
            logger = logging.getLogger("benchmark")
            try:
                request.df = saved_df
                artifacts = execute_run(request, logger)
                self.call_from_thread(log_widget.write, "Analysis completed successfully.\n")
                summary = artifacts.compliance_summary or artifacts.metadata.get('compliance_summary', {})
                self.call_from_thread(
                    log_widget.write,
                    f"Compliance: posture={summary.get('compliance_posture')} verdict={summary.get('compliance_verdict')} acknowledgement={summary.get('acknowledgement_state')}\n",
                )
                report_label = ", ".join(artifacts.report_paths or [artifacts.analysis_output_file or ""])
                self.call_from_thread(
                    self.notify,
                    f"Report saved: {report_label}",
                    title="Analysis Complete",
                    severity="information",
                    timeout=10,
                )
            except RunBlocked as exc:
                self.call_from_thread(log_widget.write, f"Execution Blocked: {exc}\n")
                self.call_from_thread(self.notify, str(exc), title="Blocked", severity="error", timeout=10)
            except RunAborted as exc:
                self.call_from_thread(log_widget.write, f"Execution Error: {exc}\n")
                self.call_from_thread(self.notify, str(exc), title="Failed", severity="error", timeout=10)
            except Exception as exc:
                self.call_from_thread(log_widget.write, f"Execution Error: {exc}\n")
                import traceback
                self.call_from_thread(log_widget.write, traceback.format_exc())
            finally:
                self.call_from_thread(lambda: setattr(self.query_one("#btn_run"), "disabled", False))


if __name__ == "__main__":
    app = BenchmarkApp()
    app.run()
