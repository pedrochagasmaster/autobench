import os
import sys
import logging
import threading
import glob
import pandas as pd
from pathlib import Path
from types import SimpleNamespace
from typing import List

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
    ListItem
)
from textual.worker import Worker, WorkerState
from textual import work
from textual.logging import TextualHandler
from datetime import datetime

# Import core logic from benchmark.py
# We need to add the script directory to sys.path to ensure imports work
sys.path.append(str(Path(__file__).parent))
try:
    from benchmark import run_share_analysis, run_rate_analysis
    from utils.logger import setup_logging
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

class BenchmarkApp(App):
    """Privacy-Compliant Peer Benchmark Tool TUI"""

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

    .split-inputs Input {
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
    """

    TITLE = "Privacy-Compliant Peer Benchmark Tool"
    SUB_TITLE = "TUI Wrapper"

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        
        with Container(classes="main-container"):
            yield Label("Configuration", classes="section-title")
            
            # Common Inputs
            with Horizontal(classes="input-group"):
                yield Button("Select CSV", id="btn_browse_csv", variant="default")
                yield Input(placeholder="Path to CSV file (e.g., data/input.csv)", id="csv_path", classes="file-input")
            
            # File Browser (Hidden by default)
            yield ListView(id="file_list", classes="file-browser")

            with Horizontal(classes="input-group"):
                yield Select([], prompt="Select Entity Column", id="entity_col")
                yield Select([], prompt="Select Target Entity", id="entity_name")
            
            with Horizontal(classes="input-group"):
                yield Input(placeholder="Output Filename (Optional)", id="output_file")

            yield Select([], prompt="Select Preset", id="preset_select")

            # Mode Selection
            with TabbedContent(initial="share_tab"):
                # Share Analysis Tab
                with TabPane("Share Analysis", id="share_tab"):
                    yield Label("Metric Configuration")
                    yield Select([], prompt="Select Primary Metric", id="share_metric")
                    yield Input(placeholder="Secondary Metrics (space separated)", id="share_secondary")
                    
                    yield Label("Dimensions")
                    with Horizontal(classes="input-group"):
                        yield Checkbox("Auto-detect Dimensions", value=True, id="share_auto_dim")
                        yield Checkbox("Debug Mode", value=False, id="share_debug")
                        yield Checkbox("Export Balanced CSV", value=False, id="share_export_csv")
                    yield Input(placeholder="Specific Dimensions (space separated, if not auto)", id="share_dims", disabled=True)

                # Rate Analysis Tab
                with TabPane("Rate Analysis", id="rate_tab"):
                    yield Label("Column Configuration")
                    yield Select([], prompt="Select Total Column", id="rate_total")
                    with Horizontal(classes="split-inputs"):
                        yield Select([], prompt="Select Approved Column", id="rate_approved")
                        yield Select([], prompt="Select Fraud Column", id="rate_fraud")
                    
                    yield Input(placeholder="Secondary Metrics (space separated)", id="rate_secondary")

                    yield Label("Dimensions")
                    with Horizontal(classes="input-group"):
                        yield Checkbox("Auto-detect Dimensions", value=True, id="rate_auto_dim")
                        yield Checkbox("Debug Mode", value=False, id="rate_debug")
                        yield Checkbox("Export Balanced CSV", value=False, id="rate_export_csv")
                    yield Input(placeholder="Specific Dimensions (space separated, if not auto)", id="rate_dims", disabled=True)

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

    def populate_file_list(self):
        """Populate the file list with CSV files from current directory and data/."""
        # Scan for CSV files
        csv_files = glob.glob("*.csv") + glob.glob("data/*.csv")
        items = [FileListItem(f) for f in csv_files]
        self.query_one("#file_list").extend(items)

    def load_csv_headers(self, file_path):
        """Load CSV headers and populate Select widgets."""
        try:
            # Read only headers
            cols = pd.read_csv(file_path, nrows=0).columns.tolist()
            options = [(c, c) for c in cols]
            
            # Update Select widgets
            self.query_one("#entity_col").set_options(options)
            self.query_one("#share_metric").set_options(options)
            self.query_one("#rate_total").set_options(options)
            self.query_one("#rate_approved").set_options(options)
            self.query_one("#rate_fraud").set_options(options)
            
            # Try to set defaults if they exist
            if "issuer_name" in cols:
                self.query_one("#entity_col").value = "issuer_name"
            if "txn_cnt" in cols:
                self.query_one("#share_metric").value = "txn_cnt"
                self.query_one("#rate_total").value = "txn_cnt"
            if "app_cnt" in cols:
                self.query_one("#rate_approved").value = "app_cnt"
                
        except Exception as e:
            self.query_one("#log_output").write(f"Error reading CSV headers: {e}\n")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle file selection from the list."""
        if event.item and isinstance(event.item, FileListItem):
            file_path = event.item.file_path
            self.query_one("#csv_path").value = str(file_path)
            self.query_one("#file_list").remove_class("-visible")
            self.load_csv_headers(file_path)

    def load_presets(self):
        """Load available presets from the presets directory."""
        presets_dir = Path(__file__).parent / "presets"
        options = []
        if presets_dir.exists():
            for f in presets_dir.glob("*.yaml"):
                options.append((f.stem, f.stem))
        
        # Add 'standard' or 'default' if not present, or just rely on what's found
        if not options:
            options.append(("standard", "standard"))
            
        self.query_one("#preset_select").set_options(options)
        self.query_one("#preset_select").value = options[0][0] if options else None

    def setup_logging_capture(self):
        """Redirect logging to the TUI Log widget."""
        log_widget = self.query_one("#log_output")
        handler = LogHandler(log_widget)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        
        # Attach to root logger only (propagation will handle the rest)
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)
        
        # Clear specific loggers to prevent duplication if they have handlers
        logging.getLogger("benchmark").handlers.clear()
        logging.getLogger("core").handlers.clear()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn_browse_csv":
            file_list = self.query_one("#file_list")
            file_list.toggle_class("-visible")
            if "-visible" in file_list.classes:
                file_list.focus()
                
        elif event.button.id == "btn_run":
            self.run_analysis()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Handle checkbox toggles."""
        if event.checkbox.id == "share_auto_dim":
            self.query_one("#share_dims").disabled = event.value
        elif event.checkbox.id == "rate_auto_dim":
            self.query_one("#rate_dims").disabled = event.value

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

    @work(thread=True)
    def run_analysis(self) -> None:
        """Execute the analysis in a background thread."""
        log_widget = self.query_one("#log_output")
        self.call_from_thread(log_widget.clear)
        self.call_from_thread(log_widget.write, "Starting analysis...\n")
        
        # Disable button
        self.call_from_thread(lambda: setattr(self.query_one("#btn_run"), "disabled", True))

        try:
            # Setup file logging
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_file = f"benchmark_log_{timestamp}.txt"
            
            # Configure logging (clears existing handlers)
            setup_logging(log_level="INFO", log_file=log_file, console_output=False)
            
            # Clear specific loggers to prevent duplication
            logging.getLogger("benchmark").handlers.clear()
            logging.getLogger("core").handlers.clear()
            
            # Re-attach TUI log handler
            handler = LogHandler(log_widget)
            handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            logging.getLogger().addHandler(handler)
            
            self.call_from_thread(log_widget.write, f"Log file created: {log_file}\n")

            # Gather inputs
            csv_path = self.query_one("#csv_path").value
            
            entity_val = self.query_one("#entity_name").value
            entity = entity_val if entity_val != Select.BLANK else None
            
            entity_col_val = self.query_one("#entity_col").value
            entity_col = entity_col_val if entity_col_val != Select.BLANK else None
            
            preset_val = self.query_one("#preset_select").value
            preset = preset_val if preset_val != Select.BLANK else None
            
            if not csv_path:
                log_widget.write("ERROR: CSV path is required.")
                return

            # Determine active tab
            tabbed_content = self.query_one(TabbedContent)
            active_tab = tabbed_content.active

            # Construct arguments
            args = SimpleNamespace()
            args.csv = csv_path
            args.entity = entity if entity else None
            args.preset = preset
            args.config = None
            
            output_file = self.query_one("#output_file").value
            args.output = output_file if output_file else None
            
            args.entity_col = entity_col if entity_col else "issuer_name"
            args.time_col = None # Not exposed in simple UI yet
            args.log_level = "INFO"
            
            # Common logger
            logger = logging.getLogger("benchmark")

            if active_tab == "share_tab":
                self.call_from_thread(log_widget.write, "Mode: Share Analysis\n")
                
                metric_val = self.query_one("#share_metric").value
                args.metric = metric_val if metric_val != Select.BLANK else None
                
                if not args.metric:
                    self.call_from_thread(log_widget.write, "ERROR: Metric is required for Share Analysis.\n")
                    return
                
                sec_metrics = self.query_one("#share_secondary").value
                args.secondary_metrics = sec_metrics.split() if sec_metrics else None
                
                args.auto = self.query_one("#share_auto_dim").value
                dims = self.query_one("#share_dims").value
                args.dimensions = dims.split() if dims and not args.auto else None
                
                args.debug = self.query_one("#share_debug").value
                args.per_dimension_weights = False # Default
                args.export_balanced_csv = self.query_one("#share_export_csv").value
                
                # Run Share Analysis
                run_share_analysis(args, logger)

            elif active_tab == "rate_tab":
                self.call_from_thread(log_widget.write, "Mode: Rate Analysis\n")
                
                total_val = self.query_one("#rate_total").value
                args.total_col = total_val if total_val != Select.BLANK else None
                
                if not args.total_col:
                    self.call_from_thread(log_widget.write, "ERROR: Total Column is required for Rate Analysis.\n")
                    return
                
                approved_val = self.query_one("#rate_approved").value
                approved = approved_val if approved_val != Select.BLANK else None
                
                fraud_val = self.query_one("#rate_fraud").value
                fraud = fraud_val if fraud_val != Select.BLANK else None
                
                args.approved_col = approved if approved else None
                args.fraud_col = fraud if fraud else None
                
                if not args.approved_col and not args.fraud_col:
                    self.call_from_thread(log_widget.write, "ERROR: At least one of Approved Col or Fraud Col is required.\n")
                    return

                sec_metrics = self.query_one("#rate_secondary").value
                args.secondary_metrics = sec_metrics.split() if sec_metrics else None

                args.auto = self.query_one("#rate_auto_dim").value
                dims = self.query_one("#rate_dims").value
                args.dimensions = dims.split() if dims and not args.auto else None
                
                args.debug = self.query_one("#rate_debug").value
                args.export_balanced_csv = self.query_one("#rate_export_csv").value
                
                # Run Rate Analysis
                run_rate_analysis(args, logger)

            self.call_from_thread(log_widget.write, "Analysis completed successfully.\n")

        except Exception as e:
            self.call_from_thread(log_widget.write, f"CRITICAL ERROR: {str(e)}\n")
            import traceback
            self.call_from_thread(log_widget.write, traceback.format_exc())
        
        finally:
            # Re-enable button
            self.call_from_thread(lambda: setattr(self.query_one("#btn_run"), "disabled", False))

if __name__ == "__main__":
    app = BenchmarkApp()
    app.run()
