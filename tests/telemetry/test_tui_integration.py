"""TUI session/surface/cancel telemetry integration tests."""

from __future__ import annotations

import ast
import asyncio
import logging
from pathlib import Path
from typing import Any, List, Optional, Tuple
from unittest.mock import MagicMock

import pytest
from textual.widgets import TabbedContent

import core.analysis_run as analysis_run
import core.telemetry as telemetry
import tui_app
from core.analysis_run import RunAborted, RunBlocked
from core.contracts import AnalysisRunRequest
from tui_app import BenchmarkApp, LogHandler

_ORCHESTRATION_ACTIONS = frozenset(
    {
        "action_attempted",
        "action_completed",
        "action_refused",
        "action_failed",
    }
)


@pytest.fixture(autouse=True)
def _reset_telemetry(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    telemetry._reset_for_tests()
    monkeypatch.setattr(tui_app, "SESSION_FILE", tmp_path / "session.yaml")
    yield
    telemetry._reset_for_tests()
    root = logging.getLogger()
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
    """Real action_open_file / action_quit callbacks must not emit action_cancelled."""
    calls: List[Tuple[str, tuple]] = []
    _patch_tui_helpers(monkeypatch, calls)

    app = BenchmarkApp()
    app._run_state = "running"
    app._save_session = MagicMock()  # type: ignore[method-assign]
    app.exit = MagicMock()  # type: ignore[method-assign]
    app.load_csv_headers = MagicMock()  # type: ignore[method-assign]
    app._quick_pick_files = MagicMock(return_value=[])  # type: ignore[method-assign]

    captured: list[tuple[Any, Any]] = []

    def capture_push_screen(screen: Any, callback: Any = None) -> None:
        captured.append((screen, callback))

    app.push_screen = capture_push_screen  # type: ignore[method-assign]

    app.action_open_file()
    assert len(captured) == 1
    on_picked = captured[0][1]
    assert callable(on_picked)
    on_picked(None)
    on_picked("")

    captured.clear()
    app.action_quit()
    assert len(captured) == 1
    on_confirm = captured[0][1]
    assert callable(on_confirm)
    on_confirm(False)
    on_confirm(None)
    on_confirm(True)
    app._save_session.assert_called_once()
    app.exit.assert_called_once()

    assert not any(c[0] == "cancelled" for c in calls)
    assert not any(name == "action_cancelled" for name, _args in calls)


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
            pilot.app.query_one(TabbedContent).active = "rate_tab"
            await pilot.pause()

    asyncio.run(scenario())


def _tui_imported_telemetry_names() -> set[str]:
    tree = ast.parse(Path(tui_app.__file__).read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if not node.module or "telemetry" not in node.module:
            continue
        for alias in node.names:
            names.add(alias.asname or alias.name)
    return names


def _tui_name_loads() -> set[str]:
    tree = ast.parse(Path(tui_app.__file__).read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            names.add(node.id)
    return names


def test_tui_does_not_import_or_call_orchestration_action_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shared `_execute_run` owns attempt/refuse/fail/complete; TUI must not duplicate."""
    imported = _tui_imported_telemetry_names()
    assert _ORCHESTRATION_ACTIONS.isdisjoint(imported)
    loaded = _tui_name_loads()
    assert _ORCHESTRATION_ACTIONS.isdisjoint(loaded)
    for name in _ORCHESTRATION_ACTIONS:
        assert not hasattr(tui_app, name)

    tui_layer_calls: list[str] = []
    for name in _ORCHESTRATION_ACTIONS:
        monkeypatch.setattr(
            tui_app,
            name,
            lambda *a, _n=name, **k: tui_layer_calls.append(_n),
            raising=False,
        )

    shared_calls: list[tuple[str, tuple]] = []

    def track(label: str):
        def _fn(*args: Any) -> None:
            shared_calls.append((label, args))

        return _fn

    monkeypatch.setattr(analysis_run, "action_attempted", track("attempted"))
    monkeypatch.setattr(analysis_run, "action_completed", track("completed"))
    monkeypatch.setattr(analysis_run, "action_refused", track("refused"))
    monkeypatch.setattr(analysis_run, "action_failed", track("failed"))

    session_calls: List[Tuple[str, tuple]] = []
    _patch_tui_helpers(monkeypatch, session_calls)

    app = BenchmarkApp()
    app.call_from_thread = lambda fn, *a, **k: fn(*a, **k)  # type: ignore[method-assign]
    app._begin_run_ui = MagicMock()  # type: ignore[method-assign]
    app._end_run_ui = MagicMock()  # type: ignore[method-assign]
    app.notify = MagicMock()  # type: ignore[method-assign]
    log = MagicMock()
    request = AnalysisRunRequest(mode="share", metric="txn_cnt", output="out.xlsx")

    ok = MagicMock()
    ok.compliance_summary = {
        "compliance_verdict": "fully_compliant",
        "posture": "strict",
        "acknowledgement_state": "not_required",
    }
    ok.metadata = {}
    ok.report_paths = ["out.xlsx"]
    ok.analysis_output_file = "out.xlsx"

    app._execute_run_for_tui = MagicMock(return_value=ok)  # type: ignore[method-assign]
    app._execute_confirmed_analysis(request, None, log)

    app._execute_run_for_tui = MagicMock(  # type: ignore[method-assign]
        side_effect=RunBlocked("blocked", {"compliance_verdict": "blocked"})
    )
    app._execute_confirmed_analysis(request, None, log)

    app._execute_run_for_tui = MagicMock(side_effect=RunAborted("aborted"))  # type: ignore[method-assign]
    app._execute_confirmed_analysis(request, None, log)

    app._execute_run_for_tui = MagicMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]
    app._execute_confirmed_analysis(request, None, log)

    assert tui_layer_calls == []
    # TUI stubbed the shared wrapper, so orchestration helpers stay uncalled here;
    # ownership remains on analysis_run when the real wrapper runs.
    assert shared_calls == []
    assert not any(c[0] == "cancelled" for c in session_calls)

    # Shared-wrapper integration: real `_execute_run_for_tui` delegates to execute_run.
    shared_attempted: list[str] = []
    monkeypatch.setattr(
        analysis_run,
        "action_attempted",
        lambda action: shared_attempted.append(action),
    )
    monkeypatch.setattr(
        analysis_run,
        "action_completed",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        analysis_run,
        "action_refused",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        analysis_run,
        "action_failed",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        analysis_run,
        "_execute_run_impl",
        lambda *_a, **_k: (_ for _ in ()).throw(RunAborted("from-shared")),
    )
    app._execute_run_for_tui = BenchmarkApp._execute_run_for_tui.__get__(app, BenchmarkApp)
    app._execute_confirmed_analysis(request, None, log)
    assert shared_attempted == ["share_analysis"]
    assert tui_layer_calls == []
    app._end_run_ui.assert_called()
