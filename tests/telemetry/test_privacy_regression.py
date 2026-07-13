"""Privacy and non-interference regressions for offline telemetry."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable
from uuid import UUID

import pandas as pd
import pandas.testing as pdt
import pytest

import core.analysis_run as analysis_run
import core.telemetry as telemetry
from core.analysis_run import RunBlocked, execute_share_run
from core.audit_log import build_audit_log_model
from core.contracts import AnalysisRunRequest
from core.telemetry.events import decode_record
from core.telemetry.identity import Identity, encode_user_token
from core.telemetry.service import TelemetryService
from tests.test_strict_exit_codes import _violating_share_df

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "gate_demo.csv"
SHARE_DIMENSIONS = ["card_type", "channel"]
SESSION_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
REPO_ROOT = Path(__file__).resolve().parents[2]

ENVELOPE_KEYS = frozenset(
    {
        "schema_version",
        "ts",
        "event",
        "user",
        "session_id",
        "app_version",
        "props",
    }
)

ALLOWED_TRACKED_JSONL = (
    "qa/features.jsonl",
    "test_gate/config/cases.jsonl",
    "test_gate/rate/cases.jsonl",
    "test_gate/share/cases.jsonl",
)

# Skip tool/cache/venv/worktree internals when scanning for generated events.jsonl.
_SCAN_SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "node_modules",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        ".cursor",
        ".idea",
        ".vscode",
        "worktrees",
        ".worktrees",
        "git-worktrees",
    }
)

TELEMETRY_FORBIDDEN_META_KEYS = frozenset(
    {
        "telemetry",
        "telemetry_session_id",
        "session_id",
        "telemetry_user",
        "telemetry_events",
    }
)

INCIDENTAL_META_KEYS = frozenset(
    {
        "timestamp",
        "observability",
    }
)

SHARE_ACTION_PROPS = {"action": "share_analysis"}
EXPECTED_SHARE_EVENTS = ("action_attempted", "action_completed")


@pytest.fixture(autouse=True)
def _reset_telemetry() -> None:
    telemetry._reset_for_tests()
    yield
    telemetry._reset_for_tests()


def _identity(username: str = "alice") -> Identity:
    return Identity(
        uid=os.geteuid(),
        username=username,
        token=encode_user_token(username),
    )


def _inject_service(
    *,
    writer: Callable[[bytes], None] | None = None,
    storage_root: Path,
    environ: dict[str, str] | None = None,
    shared_dir: Path | None = None,
) -> TelemetryService:
    svc = TelemetryService(
        identity=_identity(),
        session_id=SESSION_ID,
        app_version="3.0",
        environ={} if environ is None else environ,
        writer=writer,
        storage_root=storage_root,
        shared_dir=shared_dir if shared_dir is not None else storage_root / "shared",
        shutdown_budget_s=1.0,
    )
    telemetry._reset_for_tests(svc)
    return svc


def _representative_df() -> pd.DataFrame:
    return pd.read_csv(FIXTURE)


def _share_request(tmp_path: Path, *, stem: str, df: pd.DataFrame, **overrides: Any) -> AnalysisRunRequest:
    data: dict[str, Any] = {
        "df": df.copy(),
        "entity": "Target",
        "metric": "txn_cnt",
        "dimensions": list(SHARE_DIMENSIONS),
        "time_col": "year_month",
        "preset": "balanced_default",
        "compliance_posture": "strict",
        "output": str(tmp_path / f"{stem}.xlsx"),
        "validate_input": True,
        "output_format": "both",
    }
    data.update(overrides)
    return AnalysisRunRequest(**data)


def _violating_request(tmp_path: Path, *, stem: str) -> AnalysisRunRequest:
    return AnalysisRunRequest(
        df=_violating_share_df(),
        entity="Target",
        metric="txn_cnt",
        dimensions=["card_type"],
        preset="compliance_strict",
        compliance_posture="strict",
        output=str(tmp_path / f"{stem}.xlsx"),
        validate_input=False,
        output_format="both",
    )


def _is_dataframe(value: Any) -> bool:
    return hasattr(value, "equals") and hasattr(value, "shape")


def _strip_incidental(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            lowered = key.lower()
            if key in INCIDENTAL_META_KEYS:
                continue
            if "path" in lowered or lowered.endswith("_file") or lowered.endswith("_output"):
                continue
            if key in {"outputs", "balanced_csv", "report_paths"}:
                continue
            if _is_dataframe(item):
                continue
            out[key] = _strip_incidental(item)
        return out
    if isinstance(value, list):
        return [_strip_incidental(item) for item in value]
    return value


def _publication_decision(artifacts: Any) -> dict[str, Any]:
    metadata = artifacts.metadata or {}
    return {
        "publication_written": artifacts.publication_output is not None,
        "publication_withheld_reason": metadata.get("publication_withheld_reason"),
    }


def _assert_stable_result_keys(artifacts: Any, *, expected: list[str] | tuple[str, ...]) -> None:
    assert list((artifacts.results or {}).keys()) == list(expected)


def _assert_analysis_equivalent(left: Any, right: Any) -> None:
    assert left.compliance_summary == right.compliance_summary
    assert left.compliance_summary is not None
    assert left.compliance_summary["compliance_verdict"] == right.compliance_summary["compliance_verdict"]
    assert left.compliance_summary["posture"] == right.compliance_summary["posture"]
    assert _publication_decision(left) == _publication_decision(right)

    _assert_stable_result_keys(left, expected=SHARE_DIMENSIONS)
    _assert_stable_result_keys(right, expected=SHARE_DIMENSIONS)
    for key in SHARE_DIMENSIONS:
        pdt.assert_frame_equal(left.results[key], right.results[key])

    assert _strip_incidental(left.metadata or {}) == _strip_incidental(right.metadata or {})


def _assert_publication_file_exists(artifacts: Any) -> None:
    assert artifacts.publication_output is not None
    assert Path(artifacts.publication_output).exists()


def _sensitive_markers(tmp_path: Path, *, output_stem: str) -> tuple[str, ...]:
    return (
        str(FIXTURE),
        str(tmp_path / f"{output_stem}.xlsx"),
        str(tmp_path / f"{output_stem}_publication.xlsx"),
        "Target",
        "issuer_name",
        "txn_cnt",
        "card_type",
        "channel",
        "year_month",
        "balanced_default",
        "gate_demo",
        "RuntimeError",
        "boom-helper",
        "P1",
        "P2",
        "PREPAID",
        "/ads_storage",
        "observability",
        "total_elapsed_s",
    )


def _assert_no_telemetry_fields(payload: dict[str, Any]) -> None:
    stack: list[Any] = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, value in current.items():
                assert key not in TELEMETRY_FORBIDDEN_META_KEYS
                assert "telemetry" not in key.lower()
                stack.append(value)
        elif isinstance(current, list):
            stack.extend(current)


def _patch_helpers_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_always(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("boom-helper")

    for name in (
        "action_attempted",
        "action_completed",
        "action_refused",
        "action_failed",
    ):
        monkeypatch.setattr(analysis_run, name, raise_always)


def _iter_untracked_events_jsonl(root: Path) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in _SCAN_SKIP_DIR_NAMES]
        if "events.jsonl" in filenames:
            found.append(Path(dirpath) / "events.jsonl")
    return found


def test_equivalent_share_analysis_telemetry_on_vs_off(tmp_path: Path) -> None:
    df = _representative_df()
    captured: list[bytes] = []
    done = threading.Event()

    def writer(record: bytes) -> None:
        captured.append(record)
        if len(captured) >= 2:
            done.set()

    enabled_root = tmp_path / "enabled_ads"
    enabled_root.mkdir()
    _inject_service(writer=writer, storage_root=enabled_root, environ={})
    enabled = execute_share_run(
        _share_request(tmp_path / "enabled", stem="share", df=df),
        logging.getLogger("privacy_on"),
    )
    assert done.wait(timeout=2.0)
    assert captured

    disabled_root = tmp_path / "disabled_ads"
    disabled_root.mkdir()
    disabled_svc = _inject_service(
        writer=lambda _record: (_ for _ in ()).throw(AssertionError("opt-out must not write")),
        storage_root=disabled_root,
        environ={"AUTOBENCH_TELEMETRY": "0"},
    )
    disabled = execute_share_run(
        _share_request(tmp_path / "disabled", stem="share", df=df),
        logging.getLogger("privacy_off"),
    )
    assert disabled_svc.consumer_thread is None
    assert list(disabled_root.rglob("*.jsonl")) == []

    _assert_analysis_equivalent(enabled, disabled)
    assert enabled.compliance_summary["compliance_verdict"] == "fully_compliant"
    assert _publication_decision(enabled)["publication_written"] is True
    _assert_publication_file_exists(enabled)
    _assert_publication_file_exists(disabled)


def test_strict_nonpublishable_remains_withheld_on_and_off(tmp_path: Path) -> None:
    captured: list[bytes] = []
    done = threading.Event()

    def writer(record: bytes) -> None:
        captured.append(record)
        if len(captured) >= 2:
            done.set()

    enabled_root = tmp_path / "enabled_ads"
    enabled_root.mkdir()
    _inject_service(writer=writer, storage_root=enabled_root, environ={})
    enabled = execute_share_run(
        _violating_request(tmp_path / "enabled", stem="violating"),
        logging.getLogger("privacy_block_on"),
    )
    assert done.wait(timeout=2.0)

    disabled_root = tmp_path / "disabled_ads"
    disabled_root.mkdir()
    disabled_svc = _inject_service(
        writer=lambda _record: None,
        storage_root=disabled_root,
        environ={"AUTOBENCH_TELEMETRY": "0"},
    )
    disabled = execute_share_run(
        _violating_request(tmp_path / "disabled", stem="violating"),
        logging.getLogger("privacy_block_off"),
    )
    assert disabled_svc.consumer_thread is None

    for artifacts in (enabled, disabled):
        assert artifacts.compliance_summary is not None
        assert artifacts.compliance_summary["posture"] == "strict"
        assert int(artifacts.compliance_summary.get("violations", 0) or 0) > 0
        assert artifacts.publication_output is None
        assert (artifacts.metadata or {}).get("publication_withheld_reason") == "strict_posture_violations"
        analysis_path = Path(artifacts.analysis_output_file or "")
        assert analysis_path.exists()
        pub = analysis_path.with_name(f"{analysis_path.stem}_publication.xlsx")
        assert not pub.exists()

    assert enabled.compliance_summary == disabled.compliance_summary
    assert _publication_decision(enabled) == _publication_decision(disabled)

    blocked_request_kwargs = {
        "compliance_posture": "accuracy_first",
        "acknowledge_accuracy_first": False,
        "preset": None,
        "validate_input": False,
        "output_format": "analysis",
    }
    _inject_service(writer=writer, storage_root=tmp_path / "blocked_on_ads", environ={})
    with pytest.raises(RunBlocked) as enabled_blocked:
        execute_share_run(
            _share_request(
                tmp_path / "blocked_on",
                stem="blocked",
                df=_representative_df(),
                **blocked_request_kwargs,
            ),
            logging.getLogger("blocked_on"),
        )
    disabled_blocked_svc = _inject_service(
        writer=lambda _record: None,
        storage_root=tmp_path / "blocked_off_ads",
        environ={"AUTOBENCH_TELEMETRY": "0"},
    )
    with pytest.raises(RunBlocked) as disabled_blocked:
        execute_share_run(
            _share_request(
                tmp_path / "blocked_off",
                stem="blocked",
                df=_representative_df(),
                **blocked_request_kwargs,
            ),
            logging.getLogger("blocked_off"),
        )
    assert disabled_blocked_svc.consumer_thread is None
    assert enabled_blocked.value.compliance_summary == disabled_blocked.value.compliance_summary
    assert enabled_blocked.value.compliance_summary["compliance_verdict"] == "blocked"


def test_helper_failures_do_not_alter_compliance_or_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    df = _representative_df()
    ads = tmp_path / "ads"
    ads.mkdir()
    _inject_service(writer=lambda _record: None, storage_root=ads, environ={})

    baseline = execute_share_run(
        _share_request(tmp_path / "baseline", stem="share", df=df),
        logging.getLogger("privacy_baseline"),
    )

    _patch_helpers_raise(monkeypatch)

    broken = execute_share_run(
        _share_request(tmp_path / "broken", stem="share", df=df),
        logging.getLogger("privacy_broken"),
    )
    _assert_analysis_equivalent(baseline, broken)
    assert Path(broken.analysis_output_file or "").exists()
    _assert_publication_file_exists(broken)

    with pytest.raises(RunBlocked) as blocked_info:
        execute_share_run(
            _share_request(
                tmp_path / "refused",
                stem="refused",
                df=df,
                compliance_posture="accuracy_first",
                acknowledge_accuracy_first=False,
                preset=None,
                validate_input=False,
                output_format="analysis",
            ),
            logging.getLogger("privacy_refused"),
        )
    assert blocked_info.value.compliance_summary["compliance_verdict"] == "blocked"

    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("analysis-boom")

    monkeypatch.setattr(analysis_run, "build_dimensional_analyzer", boom)
    with pytest.raises(RuntimeError, match="analysis-boom"):
        execute_share_run(
            _share_request(tmp_path / "failed", stem="failed", df=df),
            logging.getLogger("privacy_failed"),
        )


def test_artifacts_metadata_and_audit_model_have_no_telemetry_fields(tmp_path: Path) -> None:
    ads = tmp_path / "ads"
    ads.mkdir()
    _inject_service(writer=lambda _record: None, storage_root=ads, environ={})
    artifacts = execute_share_run(
        _share_request(tmp_path, stem="share", df=_representative_df()),
        logging.getLogger("privacy_meta"),
    )
    assert artifacts.metadata is not None
    _assert_no_telemetry_fields(artifacts.metadata)
    _assert_no_telemetry_fields(artifacts.compliance_summary or {})
    _assert_stable_result_keys(artifacts, expected=SHARE_DIMENSIONS)
    _assert_publication_file_exists(artifacts)

    audit_model = build_audit_log_model(
        metadata=artifacts.metadata,
        report_paths=list(artifacts.report_paths or []),
        dimensions_analyzed=len(SHARE_DIMENSIONS),
        csv_output=artifacts.csv_output,
        impact_df=artifacts.impact_df,
        privacy_validation_df=artifacts.privacy_validation_df,
    )
    _assert_no_telemetry_fields(audit_model)


def test_captured_records_use_exact_envelope_and_approved_props_only(tmp_path: Path) -> None:
    captured: list[bytes] = []
    done = threading.Event()
    output_stem = "share_sensitive"

    def writer(record: bytes) -> None:
        captured.append(record)
        if len(captured) >= 2:
            done.set()

    ads = tmp_path / "ads"
    ads.mkdir()
    _inject_service(writer=writer, storage_root=ads, environ={})
    request = _share_request(tmp_path, stem=output_stem, df=_representative_df())
    artifacts = execute_share_run(request, logging.getLogger("privacy_envelope"))
    assert done.wait(timeout=2.0)
    assert Path(artifacts.analysis_output_file or "").exists()
    _assert_publication_file_exists(artifacts)
    _assert_stable_result_keys(artifacts, expected=SHARE_DIMENSIONS)

    decoded_events = [decode_record(raw) for raw in captured]
    assert [event.event for event in decoded_events] == list(EXPECTED_SHARE_EVENTS)
    assert len(decoded_events) == 2
    for event in decoded_events:
        assert dict(event.props) == SHARE_ACTION_PROPS

    markers = _sensitive_markers(tmp_path, output_stem=output_stem)
    for raw in captured:
        text = raw.decode("utf-8")
        payload = json.loads(text)
        assert frozenset(payload.keys()) == ENVELOPE_KEYS
        for marker in markers:
            assert marker not in text


def test_opt_out_starts_no_consumer_and_produces_no_records(tmp_path: Path) -> None:
    ads = tmp_path / "ads"
    ads.mkdir()
    written: list[bytes] = []
    svc = _inject_service(
        writer=written.append,
        storage_root=ads,
        environ={"AUTOBENCH_TELEMETRY": "0"},
    )
    telemetry.start_session("cli_share")
    telemetry.action_attempted("share_analysis")
    telemetry.action_completed("share_analysis")
    artifacts = execute_share_run(
        _share_request(tmp_path, stem="opt_out", df=_representative_df()),
        logging.getLogger("privacy_opt_out"),
    )
    telemetry.end_session()

    assert svc.consumer_thread is None
    assert written == []
    assert list(ads.rglob("*.jsonl")) == []
    _assert_publication_file_exists(artifacts)
    _assert_stable_result_keys(artifacts, expected=SHARE_DIMENSIONS)


def test_no_tracked_or_generated_telemetry_event_jsonl_under_repo() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.jsonl"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    tracked_paths = tuple(
        path for path in tracked.stdout.decode("utf-8").split("\0") if path
    )
    assert tracked_paths == ALLOWED_TRACKED_JSONL

    unexpected_events = _iter_untracked_events_jsonl(REPO_ROOT)
    assert unexpected_events == [], f"unexpected events.jsonl artifacts: {unexpected_events}"
