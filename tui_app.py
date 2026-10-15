"""Privacy-Compliant Peer Benchmark Tool — Textual TUI.

Layout shell (TUI redesign 01 §3): a non-gated step rail (Data, Entity,
Analysis & mode, Privacy & compliance, Review & run), one step body at a time,
a status/results column at 110+ columns (a Ctrl+T view below that), and an
action bar that always shows readiness and the run key.
All analysis execution flows through the shared ``core.analysis_run`` seam,
so behaviour stays identical to the CLI.
"""

import asyncio
import os
import sys
import time
import logging
import threading
import traceback
import glob
import contextlib
import collections
import copy
from functools import partial
import gc
import importlib
import io
import pandas as pd
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Mapping, NamedTuple, Optional, Tuple
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
from textual.content import Content
from textual.geometry import Region
from textual.markup import escape as escape_markup
from textual.widgets import (
    Header,
    Input,
    Button,
    Select,
    Checkbox,
    Label,
    Log,
    Static,
    ListView,
    ListItem,
    OptionList,
    SelectionList,
    Markdown,
    Collapsible,
    Tabs,
)
from textual.dom import DOMNode
from textual.widgets._collapsible import CollapsibleTitle
from textual.widgets._select import SelectCurrent, SelectOverlay
from textual.widgets._toast import ToastRack
from textual.widgets.option_list import Option
from datetime import datetime
from textual import events, work
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.worker import get_current_worker
from rich.text import Text

# Import shared run orchestration and adapter dependencies.
sys.path.append(str(Path(__file__).parent))
try:
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
    from tui.actionbar import ActionBar
    from tui.commands import AutobenchCommands
    from tui.expert import (
        ExpertScreen,
        diff_with,
        effective_values,
        expert_changes_text,
        rebase_diff,
    )
    from tui.form_state import (
        COLUMN_FIELDS,
        COLUMN_LIST_FIELDS,
        FIELD_STEPS,
        MORE_OPTIONS_FIELDS,
        FormState,
        SMART_DEFAULTS,
        read_session,
        session_payload,
    )
    from tui.form_widgets import (
        ENTITY_FILTER_PLACEHOLDER,
        ENTITY_LOADING_PROMPT,
        ENTITY_MATCH_LIMIT,
        ENTITY_SELECT_MAX,
        ENTITY_SELECT_PROMPT,
        SEPARATOR,
        ColumnSelect,
        Disclosure,
        EntityChooser,
        EntityIndex,
        EntitySuggester,
        ModeSwitch,
        SafeSelect,
    )
    from tui.keybar import KeyBar
    from tui.rail import ATTENTION, DONE, PENDING, RESTORED, STEP_BY_ID, STEPS, StepRail
    from tui.readiness import LaunchBlocker, launch_blockers
    from tui.steps import (
        BUILDERS,
        FIELD_WIDGETS,
        MORE_OPTIONS_WIDGETS,
        OUTPUT_FORMAT_CODES,
        PAIR_LABELS,
        RELEASE_MODE_HINTS,
        MODE_FIELD_WIDGETS,
        WIDGET_FIELDS,
        build_mode_fields,
        build_more_options,
        WIDGET_STEPS,
        StepContext,
        dimension_selections,
        more_options_title,
        secondary_selections,
    )
    from tui.status import glyph as status_glyph, status_text
    from tui.styles import AUTOBENCH_TCSS
    from tui.widgets import BoxCheckbox, BoxSelectionList, StatusBadge
except ImportError as e:
    # Fallback for when running in a different context or if imports fail
    print(f"Error importing benchmark modules: {e}")
    sys.exit(1)

# ``core.analysis_run`` pulls in the whole engine (scipy.stats through
# core.privacy_coverage_solver, about 0.8 s), and the TUI needs none of it
# until a run starts. It is imported on first use instead, and pre-warmed on a
# thread worker after the first paint (``BenchmarkApp._prewarm_analysis_run``).
_ANALYSIS_RUN: Any = None
_ANALYSIS_RUN_LOCK = threading.Lock()


def _analysis_run() -> Any:
    """Return ``core.analysis_run``, importing it on first use (thread-safe).

    Deliberate deferred import, allow-listed in
    ``tests/telemetry/test_no_inline_imports.py``. The lock makes a run that
    starts while the pre-warm import is still in progress wait for it, so the
    module is never imported twice.
    """
    global _ANALYSIS_RUN
    with _ANALYSIS_RUN_LOCK:
        if _ANALYSIS_RUN is None:
            _ANALYSIS_RUN = importlib.import_module("core.analysis_run")
    return _ANALYSIS_RUN


_GC_FROZEN = False


def _prewarm_engine() -> None:
    """Pre-warm worker body: import the engine, then ``gc.freeze()`` once.

    The import leaves ~1M long-lived objects (pandas, scipy, the engine) in
    the collected generations, so every later gen-2 collection walks them:
    65-220 ms UI stalls that landed at random in the CSV-load, entity and key
    windows (PR 6, measured with gc.callbacks). Freezing moves what exists now
    to the permanent generation. Once per process: a later freeze would also
    pin whatever garbage a previous app session left behind.
    """
    global _GC_FROZEN
    _analysis_run()
    if not _GC_FROZEN:
        _GC_FROZEN = True
        gc.freeze()


# Thin module-level wrappers keep ``tui_app.prepare_run_data`` and friends as
# patchable attributes (tests monkeypatch them) without importing the engine.
def build_run_config(*args: Any, **kwargs: Any) -> Any:
    return _analysis_run().build_run_config(*args, **kwargs)


def prepare_run_data(*args: Any, **kwargs: Any) -> Any:
    return _analysis_run().prepare_run_data(*args, **kwargs)


def resolve_dimensions(*args: Any, **kwargs: Any) -> Any:
    return _analysis_run().resolve_dimensions(*args, **kwargs)


def validate_analysis_input(*args: Any, **kwargs: Any) -> Any:
    return _analysis_run().validate_analysis_input(*args, **kwargs)


def execute_run(*args: Any, **kwargs: Any) -> Any:
    return _analysis_run().execute_run(*args, **kwargs)


def __getattr__(name: str) -> Any:
    # ``tui_app.RunBlocked`` / ``RunAborted`` / ``RunCancelled`` keep
    # resolving (PEP 562) without importing the engine at module load.
    if name in ("RunBlocked", "RunAborted", "RunCancelled"):
        return getattr(_analysis_run(), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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


# Entity widgets (tui.form_widgets) re-exported for callers and tests:
# EntityIndex, EntitySuggester, ENTITY_SELECT_MAX, ENTITY_MATCH_LIMIT and the
# prompts. Above ENTITY_SELECT_MAX values the filter picker replaces the
# Select (03 §6).
__all_entity__ = (
    EntityIndex,
    EntitySuggester,
    ENTITY_SELECT_MAX,
    ENTITY_MATCH_LIMIT,
    ENTITY_SELECT_PROMPT,
    ENTITY_LOADING_PROMPT,
    ENTITY_FILTER_PLACEHOLDER,
)

# Header rows plus a sample: enough to tell numeric columns (Metric and Total
# list them first) without reading the file on the UI thread.
NUMERIC_SAMPLE_ROWS = 500
# After a CSV load, steps 2 and 3 mount in the background (one per tick,
# this long after the load) so their first show is a display toggle.
STEP_PREWARM_DELAY_S = 0.25
STEP_PREWARM_ORDER = ("entity", "analysis")
# Textual parses a widget class's DEFAULT_CSS, and rebuilds the rules map, the
# first time an instance mounts. Steps 2-5 introduce these classes; their CSS
# is registered once in an idle tick after startup so the background step
# mounts after a CSV load do not pay for it (PR 6: background-mount stall).
STEP_CSS_PRELOAD_DELAY_S = 0.05

# Toasts (01 §5.3): top right, 40 columns; they move to the bottom when the
# focused field is in this top-right area.
TOAST_WIDTH = 40
TOAST_AREA_ROWS = 14

# Fields whose role decides what the dimensions and secondary lists offer.
ROLE_FIELDS = frozenset({"entity_col", "time_col", "metric", "total_col", "approved_col", "fraud_col"})
# Restored values marked ↺ even when they equal the default (owner decision 3).
ALWAYS_MARK_RESTORED = frozenset({"mode", "preset", "release_mode"})
# Plain names for the Review "Restored"/"Not restored" lines.
FIELD_LABELS = {
    "mode": "mode",
    "entity_col": "entity column",
    "metric": "metric",
    "total_col": "total",
    "approved_col": "approved",
    "fraud_col": "fraud",
    "time_col": "time column",
    "dimensions": "dimensions",
    "secondary": "secondary metrics",
    "auto_dims": "auto-detect",
    "preset": "preset",
    "release_mode": "release mode",
    "rule_sweep": "rule sweep",
    "output_format": "output format",
    "validate_input": "input validation",
    "analyze_distortion": "impact analysis",
    "compare_presets": "preset comparison",
    "export_balanced_csv": "balanced CSV",
    "include_calculated": "calculated metrics",
    "fraud_in_bps": "fraud in bps",
    "debug": "debug sheets",
}


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


def _elapsed_since(start: float) -> float:
    """Seconds since a ``time.monotonic()`` mark, as the run status shows them (patchable in snapshots)."""
    return time.monotonic() - start


def _launch_folder() -> str:
    """The working directory relative paths resolve from (patchable in snapshots)."""
    return os.getcwd()


def _full_path(path: str) -> str:
    """Absolute form of a user path, as the run log shows it (patchable in snapshots)."""
    return os.path.abspath(path)


def _log_view_formatter() -> logging.Formatter:
    """Short ``HH:MM:SS LEVEL message`` lines for the run log view (03 T8).

    The full record, with the date, stays in the deferred log file on disk.
    """
    return logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")


class LogHandler(logging.Handler):
    """Logging handler that batches records into a Textual Log widget.

    Records go into a bounded, thread-safe buffer. The first record after a
    drain posts one wake (``Log.call_later``, which is thread-safe and never
    waits for the UI). Each wake writes at most ``CHUNK_LINES`` pending lines
    in one ``Log.write`` on the UI thread and, if more are waiting, re-arms
    itself with a short timer, so a burst is spread over several event-loop
    turns instead of one long write that stalls input. (A re-posted message
    would not do: Textual processes a pump's queued messages back to back,
    so the chunks would still form one long stall.) An emitting worker therefore never blocks on the
    UI, and if the UI stalls the buffer keeps only the newest ``max_pending``
    lines plus a count of the ones it dropped. The full record is the
    deferred log file on disk, not this view.
    """

    MAX_PENDING = 2000  # matches the Log widget's max_lines
    # One Log.write of 500 lines stays well under 50 ms on the reference VM
    # (scripts/tui_perf_probe.py log phase); 2,000 lines in one write did not.
    CHUNK_LINES = 500
    # Gap between chunks: lets keys, timers and paints run in between.
    CHUNK_DELAY_S = 0.005

    def __init__(self, log_widget: Log, max_pending: int = MAX_PENDING, chunk_lines: int = CHUNK_LINES):
        super().__init__()
        self.log_widget = log_widget
        self._pending: "collections.deque[str]" = collections.deque(maxlen=max_pending)
        self._dropped = 0
        self._chunk_lines = max(1, int(chunk_lines))
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
        self._post_wake()

    def _post_wake(self) -> None:
        try:
            posted = bool(self.log_widget.call_later(self._flush))
        except Exception:
            posted = False
        if not posted:
            # App is shutting down; the next record may try again.
            with self._buffer_lock:
                self._wake_posted = False

    def _flush(self) -> None:
        """Write one chunk of the buffer (app thread only); re-arm if more wait."""
        with self._buffer_lock:
            take = min(self._chunk_lines, len(self._pending))
            pending = [self._pending.popleft() for _ in range(take)]
            dropped, self._dropped = self._dropped, 0
            more = bool(self._pending)
            # Still "posted" while lines remain: emitters must not post a
            # second wake; this drain posts the next one itself.
            self._wake_posted = more
        if dropped:
            pending.insert(
                0, f"… {dropped} earlier log lines not shown (full log on disk)\n"
            )
        if pending:
            self.log_widget.write("".join(pending))
        if more:
            try:
                self.log_widget.set_timer(self.CHUNK_DELAY_S, self._flush)
            except Exception:
                # Widget is gone (app closing): the next record may try again.
                with self._buffer_lock:
                    self._wake_posted = False


PRESETS_DIR = Path(__file__).resolve().parent / "presets"


def _preset_dir_signature(preset_dir: Path) -> tuple:
    """Cheap fingerprint of the preset files: one ``scandir`` plus a stat each.

    Any added, removed or edited ``*.yaml``/``*.yml`` file changes it, so a
    cached parse is never served for presets that changed on disk.
    """
    try:
        entries = []
        with os.scandir(preset_dir) as scan:
            for entry in scan:
                if entry.name.endswith((".yaml", ".yml")):
                    stat = entry.stat()
                    entries.append((entry.name, stat.st_mtime_ns, stat.st_size))
        return tuple(sorted(entries))
    except OSError:
        return ()


def _file_signature(path: Optional[str]) -> Optional[tuple]:
    """(path, mtime_ns, size) of a config file, or None when unset/missing."""
    if not path:
        return None
    try:
        stat = os.stat(path)
    except OSError:
        return (path, None, None)
    return (path, stat.st_mtime_ns, stat.st_size)


class PresetCatalog:
    """Parse the preset directory once, for display purposes only.

    The TUI used to parse every preset file four times at startup and again on
    every Advanced expand (each ``ConfigManager`` builds its own
    ``PresetManager``). The catalog keeps one ``PresetWorkflow`` and a memo of
    resolved preset configs, both invalidated when a preset file changes.

    Display only: the run path still builds a fresh ``ConfigManager`` inside
    ``build_run_config``, exactly like the CLI, so what runs never comes from
    this cache.
    """

    def __init__(self, preset_dir: Path = PRESETS_DIR) -> None:
        self._preset_dir = preset_dir
        self._signature: Optional[tuple] = None
        self._workflow: Optional[PresetWorkflow] = None
        self._resolved: Dict[str, Dict[str, Any]] = {}
        self._release_modes: Dict[tuple, str] = {}

    def _revalidate(self) -> None:
        signature = _preset_dir_signature(self._preset_dir)
        if self._workflow is None or signature != self._signature:
            self._workflow = PresetWorkflow()
            self._signature = signature
            self._resolved.clear()
            self._release_modes.clear()

    @property
    def workflow(self) -> PresetWorkflow:
        self._revalidate()
        assert self._workflow is not None
        return self._workflow

    def resolved_config(self, preset: str) -> Dict[str, Any]:
        """``ConfigManager(preset=preset).config``, memoised; callers get a copy."""
        self._revalidate()
        if preset not in self._resolved:
            self._resolved[preset] = ConfigManager(preset=preset).config
        return copy.deepcopy(self._resolved[preset])

    def resolved_release_mode(self, preset: Optional[str], config_file: Optional[str]) -> str:
        """Effective ``privacy_release_mode`` value for (preset, override file)."""
        self._revalidate()
        key = (preset, _file_signature(config_file))
        if key not in self._release_modes:
            resolved = ConfigManager(config_file=config_file, preset=preset).resolve()
            self._release_modes[key] = resolved.privacy_release_mode.value
        return self._release_modes[key]


QUICK_PICK_PATTERNS = ("*.csv", "data/*.csv", "tests/fixtures/*.csv")
# Quick picks shown at once; the filter box reaches the rest (03 §4).
QUICK_PICK_LIMIT = 50


def _is_browsable_entry(name: str, is_dir: bool) -> bool:
    """The picker's file filter: directories and ``*.csv``, no hidden entries."""
    if name.startswith(".") or name == "__pycache__":
        return False
    return is_dir or name.lower().endswith(".csv")


def scan_csv_directory(directory: str) -> List[tuple]:
    """List one directory for the CSV picker as ``(name, is_dir)`` pairs.

    Runs on a thread worker: one ``os.scandir`` and no widget access.
    ``DirEntry.is_dir()`` follows symlinks like the old ``Path.is_dir()``
    filter, but needs no extra ``stat`` for regular entries (it uses
    ``d_type``). Directories come first, then files, each sorted
    case-insensitively, as ``DirectoryTree`` ordered them.
    """
    entries: List[tuple] = []
    with os.scandir(directory) as scan:
        for entry in scan:
            try:
                is_dir = entry.is_dir()
            except OSError:
                continue
            if _is_browsable_entry(entry.name, is_dir):
                entries.append((entry.name, is_dir))
    entries.sort(key=lambda item: (not item[1], item[0].lower()))
    return entries


class CsvPickerScreen(ModalScreen[Optional[str]]):
    """Modal CSV picker: capped quick picks plus a flat, per-directory browser.

    Both lists are ``OptionList``s, which render only the visible lines, so a
    folder with thousands of CSVs costs a handful of widgets instead of one
    widget per file. The directory listing runs on a thread worker. Enter
    picks a file or opens a directory (``..`` goes up); Escape cancels.

    With ``quick_pick_source`` the quick picks (a glob plus one ``stat`` per
    file) are also gathered on a thread worker, so Ctrl+O opens at once even
    while another thread holds the GIL (PR 6: the engine pre-warm import made
    those stats queue behind it, up to 0.4 s before the picker appeared).
    """

    BINDINGS = [("escape", "cancel_picker", "Cancel")]

    def __init__(
        self,
        quick_picks: Optional[List[str]] = None,
        *,
        quick_pick_source: Optional[Callable[[], List[str]]] = None,
    ) -> None:
        super().__init__()
        self.quick_picks = list(quick_picks or [])
        self._quick_pick_source = quick_pick_source
        self._quick_loaded = quick_pick_source is None
        # Set by the first key: a late quick-pick list never steals focus.
        self._operator_moved = False
        self._browse_dir: Optional[str] = None
        self._browse_entries: List[tuple] = []

    def compose(self) -> ComposeResult:
        with Container(id="picker_container", classes="ab-modal"):
            yield Label("Open a CSV file", id="picker_title")
            yield Input(placeholder="Filter by name…", id="picker_filter", compact=True)
            with Horizontal(id="picker_body"):
                with Vertical(id="picker_quick"):
                    yield Label("Quick picks", id="picker_quick_title", classes="picker-subtitle")
                    yield OptionList(id="picker_quick_list", classes="ab-list")
                with Vertical(id="picker_tree_pane"):
                    yield Label("Browse workspace", id="picker_browse_title", classes="picker-subtitle")
                    yield OptionList(id="picker_browse_list", classes="ab-list")
            yield Label(
                "Enter opens the file · Esc cancels",
                classes="picker-hint",
            )
            yield Button("Cancel", id="btn_picker_cancel", variant="default", compact=True)
        yield KeyBar("picker")

    def on_mount(self) -> None:
        self._refresh_quick_picks()
        # Browse starts in the caller's working directory, never a fixed root.
        self._browse(os.getcwd())
        if self._quick_pick_source is not None:
            self._quick_worker(self._quick_pick_source)
        quick = self.query_one("#picker_quick_list", OptionList)
        (quick if quick.option_count else self.query_one("#picker_browse_list", OptionList)).focus()

    def on_key(self, event: events.Key) -> None:
        self._operator_moved = True

    @work(thread=True, exclusive=True, group="picker_quick", exit_on_error=False)
    def _quick_worker(self, source: Callable[[], List[str]]) -> None:
        worker = get_current_worker()
        try:
            picks = list(source())
        except OSError:
            picks = []
        if worker.is_cancelled:
            return
        try:
            self.app.call_from_thread(self._apply_quick_picks, picks)
        except RuntimeError:
            pass  # App already gone.

    def _apply_quick_picks(self, picks: List[str]) -> None:
        if not self.is_mounted:
            return
        self.quick_picks = picks
        self._quick_loaded = True
        self._refresh_quick_picks()
        quick = self.query_one("#picker_quick_list", OptionList)
        browse = self.query_one("#picker_browse_list", OptionList)
        # As when the list was ready at open: start on the quick picks, unless
        # the operator has already pressed a key.
        if quick.option_count and not self._operator_moved and self.focused in (None, browse):
            quick.focus()

    def _filter_text(self) -> str:
        try:
            return self.query_one("#picker_filter", Input).value.strip().casefold()
        except NoMatches:
            return ""

    def _refresh_quick_picks(self) -> None:
        needle = self._filter_text()
        matches = [path for path in self.quick_picks if needle in path.casefold()] if needle else self.quick_picks
        shown = matches[:QUICK_PICK_LIMIT]
        quick = self.query_one("#picker_quick_list", OptionList)
        quick.set_options(Option(Text(path), id=path) for path in shown)
        # Like the old ListView: Enter right away picks the first entry.
        quick.highlighted = 0 if shown else None
        title = "Quick picks" if self._quick_loaded else "Quick picks · finding files…"
        if len(matches) > len(shown):
            title = f"Quick picks ({len(shown)} of {len(matches):,})"
        self.query_one("#picker_quick_title", Label).update(title)

    def _browse(self, directory: str) -> None:
        self._browse_dir = directory
        self.query_one("#picker_browse_title", Label).update(Text(f"Browse {directory}"))
        self._scan_worker(directory)

    @work(thread=True, exclusive=True, group="picker_browse", exit_on_error=False)
    def _scan_worker(self, directory: str) -> None:
        worker = get_current_worker()
        try:
            entries = scan_csv_directory(directory)
        except OSError:
            entries = []
        if worker.is_cancelled:
            return
        try:
            self.app.call_from_thread(self._apply_browse, directory, entries)
        except RuntimeError:
            pass  # App already gone.

    def _apply_browse(self, directory: str, entries: List[tuple]) -> None:
        if directory != self._browse_dir or not self.is_mounted:
            return  # A newer directory request owns the list.
        self._browse_entries = entries
        self._render_browse()

    def _render_browse(self) -> None:
        directory = self._browse_dir
        if directory is None:
            return
        needle = self._filter_text()
        options: List[Option] = []
        parent = os.path.dirname(os.path.abspath(directory))
        if parent and parent != os.path.abspath(directory):
            options.append(Option(Text(".."), id=f"d:{parent}"))
        for name, is_dir in self._browse_entries:
            if needle and needle not in name.casefold():
                continue
            path = os.path.join(directory, name)
            if is_dir:
                options.append(Option(Text(f"▸ {name}/"), id=f"d:{path}"))
            else:
                options.append(Option(Text(name), id=f"f:{path}"))
        browse = self.query_one("#picker_browse_list", OptionList)
        browse.set_options(options)
        browse.highlighted = 0 if options else None

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "picker_filter":
            event.stop()
            self._refresh_quick_picks()
            self._render_browse()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "picker_filter":
            event.stop()
            for list_id in ("#picker_quick_list", "#picker_browse_list"):
                option_list = self.query_one(list_id, OptionList)
                if option_list.option_count:
                    option_list.focus()
                    break

    def on_input_blurred(self, event: Input.Blurred) -> None:
        # The app reloads the CSV when #csv_path blurs; keep the filter's
        # blur from reaching that handler.
        event.stop()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        option_id = event.option.id or ""
        if event.option_list.id == "picker_quick_list":
            self.dismiss(option_id)
        elif option_id.startswith("f:"):
            self.dismiss(option_id[2:])
        elif option_id.startswith("d:"):
            self.query_one("#picker_filter", Input).value = ""
            self._browse(option_id[2:])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_picker_cancel":
            self.dismiss(None)

    def action_cancel_picker(self) -> None:
        self.dismiss(None)


class ConfirmScreen(ModalScreen[bool]):
    """Small yes/no confirmation dialog."""

    BINDINGS = [("escape", "cancel_confirm", "Cancel")]

    def __init__(
        self,
        message: str,
        confirm_label: str = "Confirm",
        *,
        cancel_label: str = "Cancel",
        variant: str = "error",
    ) -> None:
        super().__init__()
        self.message = message
        self.confirm_label = confirm_label
        self.cancel_label = cancel_label
        self.variant = variant

    def compose(self) -> ComposeResult:
        with Container(id="confirm_container", classes="ab-modal"):
            # Literal text: messages can carry column names from the CSV.
            yield Label(Text(self.message), id="confirm_message")
            with Horizontal(id="confirm_buttons"):
                yield Button(self.confirm_label, id="btn_confirm_yes", variant=self.variant, compact=True)
                yield Button(self.cancel_label, id="btn_confirm_no", variant="default", compact=True)
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
            yield Label("Help · keys and presets", classes="section-title")
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
- **Ctrl+R** run (or jump to the first thing to fix) · **Ctrl+O** open a CSV
- **Ctrl+P** commands, including "Go to step: …" · **Tab** flows through the steps
- **F8** Expert settings · **F9** export them to a file
- **Ctrl+T** results · **Ctrl+Y** copy the report path · **Ctrl+G** cancel a run
- **F1** this guide · **Ctrl+Q** or **Ctrl+C** quit
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

# D5: the advanced field whose value is owned by the one "Debug sheets"
# control (the ``debug`` request field).
TUI_TAB_OWNED_ADVANCED_FIELDS = frozenset({"adv_output_debug_sheets"})

# Layout shell breakpoint: the status/results column needs 42 columns and the
# form at least 66, so below 110 columns results become a Ctrl+T view.
WIDE_LAYOUT_MIN_COLUMNS = 110
RESULTS_COLUMN_WIDTH = 42

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
    # Large-list picker: why the typed target entity cannot be used (03 §6),
    # resolved with ``entity`` on the UI thread by _target_entity_for_run().
    entity_error: Optional[str]
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
    # The entity choosers show the large-list filter (above the Select limit);
    # readiness uses it to focus the visible Citibank field.
    entity_large_list: bool = False


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


def _step_body(step_id: str) -> VerticalScroll:
    """One step's scrolling body. Only step 1 is displayed at first, so the
    hidden steps are never laid out (or tab-sorted) until they are shown."""
    body = VerticalScroll(id=STEP_BY_ID[step_id].container_id, classes="step", can_focus=False)
    body.display = step_id == STEPS[0].id
    return body


class BenchmarkApp(App):
    """Privacy-Compliant Peer Benchmark Tool TUI"""

    # F8 opens the Expert settings screen and F9 exports it; no widget binds
    # either, so they work in any field. Ctrl+A/Ctrl+E stay as hidden aliases
    # for muscle memory and the perf probe (a focused Input takes them for
    # Home/End). The key bar (tui.keybar) shows the keys; no Footer.
    BINDINGS = [
        Binding("ctrl+o", "open_file", "Open CSV"),
        Binding("ctrl+r", "run_analysis", "Run"),
        Binding("f1", "show_help", "Help"),
        Binding("f8", "toggle_advanced", "Expert settings"),
        Binding("f9", "export_advanced", "Export expert settings"),
        Binding("ctrl+a", "toggle_advanced", "Expert settings", show=False),
        Binding("ctrl+e", "export_advanced", "Export expert settings", show=False),
        Binding("ctrl+l", "clear_log", "Clear log"),
        # Layout shell (01 §4.1): no stock widget binds these, and none is a
        # tmux (^B) or GNU screen (^A) prefix, so they work from any field.
        Binding("ctrl+g", "cancel_run", "Cancel run", priority=True),
        Binding("ctrl+t", "toggle_results", "Results", priority=True),
        Binding("ctrl+y", "copy_path", "Copy path", priority=True),
        # Release tooling exits with Escape then Ctrl+C (edge_deploy.yaml
        # tui_exit: ctrl_c). Textual 7.5 binds Ctrl+C to copy (Input, Screen)
        # and only *hints* at quitting, so the app owns it: copy when there is
        # a selection, otherwise quit like Ctrl+Q.
        Binding("ctrl+c", "copy_or_quit", "Quit", show=False, priority=True),
    ]

    # D5: output.include_debug_sheets is driven only by the "Debug sheets"
    # control (request field ``debug``). The shared spec stays in
    # utils.config_overrides for other adapters; the TUI has no second,
    # silently overridden control for it.
    ADVANCED_FIELD_SPECS: List[ConfigFieldSpec] = [
        spec for spec in ADVANCED_FIELD_SPECS if spec.widget_id not in TUI_TAB_OWNED_ADVANCED_FIELDS
    ]

    # At most this many toasts at once (01 §5.3); a third replaces the oldest.
    MAX_TOASTS = 2
    # Toasts raised while a modal is open wait for it to close, unless older.
    QUEUED_TOAST_MAX_AGE_S = 10.0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Set before the first stylesheet pass: assigning it in on_mount
        # restyled the whole widget tree a second time (03 §1.3).
        self.theme = "tokyo-night"
        # One parse of presets/*.yaml for display (see PresetCatalog).
        self._preset_catalog = PresetCatalog()
        self._preset_options: List[Tuple[str, str]] = []
        # PR 5: the form model. Widgets bind to it; everything else reads it.
        self.form = FormState()
        self.form.set_listener(self._on_form_change)
        # Confirmations the analysis worker is blocked on (see _await_confirmation).
        self._confirmation_lock = threading.Lock()
        self._pending_confirmations: set[threading.Event] = set()
        self._confirmations_abandoned = False
        # Owner decision 1: set by request_cancel(); core checks it at phase
        # boundaries and before output writing starts (never during it).
        self._cancel_event = threading.Event()
        self._run_stage: Optional[str] = None
        # D4: restored column choices wait here for the first CSV header load.
        self._pending_session: Dict[str, Any] = {}
        self._not_restored: List[Tuple[str, Any]] = []
        self._restore_toast_due = False
        # Layout shell. Steps mount on first show (03 §1.1): mounted = mount
        # started, ready = widgets composed and synced from the form.
        self._current_step = STEPS[0].id
        self._mounted_steps: set = {STEPS[0].id}
        self._ready_steps: set = set()
        # Step 3's share/rate field groups: mounted with the step for the
        # active mode, the other on the first switch.
        self._mode_fields_mounted: set = set()
        self._mode_fields_ready: set = set()
        self._pending_focus: Optional[Tuple[str, Any]] = None
        self._blockers: Tuple[LaunchBlocker, ...] = ()
        self._shell_refresh_pending = False
        # Who asked for the cancel ("button" for ^G, "quit" for Quit). The
        # visible Cancel records telemetry where the cancel took effect.
        self._cancel_origin: Optional[str] = None
        # Path ^Y copies (report, or the log after a withheld/failed run).
        self._copy_path: Optional[str] = None
        self._outcome_message = ""
        self._setup_focus: Any = None
        self._focus_before_lock: Any = None
        # Dataset facts from the last header load.
        self._csv_loaded = False
        self._csv_meta: Any = Text("No file loaded. Type a path and press Enter, or press Ctrl+O.")
        # Expert settings: preset values per preset, for the diff.
        self._expert_preset_cache: Dict[str, Dict[str, Any]] = {}
        # Toast policy (01 §5.3).
        self._queued_toasts: "collections.deque[tuple]" = collections.deque()

    # One token stylesheet for every screen (tui/styles.py, 02 §1).
    CSS = AUTOBENCH_TCSS

    # Results column at 110+ columns, a Ctrl+T view below (01 §3.1).
    HORIZONTAL_BREAKPOINTS = [(0, "-narrow"), (WIDE_LAYOUT_MIN_COLUMNS, "-wide")]
    # Owner decision 7: step jumps are palette entries ("Go to step: …").
    COMMANDS = App.COMMANDS | {AutobenchCommands}

    # Release tooling matches the title (edge_deploy.yaml tui_chrome_regex).
    TITLE = "Privacy-Compliant Peer Benchmark"
    SUB_TITLE = ""

    def compose(self) -> ComposeResult:
        """Create child widgets for the app.

        Layout shell (01 §3.1): header, step rail, the five step bodies, the
        status/results column (a right-hand column at 110+ columns, a ``^T``
        view below that), the action bar and the key bar. Only step 1's
        widgets are composed here; the other steps mount on first show
        (``_ensure_step_mounted``), built from the form model.
        """
        # No clock: it would repaint the header (and push bytes over SSH)
        # every second for the lifetime of the app.
        yield Header(show_clock=False)
        yield StepRail(id="step_rail")

        with Horizontal(id="app_body"):
            with Vertical(id="setup_pane"):
                yield Static("", id="form_lock_note", classes="hidden")
                for step in STEPS:
                    body = _step_body(step.id)
                    if step.id == STEPS[0].id:
                        with body:
                            yield from BUILDERS[step.id](self._step_context())
                    else:
                        yield body

            # ═══════════════════════════════════════════════════════════
            # STATUS / RESULTS — a right-hand column at 110+ columns, the
            # ^T view below that (01 §3.3)
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
                    yield Static("No runs yet in this session.", id="results_panel")
                    # The path to copy, whole and selectable even when the
                    # terminal blocks clipboard writes (OSC 52) over SSH.
                    with Vertical(id="results_copy", classes="hidden"):
                        yield Static("", id="results_path_label", classes="field-label")
                        yield Static("", id="results_path", classes="ab-path")
                        yield Button("Copy report path ^Y", id="btn_copy_path", compact=True)

                yield Button("Show run log", id="btn_show_log", compact=True)
                # highlight=False: per-line regex highlighting is CPU-costly on
                # busy logs. max_lines bounds memory and re-render cost on
                # long sessions.
                log = Log(id="log_output", highlight=False, max_lines=2000, classes="ab-panel")
                log.border_title = "Run log"
                yield log

        yield ActionBar(id="action_bar")
        yield KeyBar("field", id="key_bar")

    # ──────────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        """Event handler called when widget is added to the app."""
        self._run_state = "idle"
        self._run_started_at: Optional[float] = None
        self._run_mode: Optional[str] = None
        self._elapsed_timer = None
        self._last_status_text: Optional[tuple] = None
        self._outcome_badge: Optional[str] = None
        self._last_telemetry_surface: Optional[str] = None
        self._telemetry_session_started = False
        # Preset-driven release-mode refresh waits until session restore is done.
        self._tui_bootstrapping = True
        self.load_presets()
        self.setup_logging_capture()
        self._refresh_run_status()
        self._restore_session()
        self._tui_bootstrapping = False

        # Only step 1 is mounted. No launch toast (01 §5.3): the key bar and
        # the action bar show the keys.
        self._main_screen = self.screen
        self._ready_steps.add(STEPS[0].id)
        self._sync_step(STEPS[0].id)
        self._bind_step(STEPS[0].id)
        self._show_step(STEPS[0].id, focus=False)
        self._refresh_shell()

        # Set initial focus
        self.query_one("#csv_path").focus()
        # Session starts once the TUI is mounted and usable.
        start_session("tui")
        self._telemetry_session_started = True
        if getattr(self, "_telemetry_session_restored", False):
            session_restored()
        self._emit_surface_if_changed(self._analysis_mode())
        # Pay the deferred engine import off the UI thread once the first
        # frame is up, so the first Run does not wait for it (03 §1.4).
        self.call_after_refresh(self._prewarm_analysis_run)
        self.set_timer(STEP_CSS_PRELOAD_DELAY_S, self._preload_step_css)

    def _preload_step_css(self) -> None:
        """Register the DEFAULT_CSS of the later steps' widget classes, parse once.

        The same sources Textual would add on their first mount (identical
        location keys, so the later add is a no-op); styles do not change.
        """
        if getattr(self, "_exit", False) or not self.is_running:
            return
        stylesheet = self.stylesheet
        for cls in (
            SafeSelect, ColumnSelect, SelectCurrent, SelectOverlay, OptionList, SelectionList,
            BoxSelectionList, BoxCheckbox, Disclosure, CollapsibleTitle, Collapsible.Contents,
            Container, EntityChooser, ModeSwitch,
        ):
            for read_from, css, tie_breaker, scope in DOMNode._get_default_css(object.__new__(cls)):
                stylesheet.add_source(
                    css, read_from=read_from, is_default_css=True, tie_breaker=tie_breaker, scope=scope
                )
        stylesheet.rules_map  # parse now, while idle  # noqa: B018

    def _prewarm_analysis_run(self) -> None:
        if getattr(self, "_exit", False):
            return
        self.run_worker(
            _prewarm_engine,
            thread=True,
            group="prewarm",
            exit_on_error=False,
            description="pre-warm core.analysis_run",
        )

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
        if self.cancel_requested and self._cancel_origin == "button":
            # ^G while the review was open: the visible cancel, not a review
            # decision (and never a forced block).
            self._record_visible_cancel("cancel_before_run")
            finalize_deferred_logging(
                logging.getLogger(),
                privacy_authorized=False,
            )
            write_log_message(log_widget, "Run cancelled before the engine started. Nothing was written.")
            self._end_run_ui(
                "cancelled",
                _outcome_markup(labels.RUN_CANCELLED_BEFORE_START, code="RunCancelled"),
            )
            return
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
    # Form model binding (PR 5)
    # ──────────────────────────────────────────────────────────────────

    def _step_context(self) -> StepContext:
        return StepContext(
            form=self.form,
            loaded=self._csv_loaded,
            entity_values=list(self._entity_values),
            entity_index=self._entity_index,
            entity_loading=self.entity_values_loading,
            preset_options=list(self._preset_options),
            launch_folder=_launch_folder(),
            csv_meta=self._csv_meta,
        )

    def _widget(self, widget_id: str, kind: Any = None) -> Any:
        """A bound widget if its step is ready, else None (never raises)."""
        step = WIDGET_STEPS.get(widget_id)
        if step is not None and step not in self._ready_steps:
            return None
        try:
            return self.query_one(f"#{widget_id}", kind) if kind else self.query_one(f"#{widget_id}")
        except NoMatches:
            return None

    def _bound(self, widget: Any) -> bool:
        """Widget events count only once their step is synced from the form."""
        step = self._step_of(widget)
        return step is None or step in self._ready_steps

    def _on_form_change(self, name: str, old: Any, new: Any) -> None:
        """FormState listener: re-sync the widget, then the dependent state."""
        if getattr(self, "_exit", False):
            return
        if not getattr(self, "_applying_restore", False):
            # Editing a restored value makes it the operator's own choice.
            self.form.restored.discard(name)
        self._sync_widget(name)
        if name in ROLE_FIELDS:
            self._refresh_column_lists()
        if name == "mode":
            self._ensure_mode_fields(new)
            self._refresh_column_lists()
            if not getattr(self, "_tui_bootstrapping", False):
                self._emit_surface_if_changed(self._analysis_mode())
            self._refresh_run_status()
        elif name == "entity_col":
            if new:
                self.load_unique_entities(new)
            else:
                self._cancel_entity_load()
        elif name == "preset":
            self._on_preset_changed(old, new)
        self._refresh_derived_ui()
        self._schedule_shell_refresh()

    def _sync_widget(self, name: str) -> None:
        """Show the form value ``name`` in its widget, if that widget is mounted."""
        with self._syncing():
            self._sync_widget_now(name)

    def _sync_widget_now(self, name: str) -> None:
        widget_id = FIELD_WIDGETS.get(name)
        if widget_id is None:
            return
        widget = self._widget(widget_id)
        if widget is None:
            return
        value = getattr(self.form, name)
        if isinstance(widget, EntityChooser):
            if widget.id == "entity_chooser":
                widget.set_choice(self.form.entity, self.form.entity_filter)
            else:
                widget.set_choice(self.form.citibank_entity, self.form.citibank_filter)
        elif isinstance(widget, ColumnSelect):
            widget.set_value(value)
        elif isinstance(widget, Select):
            target = SELECT_BLANK if value is None else value
            if widget.value != target:
                try:
                    widget.value = target
                except Exception:
                    pass  # Not an option here (e.g. an unknown preset).
        elif isinstance(widget, ModeSwitch):
            if widget.mode != value:
                widget.mode = value
        elif isinstance(widget, SelectionList):
            self._sync_selection_list(widget, name)
        elif isinstance(widget, Checkbox):
            if name == "rule_sweep":
                value = self.form.effective_sweep
            if widget.value != bool(value):
                widget.value = bool(value)
        elif isinstance(widget, Input):
            if widget.value != (value or ""):
                widget.value = value or ""

    def _sync_selection_list(self, widget: SelectionList, name: str) -> None:
        form = self.form
        selections = dimension_selections(form) if name == "dimensions" else secondary_selections(form)
        values = [value for _, value, _ in selections]
        current = [widget.get_option_at_index(i).value for i in range(widget.option_count)]
        if current != values:
            with self.batch_update():
                widget.clear_options()
                widget.add_options(selections)
            return
        wanted = {value for value, chosen in ((v, c) for _, v, c in selections) if chosen}
        if set(widget.selected) != wanted:
            with self.batch_update():
                for value in values:
                    if value in wanted:
                        widget.select(value)
                    else:
                        widget.deselect(value)

    def _refresh_column_lists(self) -> None:
        """Dimensions and secondary metrics follow the active mode's roles."""
        for name in ("dimensions", "secondary"):
            self._sync_widget(name)

    def _refresh_column_selects(self) -> None:
        with self._syncing():
            self._refresh_column_selects_now()

    def _refresh_column_selects_now(self) -> None:
        form = self.form
        numeric, other = form.numeric_first()
        for name, widget_id in (
            ("entity_col", "entity_col"),
            ("time_col", "time_col"),
            ("metric", "share_metric"),
            ("total_col", "rate_total"),
            ("approved_col", "rate_approved"),
            ("fraud_col", "rate_fraud"),
        ):
            widget = self._widget(widget_id, ColumnSelect)
            if widget is None:
                continue
            numeric_first = name not in ("entity_col", "time_col")
            primary, secondary = (numeric, other) if numeric_first else (other, numeric)
            widget.prompt = "Select column…" if self._csv_loaded else "Load a CSV first"
            widget.set_columns(primary, secondary, getattr(form, name), mark=form.numeric_columns)
        self._refresh_column_lists()

    def _sync_step(self, step_id: str) -> None:
        """Bring every widget of a just-mounted step up to the form (UI thread)."""
        with self.batch_update(), self._syncing():
            for name, step in FIELD_STEPS.items():
                if step == step_id:
                    self._sync_widget(name)
            if step_id in ("entity", "analysis", "privacy"):
                self._refresh_column_selects()
            if step_id in ("entity", "privacy"):
                self._sync_entity_choosers()
            self._refresh_derived_ui()
        if step_id == "data":
            self._show_csv_meta()

    def _sync_entity_choosers(self) -> None:
        with self._syncing():
            self._sync_entity_choosers_now()

    def _sync_entity_choosers_now(self) -> None:
        for chooser_id, choice, text in (
            ("entity_chooser", self.form.entity, self.form.entity_filter),
            ("citibank_chooser", self.form.citibank_entity, self.form.citibank_filter),
        ):
            step = "entity" if chooser_id == "entity_chooser" else "privacy"
            if step not in self._ready_steps:
                continue
            try:
                chooser = self.query_one(f"#{chooser_id}", EntityChooser)
            except NoMatches:
                continue
            chooser.set_loading(self.entity_values_loading)
            if chooser.large != (self._entity_index is not None) or chooser.values != self.entity_choices:
                chooser.set_values(
                    self._entity_values, self._entity_index, choice=choice, text=text, loaded=self._csv_loaded
                )
            else:
                chooser.set_choice(choice, text)

    def _refresh_derived_ui(self) -> None:
        """Visibility, enablement and summaries that follow the form (idempotent)."""
        with self._syncing():
            self._refresh_derived_ui_now()

    def _refresh_derived_ui_now(self) -> None:
        form = self.form
        share = form.mode == "share"

        def show(widget_id: str, visible: bool) -> None:
            widget = self._widget(widget_id)
            if widget is not None and widget.display != visible:
                widget.display = visible

        def enable(widget_id: str, enabled: bool) -> None:
            widget = self._widget(widget_id)
            if widget is not None and widget.disabled == enabled:
                widget.disabled = not enabled

        cache = self.__dict__.setdefault("_derived_text", {})

        def text(widget_id: str, value: Any) -> None:
            # Static.update forces a layout pass; this runs on every form
            # change (each keystroke in a text field), so skip unchanged text.
            widget = self._widget(widget_id, Static)
            if widget is None:
                return
            key = str(value) if not isinstance(value, Text) else (value.plain, str(value.spans))
            if cache.get(widget_id) == (id(widget), key):
                return
            cache[widget_id] = (id(widget), key)
            widget.update(value)

        if "analysis" in self._ready_steps:
            show("share_fields", share)
            show("rate_fields", not share)
            show("dims", not form.auto_dims)
            show("dims_hint", not form.auto_dims)
            show("fraud_in_bps_row", not share)
            bps_ok = bool(form.fraud_col) and form.output_format in ("publication", "both")
            enable("fraud_in_bps", bps_ok)
            text(
                "fraud_in_bps_hint",
                "" if bps_ok else "(disabled here: needs a fraud column and a publication workbook)",
            )
            enable("include_calculated", form.export_balanced_csv)
            more = self._widget("more_options", Collapsible)
            if more is not None:
                title = more_options_title(form)
                if more.title != title:
                    more.title = title
            text("expert_summary", f"optimizer tuning · {expert_changes_text(len(form.expert))}")
        if "privacy" in self._ready_steps:
            show("release_mode_row", share)
            show("release_mode_rate_note", not share)
            sweep = self._widget("privacy_rule_sweep_mode", Checkbox)
            if sweep is not None:
                if sweep.disabled != form.sweep_locked:
                    sweep.disabled = form.sweep_locked
                if sweep.value != form.effective_sweep:
                    sweep.value = form.effective_sweep
            text(
                "sweep_lock_note",
                "Locked on by Verified safe coverage." if form.sweep_locked else "",
            )
            restored = " ↺ restored" if "release_mode" in form.restored else ""
            text("privacy_release_mode_hint", RELEASE_MODE_HINTS.get(form.release_mode, "") + restored)
            chooser = self._widget("citibank_chooser", EntityChooser)
            if chooser is not None:
                chooser.set_enabled(form.citi_competitor)
            text(
                "citibank_entity_hint",
                "Pick the exact value from the entity column. Never restored."
                if form.citi_competitor
                else "Only needed when the box above is ticked.",
            )
            text("posture_line", self._posture_line())
            text("preset_blurb", self._preset_blurb_text(form.preset))
        for name, (label_id, base) in PAIR_LABELS.items():
            label = self._widget(label_id, Label)
            if label is not None:
                wanted = self._restored_label(base, name)
                if str(label.content) != wanted:
                    label.update(wanted)
        if "entity" in self._ready_steps:
            count = len(self.entity_choices)
            column = form.entity_col or "—"
            text(
                "entity_count",
                f"{count:,} entities in {column}." if self._csv_loaded and count else "",
            )

    def _restored_label(self, label: str, name: str) -> str:
        return f"{label}  ↺" if name in self.form.restored else label

    # ── Widget → form binding ─────────────────────────────────────────
    #
    # Synchronous: each bound widget's reactive is watched (App.watch), so the
    # form holds a widget's value the moment it changes, as reading the widget
    # did before PR 5. App-driven widget updates run inside ``_syncing`` and
    # are not echoed back.

    @contextlib.contextmanager
    def _syncing(self) -> Iterator[None]:
        self._sync_depth = getattr(self, "_sync_depth", 0) + 1
        try:
            yield
        finally:
            self._sync_depth -= 1

    @property
    def _is_syncing(self) -> bool:
        return getattr(self, "_sync_depth", 0) > 0

    def _bind_step(self, step_id: str) -> None:
        """Watch every bound widget of a mounted step (after its first sync)."""
        try:
            body = self.query_one(f"#{STEP_BY_ID[step_id].container_id}")
        except NoMatches:
            return
        self._bind_container(body)

    def _bind_container(self, container: Any) -> None:
        for widget in container.query("*"):
            if getattr(widget, "_ab_bound", False):
                continue
            widget._ab_bound = True
            if isinstance(widget, EntityChooser):
                widget.change_callback = self._chooser_changed
                continue
            if (widget.id or "") not in WIDGET_FIELDS:
                continue
            callback = self._widget_callback(widget)
            if isinstance(widget, SelectionList):
                widget.selection_callback = callback  # type: ignore[attr-defined]
            elif isinstance(widget, ModeSwitch):
                self.watch(widget, "mode", callback, init=False)
            else:
                self.watch(widget, "value", callback, init=False)

    def _widget_callback(self, widget: Any) -> Callable[[Any], None]:
        def changed(_value: Any = None) -> None:
            self._widget_to_form(widget)

        return changed

    def _widget_to_form(self, widget: Any) -> None:
        """Write one bound widget's current value into the form."""
        if self._is_syncing or getattr(self, "_exit", False) or not self._bound(widget):
            return
        name = WIDGET_FIELDS.get(widget.id or "")
        if name is None:
            return
        form = self.form
        if isinstance(widget, ColumnSelect):
            if widget.value == SEPARATOR:
                with self._syncing():
                    widget.set_value(getattr(form, name))
                return
            setattr(form, name, widget.column)
        elif isinstance(widget, Select):
            raw = widget.value
            value = None if raw == SELECT_BLANK else raw
            if name == "preset":
                self._preset_selected(value)
            elif value is not None or name not in ("release_mode", "output_format"):
                setattr(form, name, value)
        elif isinstance(widget, SelectionList):
            options = set(form.dimension_options() if name == "dimensions" else form.secondary_options())
            hidden = [value for value in getattr(form, name) if value not in options]
            setattr(form, name, tuple(hidden) + tuple(widget.selected))
        elif isinstance(widget, Checkbox):
            if name == "rule_sweep" and form.sweep_locked:
                return  # Shows the forced value; the operator's own value is kept.
            setattr(form, name, bool(widget.value))
        elif isinstance(widget, ModeSwitch):
            form.mode = widget.mode
        elif isinstance(widget, Input):
            setattr(form, name, widget.value)

    def _chooser_changed(self, chooser: EntityChooser, choice: Optional[str], text: str) -> None:
        if self._is_syncing or not self._bound(chooser):
            return
        if chooser.id == "entity_chooser":
            self.form.update(entity=choice, entity_filter=text)
        else:
            self.form.update(citibank_entity=choice, citibank_filter=text)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "review_blockers":
            option_id = event.option.id or ""
            if option_id.startswith("blocker:"):
                self._focus_field(option_id[len("blocker:"):])

    def on_collapsible_expanded(self, event: Collapsible.Expanded) -> None:
        if event.collapsible.id == "more_options":
            self._ensure_more_options()
        self._scroll_focus_into_view()

    _mode_pending_focus: Optional[str] = None

    # monotonic time of the last key or mouse event (see on_event).
    _last_input_at = 0.0

    async def on_event(self, event: events.Event) -> None:
        if isinstance(event, events.InputEvent) and not event.is_forwarded:
            self._last_input_at = time.monotonic()
        await super().on_event(event)

    def _prewarm_next_step(self) -> None:
        """Mount the next unmounted step of STEP_PREWARM_ORDER while idle.

        One step per tick keeps each stall short; a run in progress or a
        modal screen defers nothing (the step simply mounts on first show).
        """
        if getattr(self, "_exit", False) or not self.is_running or self._run_state in ("validating", "running"):
            return
        stack = self.screen_stack  # empty while the app shuts down
        if not stack or isinstance(stack[-1], ModalScreen):
            return
        # Never mount under the operator's fingers: wait until input has been
        # quiet this long (PR 6: the step 3 mount landed in key windows).
        quiet_for = time.monotonic() - self._last_input_at
        if quiet_for < STEP_PREWARM_DELAY_S:
            self.set_timer(STEP_PREWARM_DELAY_S - quiet_for, self._prewarm_next_step)
            return
        for step_id in STEP_PREWARM_ORDER:
            if step_id not in self._mounted_steps:
                self._ensure_step_mounted(step_id)
                self.set_timer(STEP_PREWARM_DELAY_S, self._prewarm_next_step)
                return

    # More options' fields mount on first open (step 3 shows faster; most runs
    # never open it). Until then the form model holds their values as usual.
    _more_mounted = False
    _more_ready = False
    _more_pending_focus: Optional[str] = None

    def _ensure_more_options(self) -> None:
        if self._more_mounted:
            return
        more = self._widget("more_options", Collapsible)
        if more is None:
            return
        self._more_mounted = True
        contents = more.query_one(Collapsible.Contents)
        mounted = contents.mount_all(build_more_options(self._step_context()))

        async def finish() -> None:
            await mounted
            if self._mount_abandoned(contents):
                return
            with self.batch_update(), self._syncing():
                for name in MORE_OPTIONS_FIELDS:
                    self._sync_widget_now(name)
                self._refresh_column_selects_now()
                self._refresh_derived_ui_now()
            self._bind_container(contents)
            self._more_ready = True
            self._schedule_shell_refresh()
            widget_id, self._more_pending_focus = self._more_pending_focus, None
            if widget_id is not None:
                self._focus_now(widget_id)

        self.call_later(finish)

    async def open_more_options(self, timeout: float = 10.0) -> None:
        """Show step 3's More options and await its fields (palette, tests)."""
        await self.ensure_step("analysis")
        more = self._widget("more_options", Collapsible)
        if more is not None and more.collapsed:
            more.collapsed = False
        self._ensure_more_options()
        deadline = time.monotonic() + timeout
        while not self._more_ready:
            if time.monotonic() > deadline:
                raise TimeoutError("More options did not mount")
            await asyncio.sleep(0.005)

    def on_collapsible_collapsed(self, event: Collapsible.Collapsed) -> None:
        """Focus inside a closing disclosure moves to its title, not elsewhere."""
        focused = self.focused
        collapsible = event.collapsible
        if focused is not None and collapsible in focused.ancestors:
            collapsible.query_one(CollapsibleTitle).focus()

    # ──────────────────────────────────────────────────────────────────
    # Session persistence (01 §8.1; owner decision 3)
    # ──────────────────────────────────────────────────────────────────

    def _collect_session(self) -> Dict[str, Any]:
        # Column choices restored but never applied (no CSV loaded since)
        # are kept, so a quit before loading a file does not erase them.
        return session_payload(self.form, self._pending_session)

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
        self._apply_session(session)
        # Reported as session_restored once the telemetry session starts.
        self._telemetry_session_restored = bool(session)

    def _apply_session(self, session: Dict[str, Any]) -> None:
        """Restore preferences into the form; column roles wait for a header load.

        Legacy sessions may contain governed dataset/output paths, the target
        entity and the compliance declarations. ``read_session`` never returns
        those; the operator chooses them afresh in each process.
        """
        values = read_session(session)
        defaults = FormState()
        self._applying_restore = True
        try:
            for name, value in values.items():
                if name in COLUMN_FIELDS or name in COLUMN_LIST_FIELDS:
                    # D4: no CSV is loaded yet. Keep the choice until a header
                    # load offers the column.
                    self._pending_session[name] = value
                    continue
                if name == "release_mode":
                    continue  # After the sweep, so the coupling sees its value.
                if name == "preset":
                    if value not in {v for _, v in self._preset_options}:
                        continue  # Stored preset no longer exists.
                elif name == "output_format" and value not in OUTPUT_FORMAT_CODES:
                    continue
                setattr(self.form, name, value)
                if name in ALWAYS_MARK_RESTORED or getattr(self.form, name) != getattr(defaults, name):
                    self.form.restored.add(name)
            if "release_mode" in values:
                self._restore_privacy_release_mode(values["release_mode"])
        finally:
            self._applying_restore = False

    def _restore_privacy_release_mode(self, value: Any) -> None:
        """Restore a session release mode; unknown values fall back safely."""
        if value in _PRIVACY_RELEASE_MODE_VALUES:
            self.form.release_mode = str(value)
            self.form.restored.add("release_mode")
            return
        self.form.release_mode = PrivacyReleaseMode.COMPLETE_OUTPUT.value
        self.notify(
            "The saved release mode is no longer available, so the release "
            "fell back to Complete output.",
            title="Session restore",
            severity="warning",
            timeout=6,
        )

    def _apply_pending_session_columns(self, cols: List[str]) -> None:
        """Apply restored column choices once a CSV header load offers them.

        Runs inside ``load_csv_headers``, after the columns are known and
        before smart defaults. A stored column missing from this file is
        dropped and listed in Review. Pending choices are used by the first
        header load only; a later file never resurrects them.
        """
        pending, self._pending_session = self._pending_session, {}
        if not pending:
            return
        available = set(cols)
        self._applying_restore = True
        try:
            for name, value in pending.items():
                if name in COLUMN_LIST_FIELDS:
                    kept = [v for v in value if v in available]
                    if kept:
                        setattr(self.form, name, tuple(kept))
                        self.form.restored.add(name)
                    for missing in (v for v in value if v not in available):
                        self._not_restored.append((name, missing))
                    continue
                if value in available:
                    setattr(self.form, name, value)
                    self.form.restored.add(name)
                else:
                    self._not_restored.append((name, value))
        finally:
            self._applying_restore = False
        self._restore_toast_due = bool(self.form.restored)

    def action_clear_restored(self) -> None:
        """Reset every restored value to its default (Review, palette)."""
        defaults = FormState()
        for name in sorted(self.form.restored):
            if name == "preset":
                self.form.preset = self._default_preset()
            else:
                setattr(self.form, name, getattr(defaults, name))
        self.form.restored.clear()
        self._not_restored.clear()
        self._schedule_shell_refresh()

    # ──────────────────────────────────────────────────────────────────
    # Layout shell: steps, rail, results view, action bar (PR 4, 01 §3)
    # ──────────────────────────────────────────────────────────────────

    def _step_of(self, widget: Any) -> Optional[str]:
        """The step whose body holds ``widget``, or None (rail, results, bars)."""
        for node in widget.ancestors_with_self:
            node_id = node.id or ""
            if node_id.startswith("step_") and node_id[5:] in STEP_BY_ID:
                return node_id[5:]
        return None

    def _step_of_id(self, widget_id: str) -> Optional[str]:
        step = WIDGET_STEPS.get(widget_id)
        if step is not None:
            return step
        try:
            return self._step_of(self.query_one(f"#{widget_id}"))
        except NoMatches:
            return None

    @property
    def _restored_steps(self) -> set:
        return {FIELD_STEPS[name] for name in self.form.restored if name in FIELD_STEPS}

    def _mount_abandoned(self, container: Any) -> bool:
        """True when a lazy mount finished after the app began closing."""
        # ``is_running`` turns False first thing in App._shutdown.
        return bool(
            getattr(self, "_exit", False) or not self.is_running or self._closing or not container.is_attached
        )

    def _ensure_step_mounted(self, step_id: str) -> None:
        """Mount a step's widgets the first time it is shown (03 §1.1)."""
        if step_id in self._mounted_steps or step_id not in STEP_BY_ID:
            return
        try:
            body = self.query_one(f"#{STEP_BY_ID[step_id].container_id}")
        except NoMatches:
            return
        self._mounted_steps.add(step_id)
        if step_id == "analysis":
            self._mode_fields_mounted.add(self.form.mode)
            built_mode = self.form.mode
        mounted = body.mount_all(BUILDERS[step_id](self._step_context()))

        async def finish() -> None:
            await mounted
            if self._mount_abandoned(body):
                return
            if step_id == "analysis":
                self._mode_fields_ready.add(built_mode)
            self._ready_steps.add(step_id)
            if self._run_state in ("validating", "running"):
                body.disabled = True
            self._sync_step(step_id)
            self._bind_step(step_id)
            if step_id == "analysis":
                self._ensure_mode_fields(self.form.mode)
            self._refresh_shell()
            pending, self._pending_focus = self._pending_focus, None
            if pending is not None:
                if pending[0] == step_id:
                    self._apply_focus(step_id, pending[1])
                else:
                    self._pending_focus = pending

        self.call_later(finish)

    async def ensure_step(self, step_id: str, timeout: float = 10.0) -> None:
        """Await a step's widgets (mounting it if needed) without showing it.

        For step 3 that is the active mode's fields; the other mode's mount
        when the mode is switched.
        """
        self._ensure_step_mounted(step_id)
        deadline = time.monotonic() + timeout

        def ready() -> bool:
            if step_id not in self._ready_steps:
                return False
            return step_id != "analysis" or self.form.mode in self._mode_fields_ready

        while not ready():
            if time.monotonic() > deadline:
                raise TimeoutError(f"step {step_id} did not mount")
            await asyncio.sleep(0.005)

    def _ensure_mode_fields(self, mode: str) -> None:
        """Mount a mode's step 3 fields the first time that mode is used."""
        if "analysis" not in self._ready_steps or mode in self._mode_fields_mounted:
            return
        try:
            group = self.query_one("#share_fields" if mode == "share" else "#rate_fields")
        except NoMatches:
            return
        self._mode_fields_mounted.add(mode)
        mounted = group.mount_all(build_mode_fields(self._step_context(), mode))

        async def finish() -> None:
            await mounted
            if self._mount_abandoned(group):
                return
            with self.batch_update(), self._syncing():
                self._refresh_column_selects_now()
                self._refresh_derived_ui_now()
            self._bind_container(group)
            self._mode_fields_ready.add(mode)
            self._schedule_shell_refresh()
            widget_id, self._mode_pending_focus = self._mode_pending_focus, None
            if widget_id is not None and widget_id in MODE_FIELD_WIDGETS[mode]:
                self._focus_now(widget_id)

        self.call_later(finish)

    def _step_focus_chain(self, step_id: str) -> List[Any]:
        try:
            container = self.query_one(f"#{STEP_BY_ID[step_id].container_id}")
        except NoMatches:
            return []
        main = getattr(self, "_main_screen", None) or self.screen
        in_chain = {widget for widget in main.focus_chain if container in widget.ancestors}
        # DOM order: a step that was just displayed has no layout yet, and
        # Textual's layout-sorted chain would put margin-topped containers
        # first. Once laid out, both orders agree in these vertical forms.
        return [widget for widget in container.walk_children() if widget in in_chain]

    def _step_entry_widget(self, step_id: str) -> Any:
        """First blocker in the step (01 §4.3 rule 3), else its first stop."""
        for blocker in self._blockers:
            if self._step_of_id(blocker.focus_id) == step_id:
                widget = self._widget(blocker.focus_id)
                if widget is not None and widget.focusable and widget.display:
                    return widget
        chain = self._step_focus_chain(step_id)
        return chain[0] if chain else None

    def _show_step(self, step_id: str, *, focus: Any = True) -> None:
        """Display one step body; the others stay mounted with ``display: none``.

        ``focus=True`` moves focus to the step's entry widget unless focus is
        already inside it; ``"entry"`` always does; ``"first"``/``"last"``
        focus its first/last stop;
        a widget id focuses that field; ``False`` leaves focus alone. A step
        shown for the first time is mounted, and the focus waits for it.
        """
        if step_id not in STEP_BY_ID:
            return
        changed = step_id != self._current_step
        self._current_step = step_id
        self._ensure_step_mounted(step_id)
        focused = self.focused
        if focused is not None and self._step_of(focused) not in (None, step_id):
            # Its step is about to be hidden. Textual would otherwise refocus
            # a sibling in that hidden step, which would bring the step back.
            self.screen.set_focus(None)
        for step in STEPS:
            try:
                self.query_one(f"#{step.container_id}").display = step.id == step_id
            except NoMatches:
                continue
        self._set_results_view(False)
        if changed:
            # Ask for the screen layout now. Otherwise the display switch is
            # only noticed on the idle pass after the next frame, and at 20 FPS
            # the newly shown step waits one extra 50 ms frame for its layout
            # (PR 6: step 3 first show 0.13 s -> about 0.08 s at 50 entities).
            self.screen.refresh(layout=True)
            # A step that was just displayed has no layout yet, so the focus
            # scroll inside it happens after the next refresh.
            self.call_after_refresh(self._scroll_focus_into_view)
        if focus:
            if step_id in self._ready_steps:
                self._apply_focus(step_id, focus)
            else:
                self._pending_focus = (step_id, focus)
        self._schedule_shell_refresh()

    def _apply_focus(self, step_id: str, focus: Any) -> None:
        if focus in ("first", "last"):
            chain = self._step_focus_chain(step_id)
            target = (chain[0] if focus == "first" else chain[-1]) if chain else None
        elif focus == "entry":
            target = self._step_entry_widget(step_id)
        elif focus is True:
            focused = self.focused
            if focused is not None and self._step_of(focused) == step_id:
                return
            target = self._step_entry_widget(step_id)
        else:
            widget_id = str(focus)
            if widget_id in MORE_OPTIONS_WIDGETS and not self._more_ready:
                more = self._widget("more_options", Collapsible)
                if more is not None:
                    self._more_pending_focus = widget_id
                    more.collapsed = False
                    self._ensure_more_options()
                    return
            if widget_id in MORE_OPTIONS_WIDGETS:
                more = self._widget("more_options", Collapsible)
                if more is not None and more.collapsed:
                    more.collapsed = False
                    self.call_after_refresh(self._focus_now, widget_id)
                    return
            target = self._widget(widget_id)
            if target is None:
                for mode, ids in MODE_FIELD_WIDGETS.items():
                    if widget_id in ids and mode not in self._mode_fields_ready:
                        # Its mode group is still mounting: focus it when ready.
                        self._mode_pending_focus = widget_id
                        self._ensure_mode_fields(mode)
                        return
        if target is not None:
            target.focus()

    def _focus_now(self, widget_id: str) -> None:
        widget = self._widget(widget_id)
        if widget is not None:
            widget.focus()
            widget.scroll_visible(animate=False)

    def _scroll_focus_into_view(self) -> None:
        focused = self.focused
        if focused is not None and self._step_of(focused) == self._current_step:
            focused.scroll_visible(animate=False)

    def action_go_to_step(self, step_id: str) -> None:
        """Palette "Go to step: …" and rail clicks: show the step, focus its entry."""
        if isinstance(self.screen, ModalScreen) or step_id not in STEP_BY_ID:
            return
        self._show_step(step_id, focus="entry")

    def on_step_rail_step_clicked(self, event: StepRail.StepClicked) -> None:
        self.action_go_to_step(event.step_id)

    def _focus_field(self, widget_id: str) -> None:
        """Show the step holding ``widget_id`` (closing the results view) and focus it."""
        step = self._step_of_id(widget_id)
        if step is None:
            try:
                self.query_one(f"#{widget_id}").focus()
            except NoMatches:
                pass
            return
        self._show_step(step, focus=widget_id)

    # Tab flows from the last stop of a step into the next step, Shift+Tab
    # from the first stop into the previous one; Review wraps to Data (01 §4.3).
    def action_focus_next(self) -> None:
        if not self._flow_between_steps(+1):
            super().action_focus_next()

    def action_focus_previous(self) -> None:
        if not self._flow_between_steps(-1):
            super().action_focus_previous()

    def _flow_between_steps(self, direction: int) -> bool:
        main = getattr(self, "_main_screen", None)
        if main is None or self.screen is not main or self._results_view_open() or self._log_view_open():
            return False
        focused = self.focused
        if focused is None or self._step_of(focused) != self._current_step:
            return False
        chain = self._step_focus_chain(self._current_step)
        if not chain:
            return False
        edge = chain[-1] if direction > 0 else chain[0]
        if focused is not edge:
            return False
        ids = [step.id for step in STEPS]
        target = ids[(ids.index(self._current_step) + direction) % len(ids)]
        self._show_step(target, focus="first" if direction > 0 else "last")
        return True

    # ── Results column (wide) / ^T view (narrow) ──────────────────────

    def _is_wide(self) -> bool:
        return self.size.width >= WIDE_LAYOUT_MIN_COLUMNS

    def _results_view_open(self) -> bool:
        main = getattr(self, "_main_screen", None)
        return bool(main is not None and not self._is_wide() and main.has_class("-show-results"))

    def _set_results_view(self, show: bool) -> None:
        main = getattr(self, "_main_screen", None)
        if main is None or main.has_class("-show-results") == show:
            return
        if show:
            focused = self.focused
            if focused is not None and self._step_of(focused) is not None:
                self._setup_focus = focused
        main.set_class(show, "-show-results")
        self._update_key_bar()

    def _open_results_view(self, *, focus_copy: bool) -> None:
        """Narrow layout only: swap the step body for the status/results view."""
        if self._is_wide():
            return
        self._set_results_view(True)
        target = self._copy_button_if_shown() if focus_copy else None
        if target is not None:
            target.focus()
        elif self.focused is not None and self._step_of(self.focused) is not None:
            # Keys must never reach a field that is no longer displayed.
            self.screen.set_focus(None)

    def _set_has_outcome(self, value: bool) -> None:
        main = getattr(self, "_main_screen", None)
        if main is not None:
            main.set_class(value, "-has-outcome")

    def _copy_button_if_shown(self) -> Any:
        try:
            button = self.query_one("#btn_copy_path", Button)
            box = self.query_one("#results_copy")
        except NoMatches:
            return None
        return button if box.display and not box.has_class("hidden") else None

    def _restore_setup_focus(self) -> None:
        widget = getattr(self, "_setup_focus", None)
        self._setup_focus = None
        if widget is not None and widget.is_attached and self._step_of(widget) == self._current_step:
            widget.focus()
            return
        target = self._step_entry_widget(self._current_step)
        if target is not None:
            target.focus()

    def action_toggle_results(self) -> None:
        """Ctrl+T: <110 swaps setup and results; ≥110 moves focus into the column and back."""
        if isinstance(self.screen, ModalScreen):
            return
        if self._log_view_open():
            self.action_show_log()
            return
        focused = self.focused
        in_results = focused is not None and any(
            node.id == "activity_pane" for node in focused.ancestors_with_self
        )
        if self._is_wide():
            if in_results:
                self._restore_setup_focus()
                return
            if focused is not None and self._step_of(focused) is not None:
                self._setup_focus = focused
            target = self._copy_button_if_shown() or self.query_one("#log_output", Log)
            target.focus()
            return
        if self._results_view_open():
            self._set_results_view(False)
            self._restore_setup_focus()
        else:
            self._open_results_view(focus_copy=True)

    # ── Run log view (PR 5): the whole body for the log, at any width ──

    def _log_view_open(self) -> bool:
        main = getattr(self, "_main_screen", None)
        return bool(main is not None and main.has_class("-show-log"))

    def action_show_log(self) -> None:
        """Show the run log across the whole body (again: back to the form)."""
        main = getattr(self, "_main_screen", None)
        if main is None or isinstance(self.screen, ModalScreen):
            return
        opening = not main.has_class("-show-log")
        if opening:
            focused = self.focused
            if focused is not None and self._step_of(focused) is not None:
                self._setup_focus = focused
        main.set_class(opening, "-show-log")
        try:
            button = self.query_one("#btn_show_log", Button)
            button.label = "Back to the form ^T" if opening else "Show run log"
        except NoMatches:
            pass
        if opening:
            self.query_one("#log_output", Log).focus()
        else:
            self._restore_setup_focus()
        self._update_key_bar()

    # ── Copy path (01 §7.3) ──────────────────────────────────────────

    def action_copy_path(self) -> None:
        """Ctrl+Y: copy the report path (or the log path) via OSC 52.

        Terminals may block clipboard writes over SSH, so the full path is
        always shown, whole and selectable, in the results view as well.
        """
        path = self._copy_path
        if not path:
            self.notify("No report path yet: run an analysis first.", title="Copy path", timeout=3)
            return
        try:
            self.copy_to_clipboard(path)
        except Exception:
            logging.getLogger(__name__).debug("copy_to_clipboard failed", exc_info=True)
        self.notify(
            "Sent to the clipboard. If your terminal blocks that (common over SSH), "
            "select the path in Results instead.",
            title="Path copied",
            timeout=3,
            markup=False,
        )
        if not self._is_wide() and not self._results_view_open():
            self._open_results_view(focus_copy=True)

    def _set_copy_path(self, path: Optional[str], label: str) -> None:
        self._copy_path = path or None
        try:
            box = self.query_one("#results_copy")
            self.query_one("#results_path_label", Static).update(Content(f"{label} · Ctrl+Y copies this path"))
            self.query_one("#results_path", Static).update(Content(path or ""))
            self.query_one("#btn_copy_path", Button).label = (
                "Copy report path ^Y" if label.startswith("Report") else "Copy log path ^Y"
            )
        except NoMatches:
            return
        box.set_class(not path, "hidden")

    # ── Readiness: the launch guards, on the UI thread ────────────────

    def _schedule_shell_refresh(self) -> None:
        """Coalesce rail/action bar/Review updates into one per refresh."""
        if self._shell_refresh_pending or getattr(self, "_exit", False):
            return
        self._shell_refresh_pending = True
        # Next message, not next repaint: one refresh per burst of changes,
        # and done by the time the app is idle again.
        self.call_later(self._refresh_shell)

    def _readiness_blockers(self) -> Tuple[LaunchBlocker, ...]:
        """``launch_blockers`` over a side-effect-free snapshot of the form."""
        try:
            inputs = self._collect_run_inputs(resolve_config=False)
        except Exception:
            return self._blockers
        return launch_blockers(inputs)

    def _refresh_shell(self) -> None:
        self._shell_refresh_pending = False
        if getattr(self, "_exit", False):
            return
        self._blockers = self._readiness_blockers()
        self._refresh_derived_ui()
        self._refresh_rail()
        self._refresh_run_status()  # also refreshes the action bar
        self._refresh_review()
        if self._restore_toast_due and self._csv_loaded:
            self._restore_toast_due = False
            count = len(self.form.restored)
            self.notify(
                f"Restored {count} value{'s' if count != 1 else ''} from last session · Review & run lists them",
                title="Session restore",
                timeout=3,
            )

    def _blocked_steps(self) -> set:
        return {self._step_of_id(b.focus_id) for b in self._blockers}

    def _rail_states(self) -> Dict[str, str]:
        blocked = self._blocked_steps()
        loaded = getattr(self, "_loaded_csv_signature", None) is not None
        restored = self._restored_steps
        states: Dict[str, str] = {}
        for step in STEPS:
            if not loaded and step.id in ("entity", "analysis"):
                # Nothing to choose before a file is loaded (01 §5.1).
                states[step.id] = PENDING
            elif step.id in blocked or (step.id == "review" and self._blockers):
                states[step.id] = ATTENTION
            elif step.id in restored:
                states[step.id] = RESTORED
            elif step.id in ("data", "entity", "analysis"):
                states[step.id] = DONE if loaded else PENDING
            else:
                states[step.id] = DONE
        return states

    def _refresh_rail(self) -> None:
        try:
            rail = self.query_one("#step_rail", StepRail)
        except NoMatches:
            return
        rail.set_states(self._current_step, self._rail_states())

    def _run_label(self) -> str:
        mode = self._run_mode if self._run_state in ("running", "validating") and self._run_mode else self._analysis_mode()
        if mode == "privacy-sweep" or (mode in ("share", "rate") and self._privacy_sweep_enabled()):
            base = self._analysis_mode() if mode == "privacy-sweep" else mode
            return f"{base} privacy sweep"
        return f"{mode} analysis"

    def _ready_summary(self) -> str:
        entity, _ = self._target_entity_for_run()
        parts = [self._run_label(), entity or "peer-only"]
        if self.form.auto_dims:
            parts.append("auto dims")
        else:
            count = len(self.form.effective_dimensions())
            parts.append(f"{count} dim{'s' if count != 1 else ''}")
        if self._effective_preset_posture() == "accuracy_first":
            parts.append("consent asked at run")
        return " · ".join(parts)

    def _refresh_action_bar(self) -> None:
        """One row: readiness or run stage or outcome, plus the key that acts on it."""
        try:
            bar = self.query_one("#action_bar", ActionBar)
        except NoMatches:
            return
        state = getattr(self, "_run_state", "idle")
        run_key = f"^R Run {self._run_label()}"
        if state in ("validating", "running"):
            if self.cancel_requested and self._cancel_origin == "button":
                bar.set_state(
                    "cancelled", "Cancelling: the run stops at its next safe point; nothing is written."
                )
                return
            if state == "validating":
                if isinstance(self.screen, ModalScreen):
                    bar.set_state("awaiting", "Answer the dialog to continue, or cancel the run.", "^G Cancel run", "app.cancel_run")
                else:
                    bar.set_state("running", "Checking inputs and loading data", "^G Cancel run", "app.cancel_run")
                return
            stage = _RUN_STAGE_LABELS.get(self._run_stage or "", "Starting the engine")
            elapsed = ""
            if self._run_started_at is not None:
                elapsed = f" · {_elapsed_since(self._run_started_at):.0f} s"
            if self._run_stage == "output":
                bar.set_state("running", f"{stage}{elapsed}", "Cancel unavailable: writing outputs")
            else:
                bar.set_state("running", f"{stage}{elapsed}", "^G Cancel run", "app.cancel_run")
            return
        if state in ("success", "error", "blocked", "cancelled"):
            badge = self._current_run_badge().state
            message = self._outcome_message or labels.text_for(labels.RUN_STATUS, state)
            if self._copy_path and state == "success":
                bar.set_state(badge, message, "^Y Copy path", "app.copy_path")
            else:
                bar.set_state(badge, message, run_key, "app.run_analysis")
            return
        if self._blockers:
            first = self._blockers[0]
            more = f" (+{len(self._blockers) - 1} more)" if len(self._blockers) > 1 else ""
            bar.set_state("notready", f"{first.message}{more}", run_key, "app.run_analysis", dim_key=True)
            return
        bar.set_state("ready", self._ready_summary(), run_key, "app.run_analysis")

    def _refresh_review(self) -> None:
        """Step 5: blockers you can jump to, then a read-only summary of the form."""
        if "review" not in self._ready_steps:
            return
        try:
            status = self.query_one("#review_status", Static)
            blockers = self.query_one("#review_blockers", OptionList)
            hint = self.query_one("#review_blockers_hint", Static)
            review = self.query_one("#review_summary", Static)
        except NoMatches:
            return
        label = self._run_label()
        if self._blockers:
            count = len(self._blockers)
            noun = "thing" if count == 1 else "things"
            _update_if_changed(status, Text(f"{status_glyph('notready')} {count} {noun} to fix before this {label} can run", style="bold"))
            options = []
            for blocker in self._blockers:
                step = STEP_BY_ID.get(self._step_of_id(blocker.focus_id) or "")
                where = f"  · step {step.number}" if step else ""
                options.append(
                    Option(Text(f"{status_glyph('notready')} {blocker.message}{where}"), id=f"blocker:{blocker.focus_id}")
                )
            key = tuple(option.id for option in options) + tuple(str(o.prompt) for o in options)
            if getattr(self, "_review_blockers_key", None) != key:
                self._review_blockers_key = key
                blockers.set_options(options)
                blockers.highlighted = 0  # ↵ jumps to the first one at once
            blockers.display = True
            _update_if_changed(hint, "↵ or click a line to jump to that field. Ctrl+R jumps to the first one.")
        else:
            _update_if_changed(status, Text(f"{status_glyph('ready')} Ready to run {label}", style="bold"))
            if blockers.display:
                blockers.display = False
            self._review_blockers_key = None
            _update_if_changed(hint, "")
        text = Text()
        for name, value in self._review_lines():
            text.append(f"{name:<10}", style="bold")
            text.append(f"{value}\n")
        restored = sorted({FIELD_LABELS.get(n, n) for n in self.form.restored})
        if restored:
            text.append(f"\n↺ Restored from the last session: {', '.join(restored)}\n")
        for name, value in self._not_restored:
            text.append(f"Not restored: {FIELD_LABELS.get(name, name)} (column {value!r} not in this file)\n")
        _update_if_changed(review, text)
        try:
            run_button = self.query_one("#btn_run", Button)
            clear = self.query_one("#btn_clear_restored", Button)
        except NoMatches:
            return
        if self._run_state not in ("validating", "running"):
            run_button.label = f"Run {label} ^R"
        clear.display = bool(self.form.restored)

    def _review_lines(self) -> List[Tuple[str, str]]:
        form = self.form

        def on_off(value: bool) -> str:
            return "on" if value else "off"

        def mark(name: str) -> str:
            return " ↺" if name in form.restored else ""

        lines: List[Tuple[str, str]] = []
        csv_text = form.csv_path.strip()
        columns = len(form.columns)
        loaded = getattr(self, "_loaded_csv_signature", None) is not None
        if loaded and csv_text:
            # File name only (PR 6). The full path is in step 1's path field
            # and is the first line of the run log.
            lines.append(("Data", f"{os.path.basename(csv_text)} · {columns} columns · full path in step 1"))
        else:
            lines.append(("Data", csv_text or "no file loaded"))
        entity, _ = self._target_entity_for_run()
        lines.append(("Entity", f"{form.entity_col or '—'}{mark('entity_col')} → {entity or 'peer-only benchmark'}"))
        if form.auto_dims:
            dims = "auto-detect"
        else:
            dims = ", ".join(form.effective_dimensions()) or "none"
        if form.mode == "share":
            lines.append(("Analysis", f"Share{mark('mode')} · metric {form.metric or '—'}{mark('metric')} · dims {dims}{mark('dimensions')}"))
        else:
            lines.append((
                "Analysis",
                f"Rate{mark('mode')} · total {form.total_col or '—'} · approved {form.approved_col or '—'} · "
                f"fraud {form.fraud_col or '—'} · dims {dims}{mark('dimensions')}",
            ))
        preset_text = _preset_display(form.preset)
        posture = self._effective_preset_posture()
        if posture:
            posture_text = labels.text_for(labels.POSTURE, posture)
            if posture_text not in preset_text:
                preset_text = f"{preset_text} · posture {posture_text}"
        release = (
            labels.text_for(labels.RELEASE_MODE, form.release_mode) + mark("release_mode")
            if form.mode == "share"
            else "release mode not used for rate"
        )
        lines.append((
            "Privacy",
            f"{preset_text}{mark('preset')} · {release} · rule sweep {on_off(form.effective_sweep)}",
        ))
        citi = "Yes" if form.citi_competitor else "No"
        if form.citi_competitor:
            citi += f" ({form.citibank_entity or 'Citibank entity not chosen'})"
        lines.append((
            "Declared",
            f"merchant spend: {'Yes' if form.merchant_spend else 'No'} · Citi competitor: {citi}",
        ))
        lines.append((
            "Checks",
            f"input validation {on_off(form.validate_input)} · impact {on_off(form.analyze_distortion)} · "
            f"preset comparison {on_off(form.compare_presets)}",
        ))
        output = form.output_file.strip()
        format_text = labels.text_for(labels.OUTPUT_FORMAT, form.output_format)
        where = _full_path(output) if output else f"named automatically in {_launch_folder()}"
        lines.append(("Output", f"{format_text} → {where}"))
        lines.append(("Expert", expert_changes_text(len(form.expert))))
        return lines

    # ── Cancel (owner decision 1; 01 §7.2) ────────────────────────────

    def action_cancel_run(self) -> None:
        """Ctrl+G / action bar: stop the run at its next safe point.

        Available until output writing starts. Cancelling a consent or
        clearing-spend dialog, or the validation review, through ^G is the
        same as its Cancel button, except that it is recorded as the
        visible cancel (``cancel_before_run``).
        """
        if self._run_state not in ("validating", "running"):
            return
        if self._run_stage == "output":
            self.notify(
                "Cancel unavailable: the run is writing outputs and finishes under the normal privacy rules.",
                title=status_text("running"),
                timeout=4,
            )
            return
        if self.cancel_requested:
            return
        self._cancel_origin = "button"
        self.request_cancel()
        screen = self.screen
        if isinstance(screen, ConfirmScreen) and screen.confirm_label != "Quit":
            screen.dismiss(False)
        elif isinstance(screen, ValidationModal):
            screen.dismiss(False)
        self._refresh_action_bar()

    def _record_visible_cancel(self, prompt: str) -> None:
        """Telemetry for ^G, recorded where the cancel took effect (worker-safe)."""
        if self._cancel_origin == "button":
            action_cancelled(self._telemetry_action(), prompt)

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
        if badge.state == "ready" and self._blockers:
            # Idle with blockers: say what the action bar says, not READY.
            badge = RunBadge("notready")
        mode = self._run_mode or self._analysis_mode()
        lines = [
            f"[$text-muted]Mode[/]    {escape_markup(labels.text_for(labels.ANALYSIS_MODE, mode))}",
            f"[$text-muted]Preset[/]  {escape_markup(_preset_display(self.form.preset))}",
        ]
        if self._run_started_at is not None and self._run_state == "running":
            elapsed = _elapsed_since(self._run_started_at)
            lines.append(f"[$text-muted]Elapsed[/] {elapsed:.0f} s")
            stage = _RUN_STAGE_LABELS.get(self._run_stage or "")
            if stage:
                lines.append(f"[$text-muted]Stage[/]   {escape_markup(stage)}")
        text = "\n".join(lines)
        key = (badge, text)
        if key == self._last_status_text:
            self._refresh_action_bar()  # Elapsed time and cancel state move on.
            return  # Nothing changed; skip the repaint.
        try:
            self.query_one("#run_status_badge", StatusBadge).set_status(badge.state, badge.detail)
            self.query_one("#run_status_detail", Static).update(text)
            self._last_status_text = key
        except NoMatches:
            pass
        self._refresh_action_bar()
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
            elif isinstance(focused, OptionList):
                context = "choose"
            elif isinstance(focused, Checkbox):
                context = "toggle"
            elif isinstance(focused, (Button, CollapsibleTitle)):
                context = "button"
            elif isinstance(focused, (Tabs, ModeSwitch)):
                context = "tabs"
            elif isinstance(focused, Log):
                context = "log"
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
        # Focus decides the visible step: a field focused in another step
        # (a launch blocker, a restored focus, a test) brings its step up, and
        # a setup field focused while the <110 results view is open closes it.
        step = self._step_of(event.widget)
        if step is not None and (step != self._current_step or self._results_view_open()):
            self._show_step(step, focus=False)
        if step is not None and self._log_view_open():
            self.action_show_log()
        self._mark_field_pair(event.widget, True)
        self._update_key_bar()
        self._place_toasts()

    @staticmethod
    def _mark_field_pair(widget: Any, focused: bool) -> None:
        """Reverse-video the label of the focused field's pair (02 §4.4).

        Replaces ``.field-pair:focus-within``: Textual restyles the whole
        subtree of a ``:focus-within`` ancestor on every focus change (03 §2),
        while this restyles one label. Survives NO_COLOR like the rule did.
        """
        for node in widget.ancestors_with_self:
            if node.has_class("form-section"):
                return
            if node.has_class("field-pair"):
                for label in node.query_children(".field-label"):
                    label.set_class(focused, "-pair-focus")
                return

    def on_descendant_blur(self, event: Any) -> None:
        self._mark_field_pair(event.widget, False)
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

    # ── Toast policy (01 §5.3) ────────────────────────────────────────

    def _on_notify(self, event: Any) -> None:
        """At most two toasts; none over a modal; never over the focused field.

        Textual 7.5 has no public per-toast dismiss, so the cap uses the
        private ``_unnotify`` here and nowhere else.
        """
        event.prevent_default()  # App._on_notify would add it uncapped.
        if isinstance(self.screen, ModalScreen):
            self._queued_toasts.append((time.monotonic(), event.notification))
            return
        self._show_toast(event.notification)

    def _show_toast(self, notification: Any) -> None:
        live = list(self._notifications)
        while len(live) >= self.MAX_TOASTS:
            self._unnotify(live.pop(0), refresh=False)
        self._place_toasts()
        self._notifications.add(notification)
        self._refresh_notifications()

    def _flush_queued_toasts(self) -> None:
        if isinstance(self.screen, ModalScreen):
            return
        now = time.monotonic()
        while self._queued_toasts:
            raised_at, notification = self._queued_toasts.popleft()
            if now - raised_at <= self.QUEUED_TOAST_MAX_AGE_S:
                self._show_toast(notification)

    def pop_screen(self) -> Any:
        result = super().pop_screen()
        self.call_after_refresh(self._flush_queued_toasts)
        return result

    def _place_toasts(self) -> None:
        """Toasts sit top right; they move to the bottom when the focus is up there."""
        main = getattr(self, "_main_screen", None)
        if main is None or not self.screen_stack:  # no stack while shutting down
            return
        focused = self.focused
        bottom = False
        if focused is not None and focused.screen is main:
            region = focused.region
            width = self.size.width
            top_area = Region(max(width - TOAST_WIDTH - 1, 0), 0, TOAST_WIDTH + 1, TOAST_AREA_ROWS)
            bottom = region.overlaps(top_area)
        # On the rack, not the Screen: a Screen class change restyles every
        # widget (a 100+ ms Tab), a rack class change restyles the rack.
        try:
            rack = main.get_child_by_type(ToastRack)
        except NoMatches:
            return
        if rack.has_class("-bottom") != bottom:
            rack.set_class(bottom, "-bottom")

    # ── Run lifecycle (UI) ────────────────────────────────────────────

    def _set_form_locked(self, locked: bool, *, restore_focus: bool = True) -> None:
        """Lock the form while a run is active, and say why (01 §5.2).

        Unlocking puts focus back on the field that had it, unless the caller
        moves focus itself (``restore_focus=False``: a blocker jump).
        """
        if locked and self._focus_before_lock is None:
            focused = self.focused
            if focused is not None and self._step_of(focused) is not None:
                self._focus_before_lock = focused
        for step in STEPS:
            try:
                body = self.query_one(f"#{step.container_id}")
            except NoMatches:
                continue
            if body.disabled != locked:
                body.disabled = locked
        try:
            note = self.query_one("#form_lock_note", Static)
        except NoMatches:
            return
        note.update(
            f"{status_glyph('running')} Form locked while the run is active · ^G cancels"
            if locked
            else ""
        )
        note.set_class(not locked, "hidden")
        if not locked:
            widget, self._focus_before_lock = self._focus_before_lock, None
            if widget is None or not widget.is_attached or not restore_focus:
                return
            if self._results_view_open():
                # <110: Results stay open; ^T goes back to this field.
                self._setup_focus = widget
            else:
                if self.focused is None and self._step_of(widget) == self._current_step:
                    widget.focus()
                # Unlocked from a dialog's dismiss callback (e.g. Cancel on the
                # validation review): the main screen resumes after this with
                # the focus it remembered, which the lock had disabled, so it
                # came back with nothing focused (PR 6). Check again after it.
                self.call_after_refresh(self._restore_unlocked_focus, widget)

    def _restore_unlocked_focus(self, widget: Any) -> None:
        if (
            self.screen is getattr(self, "_main_screen", None)
            and self.focused is None
            and widget.is_attached
            and self._step_of(widget) == self._current_step
        ):
            widget.focus()

    def _set_run_button(self, label: str, disabled: bool) -> None:
        try:
            button = self.query_one("#btn_run", Button)
        except NoMatches:
            return
        button.disabled = disabled
        button.label = label

    def _begin_validation_ui(self) -> None:
        """Switch UI into the pre-run validation state (app thread only).

        Locks the form (and the run button, to block double launches) and
        shows a distinct ``Validating`` badge, but deliberately does NOT start
        the elapsed clock or the ``running`` badge: execution has not begun
        yet, and a ``ValidationModal`` may still be awaiting the user's decision.
        """
        self._run_state = "validating"
        self._run_started_at = None
        self._run_mode = "privacy-sweep" if self._privacy_sweep_enabled() else self._analysis_mode()
        self._set_run_button("Validating…", True)
        self._set_form_locked(True)
        if self._elapsed_timer is not None:
            self._elapsed_timer.stop()
            self._elapsed_timer = None
        self._set_copy_path(None, "")
        self._set_has_outcome(False)
        self._refresh_run_status()
        self._save_session()

    def _begin_run_ui(self) -> None:
        """Switch UI into the running state (app thread only)."""
        self._run_state = "running"
        self._run_started_at = time.monotonic()
        self._run_stage = None
        self._run_mode = "privacy-sweep" if self._privacy_sweep_enabled() else self._analysis_mode()
        self._set_run_button("Running…", True)
        self._set_form_locked(True)
        if self._elapsed_timer is not None:
            self._elapsed_timer.stop()
        self._elapsed_timer = self.set_interval(1.0, self._refresh_run_status)
        # Restored-value markers clear once a run uses them (01 §7.3).
        self.form.restored.clear()
        self._not_restored.clear()
        self._refresh_run_status()
        self._schedule_shell_refresh()
        self._save_session()
        # <110 columns: the status view opens when the run starts (01 §4.3 rule 5).
        self._open_results_view(focus_copy=False)

    _OUTCOME_MESSAGES = {
        "success": "The run finished and the report was written.",
        "withheld": "Privacy rules withheld publication · see Results",
        "blocked": "The run was blocked · see Results",
        "error": "The run failed · see Results",
        "cancelled": "Nothing was written.",
    }

    def _end_run_ui(
        self,
        state: str,
        summary_markup: str,
        badge: Optional[str] = None,
        verdict: Optional[str] = None,
        *,
        copy_path: Optional[str] = None,
        copy_label: str = "Report",
        message: str = "",
    ) -> None:
        """Restore UI after a run and publish the last-run summary (app thread only).

        ``state`` is the app run state (success/error/blocked). ``badge``
        overrides its status-language badge (``withheld`` for a privacy
        denial) and ``verdict`` adds a second badge (``compliant`` or
        ``warning``) next to DONE. ``copy_path`` is the whole path ^Y copies
        and the results view shows (the report, or a log); ``message`` is the
        action bar's one-line outcome. Outcomes are not toasted: the action
        bar and the results card already say them (01 §5.3 rule 5).
        """
        self._run_state = state
        self._outcome_badge = badge
        self._outcome_message = message or self._OUTCOME_MESSAGES.get(badge or state, "")
        self._set_copy_path(copy_path, copy_label)
        self._set_has_outcome(True)
        self._run_stage = None
        if self._elapsed_timer is not None:
            self._elapsed_timer.stop()
            self._elapsed_timer = None
        elapsed = None
        if self._run_started_at is not None:
            elapsed = _elapsed_since(self._run_started_at)
        self._run_started_at = None
        self._set_form_locked(False)
        self._set_run_button(f"Run {self._run_label()} ^R", False)
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
        self._schedule_shell_refresh()
        # <110 columns: results open when the run ends, focus on Copy path
        # (01 §4.3 rule 5); at 110+ focus stays and the action bar announces it.
        if self.focused is None or self._results_view_open() or self._step_of(self.focused) is None:
            self._open_results_view(focus_copy=True)

    def _reset_run_ui(self, *, restore_focus: bool = True) -> None:
        """Re-enable the run controls after an aborted launch (app thread only)."""
        self._run_state = "idle"
        self._outcome_badge = None
        if self._elapsed_timer is not None:
            self._elapsed_timer.stop()
            self._elapsed_timer = None
        self._run_started_at = None
        self._set_form_locked(False, restore_focus=restore_focus)
        self._set_run_button(f"Run {self._run_label()} ^R", False)
        self._outcome_message = ""
        self._set_has_outcome(False)
        self._refresh_run_status()
        self._schedule_shell_refresh()

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
        """Report an invalid launch and return UI to idle (worker-safe).

        ``block_reason`` is a closed LAUNCH_BLOCK_REASONS value recorded as
        ``launch_blocked``; ``message`` never reaches telemetry.
        ``title_state`` picks the status-language toast title (tui.status).
        A readiness blocker (``focus_id``) is not toasted: the action bar
        names it and focus moves to its field (01 §5.3).
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
        if not focus_id:
            self.call_from_thread(
                self.notify, message, title=status_text(title_state), severity="error", markup=False
            )
        if focus_id:
            # Ctrl+R from any step: show the blocker's step and focus it; the
            # action bar names it (the same launch_blockers result).
            self.call_from_thread(partial(self._reset_run_ui, restore_focus=False))
            self.call_from_thread(self._focus_field, focus_id)
        else:
            self.call_from_thread(self._reset_run_ui)

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

    def _quick_pick_files(self, root: Optional[str] = None) -> List[str]:
        """CSV files from the working directory and known data folders.

        De-duplicated with a set (the old list check was O(F²)) and sorted
        newest first, so the capped quick-pick list shows recent files.
        Paths are relative to ``root`` (default: the working directory), as
        before; the picker calls this on a thread with the cwd at Ctrl+O.
        """
        base = root or os.getcwd()
        seen: set = set()
        matches: List[str] = []
        for pattern in QUICK_PICK_PATTERNS:
            for match in glob.glob(pattern, root_dir=base):
                if match not in seen:
                    seen.add(match)
                    matches.append(match)

        def newest_first(path: str) -> tuple:
            try:
                return (-os.stat(os.path.join(base, path)).st_mtime_ns, path)
            except OSError:
                return (0, path)

        matches.sort(key=newest_first)
        return matches

    def _resolve_csv_path(self, raw_path: str, *, quiet: bool = False) -> Optional[str]:
        """Normalize and validate a CSV path from manual entry or browse.

        ``quiet`` skips the not-found notice, log line and telemetry; callers
        that only need the same normalization as the header load (entity
        loading, D8) use it so one bad path is reported once. The notice is
        inline under the path field, not a toast (01 §5.3).
        """
        csv_path = raw_path.strip()
        if not csv_path:
            return None
        if not os.path.isfile(csv_path):
            if quiet:
                return None
            self._emit_dataset_load("not_found", csv_path)
            self._set_csv_meta(
                Text(
                    f"{status_glyph('error')} Not found: {csv_path}\n"
                    "  Check the spelling, or press Ctrl+O to browse."
                ),
                error=True,
            )
            self.query_one("#log_output").write(f"CSV file not found: {csv_path}\n")
            return None
        return csv_path

    @staticmethod
    def _csv_signature(path: str) -> Optional[tuple]:
        """(path as typed, realpath, mtime_ns, size) of a CSV, or None if unreadable.

        One ``stat()``. The typed path is part of it because the entity loader
        keys its results by the ``#csv_path`` text.
        """
        try:
            stat = os.stat(path)
        except OSError:
            return None
        return (path, os.path.realpath(path), stat.st_mtime_ns, stat.st_size)

    def _try_load_csv_from_path_input(self, raw_path: Optional[str] = None, *, focus_next: bool = False) -> None:
        """Load headers when the user submits or leaves the CSV path field.

        A path whose (realpath, mtime, size) matches the last successful load
        is a no-op: no header re-read and no widget repopulation (03 §3). A
        changed file reloads as before.
        """
        if raw_path is None:
            raw_path = self.form.csv_path
        signature = self._csv_signature(raw_path.strip()) if raw_path.strip() else None
        if signature is not None and signature == getattr(self, "_loaded_csv_signature", None):
            if focus_next:
                self._focus_next_empty_field()
            return
        csv_path = self._resolve_csv_path(raw_path)
        if csv_path:
            self.load_csv_headers(csv_path, focus_next=focus_next)

    def load_csv_headers(self, file_path, announce: bool = True, *, focus_next: bool = False):
        """Load CSV headers into the form; mounted widgets follow it.

        ``focus_next`` (Enter in the path, or a picker choice) then moves focus
        to the next empty every-run field: Entity column, else Target entity
        (01 §4.3 rule 2). ``announce`` is kept for callers; the meta line under
        the path is the confirmation, so a load is never toasted (01 §5.3).
        """
        headers_read = False
        try:
            resolved = self._resolve_csv_path(file_path)
            if not resolved:
                return
            file_path = resolved
            # Headers plus a small sample: enough to tell numeric columns
            # (Metric/Total list them first) without reading the file.
            sample = pd.read_csv(file_path, nrows=NUMERIC_SAMPLE_ROWS)
            cols = [str(c) for c in sample.columns.tolist()]
            headers_read = True
            numeric = [
                str(c)
                for c in sample.columns
                if pd.api.types.is_numeric_dtype(sample[c]) and not pd.api.types.is_bool_dtype(sample[c])
            ]
            self._emit_dataset_load("loaded", file_path)
            self.csv_columns = cols
            form = self.form
            if form.csv_path.strip() != file_path:
                # The file being loaded is the form's file (picker, callers).
                form.csv_path = file_path
            # Repopulating the form repaints once, not once per field.
            with self.batch_update():
                form.set_columns(cols, numeric)
                self._csv_loaded = True
                available = set(cols)
                # Still-valid choices survive a reload; others are cleared.
                for name in COLUMN_FIELDS:
                    if getattr(form, name) not in available:
                        setattr(form, name, None)
                # D4: restored session column choices win over smart defaults.
                self._apply_pending_session_columns(cols)
                # Smart defaults for fields that are still empty. The rate
                # Total column has none (owner decision 4): it is the
                # clearing-spend basis and must always be an explicit choice.
                for name, column in SMART_DEFAULTS:
                    if getattr(form, name) is None and column in available:
                        setattr(form, name, column)
                self._refresh_column_selects()
                self._update_csv_meta(file_path, cols, numeric)

            # A new file with an unchanged entity column posts no change, so
            # refresh the entity values explicitly. Requests for values
            # already loaded or in flight are no-ops.
            if form.entity_col:
                self.load_unique_entities(form.entity_col)
            self._loaded_csv_signature = self._csv_signature(file_path)
            self._schedule_shell_refresh()
            if focus_next:
                self._focus_next_empty_field()
            self.set_timer(STEP_PREWARM_DELAY_S, self._prewarm_next_step)

        except Exception as e:
            self._loaded_csv_signature = None
            if not headers_read:
                self._emit_dataset_load("header_read_failed", file_path)
            self.query_one("#log_output").write(f"Error reading CSV headers: {e}\n")
            first_line = str(e).splitlines()[0] if str(e) else type(e).__name__
            self._set_csv_meta(
                Text(
                    f"{status_glyph('error')} Can't read this file as CSV: {first_line}\n"
                    "  Check that it is comma-separated text."
                ),
                error=True,
            )

    def _focus_next_empty_field(self) -> None:
        """After a load: Entity column if it has no value, else Target entity.

        Target entity is disabled while its values load; the focus then waits
        for them (``_apply_unique_entities``) with step 2 already shown.
        """
        if not self.form.entity_col:
            self._focus_field("entity_col")
            return
        if self.entity_values_loading:
            self._focus_target_when_loaded = True
            self._show_step("entity", focus=False)
            return
        self._focus_field("entity_filter" if self._entity_index is not None else "entity_name")

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

    def _set_csv_meta(self, content: Any, *, error: bool = False) -> None:
        self._csv_meta = content
        self._csv_meta_error = error
        self._show_csv_meta()

    def _show_csv_meta(self) -> None:
        widget = self._widget("csv_meta", Static)
        if widget is None:
            return
        widget.update(self._csv_meta)
        widget.set_class(getattr(self, "_csv_meta_error", False), "-error")

    def _update_csv_meta(self, file_path: str, cols: List[str], numeric: Iterable[str] = ()) -> None:
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
        numeric_set = set(numeric)
        listed = [f"{c}#" if c in numeric_set else c for c in cols[:12]]
        preview = " · ".join(listed) + (" …" if len(cols) > 12 else "")
        # Literal text: file and column names come from the operator's data.
        self._set_csv_meta(
            Text(
                f"{status_glyph('success')} {os.path.basename(file_path)} · "
                f"{len(cols)} columns · {len(numeric_set)} numeric (#) · {size_text}\n{preview}"
            )
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter in text inputs."""
        if event.input.id == "csv_path":
            self.form.csv_path = event.input.value
            self._try_load_csv_from_path_input(event.input.value, focus_next=True)

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
    # Presets / expert settings
    # ──────────────────────────────────────────────────────────────────

    @property
    def preset_workflow(self) -> PresetWorkflow:
        """The shared preset workflow (cached, re-parsed when presets change)."""
        override = self.__dict__.get("_preset_workflow_override")
        if override is not None:
            return override
        return self._preset_catalog.workflow

    @preset_workflow.setter
    def preset_workflow(self, value: PresetWorkflow) -> None:
        self.__dict__["_preset_workflow_override"] = value

    def load_presets(self):
        """Load available presets through the shared preset workflow."""
        presets = self.preset_workflow.list_presets()
        self._preset_options = [(preset, preset) for preset in presets] or [("standard", "standard")]
        default_preset = self._default_preset()
        self.form.preset = default_preset
        # Do not refresh privacy_release_mode here: load_presets runs before
        # session restore, which must be able to restore Verified safe
        # coverage. User-driven preset changes refresh it (_on_preset_changed).

    def _default_preset(self) -> Optional[str]:
        values = [value for _, value in self._preset_options]
        if DEFAULT_PRESET_NAME in values:
            return DEFAULT_PRESET_NAME
        return values[0] if values else None

    def _preset_selected(self, value: Optional[str]) -> None:
        """The preset Select changed. With expert changes, ask first (01 §8.2 item 3)."""
        form = self.form
        if value is None or value == form.preset:
            return
        if not form.expert:
            form.preset = value
            return
        count = len(form.expert)
        old = form.preset

        def answered(reset: Optional[bool]) -> None:
            if reset:
                form.expert = {}
                form.preset = value
            else:
                self._sync_widget("preset")  # Back to the current preset.

        self.push_screen(
            ConfirmScreen(
                f"Change the preset to {value}?\n\n"
                f"You have {expert_changes_text(count)} on {old}. Switching resets "
                f"them to {value}'s values.",
                confirm_label=f"Reset and use {value}",
                cancel_label="Keep current preset",
                variant="primary",
            ),
            answered,
        )

    def _on_preset_changed(self, old: Optional[str], new: Optional[str]) -> None:
        if new:
            if self.form.expert:
                # Programmatic change: entries the new preset already has go.
                self.form.expert = rebase_diff(
                    self.ADVANCED_FIELD_SPECS, self.form.expert, self._expert_preset_values(new)
                )
            if not getattr(self, "_tui_bootstrapping", False):
                self._refresh_privacy_release_mode_from_config()
        self._refresh_run_status()

    def _preset_posture(self, preset: Optional[str]) -> Optional[str]:
        if not preset:
            return None
        try:
            data = self.preset_workflow.load_preset_data(preset)
        except Exception:
            return None
        posture = data.get("compliance_posture") if isinstance(data, dict) else None
        return str(posture) if posture else None

    def _effective_preset_posture(self) -> Optional[str]:
        """The posture a run will use: the expert file inherits the preset's (01 §8.2)."""
        return self._preset_posture(self.form.preset)

    def _posture_line(self) -> Text:
        posture = self._effective_preset_posture()
        if not posture:
            return Text("—")
        label = labels.label_for(labels.POSTURE, posture)
        glyph = status_glyph("success") if posture == "strict" else status_glyph("warning")
        changes = len(self.form.expert)
        source = "from preset" if not changes else f"from preset + {expert_changes_text(changes, short=True)}"
        return Text(f"{glyph} {label.primary} — {label.why}\n{source} · F1 explains every preset")

    def _preset_blurb_text(self, preset_name: Optional[str]) -> Text:
        if not preset_name:
            return Text("")
        try:
            data = self.preset_workflow.load_preset_data(preset_name)
            description = labels.strip_preset_description(str(data.get("description") or "")) if isinstance(data, dict) else ""
        except Exception:
            description = ""
        mark = "  ↺ restored" if "preset" in self.form.restored else ""
        return Text(description + mark)

    def _warn_missing_widget(self, widget_id: str) -> None:
        logging.getLogger(__name__).warning("Advanced widget not found: %s", widget_id)
        self.notify(
            f"Couldn't show the advanced setting {widget_id}; the preset value is used.",
            title="Advanced optimization",
            severity="warning",
            timeout=4,
            markup=False,
        )

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
        raw_data = self.preset_workflow.load_preset_data(preset_name)
        if not raw_data:
            return {}

        try:
            return self._preset_catalog.resolved_config(preset_name)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Falling back to raw preset data for advanced parameters: %s",
                exc,
            )
            return raw_data

    def _expert_preset_values(self, preset: Optional[str]) -> Dict[str, Any]:
        """Preset value per expert field (None = engine default), cached per preset."""
        if not preset:
            return {}
        if preset not in self._expert_preset_cache:
            data = self._load_advanced_parameter_data(preset)
            self._expert_preset_cache[preset] = {
                spec.widget_id: self._read_field_value_from_preset(data, spec) for spec in self.ADVANCED_FIELD_SPECS
            }
        return dict(self._expert_preset_cache[preset])

    def set_expert_value(self, widget_id: str, value: Any) -> Dict[str, Any]:
        """One Expert screen edit: update the in-memory diff and return it."""
        self.form.expert = diff_with(
            self.ADVANCED_FIELD_SPECS, self.form.expert, widget_id, value, self._expert_preset_values(self.form.preset)
        )
        return dict(self.form.expert)

    def reset_expert(self) -> None:
        self.form.expert = {}

    def _expert_override_data(self, values: Mapping[str, Any]) -> Dict[str, Any]:
        return self._override_builder.read_from_mapping(values)

    def _write_expert_override(self) -> Optional[str]:
        """Write the expert diff for this run (stage 1), with the current preset's posture.

        Owner decision 2: the file goes to the launch folder and stays there.
        It is regenerated from the current preset on every run, so its posture
        can never be stale (D2).
        """
        yaml_data = self._expert_override_data(self.form.expert)
        if not yaml_data:
            return None
        posture = self._preset_posture(self.form.preset) or "strict"
        try:
            path = self.preset_workflow.write_override_file(yaml_data, posture=posture)
        except Exception:
            advanced_override("failed")
            raise
        advanced_override("applied")
        return str(path)

    def _collect_advanced_override_data(self) -> Dict[str, Any]:
        """Preset values with the expert diff on top (what Export writes)."""
        values = effective_values(
            self.ADVANCED_FIELD_SPECS, self.form.expert, self._expert_preset_values(self.form.preset)
        )
        return self._expert_override_data(values)

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
        handler.setFormatter(_log_view_formatter())

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

    def action_toggle_advanced(self) -> None:
        """F8: open the Expert settings screen (again: close it)."""
        if isinstance(self.screen, ExpertScreen):
            self.screen.dismiss(None)
            return
        if isinstance(self.screen, ModalScreen):
            return
        surface_viewed("advanced")
        preset = self.form.preset
        posture = self._effective_preset_posture()
        self.push_screen(
            ExpertScreen(
                specs=self.ADVANCED_FIELD_SPECS,
                preset=preset,
                preset_values=self._expert_preset_values(preset),
                diff=self.form.expert,
                debug=self.form.debug,
                posture_text=labels.text_for(labels.POSTURE, posture) if posture else "—",
            )
        )

    action_open_expert = action_toggle_advanced

    def action_export_advanced(self) -> None:
        """F9: export the expert settings (preset values plus your changes)."""
        self.export_advanced_overrides()

    def export_advanced_overrides(self) -> Optional[str]:
        """Write ``exported_<preset>_overrides.yaml`` to the launch folder; return its full path."""
        yaml_data = self._collect_advanced_override_data()
        if not yaml_data:
            advanced_override("empty")
            self.notify(
                "No expert values to export: this preset sets none and nothing was changed.",
                title="Expert settings",
                severity="warning",
                timeout=4,
            )
            return None
        posture = self._preset_posture(self.form.preset) or "strict"
        content = {**yaml_data, "version": "3.0", "compliance_posture": posture}
        try:
            export_path = self.preset_workflow.export_override_file(
                content, preset_name=str(self.form.preset or "custom")
            )
            full_path = os.path.abspath(str(export_path))
            self.notify(
                f"Expert settings exported to {full_path}",
                title="Expert settings exported",
                severity="information",
                timeout=6,
                markup=False,
            )
            advanced_override("exported")
            return full_path
        except Exception as e:
            advanced_override("export_failed")
            self.notify(
                f"Couldn't export the expert settings. Why: {e}. "
                "Next: check that the folder is writable, then export again (F9).",
                title=status_text("error"),
                severity="error",
                timeout=6,
                markup=False,
            )
            return None

    # ──────────────────────────────────────────────────────────────────
    # Events / actions
    # ──────────────────────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id
        if button_id == "btn_browse_csv":
            self.action_open_file()
        elif button_id == "btn_run":
            self.run_analysis()
        elif button_id == "btn_expert":
            self.action_toggle_advanced()
        elif button_id == "btn_clear_restored":
            self.action_clear_restored()
        elif button_id == "btn_copy_path":
            self.action_copy_path()
        elif button_id == "btn_show_log":
            self.action_show_log()

    def action_open_file(self) -> None:
        """Open the CSV picker modal (Ctrl+O)."""
        if self._run_state in ("validating", "running"):
            return  # The form is locked while a run is active.

        def on_picked(path: Optional[str]) -> None:
            if not path:
                return
            self.form.csv_path = path
            self.load_csv_headers(path, focus_next=True)

        cwd = os.getcwd()
        self.push_screen(
            CsvPickerScreen(quick_pick_source=partial(self._quick_pick_files, cwd)), on_picked
        )

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
                    self._cancel_origin = "quit"
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
        return self.form.mode

    def set_analysis_mode(self, mode: str) -> None:
        self.form.mode = mode

    def _privacy_sweep_enabled(self) -> bool:
        return self.form.effective_sweep

    def _privacy_release_mode_value(self) -> str:
        value = self.form.release_mode
        return value if value in _PRIVACY_RELEASE_MODE_VALUES else PrivacyReleaseMode.COMPLETE_OUTPUT.value

    def _privacy_release_mode(self) -> PrivacyReleaseMode:
        """The selected PrivacyReleaseMode enum for share requests."""
        try:
            return PrivacyReleaseMode(self._privacy_release_mode_value())
        except ValueError:
            return PrivacyReleaseMode.COMPLETE_OUTPUT

    def _privacy_values(self) -> Dict[str, Any]:
        """Privacy request fields from the form.

        Includes rule strategy, release mode (share only), and compliance
        attestations. Rate analysis never receives a hidden Verified safe
        coverage selection from the release-mode field.
        """
        form = self.form
        values: Dict[str, Any] = {
            "privacy_rule_strategy": (
                PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE
                if form.effective_sweep
                else PrivacyRuleStrategy.SELECT_BY_PEER_COUNT
            ),
            "is_anonymized_aggregated_merchant_spend": form.merchant_spend,
            "citibank_entity_name": (form.citibank_entity or "").strip() or None,
            "citi_competitor_receives_output": form.citi_competitor,
        }
        if form.mode == "share":
            values["privacy_release_mode"] = self._privacy_release_mode()
        else:
            # Do not let a hidden verified-safe-coverage value reach a rate
            # request. Leave None so configuration resolution stays clear.
            values["privacy_release_mode"] = None
        return values

    def _refresh_privacy_release_mode_from_config(self, config_file: Optional[str] = None) -> None:
        """Set the release mode the resolved preset (and config file) declares."""
        try:
            mode_value = self._preset_catalog.resolved_release_mode(self.form.preset, config_file)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Could not resolve privacy_release_mode from configuration: %s",
                exc,
            )
            return
        self.form.release_mode = mode_value

    def action_show_help(self) -> None:
        """Show help (F1): keys and the preset guide."""
        surface_viewed("preset_help")
        self.push_screen(PresetHelpScreen())

    # Entity value loading runs in a background worker. These track, on the UI
    # thread only, which (csv_path, column) is in flight and which one the
    # current values were built from. The chosen entity lives in the form.
    _entity_load_key: Optional[tuple] = None
    _entity_options_key: Optional[tuple] = None
    _entity_values: List[str] = []
    # Large-list mode (more than ENTITY_SELECT_MAX values): the filter picker
    # replaces the Select and the full value set lives in _entity_index.
    _entity_index: Optional[EntityIndex] = None

    @property
    def _entity_large(self) -> bool:
        return self._entity_index is not None

    @property
    def entity_choices(self) -> List[str]:
        """Every target-entity value currently offered, in either widget."""
        if self._entity_index is not None:
            return list(self._entity_index.values)
        return list(self._entity_values)

    def _target_entity_for_run(self) -> tuple:
        """Return (target entity or None, blocking message or None) for a run."""
        form = self.form
        if self._entity_index is None:
            return form.entity, None
        text = form.entity_filter
        if not text.strip():
            return None, None  # blank = peer-only, as with the Select
        if text in self._entity_index.value_set:
            return text, None
        return None, (
            f"Target entity not found in {form.entity_col}. Pick a value from the list, "
            "or clear the filter to compare with the peer group only."
        )

    def _entity_source_key(self) -> Optional[tuple]:
        """The (csv_path, entity column) the form currently points at."""
        csv_path = self._resolve_csv_path(self.form.csv_path, quiet=True)
        if not csv_path or not self.form.entity_col:
            return None
        return (csv_path, self.form.entity_col)

    def load_unique_entities(self, column_name) -> None:
        """Load the column's distinct values for both entity choosers, off the UI thread.

        The CSV read happens in ``_load_unique_entities_worker``; this method
        only flips the choosers into their loading state and starts the
        worker. A request for the (path, column) that is already loading or
        already shown is a no-op.
        """
        # D8: the same normalization as the header load, so a path with
        # surrounding spaces loads entities as well as headers.
        csv_path = self._resolve_csv_path(self.form.csv_path, quiet=True)
        if not csv_path:
            return
        key = (csv_path, column_name)
        if key == self._entity_load_key:
            return
        if self._entity_load_key is None and key == self._entity_options_key:
            return
        self._entity_load_key = key
        if key != self._entity_options_key:
            # Values from another file/column are meaningless for this one.
            # The chosen entity stays in the form, pending, until they land.
            self._entity_values = []
            self._entity_index = None
            self._entity_options_key = None
        self._set_entity_loading(True)
        with self.batch_update():
            self._sync_entity_choosers()
        self._load_unique_entities_worker(csv_path, column_name)

    def _set_entity_loading(self, loading: bool) -> None:
        for chooser_id, step in (("entity_chooser", "entity"), ("citibank_chooser", "privacy")):
            if step not in self._ready_steps:
                continue
            try:
                self.query_one(f"#{chooser_id}", EntityChooser).set_loading(loading)
            except NoMatches:
                continue

    @work(thread=True, exclusive=True, group="entity_values", exit_on_error=False)
    def _load_unique_entities_worker(self, csv_path: str, column_name: str) -> None:
        """Read the entity column on a worker thread and hand results back."""
        worker = get_current_worker()
        values: Optional[List[str]] = None
        index: Optional[EntityIndex] = None
        error: Optional[Exception] = None
        try:
            values = read_unique_entity_values(csv_path, column_name)
            if len(values) > ENTITY_SELECT_MAX:
                index = EntityIndex(values)  # sorted/casefolded off the UI thread
        except Exception as exc:  # reported on the UI thread like before
            error = exc
        if worker.is_cancelled:
            return  # superseded by a newer request (exclusive group) or exit
        try:
            self.call_from_thread(
                self._apply_unique_entities, (csv_path, column_name), values, error, index
            )
        except RuntimeError:
            pass  # App loop already gone (shutdown); nothing to update.

    def _apply_unique_entities(
        self,
        key: tuple,
        values: Optional[List[str]],
        error: Optional[Exception],
        index: Optional[EntityIndex] = None,
    ) -> None:
        """Apply a finished entity load on the UI thread, unless it is stale.

        Up to ENTITY_SELECT_MAX values fill the Selects. Above that, the filter
        picker replaces them and the full value set stays in an ``EntityIndex``.
        A chosen entity that is not in the new values is cleared.
        """
        if getattr(self, "_exit", False):
            return
        if key != self._entity_load_key:
            return  # A newer request owns the loading state.
        self._entity_load_key = None
        try:
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
            form = self.form
            if len(values) > ENTITY_SELECT_MAX:
                self._entity_index = index or EntityIndex(values)
                self._entity_values = []
                value_set = self._entity_index.value_set
                if form.entity is not None and form.entity in value_set and not form.entity_filter:
                    form.entity_filter = form.entity
                if form.entity_filter and form.entity_filter not in value_set:
                    form.entity_filter = form.entity_filter  # kept: readiness names it
                form.entity = form.entity_filter if form.entity_filter in value_set else None
            else:
                self._entity_index = None
                self._entity_values = list(values)
                value_set = set(values)
                form.entity_filter = ""
                if form.entity not in value_set:
                    form.entity = None
            if form.citibank_entity is not None and form.citibank_entity not in set(self.entity_choices):
                form.update(citibank_entity=None, citibank_filter="")
            self._entity_options_key = key
        finally:
            # Loaded, failed or dropped: the entity widgets must be usable again.
            self._set_entity_loading(False)
            with self.batch_update():
                self._sync_entity_choosers()
            self._schedule_shell_refresh()
            if getattr(self, "_focus_target_when_loaded", False):
                self._focus_target_when_loaded = False
                focused = self.focused
                if self._current_step == "entity" and (focused is None or self._step_of(focused) == "entity"):
                    self._focus_field("entity_filter" if self._entity_index is not None else "entity_name")

    def _cancel_entity_load(self) -> None:
        """Abandon an in-flight entity load and leave the choosers usable."""
        if self._entity_load_key is None:
            return
        self._entity_load_key = None
        self.workers.cancel_group(self, "entity_values")
        self._set_entity_loading(False)

    @property
    def entity_values_loading(self) -> bool:
        """True while a background entity load has not been applied yet."""
        return self._entity_load_key is not None

    @property
    def entity_selection_pending(self) -> bool:
        """True while a chosen entity waits for its reload to be re-applied."""
        return self.entity_values_loading and (
            self.form.entity is not None or bool(self.form.entity_filter.strip())
        )

    # ──────────────────────────────────────────────────────────────────
    # Analysis execution
    # ──────────────────────────────────────────────────────────────────

    def _collect_run_inputs(self, *, resolve_config: bool = True) -> RunInputs:
        """Snapshot every form value a run attempt needs (UI thread only, D7).

        Reads ``FormState``, never a widget. ``resolve_config=False`` is the
        readiness snapshot for the action bar, rail and Review step: the same
        values, without writing the expert override file or looking up the
        posture (no side effects, no file writes). With ``resolve_config``, a
        non-empty expert diff is written once through
        ``PresetWorkflow.write_override_file`` with the current preset's
        posture, and consent follows the effective posture (D2).
        """
        form = self.form
        preset = form.preset
        config = self._write_expert_override() if resolve_config and form.expert else None
        posture = (
            self._effective_compliance_posture(preset, config)
            if resolve_config and (preset or config)
            else None
        )
        mode = form.mode
        entity, entity_error = self._target_entity_for_run()
        common: Dict[str, Any] = {
            "mode": mode,
            "csv_path": form.csv_path,
            "entity_selection_pending": self.entity_selection_pending,
            "entity": entity,
            "entity_error": entity_error,
            "entity_col": form.entity_col or "issuer_name",
            "preset": preset,
            "config": config,
            "compliance_posture": posture,
            "output": form.output_file or None,
            "time_col": form.time_col,
            "validate_input": form.validate_input,
            "analyze_distortion": form.analyze_distortion,
            "compare_presets": form.compare_presets,
            "include_calculated": form.include_calculated,
            "output_format": str(form.output_format or "analysis"),
            "privacy_values": tuple(self._privacy_values().items()),
            "entity_large_list": self._entity_index is not None,
        }
        per_mode: Dict[str, Any] = {
            "secondary_metrics": form.effective_secondary(),
            "auto": form.auto_dims,
            "dimensions": form.effective_dimensions(),
            "debug": form.debug,
            "export_balanced_csv": form.export_balanced_csv,
        }
        if mode == "share":
            per_mode["metric"] = form.metric
        else:
            per_mode["total_col"] = form.total_col
            per_mode["approved_col"] = form.approved_col
            per_mode["fraud_col"] = form.fraud_col
            per_mode["fraud_in_bps"] = form.fraud_in_bps
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
        if self._run_state in ("validating", "running"):
            return  # Already running; the action bar says so.
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
        self._cancel_origin = None
        self._run_action = "share_analysis" if inputs.mode == "share" else "rate_analysis"
        log_widget.clear()
        started = datetime.now().strftime("%H:%M:%S")
        mode_text = labels.text_for(labels.ANALYSIS_MODE, inputs.mode)
        log_widget.write(f"Run started · {mode_text} · {started}\n")
        if inputs.csv_path:
            # The Review step shows only the file name; the log keeps the path.
            log_widget.write(f"Input file: {_full_path(inputs.csv_path)}\n")
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
        self._record_visible_cancel("cancel_before_run")
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

        Reads only ``inputs``. The launch guards are ``tui.readiness``'s
        ``launch_blockers`` (the same function the action bar uses), checked
        before any consent or attestation is asked, so a run that cannot
        start never asks for one.
        """
        action = "share_analysis" if inputs.mode == "share" else "rate_analysis"
        try:
            blockers = launch_blockers(inputs)
            if blockers:
                blocker = blockers[0]
                self._fail_launch(
                    blocker.message, focus_id=blocker.focus_id, block_reason=blocker.reason
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
            else:
                values["total_col"] = inputs.total_col
                values["approved_col"] = inputs.approved_col
                values["fraud_col"] = inputs.fraud_col
            values["secondary_metrics"] = list(inputs.secondary_metrics) or None
            values["auto"] = inputs.auto
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
            handler.setFormatter(_log_view_formatter())
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
            # The first report is the copy path, shown once below the card.
            for path in report_paths[1:]:
                details.append(_summary_field("Also written", path))
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
                # The quarantined log is the copy path: shown once, below the card.
                self.call_from_thread(
                    partial(
                        self._end_run_ui,
                        "blocked",
                        _outcome_markup(headline, details, code=f"{reason} · {verdict}"),
                        badge="withheld",
                        copy_path=str(quarantine_path) if quarantine_path else None,
                        copy_label="Internal run log (do not share)",
                    )
                )
            else:
                verdict_state = labels.VERDICT_STATUS.get(verdict)
                if verdict_state not in ("compliant", "warning"):
                    verdict_state = None
                verdict_text = labels.text_for(labels.COMPLIANCE_VERDICT, verdict)
                first_report = report_paths[0] if report_paths else None
                self.call_from_thread(
                    partial(
                        self._end_run_ui,
                        "success",
                        _outcome_markup(
                            labels.Label("The run finished and the report was written."),
                            details,
                            code=verdict,
                        ),
                        verdict=verdict_state,
                        copy_path=first_report,
                        copy_label="Report",
                        message=" · ".join(part for part in (verdict_text, first_report) if part),
                    )
                )
        # ``except`` expressions are evaluated only while an exception
        # propagates, and by then execute_run has imported the module.
        except _analysis_run().RunCancelled:
            # Core stopped before output writing started: nothing was written.
            # The deferred log is finalised unauthorised. Quit recorded
            # action_cancelled when it was confirmed; the visible Cancel is
            # recorded here, where it took effect (after action_attempted).
            self._record_visible_cancel("cancel_during_run")
            log_path = self._quarantine_run_logging(logger, log_widget)
            write_log_message(log_widget, "Run cancelled before any output was written.")
            self._call_ui_if_running(
                self._end_run_ui,
                "cancelled",
                _outcome_markup(labels.RUN_CANCELLED, _log_details(log_path), code="RunCancelled"),
            )
        except _analysis_run().RunBlocked as exc:
            log_path = self._quarantine_run_logging(logger, log_widget)
            self.call_from_thread(log_widget.write, f"Run blocked: {exc}\n")
            label = labels.blocked_label(str(exc))
            self.call_from_thread(
                partial(
                    self._end_run_ui,
                    "blocked",
                    _outcome_markup(label, why=str(exc), code="RunBlocked"),
                    copy_path=log_path,
                    copy_label="Internal run log (do not share)",
                )
            )
        except _analysis_run().RunAborted as exc:
            log_path = self._quarantine_run_logging(logger, log_widget)
            self.call_from_thread(log_widget.write, f"Run failed: {exc}\n")
            label = labels.aborted_label(str(exc))
            self.call_from_thread(
                partial(
                    self._end_run_ui,
                    "error",
                    _outcome_markup(label, why=str(exc), code="RunAborted"),
                    copy_path=log_path,
                    copy_label="Internal run log (do not share)",
                )
            )
        except Exception as exc:
            log_path = self._quarantine_run_logging(logger, log_widget)
            self.call_from_thread(log_widget.write, f"Run failed: {exc}\n")
            self.call_from_thread(log_widget.write, traceback.format_exc())
            label = labels.UNEXPECTED_ERROR
            self.call_from_thread(
                partial(
                    self._end_run_ui,
                    "error",
                    _outcome_markup(
                        label,
                        why=f"An unexpected error ({type(exc).__name__}) stopped the run. The input file was not changed.",
                        code=f"{type(exc).__name__}: {exc}",
                    ),
                    copy_path=log_path,
                    copy_label="Internal run log (do not share)",
                )
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


def _update_if_changed(widget: Static, value: Any) -> None:
    """``Static.update`` only when the content changed (each update re-lays out)."""
    key = (value.plain, str(value.spans)) if isinstance(value, Text) else str(value)
    if getattr(widget, "_ab_last_update", None) == key:
        return
    widget._ab_last_update = key  # type: ignore[attr-defined]
    widget.update(value)


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
