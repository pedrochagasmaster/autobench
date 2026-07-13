#!/usr/bin/env python3
"""Operator validator for shared Autobench telemetry filesystem guarantees.

Noninteractive and automation-friendly. Creates temporary probe entries only
under the sticky ``users`` directory, never reads telemetry payloads, and exits
nonzero when any required guarantee fails.

Cross-user sticky deletion requires a separate two-account operational check;
this script does not exercise it.
"""

from __future__ import annotations

import argparse
import errno
import fcntl
import os
import secrets
import signal
import stat
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.telemetry.fs_safety import existing_ancestors_are_real_dirs  # noqa: E402

DEFAULT_PARENT = Path("/ads_storage/autobench/telemetry")
DEFAULT_PROTECTED_HARDLINKS = Path("/proc/sys/fs/protected_hardlinks")
PARENT_MODE = 0o0755
USERS_MODE = 0o1777
PROBE_CREATE_MODE = 0o0600
PROBE_FINAL_MODE = 0o0644
CHILD_TIMEOUT_S = 2.0
CHILD_KILL_WAIT_S = 0.5
_REQUIRED_OS_FLAGS = (
    "O_APPEND",
    "O_NOFOLLOW",
    "O_NONBLOCK",
    "O_CLOEXEC",
    "O_CREAT",
    "O_EXCL",
)
_REQUIRED_FCNTL = ("flock", "LOCK_EX", "LOCK_NB", "LOCK_UN")
_INTERNAL_LOCK = "lock-contend"
_INTERNAL_FIFO = "fifo-open"


class InvalidTelemetryDirError(ValueError):
    """Operator --dir / telemetry parent path violates the absolute path policy."""


def normalize_operator_telemetry_dir(raw: str | os.PathLike[str]) -> Path:
    """Validate operator telemetry parent path before any filesystem probe.

    Preserves the raw string long enough to detect lexical ``.`` / ``..``
    components (``pathlib.Path`` may otherwise obscure them). Strips one or more
    trailing slashes while preserving a lone ``/``, collapses repeated internal
    slashes, requires an absolute non-root path, and returns a ``Path``.
    """
    text = os.fsdecode(raw)
    while len(text) > 1 and text.endswith("/"):
        text = text[:-1]

    if text == "":
        raise InvalidTelemetryDirError(
            "telemetry --dir is empty (refusing unsafe root)"
        )
    if text == ".":
        raise InvalidTelemetryDirError(
            "telemetry --dir is '.' (refusing unsafe root)"
        )
    if text == "/":
        raise InvalidTelemetryDirError(
            "telemetry --dir is '/' (refusing unsafe root)"
        )
    if not text.startswith("/"):
        raise InvalidTelemetryDirError(
            f"telemetry --dir must be an absolute path (refusing): {text}"
        )

    components = text.split("/")
    for comp in components:
        if comp in (".", ".."):
            raise InvalidTelemetryDirError(
                f"telemetry --dir contains a '.' or '..' dot component (refusing): {text}"
            )

    cleaned = "/" + "/".join(comp for comp in components if comp)
    if cleaned == "/":
        raise InvalidTelemetryDirError(
            "telemetry --dir is '/' (refusing unsafe root)"
        )
    return Path(cleaned)


def _pass(lines: List[str], message: str) -> None:
    lines.append(f"PASS: {message}")


def _fail(lines: List[str], message: str) -> None:
    lines.append(f"FAIL: {message}")


def _probe_name(prefix: str) -> str:
    return f".ab-telem-{prefix}-{secrets.token_hex(16)}"


def _close_fd(fd: Optional[int]) -> None:
    if fd is None:
        return
    try:
        os.close(fd)
    except OSError:
        pass


def _unlink_owned(path: Path, euid: int) -> None:
    try:
        st = os.lstat(path)
    except OSError:
        return
    if st.st_uid != euid:
        return
    try:
        os.unlink(path)
    except OSError:
        pass


def _owned_non_symlink_dir(
    path: Path, euid: int, expected_mode: int, label: str, lines: List[str]
) -> bool:
    try:
        st = os.lstat(path)
    except OSError as exc:
        _fail(lines, f"{label} missing or unreadable: {exc.strerror}")
        return False
    if stat.S_ISLNK(st.st_mode):
        _fail(lines, f"{label} must be a real directory, not a symlink: {path}")
        return False
    if not stat.S_ISDIR(st.st_mode):
        _fail(lines, f"{label} must be a directory: {path}")
        return False
    if st.st_uid != euid:
        _fail(
            lines,
            f"{label} owner uid {st.st_uid} != trusted euid {euid}: {path}",
        )
        return False
    mode = stat.S_IMODE(st.st_mode)
    if mode != expected_mode:
        _fail(
            lines,
            f"{label} mode {mode:04o} != required {expected_mode:04o}: {path}",
        )
        return False
    _pass(lines, f"{label} real dir mode {mode:04o} owned by euid {euid}")
    return True


def _check_platform(lines: List[str]) -> bool:
    if sys.platform != "linux":
        _fail(lines, f"Linux required, got platform={sys.platform!r}")
        return False
    _pass(lines, "Linux platform")
    return True


def _check_primitives(lines: List[str]) -> bool:
    missing_os = [name for name in _REQUIRED_OS_FLAGS if not hasattr(os, name)]
    missing_fcntl = [name for name in _REQUIRED_FCNTL if not hasattr(fcntl, name)]
    if missing_os or missing_fcntl:
        parts = []
        if missing_os:
            parts.append("os." + ",".join(missing_os))
        if missing_fcntl:
            parts.append("fcntl." + ",".join(missing_fcntl))
        _fail(lines, "missing primitives: " + "; ".join(parts))
        return False
    _pass(lines, "O_APPEND/O_NOFOLLOW/O_NONBLOCK/O_CLOEXEC and flock NB available")
    return True


def _check_protected_hardlinks(path: Path, lines: List[str]) -> bool:
    try:
        raw = path.read_text(encoding="ascii")
    except OSError as exc:
        _fail(lines, f"protected_hardlinks unreadable at {path}: {exc.strerror}")
        return False
    if raw.strip() != "1":
        _fail(
            lines,
            f"protected_hardlinks must be exactly 1 at {path}, got {raw.strip()!r}",
        )
        return False
    _pass(lines, f"protected_hardlinks == 1 ({path})")
    return True


def _child_try_lock(path_str: str) -> int:
    fd = None
    try:
        fd = os.open(
            path_str,
            os.O_RDWR | os.O_CLOEXEC | os.O_NONBLOCK | os.O_NOFOLLOW,
        )
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            print(f"busy:{exc.errno}")
            return 0
        print("locked:0")
        return 0
    except Exception as exc:  # noqa: BLE001 - child reports any failure
        print(f"error:{exc}")
        return 1
    finally:
        _close_fd(fd)


def _child_fifo_open(path_str: str) -> int:
    fd = None
    try:
        fd = os.open(
            path_str,
            os.O_WRONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW,
        )
        print("opened:0")
        return 0
    except OSError as exc:
        # ENXIO is the expected nonblocking open-for-write without a reader.
        print(f"errno:{exc.errno}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"error:{exc}")
        return 1
    finally:
        _close_fd(fd)


def _close_pipe(pipe: Optional[object]) -> None:
    if pipe is None:
        return
    close = getattr(pipe, "close", None)
    if close is None:
        return
    try:
        close()
    except OSError:
        pass


def _run_internal_child(
    mode: str, path: Path, timeout_s: float = CHILD_TIMEOUT_S
) -> Tuple[str, object]:
    script = Path(__file__).resolve()
    proc = subprocess.Popen(
        [sys.executable, str(script), "--internal-child", mode, str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, _stderr = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            try:
                proc.kill()
            except OSError:
                pass
        try:
            proc.communicate(timeout=CHILD_KILL_WAIT_S)
        except subprocess.TimeoutExpired:
            # Stubborn/uninterruptible child: close pipes and fail without an
            # unbounded wait or context-manager destructor hang.
            _close_pipe(proc.stdout)
            _close_pipe(proc.stderr)
            return ("timeout", None)
        return ("timeout", None)

    raw = (stdout or "").strip().splitlines()
    if not raw:
        return ("empty", proc.returncode)
    status, _, detail = raw[-1].partition(":")
    if status in {"busy", "errno"}:
        try:
            return (status, int(detail))
        except ValueError:
            return (status, detail)
    if status in {"locked", "opened"}:
        return (status, 0)
    if status == "error":
        return ("error", detail)
    return (status or "empty", detail)


def _run_lock_child(path: Path, timeout_s: float = CHILD_TIMEOUT_S) -> Tuple[str, object]:
    return _run_internal_child(_INTERNAL_LOCK, path, timeout_s)


def _run_fifo_child(path: Path, timeout_s: float = CHILD_TIMEOUT_S) -> Tuple[str, object]:
    return _run_internal_child(_INTERNAL_FIFO, path, timeout_s)


def _probe_file_ops(
    users_dir: Path,
    euid: int,
    lines: List[str],
) -> bool:
    """Create owned probes and validate append/lock/nofollow/rename/fifo."""
    owned: List[Path] = []
    fds: List[int] = []
    ok = True

    def track(path: Path) -> Path:
        owned.append(path)
        return path

    try:
        name = _probe_name("file")
        path = track(users_dir / name)
        flags = (
            os.O_CREAT
            | os.O_EXCL
            | os.O_NOFOLLOW
            | os.O_CLOEXEC
            | os.O_NONBLOCK
            | os.O_RDWR
            | os.O_APPEND
        )
        fd = os.open(str(path), flags, PROBE_CREATE_MODE)
        fds.append(fd)

        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            _fail(lines, "probe fstat: not a regular file")
            ok = False
        elif st.st_uid != euid:
            _fail(lines, f"probe fstat owner {st.st_uid} != euid {euid}")
            ok = False
        elif st.st_nlink != 1:
            _fail(lines, f"probe fstat nlink {st.st_nlink} != 1")
            ok = False
        else:
            mode = stat.S_IMODE(st.st_mode)
            _pass(
                lines,
                f"probe create O_EXCL|O_NOFOLLOW mode={mode:04o} owner={st.st_uid} nlink=1",
            )

        os.write(fd, b"alpha")
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, b"BETA")
        os.fsync(fd)
        with open(path, "rb") as handle:
            body = handle.read()
        if body != b"alphaBETA":
            _fail(lines, f"O_APPEND ignored seek; content={body!r}")
            ok = False
        else:
            _pass(lines, "O_APPEND appends despite seek")

        try:
            os.fchmod(fd, PROBE_FINAL_MODE)
            st2 = os.fstat(fd)
            if stat.S_IMODE(st2.st_mode) != PROBE_FINAL_MODE:
                _fail(
                    lines,
                    f"fchmod final mode {stat.S_IMODE(st2.st_mode):04o} "
                    f"!= {PROBE_FINAL_MODE:04o}",
                )
                ok = False
            else:
                _pass(lines, f"fchmod to {PROBE_FINAL_MODE:04o}")
        except OSError as exc:
            _fail(lines, f"fchmod failed: {exc.strerror}")
            ok = False

        # Nonblocking exclusive flock across a child process.
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            _fail(lines, f"parent flock LOCK_EX|LOCK_NB failed: {exc.strerror}")
            ok = False
        else:
            status, detail = _run_lock_child(path)
            if status != "busy":
                _fail(
                    lines,
                    f"contended child flock expected busy, got {status!r} detail={detail!r}",
                )
                ok = False
            else:
                _pass(lines, "contended child flock fails promptly (LOCK_NB)")
            fcntl.flock(fd, fcntl.LOCK_UN)
            status2, detail2 = _run_lock_child(path)
            if status2 != "locked":
                _fail(
                    lines,
                    f"released child flock expected locked, got {status2!r} detail={detail2!r}",
                )
                ok = False
            else:
                _pass(lines, "released child flock succeeds")
                # Child holds the lock briefly; unlock by reopening is unnecessary
                # because child closed its fd after LOCK_UN is not called — child
                # leaves lock held until fd close in finally. Wait for child exit
                # already done. Parent may re-acquire:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError as exc:
                    _fail(lines, f"parent could not re-acquire flock: {exc.strerror}")
                    ok = False

        # O_NOFOLLOW rejects a symlink target.
        link_name = track(users_dir / _probe_name("link"))
        target_name = track(users_dir / _probe_name("linktgt"))
        target_fd = os.open(
            str(target_name),
            os.O_CREAT
            | os.O_EXCL
            | os.O_NOFOLLOW
            | os.O_CLOEXEC
            | os.O_NONBLOCK
            | os.O_WRONLY,
            PROBE_CREATE_MODE,
        )
        fds.append(target_fd)
        os.close(target_fd)
        fds.remove(target_fd)
        os.symlink(target_name.name, link_name)
        try:
            bad_fd = os.open(
                str(link_name),
                os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
            )
            _close_fd(bad_fd)
            _fail(lines, "O_NOFOLLOW unexpectedly opened a symlink")
            ok = False
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                _pass(lines, "O_NOFOLLOW rejects symlink (ELOOP)")
            else:
                _fail(
                    lines,
                    f"O_NOFOLLOW symlink open unexpected errno={exc.errno}",
                )
                ok = False

        # Same-directory rename preserves inode and content.
        rename_src = track(users_dir / _probe_name("rensrc"))
        rename_dst = track(users_dir / _probe_name("rendst"))
        rfd: Optional[int] = None
        try:
            rfd = os.open(
                str(rename_src),
                os.O_CREAT
                | os.O_EXCL
                | os.O_NOFOLLOW
                | os.O_CLOEXEC
                | os.O_NONBLOCK
                | os.O_WRONLY,
                PROBE_CREATE_MODE,
            )
            os.write(rfd, b"rename-payload")
            st_src = os.fstat(rfd)
        finally:
            _close_fd(rfd)
            rfd = None
        os.rename(rename_src, rename_dst)
        # src path no longer exists; keep dst for cleanup.
        owned.remove(rename_src)
        st_dst = os.lstat(rename_dst)
        with open(rename_dst, "rb") as handle:
            renamed_body = handle.read()
        if st_dst.st_ino != st_src.st_ino or renamed_body != b"rename-payload":
            _fail(
                lines,
                "same-directory rename did not preserve inode/content "
                f"(ino {st_src.st_ino}->{st_dst.st_ino}, body={renamed_body!r})",
            )
            ok = False
        else:
            _pass(lines, "same-directory rename preserves inode/content")

        # O_NONBLOCK FIFO open in a timeout-bounded child.
        fifo_path = track(users_dir / _probe_name("fifo"))
        os.mkfifo(fifo_path, 0o0600)
        # Ensure ownership for cleanup (mkfifo uses umask).
        try:
            os.chmod(fifo_path, 0o0600)
        except OSError:
            pass
        status_f, detail_f = _run_fifo_child(fifo_path)
        if status_f == "timeout":
            _fail(lines, "FIFO O_NONBLOCK child hung until timeout")
            ok = False
        elif status_f == "errno" and detail_f == errno.ENXIO:
            _pass(lines, "FIFO O_NONBLOCK open returns ENXIO promptly without hang")
        else:
            _fail(
                lines,
                f"FIFO O_NONBLOCK expected ENXIO, got {status_f!r} detail={detail_f!r}",
            )
            ok = False

    except OSError as exc:
        _fail(lines, f"probe operations failed: {exc.strerror}")
        ok = False
    finally:
        for fd in list(fds):
            _close_fd(fd)
        for path in owned:
            _unlink_owned(path, euid)

    return ok


def validate_filesystem(
    parent_dir: str | os.PathLike[str],
    *,
    protected_hardlinks_path: Path = DEFAULT_PROTECTED_HARDLINKS,
    geteuid: Callable[[], int] = os.geteuid,
) -> Tuple[int, List[str]]:
    """Validate shared telemetry filesystem guarantees.

    Returns ``(exit_code, status_lines)`` where exit_code is 0 only when every
    required guarantee passes. Never raises for expected validation failures.
    """
    lines: List[str] = []
    try:
        try:
            parent = normalize_operator_telemetry_dir(parent_dir)
        except InvalidTelemetryDirError as exc:
            _fail(lines, str(exc))
            return (1, lines)

        users = parent / "users"
        if not existing_ancestors_are_real_dirs(parent):
            _fail(
                lines,
                f"telemetry parent has a symlink or non-directory ancestor (refusing): {parent}",
            )
            return (1, lines)
        if not existing_ancestors_are_real_dirs(users):
            _fail(
                lines,
                f"users path has a symlink or non-directory ancestor (refusing): {users}",
            )
            return (1, lines)

        euid = geteuid()
        ok = True
        ok = _check_platform(lines) and ok
        ok = _check_primitives(lines) and ok
        ok = _check_protected_hardlinks(protected_hardlinks_path, lines) and ok

        parent_ok = _owned_non_symlink_dir(parent, euid, PARENT_MODE, "telemetry parent", lines)
        users_ok = _owned_non_symlink_dir(users, euid, USERS_MODE, "users", lines)
        ok = parent_ok and users_ok and ok

        if parent_ok and users_ok and sys.platform == "linux":
            # Still run probe ops when primitives/hardlinks failed so messages
            # stay actionable, but only if dirs are usable.
            if not _probe_file_ops(users, euid, lines):
                ok = False
        elif parent_ok and users_ok:
            _fail(lines, "skipped probe ops because platform is not Linux")
            ok = False

        # Sticky cross-user deletion is intentionally not exercised here.
        _pass(
            lines,
            "sticky cross-user deletion requires separate two-account operational check",
        )
        return (0 if ok else 1, lines)
    except Exception as exc:  # noqa: BLE001 - never traceback for operator CLI
        _fail(lines, f"unexpected validator error: {exc}")
        return (1, lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="validate_telemetry_filesystem.py",
        description=(
            "Validate shared Autobench telemetry filesystem guarantees on the "
            "actual edge-node mount. Exit 0 only when every required check passes."
        ),
        epilog=(
            "Example:\n"
            "  python scripts/validate_telemetry_filesystem.py "
            "--dir /ads_storage/autobench/telemetry\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dir",
        type=str,
        default=str(DEFAULT_PARENT),
        help=(
            "Absolute telemetry parent directory whose direct child is users/ "
            f"(default: {DEFAULT_PARENT})"
        ),
    )
    parser.add_argument(
        "--internal-child",
        nargs=2,
        metavar=("MODE", "PATH"),
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.internal_child:
        mode, path = args.internal_child
        if mode == _INTERNAL_LOCK:
            return _child_try_lock(path)
        if mode == _INTERNAL_FIFO:
            return _child_fifo_open(path)
        print(f"error:unknown-mode:{mode}")
        return 2
    code, lines = validate_filesystem(
        args.dir,
        protected_hardlinks_path=DEFAULT_PROTECTED_HARDLINKS,
    )
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: unexpected error: {exc}", file=sys.stderr)
        raise SystemExit(1)
