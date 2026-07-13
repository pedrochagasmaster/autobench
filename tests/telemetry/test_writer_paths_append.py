"""Writer paths_for, append_one happy paths/modes, and record validation."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

import pytest

from core.telemetry.capability import shared_writer_supported
from core.telemetry.constants import MAX_RECORD_BYTES
from core.telemetry.writer import (
    WriterPaths,
    append_one,
    append_record,
    paths_for,
)

from tests.telemetry.writer_helpers import (
    OPEN_FLAGS,
    RECORD,
    _identity,
)

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


def test_paths_for_absolutizes_relative_shared_without_collapsing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a").mkdir()
    (tmp_path / "shared").mkdir()

    paths = paths_for(identity, Path("a/../shared"), storage_root=tmp_path / "ads")

    assert os.fspath(paths.shared_users_dir).startswith("/")
    assert "a" in paths.shared_users_dir.parts
    assert ".." in paths.shared_users_dir.parts
    assert paths.shared_users_dir.name == "users"


def test_paths_for_and_gate_reject_escape_symlink_dotdot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """escape/../shared must not gate or write; kernel target differs from lexical."""
    identity = _identity()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("core.telemetry.capability.sys.platform", "linux")
    protected = tmp_path / "protected_hardlinks"
    protected.write_text("1\n", encoding="ascii")

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (tmp_path / "escape").symlink_to(elsewhere)
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    users.chmod(0o1777)

    rel_shared = Path("escape/../shared")
    paths = paths_for(identity, rel_shared, storage_root=tmp_path / "ads")
    assert "escape" in paths.shared_users_dir.parts
    assert (
        shared_writer_supported(
            paths.shared_users_dir, protected_hardlinks_path=protected
        )
        is False
    )

    result = append_record(
        RECORD,
        identity=identity,
        paths=paths,
        shared_enabled=False,
    )
    assert result.shared_attempted is False
    assert list(users.iterdir()) == []
    assert "escape" in str(paths.shared_users_dir)
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


