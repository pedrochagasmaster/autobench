"""TUI session/surface/cancel telemetry integration tests."""

from __future__ import annotations

import asyncio
from typing import Any, List, Optional, Tuple
from unittest.mock import MagicMock

import pytest

import core.telemetry as telemetry
import tui_app
from core.contracts import AnalysisRunRequest
from tui_app import BenchmarkApp, LogHandler


@pytest.fixture(autouse=True)
def _reset_telemetry(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    telemetry._reset_for_tests()
    monkeypatch.setattr(tui_app, "SESSION_FILE", tmp_path / "session.yaml")
    yield
    telemetry._reset_for_tests()
    root = __import__("logging").getLogger()
    for handler in list(root.handlers):
        if isinstance(handler, LogHandler):
            root.removeHandler(handler)


def _patch_tui_helpers(
    monkeypatch: pytest.MonkeyPatch,
    calls: List[Tuple[str, tuple]],
) -> None:
    monkeypatch.setattr(
        tui_app,
        "start_session",
        lambda ctx: calls.append(("start", (ctx,))),
    )
    monkeypatch.setattr(
        tui_app,
        "end_session",
        lambda: calls.append(("end", ())),
    )
    monkeypatch.setattr(
        tui_app,
        "surface_viewed",
        lambda surface: calls.append(("surface", (surface,))),
    )
    monkeypatch.setattr(
        tui_app,
        "action_cancelled",
        lambda action: calls.append(("cancelled", (action,))),
    )


def test_mount_starts_tui_session_and_initial_share_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: List[Tuple[str, tuple]] = []
    _patch_tui_helpers(monkeypatch, calls)

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert ("start", ("tui",)) in calls
            assert ("surface", ("share",)) in calls
            # Exactly one initial share from mount/dedupe.
            assert calls.count(("surface", ("share",))) == 1

    asyncio.run(scenario())


def test_tab_switch_rate_and_share_deduped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: List[Tuple[str, tuple]] = []
    _patch_tui_helpers(monkeypatch, calls)

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            app = pilot.app
            await pilot.pause()
            from textual.widgets import TabbedContent

            tabs = app.query_one(TabbedContent)
            tabs.active = "rate_tab"
            await pilot.pause()
            tabs.active = "rate_tab"
            await pilot.pause()
            tabs.active = "share_tab"
            await pilot.pause()
            tabs.active = "share_tab"
            await pilot.pause()

            surfaces = [c for c in calls if c[0] == "surface"]
            assert surfaces == [
                ("surface", ("share",)),
                ("surface", ("rate",)),
                ("surface", ("share",)),
            ]

    asyncio.run(scenario())


def test_unmount_ends_session_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: List[Tuple[str, tuple]] = []
    _patch_tui_helpers(monkeypatch, calls)

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            await pilot.pause()
        ends = [c for c in calls if c[0] == "end"]
        assert len(ends) == 1

    asyncio.run(scenario())


def test_validation_modal_false_emits_cancel_for_request_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: List[Tuple[str, tuple]] = []
    _patch_tui_helpers(monkeypatch, calls)
    app = BenchmarkApp()
    app._reset_run_ui = MagicMock()  # type: ignore[method-assign]
    request = AnalysisRunRequest(mode="rate", metric=None, total_col="total", approved_col="a")
    log = MagicMock()
    app._handle_validation_modal_result(
        False,
        has_errors=False,
        should_abort=False,
        request=request,
        saved_df=None,
        log_widget=log,
    )
    assert ("cancelled", ("rate_analysis",)) in calls
    app._reset_run_ui.assert_called_once()


def test_validation_modal_true_or_errors_do_not_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: List[Tuple[str, tuple]] = []
    _patch_tui_helpers(monkeypatch, calls)
    app = BenchmarkApp()
    request = AnalysisRunRequest(mode="share", metric="txn_cnt")
    log = MagicMock()
    app._reset_run_ui = MagicMock()  # type: ignore[method-assign]
    app.run_analysis = MagicMock()  # type: ignore[method-assign]

    app._handle_validation_modal_result(
        True,
        has_errors=False,
        should_abort=False,
        request=request,
        saved_df=None,
        log_widget=log,
    )
    app._handle_validation_modal_result(
        True,
        has_errors=True,
        should_abort=False,
        request=request,
        saved_df=None,
        log_widget=log,
    )
    assert not any(c[0] == "cancelled" for c in calls)


def test_csv_picker_cancel_and_quit_confirm_emit_no_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: List[Tuple[str, tuple]] = []
    _patch_tui_helpers(monkeypatch, calls)

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            app = pilot.app
            await pilot.pause()
            before = list(calls)
            # CSV picker cancel path: callback with None/empty must not cancel analysis.
            app.push_screen = MagicMock()  # type: ignore[method-assign]
            # Simulate picker on_picked(None) body used by action_open_file.
            path: Optional[str] = None
            if path:
                raise AssertionError("unreachable")
            # Quit confirmation decline path does not call action_cancelled.
            def on_confirm(confirmed: Optional[bool]) -> None:
                if confirmed:
                    app.exit()

            on_confirm(False)
            on_confirm(None)
            assert calls == before

    asyncio.run(scenario())


def test_helper_failure_does_not_crash_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("tui telemetry boom")

    monkeypatch.setattr(tui_app, "start_session", boom)
    monkeypatch.setattr(tui_app, "end_session", boom)
    monkeypatch.setattr(tui_app, "surface_viewed", boom)
    monkeypatch.setattr(tui_app, "action_cancelled", boom)

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            from textual.widgets import TabbedContent

            pilot.app.query_one(TabbedContent).active = "rate_tab"
            await pilot.pause()

    asyncio.run(scenario())
