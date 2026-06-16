"""Regression tests for the production polish pass (design system + UX fixes)."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from textual.widgets import DataTable, RadioButton, RadioSet

from dispatch import manifest
from dispatch.app import DispatchApp
from dispatch.formatting import format_kerberos_ttl, format_state, format_timestamp
from dispatch.screens.job_detail import JobDetailScreen
from dispatch.screens.new_job import NewJobScreen
from dispatch.screens.sidebar import KerberosChip


def _seed_job(jobs_dir: Path, job_id: str, state: str, *, pid: int | None = None) -> str:
    job_dir = jobs_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    finished = (
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if state not in ("Running", "Pending")
        else None
    )
    manifest.write(
        job_dir / "manifest.json",
        {
            "schema_version": 1,
            "id": job_id,
            "tool": "dispatch",
            "user": "testuser",
            "source": {"type": "SqlFile", "sql_path_at_launch": "/tmp/q.sql"},
            "destination": {
                "type": "Csv",
                "schema": "aa_enc",
                "table_name": "t",
                "csv_path": "/tmp/t.csv",
            },
            "params": {},
            "orchestrator_calls": [{"script": "download_to_csv.py", "argv": ["python3", "x.py"]}],
            "state": state,  # type: ignore[typeddict-item]
            "pid": pid,
            "started_at": "2026-05-20T12:00:00Z",
            "finished_at": finished,
            "exit_code": 0 if state == "Succeeded" else None,
        },
    )
    (job_dir / "run.log").write_text("line\n", encoding="utf-8")
    return job_id


class TestFormatting:
    def test_format_state_pairs_symbol_and_label(self) -> None:
        assert "\u2713 SUCCEEDED" in format_state("Succeeded")
        assert "\u2717 FAILED" in format_state("Failed")
        assert "\u25cf RUNNING" in format_state("Running")
        assert "\u25cb CANCELLED" in format_state("Cancelled")

    def test_format_state_appends_error_code(self) -> None:
        assert "FAILED \u00b7 SYNTAX" in format_state("Failed", "SYNTAX")

    def test_format_timestamp_humanizes_utc(self) -> None:
        assert format_timestamp(None) == "--"
        result = format_timestamp("2026-05-20T12:34:56Z")
        assert "T" not in result and result.count(":") == 1

    def test_format_kerberos_ttl(self) -> None:
        assert format_kerberos_ttl(None) == "missing"
        assert format_kerberos_ttl(7260) == "2h 01m"
        assert format_kerberos_ttl(540) == "9m"


def test_template_source_auto_corrects_illegal_destination(mock_env_with_config) -> None:
    """Detecting SqlTemplate must move an illegal Csv destination to Table."""

    async def run() -> None:
        app = DispatchApp()
        async with app.run_test(size=(140, 50)) as pilot:
            screen = NewJobScreen(Path("/tmp"))
            app.push_screen(screen)
            await pilot.pause()
            # Default destination is Csv; switching source to SqlTemplate makes
            # that cell illegal and must auto-select Table.
            screen.query_one("#src-sqltemplate", RadioButton).value = True
            await pilot.pause(0.5)
            dest = screen.query_one("#destination", RadioSet)
            assert dest.pressed_button is not None
            assert dest.pressed_button.id == "dst-table"
            assert screen._validate() != (
                "Illegal Source/Destination cell: SqlTemplate/Csv"
            )

    asyncio.run(run())


def test_job_detail_hides_cancel_for_finished_jobs(mock_env_with_config) -> None:
    """The Cancel binding and button must not be offered on terminal states."""
    data_root = Path(os.environ["DISPATCH_DATA_ROOT"])
    jobs_dir = data_root / ".dispatch" / "jobs"
    job_id = _seed_job(jobs_dir, "20260520T120000Z_done01", "Succeeded")

    async def run() -> None:
        app = DispatchApp()
        async with app.run_test(size=(120, 40)) as pilot:
            app.push_screen(JobDetailScreen(job_id))
            await pilot.pause(1.0)
            screen = app.screen
            assert isinstance(screen, JobDetailScreen)
            assert screen.check_action("cancel", ()) is False
            assert screen.check_action("clone_job", ()) is True
            assert screen.query_one("#cancel").display is False
            assert screen.query_one("#clone").display is True

    asyncio.run(run())


def test_job_detail_offers_cancel_for_running_jobs(mock_env_with_config) -> None:
    data_root = Path(os.environ["DISPATCH_DATA_ROOT"])
    jobs_dir = data_root / ".dispatch" / "jobs"
    job_id = _seed_job(jobs_dir, "20260520T120000Z_run001", "Running", pid=99999)

    async def run() -> None:
        app = DispatchApp()
        async with app.run_test(size=(120, 40)) as pilot:
            app.push_screen(JobDetailScreen(job_id))
            await pilot.pause(1.0)
            screen = app.screen
            assert isinstance(screen, JobDetailScreen)
            assert screen.check_action("cancel", ()) is True
            assert screen.query_one("#cancel").display is True
            assert screen.query_one("#clone").display is False

    asyncio.run(run())


def test_dashboard_preserves_cursor_across_refresh(mock_env_with_config) -> None:
    """The selected row must survive the periodic table rebuild."""
    data_root = Path(os.environ["DISPATCH_DATA_ROOT"])
    jobs_dir = data_root / ".dispatch" / "jobs"
    for index in range(3):
        _seed_job(jobs_dir, f"20260520T12000{index}Z_job{index:03d}", "Succeeded")

    async def run() -> None:
        app = DispatchApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(1.0)
            screen = app.screen
            table = screen.query_one("#jobs-table", DataTable)
            assert table.row_count == 3

            await pilot.press("down")
            await pilot.pause()
            selected_before = table.coordinate_to_cell_key(
                table.cursor_coordinate
            ).row_key.value

            # Force a content change so the rebuild path runs, then refresh.
            _seed_job(jobs_dir, "20260520T120009Z_jobnew", "Succeeded")
            await screen._refresh_jobs_async()
            await pilot.pause()

            assert table.row_count == 4
            selected_after = table.coordinate_to_cell_key(
                table.cursor_coordinate
            ).row_key.value
            assert selected_after == selected_before

    asyncio.run(run())


def test_sidebar_kerberos_chip_mirrors_app_state(mock_env_with_config, monkeypatch) -> None:
    async def fake_ttl() -> int:
        return 7200

    monkeypatch.setattr("dispatch.kerberos.ticket_ttl_seconds", fake_ttl)

    async def run() -> None:
        app = DispatchApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(1.0)
            chip = app.screen.query_one(KerberosChip)
            assert chip.ttl_seconds == 7200
            assert "KRB 2h 00m" in str(chip.render())

    asyncio.run(run())
