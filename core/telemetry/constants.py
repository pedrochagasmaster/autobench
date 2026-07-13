"""Telemetry numeric limits, environment values, and default paths."""

from __future__ import annotations

from pathlib import Path

SCHEMA_VERSION = 1
MAX_RECORD_BYTES = 8192
SHARED_GATE_SCAN_MAX_BYTES = 64 * 1024
DATA_CAPACITY = 256
PHYSICAL_QUEUE_CAPACITY = DATA_CAPACITY + 2
SHUTDOWN_BUDGET_S = 0.250
FUTURE_SKEW_S = 300
DEFAULT_DAYS = 30
DEFAULT_SHARED_DIR = Path("/ads_storage/autobench/telemetry")
DISABLED_VALUES = frozenset({"0", "false", "off", "no"})
