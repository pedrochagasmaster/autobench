"""TUI redesign Phase 2 PR 6: verification gaps.

The Citibank entity readiness blocker (schema v4 ``citi_entity_missing``),
the dimensions list sized to its content, and the Review step's file name.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import List, Tuple

import pytest
from textual.pilot import Pilot
from textual.widgets import Select

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
