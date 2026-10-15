"""TUI session/surface/cancel telemetry integration tests."""

from __future__ import annotations

import ast
import asyncio
import logging
from pathlib import Path
from typing import Any, List, Tuple
from unittest.mock import MagicMock

import pytest
from tui.form_widgets import ModeSwitch

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
        lambda action, prompt: calls.append(("cancelled", (action, prompt))),
    )
    monkeypatch.setattr(
        tui_app,
        "launch_blocked",
        lambda action, reason: calls.append(("blocked", (action, reason))),
    )
    monkeypatch.setattr(
        tui_app,
        "dataset_load",
        lambda outcome: calls.append(("dataset", (outcome,))),
    )
    monkeypatch.setattr(
        tui_app,
        "advanced_override",
        lambda outcome: calls.append(("advanced", (outcome,))),
    )
    monkeypatch.setattr(
        tui_app,
        "session_restored",
        lambda: calls.append(("restored", ())),
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

            # PR 5: the Share/Rate switch on step 3 (one control, ←/→).
            await app.ensure_step("analysis")
            switch = app.query_one("#mode_switch", ModeSwitch)
            switch.mode = "rate"
            await pilot.pause()
            switch.mode = "rate"
            await pilot.pause()
            switch.mode = "share"
            await pilot.pause()
            switch.mode = "share"
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
    assert ("cancelled", ("rate_analysis", "validation_review")) in calls
    assert not any(c[0] == "blocked" for c in calls)
    app._reset_run_ui.assert_called_once()


@pytest.mark.parametrize(
    ("result", "has_errors", "should_abort"),
    [
        (False, True, False),  # Proceed disabled: Cancel is a forced exit
        (False, False, True),
        (False, True, True),
        (True, False, True),  # Proceed pressed but validation aborts
    ],
)
def test_validation_modal_forced_exit_is_launch_block_not_cancel(
    monkeypatch: pytest.MonkeyPatch,
    result: bool,
    has_errors: bool,
    should_abort: bool,
) -> None:
    calls: List[Tuple[str, tuple]] = []
    _patch_tui_helpers(monkeypatch, calls)
    app = BenchmarkApp()
    app._reset_run_ui = MagicMock()  # type: ignore[method-assign]
    app.run_analysis = MagicMock()  # type: ignore[method-assign]
    app._handle_validation_modal_result(
        result,
        has_errors=has_errors,
        should_abort=should_abort,
        request=AnalysisRunRequest(mode="share", metric="txn_cnt"),
        saved_df=None,
        log_widget=MagicMock(),
    )
    assert calls == [("blocked", ("share_analysis", "validation_errors"))]
    app.run_analysis.assert_not_called()


def test_validation_modal_none_result_records_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: List[Tuple[str, tuple]] = []
    _patch_tui_helpers(monkeypatch, calls)
    app = BenchmarkApp()
    app._reset_run_ui = MagicMock()  # type: ignore[method-assign]
    app._handle_validation_modal_result(
        None,
        has_errors=True,
        should_abort=True,
        request=AnalysisRunRequest(mode="share", metric="txn_cnt"),
        saved_df=None,
        log_widget=MagicMock(),
    )
    assert calls == []


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


@pytest.mark.parametrize(
    ("run_state", "prompt"),
    [("running", "quit_during_run"), ("validating", "quit_before_run")],
)
def test_csv_picker_cancel_and_quit_confirm_cancel_semantics(
    monkeypatch: pytest.MonkeyPatch,
    run_state: str,
    prompt: str,
) -> None:
    """Picker cancel and declined quit emit nothing; a confirmed quit names
    the abandoned intent (G15) with the stage it was in."""
    calls: List[Tuple[str, tuple]] = []
    _patch_tui_helpers(monkeypatch, calls)

    app = BenchmarkApp()
    app._run_state = "idle"  # PR 5: the picker is not offered while a run locks the form
    app._run_mode = "rate"
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
    assert calls == []

    captured.clear()
    app._run_state = run_state
    app.action_open_file()  # locked while a run is active: nothing opens
    assert captured == []
    app.action_quit()
    assert len(captured) == 1
    on_confirm = captured[0][1]
    assert callable(on_confirm)
    on_confirm(False)
    on_confirm(None)
    assert calls == []
    on_confirm(True)
    app._save_session.assert_called_once()
    app.exit.assert_called_once()

    assert calls == [("cancelled", ("rate_analysis", prompt))]


def test_fail_launch_records_only_the_closed_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: List[Tuple[str, tuple]] = []
    _patch_tui_helpers(monkeypatch, calls)
    app = BenchmarkApp()
    app._run_mode = "share"
    app.query_one = MagicMock()  # type: ignore[method-assign]
    app.call_from_thread = lambda fn, *a, **k: None  # type: ignore[method-assign]
    monkeypatch.setattr(tui_app, "write_log_message", lambda *_a, **_k: None)
    monkeypatch.setattr(tui_app, "finalize_deferred_logging", lambda *_a, **_k: None)

    app._fail_launch("Primary metric txn_cnt is required.", block_reason="metric_missing")
    app._fail_launch("accuracy_first run cancelled: operator consent was not given.")
    assert calls == [("blocked", ("share_analysis", "metric_missing"))]


def test_dataset_load_dedupes_and_never_passes_the_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: List[Tuple[str, tuple]] = []
    _patch_tui_helpers(monkeypatch, calls)
    app = BenchmarkApp()
    app._emit_dataset_load("loaded", "/data/acme_peers.csv")
    app._emit_dataset_load("loaded", "/data/acme_peers.csv")
    app._emit_dataset_load("not_found", "/data/typo.csv")
    app._emit_dataset_load("loaded", "/data/acme_peers.csv")
    assert calls == [
        ("dataset", ("loaded",)),
        ("dataset", ("not_found",)),
        ("dataset", ("loaded",)),
    ]


def test_mount_with_saved_session_emits_session_restored(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: List[Tuple[str, tuple]] = []
    _patch_tui_helpers(monkeypatch, calls)
    (tmp_path / "session.yaml").write_text("validate_input: false\n", encoding="utf-8")

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            await pilot.pause()

    asyncio.run(scenario())
    names = [c[0] for c in calls]
    assert names.index("start") < names.index("restored")
    assert names.count("restored") == 1


def test_mount_without_saved_session_emits_no_restore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: List[Tuple[str, tuple]] = []
    _patch_tui_helpers(monkeypatch, calls)

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            await pilot.pause()

    asyncio.run(scenario())
    assert not any(c[0] == "restored" for c in calls)


def test_help_and_advanced_panel_emit_surfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: List[Tuple[str, tuple]] = []
    _patch_tui_helpers(monkeypatch, calls)

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            pilot.app.action_toggle_advanced()  # PR 5: opens Expert settings
            await pilot.pause()
            pilot.app.action_toggle_advanced()  # closing emits nothing
            await pilot.pause()
            pilot.app.action_show_help()
            await pilot.pause()

    asyncio.run(scenario())
    surfaces = [c[1][0] for c in calls if c[0] == "surface"]
    assert surfaces.count("advanced") == 1
    assert surfaces.count("preset_help") == 1


def test_advanced_overrides_emit_closed_outcomes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: List[Tuple[str, tuple]] = []
    _patch_tui_helpers(monkeypatch, calls)
    app = BenchmarkApp()
    app.notify = MagicMock()  # type: ignore[method-assign]
    # Export with nothing to export: "empty".
    app._collect_advanced_override_data = MagicMock(return_value={})  # type: ignore[method-assign]
    assert app.export_advanced_overrides() is None
    # PR 5: expert changes are written at run time; a write failure is
    # "failed" and stops the launch (the caller reports it).
    app.form.expert = {"adv_bounds_max_weight": "0.3"}
    app.preset_workflow = MagicMock()
    app.preset_workflow.load_preset_data.return_value = {"compliance_posture": "strict"}
    app.preset_workflow.write_override_file.side_effect = OSError("/secret/dir is read-only")
    with pytest.raises(OSError):
        app._write_expert_override()
    app.preset_workflow.write_override_file.side_effect = None
    app.preset_workflow.write_override_file.return_value = "adv_override_x.yaml"
    assert app._write_expert_override() == "adv_override_x.yaml"
    assert calls == [("advanced", ("empty",)), ("advanced", ("failed",)), ("advanced", ("applied",))]


def test_telemetry_service_failure_does_not_crash_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The helpers' never-raise guarantee must protect the TUI lifecycle."""

    def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("tui telemetry boom")

    monkeypatch.setattr("core.telemetry._get_service", boom)

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            pilot.app.form.mode = "rate"
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
