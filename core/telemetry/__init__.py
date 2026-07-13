"""Offline telemetry package: typed best-effort product helpers only."""

from __future__ import annotations

import logging
import threading
import unicodedata
import uuid
from pathlib import Path
from typing import Callable, Literal

from core.telemetry.events import MAX_APP_VERSION_BYTES
from core.telemetry.identity import resolve_identity
from core.telemetry.service import TelemetryService

logger = logging.getLogger(__name__)

# Static mirrors of the canonical vocabulary tuples in
# core.telemetry.constants (Literal needs literal strings); a test asserts
# they stay identical.
LaunchContext = Literal["cli_share", "cli_rate", "tui"]
Surface = Literal["share", "rate"]
Action = Literal["share_analysis", "rate_analysis"]
RefuseReason = Literal["configuration", "input_validation", "compliance_policy"]
FailCategory = Literal["input", "analysis", "output", "unexpected"]

_FALLBACK_VERSION = "0"
_VERSION_PATH = Path(__file__).resolve().parents[2] / "VERSION"

_service: TelemetryService | None = None
_service_lock = threading.Lock()


def _read_app_version() -> str:
    try:
        text = _VERSION_PATH.read_text(encoding="utf-8").strip()
        if not text:
            return _FALLBACK_VERSION
        if len(text.encode("utf-8")) > MAX_APP_VERSION_BYTES:
            return _FALLBACK_VERSION
        # Match _validate_app_version's category-C rejection (DEL, C1, format
        # chars); a weaker check here would make every build_record fail
        # instead of falling back.
        if any(unicodedata.category(ch).startswith("C") for ch in text):
            return _FALLBACK_VERSION
        return text
    except Exception:
        return _FALLBACK_VERSION


# Captured once at import so helpers do not re-read VERSION.
_APP_VERSION = _read_app_version()


def _build_default_service() -> TelemetryService:
    return TelemetryService(
        identity=resolve_identity(),
        session_id=uuid.uuid4(),
        app_version=_APP_VERSION,
    )


def _get_service() -> TelemetryService:
    global _service
    with _service_lock:
        if _service is None:
            _service = _build_default_service()
        return _service


def _reset_for_tests(service: TelemetryService | None = None) -> None:
    """Close and replace the process singleton (test helper)."""
    global _service
    with _service_lock:
        previous = _service
        _service = service
    if previous is not None and previous is not service:
        try:
            previous.shutdown()
        except Exception:
            logger.debug("telemetry reset shutdown failed", exc_info=True)


def _run_safely(
    operation: str,
    callback: Callable[[TelemetryService], None],
) -> None:
    try:
        callback(_get_service())
    except Exception:
        logger.debug("telemetry %s failed", operation, exc_info=True)


def start_session(launch_context: LaunchContext) -> None:
    _run_safely("start_session", lambda s: s.start_session(launch_context))


def end_session() -> None:
    _run_safely("end_session", lambda s: s.end_session())


def surface_viewed(surface: Surface) -> None:
    _run_safely("surface_viewed", lambda s: s.surface_viewed(surface))


def action_attempted(action: Action) -> None:
    _run_safely("action_attempted", lambda s: s.action_attempted(action))


def action_completed(action: Action) -> None:
    _run_safely("action_completed", lambda s: s.action_completed(action))


def action_cancelled(action: Action) -> None:
    _run_safely("action_cancelled", lambda s: s.action_cancelled(action))


def action_refused(action: Action, reason: RefuseReason) -> None:
    _run_safely("action_refused", lambda s: s.action_refused(action, reason))


def action_failed(action: Action, category: FailCategory) -> None:
    _run_safely("action_failed", lambda s: s.action_failed(action, category))
