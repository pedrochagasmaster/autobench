"""Read-only friction breakdowns over the validated telemetry stream.

Every function here consumes ``ValidatedEvent`` values that came through
``TelemetryReader.iter_events`` (owner/token gate, strict decoding, date
window) and returns counts keyed only by closed vocabulary values. Nothing
here reads files, and no output carries a username, path or data value.

Funnel semantics (schema v2, also correct on v1 data):

* A **run intent** is one ``action_attempted`` or one pre-attempt terminal:
  ``launch_blocked`` or an ``action_cancelled`` whose prompt is not in
  ``IN_RUN_CANCEL_PROMPTS`` (v1 cancels carry no prompt and were all
  pre-attempt). ``intents = blocked + cancelled_before_run + attempted``.
* Each attempt ends in ``completed``, ``refused``, ``failed`` or a
  ``quit_during_run`` cancel; whatever is left is **open** (the process died,
  or an outcome was dropped at shutdown).
* ``completed`` includes strict runs whose publication was withheld; v2
  records say so with ``publication_withheld``. v1 completions carry no flag
  and are reported as ``unflagged``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from core.telemetry.constants import (
    ACTIONS,
    ADVANCED_OVERRIDE_OUTCOMES,
    CANCEL_PROMPTS,
    DATASET_LOAD_OUTCOMES,
    FAILURE_CATEGORIES,
    IN_RUN_CANCEL_PROMPTS,
    LAUNCH_BLOCK_REASONS,
    LAUNCH_CONTEXTS,
    REFUSAL_REASONS,
    SURFACES,
    TAB_SURFACES,
)
from core.telemetry.events import ValidatedEvent

# Ratios with a denominator below this are flagged (05 §6 rule of thumb 1).
MIN_RATIO_DENOMINATOR = 30
# Row label for v1 cancels, which predate the prompt prop.
UNRECORDED_PROMPT = "unrecorded_v1"
DURATION_BINS: tuple[tuple[float, float | None], ...] = (
    (0, 10),
    (10, 60),
    (60, 300),
    (300, 900),
    (900, 3600),
    (3600, None),
)


@dataclass(frozen=True)
class Session:
    user: str
    session_id: str
    events: tuple[ValidatedEvent, ...]  # sorted by ts

    @property
    def launch_context(self) -> str | None:
        for event in self.events:
            if event.event == "session_start":
                value = event.props.get("launch_context")
                return value if isinstance(value, str) else None
        return None

    @property
    def app_version(self) -> str:
        return self.events[0].app_version

    def first_ts(self, *names: str) -> datetime | None:
        for event in self.events:
            if event.event in names:
                return event.ts
        return None


def group_sessions(events: Iterable[ValidatedEvent]) -> list[Session]:
    grouped: dict[tuple[str, str], list[ValidatedEvent]] = {}
    for event in events:
        grouped.setdefault((event.user, event.session_id), []).append(event)
    return [
        Session(user=user, session_id=sid, events=tuple(sorted(evs, key=lambda e: e.ts)))
        for (user, sid), evs in sorted(grouped.items())
    ]


def filter_sessions(
    sessions: Sequence[Session],
    *,
    context: str | None = None,
    app_version: str | None = None,
) -> list[Session]:
    """Keep sessions by launch context and/or app_version.

    A session whose ``session_start`` fell outside the window has no known
    context and is dropped whenever ``context`` is set.
    """
    kept = []
    for session in sessions:
        if context is not None and session.launch_context != context:
            continue
        if app_version is not None and session.app_version != app_version:
            continue
        kept.append(session)
    return kept


def is_run_intent(event: ValidatedEvent) -> bool:
    """True for the one event that opens each run intent.

    An intent is either an ``action_attempted`` or a terminal that happens
    before any attempt: ``launch_blocked`` or a pre-attempt
    ``action_cancelled``. v1 cancels carry no ``prompt`` and were all
    pre-attempt (validation modal or clearing-spend confirm).
    """
    if event.event in ("action_attempted", "launch_blocked"):
        return True
    if event.event == "action_cancelled":
        return event.props.get("prompt") not in IN_RUN_CANCEL_PROMPTS
    return False


def _events(sessions: Sequence[Session]) -> Iterable[ValidatedEvent]:
    for session in sessions:
        yield from session.events


@dataclass(frozen=True)
class Scope:
    users: int
    sessions: int
    events: int


def scope(sessions: Sequence[Session]) -> Scope:
    return Scope(
        users=len({s.user for s in sessions}),
        sessions=len(sessions),
        events=sum(len(s.events) for s in sessions),
    )


# ---------------------------------------------------------------- funnel


@dataclass(frozen=True)
class FunnelRow:
    action: str
    blocked: int
    cancelled_before_run: int
    attempted: int
    completed: int
    withheld: int
    unflagged: int
    refused: int
    failed: int
    cancelled_during_run: int

    @property
    def intents(self) -> int:
        return self.blocked + self.cancelled_before_run + self.attempted

    @property
    def open(self) -> int:
        ended = self.completed + self.refused + self.failed + self.cancelled_during_run
        return max(0, self.attempted - ended)


def funnel(sessions: Sequence[Session]) -> list[FunnelRow]:
    counts: Counter[tuple[str, str]] = Counter()
    for event in _events(sessions):
        action = event.props.get("action")
        if action not in ACTIONS:
            continue
        name = event.event
        if name == "action_attempted":
            counts[(action, "attempted")] += 1
        elif name == "launch_blocked":
            counts[(action, "blocked")] += 1
        elif name == "action_cancelled":
            if event.props.get("prompt") in IN_RUN_CANCEL_PROMPTS:
                counts[(action, "cancelled_during_run")] += 1
            else:
                counts[(action, "cancelled_before_run")] += 1
        elif name == "action_completed":
            counts[(action, "completed")] += 1
            flag = event.props.get("publication_withheld")
            if flag is True:
                counts[(action, "withheld")] += 1
            elif flag is None:
                counts[(action, "unflagged")] += 1
        elif name == "action_refused":
            counts[(action, "refused")] += 1
        elif name == "action_failed":
            counts[(action, "failed")] += 1
    return [
        FunnelRow(
            action=action,
            blocked=counts[(action, "blocked")],
            cancelled_before_run=counts[(action, "cancelled_before_run")],
            attempted=counts[(action, "attempted")],
            completed=counts[(action, "completed")],
            withheld=counts[(action, "withheld")],
            unflagged=counts[(action, "unflagged")],
            refused=counts[(action, "refused")],
            failed=counts[(action, "failed")],
            cancelled_during_run=counts[(action, "cancelled_during_run")],
        )
        for action in ACTIONS
    ]


# ------------------------------------------------------- reason breakdowns


@dataclass(frozen=True)
class Breakdown:
    """Counts of one closed prop value per action, in vocabulary order."""

    keys: tuple[str, ...]
    counts: Mapping[tuple[str, str], int]  # (key, action) -> count

    def total(self, key: str) -> int:
        return sum(self.counts.get((key, action), 0) for action in ACTIONS)


def _breakdown(
    sessions: Sequence[Session],
    event_name: str,
    prop: str,
    keys: tuple[str, ...],
    *,
    missing_key: str | None = None,
) -> Breakdown:
    counts: Counter[tuple[str, str]] = Counter()
    for event in _events(sessions):
        if event.event != event_name:
            continue
        action = event.props.get("action")
        if action not in ACTIONS:
            continue
        value = event.props.get(prop)
        if value is None and missing_key is not None:
            value = missing_key
        if value in keys:
            counts[(value, action)] += 1
    return Breakdown(keys=keys, counts=dict(counts))


def refusals(sessions: Sequence[Session]) -> Breakdown:
    return _breakdown(sessions, "action_refused", "reason", REFUSAL_REASONS)


def failures(sessions: Sequence[Session]) -> Breakdown:
    return _breakdown(sessions, "action_failed", "category", FAILURE_CATEGORIES)


def launch_blocks(sessions: Sequence[Session]) -> Breakdown:
    return _breakdown(sessions, "launch_blocked", "reason", LAUNCH_BLOCK_REASONS)


def cancels(sessions: Sequence[Session]) -> Breakdown:
    return _breakdown(
        sessions,
        "action_cancelled",
        "prompt",
        CANCEL_PROMPTS + (UNRECORDED_PROMPT,),
        missing_key=UNRECORDED_PROMPT,
    )


# ---------------------------------------------------------------- surfaces


@dataclass(frozen=True)
class SurfaceUsage:
    views: Mapping[str, int]
    tui_sessions: int
    tui_sessions_viewing: Mapping[str, int]
    tui_sessions_both_tabs: int
    launch_contexts: Mapping[str, int]
    unknown_context_sessions: int


def surfaces(sessions: Sequence[Session]) -> SurfaceUsage:
    views = {key: 0 for key in SURFACES}
    for event in _events(sessions):
        if event.event == "surface_viewed":
            surface = event.props.get("surface")
            if surface in views:
                views[surface] += 1
    tui = [s for s in sessions if s.launch_context == "tui"]
    viewing = {key: 0 for key in SURFACES}
    both = 0
    for session in tui:
        seen = {
            e.props.get("surface") for e in session.events if e.event == "surface_viewed"
        }
        for key in SURFACES:
            if key in seen:
                viewing[key] += 1
        if all(tab in seen for tab in TAB_SURFACES):
            both += 1
    contexts = {key: 0 for key in LAUNCH_CONTEXTS}
    unknown = 0
    for session in sessions:
        ctx = session.launch_context
        if ctx in contexts:
            contexts[ctx] += 1
        else:
            unknown += 1
    return SurfaceUsage(
        views=views,
        tui_sessions=len(tui),
        tui_sessions_viewing=viewing,
        tui_sessions_both_tabs=both,
        launch_contexts=contexts,
        unknown_context_sessions=unknown,
    )


# --------------------------------------------------------------- durations


def percentile(values: Sequence[float], pct: float) -> float:
    """Nearest-rank percentile on sorted values (``values`` must be nonempty)."""
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(pct / 100 * (len(ordered) - 1))))
    return ordered[index]


@dataclass(frozen=True)
class DurationStats:
    label: str
    n: int
    p10: float | None = None
    p50: float | None = None
    p90: float | None = None
    max: float | None = None


def _stats(label: str, values: Sequence[float]) -> DurationStats:
    if not values:
        return DurationStats(label=label, n=0)
    return DurationStats(
        label=label,
        n=len(values),
        p10=percentile(values, 10),
        p50=percentile(values, 50),
        p90=percentile(values, 90),
        max=max(values),
    )


def _bin_counts(values: Sequence[float]) -> list[tuple[str, int]]:
    out = []
    for lo, hi in DURATION_BINS:
        label = f"[{lo:g}-{'inf' if hi is None else f'{hi:g}'})s"
        out.append((label, sum(1 for v in values if v >= lo and (hi is None or v < hi))))
    return out


@dataclass(frozen=True)
class Durations:
    rows: tuple[DurationStats, ...]
    histogram: Mapping[str, Sequence[tuple[str, int]]]  # label -> bins
    without_end: int


def _session_durations(session: Session) -> list[float]:
    out = []
    for event in session.events:
        if event.event == "session_end":
            value = event.props.get("duration_s")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                out.append(float(value))
    return out


def durations(sessions: Sequence[Session]) -> Durations:
    by_label: dict[str, list[float]] = {"all": []}
    for ctx in LAUNCH_CONTEXTS:
        by_label[ctx] = []
    without_end = 0
    for session in sessions:
        values = _session_durations(session)
        if not values:
            without_end += 1
        by_label["all"].extend(values)
        ctx = session.launch_context
        if ctx in by_label:
            by_label[ctx].extend(values)
    rows = tuple(_stats(label, values) for label, values in by_label.items())
    histogram = {
        label: _bin_counts(values) for label, values in by_label.items() if values
    }
    return Durations(rows=rows, histogram=histogram, without_end=without_end)


# ------------------------------------------------------- derived friction


@dataclass(frozen=True)
class TimingStats:
    n: int
    p50: float | None
    p90: float | None


def _timing(values: Sequence[float]) -> TimingStats:
    if not values:
        return TimingStats(n=0, p50=None, p90=None)
    return TimingStats(
        n=len(values), p50=percentile(values, 50), p90=percentile(values, 90)
    )


@dataclass(frozen=True)
class Friction:
    tui_sessions: int
    no_intent_sessions: int
    attempt_without_completion_sessions: int
    restored_sessions: int
    time_to_first_intent: TimingStats
    time_to_first_attempt: TimingStats
    time_to_first_completion: TimingStats
    validation_review_dwell: TimingStats
    validation_review_outcomes: Mapping[str, int]
    dataset_loads: Mapping[str, int]
    advanced_overrides: Mapping[str, int]
    recovered_sessions: int
    sessions_with_bad_outcome: int


_BAD_OUTCOMES = frozenset({"action_refused", "action_failed", "launch_blocked", "action_cancelled"})
_REVIEW_EXITS = ("action_attempted", "action_cancelled", "launch_blocked")
REVIEW_OUTCOMES = ("proceeded", "cancelled", "blocked", "no_decision")


def friction(sessions: Sequence[Session]) -> Friction:
    """TUI-only derived metrics (05 §5.2/§6) from the v2 stream."""
    tui = [s for s in sessions if s.launch_context == "tui"]
    no_intent = 0
    no_completion = 0
    restored = 0
    to_intent: list[float] = []
    to_attempt: list[float] = []
    to_completion: list[float] = []
    dwell: list[float] = []
    review = {key: 0 for key in REVIEW_OUTCOMES}
    recovered = 0
    with_bad = 0
    for session in tui:
        start = session.first_ts("session_start")
        intents = [e for e in session.events if is_run_intent(e)]
        if not intents:
            no_intent += 1
        has_attempt = any(e.event == "action_attempted" for e in session.events)
        has_completion = any(e.event == "action_completed" for e in session.events)
        if has_attempt and not has_completion:
            no_completion += 1
        if any(e.event == "session_restored" for e in session.events):
            restored += 1
        if start is not None:
            if intents:
                to_intent.append((intents[0].ts - start).total_seconds())
            first_attempt = session.first_ts("action_attempted")
            if first_attempt is not None:
                to_attempt.append((first_attempt - start).total_seconds())
            first_done = session.first_ts("action_completed")
            if first_done is not None:
                to_completion.append((first_done - start).total_seconds())
        events = session.events
        for index, event in enumerate(events):
            if event.event != "surface_viewed" or event.props.get("surface") != "validation_review":
                continue
            exit_event = next((e for e in events[index + 1 :] if e.event in _REVIEW_EXITS), None)
            if exit_event is None:
                review["no_decision"] += 1
                continue
            dwell.append((exit_event.ts - event.ts).total_seconds())
            if exit_event.event == "action_attempted":
                review["proceeded"] += 1
            elif exit_event.event == "action_cancelled":
                review["cancelled"] += 1
            else:
                review["blocked"] += 1
        bad_seen = False
        for event in events:
            if event.event in _BAD_OUTCOMES:
                bad_seen = True
            elif event.event == "action_completed" and bad_seen:
                recovered += 1
                break
        if bad_seen:
            with_bad += 1
    return Friction(
        tui_sessions=len(tui),
        no_intent_sessions=no_intent,
        attempt_without_completion_sessions=no_completion,
        restored_sessions=restored,
        time_to_first_intent=_timing(to_intent),
        time_to_first_attempt=_timing(to_attempt),
        time_to_first_completion=_timing(to_completion),
        validation_review_dwell=_timing(dwell),
        validation_review_outcomes=review,
        dataset_loads=_value_counts(tui, "dataset_load", DATASET_LOAD_OUTCOMES),
        advanced_overrides=_value_counts(tui, "advanced_override", ADVANCED_OVERRIDE_OUTCOMES),
        recovered_sessions=recovered,
        sessions_with_bad_outcome=with_bad,
    )


def _value_counts(
    sessions: Sequence[Session], event_name: str, keys: tuple[str, ...]
) -> dict[str, int]:
    out = {key: 0 for key in keys}
    for event in _events(sessions):
        if event.event == event_name:
            value = event.props.get("outcome")
            if value in out:
                out[value] += 1
    return out


@dataclass(frozen=True)
class ReportHeader:
    days: int | None
    source: str
    scope: Scope
    filters: Mapping[str, str] = field(default_factory=dict)
