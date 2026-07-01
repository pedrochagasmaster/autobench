"""Tests for production TUI behaviours: layout panels, session persistence,
select sentinel handling, and launch preflight checks."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import yaml
from textual.widgets import Checkbox, Select, SelectionList, Static

import tui_app
from tui_app import SELECT_BLANK, BenchmarkApp

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "gate_demo.csv"


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
    assert saved["csv_path"] == str(FIXTURE)
    assert saved["entity_name"] == "Target"
    assert saved["share_dims"] == ["card_type"]

    async def restore_scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 45)) as pilot:
            app = pilot.app
            await pilot.pause(0.3)
            assert app.query_one("#csv_path").value == str(FIXTURE)
            assert app.query_one("#entity_col", Select).value == "issuer_name"
            assert app.query_one("#entity_name", Select).value == "Target"
            assert app.query_one("#time_col", Select).value == "year_month"
            assert app.query_one("#share_dims", SelectionList).selected == ["card_type"]

    asyncio.run(restore_scenario())


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
            log_text = ""
            for _ in range(40):
                await pilot.pause(0.25)
                log_text = "\n".join(app.query_one("#log_output").lines)
                if "ERROR:" in log_text:
                    break
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
            log_text = ""
            for _ in range(120):
                await pilot.pause(0.5)
                log_text = "\n".join(app.query_one("#log_output").lines)
                if "Analysis completed successfully" in log_text or "Execution" in log_text:
                    break
            await pilot.pause(0.5)
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
            log_text = ""
            for _ in range(120):
                await pilot.pause(0.5)
                log_text = "\n".join(app.query_one("#log_output").lines)
                if "Analysis completed successfully" in log_text or "Execution" in log_text:
                    break
            return log_text, app._run_state

    log_text, run_state = asyncio.run(scenario())
    assert "Balanced CSV:" in log_text
    assert "Analysis completed successfully" in log_text
    assert run_state == "success"
    assert output.exists()
