"""TUI redesign Phase 2 PR 4: the layout shell.

Step rail states, Tab flowing across steps, command-palette step jumps
(owner decision 7: no step keys), Ctrl+R jumping to the first blocker, the
action bar's Cancel with schema v3 telemetry, the results column (110+
columns) versus the Ctrl+T view (80x24), Copy path, and reachability.
"""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from typing import List, Tuple

import pytest
import yaml
from textual.geometry import Region
from textual.pilot import Pilot
from textual.widgets import Button, Checkbox, Input, Select, Static

import tui_app
from tui import status as tui_status
from core.analysis_run import RunCancelled
from core.contracts import AnalysisArtifacts, PrivacyOutputDecision
from tui.actionbar import ActionBar
from tui.commands import AutobenchCommands
from tui.rail import ATTENTION, DONE, PENDING, RESTORED, STEPS, StepRail
from tui.readiness import launch_blockers
from tui.expert import ExpertScreen
from tui_app import SELECT_BLANK, BenchmarkApp, ClearingSpendConfirmScreen, RunInputs

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "gate_demo.csv"
REPORT = "/home/analyst/work/outputs/benchmark_share_Target_20261014_101530.xlsx"


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


async def _until(pilot: Pilot, predicate, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            return False
        await pilot.pause(0.05)
    return True


async def _load(pilot: Pilot) -> None:
    app = pilot.app
    app.query_one("#csv_path", Input).value = str(FIXTURE)
    app.load_csv_headers(str(FIXTURE), announce=False)
    await pilot.pause()
    assert await _until(pilot, lambda: not app.entity_values_loading)
    # PR 5: the form model is the source of truth; step widgets bind to it.
    app.form.validate_input = False
    await pilot.pause()


async def _ready_share_form(pilot: Pilot) -> None:
    await _load(pilot)
    app = pilot.app
    app.form.update(entity="Target", metric="txn_cnt", dimensions=("card_type",))
    await pilot.pause()


def _success(request, logger, **_kwargs):
    return AnalysisArtifacts(
        metadata={},
        compliance_summary={"posture": "strict", "compliance_verdict": "fully_compliant",
                            "acknowledgement_state": "not_required"},
        report_paths=[REPORT],
        privacy_output_decision=PrivacyOutputDecision(True, False, None),
        privacy_sink_authorized=True,
        privacy_log_authorized=True,
    )


def _rail(app: BenchmarkApp) -> StepRail:
    return app.query_one("#step_rail", StepRail)


# ── Rail ────────────────────────────────────────────────────────────────────


def test_only_step_one_is_mounted_and_each_step_mounts_on_first_show() -> None:
    """03 §1.1 (PR 5): startup lays out step 1 only; a step mounts when first shown."""

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(80, 24)) as pilot:
            app = pilot.app
            await pilot.pause()
            for step in STEPS:
                body = app.query_one(f"#{step.container_id}")
                assert body.display is (step.id == "data"), step.id
                assert bool(body.children) is (step.id == "data"), step.id
            app.query_one("#csv_path")
            assert not app.query("#entity_name") and not app.query("#preset_select")
            app.action_go_to_step("privacy")
            assert await _until(pilot, lambda: "privacy" in app._ready_steps)
            await pilot.pause()
            shown = [step.id for step in STEPS if app.query_one(f"#{step.container_id}").display]
            assert shown == ["privacy"]
            assert app.focused is not None and app.focused.id == "preset_select"
            assert not app.query("#entity_name")  # step 2 was never shown
            # Every field keeps its id once its step is mounted.
            for step in STEPS:
                await app.ensure_step(step.id)
            for widget_id in ("csv_path", "entity_name", "dims", "share_metric", "preset_select",
                              "privacy_release_mode", "citibank_entity_name", "btn_run"):
                app.query_one(f"#{widget_id}")
            # Step 3 mounts the active mode's fields; the other mode's mount
            # on the first switch.
            assert not app.query("#rate_total")
            app.form.mode = "rate"
            await app.ensure_step("analysis")
            app.query_one("#rate_total")
            # Expert fields left the main screen for the Expert settings screen (F8).
            assert not app.query("#adv_lp_tolerance")
            await pilot.press("f8")
            assert await _until(pilot, lambda: isinstance(app.screen, ExpertScreen))
            await pilot.pause()
            app.screen.query_one("#adv_lp_tolerance", Input)

    asyncio.run(scenario())


def test_rail_states_follow_the_form_and_launch_guards() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(80, 24)) as pilot:
            app = pilot.app
            await pilot.pause()
            rail = _rail(app)
            # Launch: no file. Data and Review need attention; nothing to
            # choose on Entity/Analysis yet; Privacy has its preset default.
            assert rail.current == "data"
            assert rail.states == {
                "data": ATTENTION, "entity": PENDING, "analysis": PENDING,
                "privacy": DONE, "review": ATTENTION,
            }
            text = rail.visible_text
            assert "\n" not in text and len(text) <= 80
            assert text.startswith("▸! 1 Data")
            for number in "12345":
                assert f" {number} " in text

            await _load(pilot)
            await pilot.pause()
            # Loaded, but no dimensions chosen yet: Analysis needs attention.
            assert rail.states["data"] == DONE
            assert rail.states["analysis"] == ATTENTION
            assert rail.states["review"] == ATTENTION
            app.form.dimensions = ("card_type",)
            await pilot.pause()
            await pilot.pause()
            assert set(rail.states.values()) == {DONE}

            app.action_go_to_step("analysis")
            await pilot.pause()
            assert rail.current == "analysis"
            assert "▸✓ 3 Analysis & mode" in rail.visible_text

    asyncio.run(scenario())


def test_rail_marks_restored_steps_and_never_restores_declarations(tmp_path: Path) -> None:
    session = {
        "analysis_mode": "share",
        "preset_select": "compliance_strict",
        "share_dims": ["card_type"],
        "share_metric": "txn_cnt",
        # A legacy session must never bring these back.
        "privacy_merchant_spend_scope": True,
        "citi_competitor_receives_output": True,
        "citibank_entity_name": "Citibank N.A.",
        "entity_name": "Target",
    }
    tui_app.SESSION_FILE.write_text(yaml.safe_dump(session), encoding="utf-8")

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            app = pilot.app
            await pilot.pause()
            await _load(pilot)
            await pilot.pause()
            for step in ("entity", "privacy", "review"):
                await app.ensure_step(step)
            states = _rail(app).states
            assert states["analysis"] == RESTORED
            assert states["privacy"] == RESTORED
            assert "↺ Restored from the last session" in str(app.query_one("#review_summary", Static).content)
            assert app.query_one("#privacy_merchant_spend_scope", Checkbox).value is False
            assert app.query_one("#citi_competitor_receives_output", Checkbox).value is False
            # PR 5: the Citibank entity is a Select over the entity values.
            assert app.query_one("#citibank_entity_name", Select).value == SELECT_BLANK
            assert app.query_one("#entity_name", Select).value == SELECT_BLANK
            assert app.form.citibank_entity is None and app.form.entity is None
            assert not app.form.merchant_spend and not app.form.citi_competitor

    asyncio.run(scenario())


def test_rail_click_goes_to_the_step() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            app = pilot.app
            await pilot.pause()
            text = _rail(app).visible_text
            await pilot.click("#step_rail", offset=(text.index("4 Privacy") + 1, 0))
            assert await _until(pilot, lambda: app.focused is not None and app._step_of(app.focused) == "privacy")
            assert app._current_step == "privacy"
            assert app._step_of(app.focused) == "privacy"

    asyncio.run(scenario())


# ── Tab flow across steps ───────────────────────────────────────────────────


def test_tab_flows_from_the_last_field_of_a_step_into_the_next() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(80, 24)) as pilot:
            app = pilot.app
            await pilot.pause()
            assert app.focused.id == "csv_path"  # last stop of step 1
            await pilot.press("tab")
            await pilot.pause()
            assert app._current_step == "entity"
            assert app.focused.id == "entity_col"
            assert not app.query_one("#step_data").display
            await pilot.press("shift+tab")
            await pilot.pause()
            assert app._current_step == "data"
            assert app.focused.id == "csv_path"
            # Review wraps to Data.
            app.action_go_to_step("review")
            await pilot.pause()
            chain = app._step_focus_chain("review")
            chain[-1].focus()
            await pilot.pause()
            await pilot.press("tab")
            await pilot.pause()
            assert app._current_step == "data"
            assert app.focused.id == "btn_browse_csv"

    asyncio.run(scenario())


def test_forward_tab_alone_reaches_every_field_at_80x24() -> None:
    """Nothing is unreachable: one Tab cycle visits every enabled form field."""

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(80, 24)) as pilot:
            app = pilot.app
            await pilot.pause()
            await _load(pilot)
            for step in STEPS:
                await app.ensure_step(step.id)
            await app.open_more_options()
            app.action_go_to_step("data")
            app.query_one("#btn_browse_csv").focus()
            await pilot.pause()
            expected = set()
            for step in STEPS:
                body = app.query_one(f"#{step.container_id}")
                for widget in body.query("Input, Select, Checkbox, Button, SelectionList, ModeSwitch, OptionList"):
                    hidden = any(
                        not node.display for node in widget.ancestors_with_self
                        if node is not body and node is not app
                    ) or widget.has_class("hidden")
                    if widget.disabled or hidden or not widget.can_focus:
                        continue
                    expected.add(widget)
            seen = set()
            screen = Region(0, 0, 80, 24)
            for _ in range(len(expected) * 2 + 10):
                focused = app.focused
                seen.add(focused)
                # Every focused field is on screen (its step shown, scrolled to).
                assert focused.region.area > 0 and screen.contains_region(focused.region), focused
                await pilot.press("tab")
                await pilot.pause()
                if app.focused.id == "btn_browse_csv":
                    break
            missing = {w.id or repr(w) for w in expected - seen}
            assert not missing, missing
            assert {app._step_of(w) for w in seen} == {step.id for step in STEPS}

    asyncio.run(scenario())


# ── Command palette: the only step jump ─────────────────────────────────────


def test_no_step_keys_and_palette_lists_every_step() -> None:
    keys = {binding.key for binding in BenchmarkApp.BINDINGS}
    assert not any(key in keys for key in ("f2", "f3", "f4", "f5", "f6"))
    assert not any(key.startswith("alt+") for key in keys)
    assert AutobenchCommands in BenchmarkApp.COMMANDS

    async def scenario() -> list:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            provider = AutobenchCommands(pilot.app.screen)
            return [hit.text async for hit in provider.discover()]

    names = asyncio.run(scenario())
    assert [n for n in names if n.startswith("Go to step: ")] == [
        "Go to step: 1 Data",
        "Go to step: 2 Entity",
        "Go to step: 3 Analysis & mode",
        "Go to step: 4 Privacy & compliance",
        "Go to step: 5 Review & run",
    ]


def test_palette_go_to_step_jumps_and_focuses_the_first_blocker() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(80, 24)) as pilot:
            app = pilot.app
            await pilot.pause()
            await _load(pilot)
            await pilot.press("ctrl+p")
            await pilot.pause()
            await pilot.press(*"step: analysis")
            await pilot.pause(0.5)  # the palette searches in a worker
            await pilot.press("enter")
            assert await _until(pilot, lambda: app._current_step == "analysis")
            await pilot.pause()
            # No dimensions yet: the step's first blocker gets focus.
            assert await _until(pilot, lambda: app.focused is not None and app.focused.id == "dims")
            # A step without blockers focuses its first field.
            await pilot.press("ctrl+p")
            await pilot.pause()
            await pilot.press(*"step: privacy")
            await pilot.pause(0.5)
            await pilot.press("enter")
            assert await _until(pilot, lambda: app._current_step == "privacy")
            assert await _until(pilot, lambda: app.focused is not None and app.focused.id == "preset_select")

    asyncio.run(scenario())


# ── Ctrl+R from any step ────────────────────────────────────────────────────


def test_ctrl_r_jumps_to_the_first_blocker_and_says_why(telemetry_calls) -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(80, 24)) as pilot:
            app = pilot.app
            await pilot.pause()
            await _load(pilot)
            app.form.update(mode="rate", dimensions=("card_type",))
            app.action_go_to_step("review")
            await pilot.pause()
            await pilot.pause()
            bar = app.query_one("#action_bar", ActionBar)
            assert bar.state == "notready"
            assert bar.message.startswith("Total column is required for rate analysis.")
            assert bar.key_text == "^R Run rate analysis"
            await pilot.press("ctrl+r")
            assert await _until(pilot, lambda: app.focused is not None and app.focused.id == "rate_total")
            await pilot.pause()
            assert app._current_step == "analysis"
            assert app._run_state == "idle"
            assert app.query_one("#rate_total").region.area > 0
            assert bar.message.startswith("Total column is required for rate analysis.")
            assert "(+1 more)" in bar.message  # approved/fraud missing too

    asyncio.run(scenario())
    assert telemetry_calls == [("blocked", ("rate_analysis", "total_missing"))]


def test_readiness_is_the_launch_guard_function() -> None:
    """The action bar and the worker share one guard list, in guard order."""
    base = dict(
        mode="share", csv_path="", entity_selection_pending=True, entity="x",
        entity_error="Target entity not found in issuer_name.", entity_col="issuer_name",
        preset=None, config=None, compliance_posture=None, output=None, time_col=None,
        validate_input=False, analyze_distortion=False, compare_presets=False,
        include_calculated=False, output_format="analysis", privacy_values=(),
    )
    blockers = launch_blockers(RunInputs(**base))
    assert [b.reason for b in blockers] == [
        "csv_missing", "entity_loading", "entity_not_found", "metric_missing", "dimensions_missing",
    ]
    rate = launch_blockers(RunInputs(**{**base, "mode": "rate", "csv_path": "x.csv",
                                        "entity_selection_pending": False, "entity_error": None,
                                        "dimensions": ("a",)}))
    assert [(b.reason, b.focus_id) for b in rate] == [
        ("total_missing", "rate_total"), ("rate_column_missing", "rate_approved"),
    ]


# ── Cancel through the action bar (schema v3) ───────────────────────────────


def test_ctrl_g_in_the_clearing_spend_dialog_cancels_before_the_run(tmp_path, telemetry_calls) -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(80, 24)) as pilot:
            app = pilot.app
            await pilot.pause()
            await _load(pilot)
            app.form.mode = "rate"
            await pilot.pause()
            app.form.update(
                total_col="total", fraud_col="fraud", dimensions=("card_type",),
                output_file=str(tmp_path / "rate.xlsx"),
            )
            await pilot.pause()
            app.run_analysis()
            assert await _until(pilot, lambda: isinstance(app.screen, ClearingSpendConfirmScreen))
            await pilot.pause()
            bar = app.query_one("#action_bar", ActionBar)
            # D3 still holds: the dialog opens on Cancel.
            assert app.focused.id == "btn_confirm_no"
            await pilot.press("ctrl+g")
            assert await _until(pilot, lambda: app._run_state == "cancelled")
            await pilot.pause()
            assert not isinstance(app.screen, ClearingSpendConfirmScreen)
            assert bar.state == "cancelled"
            assert not (tmp_path / "rate.xlsx").exists()

    asyncio.run(scenario())
    # The visible cancel, not a clearing-spend decline, and never both.
    assert telemetry_calls == [("cancelled", ("rate_analysis", "cancel_before_run"))]


def test_action_bar_cancel_during_the_engine_records_cancel_during_run(
    monkeypatch: pytest.MonkeyPatch, telemetry_calls
) -> None:
    def fake_execute_run(request, logger, *, cancel_requested, on_stage):
        on_stage("analysis")
        deadline = time.monotonic() + 20
        while not cancel_requested():
            if time.monotonic() > deadline:
                raise AssertionError("cancel never requested")
            time.sleep(0.01)
        raise RunCancelled("analysis")

    monkeypatch.setattr(tui_app, "execute_run", fake_execute_run)

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            app = pilot.app
            await pilot.pause()
            await _ready_share_form(pilot)
            app.run_analysis()
            bar = app.query_one("#action_bar", ActionBar)
            assert await _until(pilot, lambda: bar.key_text == "^G Cancel run" and app._run_stage == "analysis")
            assert bar.state == "running"
            await pilot.click("#action_key")  # the action bar's Cancel
            assert await _until(pilot, lambda: app._run_state == "cancelled")
            await pilot.pause()
            assert bar.state == "cancelled"
            assert "nothing was written" in str(app.query_one("#results_panel", Static).content)

    asyncio.run(scenario())
    assert telemetry_calls == [("cancelled", ("share_analysis", "cancel_during_run"))]


def test_cancel_is_unavailable_while_writing_outputs(monkeypatch: pytest.MonkeyPatch, telemetry_calls) -> None:
    release = threading.Event()

    def fake_execute_run(request, logger, *, cancel_requested, on_stage):
        on_stage("output")
        release.wait(20)
        return _success(request, logger)

    monkeypatch.setattr(tui_app, "execute_run", fake_execute_run)

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(80, 24)) as pilot:
            app = pilot.app
            await pilot.pause()
            await _ready_share_form(pilot)
            app.run_analysis()
            bar = app.query_one("#action_bar", ActionBar)
            assert await _until(pilot, lambda: app._run_stage == "output")
            await pilot.pause()
            assert bar.key_text == "Cancel unavailable: writing outputs"
            await pilot.press("ctrl+g")
            await pilot.pause()
            assert not app.cancel_requested
            release.set()
            assert await _until(pilot, lambda: app._run_state == "success")

    asyncio.run(scenario())
    assert telemetry_calls == []


# ── Results: column at 110+, Ctrl+T view below; Copy path ───────────────────


def _screen_text(app: BenchmarkApp) -> str:
    """Plain text of what is on screen now (the exported screenshot)."""
    import re as _re
    svg = app.export_screenshot()
    text = _re.sub(r"<[^>]+>", "", svg)
    return text.replace("&#160;", " ").replace("&amp;", "&")


def test_results_column_at_120x40_and_ctrl_t_view_at_80x24(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tui_app, "execute_run", _success)

    async def run(size: Tuple[int, int]) -> dict:
        out: dict = {}
        async with BenchmarkApp().run_test(size=size) as pilot:
            app = pilot.app
            await pilot.pause()
            pane = app.query_one("#activity_pane")
            setup = app.query_one("#setup_pane")
            out["idle_pane"] = pane.region.width
            await _ready_share_form(pilot)
            app.run_analysis()
            assert await _until(pilot, lambda: app._run_state == "success")
            await pilot.pause(0.3)
            out["pane_width"] = pane.region.width
            out["setup_width"] = setup.region.width
            screen = Region(0, 0, *size)
            verdict = app.query_one("#results_badges")
            path = app.query_one("#results_path", Static)
            panel = app.query_one("#results_panel", Static)
            out["verdict_visible"] = screen.contains_region(verdict.region) and verdict.region.area > 0
            out["path_visible"] = screen.contains_region(path.region) and path.region.area > 0
            out["panel_visible"] = screen.contains_region(panel.region)
            out["path_text"] = str(path.content)
            out["copy_focused"] = app.focused is not None and app.focused.id == "btn_copy_path"
            out["text"] = _screen_text(app)
            await pilot.press("ctrl+y")
            await pilot.pause()
            out["clipboard"] = app.clipboard
            await pilot.press("ctrl+t")
            await pilot.pause()
            out["after_t_pane"] = pane.region.width
            out["after_t_setup"] = setup.region.width
            out["after_t_focus_step"] = app._step_of(app.focused) if app.focused else None
            await pilot.press("ctrl+t")
            await pilot.pause()
            out["after_tt_pane"] = pane.region.width
        return out

    wide = asyncio.run(run((120, 40)))
    assert wide["idle_pane"] == tui_app.RESULTS_COLUMN_WIDTH
    assert wide["pane_width"] == tui_app.RESULTS_COLUMN_WIDTH and wide["setup_width"] == 78
    assert wide["verdict_visible"] and wide["path_visible"]
    assert not wide["copy_focused"]  # ≥110: focus stays in the form
    assert wide["clipboard"] == REPORT
    assert wide["after_t_setup"] == 78  # ^T only moves focus at 110+

    narrow = asyncio.run(run((80, 24)))
    assert narrow["idle_pane"] == 0  # hidden until a run or ^T
    assert narrow["pane_width"] == 80 and narrow["setup_width"] == 0
    # T1: the verdict and the whole report path are on screen at 80x24.
    assert narrow["verdict_visible"] and narrow["path_visible"] and narrow["panel_visible"]
    assert narrow["path_text"] == REPORT
    flat = narrow["text"].replace("\n", "")
    assert "COMPLIANT" in flat and "Privacy checks passed" in flat
    assert narrow["copy_focused"]
    assert narrow["clipboard"] == REPORT
    assert narrow["after_t_pane"] == 0 and narrow["after_t_setup"] == 80
    assert narrow["after_t_focus_step"] is not None
    assert narrow["after_tt_pane"] == 80


def test_results_view_opens_when_a_run_starts_at_80x24(monkeypatch: pytest.MonkeyPatch) -> None:
    release = threading.Event()

    def slow(request, logger, *, cancel_requested, on_stage):
        on_stage("analysis")
        release.wait(20)
        return _success(request, logger)

    monkeypatch.setattr(tui_app, "execute_run", slow)

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(80, 24)) as pilot:
            app = pilot.app
            await pilot.pause()
            await _ready_share_form(pilot)
            app.run_analysis()
            assert await _until(pilot, lambda: app._run_state == "running")
            await pilot.pause()
            assert app._results_view_open()
            assert app.query_one("#setup_pane").region.width == 0
            # No hidden field keeps focus while the setup view is gone.
            assert app.focused is None or app._step_of(app.focused) is None
            release.set()
            assert await _until(pilot, lambda: app._run_state == "success")

    asyncio.run(scenario())


def test_copy_path_without_a_run_explains_instead_of_copying() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(80, 24)) as pilot:
            app = pilot.app
            await pilot.pause()
            await pilot.press("ctrl+y")
            await pilot.pause()
            assert app.clipboard == ""
            assert app.query_one("#results_copy").has_class("hidden")

    asyncio.run(scenario())


def test_header_keeps_the_release_title_and_ctrl_c_still_quits() -> None:
    async def scenario() -> bool:
        async with BenchmarkApp().run_test(size=(80, 24)) as pilot:
            app = pilot.app
            await pilot.pause()
            assert "Privacy-Compliant Peer Benchmark" in _screen_text(app)
            await pilot.press("escape", "ctrl+c")
            await pilot.pause()
            return bool(app._exit)

    assert asyncio.run(scenario())


def test_new_global_keys_are_free_in_text_fields() -> None:
    """^G, ^T and ^Y reach the app from a focused Input (no stock binding)."""
    from textual.widgets import Input as _Input

    bound = {b.key if hasattr(b, "key") else b[0] for b in _Input.BINDINGS}
    for key in ("ctrl+g", "ctrl+t", "ctrl+y"):
        assert not any(key in str(k).split(",") for k in bound), key
    priority = {b.key: b.priority for b in BenchmarkApp.BINDINGS}
    assert priority["ctrl+g"] and priority["ctrl+t"] and priority["ctrl+y"]


def test_review_summarises_the_current_form() -> None:
    async def scenario() -> str:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            app = pilot.app
            await pilot.pause()
            await _ready_share_form(pilot)
            # PR 6: ticking Citi needs the Citibank entity to be ready.
            app.form.update(citi_competitor=True, citibank_entity="P1")
            app.action_go_to_step("review")
            await app.ensure_step("review")
            await pilot.pause()
            await pilot.pause()
            return str(app.query_one("#review_status", Static).content) + "\n" + str(
                app.query_one("#review_summary", Static).content
            )

    text = asyncio.run(scenario())
    assert "Ready to run share analysis" in text
    assert "issuer_name → Target" in text
    assert "metric txn_cnt" in text and "dims card_type" in text
    assert "Citi competitor: Yes (P1)" in text


def test_review_button_still_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tui_app, "execute_run", _success)

    async def scenario() -> str:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            app = pilot.app
            await pilot.pause()
            await _ready_share_form(pilot)
            app.action_go_to_step("review")
            await app.ensure_step("review")
            await pilot.pause()
            app.query_one("#btn_run", Button).press()
            assert await _until(pilot, lambda: app._run_state == "success")
            return app.query_one("#action_bar", ActionBar).message

    message = asyncio.run(scenario())
    assert REPORT in message and "Privacy checks passed" in message
