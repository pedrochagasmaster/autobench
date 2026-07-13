"""Writer hostile final-path and lock/chmod/write failure tests."""

from __future__ import annotations

import errno
import fcntl
import os
import socket
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from core.telemetry.writer import (
    append_one,
)

from tests.telemetry.writer_helpers import (
    RECORD,
    _assert_before,
    _deadline,
    _identity,
    _stat_standin,
)

# ---------------------------------------------------------------------------
# hostile final paths
# ---------------------------------------------------------------------------


def test_append_one_rejects_symlink_final_path(tmp_path: Path) -> None:
    identity = _identity()
    real = tmp_path / "real.jsonl"
    real.write_bytes(b"")
    target = tmp_path / "link.jsonl"
    target.symlink_to(real)
    deadline = _deadline()
    ok = append_one(
        target,
        RECORD,
        expected_uid=identity.uid,
        final_mode=0o600,
        create_private_parents=False,
    )
    _assert_before(deadline)
    assert ok is False
    assert real.read_bytes() == b""


def test_append_one_rejects_fifo_promptly(tmp_path: Path) -> None:
    identity = _identity()
    target = tmp_path / "fifo.jsonl"
    os.mkfifo(target)
    deadline = _deadline(2.0)
    ok = append_one(
        target,
        RECORD,
        expected_uid=identity.uid,
        final_mode=0o600,
        create_private_parents=False,
    )
    _assert_before(deadline)
    assert ok is False


def test_append_one_rejects_directory(tmp_path: Path) -> None:
    identity = _identity()
    target = tmp_path / "dir.jsonl"
    target.mkdir()
    deadline = _deadline()
    ok = append_one(
        target,
        RECORD,
        expected_uid=identity.uid,
        final_mode=0o600,
        create_private_parents=False,
    )
    _assert_before(deadline)
    assert ok is False


def test_append_one_rejects_unix_socket_promptly(tmp_path: Path) -> None:
    identity = _identity()
    target = tmp_path / "sock.jsonl"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(str(target))
        deadline = _deadline(2.0)
        ok = append_one(
            target,
            RECORD,
            expected_uid=identity.uid,
            final_mode=0o600,
            create_private_parents=False,
        )
        _assert_before(deadline)
        assert ok is False
    finally:
        server.close()
        if target.exists():
            target.unlink()


def test_append_one_rejects_existing_char_device_promptly() -> None:
    """Use a pre-existing device node; never create/modify it."""
    identity = _identity()
    target = Path("/dev/null")
    try:
        st = target.lstat()
    except OSError:
        pytest.skip("/dev/null unavailable")
    if not stat.S_ISCHR(st.st_mode):
        pytest.skip("/dev/null is not a character device")
    mode_before = st.st_mode
    mtime_before = st.st_mtime_ns
    deadline = _deadline(2.0)
    ok = append_one(
        target,
        RECORD,
        expected_uid=identity.uid,
        final_mode=0o600,
        create_private_parents=False,
    )
    _assert_before(deadline)
    assert ok is False
    st_after = target.lstat()
    assert st_after.st_mode == mode_before
    assert st_after.st_mtime_ns == mtime_before


def test_append_one_rejects_hardlink_nlink_gt_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    target = tmp_path / "events.jsonl"
    other = tmp_path / "other.jsonl"
    target.write_bytes(b"")
    os.link(target, other)
    assert target.stat().st_nlink > 1
    opened: list[int] = []
    closed: list[int] = []
    real_open = os.open
    real_close = os.close

    def spy_open(
        path: str | bytes | os.PathLike[str],
        flags: int,
        mode: int = 0o777,
        *args: Any,
        **kwargs: Any,
    ) -> int:
        fd = real_open(path, flags, mode, *args, **kwargs)
        opened.append(fd)
        return fd

    def spy_close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    monkeypatch.setattr("core.telemetry.writer.os.open", spy_open)
    monkeypatch.setattr("core.telemetry.writer.os.close", spy_close)
    deadline = _deadline()
    ok = append_one(
        target,
        RECORD,
        expected_uid=identity.uid,
        final_mode=0o600,
        create_private_parents=False,
    )
    _assert_before(deadline)
    assert ok is False
    assert target.read_bytes() == b""
    assert opened
    assert closed == opened


def test_append_one_rejects_foreign_owner_via_fstat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    target = tmp_path / "events.jsonl"
    real_fstat = os.fstat
    opened: list[int] = []
    closed: list[int] = []
    fchmod_calls: list[Any] = []
    write_calls: list[Any] = []
    real_open = os.open
    real_close = os.close

    def fake_fstat(fd: int) -> SimpleNamespace:
        st = real_fstat(fd)
        return _stat_standin(st, uid=identity.uid + 1)

    def spy_open(
        path: str | bytes | os.PathLike[str],
        flags: int,
        mode: int = 0o777,
        *args: Any,
        **kwargs: Any,
    ) -> int:
        fd = real_open(path, flags, mode, *args, **kwargs)
        opened.append(fd)
        return fd

    def spy_close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    monkeypatch.setattr("core.telemetry.writer.os.fstat", fake_fstat)
    monkeypatch.setattr("core.telemetry.writer.os.open", spy_open)
    monkeypatch.setattr("core.telemetry.writer.os.close", spy_close)
    monkeypatch.setattr(
        "core.telemetry.writer.os.fchmod",
        lambda *a, **k: fchmod_calls.append(a),
    )
    monkeypatch.setattr(
        "core.telemetry.writer.os.write",
        lambda *a, **k: write_calls.append(a) or 0,
    )
    assert (
        append_one(
            target,
            RECORD,
            expected_uid=identity.uid,
            final_mode=0o600,
            create_private_parents=False,
        )
        is False
    )
    assert opened
    assert closed == opened
    assert fchmod_calls == []
    assert write_calls == []


# ---------------------------------------------------------------------------
# lock / chmod / write failures
# ---------------------------------------------------------------------------


def test_append_one_returns_false_on_lock_contention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    target = tmp_path / "events.jsonl"
    target.write_bytes(b"")
    holder = os.open(str(target), os.O_WRONLY)
    executor: ThreadPoolExecutor | None = None
    opened: list[int] = []
    closed: list[int] = []
    real_open = os.open
    real_close = os.close

    def spy_open(
        path: str | bytes | os.PathLike[str],
        flags: int,
        mode: int = 0o777,
        *args: Any,
        **kwargs: Any,
    ) -> int:
        fd = real_open(path, flags, mode, *args, **kwargs)
        opened.append(fd)
        return fd

    def spy_close(fd: int) -> None:
        # Track writer closes only; never close the held lock fd via this spy path
        # unless append_one opened it (holder uses real_close in finally).
        closed.append(fd)
        real_close(fd)

    try:
        fcntl.flock(holder, fcntl.LOCK_EX)
        monkeypatch.setattr("core.telemetry.writer.os.open", spy_open)
        monkeypatch.setattr("core.telemetry.writer.os.close", spy_close)
        deadline = _deadline(2.0)
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(
            append_one,
            target,
            RECORD,
            expected_uid=identity.uid,
            final_mode=0o600,
            create_private_parents=False,
        )
        ok = future.result(timeout=1.5)
        _assert_before(deadline)
        assert ok is False
        assert target.read_bytes() == b""
        assert opened
        assert closed == opened
        assert holder not in closed
        # Held lock fd must remain usable (spy must not have closed it).
        os.fstat(holder)
    finally:
        try:
            fcntl.flock(holder, fcntl.LOCK_UN)
        finally:
            real_close(holder)
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)


def test_append_one_returns_false_on_fchmod_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    target = tmp_path / "events.jsonl"
    closed: list[int] = []
    real_close = os.close

    def tracking_close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    monkeypatch.setattr("core.telemetry.writer.os.close", tracking_close)
    monkeypatch.setattr(
        "core.telemetry.writer.os.fchmod",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError(errno.EPERM, "denied")),
    )
    assert (
        append_one(
            target,
            RECORD,
            expected_uid=identity.uid,
            final_mode=0o600,
            create_private_parents=False,
        )
        is False
    )
    assert closed


def test_append_one_returns_false_on_fstat_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    target = tmp_path / "events.jsonl"
    closed: list[int] = []
    real_close = os.close

    def tracking_close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    monkeypatch.setattr("core.telemetry.writer.os.close", tracking_close)
    monkeypatch.setattr(
        "core.telemetry.writer.os.fstat",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError(errno.EBADF, "bad")),
    )
    assert (
        append_one(
            target,
            RECORD,
            expected_uid=identity.uid,
            final_mode=0o600,
            create_private_parents=False,
        )
        is False
    )
    assert closed


def test_append_one_retries_eintr_and_completes_partial_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    target = tmp_path / "events.jsonl"
    record = b"abcdefghij\n"
    calls = {"n": 0}
    real_write = os.write

    def flaky_write(fd: int, data: bytes) -> int:
        calls["n"] += 1
        if calls["n"] == 1:
            raise InterruptedError  # EINTR-style
        if calls["n"] == 2:
            raise OSError(errno.EINTR, "interrupted")
        if calls["n"] == 3:
            return real_write(fd, data[:3])
        return real_write(fd, data)

    monkeypatch.setattr("core.telemetry.writer.os.write", flaky_write)
    assert (
        append_one(
            target,
            record,
            expected_uid=identity.uid,
            final_mode=0o600,
            create_private_parents=False,
        )
        is True
    )
    assert target.read_bytes() == record


def test_append_one_returns_false_on_zero_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    target = tmp_path / "events.jsonl"
    closed: list[int] = []
    real_close = os.close

    def tracking_close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    monkeypatch.setattr("core.telemetry.writer.os.close", tracking_close)
    monkeypatch.setattr("core.telemetry.writer.os.write", lambda *_a, **_k: 0)
    assert (
        append_one(
            target,
            RECORD,
            expected_uid=identity.uid,
            final_mode=0o600,
            create_private_parents=False,
        )
        is False
    )
    assert closed


def test_append_one_returns_false_on_write_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    target = tmp_path / "events.jsonl"
    closed: list[int] = []
    real_close = os.close

    def tracking_close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    monkeypatch.setattr("core.telemetry.writer.os.close", tracking_close)
    monkeypatch.setattr(
        "core.telemetry.writer.os.write",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError(errno.EIO, "io")),
    )
    assert (
        append_one(
            target,
            RECORD,
            expected_uid=identity.uid,
            final_mode=0o600,
            create_private_parents=False,
        )
        is False
    )
    assert closed


def test_append_one_never_raises_on_open_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    target = tmp_path / "events.jsonl"
    monkeypatch.setattr(
        "core.telemetry.writer.os.open",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError(errno.EACCES, "denied")),
    )
    assert (
        append_one(
            target,
            RECORD,
            expected_uid=identity.uid,
            final_mode=0o600,
            create_private_parents=False,
        )
        is False
    )


