"""Closed telemetry event catalog, envelope encoding, and strict decoding."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping
from uuid import UUID

from core.telemetry.constants import MAX_RECORD_BYTES, SCHEMA_VERSION
from core.telemetry.identity import validate_username

MAX_APP_VERSION_BYTES = 64
_MAX_DURATION_S = 31_536_000
_TS_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})T(?P<time>\d{2}:\d{2}:\d{2})"
    r"(?:\.(?P<frac>\d{1,6}))?Z$"
)

_ENVELOPE_KEYS = (
    "schema_version",
    "ts",
    "event",
    "user",
    "session_id",
    "app_version",
    "props",
)

_LAUNCH_CONTEXTS = frozenset({"cli_share", "cli_rate", "tui"})
_SURFACES = frozenset({"share", "rate"})
_ACTIONS = frozenset({"share_analysis", "rate_analysis"})
_REFUSAL_REASONS = frozenset({"configuration", "input_validation", "compliance_policy"})
_FAILURE_CATEGORIES = frozenset({"input", "analysis", "output", "unexpected"})

_EVENT_SCHEMAS: dict[str, frozenset[str]] = {
    "session_start": frozenset({"launch_context"}),
    "session_end": frozenset({"duration_s"}),
    "surface_viewed": frozenset({"surface"}),
    "action_attempted": frozenset({"action"}),
    "action_completed": frozenset({"action"}),
    "action_cancelled": frozenset({"action"}),
    "action_refused": frozenset({"action", "reason"}),
    "action_failed": frozenset({"action", "category"}),
}


class EventValidationError(ValueError):
    """Raised when a telemetry event or encoded record is invalid."""


class UnsupportedSchemaVersion(EventValidationError):
    """Raised when a record uses an unsupported schema_version."""


@dataclass(frozen=True)
class ValidatedEvent:
    schema_version: int
    ts: datetime
    event: str
    user: str
    session_id: str
    app_version: str
    props: Mapping[str, object]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_mapping(value: object, *, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or isinstance(value, (str, bytes)):
        raise EventValidationError(f"{label} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise EventValidationError(f"{label} keys must be strings")
    return value


def _validate_app_version(app_version: str) -> str:
    if not isinstance(app_version, str):
        raise EventValidationError("app_version must be a string")
    if not app_version:
        raise EventValidationError("app_version must be nonempty")
    if any(unicodedata.category(ch).startswith("C") for ch in app_version):
        raise EventValidationError("app_version must not contain control characters")
    if len(app_version.encode("utf-8")) > MAX_APP_VERSION_BYTES:
        raise EventValidationError(
            f"app_version must be at most {MAX_APP_VERSION_BYTES} UTF-8 bytes"
        )
    return app_version


def _validate_enum(value: object, allowed: frozenset[str], *, label: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise EventValidationError(f"invalid {label}")
    return value


def _validate_duration(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EventValidationError("duration_s must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise EventValidationError("duration_s must be finite")
    rounded = round(number, 3)
    if rounded < 0 or rounded > _MAX_DURATION_S:
        raise EventValidationError("duration_s out of range")
    return rounded


def _normalize_props(event: str, props: Mapping[str, object]) -> dict[str, object]:
    if event not in _EVENT_SCHEMAS:
        raise EventValidationError(f"unknown event: {event}")
    props_map = _require_mapping(props, label="props")
    expected = _EVENT_SCHEMAS[event]
    keys = frozenset(props_map)
    if keys != expected:
        raise EventValidationError(f"props keys must be exactly {sorted(expected)}")

    if event == "session_start":
        return {
            "launch_context": _validate_enum(
                props_map["launch_context"], _LAUNCH_CONTEXTS, label="launch_context"
            )
        }
    if event == "session_end":
        return {"duration_s": _validate_duration(props_map["duration_s"])}
    if event == "surface_viewed":
        return {"surface": _validate_enum(props_map["surface"], _SURFACES, label="surface")}
    if event in {"action_attempted", "action_completed", "action_cancelled"}:
        return {"action": _validate_enum(props_map["action"], _ACTIONS, label="action")}
    if event == "action_refused":
        return {
            "action": _validate_enum(props_map["action"], _ACTIONS, label="action"),
            "reason": _validate_enum(props_map["reason"], _REFUSAL_REASONS, label="reason"),
        }
    if event == "action_failed":
        return {
            "action": _validate_enum(props_map["action"], _ACTIONS, label="action"),
            "category": _validate_enum(
                props_map["category"], _FAILURE_CATEGORIES, label="category"
            ),
        }
    raise EventValidationError(f"unknown event: {event}")


def _require_aware_utc(now: datetime) -> datetime:
    if not isinstance(now, datetime):
        raise EventValidationError("now must be a datetime")
    if now.tzinfo is None or now.utcoffset() is None:
        raise EventValidationError("timestamp must be timezone-aware UTC")
    utc = now.astimezone(timezone.utc)
    if utc.utcoffset() != timezone.utc.utcoffset(utc):
        raise EventValidationError("timestamp must be UTC")
    return utc


def _format_ts(now: datetime) -> str:
    utc = _require_aware_utc(now)
    if utc.microsecond:
        return utc.strftime("%Y-%m-%dT%H:%M:%S.%f").rstrip("0").rstrip(".") + "Z"
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(value: object) -> datetime:
    if not isinstance(value, str):
        raise EventValidationError("ts must be a string")
    match = _TS_RE.fullmatch(value)
    if match is None:
        raise EventValidationError("ts must be strict ISO UTC ending in Z")
    frac = match.group("frac")
    if frac is None:
        microsecond = 0
    else:
        microsecond = int(frac.ljust(6, "0"))
    try:
        return datetime(
            int(value[0:4]),
            int(value[5:7]),
            int(value[8:10]),
            int(value[11:13]),
            int(value[14:16]),
            int(value[17:19]),
            microsecond,
            tzinfo=timezone.utc,
        )
    except ValueError as exc:
        raise EventValidationError("ts is not a valid timestamp") from exc


def _require_session_id(session_id: object) -> UUID:
    if isinstance(session_id, UUID):
        return session_id
    if isinstance(session_id, str):
        try:
            return UUID(session_id)
        except ValueError as exc:
            raise EventValidationError("session_id must be a UUID") from exc
    raise EventValidationError("session_id must be a UUID")


def build_record(
    event: str,
    props: Mapping[str, object],
    *,
    user: str,
    session_id: UUID,
    app_version: str,
    now: datetime | None = None,
) -> bytes:
    if not isinstance(event, str):
        raise EventValidationError("event must be a string")
    if not isinstance(session_id, UUID):
        raise EventValidationError("session_id must be a UUID")
    try:
        validated_user = validate_username(user)
    except ValueError as exc:
        raise EventValidationError(str(exc)) from exc
    validated_version = _validate_app_version(app_version)
    normalized_props = _normalize_props(event, props)
    ts = _format_ts(_utc_now() if now is None else now)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "ts": ts,
        "event": event,
        "user": validated_user,
        "session_id": str(session_id),
        "app_version": validated_version,
        "props": normalized_props,
    }
    try:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise EventValidationError("event payload is not JSON-serializable") from exc
    raw = (body + "\n").encode("utf-8")
    if len(raw) > MAX_RECORD_BYTES:
        raise EventValidationError("encoded record exceeds MAX_RECORD_BYTES")
    return raw


def _reject_nonfinite_json_constant(token: str) -> object:
    raise EventValidationError(f"non-finite JSON number: {token}")


def decode_record(raw_line: bytes) -> ValidatedEvent:
    if not isinstance(raw_line, (bytes, bytearray)):
        raise EventValidationError("raw_line must be bytes")
    raw = bytes(raw_line)
    if len(raw) > MAX_RECORD_BYTES:
        raise EventValidationError("encoded record exceeds MAX_RECORD_BYTES")
    if raw.count(b"\n") > 1:
        raise EventValidationError("record must not contain embedded or multiple LF")
    if raw.endswith(b"\n"):
        raw = raw[:-1]
    if b"\n" in raw:
        raise EventValidationError("record must not contain embedded LF")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EventValidationError("record is not valid UTF-8") from exc
    try:
        payload = json.loads(text, parse_constant=_reject_nonfinite_json_constant)
    except EventValidationError:
        raise
    except json.JSONDecodeError as exc:
        raise EventValidationError("record is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise EventValidationError("record JSON must be an object")
    if tuple(payload.keys()) != _ENVELOPE_KEYS:
        raise EventValidationError("envelope keys must match the exact contract")

    schema_version = payload["schema_version"]
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise EventValidationError("schema_version must be an integer")
    if schema_version != SCHEMA_VERSION:
        raise UnsupportedSchemaVersion(f"unsupported schema_version: {schema_version}")

    ts = _parse_ts(payload["ts"])
    event = payload["event"]
    if not isinstance(event, str):
        raise EventValidationError("event must be a string")

    try:
        user = validate_username(payload["user"])
    except ValueError as exc:
        raise EventValidationError(str(exc)) from exc

    session_uuid = _require_session_id(payload["session_id"])
    app_version = _validate_app_version(payload["app_version"])
    normalized_props = _normalize_props(event, payload["props"])

    return ValidatedEvent(
        schema_version=schema_version,
        ts=ts,
        event=event,
        user=user,
        session_id=str(session_uuid),
        app_version=app_version,
        props=normalized_props,
    )
