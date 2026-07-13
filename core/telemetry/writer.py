"""Safe private and shared telemetry append writer."""

from __future__ import annotations

import errno
import fcntl
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from core.telemetry.constants import MAX_RECORD_BYTES
from core.telemetry.fs_safety import TelemetryPath, lexical_absolute_path
from core.telemetry.identity import Identity

_OPEN_FLAGS = (
    os.O_APPEND
    | os.O_CREAT
    | os.O_WRONLY
    | os.O_CLOEXEC
    | os.O_NONBLOCK
    | os.O_NOFOLLOW
)
_CREATE_MODE = 0o600
_PRIVATE_DIR_MODE = 0o700
_PRIVATE_FILE_MODE = 0o600
_SHARED_FILE_MODE = 0o644


@dataclass(frozen=True)
class WriterPaths:
    private_file: Path
    shared_users_dir: TelemetryPath


@dataclass(frozen=True)
class AppendResult:
    private_ok: bool
    shared_attempted: bool
    shared_ok: bool


def paths_for(
    identity: Identity,
    shared_dir: TelemetryPath | str | os.PathLike[str],
    *,
    storage_root: Path = Path("/ads_storage"),
) -> WriterPaths:
    private_file = (
        storage_root
        / identity.username
        / ".autobench"
        / "telemetry"
        / "events.jsonl"
    )
    # Same uncollapsed absolute shared path the capability gate inspects.
    shared_abs = lexical_absolute_path(shared_dir)
    shared_users_dir = shared_abs / "users"
    return WriterPaths(private_file=private_file, shared_users_dir=shared_users_dir)


def _validate_record(record: object) -> bool:
    if not isinstance(record, (bytes, bytearray)):
        return False
    data = bytes(record)
    if len(data) > MAX_RECORD_BYTES:
        return False
    if not data.endswith(b"\n"):
        return False
    if b"\n" in data[:-1]:
        return False
    return True


def _ensure_private_parents(path: Path, expected_uid: int) -> bool:
    """Create/normalize ``.autobench`` and ``telemetry`` under an existing home.

    Does not create or chmod ``storage_root/<username>``.
    """
    try:
        telemetry_dir = path.parent
        app_dir = telemetry_dir.parent
        home_dir = app_dir.parent
        if app_dir.name != ".autobench" or telemetry_dir.name != "telemetry":
            return False
        try:
            home_st = os.lstat(home_dir)
        except OSError:
            return False
        if stat.S_ISLNK(home_st.st_mode) or not stat.S_ISDIR(home_st.st_mode):
            return False
        if home_st.st_uid != expected_uid:
            return False
        home_mode = stat.S_IMODE(home_st.st_mode)
        if (home_mode & stat.S_IWOTH) and not (home_mode & stat.S_ISVTX):
            return False

        for directory in (app_dir, telemetry_dir):
            try:
                st = os.lstat(directory)
            except FileNotFoundError:
                try:
                    os.mkdir(directory, _PRIVATE_DIR_MODE)
                except FileExistsError:
                    pass
                except OSError as exc:
                    if exc.errno != errno.EEXIST:
                        return False
                try:
                    st = os.lstat(directory)
                except OSError:
                    return False
            except OSError:
                return False
            if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
                return False
            if st.st_uid != expected_uid:
                return False
            try:
                # Path-based chmod after lstat; follow_symlinks=False avoids
                # chasing a swapped-in symlink (TOCTOU mitigation).
                os.chmod(directory, _PRIVATE_DIR_MODE, follow_symlinks=False)
            except OSError:
                return False
        return True
    except Exception:
        return False


def _close_quiet(fd: int | None) -> None:
    if fd is None:
        return
    try:
        os.close(fd)
    except OSError:
        pass


def _write_all(fd: int, data: bytes) -> bool:
    offset = 0
    length = len(data)
    while offset < length:
        try:
            written = os.write(fd, data[offset:])
        except InterruptedError:
            continue
        except OSError as exc:
            if exc.errno == errno.EINTR:
                continue
            return False
        if written == 0:
            return False
        offset += written
    return True


def append_one(
    path: TelemetryPath,
    record: bytes,
    *,
    expected_uid: int,
    final_mode: int,
    create_private_parents: bool,
) -> bool:
    """Append one validated record to ``path`` using descriptor-based checks.

    Returns False on any ordinary failure and never raises.
    """
    fd: int | None = None
    try:
        if not _validate_record(record):
            return False
        data = bytes(record)

        if create_private_parents:
            # Private parents only apply to pathlib home paths, never lexical shared.
            if not isinstance(path, Path):
                return False
            if not _ensure_private_parents(path, expected_uid):
                return False

        try:
            fd = os.open(path, _OPEN_FLAGS, _CREATE_MODE)
        except OSError:
            return False

        try:
            st = os.fstat(fd)
        except OSError:
            return False
        if not stat.S_ISREG(st.st_mode):
            return False
        if st.st_uid != expected_uid:
            return False
        if st.st_nlink != 1:
            return False

        try:
            os.fchmod(fd, final_mode)
        except OSError:
            return False

        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False

        if not _write_all(fd, data):
            return False
        return True
    except Exception:
        return False
    finally:
        _close_quiet(fd)


def append_record(
    record: bytes,
    *,
    identity: Identity,
    paths: WriterPaths,
    shared_enabled: bool,
) -> AppendResult:
    """Attempt private append and optionally independent shared append."""
    private_ok = append_one(
        paths.private_file,
        record,
        expected_uid=identity.uid,
        final_mode=_PRIVATE_FILE_MODE,
        create_private_parents=True,
    )
    if not shared_enabled:
        return AppendResult(
            private_ok=private_ok, shared_attempted=False, shared_ok=False
        )
    shared_path = paths.shared_users_dir / f"{identity.token}.jsonl"
    shared_ok = append_one(
        shared_path,
        record,
        expected_uid=identity.uid,
        final_mode=_SHARED_FILE_MODE,
        create_private_parents=False,
    )
    return AppendResult(
        private_ok=private_ok, shared_attempted=True, shared_ok=shared_ok
    )
