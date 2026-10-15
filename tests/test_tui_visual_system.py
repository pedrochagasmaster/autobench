"""Visual system (TUI redesign 02, Phase 2 PR 3).

Status language, ``[x]``/``[ ]`` checkboxes (private-API guard), the
app-owned key bar per context, NO_COLOR meaning, the token stylesheet, the
``core.labels`` glossary and the edge-node manifest coverage of ``tui/``.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml
from textual.geometry import Region
from textual.screen import ModalScreen
from textual.widgets import Checkbox, Input, Select, SelectionList, Static
from textual.widgets._toggle_button import ToggleButton

import tui_app
from core import labels
from core.analysis_run import RunAborted, RunBlocked
from core.contracts import (
    AnalysisArtifacts,
    AnalysisRunRequest,
    PrivacyOutputDecision,
    PrivacyReleaseMode,
    PrivacyRuleStrategy,
    PrivacySweepStatus,
)
from core.data_loader import ValidationIssue, ValidationSeverity
from core import privacy_output_policy
from tui import status as tui_status
from tui.keybar import CONTEXTS, KeyBar, context_text
from tui.status import STATUS, status_text
from tui.styles import AUTOBENCH_TCSS
from tui.widgets import BoxCheckbox, BoxSelectionList, StatusBadge
from tui_app import BenchmarkApp, ClearingSpendConfirmScreen, ConfirmScreen, ValidationModal

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_STATES = {
    "ready": ("READY", "●", "(*)"),
    "notready": ("NOT READY", "!", "(!)"),
    "loading": ("LOADING", "◌", "(~)"),
    "running": ("RUNNING", "▸", "(>)"),
    "awaiting": ("WAITING FOR YOU", "?", "(?)"),
    "success": ("DONE", "✓", "(+)"),
    "compliant": ("COMPLIANT", "◆", "(=)"),
    "warning": ("WARNING", "▲", "(^)"),
    "withheld": ("WITHHELD", "◐", "(-)"),
    "blocked": ("BLOCKED", "⊘", "(/)"),
    "error": ("FAILED", "✗", "(x)"),
    "cancelled": ("CANCELLED", "■", "(#)"),
}


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(tui_app, "SESSION_FILE", tmp_path / "session.yaml")
    tui_status.set_ascii_glyphs(False)
    yield
    tui_status.set_ascii_glyphs(None)


def _rendered_text(app: BenchmarkApp, region: Region) -> str:
    lines = [strip.text for strip in app.screen._compositor.render_strips()]
    return "\n".join(line[region.x : region.right] for line in lines[region.y : region.bottom])


# ── Status language ─────────────────────────────────────────────────────────


def test_status_language_has_the_twelve_states_with_glyph_and_ascii() -> None:
    assert set(STATUS) == set(EXPECTED_STATES)
    for state, (word, glyph, ascii_mark) in EXPECTED_STATES.items():
        spec = STATUS[state]
        assert (spec.word, spec.glyph, spec.ascii) == (word, glyph, ascii_mark)
        text = status_text(state)
        assert word in text and glyph in text
    assert {s for s, spec in STATUS.items() if spec.filled} == {"withheld", "blocked", "error"}


def test_ascii_glyph_set_swaps_glyphs_only() -> None:
    tui_status.set_ascii_glyphs(True)
    for state, (word, glyph, ascii_mark) in EXPECTED_STATES.items():
        text = status_text(state)
        assert text == f"{ascii_mark} {word}"


def test_ascii_glyph_detection_rules() -> None:
    tui_status.set_ascii_glyphs(None)
    assert tui_status.use_ascii_glyphs({"AUTOBENCH_GLYPHS": "ascii"}, "utf-8") is True
    assert tui_status.use_ascii_glyphs({"AUTOBENCH_GLYPHS": "unicode"}, "ascii") is False
    assert tui_status.use_ascii_glyphs({"TERM": "linux"}, "utf-8") is True
    assert tui_status.use_ascii_glyphs({}, "UTF-8") is False
    assert tui_status.use_ascii_glyphs({}, "cp1252") is True


def test_status_badge_text_contains_word_and_glyph_for_every_state() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            app = pilot.app
            await pilot.pause()
            badge = app.query_one("#run_status_badge", StatusBadge)
            for state, (word, glyph, _ascii) in EXPECTED_STATES.items():
                badge.set_status(state)
                await pilot.pause()
                rendered = _rendered_text(app, badge.region)
                assert word in rendered and glyph in rendered, state
                assert badge.has_class(f"-{state}")
                assert [name for name in STATUS if badge.has_class(f"-{name}")] == [state]

    asyncio.run(scenario())


def test_no_color_marks_filled_states_with_reverse_video(monkeypatch: pytest.MonkeyPatch) -> None:
    """NO_COLOR: meaning is glyph + word + style, never colour alone."""
    monkeypatch.setenv("NO_COLOR", "1")

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            app = pilot.app
            await pilot.pause()
            assert app.no_color
            badge = app.query_one("#run_status_badge", StatusBadge)
            texts = set()
            for state, (word, glyph, _ascii) in EXPECTED_STATES.items():
                badge.set_status(state)
                await pilot.pause()
                style = badge.rich_style
                # 02 §2.1: LOADING is italic, every other state bold.
                assert (style.italic if state == "loading" else style.bold), state
                assert bool(style.reverse) == STATUS[state].filled, state
                texts.add(_rendered_text(app, badge.region).strip())
            # Twelve states, twelve distinct texts: no state relies on colour.
            assert len(texts) == len(EXPECTED_STATES)

            # Checkboxes and lists also read without colour.
            validate = app.query_one("#validate_input", Checkbox)
            assert "[x]" in _rendered_text(app, validate.region)

    asyncio.run(scenario())


# ── Checkbox affordance and its private-API guard ───────────────────────────


def test_textual_private_apis_used_by_box_widgets_still_exist() -> None:
    """BoxCheckbox overrides ToggleButton._button; BoxSelectionList reads _selected."""
    assert isinstance(getattr(ToggleButton, "_button", None), property)

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            sl = pilot.app.query_one("#share_dims", SelectionList)
            assert isinstance(sl._selected, dict)

    asyncio.run(scenario())


def test_checkboxes_and_selection_lists_draw_box_marks() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(120, 50)) as pilot:
            app = pilot.app
            await pilot.pause()
            # Every checkbox and multi-select in the app uses the box subclasses,
            # attestations included.
            assert all(isinstance(cb, BoxCheckbox) for cb in app.query(Checkbox))
            assert all(isinstance(sl, BoxSelectionList) for sl in app.query(SelectionList))
            assert isinstance(app.query_one("#citi_competitor_receives_output"), BoxCheckbox)
            assert isinstance(app.query_one("#privacy_merchant_spend_scope"), BoxCheckbox)

            on = app.query_one("#validate_input", Checkbox)
            off = app.query_one("#compare_presets", Checkbox)
            for widget in (on, off):
                widget.scroll_visible(animate=False)
            await pilot.pause()
            assert on.value is True and off.value is False
            assert _rendered_text(app, on.region).lstrip().startswith("[x]")
            assert _rendered_text(app, off.region).lstrip().startswith("[ ]")
            off.value = True
            await pilot.pause()
            assert _rendered_text(app, off.region).lstrip().startswith("[x]")

            app.query_one("#csv_path", Input).value = str(ROOT / "tests" / "fixtures" / "gate_demo.csv")
            app.load_csv_headers(str(ROOT / "tests" / "fixtures" / "gate_demo.csv"))
            await pilot.pause()
            dims = app.query_one("#share_dims", SelectionList)
            dims.select("card_type")
            dims.scroll_visible(animate=False, top=True)
            await pilot.pause()
            text = _rendered_text(app, dims.content_region)
            assert "[x] card_type" in text
            assert "[ ] channel" in text
            assert "▐X▌" not in text

    asyncio.run(scenario())


# ── Key bar ─────────────────────────────────────────────────────────────────


def test_key_bar_replaces_footer_and_has_no_step_keys() -> None:
    assert "Footer" not in {name for name in dir(tui_app) if not name.startswith("_")}
    for context, hints in CONTEXTS.items():
        keys = {hint.key for hint in hints}
        assert not any(re.fullmatch(r"F[2-6]", key) for key in keys), context
        assert not any(key.lower().startswith("alt+") for key in keys), context
        assert "^A" not in keys and "^E" not in keys, context


def test_key_bar_shows_the_right_keys_per_context() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            app = pilot.app
            await pilot.pause()
            bar = app.query_one("#key_bar", KeyBar)

            # Launch: the path field is focused.
            assert app.focused is app.query_one("#csv_path", Input)
            assert bar.context == "field"
            text = bar.visible_text
            for expected in ("^R Run", "^O Open CSV", "F8 Advanced", "F1 Preset guide", "^Q Quit", "^P Commands"):
                assert expected in text

            app.query_one("#entity_col", Select).focus()
            await pilot.pause()
            assert bar.context == "select"
            assert "↵ Open" in bar.visible_text

            app.query_one("#share_dims", SelectionList).focus()
            await pilot.pause()
            assert bar.context == "list"
            assert "␣ Toggle" in bar.visible_text

            app.query_one("#validate_input", Checkbox).focus()
            await pilot.pause()
            assert bar.context == "toggle"

            app._run_state = "running"
            app._refresh_run_status()
            await pilot.pause()
            assert bar.context == "running"
            assert "^R" not in bar.visible_text
            assert "^Q Quit" in bar.visible_text

            app._end_run_ui("success", "done")
            app.query_one("#csv_path", Input).focus()
            await pilot.pause()
            assert bar.context == "results"
            assert "^R Run again" in bar.visible_text

    asyncio.run(scenario())


def test_key_bar_truncates_at_80_columns_and_keeps_run() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            bar = pilot.app.query_one("#key_bar", KeyBar)
            text = bar.visible_text
            assert len(text) <= 80
            assert text.lstrip().startswith("^R Run")
            assert "F8 Advanced" in text

    asyncio.run(scenario())


def test_modal_key_bars_name_their_keys() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(80, 24)) as pilot:
            app = pilot.app
            await pilot.pause()
            app.push_screen(ConfirmScreen("Sure?"))
            await pilot.pause()
            assert app.screen.query_one(KeyBar).visible_text.split() == ["Tab", "Move", "↵", "Choose", "Esc", "Cancel"]
            app.pop_screen()
            app.push_screen(
                ValidationModal([ValidationIssue(ValidationSeverity.WARNING, "x", "Something odd")])
            )
            await pilot.pause()
            assert "Esc Cancel run" in app.screen.query_one(KeyBar).visible_text

    asyncio.run(scenario())


def test_key_bar_click_runs_the_key_action() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            app = pilot.app
            await pilot.pause()
            app.action_show_help = MagicMock()  # type: ignore[method-assign]
            text = app.query_one("#key_bar", KeyBar).visible_text
            await pilot.click("#key_bar", offset=(text.index("F1 Preset") + 1, 0))
            await pilot.pause()
            app.action_show_help.assert_called_once()

    asyncio.run(scenario())


def test_context_text_lists_every_hint() -> None:
    assert context_text("confirm") == "Tab Move  ↵ Choose  Esc Cancel"


# ── Bindings: F8/F9 work from a text field, Ctrl+C quits ────────────────────


def test_f8_toggles_advanced_from_a_focused_input() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            app = pilot.app
            await pilot.pause()
            assert isinstance(app.focused, Input)
            advanced = app.query_one("#advanced_opt")
            assert advanced.collapsed
            await pilot.press("f8")
            await pilot.pause()
            assert not advanced.collapsed
            await pilot.press("f8")
            await pilot.pause()
            assert advanced.collapsed

    asyncio.run(scenario())


def test_f9_exports_advanced_from_a_focused_input() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            app = pilot.app
            await pilot.pause()
            app.action_export_advanced = MagicMock()  # type: ignore[method-assign]
            assert isinstance(app.focused, Input)
            await pilot.press("f9")
            await pilot.pause()
            app.action_export_advanced.assert_called_once()

    asyncio.run(scenario())


def test_escape_then_ctrl_c_exits_from_a_focused_input() -> None:
    """Release tooling (edge_deploy.yaml tui_exit: ctrl_c) sends Escape, C-c."""

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(80, 24)) as pilot:
            app = pilot.app
            await pilot.pause()
            assert isinstance(app.focused, Input)
            await pilot.press("escape", "ctrl+c")
            await pilot.pause()
            assert app._exit

    asyncio.run(scenario())


def test_ctrl_c_copies_an_input_selection_instead_of_quitting() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(80, 24)) as pilot:
            app = pilot.app
            await pilot.pause()
            field = app.query_one("#csv_path", Input)
            field.value = "data.csv"
            field.select_all()
            await pilot.press("ctrl+c")
            await pilot.pause()
            assert not app._exit
            assert app.clipboard == "data.csv"

    asyncio.run(scenario())


def test_ctrl_c_while_running_asks_before_quitting() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(80, 24)) as pilot:
            app = pilot.app
            await pilot.pause()
            app._run_state = "running"
            await pilot.press("ctrl+c")
            await pilot.pause()
            assert isinstance(app.screen, ConfirmScreen)
            await pilot.press("ctrl+c")  # no second dialog stacked
            await pilot.pause()
            assert sum(isinstance(s, ConfirmScreen) for s in app.screen_stack) == 1
            assert not app._exit
            app._run_state = "idle"

    asyncio.run(scenario())


# ── Outcome copy (02 §5.3/§5.4) ─────────────────────────────────────────────


def _outcome_app() -> BenchmarkApp:
    app = BenchmarkApp()
    app.call_from_thread = lambda fn, *a, **k: fn(*a, **k)  # type: ignore[method-assign]
    app._begin_run_ui = MagicMock()  # type: ignore[method-assign]
    app._end_run_ui = MagicMock()  # type: ignore[method-assign]
    app.notify = MagicMock()  # type: ignore[method-assign]
    return app


def test_withheld_outcome_has_what_why_next_code_and_withheld_badge() -> None:
    app = _outcome_app()
    app._execute_run_for_tui = MagicMock(  # type: ignore[method-assign]
        return_value=AnalysisArtifacts(
            metadata={},
            compliance_summary={
                "compliance_verdict": "violations_detected",
                "posture": "strict",
                "acknowledgement_state": "not_required",
            },
            report_paths=[],
            privacy_output_decision=PrivacyOutputDecision(
                privacy_publication_authorized=False,
                hard_privacy_block=True,
                withholding_reason="control3_numeric_policy_blocked",
            ),
        )
    )
    app._execute_confirmed_analysis(AnalysisRunRequest(mode="share", metric="amount"), None, MagicMock())
    args, kwargs = app._end_run_ui.call_args
    assert args[0] == "blocked" and kwargs["badge"] == "withheld"
    summary = args[1]
    assert "Results were withheld to protect peer privacy." in summary
    assert "Why" in summary and "Next" in summary
    assert "Code: control3_numeric_policy_blocked" in summary
    assert "[red]" not in summary and "[dim]" not in summary
    title = app.notify.call_args.kwargs["title"]
    assert "WITHHELD" in title and "◐" in title


def test_success_outcome_adds_the_verdict_badge() -> None:
    app = _outcome_app()
    app._execute_run_for_tui = MagicMock(  # type: ignore[method-assign]
        return_value=AnalysisArtifacts(
            metadata={},
            compliance_summary={"compliance_verdict": "fully_compliant", "posture": "strict"},
            report_paths=["/out/[weird] report.xlsx"],
            privacy_output_decision=PrivacyOutputDecision(True, False),
            privacy_sink_authorized=True,
            privacy_log_authorized=True,
        )
    )
    app._execute_confirmed_analysis(AnalysisRunRequest(mode="share", metric="amount"), None, MagicMock())
    args, kwargs = app._end_run_ui.call_args
    assert args[0] == "success" and kwargs["verdict"] == "compliant"
    # Paths are escaped, never parsed as markup.
    assert r"\[weird]" in args[1]
    assert "DONE" in app.notify.call_args.kwargs["title"]


@pytest.mark.parametrize(
    ("exc", "state", "headline", "word"),
    [
        (RunBlocked("insufficient_peers: 3 peers", {"compliance_verdict": "blocked"}), "blocked", "Not enough peers to benchmark safely", "BLOCKED"),
        (RunAborted("No analysis results generated"), "error", "The analysis produced no results.", "FAILED"),
        (KeyError("card_type_input_mode"), "error", "Something went wrong inside the analysis.", None),
    ],
)
def test_failure_outcomes_use_plain_headlines(exc, state, headline, word) -> None:
    app = _outcome_app()
    app._execute_run_for_tui = MagicMock(side_effect=exc)  # type: ignore[method-assign]
    app._execute_confirmed_analysis(AnalysisRunRequest(mode="share", metric="amount"), None, MagicMock())
    args = app._end_run_ui.call_args.args
    assert args[0] == state
    assert headline in args[1]
    assert "Code:" in args[1]
    if word:
        assert word in app.notify.call_args.kwargs["title"]


def test_run_status_panel_and_last_run_show_badges_after_a_run() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            app = pilot.app
            await pilot.pause()
            app._end_run_ui("blocked", "body", badge="withheld")
            await pilot.pause()
            assert app.query_one("#run_status_badge", StatusBadge).state == "withheld"
            assert app.query_one("#results_badge", StatusBadge).state == "withheld"
            assert app.query_one("#results_verdict_badge").has_class("hidden")
            app._end_run_ui("success", "body", verdict="compliant")
            await pilot.pause()
            assert app.query_one("#results_badge", StatusBadge).state == "success"
            assert app.query_one("#results_verdict_badge", StatusBadge).state == "compliant"
            app._reset_run_ui()
            await pilot.pause()
            assert app.query_one("#run_status_badge", StatusBadge).state == "ready"

    asyncio.run(scenario())


def test_every_app_run_state_maps_to_a_status_language_state() -> None:
    for state, badge in BenchmarkApp._STATE_BADGES.items():
        assert badge.state in STATUS, state
    assert BenchmarkApp._STATE_BADGES["cancelled"].state == "cancelled"


def test_cancelled_run_shows_the_cancelled_badge_and_outcome_card() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            app = pilot.app
            await pilot.pause()
            app._begin_run_ui()
            app._set_run_stage("analysis")
            await pilot.pause()
            detail = str(app.query_one("#run_status_detail", Static).content)
            assert "Stage" in detail and "Optimizing and checking privacy" in detail
            app._end_run_ui(
                "cancelled", tui_app._outcome_markup(labels.RUN_CANCELLED, code="RunCancelled")
            )
            await pilot.pause()
            assert app.query_one("#run_status_badge", StatusBadge).state == "cancelled"
            assert app.query_one("#results_badge", StatusBadge).state == "cancelled"
            assert app.query_one("#results_verdict_badge").has_class("hidden")
            results = str(app.query_one("#results_panel", Static).content)
            assert labels.RUN_CANCELLED.primary in results and "Code: RunCancelled" in results
            assert "Stage" not in str(app.query_one("#run_status_detail", Static).content)
            app.query_one("#csv_path", Input).focus()
            await pilot.pause()
            assert app.query_one(KeyBar).context == "results"

    asyncio.run(scenario())


def test_validation_shows_waiting_for_you_while_the_dialog_is_open() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            app = pilot.app
            await pilot.pause()
            app._begin_validation_ui()
            await pilot.pause()
            badge = app.query_one("#run_status_badge", StatusBadge)
            assert badge.state == "running"
            app.push_screen(ValidationModal([ValidationIssue(ValidationSeverity.WARNING, "x", "Odd")]))
            await pilot.pause()
            await pilot.pause()
            assert badge.state == "awaiting"
            app.pop_screen()
            await pilot.pause()
            await pilot.pause()
            assert badge.state == "running"
            app._reset_run_ui()

    asyncio.run(scenario())


def test_validation_modal_badges_use_the_status_glyphs() -> None:
    error = ValidationModal._issue_text(ValidationIssue(ValidationSeverity.ERROR, "x", "Bad"))
    warning = ValidationModal._issue_text(ValidationIssue(ValidationSeverity.WARNING, "x", "Odd"))
    assert "✗ ERROR" in error.plain
    assert "▲ WARNING" in warning.plain
    assert any("reverse" in str(span.style) for span in error.spans)


def test_clearing_spend_dialog_names_the_act() -> None:
    screen = ClearingSpendConfirmScreen("txn_amt")
    assert screen.confirm_label == "Yes, it is clearing spend"
    assert '"txn_amt"' in screen.message and "`" not in screen.message


def test_title_keeps_the_release_chrome_regex_match() -> None:
    profile = yaml.safe_load((ROOT / "edge_deploy.yaml").read_text(encoding="utf-8"))
    assert re.search(profile["tui_chrome_regex"], BenchmarkApp.TITLE)


# ── Stylesheet ──────────────────────────────────────────────────────────────


def test_one_stylesheet_and_no_screen_css() -> None:
    assert BenchmarkApp.CSS == AUTOBENCH_TCSS
    for name in dir(tui_app):
        obj = getattr(tui_app, name)
        if isinstance(obj, type) and issubclass(obj, ModalScreen) and obj.__module__ == "tui_app":
            assert not obj.__dict__.get("CSS"), name


def test_stylesheet_has_no_literal_colours_outside_ansi_overrides() -> None:
    css = re.sub(r"/\*.*?\*/", "", AUTOBENCH_TCSS, flags=re.S)
    for line in css.splitlines():
        if line.lstrip().startswith("App:ansi"):
            continue
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|ansi_", line), line


def test_tui_app_has_no_colour_markup_for_status() -> None:
    source = (ROOT / "tui_app.py").read_text(encoding="utf-8")
    for tag in ("[red]", "[green]", "[yellow]", "[cyan]", "[dim]", "rgba("):
        assert tag not in source, tag


def test_widgets_are_compact() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(80, 24)) as pilot:
            app = pilot.app
            await pilot.pause()
            for widget in app.query("Input, Select, Checkbox, Button"):
                assert widget.compact, widget

    asyncio.run(scenario())


def test_everything_is_reachable_at_80x24() -> None:
    """Every focusable form widget can be scrolled into view at 80x24."""

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(80, 24)) as pilot:
            app = pilot.app
            await pilot.pause()
            app.query_one("#advanced_opt").collapsed = False
            app.query_one("#compliance_declarations").collapsed = False
            await pilot.pause()
            screen = Region(0, 0, 80, 24)
            pane = app.query_one("#config_pane")
            checked = 0
            for widget in pane.query("Input, Select, Checkbox, Button, SelectionList"):
                if any(not node.display for node in widget.ancestors_with_self if node is not app):
                    continue  # Inactive tab or hidden by a mode switch.
                widget.scroll_visible(animate=False, immediate=True)
                # Layout can take more than one frame to settle under load.
                for _ in range(20):
                    await pilot.pause()
                    if widget.region.area > 0 and screen.contains_region(widget.region):
                        break
                assert widget.region.area > 0, widget
                assert screen.contains_region(widget.region), widget
                checked += 1
            assert checked > 30

    asyncio.run(scenario())


# ── core.labels glossary ────────────────────────────────────────────────────


def _codes(kind: str) -> set:
    return {code for (k, code) in labels.LABELS if k == kind}


def test_labels_cover_every_internal_code() -> None:
    assert {m.value for m in PrivacyReleaseMode} <= _codes(labels.RELEASE_MODE)
    assert {m.value for m in PrivacyRuleStrategy} <= _codes(labels.RULE_STRATEGY)
    assert {m.value for m in PrivacySweepStatus} <= _codes(labels.SWEEP_STATUS)
    assert {m.value for m in ValidationSeverity} <= _codes(labels.VALIDATION_SEVERITY)
    control3 = {
        value
        for name, value in vars(privacy_output_policy).items()
        if name.startswith("CONTROL3_") and isinstance(value, str) and value.startswith("control3_")
        and not name.endswith(("VERSION", "SOURCE"))
    }
    assert control3 and control3 <= _codes(labels.WITHHOLDING_REASON)
    verdicts = {"fully_compliant", "violations_detected", "not_publishable_input", "structural_infeasibility", "blocked"}
    assert verdicts <= _codes(labels.COMPLIANCE_VERDICT)
    assert verdicts <= set(labels.VERDICT_STATUS)
    run_statuses = {"compliant", "non_compliant", "completed_with_warnings", "completed_accuracy_first",
                    "completed", "blocked", "withheld"}
    assert run_statuses <= _codes(labels.RUN_STATUS)
    assert {"acknowledged", "not_required", "required_missing"} <= _codes(labels.CONSENT_STATE)
    presets = {}
    for path in (ROOT / "presets").glob("*.yaml"):
        presets[path.stem] = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert set(presets) <= _codes(labels.PRESET)
    assert {p["compliance_posture"] for p in presets.values()} <= _codes(labels.POSTURE)
    assert set(labels.VERDICT_STATUS.values()) <= set(STATUS)


def test_unknown_codes_never_render_bare() -> None:
    assert labels.text_for(labels.COMPLIANCE_VERDICT, "brand_new_code") == labels.UNRECOGNISED
    assert labels.text_for(labels.POSTURE, None) == labels.UNRECOGNISED
    assert labels.blocked_label("something new") == labels.BLOCKED_FALLBACK
    assert labels.aborted_label("something new") == labels.ABORTED_FALLBACK


def test_labels_never_suggest_weakening_privacy() -> None:
    texts = [lbl.next.lower() for lbl in labels.LABELS.values()]
    texts += [lbl.next.lower() for _, lbl in labels.BLOCKED_REASONS + labels.ABORTED_PREFIXES]
    for text in texts:
        assert "accuracy_first" not in text and "accuracy first" not in text
        assert "best effort" not in text and "best_effort" not in text


def test_labels_module_is_pure_data() -> None:
    source = (ROOT / "core" / "labels.py").read_text(encoding="utf-8")
    imports = re.findall(r"^\s*(?:from|import)\s+([\w.]+)", source, flags=re.M)
    assert set(imports) <= {"__future__", "typing"}


def test_preset_description_strips_formerly_suffix() -> None:
    assert labels.strip_preset_description("Standard Analysis - x (formerly standard)") == "Standard Analysis - x"
    assert labels.strip_preset_description("No suffix") == "No suffix"


# ── Deployment manifest covers tui/ ─────────────────────────────────────────


def test_tui_package_ships_to_edge_nodes() -> None:
    profile = yaml.safe_load((ROOT / "edge_deploy.yaml").read_text(encoding="utf-8"))
    assert "tui/**/*.py" in profile["runtime_paths"]
    assert "tui" in profile["compile_targets"].split()
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    include = re.search(r"\[tool\.setuptools\.packages\.find\]\s*include\s*=\s*\[([^\]]*)\]", pyproject)
    assert include and '"tui*"' in include.group(1)
    # Only Python ships: no stylesheet file that a *.py glob would miss.
    assert not list((ROOT / "tui").rglob("*.tcss"))
    assert all(p.suffix == ".py" for p in (ROOT / "tui").rglob("*") if p.is_file() and "__pycache__" not in p.parts)


def test_results_panel_stays_a_static_with_the_verdict_code() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            app = pilot.app
            await pilot.pause()
            app._end_run_ui("success", tui_app._outcome_markup(labels.Label("ok"), code="fully_compliant"))
            await pilot.pause()
            assert "fully_compliant" in str(app.query_one("#results_panel", Static).content)

    asyncio.run(scenario())
