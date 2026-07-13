"""Writer private parent creation and append_record orchestration tests."""

from __future__ import annotations

import errno
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from core.telemetry.writer import (
    AppendResult,
    append_one,
    append_record,
    paths_for,
)

from tests.telemetry.writer_helpers import (
    RECORD,
    _assert_before,
    _deadline,
    _identity,
    _stat_standin,
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
    open_calls: list[Any] = []
    fchmod_calls: list[Any] = []
    write_calls: list[Any] = []

    def fake_lstat(path: str | bytes | os.PathLike[str]) -> Any:
        st = real_lstat(path)
        resolved = Path(os.fsdecode(path))
        if resolved == tele or resolved == app:
            return _stat_standin(st, uid=identity.uid + 99)
        return st

    monkeypatch.setattr("core.telemetry.writer.os.lstat", fake_lstat)
    monkeypatch.setattr(
        "core.telemetry.writer.os.open",
        lambda *a, **k: open_calls.append(a) or (_ for _ in ()).throw(
            AssertionError("open must not run after foreign parent uid reject")
        ),
    )
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
            create_private_parents=True,
        )
        is False
    )
    assert open_calls == []
    assert fchmod_calls == []
    assert write_calls == []


def test_append_one_rejects_foreign_owned_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    home = tmp_path / identity.username
    home.mkdir()
    target = home / ".autobench" / "telemetry" / "events.jsonl"
    real_lstat = os.lstat
    open_calls: list[Any] = []
    mkdir_calls: list[Any] = []

    def fake_lstat(path: str | bytes | os.PathLike[str]) -> Any:
        st = real_lstat(path)
        if Path(os.fsdecode(path)) == home:
            return _stat_standin(st, uid=identity.uid + 7)
        return st

    monkeypatch.setattr("core.telemetry.writer.os.lstat", fake_lstat)
    monkeypatch.setattr(
        "core.telemetry.writer.os.mkdir",
        lambda *a, **k: mkdir_calls.append(a),
    )
    monkeypatch.setattr(
        "core.telemetry.writer.os.open",
        lambda *a, **k: open_calls.append(a) or (_ for _ in ()).throw(
            AssertionError("open must not run after foreign home reject")
        ),
    )
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
    assert mkdir_calls == []
    assert open_calls == []
    assert not (home / ".autobench").exists()


def test_append_one_rejects_nonsticky_world_writable_home(tmp_path: Path) -> None:
    identity = _identity()
    home = tmp_path / identity.username
    home.mkdir()
    home.chmod(0o0777)
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
    assert not (home / ".autobench").exists()
    assert stat.S_IMODE(home.stat().st_mode) == 0o0777


def test_append_one_accepts_owner_home(tmp_path: Path) -> None:
    identity = _identity()
    home = tmp_path / identity.username
    home.mkdir()
    home.chmod(0o755)
    target = home / ".autobench" / "telemetry" / "events.jsonl"
    assert (
        append_one(
            target,
            RECORD,
            expected_uid=identity.uid,
            final_mode=0o600,
            create_private_parents=True,
        )
        is True
    )
    assert target.read_bytes() == RECORD


def test_append_one_accepts_sticky_world_writable_owner_home(tmp_path: Path) -> None:
    identity = _identity()
    home = tmp_path / identity.username
    home.mkdir()
    home.chmod(0o1777)
    mode_before = stat.S_IMODE(home.stat().st_mode)
    target = home / ".autobench" / "telemetry" / "events.jsonl"
    assert (
        append_one(
            target,
            RECORD,
            expected_uid=identity.uid,
            final_mode=0o600,
            create_private_parents=True,
        )
        is True
    )
    assert target.read_bytes() == RECORD
    assert stat.S_IMODE(home.stat().st_mode) == mode_before


def test_append_one_mkdir_eexist_race_relstats_and_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deterministic race: mkdir loses with EEXIST; winner dir must be accepted."""
    identity = _identity()
    home = tmp_path / identity.username
    home.mkdir()
    home.chmod(0o755)
    target = home / ".autobench" / "telemetry" / "events.jsonl"
    real_mkdir = os.mkdir

    def race_mkdir(path: str | bytes | os.PathLike[str], mode: int = 0o777) -> None:
        real_mkdir(path, mode)
        raise FileExistsError(errno.EEXIST, "File exists", os.fsdecode(path))

    monkeypatch.setattr("core.telemetry.writer.os.mkdir", race_mkdir)
    assert (
        append_one(
            target,
            RECORD,
            expected_uid=identity.uid,
            final_mode=0o600,
            create_private_parents=True,
        )
        is True
    )
    assert target.read_bytes() == RECORD
    assert stat.S_IMODE((home / ".autobench").stat().st_mode) == 0o700
    assert (
        stat.S_IMODE((home / ".autobench" / "telemetry").stat().st_mode) == 0o700
    )


def test_append_one_concurrent_private_parent_creation(tmp_path: Path) -> None:
    """Race parent mkdir across threads; distinct files avoid LOCK_NB contention."""
    identity = _identity()
    home = tmp_path / identity.username
    home.mkdir()
    home.chmod(0o755)
    tele = home / ".autobench" / "telemetry"
    deadline = _deadline(5.0)
    workers = 8

    def worker(index: int) -> bool:
        target = tele / f"events-{index}.jsonl"
        return append_one(
            target,
            RECORD,
            expected_uid=identity.uid,
            final_mode=0o600,
            create_private_parents=True,
        )

    executor = ThreadPoolExecutor(max_workers=workers)
    try:
        futures = [executor.submit(worker, i) for i in range(workers)]
        results = [f.result(timeout=3.0) for f in futures]
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
    _assert_before(deadline)
    assert all(results)
    assert stat.S_IMODE((home / ".autobench").stat().st_mode) == 0o700
    assert stat.S_IMODE(tele.stat().st_mode) == 0o700
    for i in range(workers):
        assert (tele / f"events-{i}.jsonl").read_bytes() == RECORD


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
    shared_file = Path(os.fspath(paths.shared_users_dir)) / f"{identity.token}.jsonl"
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
    shared_file = Path(os.fspath(paths.shared_users_dir)) / f"{identity.token}.jsonl"
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
    assert not Path(os.fspath(paths.shared_users_dir)).exists()


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
