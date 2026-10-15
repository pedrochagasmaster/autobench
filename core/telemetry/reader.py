"""Safe streaming telemetry source selection, validation, and aggregation."""

from __future__ import annotations

import os
import stat
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path

from core.telemetry.constants import (
    ACTIONS,
    DEFAULT_DAYS,
    DEFAULT_SHARED_DIR,
    FUTURE_SKEW_S,
    MAX_RECORD_BYTES,
    OUTCOMES,
    SHARED_GATE_SCAN_MAX_BYTES,
    SUPPORTED_SCHEMA_VERSIONS,
    SURFACES,
    shared_dir_override,
)
from core.telemetry.events import (
    EventValidationError,
    UnsupportedSchemaVersion,
    ValidatedEvent,
    decode_record,
    require_aware_utc,
)
from core.telemetry.fs_safety import (
    LexicalAbsolutePath,
    TelemetryPath,
    close_quietly,
    combine_open_flags,
    existing_ancestors_are_real_dirs,
    lexical_absolute_path,
)
from core.telemetry.identity import (
    Identity,
    encode_user_token,
    lookup_uid,
    resolve_identity,
    validate_username,
)
from core.telemetry.report import is_run_intent
from core.telemetry.writer import paths_for

_READ_CHUNK = 4096

# None on platforms missing any safe-open flag; reads then fail closed.
_OPEN_FLAGS = combine_open_flags(("O_RDONLY", "O_CLOEXEC", "O_NONBLOCK", "O_NOFOLLOW"))

_OUTCOME_EVENTS = {
    "action_completed": "completed",
    "action_cancelled": "cancelled",
    "action_refused": "refused",
    "action_failed": "failed",
}

# Why a shared users/*.jsonl file was not read (closed; counts only are shown).
SHARED_REJECTION_REASONS = (
    "unreadable",  # symlink, hard link, non-regular file, or open failed
    "no_valid_record",  # no schema-valid record within the gate scan budget
    "name_mismatch",  # filename is not the token of its first record's user
    "unknown_user",  # that user does not resolve through NSS on this host
    "owner_mismatch",  # file owner UID differs from that user's UID (copies)
)

# Why a report fell back to the caller's own private file.
FALLBACK_NO_SHARED_DIR = "no_shared_dir"
FALLBACK_NO_SHARED_FILES = "no_shared_files"
FALLBACK_ALL_SHARED_REJECTED = "all_shared_rejected"


class SourceKind(Enum):
    SHARED = "shared"
    PRIVATE = "private"


@dataclass
class SourceSelection:
    kind: SourceKind
    paths: tuple[TelemetryPath, ...]
    # Set only when kind is PRIVATE: why the shared profile was not used.
    fallback_reason: str | None = None
    # Shared files that failed the gate, counted by SHARED_REJECTION_REASONS.
    rejected: Mapping[str, int] = field(default_factory=dict)
    users_dir: TelemetryPath | None = None


@dataclass(frozen=True)
class WhoRow:
    user: str
    sessions: int
    last_seen: datetime
    completed: int


@dataclass(frozen=True)
class Summary:
    surfaces: Mapping[str, int]
    # Run intents per action (see is_run_intent), not raw action_* events.
    actions: Mapping[str, int]
    outcomes: Mapping[str, int]


@dataclass
class _SkipCounts:
    unsupported_schema: int = 0
    invalid: int = 0

    def add(self, other: "_SkipCounts") -> None:
        self.unsupported_schema += other.unsupported_schema
        self.invalid += other.invalid


def _validate_days(days: int | None) -> int | None:
    if days is None:
        return None
    if isinstance(days, bool) or not isinstance(days, int):
        raise ValueError("days must be a nonnegative integer or None")
    if days < 0:
        raise ValueError("days must be a nonnegative integer or None")
    return days


def _resolve_shared_parent(
    explicit: Path | None,
    environ: Mapping[str, str],
) -> Path:
    """Explicit ``--dir`` wins; a blank env override falls back to the default.

    Unlike the writer (which fails shared writes closed on a blank override),
    reports still have a sensible source: the default shared parent.
    """
    if explicit is not None:
        return explicit
    override = shared_dir_override(environ)
    return override if override is not None else DEFAULT_SHARED_DIR


def _list_shared_jsonl(users_dir: TelemetryPath) -> tuple[TelemetryPath, ...]:
    try:
        names = os.listdir(users_dir)
    except OSError:
        return ()
    paths: list[TelemetryPath] = [
        users_dir / name
        for name in names
        if name.endswith(".jsonl") and "/" not in name and name not in {".", ".."}
    ]
    return tuple(sorted(paths, key=lambda p: p.name))


def _safe_open_regular(path: TelemetryPath) -> tuple[int, os.stat_result] | None:
    """Open ``path`` safely; return (fd, fstat) only for regular singly-linked files."""
    fd: int | None = None
    try:
        if _OPEN_FLAGS is None:
            return None
        try:
            fd = os.open(path, _OPEN_FLAGS)
        except OSError:
            return None
        try:
            st = os.fstat(fd)
        except OSError:
            close_quietly(fd)
            return None
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            close_quietly(fd)
            return None
        return fd, st
    except Exception:
        close_quietly(fd)
        return None


@dataclass
class _LineScanState:
    """Mutable physical-read budget for shared pre-gate scans.

    ``max_read_bytes`` of ``None`` means unlimited (post-gate / private).
    ``bytes_read`` counts every byte returned by ``os.read``, including
    oversized, no-LF, and invalid content.
    """

    max_read_bytes: int | None
    bytes_read: int = 0

    def lift_budget(self) -> None:
        """Remove the read cap mid-iteration (after the shared gate accepts).

        ``_iter_raw_lines`` re-reads this state each chunk, so lifting takes
        effect immediately without dropping already-buffered data.
        """
        self.max_read_bytes = None


class TelemetryReader:
    """Stream and aggregate privacy-aware offline telemetry sources."""

    def __init__(
        self,
        shared_dir: Path | None = None,
        identity: Identity | None = None,
        storage_root: Path = Path("/ads_storage"),
        now: datetime | None = None,
        warn: Callable[[str], None] | None = None,
    ) -> None:
        self._identity = identity if identity is not None else resolve_identity()
        self._storage_root = storage_root
        self._warn = warn if warn is not None else (lambda _msg: None)
        # Capture cwd now so later chdir cannot redirect shared ancestor checks.
        self._shared_parent: LexicalAbsolutePath = lexical_absolute_path(
            _resolve_shared_parent(shared_dir, os.environ)
        )
        if now is None:
            self._now = datetime.now(timezone.utc)
        else:
            # EventValidationError subclasses ValueError, preserving the
            # reader's documented raise type.
            self._now = require_aware_utc(now)
        # Source used by the most recent iter_events call (for report headers).
        self.last_selection: SourceSelection | None = None

    def select_sources(self, *, user: str | None = None) -> SourceSelection:
        token: str | None = None
        if user is not None:
            token = encode_user_token(user)

        users_dir = self._shared_parent / "users"
        dir_ok = existing_ancestors_are_real_dirs(users_dir)
        candidates = _list_shared_jsonl(users_dir) if dir_ok else ()
        qualifying: list[TelemetryPath] = []
        rejected: dict[str, int] = {}
        for path in candidates:
            reason = self._shared_path_rejection(path)
            if reason is None:
                qualifying.append(path)
            else:
                rejected[reason] = rejected.get(reason, 0) + 1

        if qualifying:
            if token is not None:
                wanted = users_dir / f"{token}.jsonl"
                if wanted in qualifying:
                    return SourceSelection(
                        kind=SourceKind.SHARED,
                        paths=(wanted,),
                        rejected=rejected,
                        users_dir=users_dir,
                    )
                # Fleet has expected event files; stay shared-only (no private leak).
                return SourceSelection(
                    kind=SourceKind.SHARED,
                    paths=(),
                    rejected=rejected,
                    users_dir=users_dir,
                )
            return SourceSelection(
                kind=SourceKind.SHARED,
                paths=tuple(qualifying),
                rejected=rejected,
                users_dir=users_dir,
            )

        if not dir_ok or not os.path.isdir(users_dir):
            fallback = FALLBACK_NO_SHARED_DIR
        elif not candidates:
            fallback = FALLBACK_NO_SHARED_FILES
        else:
            fallback = FALLBACK_ALL_SHARED_REJECTED
        paths = paths_for(
            self._identity,
            self._shared_parent,
            storage_root=self._storage_root,
        )
        return SourceSelection(
            kind=SourceKind.PRIVATE,
            paths=(paths.private_file,),
            fallback_reason=fallback,
            rejected=rejected,
            users_dir=users_dir,
        )

    def _shared_path_rejection(self, path: TelemetryPath) -> str | None:
        """None when path is a safe expected shared event file (owner/token
        gate); otherwise the SHARED_REJECTION_REASONS value explaining why."""
        opened = _safe_open_regular(path)
        if opened is None:
            return "unreadable"
        fd, st = opened
        try:
            scan = _LineScanState(max_read_bytes=SHARED_GATE_SCAN_MAX_BYTES)
            first = self._first_schema_valid_event(fd, scan=scan)
            if first is None:
                return "no_valid_record"
            return self._shared_file_rejection(path, first, st.st_uid)
        finally:
            close_quietly(fd)

    def _first_schema_valid_event(
        self,
        fd: int,
        *,
        scan: _LineScanState | None = None,
    ) -> ValidatedEvent | None:
        for raw_line in _iter_raw_lines(fd, scan=scan):
            event = self._try_decode_line(raw_line, _SkipCounts())
            if event is not None:
                return event
        return None

    def _warn_selection(self, selection: SourceSelection) -> None:
        """Make a private fallback or skipped shared files explicit.

        Only the directory the operator chose, closed reason names and counts
        are printed: never a rejected file's name or contents.
        """
        rejected_total = sum(selection.rejected.values())
        detail = ", ".join(
            f"{reason}={selection.rejected[reason]}"
            for reason in SHARED_REJECTION_REASONS
            if selection.rejected.get(reason)
        )
        where = selection.users_dir
        if selection.kind is SourceKind.PRIVATE:
            if selection.fallback_reason == FALLBACK_ALL_SHARED_REJECTED:
                self._warn(
                    f"no shared telemetry file in {where} passed the owner/name "
                    f"check ({rejected_total} rejected: {detail}); reporting only "
                    "your own private telemetry file. Files copied from another "
                    "host fail the owner check: run the report on the node that "
                    "wrote them."
                )
            elif selection.fallback_reason == FALLBACK_NO_SHARED_FILES:
                self._warn(
                    f"no shared telemetry files in {where}; reporting only your "
                    "own private telemetry file."
                )
            else:
                self._warn(
                    f"shared telemetry directory {where} not found or not a real "
                    "directory; reporting only your own private telemetry file."
                )
        elif rejected_total:
            self._warn(
                f"skipped {rejected_total} shared telemetry file(s) in {where} that "
                f"failed the owner/name check ({detail}). Files copied from "
                "another host fail the owner check."
            )

    def _warn_skips(self, skips: _SkipCounts) -> None:
        if skips.unsupported_schema:
            supported = ", ".join(str(v) for v in SUPPORTED_SCHEMA_VERSIONS)
            self._warn(
                f"skipped {skips.unsupported_schema} record(s) with an unsupported "
                f"schema_version (this reader supports {supported}); upgrade "
                "Autobench to read them."
            )
        if skips.invalid:
            self._warn(
                f"skipped {skips.invalid} record(s) that failed schema validation."
            )

    def iter_events(
        self,
        *,
        days: int | None = DEFAULT_DAYS,
        user: str | None = None,
    ) -> Iterator[ValidatedEvent]:
        days = _validate_days(days)
        user_filter: str | None = None
        if user is not None:
            user_filter = validate_username(user)
            encode_user_token(user_filter)

        lower: datetime | None = None
        if days is not None:
            try:
                lower = self._now - timedelta(days=days)
            except OverflowError:
                # A window larger than the representable datetime range bounds
                # nothing; treat it as unlimited instead of crashing.
                lower = None
        upper = self._now + timedelta(seconds=FUTURE_SKEW_S)

        selection = self.select_sources(user=user)
        self.last_selection = selection
        self._warn_selection(selection)
        skips = _SkipCounts()
        for path in selection.paths:
            yield from self._iter_path(
                path,
                kind=selection.kind,
                lower=lower,
                upper=upper,
                user_filter=user_filter,
                skips=skips,
            )
        self._warn_skips(skips)

    def who(self, *, days: int | None = DEFAULT_DAYS) -> list[WhoRow]:
        sessions: dict[str, set[str]] = {}
        last_seen: dict[str, datetime] = {}
        completed: dict[str, int] = {}
        for event in self.iter_events(days=days):
            user = event.user
            if event.event == "session_start":
                sessions.setdefault(user, set()).add(event.session_id)
            prev = last_seen.get(user)
            if prev is None or event.ts > prev:
                last_seen[user] = event.ts
            if event.event == "action_completed":
                completed[user] = completed.get(user, 0) + 1
            else:
                completed.setdefault(user, 0)
            sessions.setdefault(user, set())

        rows = [
            WhoRow(
                user=user,
                sessions=len(sessions.get(user, set())),
                last_seen=last_seen[user],
                completed=completed.get(user, 0),
            )
            for user in sorted(last_seen)
        ]
        return rows

    def summary(
        self,
        *,
        days: int | None = DEFAULT_DAYS,
        user: str | None = None,
    ) -> Summary:
        surfaces = {key: 0 for key in SURFACES}
        actions = {key: 0 for key in ACTIONS}
        outcomes = {key: 0 for key in OUTCOMES}
        for event in self.iter_events(days=days, user=user):
            if event.event == "surface_viewed":
                surface = event.props.get("surface")
                if isinstance(surface, str) and surface in surfaces:
                    surfaces[surface] += 1
            # One count per run intent; outcomes after an attempt are not
            # counted again (the v1 report counted every action_* event).
            if is_run_intent(event):
                action = event.props.get("action")
                if isinstance(action, str) and action in actions:
                    actions[action] += 1
            outcome_key = _OUTCOME_EVENTS.get(event.event)
            if outcome_key is not None:
                outcomes[outcome_key] += 1
        return Summary(surfaces=surfaces, actions=actions, outcomes=outcomes)

    def _iter_path(
        self,
        path: TelemetryPath,
        *,
        kind: SourceKind,
        lower: datetime | None,
        upper: datetime,
        user_filter: str | None,
        skips: _SkipCounts | None = None,
    ) -> Iterator[ValidatedEvent]:
        if skips is None:
            skips = _SkipCounts()
        opened = _safe_open_regular(path)
        if opened is None:
            return
        fd, st = opened
        # Lines skipped before a shared file passes its gate are only reported
        # once the file is accepted, so a rejected file contributes nothing.
        pending = _SkipCounts()
        try:
            if kind is SourceKind.PRIVATE and st.st_uid != self._identity.uid:
                return

            file_uid = st.st_uid
            accepted_user: str | None = None
            gated = False
            # Shared re-gate after reopen/TOCTOU uses the same physical budget;
            # private and post-gate shared streaming are unlimited.
            scan = (
                _LineScanState(max_read_bytes=SHARED_GATE_SCAN_MAX_BYTES)
                if kind is SourceKind.SHARED
                else None
            )

            for raw_line in _iter_raw_lines(fd, scan=scan):
                event = self._try_decode_line(
                    raw_line, pending if kind is SourceKind.SHARED and not gated else skips
                )
                if event is None:
                    continue

                if kind is SourceKind.SHARED:
                    if not gated:
                        if self._shared_file_rejection(path, event, file_uid) is not None:
                            return
                        accepted_user = event.user
                        gated = True
                        skips.add(pending)
                        if scan is not None:
                            scan.lift_budget()
                    elif event.user != accepted_user:
                        continue
                else:
                    if event.user != self._identity.username:
                        continue

                # Date filter after identity/file gate.
                if lower is not None and event.ts < lower:
                    continue
                if event.ts > upper:
                    continue
                if user_filter is not None and event.user != user_filter:
                    continue
                yield event
        finally:
            close_quietly(fd)

    def _shared_file_rejection(
        self, path: TelemetryPath, first: ValidatedEvent, file_uid: int
    ) -> str | None:
        """Owner/token gate: None to accept, else a SHARED_REJECTION_REASONS value."""
        try:
            expected_name = f"{encode_user_token(first.user)}.jsonl"
        except ValueError:
            return "name_mismatch"
        if path.name != expected_name:
            return "name_mismatch"
        try:
            owner_uid = lookup_uid(first.user)
        except Exception:
            return "unknown_user"
        if owner_uid != file_uid:
            return "owner_mismatch"
        return None

    def _try_decode_line(
        self, raw_line: bytes, skips: _SkipCounts
    ) -> ValidatedEvent | None:
        try:
            return decode_record(raw_line)
        except UnsupportedSchemaVersion:
            skips.unsupported_schema += 1
            return None
        except EventValidationError:
            skips.invalid += 1
            return None
        except Exception:
            skips.invalid += 1
            return None


def _iter_raw_lines(
    fd: int, *, scan: _LineScanState | None = None
) -> Iterator[bytes]:
    """Yield LF-terminated raw lines with bounded memory; discard incomplete tail.

    When ``scan.max_read_bytes`` is set, stop once physical ``os.read`` bytes
    reach that budget (counts oversized/no-LF/invalid content). Calling
    ``scan.lift_budget()`` mid-iteration removes the cap without dropping
    already-buffered chunk data.
    """
    buf = bytearray()
    skipping = False
    while True:
        if scan is not None and scan.max_read_bytes is not None:
            remaining = scan.max_read_bytes - scan.bytes_read
            if remaining <= 0:
                return
            to_read = min(_READ_CHUNK, remaining)
        else:
            to_read = _READ_CHUNK
        try:
            chunk = os.read(fd, to_read)
        except InterruptedError:
            continue
        except OSError:
            return
        if not chunk:
            return
        if scan is not None:
            scan.bytes_read += len(chunk)
        offset = 0
        while offset < len(chunk):
            if skipping:
                nl = chunk.find(b"\n", offset)
                if nl < 0:
                    break
                offset = nl + 1
                skipping = False
                buf.clear()
                continue

            nl = chunk.find(b"\n", offset)
            if nl < 0:
                remaining_bytes = chunk[offset:]
                if len(buf) + len(remaining_bytes) >= MAX_RECORD_BYTES:
                    # Would exceed limit even before LF; enter skip mode.
                    skipping = True
                    buf.clear()
                    break
                buf.extend(remaining_bytes)
                break

            piece = chunk[offset : nl + 1]
            if len(buf) + len(piece) > MAX_RECORD_BYTES:
                skipping = False
                buf.clear()
                offset = nl + 1
                continue
            if buf:
                buf.extend(piece)
                line = bytes(buf)
                buf.clear()
            else:
                line = bytes(piece)
            offset = nl + 1
            yield line
