"""Telemetry limits, environment handling, default paths, and event vocabulary."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

SCHEMA_VERSION = 1
MAX_RECORD_BYTES = 8192
SHARED_GATE_SCAN_MAX_BYTES = 64 * 1024
DATA_CAPACITY = 256
PHYSICAL_QUEUE_CAPACITY = DATA_CAPACITY + 2
SHUTDOWN_BUDGET_S = 0.250
FUTURE_SKEW_S = 300
MAX_DURATION_S = 31_536_000
DEFAULT_DAYS = 30
DEFAULT_SHARED_DIR = Path("/ads_storage/autobench/telemetry")

ENV_TELEMETRY = "AUTOBENCH_TELEMETRY"
ENV_TELEMETRY_DIR = "AUTOBENCH_TELEMETRY_DIR"
DISABLED_VALUES = frozenset({"0", "false", "off", "no"})

# Closed event vocabulary: the single source of truth for prop values and
# report ordering. The Literal types in core.telemetry mirror these tuples
# (enforced by test), and the validator frozensets are derived from them.
LAUNCH_CONTEXTS = ("cli_share", "cli_rate", "tui")
SURFACES = ("share", "rate")
ACTIONS = ("share_analysis", "rate_analysis")
REFUSAL_REASONS = ("configuration", "input_validation", "compliance_policy")
FAILURE_CATEGORIES = ("input", "analysis", "output", "unexpected")
OUTCOMES = ("completed", "cancelled", "refused", "failed")


def shared_dir_override(environ: Mapping[str, str]) -> Path | None:
    """Return the ``AUTOBENCH_TELEMETRY_DIR`` override, or None when unusable.

    None covers both "unset" and "present but blank"; callers decide whether
    that means fail-closed (writer) or fall back to the default (reader).
    """
    raw = environ.get(ENV_TELEMETRY_DIR)
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    return Path(stripped)
