"""Regression tests for TUI redesign Phase 2 PR 1 (D2-D8, owner decisions 1, 4-6)."""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml
from textual.pilot import Pilot
from textual.widgets import Button, Checkbox, Log, Select, SelectionList, Static, TabbedContent

import benchmark
import tui_app
from core.analysis_run import RunCancelled
from core.contracts import PrivacyReleaseMode, PrivacyRuleStrategy
from tui_app import (
    SELECT_BLANK,
    BenchmarkApp,
    ClearingSpendConfirmScreen,
    ConfirmScreen,
    LogHandler,
    RunInputs,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "gate_demo.csv"
SIZE = (140, 45)


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tui_app, "SESSION_FILE", tmp_path / "session.yaml")
    monkeypatch.setenv("AUTOBENCH_LOG_DIR", str(tmp_path / "logs"))
    # Override files are written to the launch folder (owner decision 2).
    monkeypatch.chdir(tmp_path)


async def _until(pilot: Pilot, predicate, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            return False
        await pilot.pause(0.05)
    return True


async def _wait_for_screen(pilot: Pilot, screen_type: type, timeout: float = 10.0) -> None:
    """Wait until a modal of ``screen_type`` is pushed and its buttons laid out."""

    def ready() -> bool:
        screen = pilot.app.screen
        if not isinstance(screen, screen_type):
            return False
        buttons = list(screen.query("#btn_confirm_yes, #btn_confirm_no"))
        return len(buttons) == 2 and all(b.region.width for b in buttons)

    assert await _until(pilot, ready, timeout), f"{screen_type.__name__} never appeared"
    await pilot.pause()


def _load_fixture(app: BenchmarkApp, path: str | None = None) -> None:
    app.query_one("#csv_path").value = path if path is not None else str(FIXTURE)
    app.load_csv_headers(path if path is not None else str(FIXTURE))


async def _share_form(pilot: Pilot, tmp_path: Path) -> None:
    app = pilot.app
    _load_fixture(app)
    await pilot.pause()
    app.query_one("#share_metric", Select).value = "txn_cnt"
    app.query_one("#share_dims", SelectionList).select("card_type")
    app.query_one("#output_file").value = str(tmp_path / "share.xlsx")
    app.query_one("#validate_input", Checkbox).value = False


async def _rate_form(pilot: Pilot, tmp_path: Path, *, fraud: bool) -> None:
    app = pilot.app
    _load_fixture(app)
    app.query_one(TabbedContent).active = "rate_tab"
    await pilot.pause()
    app.query_one("#rate_total", Select).value = "total"
    app.query_one("#rate_approved", Select).value = "approved"
    app.query_one("#rate_fraud", Select).value = "fraud" if fraud else SELECT_BLANK
    app.query_one("#rate_dims", SelectionList).select("card_type")
    app.query_one("#output_file").value = str(tmp_path / "rate.xlsx")
    app.query_one("#validate_input", Checkbox).value = False


def _capture_notices(app: BenchmarkApp) -> list[str]:
    notices: list[str] = []
    original = app.notify

    def notify(message, *args, **kwargs):
        notices.append(str(message))
        return original(message, *args, **kwargs)

    app.notify = notify  # type: ignore[method-assign]
    return notices


# ──────────────────────────────────────────────────────────────────────
# D2: stale advanced overrides and the effective posture
# ──────────────────────────────────────────────────────────────────────


def test_preset_change_invalidates_applied_override_with_notice(tmp_path: Path) -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            preset = app.query_one("#preset_select", Select)
            preset.value = "balanced_default"
            await pilot.pause()
            app.apply_advanced_overrides()
            override = Path(app.advanced_config_path)
            assert override.is_file()
            notices = _capture_notices(app)

            preset.value = "low_distortion"
            await pilot.pause()

            assert app.advanced_config_path is None
            assert any("previous preset will not be used" in n for n in notices)
            # Owner decision 2: the file stays in the launch folder.
            assert override.is_file()
            assert override.parent.resolve() == tmp_path.resolve()

            inputs = app._collect_run_inputs()
            assert inputs.config is None
            assert inputs.preset == "low_distortion"
            assert inputs.compliance_posture == "accuracy_first"

    asyncio.run(scenario())


def test_run_snapshot_never_sends_override_written_for_another_preset(tmp_path: Path) -> None:
    """Belt and braces: even without a Changed event, the snapshot drops it."""

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            app.query_one("#preset_select", Select).value = "balanced_default"
            await pilot.pause()
            app.apply_advanced_overrides()
            assert app.advanced_config_path
            # Simulate the preset changing without the handler having run.
            app._advanced_config_preset = "compliance_strict"
            inputs = app._collect_run_inputs()
            assert inputs.config is None
            assert inputs.compliance_posture == "best_effort"

    asyncio.run(scenario())


@pytest.mark.parametrize("answer", ["btn_confirm_yes", "btn_confirm_no"])
def test_accuracy_first_consent_is_asked_when_an_override_is_applied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, answer: str
) -> None:
    """Consent follows the effective posture, including with an override file."""
    cancelled: list[tuple[str, str]] = []
    monkeypatch.setattr(
        tui_app, "action_cancelled", lambda action, prompt: cancelled.append((action, prompt))
    )

    async def scenario() -> Any:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            await _share_form(pilot, tmp_path)
            app.query_one("#preset_select", Select).value = "low_distortion"
            await pilot.pause()
            app.apply_advanced_overrides()
            assert app.advanced_config_path
            executed = MagicMock()
            app._execute_confirmed_analysis = executed  # type: ignore[method-assign]

            app.run_analysis()
            await _wait_for_screen(pilot, ConfirmScreen)
            message = str(app.screen.query_one("#confirm_message", Static).content)
            assert "accuracy_first" in message
            await pilot.click(f"#{answer}")
            await _until(pilot, lambda: executed.called or app._run_state == "idle")
            return executed

    executed = asyncio.run(scenario())
    if answer == "btn_confirm_yes":
        request = executed.call_args.args[0]
        assert request.config
        assert request.acknowledge_accuracy_first is True
        assert cancelled == []
    else:
        executed.assert_not_called()
        assert cancelled == [("share_analysis", "accuracy_first_consent")]


def test_effective_posture_reads_the_override_file(tmp_path: Path) -> None:
    override = tmp_path / "custom_override.yaml"
    override.write_text(
        yaml.safe_dump({"version": "3.0", "compliance_posture": "accuracy_first"}),
        encoding="utf-8",
    )
    app = BenchmarkApp()
    assert app._effective_compliance_posture("balanced_default", None) == "best_effort"
    assert (
        app._effective_compliance_posture("balanced_default", str(override))
        == "accuracy_first"
    )
    assert app._effective_compliance_posture(None, None) is None


# ──────────────────────────────────────────────────────────────────────
# D3: Cancel has initial focus on consent and attestation dialogs
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("key", ["enter", "escape"])
@pytest.mark.parametrize("dialog", ["consent", "clearing_spend"])
def test_confirmation_dialogs_focus_cancel_and_enter_or_escape_declines(
    dialog: str, key: str
) -> None:
    async def scenario() -> bool:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            outcome: dict[str, bool] = {}
            ask = (
                app._confirm_accuracy_first_consent
                if dialog == "consent"
                else (lambda: app._confirm_clearing_spend_basis("total"))
            )
            worker = threading.Thread(target=lambda: outcome.setdefault("value", ask()))
            worker.start()
            expected = ConfirmScreen if dialog == "consent" else ClearingSpendConfirmScreen
            await _wait_for_screen(pilot, expected)
            assert app.focused is not None
            assert app.focused.id == "btn_confirm_no"
            await pilot.press(key)
            worker.join(timeout=5)
            assert not worker.is_alive()
            return outcome["value"]

    assert asyncio.run(scenario()) is False


# ──────────────────────────────────────────────────────────────────────
# D4: session restore applies column choices after the CSV loads
# ──────────────────────────────────────────────────────────────────────


def _write_session(tmp_path: Path, data: dict[str, Any]) -> None:
    (tmp_path / "session.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")


def test_restored_column_choices_apply_after_csv_load(tmp_path: Path) -> None:
    _write_session(
        tmp_path,
        {
            "entity_col": "issuer_name",
            "time_col": "year_month",
            "share_metric": "total",
            "share_dims": ["card_type", "channel"],
            "share_secondary": ["approved"],
            "rate_total": "total",
            "rate_fraud": "missing_in_this_file",
            "rate_dims": ["channel", "not_a_column"],
            # Never restored, even from a legacy session file.
            "csv_path": str(FIXTURE),
            "output_file": str(tmp_path / "old.xlsx"),
            "entity_name": "Target",
            "citi_competitor_receives_output": True,
            "privacy_merchant_spend_scope": True,
        },
    )

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause(0.3)
            # Nothing is applied before a CSV is loaded...
            assert app.query_one("#csv_path").value == ""
            assert app.query_one("#time_col", Select).value == SELECT_BLANK
            assert app.query_one("#share_dims", SelectionList).selected == []

            _load_fixture(app)
            await pilot.pause(0.3)

            # ...and every stored column the file has is applied afterwards.
            assert app.query_one("#entity_col", Select).value == "issuer_name"
            assert app.query_one("#time_col", Select).value == "year_month"
            assert app.query_one("#share_metric", Select).value == "total"
            assert set(app.query_one("#share_dims", SelectionList).selected) == {
                "card_type",
                "channel",
            }
            assert app.query_one("#share_secondary", SelectionList).selected == ["approved"]
            assert app.query_one("#rate_total", Select).value == "total"
            assert app.query_one("#rate_fraud", Select).value == SELECT_BLANK
            assert app.query_one("#rate_dims", SelectionList).selected == ["channel"]
            # Governed references and attestations stay unset.
            assert app.query_one("#output_file").value == ""
            assert app.query_one("#entity_name", Select).value == SELECT_BLANK
            assert app.query_one("#citi_competitor_receives_output", Checkbox).value is False
            assert app.query_one("#privacy_merchant_spend_scope", Checkbox).value is False

    asyncio.run(scenario())


def test_restored_column_choices_are_used_by_the_first_load_only(tmp_path: Path) -> None:
    _write_session(tmp_path, {"time_col": "year_month"})
    other = tmp_path / "no_time.csv"
    other.write_text("issuer_name,txn_cnt,card_type\nA,1,X\n", encoding="utf-8")

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            _load_fixture(app, str(other))
            await pilot.pause()
            assert app.query_one("#time_col", Select).value == SELECT_BLANK
            _load_fixture(app)
            await pilot.pause()
            # Dropped for the first file; a later file never resurrects it.
            assert app.query_one("#time_col", Select).value == SELECT_BLANK

    asyncio.run(scenario())


def test_session_round_trip_restores_tab_and_dims(tmp_path: Path) -> None:
    async def save() -> None:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            _load_fixture(app)
            app.query_one(TabbedContent).active = "rate_tab"
            await pilot.pause()
            app.query_one("#rate_total", Select).value = "total"
            app.query_one("#rate_dims", SelectionList).select("channel")
            app._save_session()

    asyncio.run(save())
    saved = yaml.safe_load((tmp_path / "session.yaml").read_text(encoding="utf-8"))
    assert saved["analysis_mode"] == "rate"
    assert saved["rate_dims"] == ["channel"]
    assert "csv_path" not in saved and "entity_name" not in saved

    async def restore() -> None:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause(0.3)
            assert app._analysis_mode() == "rate"
            # Quitting before any CSV load keeps the pending choices saved.
            app._save_session()
            again = yaml.safe_load((tmp_path / "session.yaml").read_text(encoding="utf-8"))
            assert again["rate_dims"] == ["channel"]
            assert again["rate_total"] == "total"
            _load_fixture(app)
            await pilot.pause(0.3)
            assert app.query_one("#rate_dims", SelectionList).selected == ["channel"]
            assert app.query_one("#rate_total", Select).value == "total"

    asyncio.run(restore())


# ──────────────────────────────────────────────────────────────────────
# D5: one debug-sheets control
# ──────────────────────────────────────────────────────────────────────


def test_debug_sheets_have_a_single_control(tmp_path: Path) -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            assert not app.query("#adv_output_debug_sheets")
            assert "adv_output_debug_sheets" not in {
                spec.widget_id for spec in BenchmarkApp.ADVANCED_FIELD_SPECS
            }
            # The override file never carries a debug value the tab would override.
            app.apply_advanced_overrides()
            data = yaml.safe_load(Path(app.advanced_config_path).read_text(encoding="utf-8"))
            assert "include_debug_sheets" not in (data.get("output") or {})
            await _share_form(pilot, tmp_path)
            app.query_one("#share_debug", Checkbox).value = False
            assert app._collect_run_inputs().debug is False
            app.query_one("#share_debug", Checkbox).value = True
            assert app._collect_run_inputs().debug is True

    asyncio.run(scenario())


# ──────────────────────────────────────────────────────────────────────
# D6: LogHandler never blocks the emitting worker
# ──────────────────────────────────────────────────────────────────────


def _worker_side_widget(max_ui_thread: int) -> tuple[MagicMock, MagicMock]:
    log_widget = MagicMock(spec=Log)
    app = MagicMock()
    app._thread_id = max_ui_thread
    app.call_from_thread.side_effect = AssertionError("must not block on the UI")
    log_widget.app = app
    log_widget.call_later.return_value = True
    return log_widget, app


def test_log_handler_posts_one_wake_and_drains_in_one_write() -> None:
    log_widget, app = _worker_side_widget(threading.get_ident() + 1)
    handler = LogHandler(log_widget)
    handler.setFormatter(logging.Formatter("%(message)s"))

    def emit_many() -> None:
        for i in range(500):
            handler.emit(logging.LogRecord("t", logging.INFO, "", 0, f"line {i}", (), None))

    worker = threading.Thread(target=emit_many)
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive()
    app.call_from_thread.assert_not_called()
    assert log_widget.call_later.call_count == 1  # one wake until the UI drains
    drain = log_widget.call_later.call_args.args[0]
    drain()
    log_widget.write.assert_called_once()
    written = log_widget.write.call_args.args[0]
    assert written.count("\n") == 500
    assert written.startswith("line 0\n") and written.endswith("line 499\n")
    # After a drain the next record posts a new wake.
    handler.emit(logging.LogRecord("t", logging.INFO, "", 0, "again", (), None))
    assert log_widget.call_later.call_count == 2


def test_log_handler_buffer_is_bounded_when_the_ui_stalls() -> None:
    log_widget, _app = _worker_side_widget(threading.get_ident() + 1)
    handler = LogHandler(log_widget, max_pending=100)
    handler.setFormatter(logging.Formatter("%(message)s"))
    for i in range(250):
        handler.emit(logging.LogRecord("t", logging.INFO, "", 0, f"line {i}", (), None))
    assert len(handler._pending) == 100
    handler._flush()
    written = log_widget.write.call_args.args[0]
    assert written.startswith("… 150 earlier log lines not shown")
    assert written.endswith("line 249\n")
    assert "line 149\n" not in written


def test_log_handler_drops_wake_quietly_when_app_is_closing() -> None:
    log_widget, _app = _worker_side_widget(threading.get_ident() + 1)
    log_widget.call_later.return_value = False
    handler = LogHandler(log_widget)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.emit(logging.LogRecord("t", logging.INFO, "", 0, "a", (), None))
    handler.emit(logging.LogRecord("t", logging.INFO, "", 0, "b", (), None))
    # No wake is stuck "in flight": each record tries again.
    assert log_widget.call_later.call_count == 2


def test_log_handler_delivers_records_in_a_running_app() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            log = app.query_one("#log_output", Log)
            log.clear()
            handler = LogHandler(log)
            handler.setFormatter(logging.Formatter("%(message)s"))
            start = time.monotonic()

            def emit_many() -> None:
                for i in range(2000):
                    handler.emit(
                        logging.LogRecord("t", logging.INFO, "", 0, f"worker {i}", (), None)
                    )

            worker = threading.Thread(target=emit_many)
            worker.start()
            while worker.is_alive():
                await pilot.pause(0.01)
            worker_seconds = time.monotonic() - start
            assert await _until(pilot, lambda: "worker 1999" in "\n".join(log.lines))
            assert worker_seconds < 2.0

    asyncio.run(scenario())


# ──────────────────────────────────────────────────────────────────────
# D7: the worker reads a frozen snapshot, never a widget
# ──────────────────────────────────────────────────────────────────────


def test_run_inputs_snapshot_is_frozen(tmp_path: Path) -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            await _share_form(pilot, tmp_path)
            inputs = app._collect_run_inputs()
            assert isinstance(inputs, RunInputs)
            assert inputs.metric == "txn_cnt"
            assert inputs.dimensions == ("card_type",)
            with pytest.raises(dataclasses.FrozenInstanceError):
                inputs.metric = "total"  # type: ignore[misc]

    asyncio.run(scenario())


def test_run_worker_never_queries_widgets(tmp_path: Path) -> None:
    """Every DOM query of a run attempt happens on the UI thread."""

    async def scenario() -> tuple[set[int], int, Any]:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            await _rate_form(pilot, tmp_path, fraud=True)
            ui_thread = threading.get_ident()
            query_threads: set[int] = set()
            real_query_one = app.query_one

            def tracking_query_one(*args, **kwargs):
                query_threads.add(threading.get_ident())
                return real_query_one(*args, **kwargs)

            app.query_one = tracking_query_one  # type: ignore[method-assign]
            executed = MagicMock()
            app._execute_confirmed_analysis = executed  # type: ignore[method-assign]
            app.run_analysis()
            await _wait_for_screen(pilot, ClearingSpendConfirmScreen)
            # Widgets changed while the worker waits do not reach the request.
            real_query_one("#rate_total", Select).value = "txn_cnt"
            real_query_one("#rate_dims", SelectionList).select("channel")
            await pilot.click("#btn_confirm_yes")
            await _until(pilot, lambda: executed.called)
            app.query_one = real_query_one  # type: ignore[method-assign]
            return query_threads, ui_thread, executed.call_args.args[0]

    threads, ui_thread, request = asyncio.run(scenario())
    assert threads == {ui_thread}
    assert request.total_col == "total"
    assert request.dimensions == ["card_type"]
    assert request._fraud_confirmation_source == "tui_modal"


# ──────────────────────────────────────────────────────────────────────
# D8: entity loading uses the resolved CSV path
# ──────────────────────────────────────────────────────────────────────


def test_entity_values_load_for_a_path_with_surrounding_spaces() -> None:
    async def scenario() -> list[Any]:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            padded = f"  {FIXTURE}  "
            app.query_one("#csv_path").value = padded
            app._try_load_csv_from_path_input(padded)
            await pilot.pause()
            assert await _until(pilot, lambda: not app.entity_values_loading)
            await pilot.pause()
            select = app.query_one("#entity_name", Select)
            return [value for _, value in select._options if value != SELECT_BLANK]

    assert "Target" in asyncio.run(scenario())


# ──────────────────────────────────────────────────────────────────────
# Owner decision 1: engine cancel and stage hook, wired minimally
# ──────────────────────────────────────────────────────────────────────


def test_request_cancel_stops_the_engine_before_anything_is_written(tmp_path: Path) -> None:
    async def scenario() -> tuple[str, str, list[str]]:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            await _share_form(pilot, tmp_path)
            app.query_one("#share_export_csv", Checkbox).value = True
            stages: list[str] = []
            real_report = app._report_run_stage

            def report(stage: str) -> None:
                stages.append(stage)
                if stage == "input":
                    app.request_cancel()  # as Quit does, from any thread
                real_report(stage)

            app._report_run_stage = report  # type: ignore[method-assign]
            app.run_analysis()
            assert await _until(pilot, lambda: app._run_state == "cancelled", 60)
            log_text = "\n".join(app.query_one("#log_output", Log).lines)
            results = str(app.query_one("#results_panel", Static).content)
            return log_text, results, stages

    log_text, results, stages = asyncio.run(scenario())
    assert stages == ["configuration", "input"]
    assert "Run cancelled before any output was written" in log_text
    assert "nothing was written" in results
    assert not (tmp_path / "share.xlsx").exists()
    assert list(tmp_path.glob("*.csv")) == []


def test_stage_callback_updates_run_status_text() -> None:
    async def scenario() -> str:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            app._begin_run_ui()
            app._set_run_stage("analysis")
            await pilot.pause()
            text = str(app.query_one("#run_status", Static).content)
            app._end_run_ui("cancelled", "")
            return text

    assert "Optimizing and checking privacy" in asyncio.run(scenario())


def test_quit_during_engine_cancels_at_next_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Quit while the engine runs stops it, so the process can exit."""
    cancelled: list[tuple[str, str]] = []
    monkeypatch.setattr(
        tui_app, "action_cancelled", lambda action, prompt: cancelled.append((action, prompt))
    )
    engine_saw_cancel = threading.Event()

    def fake_execute_run(request, logger, *, cancel_requested, on_stage):
        on_stage("analysis")
        deadline = time.monotonic() + 20
        while not cancel_requested():
            if time.monotonic() > deadline:
                raise AssertionError("cancel never requested")
            time.sleep(0.01)
        engine_saw_cancel.set()
        raise RunCancelled("analysis")

    monkeypatch.setattr(tui_app, "execute_run", fake_execute_run)
    workers: list[threading.Thread] = []

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            await _share_form(pilot, tmp_path)
            before = set(threading.enumerate())
            app.run_analysis()
            assert await _until(pilot, lambda: app._run_state == "running")
            assert await _until(
                pilot,
                lambda: "Optimizing" in str(app.query_one("#run_status", Static).content),
            )
            workers.extend(t for t in threading.enumerate() if t not in before)
            app.action_quit()
            await _wait_for_screen(pilot, ConfirmScreen)
            # D3 applies to the quit dialog too: Enter keeps working.
            assert app.focused is not None and app.focused.id == "btn_confirm_no"
            app.screen.query_one("#btn_confirm_yes", Button).press()
            await pilot.pause(0.2)

    runner = threading.Thread(target=lambda: asyncio.run(scenario()), daemon=True)
    runner.start()
    runner.join(timeout=60)
    assert not runner.is_alive(), "app did not exit"
    assert engine_saw_cancel.wait(timeout=5)
    for worker in workers:
        worker.join(timeout=5)
        assert not worker.is_alive(), "analysis worker still running after quit"
    assert cancelled == [("share_analysis", "quit_during_run")]


# ──────────────────────────────────────────────────────────────────────
# Owner decisions 4, 5 and 6
# ──────────────────────────────────────────────────────────────────────


def test_rate_total_has_no_smart_default(tmp_path: Path) -> None:
    csv_path = tmp_path / "with_txn_cnt.csv"
    csv_path.write_text(
        "issuer_name,txn_cnt,app_cnt,card_type\nA,10,9,X\n", encoding="utf-8"
    )

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            _load_fixture(app, str(csv_path))
            await pilot.pause()
            assert app.query_one("#rate_total", Select).value == SELECT_BLANK
            # The other smart defaults are unchanged.
            assert app.query_one("#share_metric", Select).value == "txn_cnt"
            assert app.query_one("#rate_approved", Select).value == "app_cnt"
            assert app.query_one("#entity_col", Select).value == "issuer_name"

    asyncio.run(scenario())


def test_balanced_csv_export_defaults_off_for_share_and_rate() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            assert app.query_one("#share_export_csv", Checkbox).value is False
            assert app.query_one("#rate_export_csv", Checkbox).value is False

    asyncio.run(scenario())


def test_cli_balanced_csv_export_defaults_off() -> None:
    parser = benchmark.create_parser()
    for mode, extra in (
        ("share", ["--metric", "txn_cnt"]),
        ("rate", ["--total-col", "total", "--approved-col", "approved"]),
    ):
        args = parser.parse_args([mode, "--csv", "data.csv", *extra])
        assert args.export_balanced_csv is False


def test_rate_mode_sweep_is_unlocked_and_sent_as_shown() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=SIZE) as pilot:
            app = pilot.app
            await pilot.pause()
            sweep = app.query_one("#privacy_rule_sweep_mode", Checkbox)
            assert sweep.value is False
            app.query_one("#privacy_release_mode", Select).value = (
                PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE.value
            )
            await pilot.pause()
            assert sweep.disabled is True and sweep.value is True

            app.query_one(TabbedContent).active = "rate_tab"
            await pilot.pause()
            # The VSC lock is share-only: rate shows and sends its own value.
            assert sweep.disabled is False
            assert sweep.value is False
            values = app._privacy_values_from_widgets()
            assert values["privacy_rule_strategy"] is PrivacyRuleStrategy.SELECT_BY_PEER_COUNT
            assert values["privacy_release_mode"] is None

            sweep.value = True
            await pilot.pause()
            values = app._privacy_values_from_widgets()
            assert values["privacy_rule_strategy"] is PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE
            sweep.value = False
            await pilot.pause()

            app.query_one(TabbedContent).active = "share_tab"
            await pilot.pause()
            assert sweep.disabled is True and sweep.value is True
            app.query_one("#privacy_release_mode", Select).value = (
                PrivacyReleaseMode.COMPLETE_OUTPUT.value
            )
            await pilot.pause()
            assert sweep.disabled is False and sweep.value is False

    asyncio.run(scenario())
