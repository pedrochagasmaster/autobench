"""TUI redesign Phase 2 PR 6: verification gaps.

The Citibank entity readiness blocker (schema v4 ``citi_entity_missing``),
the dimensions list sized to its content, the Review step's file name, the
CSV picker's quick picks off the UI thread and background step mounts that
wait for quiet input.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import List, Tuple

import pytest
from textual.pilot import Pilot
from textual.widgets import OptionList, Select, SelectionList, Static

import tui_app
from tui import status as tui_status
from tui.actionbar import ActionBar
from tui.rail import ATTENTION, StepRail
from tui.readiness import launch_blockers
from tui_app import BenchmarkApp, RunInputs

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "gate_demo.csv"


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tui_app, "SESSION_FILE", tmp_path / "session.yaml")
    monkeypatch.setenv("AUTOBENCH_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.chdir(tmp_path)
    tui_status.set_ascii_glyphs(False)
    yield
    tui_status.set_ascii_glyphs(None)


@pytest.fixture
def telemetry_calls(monkeypatch: pytest.MonkeyPatch) -> List[Tuple[str, tuple]]:
    calls: List[Tuple[str, tuple]] = []
    monkeypatch.setattr(tui_app, "action_cancelled", lambda a, p: calls.append(("cancelled", (a, p))))
    monkeypatch.setattr(tui_app, "launch_blocked", lambda a, r: calls.append(("blocked", (a, r))))
    return calls


@pytest.fixture
def engine_calls(monkeypatch: pytest.MonkeyPatch) -> list:
    calls: list = []
    monkeypatch.setattr(tui_app, "execute_run", lambda *a, **k: calls.append(a))
    return calls


async def _until(pilot: Pilot, predicate, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            return False
        await pilot.pause(0.05)
    return True


async def _load(pilot: Pilot, path: Path = FIXTURE) -> None:
    app = pilot.app
    app.form.csv_path = str(path)
    app.load_csv_headers(str(path), announce=False)
    await pilot.pause()
    assert await _until(pilot, lambda: not app.entity_values_loading)
    app.form.validate_input = False
    await pilot.pause()


def _inputs(**overrides) -> RunInputs:
    base = dict(
        mode="share", csv_path="x.csv", entity_selection_pending=False, entity=None,
        entity_error=None, entity_col="issuer_name", preset=None, config=None,
        compliance_posture=None, output=None, time_col=None, validate_input=False,
        analyze_distortion=False, compare_presets=False, include_calculated=False,
        output_format="analysis", privacy_values=(), metric="txn_cnt", dimensions=("card_type",),
    )
    base.update(overrides)
    return RunInputs(**base)


CITI_MESSAGE = "Choose the Citibank entity, or untick “A Citi competitor will receive this output”."


# ── Citibank entity readiness (schema v4) ───────────────────────────────────


def test_citi_ticked_without_entity_is_a_readiness_blocker() -> None:
    ticked = (("citi_competitor_receives_output", True), ("citibank_entity_name", None))
    blockers = launch_blockers(_inputs(privacy_values=ticked))
    assert [(b.reason, b.focus_id, b.message) for b in blockers] == [
        ("citi_entity_missing", "citibank_entity_name", CITI_MESSAGE)
    ]
    # Large lists show the filter instead of the Select: focus the visible field.
    large = launch_blockers(_inputs(privacy_values=ticked, entity_large_list=True))
    assert [(b.reason, b.focus_id) for b in large] == [("citi_entity_missing", "citibank_entity_filter")]
    # Rate runs need it too (core refuses both modes).
    rate = launch_blockers(
        _inputs(mode="rate", metric=None, total_col="total", approved_col="approved", privacy_values=ticked)
    )
    assert [b.reason for b in rate] == ["citi_entity_missing"]


def test_citi_blocker_clears_with_an_entity_or_unticked() -> None:
    chosen = (("citi_competitor_receives_output", True), ("citibank_entity_name", "Citibank N.A."))
    assert launch_blockers(_inputs(privacy_values=chosen)) == ()
    unticked = (("citi_competitor_receives_output", False), ("citibank_entity_name", None))
    assert launch_blockers(_inputs(privacy_values=unticked)) == ()
    # Guard order: the Citibank check (privacy step) comes after the analysis checks.
    both = launch_blockers(
        _inputs(dimensions=(), privacy_values=(("citi_competitor_receives_output", True),))
    )
    assert [b.reason for b in both] == ["dimensions_missing", "citi_entity_missing"]


def test_citi_ticked_blank_entity_says_why_and_jumps_to_the_field(telemetry_calls, engine_calls) -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(80, 24)) as pilot:
            app = pilot.app
            await pilot.pause()
            await _load(pilot)
            app.form.update(entity="Target", metric="txn_cnt", dimensions=("card_type",), citi_competitor=True)
            await pilot.pause()
            await pilot.pause()
            bar = app.query_one("#action_bar", ActionBar)
            assert await _until(pilot, lambda: bar.message.startswith(CITI_MESSAGE))
            rail = app.query_one(StepRail)
            assert await _until(pilot, lambda: rail.states.get("privacy") == ATTENTION)
            await pilot.press("ctrl+r")
            assert await _until(pilot, lambda: app.focused is not None and app.focused.id == "citibank_entity_name")
            assert app._current_step == "privacy"
            assert app._run_state == "idle"
            assert app.query_one("#citibank_entity_name", Select).region.area > 0
            # Choosing the entity makes the form ready again.
            app.query_one("#citibank_entity_name", Select).value = "P1"
            await pilot.pause()
            assert await _until(pilot, lambda: not bar.message.startswith(CITI_MESSAGE))
            assert app.form.citibank_entity == "P1"
            assert launch_blockers(app._collect_run_inputs(resolve_config=False)) == ()

    asyncio.run(scenario())
    # Recorded before any attempt; core was never called.
    assert telemetry_calls == [("blocked", ("share_analysis", "citi_entity_missing"))]
    assert engine_calls == []


# ── PR 5 gaps: dimensions list, Review file name ────────────────────────────


def test_dimensions_list_is_sized_to_its_options_up_to_a_cap(tmp_path: Path) -> None:
    async def scenario() -> Tuple[int, int, int]:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            app = pilot.app
            await pilot.pause()
            await _load(pilot)
            await app.ensure_step("analysis")
            app._show_step("analysis", focus="dims")
            await pilot.pause(0.3)
            dims = app.query_one("#dims", SelectionList)
            return dims.option_count, dims.outer_size.height, dims.max_scroll_y

    count, height, max_scroll = asyncio.run(scenario())
    # gate_demo.csv offers 6 dimension candidates: all visible, no scrolling.
    assert count == 6
    assert height == count + 2  # options plus the border
    assert max_scroll == 0

    wide = tmp_path / "wide.csv"
    columns = ["issuer_name", "txn_cnt"] + [f"dim_{i:02d}" for i in range(20)]
    wide.write_text(",".join(columns) + "\n" + ",".join(["A", "1"] + ["x"] * 20) + "\n", encoding="utf-8")

    async def capped() -> Tuple[int, int]:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            app = pilot.app
            await pilot.pause()
            await _load(pilot, wide)
            await app.ensure_step("analysis")
            app._show_step("analysis", focus="dims")
            await pilot.pause(0.3)
            dims = app.query_one("#dims", SelectionList)
            return dims.outer_size.height, dims.max_scroll_y

    height, max_scroll = asyncio.run(capped())
    assert height == 10  # $ab-multi-max-rows
    assert max_scroll > 0


def test_review_shows_the_file_name_and_the_log_keeps_the_full_path(
    monkeypatch: pytest.MonkeyPatch, engine_calls
) -> None:
    async def scenario() -> Tuple[str, List[str]]:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            app = pilot.app
            await pilot.pause()
            await _load(pilot)
            app.form.update(entity="Target", metric="txn_cnt", dimensions=("card_type",))
            await app.ensure_step("review")
            app._show_step("review")
            await pilot.pause(0.2)
            review = str(app.query_one("#review_summary", Static).content)
            app.run_analysis()
            assert await _until(pilot, lambda: bool(engine_calls) or app._run_state in ("error", "success"))
            return review, [str(line) for line in app.query_one("#log_output").lines]

    review, log_lines = asyncio.run(scenario())
    data_line = next(line for line in review.splitlines() if line.startswith("Data"))
    assert "gate_demo.csv · 8 columns" in data_line
    assert str(FIXTURE.parent) not in review
    assert f"Input file: {FIXTURE}" in log_lines


# ── Performance gaps ───────────────────────────────────────────────────────


def test_picker_gathers_quick_picks_off_the_ui_thread(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ctrl+O never globs and stats the folder on the UI thread (PR 6)."""
    import threading

    for index in range(3):
        (tmp_path / f"file_{index}.csv").write_text("a\n1\n", encoding="utf-8")
    threads: List[bool] = []
    real = BenchmarkApp._quick_pick_files

    def tracking(self, root=None):
        threads.append(threading.current_thread() is threading.main_thread())
        return real(self, root)

    monkeypatch.setattr(BenchmarkApp, "_quick_pick_files", tracking)

    async def scenario() -> Tuple[int, str]:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            app = pilot.app
            await pilot.pause()
            await pilot.press("ctrl+o")
            assert await _until(pilot, lambda: isinstance(app.screen, tui_app.CsvPickerScreen))
            screen = app.screen
            assert await _until(pilot, lambda: screen._quick_loaded)
            await pilot.pause()
            quick = screen.query_one("#picker_quick_list", OptionList)
            return quick.option_count, getattr(app.focused, "id", "")

    count, focused = asyncio.run(scenario())
    assert threads == [False]
    assert count == 3
    assert focused == "picker_quick_list"


def test_background_step_mount_waits_for_quiet_input() -> None:
    async def scenario() -> Tuple[bool, bool]:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            app = pilot.app
            await pilot.pause()
            assert "entity" not in app._mounted_steps  # only step 1 at startup
            app._last_input_at = time.monotonic()
            app._prewarm_next_step()
            deferred = "entity" not in app._mounted_steps
            app._last_input_at = time.monotonic() - 10
            app._prewarm_next_step()
            return deferred, "entity" in app._mounted_steps

    deferred, mounted = asyncio.run(scenario())
    assert deferred and mounted


def test_cancelling_the_validation_review_puts_focus_back(monkeypatch: pytest.MonkeyPatch, engine_calls) -> None:
    """Escape on the validation dialog returns to the field that had focus.

    Found by tui_journeys.py J4b in PR 6: the main screen resumed with the
    focus the run lock had disabled, so nothing was focused and Tab started
    from the top of the step.
    """
    from core.data_loader import ValidationIssue, ValidationSeverity

    issues = [ValidationIssue(ValidationSeverity.ERROR, "negative_values", "Column 'txn_cnt' has 1 negative value")]
    monkeypatch.setattr(tui_app, "build_run_config", lambda *a, **k: {})
    monkeypatch.setattr(tui_app, "prepare_run_data", lambda *a, **k: (None, None, "issuer_name", None))
    monkeypatch.setattr(tui_app, "resolve_dimensions", lambda *a, **k: ["card_type"])
    monkeypatch.setattr(tui_app, "validate_analysis_input", lambda **k: (issues, True))

    async def scenario() -> Tuple[str, str]:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            app = pilot.app
            await pilot.pause()
            await _load(pilot)
            app.form.update(entity="Target", metric="txn_cnt", dimensions=("card_type",), validate_input=True)
            await app.ensure_step("analysis")
            app._focus_field("dims")
            assert await _until(pilot, lambda: getattr(app.focused, "id", None) == "dims")
            await pilot.press("ctrl+r")
            assert await _until(pilot, lambda: isinstance(app.screen, tui_app.ValidationModal))
            await pilot.press("escape")
            assert await _until(pilot, lambda: app._run_state == "idle" and app.focused is not None)
            await pilot.pause()
            return getattr(app.focused, "id", ""), app._current_step

    focused, step = asyncio.run(scenario())
    assert (focused, step) == ("dims", "analysis")
    assert engine_calls == []
