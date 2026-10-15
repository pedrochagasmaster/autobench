"""Closed telemetry event catalog, envelope encoding, and strict decoding."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import Callable, Mapping
from uuid import UUID

from core.telemetry.constants import (
    ACTIONS,
    ADVANCED_OVERRIDE_OUTCOMES,
    CANCEL_PROMPTS,
    DATASET_LOAD_OUTCOMES,
    FAILURE_CATEGORIES,
    LAUNCH_BLOCK_REASONS,
    LAUNCH_CONTEXTS,
    MAX_DURATION_S,
    MAX_RECORD_BYTES,
    REFUSAL_REASONS,
    SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
    SURFACES,
)
from core.telemetry.identity import validate_username

MAX_APP_VERSION_BYTES = 64
_TS_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})T(?P<time>\d{2}:\d{2}:\d{2})"
    r"(?:\.(?P<frac>\d{1,6}))?Z$"
)

_ENVELOPE_KEYS = frozenset(
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


class EventValidationError(ValueError):
    """Raised when a telemetry event or encoded record is invalid."""


class UnsupportedSchemaVersion(EventValidationError):
    """Raised when a record uses an unsupported schema_version."""


@dataclass(frozen=True)
class ValidatedEvent:
    """A decoded record, validated against its own schema_version's catalog.

    ``props`` keeps the shape of that version: a v1 ``action_completed`` has
    no ``publication_withheld`` and a v1 ``action_cancelled`` has no
    ``prompt``. Aggregations read optional v2 keys with ``.get``.
    """

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


def validate_app_version(app_version: str) -> str:
    """Public check for operator-supplied app_version filters (reports)."""
    return _validate_app_version(app_version)


def _validate_duration(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EventValidationError("duration_s must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise EventValidationError("duration_s must be finite")
    if number < 0:
        raise EventValidationError("duration_s out of range")
    rounded = round(number, 3)
    if rounded > MAX_DURATION_S:
        raise EventValidationError("duration_s out of range")
    if rounded == 0:
        return 0.0
    return rounded


_PropValidator = Callable[[object], object]


def _enum_prop(allowed: tuple[str, ...], label: str) -> _PropValidator:
    values = frozenset(allowed)

    def validate(value: object) -> str:
        if not isinstance(value, str) or value not in values:
            raise EventValidationError(f"invalid {label}")
        return value

    return validate


def _bool_prop(label: str) -> _PropValidator:
    def validate(value: object) -> bool:
        # Strictly a JSON boolean: 0/1, "true" or None are rejected.
        if not isinstance(value, bool):
            raise EventValidationError(f"invalid {label}")
        return value

    return validate


_ACTION_PROP = _enum_prop(ACTIONS, "action")

# Frozen v1 catalog (schema_version 1). Never edit it: the reader keeps
# decoding v1 files with exactly these rules.
_V1_SURFACES = ("share", "rate")
# Session lifecycle props are identical in v1 to v4 (same validator objects).
_SESSION_START_PROPS: dict[str, _PropValidator] = {
    "launch_context": _enum_prop(LAUNCH_CONTEXTS, "launch_context")
}
_SESSION_END_PROPS: dict[str, _PropValidator] = {"duration_s": _validate_duration}
_EVENT_SCHEMAS_V1: dict[str, dict[str, _PropValidator]] = {
    "session_start": _SESSION_START_PROPS,
    "session_end": _SESSION_END_PROPS,
    "surface_viewed": {"surface": _enum_prop(_V1_SURFACES, "surface")},
    "action_attempted": {"action": _ACTION_PROP},
    "action_completed": {"action": _ACTION_PROP},
    "action_cancelled": {"action": _ACTION_PROP},
    "action_refused": {
        "action": _ACTION_PROP,
        "reason": _enum_prop(REFUSAL_REASONS, "reason"),
    },
    "action_failed": {
        "action": _ACTION_PROP,
        "category": _enum_prop(FAILURE_CATEGORIES, "category"),
    },
}

# Frozen v2 catalog (schema_version 2). Never edit it: v2 files keep decoding
# with exactly these rules. Every value is a closed enum, a strict boolean, or
# the bounded session duration; there is no free-text field.
_V2_LAUNCH_BLOCK_REASONS = (
    "csv_missing",
    "entity_loading",
    "metric_missing",
    "total_missing",
    "rate_column_missing",
    "dimensions_missing",
    "validation_errors",
    "data_preparation_error",
    "initialization_error",
)
_V2_CANCEL_PROMPTS = (
    "validation_review",
    "accuracy_first_consent",
    "clearing_spend",
    "quit_before_run",
    "quit_during_run",
)
_V2_SURFACES = ("share", "rate", "validation_review", "preset_help", "advanced")
_EVENT_SCHEMAS_V2: dict[str, dict[str, _PropValidator]] = {
    "session_start": _SESSION_START_PROPS,
    "session_end": _SESSION_END_PROPS,
    "session_restored": {},
    "surface_viewed": {"surface": _enum_prop(_V2_SURFACES, "surface")},
    "action_attempted": {"action": _ACTION_PROP},
    "action_completed": {
        "action": _ACTION_PROP,
        "publication_withheld": _bool_prop("publication_withheld"),
    },
    "action_cancelled": {
        "action": _ACTION_PROP,
        "prompt": _enum_prop(_V2_CANCEL_PROMPTS, "prompt"),
    },
    "action_refused": {
        "action": _ACTION_PROP,
        "reason": _enum_prop(REFUSAL_REASONS, "reason"),
    },
    "action_failed": {
        "action": _ACTION_PROP,
        "category": _enum_prop(FAILURE_CATEGORIES, "category"),
    },
    "launch_blocked": {
        "action": _ACTION_PROP,
        "reason": _enum_prop(_V2_LAUNCH_BLOCK_REASONS, "reason"),
    },
    "dataset_load": {"outcome": _enum_prop(DATASET_LOAD_OUTCOMES, "outcome")},
    "advanced_override": {
        "outcome": _enum_prop(ADVANCED_OVERRIDE_OUTCOMES, "outcome")
    },
}

# Frozen v3 catalog (schema_version 3). Never edit it: v3 files keep decoding
# with exactly these rules. Same events and prop keys as v2; two closed enums
# gained values (constants.py, "v3").
_V3_LAUNCH_BLOCK_REASONS = (
    "csv_missing",
    "entity_loading",
    "metric_missing",
    "total_missing",
    "rate_column_missing",
    "dimensions_missing",
    "validation_errors",
    "data_preparation_error",
    "initialization_error",
    "entity_not_found",
)
_V3_CANCEL_PROMPTS = (
    "validation_review",
    "accuracy_first_consent",
    "clearing_spend",
    "quit_before_run",
    "quit_during_run",
    "cancel_before_run",
    "cancel_during_run",
)
_V3_SURFACES = ("share", "rate", "validation_review", "preset_help", "advanced")
_EVENT_SCHEMAS_V3: dict[str, dict[str, _PropValidator]] = {
    "session_start": _SESSION_START_PROPS,
    "session_end": _SESSION_END_PROPS,
    "session_restored": {},
    "surface_viewed": {"surface": _enum_prop(_V3_SURFACES, "surface")},
    "action_attempted": {"action": _ACTION_PROP},
    "action_completed": {
        "action": _ACTION_PROP,
        "publication_withheld": _bool_prop("publication_withheld"),
    },
    "action_cancelled": {
        "action": _ACTION_PROP,
        "prompt": _enum_prop(_V3_CANCEL_PROMPTS, "prompt"),
    },
    "action_refused": {
        "action": _ACTION_PROP,
        "reason": _enum_prop(REFUSAL_REASONS, "reason"),
    },
    "action_failed": {
        "action": _ACTION_PROP,
        "category": _enum_prop(FAILURE_CATEGORIES, "category"),
    },
    "launch_blocked": {
        "action": _ACTION_PROP,
        "reason": _enum_prop(_V3_LAUNCH_BLOCK_REASONS, "reason"),
    },
    "dataset_load": {"outcome": _enum_prop(DATASET_LOAD_OUTCOMES, "outcome")},
    "advanced_override": {
        "outcome": _enum_prop(ADVANCED_OVERRIDE_OUTCOMES, "outcome")
    },
}

# Current catalog (schema_version 4). Same events and prop keys as v3; the
# only change is launch_blocked.reason gaining citi_entity_missing
# (constants.py, "v4").
_EVENT_SCHEMAS_V4: dict[str, dict[str, _PropValidator]] = {
    "session_start": _SESSION_START_PROPS,
    "session_end": _SESSION_END_PROPS,
    "session_restored": {},
    "surface_viewed": {"surface": _enum_prop(SURFACES, "surface")},
    "action_attempted": {"action": _ACTION_PROP},
    "action_completed": {
        "action": _ACTION_PROP,
        "publication_withheld": _bool_prop("publication_withheld"),
    },
    "action_cancelled": {
        "action": _ACTION_PROP,
        "prompt": _enum_prop(CANCEL_PROMPTS, "prompt"),
    },
    "action_refused": {
        "action": _ACTION_PROP,
        "reason": _enum_prop(REFUSAL_REASONS, "reason"),
    },
    "action_failed": {
        "action": _ACTION_PROP,
        "category": _enum_prop(FAILURE_CATEGORIES, "category"),
    },
    "launch_blocked": {
        "action": _ACTION_PROP,
        "reason": _enum_prop(LAUNCH_BLOCK_REASONS, "reason"),
    },
    "dataset_load": {"outcome": _enum_prop(DATASET_LOAD_OUTCOMES, "outcome")},
    "advanced_override": {
        "outcome": _enum_prop(ADVANCED_OVERRIDE_OUTCOMES, "outcome")
    },
}

_EVENT_SCHEMAS_BY_VERSION: dict[int, dict[str, dict[str, _PropValidator]]] = {
    1: _EVENT_SCHEMAS_V1,
    2: _EVENT_SCHEMAS_V2,
    3: _EVENT_SCHEMAS_V3,
    4: _EVENT_SCHEMAS_V4,
}
_EVENT_SCHEMAS = _EVENT_SCHEMAS_BY_VERSION[SCHEMA_VERSION]
if tuple(_EVENT_SCHEMAS_BY_VERSION) != SUPPORTED_SCHEMA_VERSIONS:  # pragma: no cover
    raise RuntimeError("telemetry catalogs must match SUPPORTED_SCHEMA_VERSIONS")

# Events whose schema did not change since v1 keep being *written* as
# schema_version 1, so an installed v1 reader still passes its shared-file
# gate (it needs one v1-valid record) and still counts users and sessions on
# a node that only has new records. Every other event is written at
# SCHEMA_VERSION; a v1 reader skips each of those with a visible warning.
# Only session lifecycle events qualify: writing attempted/refused/failed as v1
# while completed is v2 would make an old reader's funnel inconsistent.
LEGACY_WRITE_EVENTS = frozenset({"session_start", "session_end"})


def record_schema_version(event: str) -> int:
    """schema_version stamped on a newly built record of ``event``."""
    return 1 if event in LEGACY_WRITE_EVENTS else SCHEMA_VERSION


def event_names(schema_version: int = SCHEMA_VERSION) -> tuple[str, ...]:
    """Event names of one supported schema version, in catalog order."""
    return tuple(_EVENT_SCHEMAS_BY_VERSION[schema_version])


def _normalize_props(
    event: str,
    props: Mapping[str, object],
    *,
    schema_version: int = SCHEMA_VERSION,
) -> dict[str, object]:
    schema = _EVENT_SCHEMAS_BY_VERSION[schema_version].get(event)
    if schema is None:
        raise EventValidationError(f"unknown event: {event}")
    props_map = _require_mapping(props, label="props")
    if frozenset(props_map) != frozenset(schema):
        raise EventValidationError(f"props keys must be exactly {sorted(schema)}")
    return {key: validate(props_map[key]) for key, validate in schema.items()}


def require_aware_utc(now: datetime) -> datetime:
    """Validate an already-UTC aware datetime; shared by encoder and reader."""
    if not isinstance(now, datetime):
        raise EventValidationError("now must be a datetime")
    if now.tzinfo is None or now.utcoffset() is None:
        raise EventValidationError("timestamp must be timezone-aware UTC")
    if now.utcoffset() != timedelta(0):
        raise EventValidationError("timestamp must already be UTC with zero offset")
    return now.replace(tzinfo=timezone.utc)


def _format_ts(now: datetime) -> str:
    utc = require_aware_utc(now)
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


def _require_canonical_session_id_text(session_id: object) -> str:
    if not isinstance(session_id, str):
        raise EventValidationError("session_id must be a UUID string")
    try:
        parsed = UUID(session_id)
    except ValueError as exc:
        raise EventValidationError("session_id must be a UUID") from exc
    canonical = str(parsed)
    if session_id != canonical:
        raise EventValidationError("session_id must be canonical lowercase UUID text")
    return canonical


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
        "schema_version": record_schema_version(event),
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
    if frozenset(payload.keys()) != _ENVELOPE_KEYS:
        raise EventValidationError("envelope keys must match the exact contract")

    schema_version = payload["schema_version"]
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise EventValidationError("schema_version must be an integer")
    if schema_version not in _EVENT_SCHEMAS_BY_VERSION:
        raise UnsupportedSchemaVersion(f"unsupported schema_version: {schema_version}")

    ts = _parse_ts(payload["ts"])
    event = payload["event"]
    if not isinstance(event, str):
        raise EventValidationError("event must be a string")

    try:
        user = validate_username(payload["user"])
    except ValueError as exc:
        raise EventValidationError(str(exc)) from exc

    session_id = _require_canonical_session_id_text(payload["session_id"])
    app_version = _validate_app_version(payload["app_version"])
    normalized_props = _normalize_props(
        event, payload["props"], schema_version=schema_version
    )

    return ValidatedEvent(
        schema_version=schema_version,
        ts=ts,
        event=event,
        user=user,
        session_id=session_id,
        app_version=app_version,
        props=MappingProxyType(normalized_props),
    )
