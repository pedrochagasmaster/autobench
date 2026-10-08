"""Tests for production TUI behaviours: layout panels, session persistence,
select sentinel handling, and launch preflight checks."""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml
from textual.pilot import Pilot
from textual.widgets import Checkbox, Select, SelectionList, Static, TabbedContent

import tui_app
from core.contracts import AnalysisRunRequest
from tui_app import SELECT_BLANK, BenchmarkApp, ClearingSpendConfirmScreen

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "gate_demo.csv"

_RUN_FINISHED_STATES = frozenset({"success", "error", "blocked"})


async def _await_run_completion(pilot: Pilot, timeout: float = 60.0) -> str:
    """Wait for the run worker to publish its final state, then return the log.

    The worker writes "Analysis completed successfully" to the log several
    ``call_from_thread`` hops before it calls ``_end_run_ui``, so waiting on
    the log text alone can read ``_run_state`` while it is still ``running``.
    """
    deadline = time.monotonic() + timeout
    while pilot.app._run_state not in _RUN_FINISHED_STATES:
        if time.monotonic() >= deadline:
            break
        await pilot.pause(0.1)
    return "\n".join(pilot.app.query_one("#log_output").lines)


async def _await_refused_launch(pilot: Pilot, timeout: float = 30.0) -> str:
    """Wait for a refused launch to restore the idle run controls, then return the log.

    ``_fail_launch`` posts its ``ERROR:`` line to the log one
    ``call_from_thread`` hop before it re-enables the run button, so waiting on
    the log text alone can read the run controls while they are still
    ``validating``.
    """
    deadline = time.monotonic() + timeout
    log_text = ""
    while True:
        log_text = "\n".join(pilot.app.query_one("#log_output").lines)
        if "ERROR:" in log_text and pilot.app._run_state == "idle":
            break
        if time.monotonic() >= deadline:
            break
        await pilot.pause(0.05)
    return log_text


async def _configure_rate_form(
    pilot: Pilot,
    tmp_path: Path,
    *,
    fraud: bool,
    approval: bool,
    validate_input: bool = False,
) -> None:
    app = pilot.app
    app.query_one("#csv_path").value = str(FIXTURE)
    app.load_csv_headers(str(FIXTURE))
    app.query_one(TabbedContent).active = "rate_tab"
    await pilot.pause()
    app.query_one("#rate_total", Select).value = "total"
    app.query_one("#rate_fraud", Select).value = "fraud" if fraud else SELECT_BLANK
    app.query_one("#rate_approved", Select).value = (
        "approved" if approval else SELECT_BLANK
    )
    app.query_one("#rate_dims", SelectionList).select("card_type")
    app.query_one("#output_file").value = str(tmp_path / "rate.xlsx")
    app.query_one("#validate_input", Checkbox).value = validate_input


def test_select_blank_sentinel_matches_empty_select_value(tmp_path: Path, monkeypatch) -> None:
    """Select.BLANK stopped being the no-selection sentinel in newer Textual;
    the app-level sentinel must match what an empty Select actually reports."""
    monkeypatch.setattr(tui_app, "SESSION_FILE", tmp_path / "session.yaml")

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            entity = pilot.app.query_one("#entity_name", Select)
            assert entity.value == SELECT_BLANK

    asyncio.run(scenario())


def test_load_csv_headers_populates_columns_and_meta(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tui_app, "SESSION_FILE", tmp_path / "session.yaml")

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 45)) as pilot:
            app = pilot.app
            await pilot.pause()
            app.query_one("#csv_path").value = str(FIXTURE)
            app.load_csv_headers(str(FIXTURE))
            await pilot.pause()

            assert app.query_one("#entity_col", Select).value == "issuer_name"
            assert app.query_one("#share_metric", Select).value == "txn_cnt"
            meta_text = str(app.query_one("#csv_meta", Static).content)
            assert "gate_demo.csv" in meta_text
            assert "8 columns" in meta_text

    asyncio.run(scenario())


def test_load_csv_headers_preserves_existing_selections(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tui_app, "SESSION_FILE", tmp_path / "session.yaml")

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 45)) as pilot:
            app = pilot.app
            await pilot.pause()
            app.query_one("#csv_path").value = str(FIXTURE)
            app.load_csv_headers(str(FIXTURE))
            await pilot.pause()

            app.query_one("#share_metric", Select).value = "total"
            dims = app.query_one("#share_dims", SelectionList)
            dims.select("card_type")
            dims.select("channel")

            # Re-picking the same file must not wipe user selections.
            app.load_csv_headers(str(FIXTURE))
            await pilot.pause()

            assert app.query_one("#share_metric", Select).value == "total"
            assert set(app.query_one("#share_dims", SelectionList).selected) == {"card_type", "channel"}

    asyncio.run(scenario())


def test_session_round_trip_restores_form(tmp_path: Path, monkeypatch) -> None:
    session_file = tmp_path / "session.yaml"
    monkeypatch.setattr(tui_app, "SESSION_FILE", session_file)

    async def save_scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 45)) as pilot:
            app = pilot.app
            await pilot.pause()
            app.query_one("#csv_path").value = str(FIXTURE)
            app.load_csv_headers(str(FIXTURE))
            await pilot.pause()
            app.query_one("#entity_col", Select).value = "issuer_name"
            app.load_unique_entities("issuer_name")
            app.query_one("#entity_name", Select).value = "Target"
            app.query_one("#time_col", Select).value = "year_month"
            app.query_one("#share_dims", SelectionList).select("card_type")
            app._save_session()

    asyncio.run(save_scenario())

    saved = yaml.safe_load(session_file.read_text())
    assert "csv_path" not in saved
    assert "output_file" not in saved
    assert "entity_name" not in saved
    assert "citibank_entity_name" not in saved
    # Per-run compliance attestations must never be carried across sessions.
    assert "citi_competitor_receives_output" not in saved
    assert "privacy_merchant_spend_scope" not in saved
    assert "acknowledge_accuracy_first" not in saved
    assert saved["share_dims"] == ["card_type"]

    async def restore_scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 45)) as pilot:
            app = pilot.app
            await pilot.pause(0.3)
            assert app.query_one("#csv_path").value == ""
            assert app.query_one("#entity_col", Select).value == SELECT_BLANK
            assert app.query_one("#entity_name", Select).value == SELECT_BLANK
            assert app.query_one("#time_col", Select).value == SELECT_BLANK
            assert app.query_one("#share_dims", SelectionList).selected == []

    asyncio.run(restore_scenario())


def test_restore_session_never_restores_compliance_attestations(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_file = tmp_path / "session.yaml"
    session_file.write_text(
        yaml.safe_dump(
            {
                "citi_competitor_receives_output": True,
                "privacy_merchant_spend_scope": True,
                "acknowledge_accuracy_first": True,
            }
        )
    )
    monkeypatch.setattr(tui_app, "SESSION_FILE", session_file)

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 45)) as pilot:
            app = pilot.app
            await pilot.pause()
            for widget_id in (
                "citi_competitor_receives_output",
                "privacy_merchant_spend_scope",
            ):
                assert app.query_one(f"#{widget_id}", Checkbox).value is False
            # The acknowledgement checkbox no longer exists; consent is a
            # per-run modal and cannot be restored from a session file.
            assert not app.query("#acknowledge_accuracy_first")

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("button_id", "expected"),
    [("btn_confirm_yes", True), ("btn_confirm_no", False)],
)
def test_accuracy_first_consent_modal_round_trip(
    tmp_path: Path,
    monkeypatch,
    button_id: str,
    expected: bool,
) -> None:
    """The per-run consent modal returns the operator's actual answer."""
    monkeypatch.setattr(tui_app, "SESSION_FILE", tmp_path / "session.yaml")

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 45)) as pilot:
            app = pilot.app
            await pilot.pause()
            outcome: dict[str, bool] = {}
            worker = threading.Thread(
                target=lambda: outcome.setdefault(
                    "value", app._confirm_accuracy_first_consent()
                )
            )
            worker.start()
            for _ in range(50):
                await pilot.pause(0.1)
                if app.query(f"#{button_id}"):
                    break
            await pilot.click(f"#{button_id}")
            worker.join(timeout=5)
            assert not worker.is_alive()
            assert outcome["value"] is expected

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("button_id", "expected"),
    [("btn_confirm_yes", True), ("btn_confirm_no", False)],
)
def test_clearing_spend_confirmation_modal_uses_selected_total(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    button_id: str,
    expected: bool,
) -> None:
    monkeypatch.setattr(tui_app, "SESSION_FILE", tmp_path / "session.yaml")

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 45)) as pilot:
            app = pilot.app
            await pilot.pause()
            outcome: dict[str, bool] = {}
            worker = threading.Thread(
                target=lambda: outcome.setdefault(
                    "value",
                    app._confirm_clearing_spend_basis("governed_total"),
                )
            )
            worker.start()
            for _ in range(50):
                await pilot.pause(0.1)
                if isinstance(app.screen, ClearingSpendConfirmScreen):
                    break
            assert isinstance(app.screen, ClearingSpendConfirmScreen)
            message = str(app.screen.query_one("#confirm_message", Static).content)
            assert "Confirm clearing-spend basis" in message
            assert "`governed_total`" in message
            await pilot.click(f"#{button_id}")
            worker.join(timeout=5)
            assert not worker.is_alive()
            assert outcome["value"] is expected

    asyncio.run(scenario())


def test_fraud_confirmation_cancel_stops_before_loading_and_logging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tui_app, "SESSION_FILE", tmp_path / "session.yaml")
    monkeypatch.setenv("AUTOBENCH_LOG_DIR", str(tmp_path / "logs"))
    prepare = MagicMock(side_effect=AssertionError("CSV loading must not start"))
    setup_logging = MagicMock()
    cancelled: list[str] = []
    monkeypatch.setattr(tui_app, "prepare_run_data", prepare)
    monkeypatch.setattr(tui_app, "setup_deferred_logging", setup_logging)
    monkeypatch.setattr(tui_app, "action_cancelled", cancelled.append)

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            await _configure_rate_form(
                pilot,
                tmp_path,
                fraud=True,
                approval=False,
                validate_input=True,
            )
            pilot.app.run_analysis()
            for _ in range(50):
                await pilot.pause(0.1)
                if isinstance(pilot.app.screen, ClearingSpendConfirmScreen):
                    break
            assert isinstance(pilot.app.screen, ClearingSpendConfirmScreen)
            await pilot.click("#btn_confirm_no")
            for _ in range(50):
                await pilot.pause(0.1)
                if pilot.app._run_state == "idle":
                    break

    asyncio.run(scenario())
    prepare.assert_not_called()
    setup_logging.assert_not_called()
    assert not (tmp_path / "logs").exists()
    assert cancelled == ["rate_analysis"]


def test_fraud_confirmation_continues_run_and_marks_tui_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tui_app, "SESSION_FILE", tmp_path / "session.yaml")

    async def scenario() -> AnalysisRunRequest:
        async with BenchmarkApp().run_test(size=(140, 45)) as pilot:
            app = pilot.app
            await pilot.pause()
            await _configure_rate_form(
                pilot,
                tmp_path,
                fraud=True,
                approval=True,
            )
            executed = MagicMock()
            app._execute_confirmed_analysis = executed  # type: ignore[method-assign]
            app.run_analysis()
            for _ in range(50):
                await pilot.pause(0.1)
                if isinstance(app.screen, ClearingSpendConfirmScreen):
                    break
            assert isinstance(app.screen, ClearingSpendConfirmScreen)
            await pilot.click("#btn_confirm_yes")
            for _ in range(50):
                await pilot.pause(0.1)
                if executed.called:
                    break
            assert executed.called
            return executed.call_args.args[0]

    request = asyncio.run(scenario())
    assert request.approved_col == "approved"
    assert request.fraud_col == "fraud"
    assert request._fraud_confirmation_source == "tui_modal"


def test_approval_only_tui_run_skips_clearing_spend_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tui_app, "SESSION_FILE", tmp_path / "session.yaml")

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 45)) as pilot:
            app = pilot.app
            await pilot.pause()
            await _configure_rate_form(
                pilot,
                tmp_path,
                fraud=False,
                approval=True,
            )
            confirm = MagicMock(side_effect=AssertionError("Approval runs must not ask"))
            executed = MagicMock()
            app._confirm_clearing_spend_basis = confirm  # type: ignore[method-assign]
            app._execute_confirmed_analysis = executed  # type: ignore[method-assign]
            app.run_analysis()
            for _ in range(50):
                await pilot.pause(0.1)
                if executed.called:
                    break
            confirm.assert_not_called()
            assert executed.called

    asyncio.run(scenario())


def test_new_fraud_run_attempt_shows_confirmation_again(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tui_app, "SESSION_FILE", tmp_path / "session.yaml")
    monkeypatch.setattr(tui_app, "action_cancelled", lambda _action: None)

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            await _configure_rate_form(
                pilot,
                tmp_path,
                fraud=True,
                approval=False,
            )
            for _attempt in range(2):
                pilot.app.run_analysis()
                for _ in range(50):
                    await pilot.pause(0.1)
                    if isinstance(
                        pilot.app.screen,
                        ClearingSpendConfirmScreen,
                    ):
                        break
                assert isinstance(
                    pilot.app.screen,
                    ClearingSpendConfirmScreen,
                )
                await pilot.click("#btn_confirm_no")
                for _ in range(50):
                    await pilot.pause(0.1)
                    if pilot.app._run_state == "idle":
                        break

    asyncio.run(scenario())


def test_validation_retry_reuses_confirmed_fraud_request() -> None:
    app = BenchmarkApp()
    request = AnalysisRunRequest(
        mode="rate",
        total_col="total",
        fraud_col="fraud",
    )
    request._fraud_confirmation_source = "tui_modal"
    app.run_analysis = MagicMock()  # type: ignore[method-assign]
    saved_df = MagicMock()

    app._handle_validation_modal_result(
        True,
        has_errors=False,
        should_abort=False,
        request=request,
        saved_df=saved_df,
        log_widget=MagicMock(),
    )

    app.run_analysis.assert_called_once_with(
        confirmed=True,
        saved_request=request,
        saved_df=saved_df,
    )


def test_restore_session_ignores_stale_values(tmp_path: Path, monkeypatch) -> None:
    session_file = tmp_path / "session.yaml"
    session_file.write_text(
        yaml.safe_dump(
            {
                "csv_path": str(tmp_path / "deleted.csv"),
                "entity_col": "missing_column",
                "preset_select": "no_such_preset",
            }
        )
    )
    monkeypatch.setattr(tui_app, "SESSION_FILE", session_file)

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 45)) as pilot:
            app = pilot.app
            await pilot.pause()
            assert app.query_one("#csv_path").value == ""
            assert app.query_one("#entity_col", Select).value == SELECT_BLANK

    asyncio.run(scenario())


def test_restore_session_ignores_valid_legacy_sensitive_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_file = tmp_path / "session.yaml"
    csv_path = tmp_path / "legacy.csv"
    csv_path.write_bytes(FIXTURE.read_bytes())
    output_path = tmp_path / "legacy_output.xlsx"
    session_file.write_text(
        yaml.safe_dump(
            {
                "csv_path": str(csv_path),
                "output_file": str(output_path),
                "entity_col": "issuer_name",
                "entity_name": "Target",
            }
        )
    )
    monkeypatch.setattr(tui_app, "SESSION_FILE", session_file)

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 45)) as pilot:
            app = pilot.app
            await pilot.pause()
            assert app.query_one("#csv_path").value == ""
            assert app.query_one("#output_file").value == ""
            assert app.query_one("#entity_col", Select).value == SELECT_BLANK
            assert app.query_one("#entity_name", Select).value == SELECT_BLANK

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("missing", "expected_fragment"),
    [
        ("csv", "CSV path is required"),
        ("metric", "Primary metric is required"),
        ("dims", "Select at least one dimension"),
    ],
)
def test_preflight_blocks_invalid_launches(tmp_path: Path, monkeypatch, missing: str, expected_fragment: str) -> None:
    monkeypatch.setattr(tui_app, "SESSION_FILE", tmp_path / "session.yaml")

    async def scenario() -> str:
        async with BenchmarkApp().run_test(size=(140, 45)) as pilot:
            app = pilot.app
            await pilot.pause()
            if missing != "csv":
                app.query_one("#csv_path").value = str(FIXTURE)
                app.load_csv_headers(str(FIXTURE))
                await pilot.pause()
                app.query_one("#validate_input", Checkbox).value = False
            if missing == "metric":
                app.query_one("#share_metric", Select).clear()
            if missing == "dims":
                app.query_one("#share_metric", Select).value = "txn_cnt"
                # auto-detect off and nothing selected in #share_dims

            app.run_analysis()
            log_text = await _await_refused_launch(pilot)
            # Run button must be re-enabled after a refused launch
            assert app.query_one("#btn_run").disabled is False
            assert app._run_state == "idle"
            return log_text

    log_text = asyncio.run(scenario())
    assert expected_fragment in log_text


def test_successful_run_updates_status_and_results(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tui_app, "SESSION_FILE", tmp_path / "session.yaml")
    output = tmp_path / "ux_run.xlsx"

    async def scenario() -> tuple[str, str, str]:
        async with BenchmarkApp().run_test(size=(140, 45)) as pilot:
            app = pilot.app
            await pilot.pause()
            app.query_one("#csv_path").value = str(FIXTURE)
            app.load_csv_headers(str(FIXTURE))
            await pilot.pause()
            app.query_one("#entity_col", Select).value = "issuer_name"
            app.load_unique_entities("issuer_name")
            app.query_one("#entity_name", Select).value = "Target"
            app.query_one("#time_col", Select).value = "year_month"
            app.query_one("#share_metric", Select).value = "txn_cnt"
            dims = app.query_one("#share_dims", SelectionList)
            dims.select("card_type")
            dims.select("channel")
            app.query_one("#output_file").value = str(output)
            # Keep input validation on: clean fixture data produces no issues,
            # so the run proceeds and the verdict is fully_compliant.
            app.query_one("#validate_input", Checkbox).value = True

            app.run_analysis()
            log_text = await _await_run_completion(pilot)
            results_text = str(app.query_one("#results_panel", Static).content)
            return log_text, results_text, app._run_state

    log_text, results_text, run_state = asyncio.run(scenario())
    assert "Analysis completed successfully" in log_text
    assert run_state == "success"
    assert "fully_compliant" in results_text
    assert output.exists()


def test_successful_run_ignores_broken_headless_stdout(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tui_app, "SESSION_FILE", tmp_path / "session.yaml")
    output = tmp_path / "ux_run_broken_stdout.xlsx"

    class BrokenStream:
        def write(self, text: str) -> None:
            raise OSError(6, "The handle is invalid")

        def flush(self) -> None:
            return None

    async def scenario() -> tuple[str, str]:
        async with BenchmarkApp().run_test(size=(140, 45)) as pilot:
            app = pilot.app
            app._original_stdout = BrokenStream()
            app._original_stderr = BrokenStream()
            await pilot.pause()
            app.query_one("#csv_path").value = str(FIXTURE)
            app.load_csv_headers(str(FIXTURE))
            await pilot.pause()
            app.query_one("#entity_col", Select).value = "issuer_name"
            app.load_unique_entities("issuer_name")
            app.query_one("#entity_name", Select).value = "Target"
            app.query_one("#time_col", Select).value = "year_month"
            app.query_one("#share_metric", Select).value = "txn_cnt"
            dims = app.query_one("#share_dims", SelectionList)
            dims.select("card_type")
            dims.select("channel")
            app.query_one("#output_file").value = str(output)
            app.query_one("#validate_input", Checkbox).value = True

            app.run_analysis()
            log_text = await _await_run_completion(pilot)
            return log_text, app._run_state

    log_text, run_state = asyncio.run(scenario())
    assert "Balanced CSV:" in log_text
    assert "Analysis completed successfully" in log_text
    assert run_state == "success"
    assert output.exists()


def test_tui_log_directory_honors_runtime_isolation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    isolated = tmp_path / "tui_logs"
    monkeypatch.setenv("AUTOBENCH_LOG_DIR", str(isolated))

    assert tui_app._resolve_log_dir() == isolated
