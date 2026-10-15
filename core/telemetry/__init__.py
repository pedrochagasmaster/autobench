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
Surface = Literal["share", "rate", "validation_review", "preset_help", "advanced"]
Action = Literal["share_analysis", "rate_analysis"]
RefuseReason = Literal["configuration", "input_validation", "compliance_policy"]
FailCategory = Literal["input", "analysis", "output", "unexpected"]
LaunchBlockReason = Literal[
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
    "citi_entity_missing",
]
CancelPrompt = Literal[
    "validation_review",
    "accuracy_first_consent",
    "clearing_spend",
    "quit_before_run",
    "quit_during_run",
    "cancel_before_run",
    "cancel_during_run",
]
DatasetLoadOutcome = Literal["loaded", "not_found", "header_read_failed", "entity_list_failed"]
AdvancedOverrideOutcome = Literal["applied", "empty", "failed", "exported", "export_failed"]

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


def action_completed(action: Action, publication_withheld: bool) -> None:
    """Record a completed run; ``publication_withheld`` is True when a strict
    posture wrote only the analysis workbook and withheld publication."""
    _run_safely(
        "action_completed",
        lambda s: s.action_completed(action, publication_withheld),
    )


def action_cancelled(action: Action, prompt: CancelPrompt) -> None:
    """Record the operator declining ``prompt``; see ``CANCEL_PROMPTS``."""
    _run_safely("action_cancelled", lambda s: s.action_cancelled(action, prompt))


def launch_blocked(action: Action, reason: LaunchBlockReason) -> None:
    """Record the TUI stopping a run before ``action_attempted``."""
    _run_safely("launch_blocked", lambda s: s.launch_blocked(action, reason))


def dataset_load(outcome: DatasetLoadOutcome) -> None:
    _run_safely("dataset_load", lambda s: s.dataset_load(outcome))


def advanced_override(outcome: AdvancedOverrideOutcome) -> None:
    _run_safely("advanced_override", lambda s: s.advanced_override(outcome))


def session_restored() -> None:
    _run_safely("session_restored", lambda s: s.session_restored())


def action_refused(action: Action, reason: RefuseReason) -> None:
    _run_safely("action_refused", lambda s: s.action_refused(action, reason))


def action_failed(action: Action, category: FailCategory) -> None:
    _run_safely("action_failed", lambda s: s.action_failed(action, category))
