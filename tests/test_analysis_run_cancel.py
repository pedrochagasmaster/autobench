"""Optional cancel and stage hooks on the shared run seam (owner decision 1).

The hooks are additive: the CLI passes neither, and a run without them (or
with hooks that never cancel) must behave exactly as before.
"""

from __future__ import annotations

import inspect
import logging
import re
from pathlib import Path
from typing import Any, List, Tuple

import pandas as pd
import pytest

import benchmark
import core.analysis_run as analysis_run
from core.analysis_run import RunAborted, RunCancelled, execute_run
from core.contracts import AnalysisRunRequest

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "gate_demo.csv"
PHASES = ["configuration", "input", "analysis", "output"]


def _share_request(output: Path, **overrides: Any) -> AnalysisRunRequest:
    data: dict[str, Any] = {
        "csv": str(FIXTURE),
        "entity": "Target",
        "metric": "txn_cnt",
        "dimensions": ["card_type", "channel"],
        "time_col": "year_month",
        "preset": "balanced_default",
        "compliance_posture": "best_effort",
        "output": str(output),
        "validate_input": False,
        "export_balanced_csv": True,
    }
    data.update(overrides)
    return AnalysisRunRequest(**data)


def _rate_request(output: Path) -> AnalysisRunRequest:
    return AnalysisRunRequest(
        mode="rate",
        csv=str(FIXTURE),
        entity="Target",
        total_col="total",
        approved_col="approved",
        dimensions=["card_type", "channel"],
        time_col="year_month",
        preset="balanced_default",
        compliance_posture="best_effort",
        output=str(output),
        validate_input=False,
    )


def _capture_telemetry(monkeypatch: pytest.MonkeyPatch) -> List[Tuple[str, tuple]]:
    calls: List[Tuple[str, tuple]] = []
    for name in (
        "action_attempted",
        "action_completed",
        "action_refused",
        "action_failed",
    ):
        monkeypatch.setattr(
            analysis_run,
            name,
            lambda *args, _name=name: calls.append((_name, args)),
        )
    return calls


@pytest.fixture
def gate_spy(monkeypatch: pytest.MonkeyPatch) -> List[bool]:
    """Record every PrivacyRunLogGate.finish(privacy_authorized=...) call."""
    finished: List[bool] = []
    real_finish = analysis_run.PrivacyRunLogGate.finish

    def finish(self, *, privacy_authorized: bool) -> None:
        finished.append(privacy_authorized)
        real_finish(self, privacy_authorized=privacy_authorized)

    monkeypatch.setattr(analysis_run.PrivacyRunLogGate, "finish", finish)
    return finished


def _files(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.rglob("*") if p.is_file())


@pytest.mark.parametrize("stop_before", PHASES)
def test_cancel_at_each_boundary_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gate_spy: List[bool],
    stop_before: str,
) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    calls = _capture_telemetry(monkeypatch)
    stages: list[str] = []

    def cancel_requested() -> bool:
        # The hook is asked before each phase; cancel before ``stop_before``.
        entered = len(stages)
        return PHASES[entered] == stop_before

    with pytest.raises(RunCancelled) as excinfo:
        execute_run(
            _share_request(out_dir / "share.xlsx"),
            logging.getLogger("test_cancel"),
            cancel_requested=cancel_requested,
            on_stage=stages.append,
        )

    assert stages == PHASES[: PHASES.index(stop_before)]
    # The exception names the last phase entered, never "output".
    assert excinfo.value.phase in ("configuration", "input", "analysis")
    assert not isinstance(excinfo.value, RunAborted)
    assert _files(out_dir) == []
    # Log-gate finalisation still ran, with privacy not authorized.
    assert gate_spy == [False]
    # Core records the attempt but no refusal or failure; the caller that
    # asked for the cancel records action_cancelled.
    assert calls == [("action_attempted", ("share_analysis",))]


def test_cancel_is_never_checked_once_output_has_started(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    _capture_telemetry(monkeypatch)
    stages: list[str] = []
    checks_after_output: list[str] = []

    def cancel_requested() -> bool:
        if stages and stages[-1] == "output":
            checks_after_output.append("checked")
            return True
        return False

    artifacts = execute_run(
        _share_request(out_dir / "share.xlsx"),
        logging.getLogger("test_cancel"),
        cancel_requested=cancel_requested,
        on_stage=stages.append,
    )

    assert stages == PHASES
    assert checks_after_output == []
    assert artifacts.analysis_output_file


def test_rate_run_reports_stages_and_cancels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _capture_telemetry(monkeypatch)
    stages: list[str] = []
    with pytest.raises(RunCancelled):
        execute_run(
            _rate_request(tmp_path / "rate.xlsx"),
            logging.getLogger("test_cancel"),
            cancel_requested=lambda: stages[-1:] == ["analysis"],
            on_stage=stages.append,
        )
    assert stages == ["configuration", "input", "analysis"]
    assert _files(tmp_path) == []


def test_failing_stage_callback_does_not_change_the_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _capture_telemetry(monkeypatch)

    def broken(_stage: str) -> None:
        raise RuntimeError("display gone")

    artifacts = execute_run(
        _share_request(tmp_path / "share.xlsx"),
        logging.getLogger("test_cancel"),
        on_stage=broken,
    )
    assert artifacts.analysis_output_file
    assert [name for name, _ in calls] == ["action_attempted", "action_completed"]


_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?")
_ELAPSED = re.compile(r'(elapsed_s"?:\s*)[\d.]+')


def _sheet_cells(path: Path, run_dir: Path) -> dict[str, list[list[str]]]:
    """Every sheet's cells as text; run timestamps, timings and folder masked."""
    sheets = pd.read_excel(path, sheet_name=None, header=None)
    normalized: dict[str, list[list[str]]] = {}
    for name, frame in sheets.items():
        rows = []
        for row in frame.astype(str).values.tolist():
            rows.append(
                [
                    _ELAPSED.sub(
                        r"\1<s>",
                        _TIMESTAMP.sub("<time>", cell.replace(str(run_dir), "<dir>")),
                    )
                    for cell in row
                ]
            )
        normalized[name] = rows
    return normalized


def test_unhooked_run_is_unchanged_by_noop_hooks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A run with hooks that never cancel equals a run with no hooks."""
    calls = _capture_telemetry(monkeypatch)
    plain_dir = tmp_path / "plain"
    hooked_dir = tmp_path / "hooked"
    plain_dir.mkdir()
    hooked_dir.mkdir()
    logger = logging.getLogger("test_cancel")

    plain = execute_run(_share_request(plain_dir / "share.xlsx"), logger)
    plain_calls = list(calls)
    calls.clear()
    stages: list[str] = []
    hooked = execute_run(
        _share_request(hooked_dir / "share.xlsx"),
        logger,
        cancel_requested=lambda: False,
        on_stage=stages.append,
    )

    assert stages == PHASES
    assert calls == plain_calls
    assert _files(plain_dir) == _files(hooked_dir)
    plain_csv = sorted(plain_dir.glob("*.csv"))
    assert plain_csv, "balanced CSV export expected"
    for csv_path in plain_csv:
        assert csv_path.read_bytes() == (hooked_dir / csv_path.name).read_bytes()
    # Same sheets, same cells; only the run timestamp and folder may differ.
    assert _sheet_cells(Path(plain.analysis_output_file), plain_dir) == _sheet_cells(
        Path(hooked.analysis_output_file), hooked_dir
    )
    assert plain.compliance_summary == hooked.compliance_summary


def test_cli_adapters_never_pass_hooks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """benchmark.py reaches _execute_run with both hooks unset."""
    seen: list[tuple[Any, Any]] = []
    real = analysis_run._execute_run

    def spy(*args: Any, **kwargs: Any):
        seen.append((kwargs.get("cancel_requested"), kwargs.get("on_stage")))
        return real(*args, **kwargs)

    monkeypatch.setattr(analysis_run, "_execute_run", spy)
    _capture_telemetry(monkeypatch)
    args = benchmark.create_parser().parse_args(
        [
            "share",
            "--csv",
            str(FIXTURE),
            "--entity",
            "Target",
            "--metric",
            "txn_cnt",
            "--dimensions",
            "card_type",
            "channel",
            "--time-col",
            "year_month",
            "--preset",
            "balanced_default",
            "--no-validate-input",
            "--output",
            str(tmp_path / "cli.xlsx"),
        ]
    )
    benchmark.run_share_analysis(args, logging.getLogger("test_cancel_cli"))
    assert seen == [(None, None)]
    # The CLI call sites keep their two-argument form.
    source = inspect.getsource(benchmark)
    assert "execute_share_run(request, logger)" in source
    assert "execute_rate_run(request, logger)" in source


def test_phase_tracker_without_hooks_only_records_the_phase() -> None:
    tracker = analysis_run._PhaseTracker()
    for phase in PHASES:
        tracker.set(phase)
        assert tracker.phase == phase
