"""TUI redesign Phase 2 PR 5: step contents.

The form model and lazy step mounting, the keystroke reductions (focus after a
load, numeric-first column lists, one dimensions list, More options), the
Expert settings screen and its in-memory diff, session restore on the form
model, the Citibank entity chooser, and the polish items (toast policy, the
results card, the run log view, actionable Review blockers, the run lock).
"""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from typing import List

import pytest
import yaml
from textual.pilot import Pilot
from textual.widgets import Button, Checkbox, Collapsible, Input, OptionList, Select, SelectionList, Static
from textual.app import App, ComposeResult
from textual.widgets._select import SelectCurrent, SelectOverlay
from textual.widgets._toast import ToastRack

import tui_app
from core.contracts import AnalysisArtifacts, PrivacyOutputDecision
from tui import status as tui_status
from tui.expert import ExpertScreen
from tui.form_state import (
    NEVER_RESTORED,
    SESSION_KEYS,
    FormState,
    read_session,
    session_payload,
)
from tui.form_widgets import SEPARATOR, ColumnSelect, Disclosure, EntityChooser, ModeSwitch
from tui_app import SELECT_BLANK, BenchmarkApp, ClearingSpendConfirmScreen, ConfirmScreen

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "gate_demo.csv"
SIZE = (120, 40)


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tui_app, "SESSION_FILE", tmp_path / "session.yaml")
    monkeypatch.setenv("AUTOBENCH_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.chdir(tmp_path)
    tui_status.set_ascii_glyphs(False)
    yield
    tui_status.set_ascii_glyphs(None)


async def _until(pilot: Pilot, predicate, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            return False
        await pilot.pause(0.05)
    return True


async def _load(pilot: Pilot, path: Path = FIXTURE, *, focus_next: bool = False) -> None:
    app = pilot.app
    app.form.csv_path = str(path)
    app.load_csv_headers(str(path), focus_next=focus_next)
    await pilot.pause()
    assert await _until(pilot, lambda: not app.entity_values_loading)
    await pilot.pause()


def _option_values(select: Select) -> List[object]:
    return [value for _, value in select._options if value != SELECT_BLANK]


def _success(request, logger, **_kwargs):
    return AnalysisArtifacts(
        metadata={},
        compliance_summary={"posture": "strict", "compliance_verdict": "fully_compliant",
                            "acknowledgement_state": "not_required"},
        report_paths=["/out/report.xlsx"],
        privacy_output_decision=PrivacyOutputDecision(True, False, None),
        privacy_sink_authorized=True,
        privacy_log_authorized=True,
    )


# ── 1. FormState ────────────────────────────────────────────────────────────


def test_form_state_notifies_once_per_real_change_and_normalises() -> None:
    form = FormState()
    seen: list = []
    form.set_listener(lambda name, old, new: seen.append((name, old, new)))
    form.metric = "txn_cnt"
    form.metric = "txn_cnt"  # unchanged: no echo
    form.dimensions = ["a", "b", "a"]  # type: ignore[assignment]
    form.metric = ""  # blank is None
    assert seen == [("metric", None, "txn_cnt"), ("dimensions", (), ("a", "b")), ("metric", "txn_cnt", None)]
    with pytest.raises(AttributeError):
        form.update(not_a_field=1)
    with pytest.raises(ValueError):
        form.mode = "sideways"


def test_one_dimensions_list_hides_the_active_modes_role_columns() -> None:
    form = FormState()
    form.set_columns(
        ["issuer_name", "card_type", "channel", "txn_cnt", "total", "approved", "fraud"],
        ["txn_cnt", "total", "approved", "fraud"],
    )
    form.update(entity_col="issuer_name", metric="txn_cnt", total_col="total", approved_col="approved")
    form.dimensions = ("card_type", "total")
    # Share: the metric is hidden; text columns first, numeric after.
    assert form.dimension_options() == ("card_type", "channel", "total", "approved", "fraud")
    assert form.effective_dimensions() == ("card_type", "total")
    form.mode = "rate"
    # Rate: total/approved are roles, txn_cnt is free again; the stored choice is kept.
    assert form.dimension_options() == ("card_type", "channel", "txn_cnt", "fraud")
    assert form.effective_dimensions() == ("card_type",)
    assert form.dimensions == ("card_type", "total")
    assert form.secondary_options() == ("txn_cnt", "fraud")


def test_sweep_lock_is_share_only_and_keeps_the_operators_value() -> None:
    form = FormState()
    form.release_mode = "verified-safe-coverage"
    assert form.sweep_locked and form.effective_sweep and form.rule_sweep is False
    form.mode = "rate"
    assert not form.sweep_locked and form.effective_sweep is False


def test_session_payload_and_reader_never_carry_governed_values() -> None:
    form = FormState()
    form.update(
        csv_path="/data/secret.csv", output_file="/out/x.xlsx", entity="Target", entity_filter="Tar",
        merchant_spend=True, citi_competitor=True, citibank_entity="Citibank N.A.",
        citibank_filter="citi", expert={"adv_lp_tolerance": "3"}, metric="txn_cnt",
        dimensions=("card_type",), mode="rate",
    )
    payload = session_payload(form, {})
    assert payload["share_metric"] == "txn_cnt"
    assert payload["dimensions"] == ["card_type"]
    assert payload["analysis_mode"] == "rate"
    text = yaml.safe_dump(payload)
    for secret in ("secret.csv", "x.xlsx", "Target", "Tar", "Citibank", "citi", "adv_lp"):
        assert secret not in text
    assert not NEVER_RESTORED & set(SESSION_KEYS)
    restored = read_session(
        {
            "csv_path": "/data/secret.csv",
            "entity_name": "Target",
            "citibank_entity_name": "Citibank N.A.",
            "citi_competitor_receives_output": True,
            "privacy_merchant_spend_scope": True,
            "analysis_mode": "rate",
            "share_dims": ["card_type"],
            "rate_dims": ["channel"],
            "rate_export_csv": True,
        }
    )
    # Legacy per-tab keys map to the merged controls; the active tab wins.
    assert restored == {"mode": "rate", "dimensions": ["channel"], "export_balanced_csv": True}


# ── 1. Lazy mounting and the form as the source of truth ────────────────────


def test_run_inputs_read_the_form_for_steps_never_shown(tmp_path: Path) -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            await _load(pilot)
            app.form.update(mode="rate", total_col="total", fraud_col="fraud", dimensions=("card_type",),
                            output_file="r.xlsx", release_mode="verified-safe-coverage")
            # Steps 3 and 4 were never shown: nothing of theirs is mounted...
            assert not app.query("#rate_total") and not app.query("#preset_select")
            inputs = app._collect_run_inputs(resolve_config=False)
            # ...and the snapshot, readiness and Review still see every value.
            assert (inputs.mode, inputs.total_col, inputs.fraud_col) == ("rate", "total", "fraud")
            assert inputs.dimensions == ("card_type",) and inputs.output == "r.xlsx"
            assert dict(inputs.privacy_values)["privacy_release_mode"] is None  # rate never sends it
            assert app._readiness_blockers() == ()
            # Showing the step mounts its widgets with the form's values.
            app.action_go_to_step("analysis")
            assert await _until(pilot, lambda: "analysis" in app._ready_steps)
            assert app.query_one("#rate_total", Select).value == "total"
            assert app.query_one("#mode_switch", ModeSwitch).mode == "rate"
            assert app.query_one("#dims", SelectionList).selected == ["card_type"]

    asyncio.run(scenario())


def test_widget_edits_reach_the_form_synchronously() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            await _load(pilot)
            await app.ensure_step("analysis")
            app.query_one("#share_metric", Select).value = "total"
            app.query_one("#dims", SelectionList).select("channel")
            app.query_one("#mode_switch", ModeSwitch).mode = "rate"
            # No pause: the form already holds every edit.
            assert app.form.metric == "total"
            assert app.form.dimensions == ("channel",)
            assert app.form.mode == "rate"

    asyncio.run(scenario())


# ── 2. Keystroke reductions ─────────────────────────────────────────────────


@pytest.mark.parametrize("size", [(80, 24), (120, 40)])
def test_enter_on_the_path_moves_focus_to_target_entity(size, tmp_path: Path) -> None:
    async def scenario() -> str:
        async with BenchmarkApp().run_test(size=size) as pilot:
            app = pilot.app
            await pilot.pause()
            app.query_one("#csv_path", Input).value = str(FIXTURE)
            await pilot.press("enter")
            assert await _until(pilot, lambda: app.focused is not None and app.focused.id == "entity_name")
            return app._current_step

    assert asyncio.run(scenario()) == "entity"


def test_enter_on_the_path_focuses_entity_column_when_it_has_no_default(tmp_path: Path) -> None:
    csv = tmp_path / "no_issuer.csv"
    csv.write_text("bank,card_type,txn_cnt\nA,X,1\nB,Y,2\n", encoding="utf-8")

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            app.query_one("#csv_path", Input).value = str(csv)
            await pilot.press("enter")
            assert await _until(pilot, lambda: app.focused is not None and app.focused.id == "entity_col")

    asyncio.run(scenario())


def test_metric_and_total_list_numeric_columns_first_with_text_below_a_separator() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            await _load(pilot)
            await app.ensure_step("analysis")
            app.form.mode = "rate"
            await pilot.pause()
            for widget_id in ("share_metric", "rate_total", "rate_approved", "rate_fraud"):
                select = app.query_one(f"#{widget_id}", ColumnSelect)
                values = _option_values(select)
                assert values == [
                    "txn_cnt", "total", "approved", "fraud", SEPARATOR,
                    "issuer_name", "year_month", "card_type", "channel",
                ], widget_id
                overlay = select.query_one(SelectOverlay)
                assert overlay.get_option_at_index(values.index(SEPARATOR) + 1).disabled
            # Non-numeric columns stay selectable.
            app.query_one("#rate_total", Select).value = "card_type"
            assert app.form.total_col == "card_type"
            # Arrow keys skip the separator row.
            total = app.query_one("#rate_total", ColumnSelect)
            total.value = "fraud"
            total.focus()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("down", "enter")
            await pilot.pause()
            assert total.value == "issuer_name"

    asyncio.run(scenario())


def test_smart_defaults_and_no_total_default() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            csv = Path("defaults.csv")
            csv.write_text("issuer_name,txn_cnt,app_cnt,total,card_type\nA,1,1,1,X\n", encoding="utf-8")
            await _load(pilot, csv)
            assert (app.form.entity_col, app.form.metric, app.form.approved_col) == (
                "issuer_name", "txn_cnt", "app_cnt",
            )
            assert app.form.total_col is None  # owner decision 4

    asyncio.run(scenario())


def test_more_options_is_one_collapsed_disclosure_with_a_change_summary() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(80, 24)) as pilot:
            app = pilot.app
            await pilot.pause()
            await _load(pilot)
            await app.ensure_step("analysis")
            more = app.query_one("#more_options", Collapsible)
            assert more.collapsed and more.title.endswith("all default")
            assert len(app.query_one("#step_analysis").query(Disclosure)) == 1
            app.form.compare_presets = True
            await pilot.pause()
            assert more.title.endswith("1 changed")
            # Its fields mount on first open (03 §1.1), with the form's values.
            assert not app.query("#output_file") and not app.query("#compare_presets")
            # Jumping to a field inside opens the disclosure first.
            app._focus_field("output_file")
            assert await _until(pilot, lambda: app.focused is not None and app.focused.id == "output_file")
            assert not more.collapsed
            assert app.query_one("#compare_presets", Checkbox).value is True
            # Share step 3 stops: mode, metric, dims, auto, More options, Expert.
            more.collapsed = True
            await pilot.pause()
            assert app._current_step == "analysis", (app._current_step, app.focused)
            ids = [w.id or type(w).__name__ for w in app._step_focus_chain("analysis")]
            assert ids == ["mode_switch", "share_metric", "dims", "auto_dim", "CollapsibleTitle", "btn_expert"]

    asyncio.run(scenario())


# ── 3. Expert settings ──────────────────────────────────────────────────────


def test_expert_edits_are_an_in_memory_diff_and_the_posture_line_names_its_source(tmp_path: Path) -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            await app.ensure_step("privacy")
            posture = app.query_one("#posture_line", Static)
            assert "from preset · F1" in str(posture.content)
            await pilot.press("f8")
            assert await _until(pilot, lambda: isinstance(app.screen, ExpertScreen))
            await pilot.pause()
            screen = app.screen
            tolerance = screen.query_one("#adv_lp_tolerance", Input)
            preset_value = tolerance.value
            tolerance.value = "9.5"
            assert app.form.expert == {"adv_lp_tolerance": "9.5"}
            assert "● changed" in str(screen.query_one("#adv_lp_tolerance_source", Static).content)
            assert not list(tmp_path.glob("adv_override_*.yaml"))  # no Apply, no file yet
            tolerance.value = preset_value  # back to the preset value: no change
            assert app.form.expert == {}
            tolerance.value = ""  # blank inherits the preset
            assert app.form.expert == {}
            tolerance.value = "9.5"
            await pilot.press("escape")
            await pilot.pause()
            assert "from preset + 1 expert change" in str(posture.content)
            assert not list(tmp_path.glob("adv_override_*.yaml"))

    asyncio.run(scenario())


def test_f9_export_keeps_todays_file_and_shows_the_full_path(tmp_path: Path) -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=SIZE, notifications=True) as pilot:
            app = pilot.app
            await pilot.pause()
            notices: list = []
            original = app.notify
            app.notify = lambda message, *a, **k: (notices.append(str(message)), original(message, *a, **k))  # type: ignore[method-assign]
            app.form.preset = "balanced_default"
            app.set_expert_value("adv_bounds_max_weight", "3.5")
            await pilot.press("f9")
            await pilot.pause()
            exported = tmp_path / "exported_balanced_default_overrides.yaml"
            assert exported.is_file()
            data = yaml.safe_load(exported.read_text(encoding="utf-8"))
            assert data["version"] == "3.0" and data["compliance_posture"] == "best_effort"
            assert data["optimization"]["bounds"]["max_weight"] == 3.5
            # Preset values travel too, as the old Apply-then-Export file did.
            assert data["optimization"]["bounds"]["min_weight"] is not None
            assert any(str(exported.resolve()) in n for n in notices)
            # From the Expert screen the path is shown on the screen as well.
            await pilot.press("f8")
            assert await _until(pilot, lambda: isinstance(app.screen, ExpertScreen))
            await pilot.press("f9")
            await pilot.pause()
            line = app.screen.query_one("#expert_export_path", Static)
            assert line.display and str(exported.resolve()) in str(line.content)

    asyncio.run(scenario())


# ── 4. Session restore ──────────────────────────────────────────────────────


def test_restored_preset_and_vsc_are_marked_and_clear_restored_resets_them(tmp_path: Path) -> None:
    tui_app.SESSION_FILE.write_text(
        yaml.safe_dump(
            {
                "preset_select": "balanced_default",
                "privacy_release_mode": "verified-safe-coverage",
                "share_metric": "total",
                "privacy_merchant_spend_scope": True,
                "citibank_entity_name": "Citibank N.A.",
            }
        ),
        encoding="utf-8",
    )

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            await _load(pilot)
            for step in ("analysis", "privacy", "review"):
                await app.ensure_step(step)
            await pilot.pause()
            assert app.form.preset == "balanced_default"
            assert app.form.release_mode == "verified-safe-coverage"
            assert app.form.metric == "total"
            assert {"preset", "release_mode", "metric"} <= app.form.restored
            assert str(app.query_one("#lbl_preset_select").content).endswith("↺")
            assert str(app.query_one("#lbl_share_metric").content).endswith("↺")
            assert "↺ restored" in str(app.query_one("#privacy_release_mode_hint", Static).content)
            # Never restored: declarations, the Citibank entity, the target.
            assert not app.form.merchant_spend and app.form.citibank_entity is None
            assert app.form.entity is None
            clear = app.query_one("#btn_clear_restored", Button)
            assert clear.display
            clear.press()
            await pilot.pause()
            assert app.form.restored == set()
            assert app.form.preset == "compliance_strict"
            assert app.form.release_mode == "complete-output"
            assert app.form.metric is None
            assert not str(app.query_one("#lbl_preset_select").content).endswith("↺")

    asyncio.run(scenario())


# ── 5. Citibank entity ──────────────────────────────────────────────────────


def test_citibank_entity_is_a_select_over_the_entity_values(tmp_path: Path) -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            await _load(pilot)
            await app.ensure_step("privacy")
            select = app.query_one("#citibank_entity_name", Select)
            # Disabled (but visible) until the Citi declaration is ticked.
            assert select.disabled and select.display
            app.query_one("#citi_competitor_receives_output", Checkbox).value = True
            await pilot.pause()
            assert not select.disabled
            assert _option_values(select) == ["P1", "P2", "P3", "P4", "P5", "P6", "Target"]
            select.value = "P3"
            values = app._privacy_values()
            assert values["citibank_entity_name"] == "P3"
            assert values["citi_competitor_receives_output"] is True

    asyncio.run(scenario())


def test_citibank_entity_uses_the_large_list_filter_above_the_limit(tmp_path: Path) -> None:
    count = tui_app.ENTITY_SELECT_MAX + 1
    csv = tmp_path / "many.csv"
    lines = ["issuer_name,card_type,txn_cnt"] + [f"BANK_{i:05d},X,{i}" for i in range(count)]
    lines.append("Citibank N.A.,X,1")
    csv.write_text("\n".join(lines) + "\n", encoding="utf-8")

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            await _load(pilot, csv)
            app.form.citi_competitor = True
            await app.ensure_step("privacy")
            await pilot.pause()
            chooser = app.query_one("#citibank_chooser", EntityChooser)
            assert chooser.large
            assert app.query_one("#citibank_entity_name", Select).has_class("hidden")
            entity_filter = app.query_one("#citibank_entity_filter", Input)
            entity_filter.value = "citibank n.a."  # case differs: one exact match
            assert app.form.citibank_entity == "Citibank N.A."
            entity_filter.value = "Citi"  # not a value: nothing is sent
            assert app._privacy_values()["citibank_entity_name"] is None

    asyncio.run(scenario())


# ── 6. Polish ───────────────────────────────────────────────────────────────


def test_toasts_cap_at_two_and_wait_while_a_modal_is_open() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=SIZE, notifications=True) as pilot:
            app = pilot.app
            await pilot.pause()
            for n in range(4):
                app.notify(f"note {n}", timeout=30)
            await pilot.pause()
            assert [n.message for n in app._notifications] == ["note 2", "note 3"]
            app.push_screen(ConfirmScreen("Sure?"))
            await pilot.pause()
            app.notify("while modal", timeout=30)
            await pilot.pause()
            assert "while modal" not in [n.message for n in app._notifications]
            app.screen.query_one("#btn_confirm_no", Button).press()
            assert await _until(pilot, lambda: "while modal" in [n.message for n in app._notifications])
            assert len(list(app._notifications)) <= 2

    asyncio.run(scenario())


def test_toasts_move_off_a_focused_field_in_the_top_right_and_loads_are_not_toasted() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(80, 24), notifications=True) as pilot:
            app = pilot.app
            await pilot.pause()
            await _load(pilot, focus_next=True)
            assert list(app._notifications) == []  # the meta line confirms the load
            rack = app._main_screen.get_child_by_type(ToastRack)
            await app.ensure_step("entity")
            app.query_one("#entity_col").focus()  # row 4, full width: under the toasts
            await pilot.pause()
            assert rack.has_class("-bottom")
            app.query_one("#csv_path").focus()
            # Let that focus event land first, as it would before any real
            # jump; otherwise it can arrive after the jump and switch back.
            await pilot.pause()
            app._focus_field("btn_run")
            assert await _until(
                pilot,
                lambda: app.focused is not None and app.focused.id == "btn_run" and app.focused.region.area > 0,
            )
            app._place_toasts()
            top = app.focused.region.y < tui_app.TOAST_AREA_ROWS
            assert rack.has_class("-bottom") is top

    asyncio.run(scenario())


def test_review_blocker_lines_jump_to_their_field() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(80, 24)) as pilot:
            app = pilot.app
            await pilot.pause()
            await _load(pilot)
            app.form.mode = "rate"
            app.action_go_to_step("review")
            assert await _until(pilot, lambda: "review" in app._ready_steps)
            await pilot.pause()
            blockers = app.query_one("#review_blockers", OptionList)
            assert blockers.display and blockers.option_count == 3
            assert app.focused is blockers  # the step's first blocker line
            await pilot.press("down", "enter")
            ok = await _until(pilot, lambda: app.focused is not None and app.focused.id == "rate_approved")
            assert ok, (app.focused, app._current_step, [o.id for o in blockers._options], blockers.highlighted)
            assert app._current_step == "analysis"

    asyncio.run(scenario())


def test_the_form_is_locked_while_a_run_is_active_and_says_why(monkeypatch: pytest.MonkeyPatch) -> None:
    release = threading.Event()

    def slow(request, logger, *, cancel_requested, on_stage):
        on_stage("analysis")
        release.wait(20)
        return _success(request, logger)

    monkeypatch.setattr(tui_app, "execute_run", slow)

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            await _load(pilot)
            app.form.update(entity="Target", dimensions=("card_type",), validate_input=False)
            app._focus_field("dims")
            ok = await _until(pilot, lambda: app.focused is not None and app.focused.id == "dims")
            assert ok, (app.focused, app._current_step, app._pending_focus, app._ready_steps)
            app.run_analysis()
            assert await _until(pilot, lambda: app._run_state == "running")
            await pilot.pause()
            note = app.query_one("#form_lock_note", Static)
            assert not note.has_class("hidden") and "locked" in str(note.content)
            assert all(app.query_one(f"#{s.container_id}").disabled for s in tui_app.STEPS)
            assert not app.query_one("#dims").focusable  # disabled through its step
            await pilot.press("ctrl+o")  # no picker while locked
            await pilot.pause()
            assert not isinstance(app.screen, tui_app.CsvPickerScreen)
            release.set()
            assert await _until(pilot, lambda: app._run_state == "success")
            await pilot.pause()
            assert note.has_class("hidden")
            assert not any(app.query_one(f"#{s.container_id}").disabled for s in tui_app.STEPS)
            assert app.focused is not None and app.focused.id == "dims"  # ≥110: focus stays

    asyncio.run(scenario())


def test_run_log_view_uses_the_whole_body_and_ctrl_t_returns() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            pane = app.query_one("#activity_pane")
            assert pane.region.width == tui_app.RESULTS_COLUMN_WIDTH
            app.query_one("#btn_show_log", Button).press()
            await pilot.pause()
            assert pane.region.width == SIZE[0]
            assert app.query_one("#setup_pane").region.width == 0
            assert app.focused is app.query_one("#log_output")
            await pilot.press("ctrl+t")
            await pilot.pause()
            assert pane.region.width == tui_app.RESULTS_COLUMN_WIDTH
            assert app.focused is not None and app._step_of(app.focused) == "data"

    asyncio.run(scenario())


def test_preset_change_without_expert_changes_is_silent() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            await app.ensure_step("privacy")
            app.query_one("#preset_select", Select).value = "low_distortion"
            await pilot.pause()
            assert not isinstance(app.screen, ConfirmScreen)
            assert app.form.preset == "low_distortion"
            assert "Accuracy first" in str(app.query_one("#posture_line", Static).content)

    asyncio.run(scenario())


def test_consent_and_attestation_still_open_on_cancel_after_the_redesign(tmp_path: Path) -> None:
    """D3 regression on the new form: Enter on the dialog declines."""

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            await _load(pilot)
            app.form.update(mode="rate", total_col="total", fraud_col="fraud",
                            dimensions=("card_type",), validate_input=False)
            app.run_analysis()
            assert await _until(pilot, lambda: isinstance(app.screen, ClearingSpendConfirmScreen))
            await pilot.pause()
            assert app.focused is not None and app.focused.id == "btn_confirm_no"
            await pilot.press("enter")
            assert await _until(pilot, lambda: app._run_state == "idle")

    asyncio.run(scenario())


def test_steps_two_and_three_mount_in_the_background_after_a_csv_load() -> None:
    """After a load, steps 2 and 3 mount while idle so their first show is a
    display toggle; nothing is shown, focus stays put, More options stays lazy."""

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(80, 24)) as pilot:
            app = pilot.app
            await pilot.pause()
            assert app._mounted_steps == {"data"}
            await _load(pilot)
            focused = app.focused
            assert await _until(pilot, lambda: {"entity", "analysis"} <= app._ready_steps)
            await pilot.pause()
            assert app._current_step == "data"
            assert app.focused is focused
            assert not app.query_one("#step_entity").display and not app.query_one("#step_analysis").display
            assert "privacy" not in app._mounted_steps and "review" not in app._mounted_steps
            assert not app.query("#output_file")  # More options mounts on first open
            # The prewarmed widgets follow the form like any mounted step.
            assert app.query_one("#share_metric", Select).value == app.form.metric

    asyncio.run(scenario())


def test_column_select_survives_a_missing_label_during_teardown() -> None:
    """A background step can still be mounting while the app exits.

    Textual's Select then writes its value into a SelectCurrent label that is
    already gone (NoMatches raised out of run_test on CI). SafeSelect must
    skip that write instead of crashing.
    """

    class _Host(App):
        def compose(self) -> ComposeResult:
            yield ColumnSelect(["alpha", "beta"], value="alpha", id="cols")

    async def scenario() -> None:
        async with _Host().run_test() as pilot:
            await pilot.pause()
            select = pilot.app.query_one("#cols", ColumnSelect)
            await select.query_one(SelectCurrent).query_one("#label").remove()
            select.value = "beta"  # must not raise NoMatches
            await pilot.pause()
            assert select.value == "beta"

    asyncio.run(scenario())
