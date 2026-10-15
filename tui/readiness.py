"""Run readiness: the TUI launch guards as one pure function (Phase 2 PR 4).

``launch_blockers`` is the single source of the pre-run checks. The analysis
worker uses it to refuse a launch (``BenchmarkApp._fail_launch``) and the UI
uses the same function, on the same ``RunInputs`` snapshot shape, for the
action bar, the step rail and the Review step. Messages and closed telemetry
reasons are exactly today's guards; nothing here touches ``core/``. PR 6
added the Citibank entity check (``citi_entity_missing``, schema v4): the
same condition core refuses, caught before the attempt instead of inside it.

Consent and the clearing-spend attestation are not blockers: they are asked
per run attempt, after these checks pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Tuple


@dataclass(frozen=True)
class LaunchBlocker:
    """One reason the form cannot run yet."""

    message: str
    # Widget id that fixes it (Ctrl+R focuses it, which also shows its step).
    focus_id: str
    # Closed ``LAUNCH_BLOCK_REASONS`` value recorded as launch_blocked.
    reason: str


def launch_blockers(inputs: Any) -> Tuple[LaunchBlocker, ...]:
    """Every launch guard that fails for ``inputs``, in the order they are checked.

    ``inputs`` is a ``tui_app.RunInputs`` (or any object with the same
    attribute names). The first blocker is the one a launch reports.
    """
    found = []
    if not inputs.csv_path:
        found.append(LaunchBlocker("CSV path is required.", "csv_path", "csv_missing"))
    if inputs.entity_selection_pending:
        # The operator's target entity is cleared while the values reload and
        # is re-applied when they land; launching now would silently run
        # peer-only instead.
        found.append(
            LaunchBlocker(
                "Target entity values are still loading; wait for the list to finish.",
                "entity_name",
                "entity_loading",
            )
        )
    if inputs.entity_error:
        # Large-list picker: typed text that is not an exact entity must never
        # silently become a peer-only run (03 §6).
        found.append(LaunchBlocker(inputs.entity_error, "entity_filter", "entity_not_found"))
    if inputs.mode == "share":
        if not inputs.metric:
            found.append(
                LaunchBlocker(
                    "Primary metric is required for share analysis.", "share_metric", "metric_missing"
                )
            )
    else:
        if not inputs.total_col:
            found.append(
                LaunchBlocker("Total column is required for rate analysis.", "rate_total", "total_missing")
            )
        if not inputs.approved_col and not inputs.fraud_col:
            found.append(
                LaunchBlocker(
                    "At least one rate column (approved or fraud) is required.",
                    "rate_approved",
                    "rate_column_missing",
                )
            )
    if not inputs.auto and not inputs.dimensions:
        found.append(
            LaunchBlocker(
                "Select at least one dimension or enable auto-detect.",
                # One dimensions list for both modes (PR 5, 01 §2.2).
                "dims",
                "dimensions_missing",
            )
        )
    privacy = dict(inputs.privacy_values)
    if privacy.get("citi_competitor_receives_output") and not privacy.get("citibank_entity_name"):
        # The same condition core refuses (compliance_policy) once the run
        # has started; checked here so it is a readiness item instead.
        found.append(
            LaunchBlocker(
                "Choose the Citibank entity, or untick “A Citi competitor will receive this output”.",
                "citibank_entity_filter" if getattr(inputs, "entity_large_list", False) else "citibank_entity_name",
                "citi_entity_missing",
            )
        )
    return tuple(found)


def first_blocker(inputs: Any) -> Optional[LaunchBlocker]:
    blockers = launch_blockers(inputs)
    return blockers[0] if blockers else None
