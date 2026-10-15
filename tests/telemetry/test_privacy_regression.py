"""Privacy and non-interference regressions for offline telemetry."""

from __future__ import annotations

import asyncio
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
import tui_app
from core.analysis_run import RunBlocked, execute_share_run
from core.audit_log import build_audit_log_model
from core.contracts import AnalysisRunRequest
from core.telemetry import constants
from core.telemetry import events as telemetry_events
from core.telemetry.events import decode_record
from core.telemetry.identity import Identity, encode_user_token
from core.telemetry.reader import TelemetryReader
from core.telemetry.service import TelemetryService

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

EXPECTED_SHARE_PROPS = (
    {"action": "share_analysis"},
    {"action": "share_analysis", "publication_withheld": False},
)
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


def _violating_share_df() -> pd.DataFrame:
    """Dataset with an exclusive PREPAID category (single peer) under 6 peers."""
    rows: list[dict[str, object]] = [
        {"issuer_name": entity, "card_type": "CREDIT", "txn_cnt": 100}
        for entity in ("Target", "P1", "P2", "P3", "P4", "P5", "P6")
    ]
    rows.append({"issuer_name": "P1", "card_type": "PREPAID", "txn_cnt": 5000})
    return pd.DataFrame(rows)


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
    """Break the telemetry service under the helpers' never-raise wrappers."""

    def raise_always(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("boom-helper")

    monkeypatch.setattr("core.telemetry._get_service", raise_always)


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
    # G13: the withheld publication is visible as a bare boolean, and the
    # record carries nothing about which violation caused it.
    completed = [decode_record(raw) for raw in captured if b"action_completed" in raw]
    assert [dict(e.props) for e in completed] == [
        {"action": "share_analysis", "publication_withheld": True}
    ]
    for raw in captured:
        text = raw.decode("utf-8")
        for marker in ("PREPAID", "CREDIT", "card_type", "P1", "Target", "strict_posture", "violat"):
            assert marker not in text

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
    assert tuple(dict(event.props) for event in decoded_events) == EXPECTED_SHARE_PROPS

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
    telemetry.action_completed("share_analysis", False)
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


# ---------------------------------------------------------------------------
# Schema v2: every new event and prop is closed (pass-1 telemetry gaps)
# ---------------------------------------------------------------------------

# One valid prop set per v2 event; each prop is then replaced by hostile values.
_V2_VALID_PROPS: dict[str, dict[str, object]] = {
    "session_start": {"launch_context": "tui"},
    "session_end": {"duration_s": 1.0},
    "session_restored": {},
    "surface_viewed": {"surface": "validation_review"},
    "action_attempted": {"action": "share_analysis"},
    "action_completed": {"action": "share_analysis", "publication_withheld": True},
    "action_cancelled": {"action": "rate_analysis", "prompt": "clearing_spend"},
    "action_refused": {"action": "share_analysis", "reason": "configuration"},
    "action_failed": {"action": "share_analysis", "category": "input"},
    "launch_blocked": {"action": "share_analysis", "reason": "metric_missing"},
    "dataset_load": {"outcome": "header_read_failed"},
    "advanced_override": {"outcome": "applied"},
}

# Free text, paths, file/column/entity names, data values, exception text,
# counts, and type confusion: none of these may ever be recordable.
_HOSTILE_VALUES: tuple[object, ...] = (
    "/ads_storage/alice/peers_2026.csv",
    "peers_2026.csv",
    "gate_demo",
    "issuer_name",
    "txn_cnt",
    "card_type",
    "Target",
    "Acme Bank N.A.",
    "PREPAID",
    "balanced_default",
    "ValueError: could not convert string to float: 'abc'",
    "CSV path is required.",
    "Primary metric is required for share analysis.",
    "strict_posture_violations",
    "x" * 300,
    "",
    " ",
    "csv_missing ",
    "CSV_MISSING",
    "loaded\n",
    "applied\x1b[31m",
    0,
    1,
    7,
    12_345,
    -1,
    3.5,
    float("nan"),
    None,
    [],
    {},
    ["csv_missing"],
    {"reason": "csv_missing"},
)


def _build_v2(event: str, props: dict[str, object]) -> bytes:
    return telemetry_events.build_record(
        event,
        props,
        user="alice",
        session_id=SESSION_ID,
        app_version="3.0",
    )


def test_v2_valid_props_cover_the_whole_catalog() -> None:
    assert set(_V2_VALID_PROPS) == set(telemetry_events.event_names())
    for event, props in _V2_VALID_PROPS.items():
        decoded = decode_record(_build_v2(event, props))
        assert dict(decoded.props) == props


@pytest.mark.parametrize("event", sorted(_V2_VALID_PROPS))
def test_every_v2_prop_rejects_free_text_and_data_values(event: str) -> None:
    for key in _V2_VALID_PROPS[event]:
        for hostile in _HOSTILE_VALUES:
            if key == "duration_s" and isinstance(hostile, (int, float)) and not isinstance(hostile, bool):
                # The one bounded numeric field: finite, 0 <= x <= 1 year.
                if hostile == hostile and 0 <= hostile <= constants.MAX_DURATION_S:
                    continue
            props = dict(_V2_VALID_PROPS[event])
            props[key] = hostile
            with pytest.raises(telemetry_events.EventValidationError):
                _build_v2(event, props)
        # Booleans only where a boolean is declared, and vice versa.
        props = dict(_V2_VALID_PROPS[event])
        props[key] = "true" if key == "publication_withheld" else True
        with pytest.raises(telemetry_events.EventValidationError):
            _build_v2(event, props)


@pytest.mark.parametrize("event", sorted(_V2_VALID_PROPS))
def test_v2_events_reject_any_extra_key(event: str) -> None:
    for extra in ("message", "path", "file", "column", "entity", "rows", "exception", "field"):
        props = dict(_V2_VALID_PROPS[event])
        props[extra] = "csv_missing"
        with pytest.raises(telemetry_events.EventValidationError):
            _build_v2(event, props)


# Schema v3 (TUI layout shell): the visible Cancel prompts and the
# large-entity no-match block. Same closed-enum rules; near misses and data
# values (the typed entity text above all) are rejected.
_V3_NEW_VALUES = (
    ("action_cancelled", "prompt", "cancel_before_run"),
    ("action_cancelled", "prompt", "cancel_during_run"),
    ("launch_blocked", "reason", "entity_not_found"),
)


@pytest.mark.parametrize(("event", "key", "value"), _V3_NEW_VALUES)
def test_v3_values_are_closed_and_reject_near_misses(event: str, key: str, value: str) -> None:
    props = dict(_V2_VALID_PROPS[event])
    props[key] = value
    raw = _build_v2(event, props)
    decoded = decode_record(raw)
    assert decoded.schema_version == constants.SCHEMA_VERSION == 3
    assert dict(decoded.props) == props
    near_misses = (
        value.upper(),
        f" {value}",
        f"{value} ",
        value.replace("_", "-"),
        f"{value}:ENT_00x9",
        "ENT_00x9",
        "Target entity not found in issuer_name.",
        "cancel_requested",
    )
    for hostile in near_misses + _HOSTILE_VALUES:
        bad = dict(props)
        bad[key] = hostile
        with pytest.raises(telemetry_events.EventValidationError):
            _build_v2(event, bad)
    for extra in ("entity", "typed", "message", "stage", "elapsed_s"):
        bad = dict(props)
        bad[extra] = value
        with pytest.raises(telemetry_events.EventValidationError):
            _build_v2(event, bad)


def test_new_vocabularies_hold_no_data_or_config_names() -> None:
    vocab = set().union(
        constants.LAUNCH_BLOCK_REASONS,
        constants.CANCEL_PROMPTS,
        constants.DATASET_LOAD_OUTCOMES,
        constants.ADVANCED_OVERRIDE_OUTCOMES,
        constants.SURFACES,
    )
    markers = _sensitive_markers(Path("/nonexistent"), output_stem="x") + tuple(
        spec.widget_id for spec in tui_app.ADVANCED_FIELD_SPECS
    )
    for value in vocab:
        assert value.isascii() and value.replace("_", "").isalpha()
        for marker in markers:
            assert marker not in value


def test_tui_friction_emission_records_only_closed_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drive the real TUI handlers with sensitive inputs; inspect raw records."""
    captured: list[bytes] = []
    _inject_service(writer=captured.append, storage_root=tmp_path / "ads", environ={})
    monkeypatch.setattr(tui_app, "SESSION_FILE", tmp_path / "session.yaml")
    (tmp_path / "session.yaml").write_text("validate_input: true\n", encoding="utf-8")
    secret_csv = tmp_path / "Acme_Bank_issuer_peers.csv"
    secret_csv.write_text("issuer_name,txn_cnt,card_type\nTarget,1,PREPAID\n", encoding="utf-8")
    missing_csv = tmp_path / "Missing_Secret_Bank.csv"

    async def scenario() -> None:
        async with tui_app.BenchmarkApp().run_test(size=(120, 40)) as pilot:
            app = pilot.app
            await pilot.pause()
            app._resolve_csv_path(str(missing_csv))
            app.load_csv_headers(str(secret_csv))
            app.load_csv_headers(str(secret_csv))  # deduplicated
            await pilot.pause()
            app.query_one("#csv_path").value = ""
            app.run_analysis()
            await app.workers.wait_for_complete()
            await pilot.pause()
            request = AnalysisRunRequest(mode="share", metric="txn_cnt", entity="Target")
            log = app.query_one("#log_output")
            app._handle_validation_modal_result(
                False, has_errors=True, should_abort=True,
                request=request, saved_df=None, log_widget=log,
            )
            app._handle_validation_modal_result(
                False, has_errors=False, should_abort=False,
                request=request, saved_df=None, log_widget=log,
            )
            app.action_show_help()
            await pilot.pause()

    asyncio.run(scenario())
    telemetry._reset_for_tests()

    decoded = [decode_record(raw) for raw in captured]
    by_event = [(e.event, dict(e.props)) for e in decoded]
    assert ("session_restored", {}) in by_event
    assert by_event.count(("dataset_load", {"outcome": "loaded"})) == 1
    assert ("dataset_load", {"outcome": "not_found"}) in by_event
    assert ("launch_blocked", {"action": "share_analysis", "reason": "csv_missing"}) in by_event
    assert (
        "launch_blocked",
        {"action": "share_analysis", "reason": "validation_errors"},
    ) in by_event
    assert (
        "action_cancelled",
        {"action": "share_analysis", "prompt": "validation_review"},
    ) in by_event
    assert ("surface_viewed", {"surface": "preset_help"}) in by_event

    markers = (
        str(tmp_path),
        "Acme",
        "Missing_Secret",
        "issuer",
        "txn_cnt",
        "card_type",
        "Target",
        "PREPAID",
        "CSV path is required",
        "cancelled by user",
        "Cannot run",
        "ERROR",
    )
    for raw in captured:
        text = raw.decode("utf-8")
        assert frozenset(json.loads(text)) == ENVELOPE_KEYS
        for marker in markers:
            assert marker not in text


def test_reader_fallback_warning_names_reason_without_leaking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copied shared files fail the owner gate; the warning says why, and
    names neither the rejected files nor anything inside them."""
    shared = tmp_path / "copied"
    users = shared / "users"
    users.mkdir(parents=True)
    copied = _build_v2("launch_blocked", {"action": "share_analysis", "reason": "csv_missing"})
    payload = json.loads(copied)
    payload["user"] = "secret_peer_analyst"
    raw = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
    (users / f"{encode_user_token('secret_peer_analyst')}.jsonl").write_bytes(raw)
    # Owner UID of the copy is ours, not the named user's: owner_mismatch.
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: os.geteuid() + 1)
    warnings: list[str] = []
    reader = TelemetryReader(
        shared_dir=shared,
        identity=_identity(),
        storage_root=tmp_path / "ads",
        warn=warnings.append,
    )
    assert list(reader.iter_events(days=None)) == []
    assert len(warnings) == 1
    assert "owner_mismatch=1" in warnings[0]
    assert "private" in warnings[0]
    assert "secret_peer_analyst" not in warnings[0]
    assert encode_user_token("secret_peer_analyst") not in warnings[0]
    assert "csv_missing" not in warnings[0]


def test_tui_v3_emissions_record_only_closed_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Schema v3 end to end: the large-entity no-match block and the visible
    Cancel reach the real writer as closed values only; the typed entity
    text, the file and its columns never do."""
    import time as _time

    from textual.widgets import Checkbox, Input, Select, SelectionList, TabbedContent

    captured: list[bytes] = []
    _inject_service(writer=captured.append, storage_root=tmp_path / "ads", environ={})
    monkeypatch.setattr(tui_app, "SESSION_FILE", tmp_path / "session.yaml")
    monkeypatch.setenv("AUTOBENCH_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.chdir(tmp_path)
    secret_csv = tmp_path / "Acme_Secret_Bank_entities.csv"
    rows = ["issuer_name,card_type,txn_cnt,total,fraud"]
    rows += [f"SecretBank_{i:05d},CREDIT,{i + 1},{i + 10},1" for i in range(2500)]
    secret_csv.write_text("\n".join(rows) + "\n", encoding="utf-8")

    async def until(pilot, predicate, timeout: float = 20.0) -> None:
        deadline = _time.monotonic() + timeout
        while not predicate():
            assert _time.monotonic() < deadline
            await pilot.pause(0.05)

    async def scenario() -> None:
        async with tui_app.BenchmarkApp().run_test(size=(120, 40)) as pilot:
            app = pilot.app
            await pilot.pause()
            app.query_one("#csv_path", Input).value = str(secret_csv)
            app.load_csv_headers(str(secret_csv), announce=False)
            await until(pilot, lambda: app._entity_large and not app.entity_values_loading)
            app.query_one("#validate_input", Checkbox).value = False
            app.query_one("#share_metric", Select).value = "txn_cnt"
            app.query_one("#share_dims", SelectionList).select("card_type")
            app.query_one("#entity_filter", Input).value = "SecretBank_0000x"
            await pilot.pause()
            app.run_analysis()
            await until(pilot, lambda: app.focused is not None and app.focused.id == "entity_filter")
            await until(pilot, lambda: app._run_state == "idle")
            # Visible Cancel at the clearing-spend dialog (rate + fraud).
            app.query_one("#entity_filter", Input).value = ""
            app.query_one(TabbedContent).active = "rate_tab"
            await pilot.pause()
            app.query_one("#rate_total", Select).value = "total"
            app.query_one("#rate_fraud", Select).value = "fraud"
            app.query_one("#rate_dims", SelectionList).select("card_type")
            await pilot.pause()
            app.run_analysis()
            await until(pilot, lambda: isinstance(app.screen, tui_app.ClearingSpendConfirmScreen))
            await pilot.press("ctrl+g")
            await until(pilot, lambda: app._run_state == "cancelled")

    asyncio.run(scenario())
    telemetry._reset_for_tests()

    decoded = [decode_record(raw) for raw in captured]
    by_event = [(e.event, dict(e.props)) for e in decoded]
    assert ("launch_blocked", {"action": "share_analysis", "reason": "entity_not_found"}) in by_event
    assert ("action_cancelled", {"action": "rate_analysis", "prompt": "cancel_before_run"}) in by_event
    assert not any(e == "action_cancelled" and p.get("prompt") == "clearing_spend" for e, p in by_event)
    assert {e.schema_version for e in decoded if e.event not in ("session_start", "session_end")} == {3}
    for raw in captured:
        text = raw.decode("utf-8")
        assert frozenset(json.loads(text)) == ENVELOPE_KEYS
        for marker in (str(tmp_path), "Acme", "Secret", "0000x", "issuer", "txn_cnt",
                       "card_type", "not found"):
            assert marker not in text, marker
