"""Tests for UI/UX audit implementation plan (2026-05-30)."""

from __future__ import annotations

from pathlib import Path

import pytest

from dispatch import errors
from dispatch.app import DispatchApp
from dispatch.formatting import format_elapsed, format_job_id
from dispatch.screens.dashboard import DashboardScreen
from dispatch.screens.job_detail import JobDetailScreen
from dispatch.screens.new_job import NewJobScreen


class TestFormatting:
    def test_format_job_id_short(self) -> None:
        job_id = "20260516T100000Z_token123"
        assert format_job_id(job_id).endswith("token123")

    def test_format_elapsed_seconds(self) -> None:
        item = {
            "state": "Succeeded",
            "started_at": "2026-05-16T10:00:00Z",
            "finished_at": "2026-05-16T10:00:30Z",
        }
        assert format_elapsed(item) == "30s"


class TestErrorClassifier:
    def test_classify_syntax_error(self, tmp_path: Path) -> None:
        log = tmp_path / "run.log"
        log.write_text("AnalysisException: Syntax error in line 1\n", encoding="utf-8")
        assert errors.classify(log) == "SYNTAX"

    def test_classify_unknown_returns_none(self, tmp_path: Path) -> None:
        log = tmp_path / "run.log"
        log.write_text("generic failure\n", encoding="utf-8")
        assert errors.classify(log) is None


@pytest.mark.asyncio
class TestNarrowTerminalLayout:
    async def test_dashboard_renders_at_80x24(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("DISPATCH_DATA_ROOT", str(tmp_path))
        dispatch_home = tmp_path / ".dispatch"
        dispatch_home.mkdir(parents=True)
        (dispatch_home / "config.json").write_text("{}", encoding="utf-8")
        (dispatch_home / "installed_version").write_text("1.0.0", encoding="utf-8")

        app = DispatchApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.5)
            assert isinstance(app.screen, DashboardScreen)
            assert list(app.screen.query("#new-job-action-bar")) == []

    async def test_new_job_launch_visible_in_action_bar(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("DISPATCH_DATA_ROOT", str(tmp_path))
        dispatch_home = tmp_path / ".dispatch"
        dispatch_home.mkdir(parents=True)
        (dispatch_home / "config.json").write_text("{}", encoding="utf-8")
        (dispatch_home / "installed_version").write_text("1.0.0", encoding="utf-8")

        app = DispatchApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.3)
            await pilot.press("n")
            await pilot.pause(0.3)
            assert isinstance(app.screen, NewJobScreen)
            app.screen.query_one("#launch")
            app.screen.query_one("#new-job-action-bar")


@pytest.mark.asyncio
class TestJobDetailFollow:
    async def test_follow_toggle_updates_indicator(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("DISPATCH_DATA_ROOT", str(tmp_path))
        from dispatch import manifest as manifest_mod

        jobs_dir = tmp_path / ".dispatch" / "jobs" / "job1"
        jobs_dir.mkdir(parents=True)
        sample = {
            "schema_version": 1,
            "tool": "dispatch",
            "id": "job1",
            "user": "tester",
            "state": "Running",
            "source": {"type": "SqlFile", "sql_path_at_launch": "/tmp/q.sql"},
            "destination": {"type": "Table", "schema": "dw", "table_name": "t"},
            "params": {},
            "pid": 12345,
            "exit_code": None,
            "started_at": "2026-05-16T10:00:00Z",
            "finished_at": None,
            "orchestrator_calls": [{"name": "table", "status": "Running"}],
        }
        manifest_mod.validate(sample)
        (jobs_dir / "manifest.json").write_text(
            __import__("json").dumps(sample),
            encoding="utf-8",
        )
        (jobs_dir / "run.log").write_text("line\n", encoding="utf-8")
        dispatch_home = tmp_path / ".dispatch"
        (dispatch_home / "config.json").write_text("{}", encoding="utf-8")
        (dispatch_home / "installed_version").write_text("1.0.0", encoding="utf-8")

        app = DispatchApp()
        async with app.run_test(size=(120, 40)) as pilot:
            app.push_screen(JobDetailScreen("job1"))
            await pilot.pause(0.5)
            screen = app.screen
            assert isinstance(screen, JobDetailScreen)
            await pilot.pause(1.0)
            await pilot.press("space")
            await pilot.pause(0.5)
            indicator = screen.query_one("#log-streaming")
            rendered = str(indicator.render())
            assert "PAUSED" in rendered or screen.follow_mode is False
