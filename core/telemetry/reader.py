"""Safe streaming telemetry source selection, validation, and aggregation."""

from __future__ import annotations

import os
import stat
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path

from core.telemetry.constants import (
    DEFAULT_DAYS,
    DEFAULT_SHARED_DIR,
    FUTURE_SKEW_S,
    MAX_RECORD_BYTES,
    SHARED_GATE_SCAN_MAX_BYTES,
)
from core.telemetry.events import (
    EventValidationError,
    UnsupportedSchemaVersion,
    ValidatedEvent,
    decode_record,
)
from core.telemetry.fs_safety import (
    LexicalAbsolutePath,
    TelemetryPath,
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
from core.telemetry.writer import paths_for

_ENV_DIR = "AUTOBENCH_TELEMETRY_DIR"
_READ_CHUNK = 4096

# Require all safe-open flags at import time (AttributeError if any missing).
_OPEN_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK | os.O_NOFOLLOW

_SURFACE_ORDER = ("share", "rate")
_ACTION_ORDER = ("share_analysis", "rate_analysis")
_OUTCOME_ORDER = ("completed", "cancelled", "refused", "failed")
_ACTION_EVENTS = frozenset(
    {
        "action_attempted",
        "action_completed",
        "action_cancelled",
        "action_refused",
        "action_failed",
    }
)
_OUTCOME_EVENTS = {
    "action_completed": "completed",
    "action_cancelled": "cancelled",
    "action_refused": "refused",
    "action_failed": "failed",
}


class SourceKind(Enum):
    SHARED = "shared"
    PRIVATE = "private"


@dataclass
class SourceSelection:
    kind: SourceKind
    paths: tuple[TelemetryPath, ...]


@dataclass(frozen=True)
class WhoRow:
    user: str
    sessions: int
    last_seen: datetime
    completed: int


@dataclass(frozen=True)
class Summary:
    surfaces: Mapping[str, int]
    actions: Mapping[str, int]
    outcomes: Mapping[str, int]


def _require_aware_utc(now: datetime) -> datetime:
    if not isinstance(now, datetime):
        raise ValueError("now must be a datetime")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware UTC")
    if now.utcoffset() != timedelta(0):
        raise ValueError("now must be timezone-aware UTC")
    return now.replace(tzinfo=timezone.utc)


def _validate_days(days: int | None) -> int | None:
    if days is None:
        return None
    if isinstance(days, bool) or not isinstance(days, int):
        raise ValueError("days must be a nonnegative integer or None")
    if days < 0:
        raise ValueError("days must be a nonnegative integer or None")
    return days


def _close_quiet(fd: int | None) -> None:
    if fd is None:
        return
    try:
        os.close(fd)
    except OSError:
        pass


def _resolve_shared_parent(
    explicit: Path | None,
    environ: Mapping[str, str],
) -> Path:
    if explicit is not None:
        return explicit
    raw = environ.get(_ENV_DIR)
    if isinstance(raw, str):
        stripped = raw.strip()
        if stripped:
            return Path(stripped)
    return DEFAULT_SHARED_DIR


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
        try:
            fd = os.open(path, _OPEN_FLAGS)
        except OSError:
            return None
        try:
            st = os.fstat(fd)
        except OSError:
            _close_quiet(fd)
            return None
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            _close_quiet(fd)
            return None
        return fd, st
    except Exception:
        _close_quiet(fd)
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
            self._now = _require_aware_utc(now)

    def select_sources(self, *, user: str | None = None) -> SourceSelection:
        token: str | None = None
        if user is not None:
            token = encode_user_token(user)

        users_dir = self._shared_parent / "users"
        qualifying = self._qualifying_shared_paths(users_dir)

        if qualifying:
            if token is not None:
                wanted = users_dir / f"{token}.jsonl"
                if wanted in qualifying:
                    return SourceSelection(kind=SourceKind.SHARED, paths=(wanted,))
                # Fleet has expected event files; stay shared-only (no private leak).
                return SourceSelection(kind=SourceKind.SHARED, paths=())
            return SourceSelection(kind=SourceKind.SHARED, paths=qualifying)

        paths = paths_for(
            self._identity,
            self._shared_parent,
            storage_root=self._storage_root,
        )
        return SourceSelection(kind=SourceKind.PRIVATE, paths=(paths.private_file,))

    def _qualifying_shared_paths(self, users_dir: TelemetryPath) -> tuple[TelemetryPath, ...]:
        if not existing_ancestors_are_real_dirs(users_dir):
            return ()
        qualified: list[TelemetryPath] = []
        for path in _list_shared_jsonl(users_dir):
            if self._shared_path_qualifies(path):
                qualified.append(path)
        return tuple(qualified)

    def _shared_path_qualifies(self, path: TelemetryPath) -> bool:
        """True when path is a safe expected shared event file (owner/token gate)."""
        opened = _safe_open_regular(path)
        if opened is None:
            return False
        fd, st = opened
        try:
            scan = _LineScanState(max_read_bytes=SHARED_GATE_SCAN_MAX_BYTES)
            first = self._first_schema_valid_event(
                fd, warn_unsupported=False, scan=scan
            )
            if first is None:
                return False
            return self._accept_shared_file(path, first, st.st_uid)
        finally:
            _close_quiet(fd)

    def _first_schema_valid_event(
        self,
        fd: int,
        *,
        warn_unsupported: bool,
        scan: _LineScanState | None = None,
    ) -> ValidatedEvent | None:
        for raw_line in _iter_raw_lines(fd, scan=scan):
            event = self._try_decode_line(raw_line, warn_unsupported=warn_unsupported)
            if event is not None:
                return event
        return None

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
            lower = self._now - timedelta(days=days)
        upper = self._now + timedelta(seconds=FUTURE_SKEW_S)

        selection = self.select_sources(user=user)
        for path in selection.paths:
            yield from self._iter_path(
                path,
                kind=selection.kind,
                lower=lower,
                upper=upper,
                user_filter=user_filter,
            )

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
        surfaces = {key: 0 for key in _SURFACE_ORDER}
        actions = {key: 0 for key in _ACTION_ORDER}
        outcomes = {key: 0 for key in _OUTCOME_ORDER}
        for event in self.iter_events(days=days, user=user):
            if event.event == "surface_viewed":
                surface = event.props.get("surface")
                if isinstance(surface, str) and surface in surfaces:
                    surfaces[surface] += 1
            if event.event in _ACTION_EVENTS:
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
    ) -> Iterator[ValidatedEvent]:
        opened = _safe_open_regular(path)
        if opened is None:
            return
        fd, st = opened
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
                event = self._try_decode_line(raw_line, warn_unsupported=True)
                if event is None:
                    continue

                if kind is SourceKind.SHARED:
                    if not gated:
                        if not self._accept_shared_file(path, event, file_uid):
                            return
                        accepted_user = event.user
                        gated = True
                        # Lift pre-gate budget; keep the same buffered iterator.
                        if scan is not None:
                            scan.max_read_bytes = None
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
            _close_quiet(fd)

    def _accept_shared_file(
        self, path: TelemetryPath, first: ValidatedEvent, file_uid: int
    ) -> bool:
        try:
            expected_name = f"{encode_user_token(first.user)}.jsonl"
        except ValueError:
            return False
        if path.name != expected_name:
            return False
        try:
            owner_uid = lookup_uid(first.user)
        except Exception:
            return False
        return owner_uid == file_uid

    def _try_decode_line(
        self, raw_line: bytes, *, warn_unsupported: bool
    ) -> ValidatedEvent | None:
        try:
            return decode_record(raw_line)
        except UnsupportedSchemaVersion as exc:
            if warn_unsupported:
                self._warn(str(exc))
            return None
        except EventValidationError:
            return None
        except Exception:
            return None

    def _decode_line(self, raw_line: bytes) -> ValidatedEvent | None:
        return self._try_decode_line(raw_line, warn_unsupported=True)


def _iter_raw_lines(
    fd: int, *, scan: _LineScanState | None = None
) -> Iterator[bytes]:
    """Yield LF-terminated raw lines with bounded memory; discard incomplete tail.

    When ``scan.max_read_bytes`` is set, stop once physical ``os.read`` bytes
    reach that budget (counts oversized/no-LF/invalid content). Clearing
    ``scan.max_read_bytes`` to ``None`` mid-iteration lifts the budget without
    dropping already-buffered chunk data.
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
