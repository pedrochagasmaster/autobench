#!/usr/bin/env python
"""Headless performance probe for the Autobench Textual TUI (``tui_app.py``).

The probe drives ``BenchmarkApp`` through ``App.run_test`` and records how long
the user-visible interactions take and how long the UI event loop is blocked
while they happen. It is intended as a repeatable baseline for the TUI
redesign: run it on one revision, keep the JSON, run it again on another
revision (``--repo`` can point at a different worktree) and compare.

Measured per run (one fresh app per dataset x repeat):

* ``import_s``             cold ``import tui_app`` in a fresh subprocess.
* ``startup_ready_s``      ``run_test`` start until the pilot is handed over
                           (screen composed and ``on_mount`` finished).
* ``startup_idle_s``       ... until the app's message queues have drained.
* ``csv_headers_ready_s``  Enter in ``#csv_path`` until ``#entity_col`` lists the
                           CSV columns.
* ``csv_entities_ready_s`` Enter in ``#csv_path`` until ``#entity_name`` lists
                           the values of the default entity column.
* ``entity_change_s``      ``#entity_col`` changed until ``#entity_name`` lists
                           the values of the new column (polled, so it works
                           whether loading is synchronous or worker-based).
* ``key_*``                keypress-to-idle latency for a tab/typing sequence.
* ``advanced_expand_s``    Ctrl+A until the Advanced collapsible is expanded
                           and the app is idle.
* ``picker_open_s`` /      Ctrl+O until the CSV picker screen is active /
  ``picker_tree_ready_s``  its directory tree has loaded, with ``cwd`` set to
                           a directory holding ``--picker-files`` CSV files.
* ``log_flood_s``          time for ``--log-lines`` records logged from a worker
                           thread to all appear in ``#log_output``.
* ``*_stall_max_ms`` /     max and p95 UI event-loop stall in each window,
  ``*_stall_p95_ms``       measured by an asyncio task that sleeps 5 ms and
                           records how late it wakes up.

"Idle" means the active screen and the app have no pending messages; it does
not include the next paint (Textual renders on its own refresh timer).

Isolation: synthetic data lives in ``--data-dir`` (a temp dir by default and
never inside the repository). ``HOME``, ``SESSION_FILE``, ``AUTOBENCH_LOG_DIR``
and the working directory are redirected to a throwaway directory, and
telemetry is disabled with ``AUTOBENCH_TELEMETRY=0``, mirroring
``tests/test_tui_ux.py`` and ``tests/conftest.py``.

Examples::

    uv run python scripts/tui_perf_probe.py --rows 10000 100000 --cardinality 50 5000
    uv run python scripts/tui_perf_probe.py --rows 1000000 --repeat 3 --json-out /tmp/tui.json
    uv run python scripts/tui_perf_probe.py --budget          # exit 1 if over budget
    uv run python scripts/tui_perf_probe.py --repo ../autobench-fix --json-out after.json

Exit codes: 0 ok, 1 budget exceeded, 2 probe error.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence

DEFAULT_REPO = Path(__file__).resolve().parent.parent
ENTITY_COL = "issuer_name"
ALT_ENTITY_COL = "alt_entity"
POLL_INTERVAL_S = 0.002
STALL_INTERVAL_S = 0.005
SETTLE_POLL_S = 0.001
WAIT_TIMEOUT_S = 300.0

# Proposed Phase 1 budgets (see docs/research/tui-redesign-phase0/04-performance-baseline.md).
# Keys are metric names; each budget is checked against the per-dataset median over
# repeats (``--budget-stat max`` checks the worst run instead).
DEFAULT_BUDGETS: Dict[str, float] = {
    "import_s": 1.0,
    "startup_idle_s": 1.0,
    "startup_stall_max_ms": 500.0,
    "csv_headers_ready_s": 0.1,
    "csv_stall_max_ms": 100.0,
    "entity_change_s": 1.5,
    "entity_change_stall_max_ms": 100.0,
    "key_latency_p95_ms": 100.0,
    "key_latency_max_ms": 250.0,
    "key_stall_max_ms": 100.0,
    "advanced_expand_s": 0.15,
    "picker_open_s": 0.2,
    "picker_stall_max_ms": 250.0,
    "log_flood_s": 1.0,
    "log_flood_stall_max_ms": 50.0,
}

ALL_PHASES = ("startup", "csv", "entity", "keys", "advanced", "picker", "log")


# ──────────────────────────────────────────────────────────────────────────
# Synthetic data
# ──────────────────────────────────────────────────────────────────────────


def generate_csv(path: Path, *, rows: int, cardinality: int, columns: int, seed: int = 7) -> Path:
    """Write a deterministic benchmark-shaped CSV (cached by file name)."""
    if path.exists():
        return path
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(seed)
    width = max(len(str(cardinality - 1)), 1)
    entities = np.array([f"ENT_{i:0{width}d}" for i in range(cardinality)])
    alt = np.array([f"ALT_{i:0{width}d}" for i in range(cardinality)])
    months = np.array([f"2025-{m:02d}" for m in range(1, 13)])
    frame: Dict[str, Any] = {
        ENTITY_COL: entities[rng.integers(0, cardinality, rows)],
        ALT_ENTITY_COL: alt[rng.integers(0, cardinality, rows)],
        "year_month": months[rng.integers(0, len(months), rows)],
        "card_type": np.array(["credit", "debit", "prepaid"])[rng.integers(0, 3, rows)],
        "channel": np.array(["pos", "ecom", "moto", "atm"])[rng.integers(0, 4, rows)],
        "txn_cnt": rng.integers(1, 10_000, rows),
        "app_cnt": rng.integers(1, 9_000, rows),
        "total": rng.integers(1, 1_000_000, rows),
    }
    for extra in range(max(columns - len(frame), 0)):
        frame[f"metric_{extra:02d}"] = rng.integers(0, 100_000, rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    pd.DataFrame(frame).to_csv(tmp, index=False)
    tmp.replace(path)
    return path


def build_picker_dir(base: Path, files: int) -> Path:
    """Directory with ``files`` small CSVs plus a few subdirectories."""
    target = base / f"picker_{files}"
    marker = target / ".complete"
    if marker.exists():
        return target
    target.mkdir(parents=True, exist_ok=True)
    for index in range(files):
        (target / f"file_{index:05d}.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    for sub in ("data", "tests", "archive"):
        (target / sub).mkdir(exist_ok=True)
    marker.write_text("ok", encoding="utf-8")
    return target


# ──────────────────────────────────────────────────────────────────────────
# Measurement helpers
# ──────────────────────────────────────────────────────────────────────────


def percentile(values: Sequence[float], pct: float) -> float:
    """Nearest-rank percentile; 0.0 for an empty sequence."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(int(round(pct / 100.0 * len(ordered) + 0.5)) - 1, 0)
    return ordered[min(rank, len(ordered) - 1)]


class PhaseProfiler:
    """Profiles each measurement window into ``out_dir``.

    Uses pyinstrument when importable (``uv run --with pyinstrument ...``),
    otherwise cProfile; writes ``<prefix>_<phase>.txt`` (plus ``.html`` and a
    self-time ``_flat.txt`` for pyinstrument).
    """

    def __init__(self, out_dir: Path, prefix: str) -> None:
        self.out_dir = out_dir
        self.prefix = prefix
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._phase: Optional[str] = None
        self._impl: Any = None
        try:
            import pyinstrument  # noqa: F401

            self.backend = "pyinstrument"
        except ImportError:
            self.backend = "cProfile"

    def start(self, phase: str) -> None:
        self._phase = phase
        if self.backend == "pyinstrument":
            from pyinstrument import Profiler

            self._impl = Profiler(interval=0.0005, async_mode="disabled")
            self._impl.start()
        else:
            import cProfile

            self._impl = cProfile.Profile()
            self._impl.enable()

    def stop(self) -> None:
        if self._impl is None or self._phase is None:
            return
        base = self.out_dir / f"{self.prefix}_{self._phase}"
        if self.backend == "pyinstrument":
            self._impl.stop()
            base.with_suffix(".txt").write_text(
                self._impl.output_text(unicode=True, color=False, show_all=False), encoding="utf-8"
            )
            base.with_suffix(".html").write_text(self._impl.output_html(), encoding="utf-8")
            try:
                from pyinstrument.renderers import ConsoleRenderer

                flat = self._impl.output(ConsoleRenderer(flat=True, unicode=True, color=False))
                Path(f"{base}_flat.txt").write_text(flat, encoding="utf-8")
            except Exception:  # older pyinstrument without flat mode
                pass
        else:
            import io
            import pstats

            self._impl.disable()
            buffer = io.StringIO()
            pstats.Stats(self._impl, stream=buffer).sort_stats("cumulative").print_stats(40)
            base.with_suffix(".txt").write_text(buffer.getvalue(), encoding="utf-8")
        self._impl = None
        self._phase = None


class StallProbe:
    """Records event-loop wake-up lateness of a periodic asyncio task.

    Any synchronous work on the loop (a pandas read inside an event handler,
    a large ``compose``) delays the task's wake-up; the lateness is the stall
    the user would feel as a frozen UI.
    """

    def __init__(self, interval: float = STALL_INTERVAL_S, profiler: Optional["PhaseProfiler"] = None) -> None:
        self.interval = interval
        self.profiler = profiler
        self.samples: List[float] = []
        self._task: Optional[asyncio.Task[None]] = None
        self._running = False

    async def _run(self) -> None:
        last = time.perf_counter()
        while self._running:
            await asyncio.sleep(self.interval)
            now = time.perf_counter()
            self.samples.append(max(now - last - self.interval, 0.0))
            last = now

    def start(self) -> None:
        self._running = True
        self._task = asyncio.get_running_loop().create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            await self._task

    def mark(self, phase: str) -> int:
        """Start a measurement window (and the phase profiler, if any)."""
        if self.profiler is not None:
            self.profiler.start(phase)
        return len(self.samples)

    async def window_stats(self, start: int) -> Dict[str, float]:
        # Give the probe task a chance to record the sample spanning the
        # stall that just ended.
        await asyncio.sleep(self.interval * 2)
        if self.profiler is not None:
            self.profiler.stop()
        window = self.samples[start:]
        return {
            "stall_max_ms": round(max(window, default=0.0) * 1000, 2),
            "stall_p95_ms": round(percentile(window, 95) * 1000, 2),
        }


def _has_pending_messages(app: Any) -> bool:
    """True while the app, any screen or any widget has queued messages/callbacks."""
    pumps: List[Any] = [app]
    for screen in getattr(app, "screen_stack", [app.screen]):
        pumps.append(screen)
        pumps.extend(screen.walk_children())
    for pump in pumps:
        size = getattr(pump, "message_queue_size", None)
        if size is None:
            queue = getattr(pump, "_message_queue", None)
            size = queue.qsize() if queue is not None else 0
        if size or getattr(pump, "_next_callbacks", None):
            return True
    return False


async def settle(pilot: Any, timeout: float = WAIT_TIMEOUT_S) -> float:
    """Wait until no message pump has pending work; return the time it went quiet.

    Polls every ~1 ms and requires two consecutive quiet polls. This avoids
    ``pilot.pause()``/``pilot.press()`` internals (``wait_for_idle`` sleeps at
    least 20 ms twice per key and ``_wait_for_screen`` round-trips every widget),
    which would otherwise add a 40-80 ms harness floor to every latency.
    """
    app = pilot.app
    deadline = time.perf_counter() + timeout
    quiet_since: Optional[float] = None
    while True:
        await asyncio.sleep(SETTLE_POLL_S)
        if _has_pending_messages(app):
            quiet_since = None
        elif quiet_since is None:
            quiet_since = time.perf_counter()
        else:
            return quiet_since
        if time.perf_counter() > deadline:
            raise TimeoutError("app did not settle")


def send_key(app: Any, key: str) -> None:
    """Post one key event to the app the way ``Pilot.press`` does, without its waits."""
    import unicodedata

    from textual import events

    try:
        from textual.keys import REPLACED_KEYS, _character_to_key, _get_unicode_name_from_key
    except ImportError:  # pragma: no cover - fallback for other Textual versions
        REPLACED_KEYS, _character_to_key, _get_unicode_name_from_key = {}, (lambda k: k), (lambda k: k)
    if len(key) == 1 and not key.isalnum():
        key = _character_to_key(key)
    original = REPLACED_KEYS.get(key, key)
    try:
        char: Optional[str] = unicodedata.lookup(_get_unicode_name_from_key(original))
    except KeyError:
        char = key if len(key) == 1 else None
    event = events.Key(key, char)
    event.set_sender(app)
    app._driver.send_message(event)


async def press(pilot: Any, key: str) -> float:
    """Press ``key`` and return seconds until the app is idle again."""
    t0 = time.perf_counter()
    send_key(pilot.app, key)
    return await settle(pilot) - t0


async def wait_until(predicate: Callable[[], bool], timeout: float = WAIT_TIMEOUT_S) -> float:
    """Poll ``predicate`` until true; return the perf_counter time it became true."""
    deadline = time.perf_counter() + timeout
    while True:
        try:
            if predicate():
                return time.perf_counter()
        except Exception:
            pass
        if time.perf_counter() > deadline:
            raise TimeoutError("condition not reached")
        await asyncio.sleep(POLL_INTERVAL_S)


def select_values(app: Any, selector: str) -> List[Any]:
    """Option values of a Select, excluding the blank sentinel."""
    from textual.widgets import Select

    select = app.query_one(selector, Select)
    options = getattr(select, "_options", [])
    blank = getattr(Select, "NULL", getattr(Select, "BLANK", None))
    return [value for _, value in options if value is not blank and value != blank]


def has_prefixed_option(app: Any, selector: str, prefix: str) -> bool:
    return any(str(value).startswith(prefix) for value in select_values(app, selector))


@contextmanager
def chdir(path: Path) -> Iterator[None]:
    previous = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


# ──────────────────────────────────────────────────────────────────────────
# Scenario
# ──────────────────────────────────────────────────────────────────────────


@dataclass
class Dataset:
    label: str
    path: Path
    rows: Optional[int]
    cardinality: Optional[int]
    entity_col: str = ENTITY_COL
    alt_entity_col: str = ALT_ENTITY_COL
    entity_prefix: Optional[str] = "ENT_"
    alt_prefix: Optional[str] = "ALT_"


@dataclass
class ProbeConfig:
    size: tuple
    phases: Sequence[str]
    picker_dir: Optional[Path]
    log_lines: int
    work_dir: Path
    keys: List[str] = field(default_factory=list)


def measure_import(repo: Path, work_dir: Path) -> float:
    """Cold-import ``tui_app`` in a fresh interpreter and return seconds."""
    code = (
        "import sys, time\n"
        f"sys.path.insert(0, {str(repo)!r})\n"
        "t = time.perf_counter()\n"
        "import tui_app  # noqa: F401\n"
        "print(time.perf_counter() - t)\n"
    )
    env = dict(os.environ, AUTOBENCH_TELEMETRY="0", HOME=str(work_dir))
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=work_dir, env=env, capture_output=True, text=True, check=True
    )
    return float(out.stdout.strip().splitlines()[-1])


async def run_scenario(
    tui_app: Any, dataset: Dataset, cfg: ProbeConfig, profiler: Optional[PhaseProfiler] = None
) -> Dict[str, Any]:
    """One fresh app session; returns flat metric dict."""
    from textual.widgets import Input, Select

    metrics: Dict[str, Any] = {}
    stall = StallProbe(profiler=profiler)
    stall.start()
    app = tui_app.BenchmarkApp()
    mark = stall.mark("startup")
    t0 = time.perf_counter()
    async with app.run_test(size=cfg.size) as pilot:
        metrics["startup_ready_s"] = time.perf_counter() - t0
        metrics["startup_idle_s"] = await settle(pilot) - t0
        stats = await stall.window_stats(mark)
        metrics["startup_stall_max_ms"] = stats["stall_max_ms"]

        csv_loaded = False
        if "csv" in cfg.phases or "entity" in cfg.phases or "keys" in cfg.phases:
            csv_input = app.query_one("#csv_path", Input)
            csv_input.focus()
            csv_input.value = str(dataset.path)
            await settle(pilot)
            mark = stall.mark("csv")
            t0 = time.perf_counter()
            send_key(app, "enter")
            t_headers = await wait_until(lambda: dataset.entity_col in select_values(app, "#entity_col"))
            metrics["csv_headers_ready_s"] = t_headers - t0
            if dataset.entity_prefix:
                t_ent = await wait_until(lambda: has_prefixed_option(app, "#entity_name", dataset.entity_prefix))
            else:
                t_ent = await wait_until(lambda: bool(select_values(app, "#entity_name")))
            metrics["csv_entities_ready_s"] = t_ent - t0
            metrics["csv_idle_s"] = await settle(pilot) - t0
            stats = await stall.window_stats(mark)
            metrics["csv_stall_max_ms"] = stats["stall_max_ms"]
            metrics["csv_stall_p95_ms"] = stats["stall_p95_ms"]
            metrics["entity_option_count"] = len(select_values(app, "#entity_name"))
            csv_loaded = True

        if "entity" in cfg.phases and csv_loaded:
            before = set(select_values(app, "#entity_name"))
            mark = stall.mark("entity")
            t0 = time.perf_counter()
            app.query_one("#entity_col", Select).value = dataset.alt_entity_col
            if dataset.alt_prefix:
                t_ready = await wait_until(lambda: has_prefixed_option(app, "#entity_name", dataset.alt_prefix))
            else:
                t_ready = await wait_until(
                    lambda: bool(select_values(app, "#entity_name"))
                    and set(select_values(app, "#entity_name")) != before
                )
            metrics["entity_change_s"] = t_ready - t0
            metrics["entity_change_idle_s"] = await settle(pilot) - t0
            stats = await stall.window_stats(mark)
            metrics["entity_change_stall_max_ms"] = stats["stall_max_ms"]
            metrics["entity_change_stall_p95_ms"] = stats["stall_p95_ms"]

        if "keys" in cfg.phases:
            latencies: List[float] = []
            per_key: List[Dict[str, Any]] = []
            app.query_one("#csv_path", Input).focus()
            await settle(pilot)
            mark = stall.mark("keys")
            for index, key in enumerate(cfg.keys):
                if key.startswith("@"):
                    app.query_one(key[1:]).focus()
                    await settle(pilot)
                    continue
                focused = getattr(app.focused, "id", None)
                latency = await press(pilot, key)
                latencies.append(latency)
                per_key.append({"i": index, "key": key, "from": focused, "ms": round(latency * 1000, 2)})
            stats = await stall.window_stats(mark)
            metrics["key_latency_p50_ms"] = round(statistics.median(latencies) * 1000, 2) if latencies else 0.0
            metrics["key_latency_p95_ms"] = round(percentile(latencies, 95) * 1000, 2)
            metrics["key_latency_max_ms"] = round(max(latencies, default=0.0) * 1000, 2)
            metrics["key_stall_max_ms"] = stats["stall_max_ms"]
            slowest = max(per_key, key=lambda item: item["ms"], default=None)
            metrics["key_slowest"] = slowest
            metrics["key_detail"] = per_key

        if "advanced" in cfg.phases:
            collapsible = app.query_one("#advanced_opt")
            app.query_one("#btn_run").focus()
            await settle(pilot)
            mark = stall.mark("advanced")
            t0 = time.perf_counter()
            t_idle = t0 + await press(pilot, "ctrl+a")
            if collapsible.collapsed:  # binding swallowed: fall back to the action
                await app.run_action("toggle_advanced")
                t_idle = await settle(pilot)
            metrics["advanced_expand_s"] = t_idle - t0
            stats = await stall.window_stats(mark)
            metrics["advanced_stall_max_ms"] = stats["stall_max_ms"]
            await press(pilot, "ctrl+a")

        if "picker" in cfg.phases and cfg.picker_dir is not None:
            base_screen = app.screen
            with chdir(cfg.picker_dir):
                app.query_one("#btn_run").focus()
                await settle(pilot)
                mark = stall.mark("picker")
                t0 = time.perf_counter()
                send_key(app, "ctrl+o")
                t_open = await wait_until(lambda: app.screen is not base_screen)
                metrics["picker_open_s"] = t_open - t0
                from textual.widgets import DirectoryTree

                def tree_loaded() -> bool:
                    tree = app.screen.query_one(DirectoryTree)
                    return len(tree.root.children) > 0

                t_tree = await wait_until(tree_loaded)
                metrics["picker_tree_ready_s"] = t_tree - t0
                metrics["picker_idle_s"] = await settle(pilot) - t0
                stats = await stall.window_stats(mark)
                metrics["picker_stall_max_ms"] = stats["stall_max_ms"]
                await press(pilot, "escape")

        if "log" in cfg.phases and cfg.log_lines > 0:
            log_widget = app.query_one("#log_output")
            logger = logging.getLogger("autobench.perf_probe")
            marker = f"perf-probe-last-{time.time_ns()}"
            mark = stall.mark("log")
            t0 = time.perf_counter()

            def flood() -> None:
                for line in range(cfg.log_lines - 1):
                    logger.info("perf probe line %d of a long analysis run", line)
                logger.info(marker)

            thread = threading.Thread(target=flood, daemon=True)
            thread.start()
            await wait_until(lambda: any(marker in str(line) for line in list(log_widget.lines)[-5:]))
            metrics["log_flood_s"] = time.perf_counter() - t0
            # Never join synchronously: the flood thread may be blocked in
            # call_from_thread waiting for this very loop.
            await wait_until(lambda: not thread.is_alive())
            stats = await stall.window_stats(mark)
            metrics["log_flood_stall_max_ms"] = stats["stall_max_ms"]
            metrics["log_line_count"] = len(log_widget.lines)

    await stall.stop()
    for key, value in list(metrics.items()):
        if isinstance(value, float):
            metrics[key] = round(value, 4)
    return metrics


# ──────────────────────────────────────────────────────────────────────────
# Reporting / budgets
# ──────────────────────────────────────────────────────────────────────────

SUMMARY_METRICS = (
    "import_s",
    "startup_ready_s",
    "startup_idle_s",
    "startup_stall_max_ms",
    "csv_headers_ready_s",
    "csv_entities_ready_s",
    "csv_stall_max_ms",
    "entity_change_s",
    "entity_change_stall_max_ms",
    "entity_change_stall_p95_ms",
    "key_latency_p50_ms",
    "key_latency_p95_ms",
    "key_latency_max_ms",
    "key_stall_max_ms",
    "advanced_expand_s",
    "advanced_stall_max_ms",
    "picker_open_s",
    "picker_tree_ready_s",
    "picker_stall_max_ms",
    "log_flood_s",
    "log_flood_stall_max_ms",
)


def summarise(runs: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    summary: Dict[str, Dict[str, float]] = {}
    for metric in SUMMARY_METRICS:
        values = [run[metric] for run in runs if isinstance(run.get(metric), (int, float))]
        if values:
            summary[metric] = {
                "median": round(statistics.median(values), 4),
                "max": round(max(values), 4),
                "min": round(min(values), 4),
                "n": len(values),
            }
    return summary


def check_budgets(results: List[Dict[str, Any]], budgets: Dict[str, float], stat: str = "median") -> List[str]:
    failures: List[str] = []
    for result in results:
        summary = result["summary"]
        for metric, limit in budgets.items():
            if metric not in summary:
                continue
            observed = summary[metric][stat]
            if observed > limit:
                failures.append(f"{result['dataset']}: {metric} {stat}={observed:g} > budget {limit:g}")
    return failures


def print_table(results: List[Dict[str, Any]]) -> None:
    labels = [result["dataset"] for result in results]
    width = max([len(m) for m in SUMMARY_METRICS] + [6])
    col = max([len(label) for label in labels] + [18])
    print()
    print("metric".ljust(width), *(label.rjust(col) for label in labels))
    print("-" * (width + (col + 1) * len(labels)))
    for metric in SUMMARY_METRICS:
        cells = []
        for result in results:
            entry = result["summary"].get(metric)
            cells.append((f"{entry['median']:g} / {entry['max']:g}" if entry else "-").rjust(col))
        print(metric.ljust(width), *cells)
    print("(median / max over repeats; *_s seconds, *_ms milliseconds)")


def machine_info() -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "processor": platform.processor() or platform.machine(),
    }
    try:
        import textual

        info["textual"] = getattr(textual, "__version__", "?")
        import pandas

        info["pandas"] = pandas.__version__
    except Exception:
        pass
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                info["cpu_model"] = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    return info


# ──────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────

DEFAULT_KEYS = (
    # Tab out of #csv_path (triggers its blur handler), walk the form, then type.
    ["tab"] * 6
    + ["@#output_file"]
    + list("report")
    + ["backspace", "shift+tab", "shift+tab"]
)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO, help="checkout whose tui_app.py is probed")
    parser.add_argument("--rows", type=int, nargs="+", default=[10_000], help="synthetic row counts")
    parser.add_argument("--cardinality", type=int, nargs="+", default=[50], help="distinct entities per column")
    parser.add_argument("--columns", type=int, default=12, help="total synthetic columns (min 8)")
    parser.add_argument("--csv", type=Path, help="probe an existing CSV instead of synthetic data")
    parser.add_argument("--entity-col", default=ENTITY_COL, help="with --csv: default entity column")
    parser.add_argument("--alt-entity-col", default=ALT_ENTITY_COL, help="with --csv: column to switch to")
    parser.add_argument("--repeat", type=int, default=3, help="fresh app sessions per dataset")
    parser.add_argument("--size", default="120x40", help="terminal size WIDTHxHEIGHT")
    parser.add_argument("--phases", nargs="+", default=list(ALL_PHASES), choices=ALL_PHASES)
    parser.add_argument("--picker-files", type=int, default=2000, help="CSV files in the picker cwd")
    parser.add_argument("--log-lines", type=int, default=5000, help="records for the log-flood phase")
    parser.add_argument("--no-import", action="store_true", help="skip the subprocess import timing")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(tempfile.gettempdir()) / "autobench-tui-perf",
        help="where synthetic CSVs are cached (must be outside the repository)",
    )
    parser.add_argument("--json-out", type=Path, help="write full results as JSON")
    parser.add_argument(
        "--profile-dir", type=Path, help="write per-phase profiles from an extra, untimed session (pyinstrument if installed, else cProfile)"
    )
    parser.add_argument("--quiet", action="store_true", help="suppress the human-readable table")
    parser.add_argument("--budget", action="store_true", help="exit 1 when a budget is exceeded")
    parser.add_argument("--budget-stat", choices=("median", "max"), default="median", help="statistic checked")
    for key, value in DEFAULT_BUDGETS.items():
        parser.add_argument(
            f"--budget-{key.replace('_', '-')}",
            dest=f"budget__{key}",
            type=float,
            default=value,
            help=f"budget for {key} (default {value:g}; <=0 disables)",
        )
    return parser.parse_args(argv)


def build_datasets(args: argparse.Namespace) -> List[Dataset]:
    if args.csv:
        return [
            Dataset(
                label=args.csv.name,
                path=args.csv.resolve(),
                rows=None,
                cardinality=None,
                entity_col=args.entity_col,
                alt_entity_col=args.alt_entity_col,
                entity_prefix=None,
                alt_prefix=None,
            )
        ]
    datasets = []
    for rows in args.rows:
        for card in args.cardinality:
            path = args.data_dir / f"synthetic_r{rows}_c{card}_k{args.columns}.csv"
            print(f"[probe] preparing {path.name}", file=sys.stderr, flush=True)
            generate_csv(path, rows=rows, cardinality=card, columns=args.columns)
            datasets.append(Dataset(label=f"{rows:,} rows x {card} ent", path=path, rows=rows, cardinality=card))
    return datasets


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    repo = args.repo.resolve()
    data_dir = args.data_dir.resolve()
    if data_dir == repo or repo in data_dir.parents:
        print("--data-dir must be outside the repository", file=sys.stderr)
        return 2
    data_dir.mkdir(parents=True, exist_ok=True)
    args.data_dir = data_dir
    width, height = (int(part) for part in args.size.lower().split("x"))

    work_root = Path(tempfile.mkdtemp(prefix="tui_probe_run_", dir=data_dir))
    home = work_root / "home"
    home.mkdir()
    os.environ["AUTOBENCH_TELEMETRY"] = "0"
    os.environ["AUTOBENCH_LOG_DIR"] = str(work_root / "logs")
    os.environ["HOME"] = str(home)
    os.chdir(work_root)

    datasets = build_datasets(args)
    picker_dir = build_picker_dir(data_dir, args.picker_files) if "picker" in args.phases else None

    import_times: List[float] = []
    if not args.no_import and "startup" in args.phases:
        for _ in range(args.repeat):
            import_times.append(round(measure_import(repo, work_root), 4))

    sys.path.insert(0, str(repo))
    import tui_app

    if hasattr(tui_app, "SESSION_FILE"):
        tui_app.SESSION_FILE = home / ".benchmark_tui" / "session.yaml"

    cfg = ProbeConfig(
        size=(width, height),
        phases=args.phases,
        picker_dir=picker_dir,
        log_lines=args.log_lines,
        work_dir=work_root,
        keys=list(DEFAULT_KEYS),
    )

    results: List[Dict[str, Any]] = []
    for dataset in datasets:
        runs: List[Dict[str, Any]] = []
        if args.profile_dir:
            # Separate session so profiler overhead never leaks into the timings.
            slug = f"r{dataset.rows}_c{dataset.cardinality}" if dataset.rows else dataset.path.stem
            profiler = PhaseProfiler(args.profile_dir, slug)
            print(f"[probe] {dataset.label}: profiling run ({profiler.backend})", file=sys.stderr, flush=True)
            asyncio.run(run_scenario(tui_app, dataset, cfg, profiler))
        for index in range(args.repeat):
            print(f"[probe] {dataset.label}: run {index + 1}/{args.repeat}", file=sys.stderr, flush=True)
            metrics = asyncio.run(run_scenario(tui_app, dataset, cfg))
            if import_times:
                metrics["import_s"] = import_times[index % len(import_times)]
            runs.append(metrics)
        results.append(
            {
                "dataset": dataset.label,
                "csv": str(dataset.path),
                "csv_bytes": dataset.path.stat().st_size,
                "rows": dataset.rows,
                "cardinality": dataset.cardinality,
                "summary": summarise(runs),
                "runs": runs,
            }
        )

    budgets = {
        key: getattr(args, f"budget__{key}") for key in DEFAULT_BUDGETS if getattr(args, f"budget__{key}") > 0
    }
    report = {
        "probe": "scripts/tui_perf_probe.py",
        "repo": str(repo),
        "git_rev": _git_rev(repo),
        "machine": machine_info(),
        "size": args.size,
        "repeat": args.repeat,
        "picker_files": args.picker_files,
        "log_lines": args.log_lines,
        "budgets": budgets,
        "results": results,
    }
    failures = check_budgets(results, budgets, args.budget_stat) if args.budget else []
    report["budget_failures"] = failures

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    if not args.quiet:
        print(json.dumps({k: report[k] for k in ("git_rev", "machine", "size", "repeat")}, indent=2))
        print_table(results)
    if args.budget:
        if failures:
            print("\nBUDGET EXCEEDED:", *failures, sep="\n  ")
            return 1
        print("\nAll budgets met.")
    return 0


def _git_rev(repo: Path) -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        )
        return out.stdout.strip()
    except Exception:
        return None


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(2)
