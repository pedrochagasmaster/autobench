"""Regression tests for the supervision-cockpit wireframe and file-first launch."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

from textual.widgets import DataTable, Input, Static

from dispatch import manifest
from dispatch.app import DispatchApp
from dispatch.screens.new_job import NewJobScreen


def _seed_job(
    jobs_dir: Path,
    job_id: str,
    state: str,
    *,
    pid: int | None = None,
    log_lines: list[str] | None = None,
) -> str:
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
            "source": {"type": "SqlFile", "sql_path_at_launch": f"/tmp/{job_id}.sql"},
            "destination": {
                "type": "Csv",
                "schema": "aa_enc",
                "table_name": f"t_{job_id[-6:]}",
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
    (job_dir / "run.log").write_text(
        "\n".join(log_lines or ["[2026-05-20 12:00:01] started"]) + "\n",
        encoding="utf-8",
    )
    return job_id


def test_cockpit_merges_running_and_recent_with_running_first(
    mock_env_with_config,
) -> None:
    data_root = Path(os.environ["DISPATCH_DATA_ROOT"])
    jobs_dir = data_root / ".dispatch" / "jobs"
    # Seed so a finished job sorts *before* the running one by id; the cockpit
    # must still pin the running job to the top.
    _seed_job(jobs_dir, "20260520T130000Z_done01", "Succeeded")
    running = _seed_job(jobs_dir, "20260520T120000Z_run001", "Running", pid=4242)

    async def run() -> None:
        app = DispatchApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(1.0)
            table = app.screen.query_one("#jobs-table", DataTable)
            assert table.row_count == 2
            first_key = table.coordinate_to_cell_key((0, 0)).row_key.value
            assert first_key == running

    asyncio.run(run())


def test_cockpit_status_strip_replaces_stat_cards(mock_env_with_config) -> None:
    _seed = None

    async def run() -> None:
        app = DispatchApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(1.0)
            strip = str(app.screen.query_one("#status-strip", Static).render())
            assert "RUNNING" in strip
            assert "FINISHED" in strip
            assert "KERBEROS" in strip
            assert list(app.screen.query(".stat-card")) == []

    asyncio.run(run())


def test_cockpit_detail_pane_tails_selected_job_log(mock_env_with_config) -> None:
    data_root = Path(os.environ["DISPATCH_DATA_ROOT"])
    jobs_dir = data_root / ".dispatch" / "jobs"
    _seed_job(
        jobs_dir,
        "20260520T120000Z_tail01",
        "Succeeded",
        log_lines=["[2026-05-20 12:00:01] starting", "[2026-05-20 12:00:09] 1,284,003 rows"],
    )

    async def run() -> None:
        app = DispatchApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(1.5)
            detail_log = str(app.screen.query_one("#detail-log", Static).render())
            assert "1,284,003 rows" in detail_log
            title = str(app.screen.query_one("#detail-title", Static).render())
            assert "tail01" in title
            assert "SUCCEEDED" in title

    asyncio.run(run())


def test_cockpit_slash_filter_narrows_jobs(mock_env_with_config) -> None:
    data_root = Path(os.environ["DISPATCH_DATA_ROOT"])
    jobs_dir = data_root / ".dispatch" / "jobs"
    _seed_job(jobs_dir, "20260520T120000Z_aaaaaa", "Succeeded")
    _seed_job(jobs_dir, "20260520T120001Z_bbbbbb", "Failed")

    async def run() -> None:
        app = DispatchApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(1.0)
            screen = app.screen
            table = screen.query_one("#jobs-table", DataTable)
            assert table.row_count == 2

            await pilot.press("slash")
            await pilot.pause()
            filter_input = screen.query_one("#jobs-filter", Input)
            assert filter_input.display is True
            assert filter_input.has_focus

            await pilot.press("b", "b", "b")
            await pilot.pause(0.5)
            assert table.row_count == 1
            only_key = table.coordinate_to_cell_key((0, 0)).row_key.value
            assert only_key.endswith("bbbbbb")

            await pilot.press("escape")
            await pilot.pause(0.5)
            assert filter_input.display is False
            assert table.row_count == 2

    asyncio.run(run())


def test_new_job_picker_lists_cwd_files_and_fills_form(
    mock_env_with_config, tmp_path
) -> None:
    (tmp_path / "alpha.sql").write_text("select 1\n", encoding="utf-8")
    (tmp_path / "beta_template.sql").write_text(
        "select * from t where d between '{date_inicio}' and '{date_fim}'\n",
        encoding="utf-8",
    )

    async def run() -> None:
        app = DispatchApp()
        async with app.run_test(size=(140, 50)) as pilot:
            screen = NewJobScreen(tmp_path)
            app.push_screen(screen)
            await pilot.pause(1.0)

            picker = screen.query_one("#sql-file-picker", DataTable)
            assert picker.display is True
            assert picker.row_count == 2

            picker.focus()
            await pilot.press("down")
            await pilot.pause(0.5)

            assert screen.query_one("#sql-file", Input).value == str(
                tmp_path / "beta_template.sql"
            )
            # Picking the template flips source detection to SqlTemplate.
            assert screen._selected_source() == "SqlTemplate"

    asyncio.run(run())


def test_command_palette_exposes_dispatch_commands(mock_env_with_config) -> None:
    async def run() -> None:
        app = DispatchApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.5)
            titles = [command.title for command in app.get_system_commands(app.screen)]
            for expected in ("New Job", "History", "Browse metadata", "Refresh Kerberos (kinit)"):
                assert expected in titles, f"Missing palette command: {expected}"

    asyncio.run(run())
