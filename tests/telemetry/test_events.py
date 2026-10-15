"""Tests for telemetry event envelope encoding and strict decoding."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Mapping
from uuid import UUID

import pytest

from core.telemetry import events as events_module
from core.telemetry.constants import MAX_RECORD_BYTES, SCHEMA_VERSION
from core.telemetry.events import (
    LEGACY_WRITE_EVENTS,
    MAX_APP_VERSION_BYTES,
    EventValidationError,
    UnsupportedSchemaVersion,
    ValidatedEvent,
    build_record,
    decode_record,
    record_schema_version,
)

SESSION_ID = UUID("12345678-1234-5678-1234-567812345678")
USER = "alice"
APP_VERSION = "3.0"
FIXED_NOW = datetime(2026, 7, 12, 22, 0, 0, tzinfo=timezone.utc)

APPROVED_EVENTS: list[tuple[str, dict[str, object]]] = [
    ("session_start", {"launch_context": "cli_share"}),
    ("session_start", {"launch_context": "cli_rate"}),
    ("session_start", {"launch_context": "tui"}),
    ("session_end", {"duration_s": 1.234}),
    ("session_end", {"duration_s": 0}),
    ("session_end", {"duration_s": 31_536_000}),
    ("surface_viewed", {"surface": "share"}),
    ("surface_viewed", {"surface": "rate"}),
    ("action_attempted", {"action": "share_analysis"}),
    ("action_attempted", {"action": "rate_analysis"}),
    ("surface_viewed", {"surface": "validation_review"}),
    ("surface_viewed", {"surface": "preset_help"}),
    ("surface_viewed", {"surface": "advanced"}),
    ("action_completed", {"action": "share_analysis", "publication_withheld": False}),
    ("action_completed", {"action": "rate_analysis", "publication_withheld": True}),
    ("action_cancelled", {"action": "share_analysis", "prompt": "validation_review"}),
    ("action_cancelled", {"action": "rate_analysis", "prompt": "clearing_spend"}),
    ("action_cancelled", {"action": "share_analysis", "prompt": "accuracy_first_consent"}),
    ("action_cancelled", {"action": "rate_analysis", "prompt": "quit_before_run"}),
    ("action_cancelled", {"action": "share_analysis", "prompt": "quit_during_run"}),
    ("launch_blocked", {"action": "share_analysis", "reason": "csv_missing"}),
    ("launch_blocked", {"action": "rate_analysis", "reason": "validation_errors"}),
    ("launch_blocked", {"action": "share_analysis", "reason": "initialization_error"}),
    ("dataset_load", {"outcome": "loaded"}),
    ("dataset_load", {"outcome": "entity_list_failed"}),
    ("advanced_override", {"outcome": "applied"}),
    ("advanced_override", {"outcome": "export_failed"}),
    ("session_restored", {}),
    ("action_refused", {"action": "share_analysis", "reason": "configuration"}),
    ("action_refused", {"action": "rate_analysis", "reason": "input_validation"}),
    ("action_refused", {"action": "share_analysis", "reason": "compliance_policy"}),
    ("action_failed", {"action": "share_analysis", "category": "input"}),
    ("action_failed", {"action": "rate_analysis", "category": "analysis"}),
    ("action_failed", {"action": "share_analysis", "category": "output"}),
    ("action_failed", {"action": "rate_analysis", "category": "unexpected"}),
]

ENVELOPE_KEYS = (
    "schema_version",
    "ts",
    "event",
    "user",
    "session_id",
    "app_version",
    "props",
)


def _build(
    event: str,
    props: Mapping[str, object],
    *,
    user: str = USER,
    session_id: UUID = SESSION_ID,
    app_version: str = APP_VERSION,
    now: datetime | None = FIXED_NOW,
) -> bytes:
    return build_record(
        event,
        props,
        user=user,
        session_id=session_id,
        app_version=app_version,
        now=now,
    )


@pytest.mark.parametrize(("event", "props"), APPROVED_EVENTS)
def test_build_and_decode_approved_events(event: str, props: dict[str, object]) -> None:
    raw = _build(event, props)
    assert raw.endswith(b"\n")
    assert raw.count(b"\n") == 1
    assert len(raw) <= MAX_RECORD_BYTES

    payload = json.loads(raw.decode("utf-8"))
    assert tuple(payload.keys()) == ENVELOPE_KEYS
    assert payload["schema_version"] == record_schema_version(event)
    assert payload["ts"] == "2026-07-12T22:00:00Z"
    assert payload["event"] == event
    assert payload["user"] == USER
    assert payload["session_id"] == str(SESSION_ID)
    assert payload["app_version"] == APP_VERSION
    assert payload["props"] == props
    assert list(payload["props"].keys()) == list(props.keys())

    decoded = decode_record(raw)
    assert isinstance(decoded, ValidatedEvent)
    assert decoded.schema_version == record_schema_version(event)
    assert decoded.ts == FIXED_NOW
    assert decoded.event == event
    assert decoded.user == USER
    assert decoded.session_id == str(SESSION_ID)
    assert decoded.app_version == APP_VERSION
    assert dict(decoded.props) == props


def test_build_record_is_compact_json_with_trailing_lf() -> None:
    raw = _build("session_start", {"launch_context": "tui"})
    body = raw[:-1]
    assert b" " not in body
    assert body.startswith(b"{") and body.endswith(b"}")


def test_build_record_rounds_duration_to_three_decimals() -> None:
    raw = _build("session_end", {"duration_s": 1.23456})
    props = json.loads(raw.decode("utf-8"))["props"]
    assert props == {"duration_s": 1.235}
    decoded = decode_record(raw)
    assert decoded.props == {"duration_s": 1.235}


def test_build_record_uses_utc_now_when_now_omitted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "core.telemetry.events._utc_now",
        lambda: datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
    )
    raw = build_record(
        "session_start",
        {"launch_context": "tui"},
        user=USER,
        session_id=SESSION_ID,
        app_version=APP_VERSION,
    )
    assert json.loads(raw.decode("utf-8"))["ts"] == "2026-01-02T03:04:05Z"


def test_decode_record_accepts_line_without_trailing_lf() -> None:
    raw = _build("session_start", {"launch_context": "tui"})
    decoded = decode_record(raw[:-1])
    assert decoded.event == "session_start"


def test_rejects_tiny_negative_duration_before_rounding() -> None:
    with pytest.raises(EventValidationError):
        _build("session_end", {"duration_s": -0.0001})


def test_duration_zero_normalizes_without_negative_zero() -> None:
    raw = _build("session_end", {"duration_s": 0.0})
    props = json.loads(raw.decode("utf-8"))["props"]
    assert props == {"duration_s": 0.0}
    assert '"duration_s":-0' not in raw.decode("utf-8")
    raw_neg_zero = _build("session_end", {"duration_s": -0.0})
    neg_props = json.loads(raw_neg_zero.decode("utf-8"))["props"]
    assert neg_props == {"duration_s": 0.0}
    assert '"duration_s":-0' not in raw_neg_zero.decode("utf-8")


def test_decode_accepts_canonical_uuid_session_id() -> None:
    raw = _build("session_start", {"launch_context": "tui"})
    decoded = decode_record(raw)
    assert decoded.session_id == str(SESSION_ID)
    assert decoded.session_id == "12345678-1234-5678-1234-567812345678"


@pytest.mark.parametrize(
    "bad_session_id",
    [
        "12345678-1234-5678-1234-567812345abc".upper(),
        "urn:uuid:12345678-1234-5678-1234-567812345678",
        "{12345678-1234-5678-1234-567812345678}",
        "12345678123456781234567812345678",
        "12345678-1234-5678-1234-567812345678 ",
    ],
)
def test_decode_rejects_noncanonical_uuid_session_id(bad_session_id: str) -> None:
    raw = _build("session_start", {"launch_context": "tui"})
    payload = json.loads(raw.decode("utf-8"))
    payload["session_id"] = bad_session_id
    line = (json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
    with pytest.raises(EventValidationError):
        decode_record(line)


def test_app_version_max_bytes_boundary() -> None:
    ok = "a" * MAX_APP_VERSION_BYTES
    raw = _build("session_start", {"launch_context": "tui"}, app_version=ok)
    assert decode_record(raw).app_version == ok
    with pytest.raises(EventValidationError):
        _build("session_start", {"launch_context": "tui"}, app_version=ok + "a")


@pytest.mark.parametrize(
    "bad_version",
    ["", "bad\nversion", "bad\x00version", "bad\u200bversion"],
)
def test_app_version_rejects_empty_and_controls(bad_version: str) -> None:
    with pytest.raises(EventValidationError):
        _build("session_start", {"launch_context": "tui"}, app_version=bad_version)


def test_rejects_unknown_event() -> None:
    with pytest.raises(EventValidationError):
        _build("session_pause", {"launch_context": "tui"})


@pytest.mark.parametrize(
    ("event", "props"),
    [
        ("session_start", {"launch_context": "cli_share", "extra": 1}),
        ("session_start", {}),
        ("session_start", {"launch_context": "other"}),
        ("session_end", {"duration_s": 1.0, "extra": True}),
        ("session_end", {}),
        ("surface_viewed", {"surface": "share", "path": "/tmp"}),
        ("surface_viewed", {"surface": "dashboard"}),
        ("action_attempted", {"action": "share_analysis", "entity": "Acme"}),
        ("action_attempted", {"action": "delete"}),
        ("action_completed", {"action": "share_analysis", "result": "ok"}),
        ("action_completed", {"action": "share_analysis"}),
        ("action_completed", {"action": "share_analysis", "publication_withheld": 1}),
        ("action_completed", {"action": "share_analysis", "publication_withheld": "true"}),
        ("action_completed", {"action": "share_analysis", "publication_withheld": None}),
        ("action_completed", {"action": "share_analysis", "publication_withheld": "strict_posture_violations"}),
        ("action_cancelled", {"action": "share_analysis", "why": "esc"}),
        ("action_cancelled", {"action": "share_analysis"}),
        ("action_cancelled", {"action": "share_analysis", "prompt": "esc"}),
        ("launch_blocked", {"action": "share_analysis"}),
        ("launch_blocked", {"reason": "csv_missing"}),
        ("launch_blocked", {"action": "share_analysis", "reason": "txn_cnt"}),
        ("launch_blocked", {"action": "share_analysis", "reason": "csv_missing", "field": "metric"}),
        ("dataset_load", {}),
        ("dataset_load", {"outcome": "peers.csv"}),
        ("dataset_load", {"outcome": "loaded", "columns": 12}),
        ("advanced_override", {"outcome": "applied", "field": "max_weight"}),
        ("advanced_override", {"outcome": "0.25"}),
        ("session_restored", {"restored": True}),
        ("action_refused", {"action": "share_analysis"}),
        ("action_refused", {"action": "share_analysis", "reason": "timeout"}),
        ("action_failed", {"action": "share_analysis"}),
        ("action_failed", {"action": "share_analysis", "category": "boom"}),
        ("action_failed", {"action": "share_analysis", "category": "input", "message": "x"}),
    ],
)
def test_rejects_unknown_missing_or_bad_property_keys(
    event: str, props: dict[str, object]
) -> None:
    with pytest.raises(EventValidationError):
        _build(event, props)


@pytest.mark.parametrize(
    "duration",
    [
        True,
        False,
        float("nan"),
        float("inf"),
        float("-inf"),
        -0.001,
        31_536_000.001,
        "1.0",
        None,
        {"s": 1},
        [1.0],
    ],
)
def test_rejects_invalid_duration_values(duration: object) -> None:
    with pytest.raises(EventValidationError):
        _build("session_end", {"duration_s": duration})  # type: ignore[dict-item]


def test_rejects_nested_and_arbitrary_payloads() -> None:
    with pytest.raises(EventValidationError):
        _build("session_start", {"launch_context": {"nested": "cli_share"}})  # type: ignore[dict-item]
    with pytest.raises(EventValidationError):
        _build(
            "action_failed",
            {"action": "share_analysis", "category": "input", "details": {"e": 1}},
        )


@pytest.mark.parametrize(
    "sensitive_props",
    [
        {"launch_context": "tui", "password": "secret"},
        {"launch_context": "tui", "token": "abc"},
        {"launch_context": "tui", "path": "/ads_storage/alice/data.csv"},
        {"launch_context": "tui", "csv": "peers.csv"},
        {"launch_context": "tui", "exception": "ValueError"},
        {"launch_context": "tui", "entity": "Acme Corp"},
        {"launch_context": "tui", "preset": "default"},
        {"launch_context": "tui", "argv": ["--csv", "x"]},
        {"launch_context": "tui", "env": {"USER": "alice"}},
    ],
)
def test_rejects_sensitive_looking_extra_keys(sensitive_props: dict[str, object]) -> None:
    with pytest.raises(EventValidationError):
        _build("session_start", sensitive_props)


def test_rejects_invalid_username() -> None:
    with pytest.raises(EventValidationError):
        _build("session_start", {"launch_context": "tui"}, user="bad/name")


def test_rejects_non_uuid_session_id_type() -> None:
    with pytest.raises(EventValidationError):
        build_record(
            "session_start",
            {"launch_context": "tui"},
            user=USER,
            session_id="not-a-uuid",  # type: ignore[arg-type]
            app_version=APP_VERSION,
            now=FIXED_NOW,
        )


def test_decode_rejects_invalid_uuid() -> None:
    raw = _build("session_start", {"launch_context": "tui"})
    payload = json.loads(raw.decode("utf-8"))
    payload["session_id"] = "not-a-uuid"
    line = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
    with pytest.raises(EventValidationError):
        decode_record(line)


@pytest.mark.parametrize("version", [0, 4, 99])
def test_decode_rejects_unsupported_schema_version(version: int) -> None:
    raw = _build("session_start", {"launch_context": "tui"})
    payload = json.loads(raw.decode("utf-8"))
    payload["schema_version"] = version
    line = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
    with pytest.raises(UnsupportedSchemaVersion):
        decode_record(line)


def test_writer_emits_current_schema_version_three() -> None:
    # A v1 or v2 reader rejects any other schema_version with a warning
    # instead of silently dropping v3-only values; this bump makes that safe.
    assert SCHEMA_VERSION == 3
    payload = json.loads(_build("action_attempted", {"action": "share_analysis"}))
    assert payload["schema_version"] == 3


def test_session_lifecycle_records_stay_v1_decodable() -> None:
    """session_start/end are unchanged since v1 and are written as v1 so an
    installed v1 reader keeps passing its shared-file gate."""
    assert LEGACY_WRITE_EVENTS == frozenset({"session_start", "session_end"})
    for event, props in (
        ("session_start", {"launch_context": "cli_rate"}),
        ("session_end", {"duration_s": 2.5}),
    ):
        payload = json.loads(_build(event, props))
        assert payload["schema_version"] == 1
        assert events_module._EVENT_SCHEMAS_V1[event] is events_module._EVENT_SCHEMAS_V2[event]
        assert events_module._EVENT_SCHEMAS_V2[event] is events_module._EVENT_SCHEMAS_V3[event]
    for event in set(events_module.event_names()) - LEGACY_WRITE_EVENTS:
        assert record_schema_version(event) == SCHEMA_VERSION


def _legacy_v1_line(event: str, props: dict[str, object]) -> bytes:
    payload = {
        "schema_version": 1,
        "ts": "2026-07-12T22:00:00Z",
        "event": event,
        "user": USER,
        "session_id": str(SESSION_ID),
        "app_version": APP_VERSION,
        "props": props,
    }
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")


@pytest.mark.parametrize(
    ("event", "props"),
    [
        ("session_start", {"launch_context": "tui"}),
        ("surface_viewed", {"surface": "rate"}),
        ("action_completed", {"action": "share_analysis"}),
        ("action_cancelled", {"action": "rate_analysis"}),
        ("action_refused", {"action": "share_analysis", "reason": "compliance_policy"}),
    ],
)
def test_decode_accepts_frozen_v1_records(event: str, props: dict[str, object]) -> None:
    decoded = decode_record(_legacy_v1_line(event, props))
    assert decoded.schema_version == 1
    assert dict(decoded.props) == props


@pytest.mark.parametrize(
    ("event", "props"),
    [
        # v2-only events and values stay invalid inside a v1 record.
        ("launch_blocked", {"action": "share_analysis", "reason": "csv_missing"}),
        ("session_restored", {}),
        ("surface_viewed", {"surface": "advanced"}),
        ("action_completed", {"action": "share_analysis", "publication_withheld": True}),
        ("action_cancelled", {"action": "share_analysis", "prompt": "clearing_spend"}),
    ],
)
def test_decode_v1_record_uses_frozen_v1_catalog(event: str, props: dict[str, object]) -> None:
    with pytest.raises(EventValidationError):
        decode_record(_legacy_v1_line(event, props))


def _legacy_line(version: int, event: str, props: dict[str, object]) -> bytes:
    payload = json.loads(_legacy_v1_line(event, props))
    payload["schema_version"] = version
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")


V3_ONLY_VALUES = [
    ("action_cancelled", {"action": "share_analysis", "prompt": "cancel_before_run"}),
    ("action_cancelled", {"action": "rate_analysis", "prompt": "cancel_during_run"}),
    ("launch_blocked", {"action": "share_analysis", "reason": "entity_not_found"}),
]


@pytest.mark.parametrize(("event", "props"), V3_ONLY_VALUES)
def test_v3_values_decode_only_in_a_v3_record(event: str, props: dict[str, object]) -> None:
    """v3 only adds enum values; the frozen v2 catalog still rejects them."""
    decoded = decode_record(_build(event, props))
    assert decoded.schema_version == 3
    assert dict(decoded.props) == props
    assert decode_record(_legacy_line(3, event, props)).props == props
    with pytest.raises(EventValidationError):
        decode_record(_legacy_line(2, event, props))
    with pytest.raises(EventValidationError):
        decode_record(_legacy_line(1, event, props))


@pytest.mark.parametrize(
    ("event", "props"),
    [
        ("launch_blocked", {"action": "share_analysis", "reason": "csv_missing"}),
        ("action_cancelled", {"action": "share_analysis", "prompt": "quit_during_run"}),
        ("action_completed", {"action": "share_analysis", "publication_withheld": False}),
        ("surface_viewed", {"surface": "advanced"}),
        ("session_restored", {}),
        ("dataset_load", {"outcome": "loaded"}),
    ],
)
def test_frozen_v2_records_still_decode(event: str, props: dict[str, object]) -> None:
    decoded = decode_record(_legacy_line(2, event, props))
    assert decoded.schema_version == 2
    assert dict(decoded.props) == props


def test_v2_catalog_is_frozen_at_its_shipped_values() -> None:
    """The v2 enums keep exactly the values v2 shipped with (05 §8.1)."""
    assert events_module._V2_CANCEL_PROMPTS == (
        "validation_review",
        "accuracy_first_consent",
        "clearing_spend",
        "quit_before_run",
        "quit_during_run",
    )
    assert "entity_not_found" not in events_module._V2_LAUNCH_BLOCK_REASONS
    assert len(events_module._V2_LAUNCH_BLOCK_REASONS) == 9
    assert set(events_module.event_names(2)) == set(events_module.event_names(3))
    for event in events_module.event_names(3):
        assert set(events_module._EVENT_SCHEMAS_V2[event]) == set(events_module._EVENT_SCHEMAS_V3[event])


def test_decode_rejects_malformed_utf8() -> None:
    with pytest.raises(EventValidationError):
        decode_record(b'{"schema_version":1}\xff\n')


def test_decode_rejects_malformed_json() -> None:
    with pytest.raises(EventValidationError):
        decode_record(b"{not-json\n")


def test_decode_rejects_non_object_json() -> None:
    with pytest.raises(EventValidationError):
        decode_record(b"[1,2,3]\n")
    with pytest.raises(EventValidationError):
        decode_record(b'"string"\n')


def test_decode_rejects_embedded_or_multiple_lf() -> None:
    raw = _build("session_start", {"launch_context": "tui"})
    with pytest.raises(EventValidationError):
        decode_record(raw + b"extra\n")
    with pytest.raises(EventValidationError):
        decode_record(b'{"a":1}\n{"b":2}\n')
    # LF embedded inside the JSON text body
    with pytest.raises(EventValidationError):
        decode_record(b'{"schema_version":1,\n"event":"x"}\n')


def test_decode_rejects_oversized_record() -> None:
    oversized = b"x" * (MAX_RECORD_BYTES + 1)
    with pytest.raises(EventValidationError):
        decode_record(oversized)


def test_max_sized_identity_fields_still_fit_record_cap() -> None:
    huge_user = "u" * 128
    raw = _build(
        "session_start",
        {"launch_context": "tui"},
        user=huge_user,
        app_version="v" * MAX_APP_VERSION_BYTES,
    )
    assert len(raw) <= MAX_RECORD_BYTES
    assert decode_record(raw).user == huge_user


@pytest.mark.parametrize(
    "bad_ts",
    [
        "2026-07-12T22:00:00+00:00",
        "2026-07-12 22:00:00Z",
        "2026-07-12T22:00:00",
        "2026-07-12T22:00:00.123456789Z",
        "not-a-timestamp",
        123,
    ],
)
def test_decode_rejects_invalid_timestamps(bad_ts: object) -> None:
    raw = _build("session_start", {"launch_context": "tui"})
    payload = json.loads(raw.decode("utf-8"))
    payload["ts"] = bad_ts
    line = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
    with pytest.raises(EventValidationError):
        decode_record(line)


def test_decode_rejects_unknown_envelope_keys() -> None:
    raw = _build("session_start", {"launch_context": "tui"})
    payload = json.loads(raw.decode("utf-8"))
    payload["extra"] = "nope"
    line = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
    with pytest.raises(EventValidationError):
        decode_record(line)


def test_decode_rejects_missing_envelope_keys() -> None:
    raw = _build("session_start", {"launch_context": "tui"})
    payload = json.loads(raw.decode("utf-8"))
    del payload["user"]
    line = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
    with pytest.raises(EventValidationError):
        decode_record(line)


def test_decode_accepts_reordered_envelope_keys() -> None:
    reordered = {
        "props": {"launch_context": "tui"},
        "app_version": APP_VERSION,
        "session_id": str(SESSION_ID),
        "user": USER,
        "event": "session_start",
        "ts": "2026-07-12T22:00:00Z",
        "schema_version": SCHEMA_VERSION,
    }
    assert tuple(reordered.keys()) != ENVELOPE_KEYS
    assert set(reordered.keys()) == set(ENVELOPE_KEYS)
    line = (json.dumps(reordered, separators=(",", ":")) + "\n").encode("utf-8")
    decoded = decode_record(line)
    assert decoded.event == "session_start"
    assert decoded.user == USER
    assert dict(decoded.props) == {"launch_context": "tui"}


def test_build_rejects_naive_or_non_utc_now() -> None:
    with pytest.raises(EventValidationError):
        _build(
            "session_start",
            {"launch_context": "tui"},
            now=datetime(2026, 7, 12, 22, 0, 0),
        )
    offset = timezone(timedelta(hours=-5))
    with pytest.raises(EventValidationError):
        _build(
            "session_start",
            {"launch_context": "tui"},
            now=datetime(2026, 7, 12, 22, 0, 0, tzinfo=offset),
        )


def test_build_record_keeps_z_for_utc_now() -> None:
    raw = _build(
        "session_start",
        {"launch_context": "tui"},
        now=datetime(2026, 7, 12, 22, 0, 0, 123000, tzinfo=timezone.utc),
    )
    assert json.loads(raw.decode("utf-8"))["ts"].endswith("Z")
    assert "+" not in json.loads(raw.decode("utf-8"))["ts"]


def test_validated_event_is_frozen() -> None:
    raw = _build("session_start", {"launch_context": "tui"})
    decoded = decode_record(raw)
    with pytest.raises(Exception):
        decoded.event = "x"  # type: ignore[misc]


def test_validated_event_props_are_immutable() -> None:
    raw = _build("session_start", {"launch_context": "tui"})
    decoded = decode_record(raw)
    with pytest.raises(TypeError):
        decoded.props["launch_context"] = "cli_share"  # type: ignore[index]


def test_event_validation_error_hierarchy() -> None:
    assert issubclass(EventValidationError, ValueError)
    assert issubclass(UnsupportedSchemaVersion, EventValidationError)


def test_decode_rejects_bool_duration_in_raw_json() -> None:
    raw = _build("session_end", {"duration_s": 1.0})
    payload = json.loads(raw.decode("utf-8"))
    payload["props"] = {"duration_s": True}
    line = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
    with pytest.raises(EventValidationError):
        decode_record(line)


def test_decode_rejects_nan_inf_duration_in_raw_json() -> None:
    for token in ("NaN", "Infinity", "-Infinity"):
        body = (
            '{"schema_version":1,"ts":"2026-07-12T22:00:00Z","event":"session_end",'
            f'"user":"alice","session_id":"{SESSION_ID}","app_version":"3.0",'
            f'"props":{{"duration_s":{token}}}}}\n'
        )
        with pytest.raises(EventValidationError):
            decode_record(body.encode("utf-8"))


def test_decode_accepts_fractional_utc_timestamp() -> None:
    raw = _build("session_start", {"launch_context": "tui"})
    payload = json.loads(raw.decode("utf-8"))
    payload["ts"] = "2026-07-12T22:00:00.123Z"
    line = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
    decoded = decode_record(line)
    assert decoded.ts == datetime(2026, 7, 12, 22, 0, 0, 123000, tzinfo=timezone.utc)
