"""Offline telemetry package: typed best-effort product helpers only."""

from __future__ import annotations

import logging
import threading
import unicodedata
import uuid
from pathlib import Path
from typing import Literal

from core.telemetry.events import MAX_APP_VERSION_BYTES
from core.telemetry.identity import resolve_identity
from core.telemetry.service import TelemetryService

logger = logging.getLogger(__name__)

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


def start_session(launch_context: LaunchContext) -> None:
    try:
        _get_service().start_session(launch_context)
    except Exception:
        logger.debug("telemetry start_session failed", exc_info=True)


def end_session() -> None:
    try:
        _get_service().end_session()
    except Exception:
        logger.debug("telemetry end_session failed", exc_info=True)


def surface_viewed(surface: Surface) -> None:
    try:
        _get_service().surface_viewed(surface)
    except Exception:
        logger.debug("telemetry surface_viewed failed", exc_info=True)


def action_attempted(action: Action) -> None:
    try:
        _get_service().action_attempted(action)
    except Exception:
        logger.debug("telemetry action_attempted failed", exc_info=True)


def action_completed(action: Action) -> None:
    try:
        _get_service().action_completed(action)
    except Exception:
        logger.debug("telemetry action_completed failed", exc_info=True)


def action_cancelled(action: Action) -> None:
    try:
        _get_service().action_cancelled(action)
    except Exception:
        logger.debug("telemetry action_cancelled failed", exc_info=True)


def action_refused(action: Action, reason: RefuseReason) -> None:
    try:
        _get_service().action_refused(action, reason)
    except Exception:
        logger.debug("telemetry action_refused failed", exc_info=True)


def action_failed(action: Action, category: FailCategory) -> None:
    try:
        _get_service().action_failed(action, category)
    except Exception:
        logger.debug("telemetry action_failed failed", exc_info=True)
