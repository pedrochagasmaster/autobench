"""Deterministic TUI scenes for snapshot tests and review screenshots (Phase 2 PR 6).

Each scene is an async ``run_before(pilot)`` that drives a real
``BenchmarkApp`` into one state. ``install_determinism`` pins everything
that would otherwise vary between runs or machines: the clock, log
timestamps, the run log path, the engine (stubbed), session and log
locations, and the glyph set. The CSV is the committed
``tests/fixtures/gate_demo.csv`` opened by a relative path from its own
folder, so no machine-specific path is ever drawn.

``scripts``-free on purpose: ``tests/test_tui_snapshots.py`` uses it, and
the heuristic-review capture in the PR 6 scratchpad imports the same scenes.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
import threading
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict

from textual.pilot import Pilot
from textual.widgets import Input

import tui_app
from core.contracts import AnalysisArtifacts, PrivacyOutputDecision
from core.data_loader import ValidationIssue, ValidationSeverity
from tui import status as tui_status

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CSV = "gate_demo.csv"
REPORT = "/home/analyst/work/outputs/benchmark_share_Target_20261014_101530.xlsx"
OUTPUT = "/home/analyst/work/outputs/benchmark_share_Target.xlsx"
QUARANTINE_LOG = "/home/analyst/.autobench/logs/autobench_NON_PUBLISHABLE_run_log_0001.log"
FIXED_NOW = _dt.datetime(2026, 10, 14, 10, 15, 30)
RELEASE = threading.Event()


class _FixedDatetime(_dt.datetime):
    @classmethod
    def now(cls, tz: Any = None) -> "_FixedDatetime":  # type: ignore[override]
        return cls(2026, 10, 14, 10, 15, 30, tzinfo=tz)


class _FixedFormatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: Any = None) -> str:  # noqa: N802
        return "10:15:30"


def _fixed_formatter() -> logging.Formatter:
    return _FixedFormatter("%(asctime)s %(levelname)-7s %(message)s")


_REAL_FINALIZE = tui_app.finalize_deferred_logging


def _finalize(logger: Any, *, privacy_authorized: bool = False, **kw: Any) -> Any:
    """The real finaliser (it detaches the deferred handler), with a fixed path shown."""
    path = _REAL_FINALIZE(logger, privacy_authorized=privacy_authorized, **kw)
    if path is None:
        return None
    return None if privacy_authorized else QUARANTINE_LOG


def install_determinism(monkeypatch: Any, tmp_path: Path) -> None:
    """Pin the clock, log lines, paths and engine for a snapshot."""
    monkeypatch.setattr(tui_app, "SESSION_FILE", tmp_path / "session.yaml")
    monkeypatch.setenv("AUTOBENCH_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("AUTOBENCH_TELEMETRY", "0")
    monkeypatch.chdir(FIXTURES)
    monkeypatch.setattr(tui_app, "datetime", _FixedDatetime)
    monkeypatch.setattr(tui_app, "_log_view_formatter", _fixed_formatter)
    monkeypatch.setattr(
        tui_app, "_full_path", lambda path: path if path.startswith("/") else f"/home/analyst/work/{Path(path).name}"
    )
    monkeypatch.setattr(tui_app, "_launch_folder", lambda: "/home/analyst/work")
    monkeypatch.setattr(tui_app, "finalize_deferred_logging", _finalize)
    monkeypatch.setattr(tui_app, "_elapsed_since", lambda _start: 1.0)
    monkeypatch.setattr(tui_app, "execute_run", fake_success)
    tui_status.set_ascii_glyphs(False)


def fake_success(request: Any, logger: logging.Logger, **_kw: Any) -> AnalysisArtifacts:
    # No logger records: the batched log handler and direct writes from the
    # worker may interleave in either order, which a snapshot cannot allow.
    return AnalysisArtifacts(
        metadata={},
        compliance_summary={
            "posture": "strict",
            "compliance_verdict": "fully_compliant",
            "acknowledgement_state": "not_required",
        },
        report_paths=[REPORT],
        privacy_output_decision=PrivacyOutputDecision(True, False, None),
        privacy_sink_authorized=True,
        privacy_log_authorized=True,
    )


def fake_withheld(request: Any, logger: logging.Logger, **_kw: Any) -> AnalysisArtifacts:
    return AnalysisArtifacts(
        metadata={},
        compliance_summary={
            "posture": "strict",
            "compliance_verdict": "violations_detected",
            "acknowledgement_state": "not_required",
        },
        report_paths=[],
        privacy_output_decision=PrivacyOutputDecision(False, True, "control3_numeric_policy_blocked"),
        privacy_sink_authorized=False,
    )


def fake_blocked(request: Any, logger: logging.Logger, **_kw: Any) -> AnalysisArtifacts:
    raise tui_app._analysis_run().RunBlocked(
        "accuracy_first compliance_posture requires explicit acknowledgement for this run", {}
    )


def fake_unexpected(request: Any, logger: logging.Logger, **_kw: Any) -> AnalysisArtifacts:
    raise KeyError("card_type_input_mode")


def fake_slow(request: Any, logger: logging.Logger, **kw: Any) -> AnalysisArtifacts:
    for stage in ("configuration", "input", "analysis"):
        kw["on_stage"](stage)
    RELEASE.wait(30)
    return fake_success(request, logger)


# ── Helpers ─────────────────────────────────────────────────────────────


async def until(pilot: Pilot, predicate: Callable[[], bool], timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise TimeoutError("scene did not reach its state")
        await pilot.pause(0.05)


async def settle(pilot: Pilot) -> None:
    """Let workers, deferred layouts and the focus scroll land; clear toasts."""
    app = pilot.app
    for _ in range(3):
        await pilot.pause(0.1)
    app.clear_notifications()
    # A blinking cursor is caught on or off at random: hold it solid.
    for screen in app.screen_stack:
        for field in screen.query(Input):
            field.cursor_blink = False
    await pilot.pause(0.1)


async def load(pilot: Pilot, **form: Any) -> None:
    """Load the fixture and fill the every-run fields (share, Target, 2 dims)."""
    app = pilot.app
    await pilot.pause()
    app.form.csv_path = CSV
    app.load_csv_headers(CSV, announce=False)
    await until(pilot, lambda: app._csv_loaded and not app.entity_values_loading)
    values: Dict[str, Any] = dict(
        entity="Target",
        metric="txn_cnt",
        dimensions=("card_type", "channel"),
        validate_input=False,
        output_file=OUTPUT,
    )
    values.update(form)
    app.form.update(**values)
    await pilot.pause()


async def show(pilot: Pilot, step: str, focus: Any = "entry") -> None:
    app = pilot.app
    await app.ensure_step(step)
    app._show_step(step, focus=focus)
    await settle(pilot)


async def run_until(pilot: Pilot, states: tuple, engine: Callable[..., Any]) -> None:
    app = pilot.app
    tui_app.execute_run = engine
    app.run_analysis()
    await until(pilot, lambda: app._run_state in states)
    await settle(pilot)


# ── Scenes ──────────────────────────────────────────────────────────────


async def step_data(pilot: Pilot) -> None:
    await pilot.pause()
    pilot.app.query_one("#csv_path").focus()
    await settle(pilot)


async def step_data_loaded(pilot: Pilot) -> None:
    await load(pilot)
    await show(pilot, "data", focus="csv_path")


async def step_entity(pilot: Pilot) -> None:
    await load(pilot)
    await show(pilot, "entity", focus="entity_name")


async def step_analysis(pilot: Pilot) -> None:
    await load(pilot)
    await show(pilot, "analysis", focus="dims")


async def step_analysis_rate(pilot: Pilot) -> None:
    await load(pilot, mode="rate", total_col="total", approved_col="approved")
    await show(pilot, "analysis", focus="rate_total")


async def step_privacy(pilot: Pilot) -> None:
    await load(pilot)
    await show(pilot, "privacy", focus="preset_select")


async def step_review(pilot: Pilot) -> None:
    await load(pilot)
    await show(pilot, "review", focus="btn_run")


async def review_blocked(pilot: Pilot) -> None:
    await load(pilot, mode="rate", dimensions=(), citi_competitor=True)
    await show(pilot, "review", focus="review_blockers")


async def expert(pilot: Pilot) -> None:
    await load(pilot)
    pilot.app.set_expert_value("adv_bounds_max_weight", "3.5")
    await pilot.press("f8")
    await until(pilot, lambda: type(pilot.app.screen).__name__ == "ExpertScreen")
    await settle(pilot)


async def reset_dialog(pilot: Pilot) -> None:
    await load(pilot)
    pilot.app.set_expert_value("adv_bounds_max_weight", "3.5")
    await show(pilot, "privacy", focus="preset_select")
    pilot.app._preset_selected("low_distortion")
    await until(pilot, lambda: isinstance(pilot.app.screen, tui_app.ModalScreen))
    await settle(pilot)


async def consent(pilot: Pilot) -> None:
    await load(pilot, preset="low_distortion")
    await show(pilot, "review", focus="btn_run")
    pilot.app.run_analysis()
    await until(pilot, lambda: isinstance(pilot.app.screen, tui_app.ConfirmScreen))
    await settle(pilot)


async def clearing_spend(pilot: Pilot) -> None:
    await load(pilot, mode="rate", total_col="total", fraud_col="fraud", approved_col=None)
    await show(pilot, "review", focus="btn_run")
    pilot.app.run_analysis()
    await until(pilot, lambda: isinstance(pilot.app.screen, tui_app.ClearingSpendConfirmScreen))
    await settle(pilot)


async def validation(pilot: Pilot) -> None:
    await load(pilot)
    await show(pilot, "review", focus="btn_run")
    issues = [
        ValidationIssue(ValidationSeverity.ERROR, "negative_values", "Column 'txn_cnt' has 1 negative value",
                        row_indices=[4]),
        ValidationIssue(ValidationSeverity.WARNING, "outliers", "Column 'total' has 2 outliers",
                        row_indices=[2, 9]),
        ValidationIssue(ValidationSeverity.WARNING, "duplicates", "5 duplicate rows detected"),
    ]
    pilot.app.push_screen(tui_app.ValidationModal(issues))
    await until(pilot, lambda: isinstance(pilot.app.screen, tui_app.ValidationModal))
    await settle(pilot)


async def running(pilot: Pilot) -> None:
    RELEASE.clear()
    await load(pilot)
    await show(pilot, "review", focus="btn_run")
    app = pilot.app
    tui_app.execute_run = fake_slow
    app.run_analysis()
    await until(pilot, lambda: app._run_state == "running" and app._run_stage == "analysis")
    app._run_started_at = time.monotonic()
    app._refresh_run_status()
    await settle(pilot)


async def success(pilot: Pilot) -> None:
    await load(pilot)
    await show(pilot, "review", focus="btn_run")
    await run_until(pilot, ("success",), fake_success)


async def withheld(pilot: Pilot) -> None:
    await load(pilot)
    await show(pilot, "review", focus="btn_run")
    await run_until(pilot, ("blocked",), fake_withheld)


async def blocked(pilot: Pilot) -> None:
    await load(pilot)
    await show(pilot, "review", focus="btn_run")
    await run_until(pilot, ("blocked",), fake_blocked)


async def unexpected_error(pilot: Pilot) -> None:
    await load(pilot)
    await show(pilot, "review", focus="btn_run")
    await run_until(pilot, ("error",), fake_unexpected)


async def results_view(pilot: Pilot) -> None:
    """The results with focus in them: below 110 columns the run already
    opened the results view (^T would close it); at 110+ ^T moves focus into
    the results column."""
    await success(pilot)
    app = pilot.app
    if app._is_wide() or not app._results_view_open():
        await pilot.press("ctrl+t")
    await settle(pilot)


SCENES: Dict[str, Callable[[Pilot], Awaitable[None]]] = {
    "step1_data": step_data,
    "step1_data_loaded": step_data_loaded,
    "step2_entity": step_entity,
    "step3_analysis_share": step_analysis,
    "step3_analysis_rate": step_analysis_rate,
    "step4_privacy": step_privacy,
    "step5_review": step_review,
    "review_blocked": review_blocked,
    "expert": expert,
    "reset_dialog": reset_dialog,
    "consent": consent,
    "clearing_spend": clearing_spend,
    "validation": validation,
    "running": running,
    "success": success,
    "withheld": withheld,
    "blocked": blocked,
    "results_view": results_view,
}


# Review-only: the unexpected-error log holds a traceback with this
# machine's paths, so it is captured for the heuristic review, not snapshotted.
REVIEW_ONLY_SCENES: Dict[str, Callable[[Pilot], Awaitable[None]]] = {
    "unexpected_error": unexpected_error,
}


def release_running() -> None:
    """Let a ``running`` scene's stub engine finish (call after the snapshot)."""
    RELEASE.set()


__all__ = ["SCENES", "install_determinism", "release_running", "until", "asyncio"]
