"""Capture current Dispatch TUI review screenshots as SVG.

Usage:
    py -3 tools/capture_ui_review.py

The script uses Textual's pilot API to render representative screens and
stores SVG screenshots under ``docs/screenshots/<date>-ui-review``.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[1]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from dispatch import impala, manifest
from dispatch.app import DispatchApp
from dispatch.screens.browser import BrowserScreen
from dispatch.screens.help import HelpScreen
from dispatch.screens.history import HistoryScreen
from dispatch.screens.job_detail import JobDetailScreen
from dispatch.screens.new_job import NewJobScreen
from dispatch.screens.preview import PreviewScreen


MOCKS_BIN = WORKSPACE / "mocks" / "bin"
SCR_DIR = WORKSPACE / "scr"
OUT_DIR = WORKSPACE / "docs" / "screenshots" / "2026-05-19-ui-review"


class CaptureContext:
    def __init__(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="dispatch-ui-review-"))
        self.state_dir = self.root / "mock_state"
        self.data_root = self.root / "data"
        self.launch_dir = self.root / "launch"

    def prepare(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.launch_dir.mkdir(parents=True, exist_ok=True)
        OUT_DIR.mkdir(parents=True, exist_ok=True)

        os.environ["PATH"] = str(MOCKS_BIN) + os.pathsep + os.environ.get("PATH", "")
        os.environ["DISPATCH_MOCK_STATE_DIR"] = str(self.state_dir)
        os.environ["DISPATCH_DATA_ROOT"] = str(self.data_root)
        os.environ["DISPATCH_SCR_DIR"] = str(SCR_DIR)
        os.environ["DISPATCH_MOCK_SCENARIO"] = "happy_path"
        os.environ["DISPATCH_MOCK_DELAY"] = "0"
        os.environ["MAILHOST"] = "127.0.0.1:9"

        dispatch_home = self.data_root / ".dispatch"
        dispatch_home.mkdir(parents=True, exist_ok=True)
        (dispatch_home / "config.json").write_text(
            json.dumps({"to_email": "test@example.com"}),
            encoding="utf-8",
        )

        sql_path = self.launch_dir / "query.sql"
        sql_path.write_text(
            "SELECT id, amount\n"
            "FROM payments\n"
            "WHERE ds BETWEEN '2026-05-01' AND '2026-05-31';\n",
            encoding="utf-8",
        )
        self.seed_jobs(sql_path)

    def seed_jobs(self, sql_path: Path) -> None:
        jobs_dir = self.data_root / ".dispatch" / "jobs"
        jobs_dir.mkdir(parents=True, exist_ok=True)

        def seed_job(
            job_id: str,
            state: str,
            *,
            dest_type: str = "Csv",
            table: str,
            finished_at: str | None = None,
            pid: int | None = None,
        ) -> None:
            job_dir = jobs_dir / job_id
            job_dir.mkdir(parents=True, exist_ok=True)
            job: manifest.JobManifest = {
                "schema_version": 1,
                "id": job_id,
                "tool": "dispatch",
                "user": "testuser",
                "source": {"type": "SqlFile", "sql_path_at_launch": str(sql_path)},
                "destination": {
                    "type": dest_type,
                    "schema": "aa_enc",
                    "table_name": table,
                    "csv_path": str(self.launch_dir / f"{table}.csv"),
                },
                "params": {"to_email": "test@example.com"},
                "orchestrator_calls": [
                    {"script": "download_to_csv.py", "argv": ["python3", "x.py"]}
                ],
                "state": state,
                "pid": pid,
                "started_at": "2026-05-19T10:00:00Z",
                "finished_at": finished_at,
                "exit_code": 0 if state == "Succeeded" else (1 if state == "Failed" else None),
            }
            manifest.write(job_dir / "manifest.json", job)
            lines = [
                "[2026-05-19 10:00:00] Starting job",
                "[2026-05-19 10:00:03] Building temp table",
            ]
            if state == "Running":
                lines.append("[2026-05-19 10:00:05] Query still running")
            elif state == "Succeeded":
                lines.append("[2026-05-19 10:10:00] Job finished successfully")
            elif state == "Failed":
                lines.append("[2026-05-19 10:07:00] ERROR memory exceeded")
            (job_dir / "run.log").write_text("\n".join(lines) + "\n", encoding="utf-8")

        seed_job("20260519T100000Z_run001", "Running", table="dispatch_running", pid=4242)
        seed_job(
            "20260519T090000Z_succ01",
            "Succeeded",
            table="dispatch_success",
            finished_at="2026-05-19T09:17:00Z",
        )
        seed_job(
            "20260519T080000Z_fail01",
            "Failed",
            table="dispatch_failed",
            finished_at="2026-05-19T08:12:00Z",
        )
        for index in range(20):
            seed_job(
                f"20260401T10{index:04d}00Z_hist{index:02d}",
                "Succeeded",
                table=f"history_{index}",
                finished_at="2026-04-01T10:05:00Z",
            )


async def capture_dashboard_with_jobs(ctx: CaptureContext) -> None:
    os.chdir(ctx.launch_dir)
    app = DispatchApp()
    async with app.run_test(size=(180, 52)) as pilot:
        await pilot.pause(1.0)
        app.save_screenshot(filename=str(OUT_DIR / "01_dashboard_jobs.svg"))


async def capture_dashboard_empty(ctx: CaptureContext) -> None:
    empty_root = Path(tempfile.mkdtemp(prefix="dispatch-ui-empty-"))
    empty_data = empty_root / "data"
    empty_state = empty_root / "state"
    empty_data.mkdir(parents=True, exist_ok=True)
    empty_state.mkdir(parents=True, exist_ok=True)
    os.environ["DISPATCH_DATA_ROOT"] = str(empty_data)
    os.environ["DISPATCH_MOCK_STATE_DIR"] = str(empty_state)
    empty_home = empty_data / ".dispatch"
    empty_home.mkdir(parents=True, exist_ok=True)
    (empty_home / "config.json").write_text(
        json.dumps({"to_email": "test@example.com"}),
        encoding="utf-8",
    )
    os.chdir(ctx.launch_dir)
    app = DispatchApp()
    async with app.run_test(size=(180, 52)) as pilot:
        await pilot.pause(1.0)
        app.save_screenshot(filename=str(OUT_DIR / "02_dashboard_empty.svg"))
    os.environ["DISPATCH_DATA_ROOT"] = str(ctx.data_root)
    os.environ["DISPATCH_MOCK_STATE_DIR"] = str(ctx.state_dir)


async def capture_new_job(ctx: CaptureContext) -> None:
    os.chdir(ctx.launch_dir)
    app = DispatchApp()
    async with app.run_test(size=(180, 52)) as pilot:
        app.push_screen(NewJobScreen(ctx.launch_dir))
        await pilot.pause(1.0)
        app.save_screenshot(filename=str(OUT_DIR / "03_new_job.svg"))


async def capture_preview() -> None:
    app = DispatchApp()
    body = (
        "CREATE TABLE aa_enc.dispatch_result AS\n"
        "SELECT id, amount\n"
        "FROM payments\n"
        "WHERE ds BETWEEN '2026-05-01' AND '2026-05-31';"
    )
    async with app.run_test(size=(180, 52)) as pilot:
        app.push_screen(
            PreviewScreen(
                "SQL Preview",
                body,
                schema="aa_enc",
                table="dispatch_result",
                source_type="SqlFile",
                dest_type="Table",
            )
        )
        await pilot.pause(0.5)
        app.save_screenshot(filename=str(OUT_DIR / "04_preview.svg"))


async def capture_job_detail() -> None:
    app = DispatchApp()
    async with app.run_test(size=(180, 52)) as pilot:
        app.push_screen(JobDetailScreen("20260519T100000Z_run001"))
        await pilot.pause(0.5)
        app.save_screenshot(filename=str(OUT_DIR / "05_job_detail.svg"))


async def capture_history() -> None:
    app = DispatchApp()
    async with app.run_test(size=(180, 52)) as pilot:
        app.push_screen(HistoryScreen())
        await pilot.pause(0.5)
        app.save_screenshot(filename=str(OUT_DIR / "06_history.svg"))


async def capture_browser_states() -> None:
    async def fake_show_tables(schema: str, pattern: str = "*") -> list[str]:
        return ["dispatch_result", "dispatch_archive"]

    async def fake_describe_table(full_table: str) -> str:
        return (
            "id|string|primary key\n"
            "amount|decimal(18,2)|gross amount\n"
            "ds|string|partition key"
        )

    impala.show_tables = fake_show_tables
    impala.describe_table = fake_describe_table

    app = DispatchApp()
    async with app.run_test(size=(180, 52)) as pilot:
        screen = BrowserScreen()
        app.push_screen(screen)
        await pilot.pause(0.5)
        app.save_screenshot(filename=str(OUT_DIR / "07_browser_initial.svg"))
        await screen.action_show_tables()
        await pilot.pause(0.5)
        app.save_screenshot(filename=str(OUT_DIR / "08_browser_loaded.svg"))
        task = asyncio.create_task(screen.action_drop())
        await pilot.pause(0.5)
        app.save_screenshot(filename=str(OUT_DIR / "09_browser_drop_confirm.svg"))
        app.screen.dismiss(False)
        await task


async def capture_help() -> None:
    app = DispatchApp()
    async with app.run_test(size=(180, 52)) as pilot:
        app.push_screen(HelpScreen())
        await pilot.pause(0.5)
        app.save_screenshot(filename=str(OUT_DIR / "10_help.svg"))


async def main() -> None:
    ctx = CaptureContext()
    ctx.prepare()
    await capture_dashboard_with_jobs(ctx)
    await capture_dashboard_empty(ctx)
    await capture_new_job(ctx)
    await capture_preview()
    await capture_job_detail()
    await capture_history()
    await capture_browser_states()
    await capture_help()
    print(f"Wrote SVG screenshots to {OUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
