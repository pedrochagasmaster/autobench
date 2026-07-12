"""Tests for safe private/shared telemetry append writer."""

from __future__ import annotations

import errno
import fcntl
import os
import stat
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from core.telemetry.constants import MAX_RECORD_BYTES
from core.telemetry.identity import Identity, encode_user_token
from core.telemetry.writer import (
    AppendResult,
    WriterPaths,
    append_one,
    append_record,
    paths_for,
)

RECORD = b'{"ok":true}\n'
OPEN_FLAGS = (
    os.O_APPEND
    | os.O_CREAT
    | os.O_WRONLY
    | os.O_CLOEXEC
    | os.O_NONBLOCK
    | os.O_NOFOLLOW
)


def _identity(username: str = "alice", uid: int | None = None) -> Identity:
    return Identity(
        uid=os.geteuid() if uid is None else uid,
        username=username,
        token=encode_user_token(username),
    )


def _deadline(seconds: float = 2.0) -> float:
    return time.monotonic() + seconds


def _assert_before(deadline: float) -> None:
    assert time.monotonic() < deadline, "test exceeded deadline (possible hang)"


# ---------------------------------------------------------------------------
# paths_for
# ---------------------------------------------------------------------------


def test_paths_for_builds_exact_private_and_shared_paths(tmp_path: Path) -> None:
    identity = _identity("bob")
    shared_dir = tmp_path / "shared"
    storage_root = tmp_path / "ads_storage"

    paths = paths_for(identity, shared_dir, storage_root=storage_root)

    assert paths.private_file == (
        storage_root / "bob" / ".autobench" / "telemetry" / "events.jsonl"
    )
    assert paths.shared_users_dir == shared_dir / "users"
    assert isinstance(paths, WriterPaths)


def test_paths_for_default_storage_root() -> None:
    identity = _identity("carol")
    paths = paths_for(identity, Path("/ads_storage/autobench/telemetry"))
    assert paths.private_file == Path(
        "/ads_storage/carol/.autobench/telemetry/events.jsonl"
    )
    assert paths.shared_users_dir == Path("/ads_storage/autobench/telemetry/users")


# ---------------------------------------------------------------------------
# append_one happy path / modes / flags
# ---------------------------------------------------------------------------


def test_append_one_writes_private_with_modes_despite_umask(
    tmp_path: Path,
) -> None:
    identity = _identity()
    home = tmp_path / identity.username
    home.mkdir()
    home.chmod(0o755)
    home_mode_before = stat.S_IMODE(home.stat().st_mode)
    target = home / ".autobench" / "telemetry" / "events.jsonl"
    old_umask = os.umask(0o077)
    try:
        ok = append_one(
            target,
            RECORD,
            expected_uid=identity.uid,
            final_mode=0o600,
            create_private_parents=True,
        )
    finally:
        os.umask(old_umask)

    assert ok is True
    assert target.read_bytes() == RECORD
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert (
        stat.S_IMODE((tmp_path / identity.username / ".autobench").stat().st_mode)
        == 0o700
    )
    assert (
        stat.S_IMODE(
            (tmp_path / identity.username / ".autobench" / "telemetry").stat().st_mode
        )
        == 0o700
    )
    assert stat.S_IMODE(home.stat().st_mode) == home_mode_before


def test_append_one_opens_with_exact_flags_and_creation_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    target = tmp_path / "events.jsonl"
    seen: dict[str, Any] = {}
    real_open = os.open

    def spy_open(path: str | bytes | os.PathLike[str], flags: int, mode: int = 0o777, *args: Any, **kwargs: Any) -> int:
        seen["path"] = Path(os.fsdecode(path))
        seen["flags"] = flags
        seen["mode"] = mode
        return real_open(path, flags, mode, *args, **kwargs)

    monkeypatch.setattr("core.telemetry.writer.os.open", spy_open)

    assert (
        append_one(
            target,
            RECORD,
            expected_uid=identity.uid,
            final_mode=0o600,
            create_private_parents=False,
        )
        is True
    )
    assert seen["path"] == target
    assert seen["flags"] == OPEN_FLAGS
    assert seen["mode"] == 0o600


def test_append_one_shared_mode_0644(tmp_path: Path) -> None:
    identity = _identity()
    users = tmp_path / "users"
    users.mkdir()
    users.chmod(0o1777)
    target = users / f"{identity.token}.jsonl"
    old_umask = os.umask(0o077)
    try:
        ok = append_one(
            target,
            RECORD,
            expected_uid=identity.uid,
            final_mode=0o644,
            create_private_parents=False,
        )
    finally:
        os.umask(old_umask)

    assert ok is True
    assert stat.S_IMODE(target.stat().st_mode) == 0o644


# ---------------------------------------------------------------------------
# record validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "record",
    [
        "not-bytes",
        b"no-newline",
        b"two\nlines\n",
        b"embedded\nnewline mid",
        b"x" * MAX_RECORD_BYTES,  # no LF, exact max without terminator
        b"x" * (MAX_RECORD_BYTES - 1) + b"\n\n",
        b"x" * MAX_RECORD_BYTES + b"\n",  # too long
    ],
)
def test_append_one_rejects_invalid_records(tmp_path: Path, record: object) -> None:
    identity = _identity()
    target = tmp_path / "events.jsonl"
    assert (
        append_one(
            target,
            record,  # type: ignore[arg-type]
            expected_uid=identity.uid,
            final_mode=0o600,
            create_private_parents=False,
        )
        is False
    )
    assert not target.exists()


def test_append_one_accepts_max_sized_record(tmp_path: Path) -> None:
    identity = _identity()
    target = tmp_path / "events.jsonl"
    record = b"x" * (MAX_RECORD_BYTES - 1) + b"\n"
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


def test_append_one_accepts_single_lf(tmp_path: Path) -> None:
    identity = _identity()
    target = tmp_path / "events.jsonl"
    assert (
        append_one(
            target,
            b"\n",
            expected_uid=identity.uid,
            final_mode=0o600,
            create_private_parents=False,
        )
        is True
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


def test_append_one_rejects_hardlink_nlink_gt_1(tmp_path: Path) -> None:
    identity = _identity()
    target = tmp_path / "events.jsonl"
    other = tmp_path / "other.jsonl"
    target.write_bytes(b"")
    os.link(target, other)
    assert target.stat().st_nlink > 1
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


def test_append_one_rejects_foreign_owner_via_fstat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    target = tmp_path / "events.jsonl"
    real_fstat = os.fstat

    def fake_fstat(fd: int) -> os.stat_result:
        st = real_fstat(fd)
        return st.replace(st_uid=identity.uid + 1)

    monkeypatch.setattr("core.telemetry.writer.os.fstat", fake_fstat)
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


# ---------------------------------------------------------------------------
# lock / chmod / write failures
# ---------------------------------------------------------------------------


def test_append_one_returns_false_on_lock_contention(tmp_path: Path) -> None:
    identity = _identity()
    target = tmp_path / "events.jsonl"
    target.write_bytes(b"")
    holder = os.open(str(target), os.O_WRONLY)
    executor: ThreadPoolExecutor | None = None
    try:
        fcntl.flock(holder, fcntl.LOCK_EX)
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
    finally:
        try:
            fcntl.flock(holder, fcntl.LOCK_UN)
        finally:
            os.close(holder)
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


# ---------------------------------------------------------------------------
# private parent creation
# ---------------------------------------------------------------------------


def test_append_one_create_private_parents_false_missing_parent(
    tmp_path: Path,
) -> None:
    identity = _identity()
    target = tmp_path / "missing" / "events.jsonl"
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
    assert not (tmp_path / "missing").exists()


def test_append_one_rejects_symlink_autobench_parent(tmp_path: Path) -> None:
    identity = _identity()
    home = tmp_path / identity.username
    home.mkdir()
    real = tmp_path / "elsewhere"
    real.mkdir()
    (home / ".autobench").symlink_to(real)
    target = home / ".autobench" / "telemetry" / "events.jsonl"
    assert (
        append_one(
            target,
            RECORD,
            expected_uid=identity.uid,
            final_mode=0o600,
            create_private_parents=True,
        )
        is False
    )


def test_append_one_rejects_foreign_owned_telemetry_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    home = tmp_path / identity.username
    app = home / ".autobench"
    tele = app / "telemetry"
    tele.mkdir(parents=True)
    target = tele / "events.jsonl"

    real_lstat = os.lstat

    def fake_lstat(path: str | bytes | os.PathLike[str]) -> os.stat_result:
        st = real_lstat(path)
        resolved = Path(os.fsdecode(path))
        if resolved == tele or resolved == app:
            return st.replace(st_uid=identity.uid + 99)
        return st

    monkeypatch.setattr("core.telemetry.writer.os.lstat", fake_lstat)
    assert (
        append_one(
            target,
            RECORD,
            expected_uid=identity.uid,
            final_mode=0o600,
            create_private_parents=True,
        )
        is False
    )


def test_append_one_rejects_nondirectory_telemetry_parent(tmp_path: Path) -> None:
    identity = _identity()
    home = tmp_path / identity.username
    app = home / ".autobench"
    app.mkdir(parents=True)
    (app / "telemetry").write_text("file", encoding="utf-8")
    target = app / "telemetry" / "events.jsonl"
    assert (
        append_one(
            target,
            RECORD,
            expected_uid=identity.uid,
            final_mode=0o600,
            create_private_parents=True,
        )
        is False
    )


# ---------------------------------------------------------------------------
# append_record orchestration
# ---------------------------------------------------------------------------


def test_append_record_private_and_shared_success(tmp_path: Path) -> None:
    identity = _identity()
    storage_root = tmp_path / "ads"
    (storage_root / identity.username).mkdir(parents=True)
    shared_dir = tmp_path / "shared"
    users = shared_dir / "users"
    users.mkdir(parents=True)
    users.chmod(0o1777)
    paths = paths_for(identity, shared_dir, storage_root=storage_root)

    result = append_record(
        RECORD, identity=identity, paths=paths, shared_enabled=True
    )

    assert result == AppendResult(
        private_ok=True, shared_attempted=True, shared_ok=True
    )
    assert paths.private_file.read_bytes() == RECORD
    shared_file = paths.shared_users_dir / f"{identity.token}.jsonl"
    assert shared_file.read_bytes() == RECORD
    assert stat.S_IMODE(paths.private_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(shared_file.stat().st_mode) == 0o644


def test_append_record_shared_disabled_leaves_shared_untouched(
    tmp_path: Path,
) -> None:
    identity = _identity()
    storage_root = tmp_path / "ads"
    (storage_root / identity.username).mkdir(parents=True)
    shared_dir = tmp_path / "shared"
    users = shared_dir / "users"
    users.mkdir(parents=True)
    paths = paths_for(identity, shared_dir, storage_root=storage_root)

    result = append_record(
        RECORD, identity=identity, paths=paths, shared_enabled=False
    )

    assert result == AppendResult(
        private_ok=True, shared_attempted=False, shared_ok=False
    )
    assert paths.private_file.exists()
    assert list(users.iterdir()) == []


def test_append_record_attempts_shared_even_when_private_fails(
    tmp_path: Path,
) -> None:
    identity = _identity()
    storage_root = tmp_path / "ads"
    # Do not create username home; private parent creation happens but we
    # sabotage private by making private_file's parent a file after paths.
    shared_dir = tmp_path / "shared"
    users = shared_dir / "users"
    users.mkdir(parents=True)
    users.chmod(0o1777)
    paths = paths_for(identity, shared_dir, storage_root=storage_root)
    # Make private path unwritable by placing a file where .autobench should be
    home = storage_root / identity.username
    home.mkdir(parents=True)
    (home / ".autobench").write_text("blocked", encoding="utf-8")

    result = append_record(
        RECORD, identity=identity, paths=paths, shared_enabled=True
    )

    assert result.private_ok is False
    assert result.shared_attempted is True
    assert result.shared_ok is True
    shared_file = paths.shared_users_dir / f"{identity.token}.jsonl"
    assert shared_file.read_bytes() == RECORD


def test_append_record_attempts_private_even_when_shared_fails(
    tmp_path: Path,
) -> None:
    identity = _identity()
    storage_root = tmp_path / "ads"
    (storage_root / identity.username).mkdir(parents=True)
    shared_dir = tmp_path / "shared"
    # missing users dir — shared must fail and must not be created
    paths = paths_for(identity, shared_dir, storage_root=storage_root)

    result = append_record(
        RECORD, identity=identity, paths=paths, shared_enabled=True
    )

    assert result.private_ok is True
    assert result.shared_attempted is True
    assert result.shared_ok is False
    assert paths.private_file.read_bytes() == RECORD
    assert not paths.shared_users_dir.exists()


def test_append_record_does_not_create_missing_shared_users(
    tmp_path: Path,
) -> None:
    identity = _identity()
    storage_root = tmp_path / "ads"
    (storage_root / identity.username).mkdir(parents=True)
    paths = paths_for(
        identity, tmp_path / "shared", storage_root=storage_root
    )
    append_record(RECORD, identity=identity, paths=paths, shared_enabled=True)
    assert not (tmp_path / "shared" / "users").exists()


def test_append_one_closes_descriptor_on_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    target = tmp_path / "events.jsonl"
    closed: list[int] = []
    opened: list[int] = []
    real_open = os.open
    real_close = os.close

    def spy_open(*args: Any, **kwargs: Any) -> int:
        fd = real_open(*args, **kwargs)
        opened.append(fd)
        return fd

    def spy_close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    monkeypatch.setattr("core.telemetry.writer.os.open", spy_open)
    monkeypatch.setattr("core.telemetry.writer.os.close", spy_close)

    assert (
        append_one(
            target,
            RECORD,
            expected_uid=identity.uid,
            final_mode=0o600,
            create_private_parents=False,
        )
        is True
    )
    assert opened
    assert closed == opened
