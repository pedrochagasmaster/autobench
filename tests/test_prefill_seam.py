"""Tests for the New Job prefill path and the DISPATCH_TEST_PREFILL seam."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from dispatch.app import DispatchApp
from dispatch.screens.new_job import NewJobScreen


def _write_sql(data_root: Path) -> Path:
    sql_path = data_root / "smoke.sql"
    sql_path.write_text("SELECT 1 AS smoke_check;\n", encoding="utf-8")
    return sql_path


def test_prefill_selects_table_destination(mock_env_with_config) -> None:
    data_root = Path(os.environ["DISPATCH_DATA_ROOT"])
    sql_path = _write_sql(data_root)
    prefill = {
        "source_type": "SqlFile",
        "dest_type": "Table",
        "sql_file": str(sql_path),
        "schema": "aa_enc",
        "table_name": "smoke_tbl",
    }

    async def run() -> None:
        app = DispatchApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.5)
            app.push_screen(NewJobScreen(app.launch_cwd, prefill=prefill))
            await pilot.pause(0.5)
            screen = app.screen
            assert isinstance(screen, NewJobScreen)
            assert screen._selected_destination() == "Table"
            assert screen._selected_source() == "SqlFile"
            assert screen.query_one("#row-schema").display is True
            assert screen.query_one("#row-table-name").display is True

    asyncio.run(run())


def test_prefill_hides_picker_and_keeps_table_rows(mock_env_with_config) -> None:
    """A prefilled (re-run / test) form suppresses the redundant cwd SQL picker.

    Regression: when the picker-populate worker showed the file list, the taller
    table-producing forms (Table / Table+Csv / SqlTemplate) pushed the Schema and
    Table Name rows below a single SSH pane's fold, so the harness could not see
    them. The SQL path is already known on a prefilled form, so the picker must
    stay hidden even after the background populate worker runs.
    """
    data_root = Path(os.environ["DISPATCH_DATA_ROOT"])
    sql_path = _write_sql(data_root)
    prefill = {
        "source_type": "SqlFile",
        "dest_type": "Table+Csv",
        "sql_file": str(sql_path),
        "schema": "aa_enc",
        "table_name": "smoke_tbl",
    }

    async def run() -> None:
        app = DispatchApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.5)
            app.push_screen(NewJobScreen(data_root, prefill=prefill))
            # Let the background picker-populate worker run to completion.
            await pilot.pause(1.0)
            screen = app.screen
            assert isinstance(screen, NewJobScreen)
            assert screen._cwd_sql_files, "worker should have scanned the cwd SQL file"
            assert screen.query_one("#sql-file-picker").display is False
            assert screen.query_one("#picker-caption").display is False
            assert screen.query_one("#row-table-name").display is True
            assert screen.query_one("#row-schema").display is True
            assert screen._selected_destination() == "Table+Csv"

    asyncio.run(run())


def test_non_prefilled_form_still_shows_picker(mock_env_with_config) -> None:
    """The file-first flow is unchanged for a fresh (non-prefilled) New Job."""
    data_root = Path(os.environ["DISPATCH_DATA_ROOT"])
    _write_sql(data_root)

    async def run() -> None:
        app = DispatchApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.5)
            app.push_screen(NewJobScreen(data_root))
            await pilot.pause(1.0)
            screen = app.screen
            assert isinstance(screen, NewJobScreen)
            assert screen._cwd_sql_files
            assert screen.query_one("#sql-file-picker").display is True

    asyncio.run(run())


def test_test_prefill_seam_opens_new_job(mock_env_with_config, monkeypatch) -> None:
    data_root = Path(os.environ["DISPATCH_DATA_ROOT"])
    sql_path = _write_sql(data_root)
    prefill_file = data_root / "prefill.json"
    prefill_file.write_text(
        json.dumps(
            {
                "source_type": "SqlFile",
                "dest_type": "Table",
                "sql_file": str(sql_path),
                "schema": "aa_enc",
                "table_name": "smoke_tbl",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DISPATCH_TEST_PREFILL", str(prefill_file))

    async def run() -> None:
        app = DispatchApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.8)
            screen = app.screen
            assert isinstance(screen, NewJobScreen)
            assert screen._selected_destination() == "Table"

    asyncio.run(run())
