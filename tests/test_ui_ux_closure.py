"""Focused UI/UX closure tests for high-risk screenshot review findings."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone

from textual.widgets import DataTable, Input

from dispatch import manifest
from dispatch.app import DispatchApp
from dispatch.screens.browser import BrowserScreen
from dispatch.screens.history import PAGE_SIZE, HistoryScreen
from dispatch.screens.job_detail import JobDetailScreen
from dispatch.screens.new_job import NewJobScreen
from dispatch.screens.sidebar import NavItem


def _seed_history_job(jobs_dir: Path, index: int) -> str:
    job_id = f"20260401T10{index:04d}00Z_hist{index:02d}"
    job_dir = jobs_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    data: manifest.JobManifest = {
        "schema_version": 1,
        "id": job_id,
        "tool": "dispatch",
        "user": "testuser",
        "source": {"type": "SqlFile", "sql_path_at_launch": f"/tmp/query_{index}.sql"},
        "destination": {
            "type": "Csv",
            "schema": "aa_enc",
            "table_name": f"history_{index}",
            "csv_path": f"/tmp/history_{index}.csv",
        },
        "params": {},
        "orchestrator_calls": [{"script": "download_to_csv.py", "argv": ["python3", "x.py"]}],
        "state": "Succeeded",
        "pid": None,
        "started_at": "2026-04-01T10:00:00Z",
        "finished_at": "2026-04-01T10:05:00Z",
        "exit_code": 0,
    }
    manifest.write(job_dir / "manifest.json", data)
    return job_id


async def _click_sidebar_item(pilot, screen, item_id: str) -> None:
    target = next(widget for widget in screen.query(NavItem) if widget.item_id == item_id)
    await pilot.click(target)


def _seed_recent_job(jobs_dir: Path, suffix: str) -> str:
    job_id = f"20260520T1200{suffix}Z_recent{suffix}"
    job_dir = jobs_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    manifest.write(
        job_dir / "manifest.json",
        {
            "schema_version": 1,
            "id": job_id,
            "tool": "dispatch",
            "user": "testuser",
            "source": {"type": "SqlFile", "sql_path_at_launch": f"/tmp/recent_{suffix}.sql"},
            "destination": {
                "type": "Csv",
                "schema": "aa_enc",
                "table_name": f"recent_{suffix}",
                "csv_path": f"/tmp/recent_{suffix}.csv",
            },
            "params": {},
            "orchestrator_calls": [{"script": "download_to_csv.py", "argv": ["python3", "x.py"]}],
            "state": "Succeeded",
            "pid": None,
            "started_at": "2026-05-20T12:00:00Z",
            "finished_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "exit_code": 0,
        },
    )
    return job_id


def _seed_old_history_job(jobs_dir: Path, suffix: str) -> str:
    finished = datetime.now(timezone.utc) - timedelta(days=10)
    started = finished - timedelta(minutes=5)
    job_id = f"20260401T1000{suffix}Z_old{suffix}"
    job_dir = jobs_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    manifest.write(
        job_dir / "manifest.json",
        {
            "schema_version": 1,
            "id": job_id,
            "tool": "dispatch",
            "user": "testuser",
            "source": {"type": "SqlFile", "sql_path_at_launch": f"/tmp/old_{suffix}.sql"},
            "destination": {
                "type": "Csv",
                "schema": "aa_enc",
                "table_name": f"old_{suffix}",
                "csv_path": f"/tmp/old_{suffix}.csv",
            },
            "params": {},
            "orchestrator_calls": [{"script": "download_to_csv.py", "argv": ["python3", "x.py"]}],
            "state": "Succeeded",
            "pid": None,
            "started_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "finished_at": finished.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "exit_code": 0,
        },
    )
    return job_id


def test_history_pagination_keys_move_between_pages(mock_env_with_config) -> None:
    """History next/previous bindings move the visible page for large histories."""
    data_root = Path(os.environ["DISPATCH_DATA_ROOT"])
    jobs_dir = data_root / ".dispatch" / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    for index in range(PAGE_SIZE + 3):
        _seed_history_job(jobs_dir, index)

    async def run() -> None:
        app = DispatchApp()
        async with app.run_test(size=(120, 40)) as pilot:
            screen = HistoryScreen()
            app.push_screen(screen)
            await pilot.pause()

            page_info = screen.query_one("#page-info")
            page_controls = screen.query_one("#page-controls")
            assert "Showing 1-17 of 20" in str(page_info.render())
            assert "Page 1 of 2" in str(page_controls.render())

            await pilot.press("]")
            await pilot.pause()
            assert "Showing 18-20 of 20" in str(page_info.render())
            assert "Page 2 of 2" in str(page_controls.render())

            await pilot.press("[")
            await pilot.pause()
            assert "Showing 1-17 of 20" in str(page_info.render())
            assert "Page 1 of 2" in str(page_controls.render())

    asyncio.run(run())


def test_history_enter_opens_full_job_id_not_truncated_value(
    mock_env_with_config,
) -> None:
    """Enter on a history row opens the full durable row key, not the visible ID."""
    data_root = Path(os.environ["DISPATCH_DATA_ROOT"])
    jobs_dir = data_root / ".dispatch" / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    job_id = _seed_history_job(jobs_dir, 12345)
    assert len(job_id) > 24

    async def run() -> None:
        app = DispatchApp()
        async with app.run_test(size=(120, 40)) as pilot:
            screen = HistoryScreen()
            app.push_screen(screen)
            await pilot.pause()

            screen.action_view_logs()
            await pilot.pause()
            assert isinstance(app.screen, JobDetailScreen)
            assert app.screen.job_id == job_id

    asyncio.run(run())


def test_sidebar_click_navigation_switches_screens_from_nested_state(
    mock_env_with_config, tmp_path
) -> None:
    """Sidebar clicks navigate reliably from nested screens and keep a flat stack."""
    (tmp_path / "query.sql").write_text("select 1\n", encoding="utf-8")

    async def run() -> None:
        app = DispatchApp()
        async with app.run_test(size=(120, 40)) as pilot:
            app.push_screen(NewJobScreen(tmp_path))
            await pilot.pause()

            await _click_sidebar_item(pilot, app.screen, "history")
            await pilot.pause()
            assert isinstance(app.screen, HistoryScreen)
            assert [type(screen).__name__ for screen in app.screen_stack] == [
                "Screen",
                "DashboardScreen",
                "HistoryScreen",
            ]

            await _click_sidebar_item(pilot, app.screen, "browse")
            await pilot.pause()
            assert isinstance(app.screen, BrowserScreen)
            assert [type(screen).__name__ for screen in app.screen_stack] == [
                "Screen",
                "DashboardScreen",
                "BrowserScreen",
            ]

    asyncio.run(run())


def test_sidebar_view_logs_from_history_uses_selected_job(
    mock_env_with_config,
) -> None:
    """Sidebar View Logs opens the selected History job on a flat stack."""
    data_root = Path(os.environ["DISPATCH_DATA_ROOT"])
    jobs_dir = data_root / ".dispatch" / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    job_id = _seed_history_job(jobs_dir, 99)

    async def run() -> None:
        app = DispatchApp()
        async with app.run_test(size=(120, 40)) as pilot:
            app.push_screen(HistoryScreen())
            await pilot.pause()

            await _click_sidebar_item(pilot, app.screen, "view_logs")
            await pilot.pause()
            assert isinstance(app.screen, JobDetailScreen)
            assert app.screen.job_id == job_id
            assert [type(screen).__name__ for screen in app.screen_stack] == [
                "Screen",
                "DashboardScreen",
                "JobDetailScreen",
            ]

    asyncio.run(run())


def test_dashboard_top_level_actions_open_expected_screens(
    mock_env_with_config, tmp_path
) -> None:
    """Dashboard keyboard actions should still open the same top-level screens."""
    (tmp_path / "query.sql").write_text("select 1\n", encoding="utf-8")

    async def run() -> None:
        app = DispatchApp()
        app.launch_cwd = tmp_path
        async with app.run_test(size=(120, 40)) as pilot:
            dashboard = app.screen
            dashboard.action_new_job()
            await pilot.pause()
            assert isinstance(app.screen, NewJobScreen)
            assert [type(screen).__name__ for screen in app.screen_stack] == [
                "Screen",
                "DashboardScreen",
                "NewJobScreen",
            ]

            app.pop_screen()
            await pilot.pause()
            dashboard.action_history()
            await pilot.pause()
            assert isinstance(app.screen, HistoryScreen)
            assert [type(screen).__name__ for screen in app.screen_stack] == [
                "Screen",
                "DashboardScreen",
                "HistoryScreen",
            ]

            app.pop_screen()
            await pilot.pause()
            dashboard.action_browser()
            await pilot.pause()
            assert isinstance(app.screen, BrowserScreen)
            assert [type(screen).__name__ for screen in app.screen_stack] == [
                "Screen",
                "DashboardScreen",
                "BrowserScreen",
            ]

    asyncio.run(run())


def test_dashboard_jobs_table_takes_focus_and_arrow_selection_works(
    mock_env_with_config,
) -> None:
    """Arrow navigation and view logs should target the unified jobs table."""
    data_root = Path(os.environ["DISPATCH_DATA_ROOT"])
    jobs_dir = data_root / ".dispatch" / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    newer_job = _seed_recent_job(jobs_dir, "1")
    older_job = _seed_recent_job(jobs_dir, "0")

    async def run() -> None:
        app = DispatchApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            screen = app.screen
            jobs_table = screen.query_one("#jobs-table", DataTable)

            assert jobs_table.has_focus is True

            await pilot.press("down")
            await pilot.pause()
            screen.action_view_logs()
            await pilot.pause()

            assert isinstance(app.screen, JobDetailScreen)
            assert app.screen.job_id == older_job
            assert app.screen.job_id != newer_job

    asyncio.run(run())


def test_history_refresh_rereads_manifests_while_screen_is_mounted(
    mock_env_with_config,
) -> None:
    """Refreshing History should pick up jobs written after the screen mounted."""
    data_root = Path(os.environ["DISPATCH_DATA_ROOT"])
    jobs_dir = data_root / ".dispatch" / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    _seed_old_history_job(jobs_dir, "0")

    async def run() -> None:
        app = DispatchApp()
        async with app.run_test(size=(120, 40)) as pilot:
            screen = HistoryScreen()
            app.push_screen(screen)
            await pilot.pause()

            page_info = screen.query_one("#page-info")
            assert "of 1" in str(page_info.render())

            _seed_old_history_job(jobs_dir, "1")
            screen.refresh_history()
            await pilot.pause()

            assert "of 2" in str(page_info.render())

    asyncio.run(run())


def test_history_empty_state_focuses_search_for_keyboard_use(
    mock_env_with_config,
) -> None:
    """Empty History should move focus to the visible search box."""

    async def run() -> None:
        app = DispatchApp()
        async with app.run_test(size=(120, 40)) as pilot:
            screen = HistoryScreen()
            app.push_screen(screen)
            await pilot.pause()

            search = screen.query_one("#search", Input)
            table = screen.query_one("#history-table", DataTable)

            assert table.display is False
            assert search.has_focus is True

            await pilot.press("x")
            await pilot.pause()
            assert search.value == "x"

    asyncio.run(run())


def test_browser_placeholder_and_auto_describe_after_show_tables(
    mock_env_with_config, monkeypatch
) -> None:
    """Browser explains the empty detail pane and fills it after loading tables."""

    async def fake_show_tables(schema: str, pattern: str = "*") -> list[str]:
        return ["dispatch_result", "dispatch_archive"]

    async def fake_describe_table(full_table: str) -> str:
        return "name|type|comment\nid|string|primary key"

    monkeypatch.setattr("dispatch.impala.show_tables", fake_show_tables)
    monkeypatch.setattr("dispatch.impala.describe_table", fake_describe_table)

    async def run() -> None:
        app = DispatchApp()
        async with app.run_test(size=(120, 40)) as pilot:
            screen = BrowserScreen()
            app.push_screen(screen)
            await pilot.pause(0.5)

            assert "aa_enc.dispatch_result" in str(
                screen.query_one("#file-preview-title").render()
            )
            # The data is now in the DataTable, not the Static body
            describe_table = screen.query_one("#describe-table", DataTable)
            assert describe_table.display is True
            # Check for column name in any row
            all_row_data = [describe_table.get_row_at(i) for i in range(describe_table.row_count)]
            assert any("id" in row for row in all_row_data)

    asyncio.run(run())


def test_browser_show_tables_failure_replaces_stale_schema_with_error(
    mock_env_with_config, monkeypatch
) -> None:
    """SHOW TABLES reruns should hide stale schema content when they fail."""
    show_tables_calls = 0

    async def fake_show_tables(schema: str, pattern: str = "*") -> list[str]:
        nonlocal show_tables_calls
        show_tables_calls += 1
        if show_tables_calls <= 1:
            return ["dispatch_result"]
        raise RuntimeError("metadata backend offline")

    async def fake_describe_table(full_table: str) -> str:
        return "name|type|comment\nid|string|primary key"

    monkeypatch.setattr("dispatch.impala.show_tables", fake_show_tables)
    monkeypatch.setattr("dispatch.impala.describe_table", fake_describe_table)

    async def run() -> None:
        app = DispatchApp()
        async with app.run_test(size=(120, 40)) as pilot:
            screen = BrowserScreen()
            app.push_screen(screen)
            await pilot.pause(0.5)
            assert screen.query_one("#describe-table", DataTable).display is True

            await screen.action_show_tables()
            await pilot.pause(0.5)

            describe_table = screen.query_one("#describe-table", DataTable)
            describe_body = screen.query_one("#describe-body")
            assert describe_table.display is False
            assert describe_body.display is True
            assert "metadata backend offline" in str(describe_body.render())

    asyncio.run(run())


def test_browser_drop_requires_typing_full_table_name(
    mock_env_with_config, monkeypatch
) -> None:
    """DROP confirmation requires the fully-qualified table name, not just Y."""
    calls: list[str] = []

    async def fake_drop_table(full_table: str) -> str:
        calls.append(full_table)
        return f"Dropped {full_table}"

    monkeypatch.setattr("dispatch.impala.drop_table", fake_drop_table)

    async def run() -> None:
        app = DispatchApp()
        async with app.run_test(size=(120, 40)) as pilot:
            screen = BrowserScreen(auto_load=False)
            app.push_screen(screen)
            await pilot.pause()
            table = screen.query_one("#browser-table")
            table.add_row("danger_table", "table")
            table.cursor_coordinate = (0, 0)

            worker = screen.action_drop()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert calls == []
            assert worker.is_running

            confirm_input = app.screen.query_one("#confirm-input", Input)
            confirm_input.value = "aa_enc.danger_table"
            await pilot.press("enter")
            await worker.wait()
            assert calls == ["aa_enc.danger_table"]

    asyncio.run(run())


def test_typed_drop_confirmation_button_does_not_bypass_input(
    mock_env_with_config, monkeypatch
) -> None:
    """Clicking the danger button still requires the exact typed table name."""
    calls: list[str] = []

    async def fake_drop_table(full_table: str) -> str:
        calls.append(full_table)
        return f"Dropped {full_table}"

    monkeypatch.setattr("dispatch.impala.drop_table", fake_drop_table)

    async def run() -> None:
        app = DispatchApp()
        async with app.run_test(size=(120, 40)) as pilot:
            screen = BrowserScreen(auto_load=False)
            app.push_screen(screen)
            await pilot.pause()
            table = screen.query_one("#browser-table")
            table.add_row("danger_table", "table")
            table.cursor_coordinate = (0, 0)

            worker = screen.action_drop()
            await pilot.pause()
            app.screen.query_one("#confirm-yes").press()
            await pilot.pause()
            assert calls == []
            assert worker.is_running

            app.screen.query_one("#confirm-input", Input).value = "aa_enc.danger_table"
            app.screen.query_one("#confirm-yes").press()
            await worker.wait()
            assert calls == ["aa_enc.danger_table"]

    asyncio.run(run())


def test_sidebar_view_logs_from_job_detail_is_a_noop(
    mock_env_with_config,
) -> None:
    """Clicking the active View Logs nav item should not warn or navigate."""
    data_root = Path(os.environ["DISPATCH_DATA_ROOT"])
    jobs_dir = data_root / ".dispatch" / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    job_id = _seed_history_job(jobs_dir, 88)

    async def run() -> None:
        notifications: list[tuple[str, dict]] = []

        def fake_notify(message: str, **kwargs) -> None:
            notifications.append((message, kwargs))

        app = DispatchApp()
        app.notify = fake_notify  # type: ignore[method-assign]

        async with app.run_test(size=(120, 40)) as pilot:
            app.push_screen(JobDetailScreen(job_id))
            await pilot.pause()
            notifications.clear()

            expected_stack = [type(screen).__name__ for screen in app.screen_stack]
            await _click_sidebar_item(pilot, app.screen, "view_logs")
            await pilot.pause()

            assert isinstance(app.screen, JobDetailScreen)
            assert app.screen.job_id == job_id
            assert [type(screen).__name__ for screen in app.screen_stack] == expected_stack
            assert notifications == []

    asyncio.run(run())


def test_browser_drop_replaces_schema_table_with_persistent_result_message(
    mock_env_with_config, monkeypatch
) -> None:
    """DROP feedback should be visible in the detail pane after describing a table."""
    calls: list[str] = []

    async def fake_describe_table(full_table: str) -> str:
        return "name|type|comment\nid|string|primary key"

    async def fake_drop_table(full_table: str) -> str:
        calls.append(full_table)
        return f"Dropped {full_table}"

    monkeypatch.setattr("dispatch.impala.describe_table", fake_describe_table)
    monkeypatch.setattr("dispatch.impala.drop_table", fake_drop_table)

    async def run() -> None:
        app = DispatchApp()
        async with app.run_test(size=(120, 40)) as pilot:
            screen = BrowserScreen(auto_load=False)
            app.push_screen(screen)
            await pilot.pause()
            table = screen.query_one("#browser-table", DataTable)
            table.add_row("danger_table", "table")
            table.cursor_coordinate = (0, 0)

            await screen.action_describe()
            await pilot.pause()
            assert screen.query_one("#describe-table", DataTable).display is True

            worker = screen.action_drop()
            await pilot.pause()
            confirm_input = app.screen.query_one("#confirm-input", Input)
            confirm_input.value = "aa_enc.danger_table"
            await pilot.press("enter")
            await worker.wait()
            await pilot.pause()

            describe_table = screen.query_one("#describe-table", DataTable)
            describe_body = screen.query_one("#describe-body")
            assert describe_table.display is False
            assert describe_body.display is True
            assert "Dropped aa_enc.danger_table" in str(describe_body.render())
            assert calls == ["aa_enc.danger_table"]

    asyncio.run(run())
