"""Telemetry limits, environment handling, default paths, and event vocabulary."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

# Records are written at SCHEMA_VERSION. The reader decodes every version in
# SUPPORTED_SCHEMA_VERSIONS, each against its own frozen catalog, and skips
# anything else with one counted warning per report. Any change to an existing
# event's exact prop keys or enum values requires a bump: a v1 reader rejects a
# record whose schema_version is not 1 *with a warning*, whereas it silently
# drops a same-version record that carries an unknown key, value or event.
# session_start/session_end are unchanged since v1 and are still written as
# version 1 (events.LEGACY_WRITE_EVENTS) so v1 readers keep their file gate.
# v3 (TUI layout shell) only adds closed enum values: the visible Cancel
# prompts and the large-entity no-match launch block.
# v4 (TUI verification) only adds one closed enum value: the Citibank entity
# readiness block.
SCHEMA_VERSION = 4
SUPPORTED_SCHEMA_VERSIONS = (1, 2, 3, 4)
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
# share/rate are the TUI tabs (v1). The others (v2) are TUI views that are not
# tabs: the validation review modal, the preset guide and the advanced panel.
SURFACES = ("share", "rate", "validation_review", "preset_help", "advanced")
TAB_SURFACES = ("share", "rate")
ACTIONS = ("share_analysis", "rate_analysis")
REFUSAL_REASONS = ("configuration", "input_validation", "compliance_policy")
FAILURE_CATEGORIES = ("input", "analysis", "output", "unexpected")
OUTCOMES = ("completed", "cancelled", "refused", "failed")

# v2: why the TUI stopped a run before any action_attempted. Each value names a
# fixed form slot or a fixed pre-run stage. None names the selected column,
# file or entity, and none carries an exception message.
LAUNCH_BLOCK_REASONS = (
    "csv_missing",
    "entity_loading",
    "metric_missing",
    "total_missing",
    "rate_column_missing",
    "dimensions_missing",
    "validation_errors",
    "data_preparation_error",
    "initialization_error",
    # v3: the large-entity filter holds text that is not an exact entity.
    "entity_not_found",
    # v4: "A Citi competitor will receive this output" is ticked and no exact
    # Citibank entity is chosen. Core refuses that run (compliance_policy);
    # the TUI now stops it before the attempt.
    "citi_entity_missing",
)
# v2: which prompt the operator declined or left. Every prompt except those in
# IN_RUN_CANCEL_PROMPTS is answered before action_attempted.
CANCEL_PROMPTS = (
    "validation_review",
    "accuracy_first_consent",
    "clearing_spend",
    "quit_before_run",
    "quit_during_run",
    # v3: the visible Cancel (action bar ^G), recorded where the cancel took
    # effect: before action_attempted, or after it (core stopped at a phase
    # boundary with RunCancelled, before any output was written).
    "cancel_before_run",
    "cancel_during_run",
)
IN_RUN_CANCEL_PROMPTS = frozenset({"quit_during_run", "cancel_during_run"})
# v2: outcome of a TUI CSV load (dataset_load).
DATASET_LOAD_OUTCOMES = ("loaded", "not_found", "header_read_failed", "entity_list_failed")
# v2: outcome of an advanced-override panel action (advanced_override).
ADVANCED_OVERRIDE_OUTCOMES = ("applied", "empty", "failed", "exported", "export_failed")


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
