"""CLI session telemetry boundary tests for share/rate entry points."""

from __future__ import annotations

from typing import Any, List, Tuple
from unittest.mock import MagicMock

import pytest

import benchmark
import core.telemetry as telemetry


@pytest.fixture(autouse=True)
def _reset_telemetry() -> None:
    telemetry._reset_for_tests()
    yield
    telemetry._reset_for_tests()


def _patch_session_helpers(
    monkeypatch: pytest.MonkeyPatch,
    calls: List[Tuple[str, tuple]],
) -> None:
    monkeypatch.setattr(
        benchmark,
        "start_session",
        lambda ctx: calls.append(("start", (ctx,))),
    )
    monkeypatch.setattr(
        benchmark,
        "end_session",
        lambda: calls.append(("end", ())),
    )


def _run_main(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> int:
    monkeypatch.setattr("sys.argv", ["benchmark.py", *argv])
    return benchmark.main()


def test_share_starts_cli_share_session_and_ends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: List[Tuple[str, tuple]] = []
    _patch_session_helpers(monkeypatch, calls)
    monkeypatch.setattr(benchmark, "setup_logging", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr(benchmark, "run_share_analysis", lambda *_a, **_k: 0)
    monkeypatch.setattr(benchmark, "_validate_preset_arg", lambda _args: None)

    code = _run_main(
        monkeypatch,
        ["share", "--csv", "x.csv", "--entity", "E", "--metric", "m"],
    )
    assert code == 0
    assert calls == [("start", ("cli_share",)), ("end", ())]


def test_rate_starts_cli_rate_session_and_ends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: List[Tuple[str, tuple]] = []
    _patch_session_helpers(monkeypatch, calls)
    monkeypatch.setattr(benchmark, "setup_logging", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr(benchmark, "run_rate_analysis", lambda *_a, **_k: 0)
    monkeypatch.setattr(benchmark, "_validate_preset_arg", lambda _args: None)

    code = _run_main(
        monkeypatch,
        [
            "rate",
            "--csv",
            "x.csv",
            "--entity",
            "E",
            "--total-col",
            "t",
            "--approved-col",
            "a",
        ],
    )
    assert code == 0
    assert calls == [("start", ("cli_rate",)), ("end", ())]


def test_end_session_runs_even_when_handler_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: List[Tuple[str, tuple]] = []
    _patch_session_helpers(monkeypatch, calls)
    monkeypatch.setattr(benchmark, "setup_logging", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr(benchmark, "_validate_preset_arg", lambda _args: None)

    def boom(*_a: Any, **_k: Any) -> int:
        raise RuntimeError("handler failed")

    monkeypatch.setattr(benchmark, "run_share_analysis", boom)
    with pytest.raises(RuntimeError, match="handler failed"):
        _run_main(
            monkeypatch,
            ["share", "--csv", "x.csv", "--entity", "E", "--metric", "m"],
        )
    assert calls == [("start", ("cli_share",)), ("end", ())]


def test_telemetry_service_failure_does_not_change_cli_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The helpers' never-raise guarantee must protect the CLI exit code."""

    def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("session service boom")

    monkeypatch.setattr("core.telemetry._get_service", boom)
    monkeypatch.setattr(benchmark, "setup_logging", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr(benchmark, "run_share_analysis", lambda *_a, **_k: 0)
    monkeypatch.setattr(benchmark, "_validate_preset_arg", lambda _args: None)

    code = _run_main(
        monkeypatch,
        ["share", "--csv", "x.csv", "--entity", "E", "--metric", "m"],
    )
    assert code == 0


@pytest.mark.parametrize(
    "argv",
    [
        ["--version"],
        ["--help"],
        ["config", "list"],
        ["telemetry", "who"],
        ["share", "--csv", "x.csv", "--entity", "E", "--metric", "m", "--preset", "no_such_preset"],
    ],
)
def test_non_analysis_and_invalid_preset_start_no_session(
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: List[Tuple[str, tuple]] = []
    _patch_session_helpers(monkeypatch, calls)
    monkeypatch.setattr(benchmark, "setup_logging", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr(benchmark, "run_share_analysis", lambda *_a, **_k: 0)
    monkeypatch.setattr(benchmark, "handle_config_command", lambda _a: 0)
    monkeypatch.setattr(benchmark, "handle_telemetry_command", lambda _a: 0)
    monkeypatch.setattr(benchmark, "print_version", lambda: None)

    if argv == ["--help"]:
        with pytest.raises(SystemExit) as exc_info:
            _run_main(monkeypatch, argv)
        assert exc_info.value.code == 0
    else:
        code = _run_main(monkeypatch, argv)
        assert code in (0, 1)
    assert calls == []
    capsys.readouterr()


def test_cli_adapters_do_not_emit_action_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    action_calls: list[str] = []
    monkeypatch.setattr(
        benchmark,
        "start_session",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(benchmark, "end_session", lambda: None)
    monkeypatch.setattr(benchmark, "setup_logging", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr(benchmark, "_validate_preset_arg", lambda _args: None)

    # If CLI adapters wrongly imported action helpers, patching analysis_run is enough;
    # also ensure benchmark module itself has no action_* calls during main.
    for name in (
        "action_attempted",
        "action_completed",
        "action_refused",
        "action_failed",
        "action_cancelled",
    ):
        if hasattr(benchmark, name):
            monkeypatch.setattr(
                benchmark,
                name,
                lambda *a, _n=name, **k: action_calls.append(_n),
            )

    monkeypatch.setattr(benchmark, "run_share_analysis", lambda *_a, **_k: 0)
    code = _run_main(
        monkeypatch,
        ["share", "--csv", "x.csv", "--entity", "E", "--metric", "m"],
    )
    assert code == 0
    assert action_calls == []
