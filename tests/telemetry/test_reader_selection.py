"""Reader source selection and safe-open tests."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from core.telemetry.identity import encode_user_token
from core.telemetry.reader import (
    SourceKind,
    SourceSelection,
    TelemetryReader,
)

from tests.telemetry.reader_helpers import (
    FIXED_NOW,
    READ_FLAGS,
    SESSION_A,
    SESSION_B,
    _assert_before,
    _deadline,
    _identity,
    _reader,
    _session_start,
    _stat_standin,
    _write_private,
    _write_shared,
)

# ---------------------------------------------------------------------------
# Source selection
# ---------------------------------------------------------------------------


def test_select_sources_private_only_when_no_shared_jsonl(tmp_path: Path) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    (shared / "users").mkdir(parents=True)
    (shared / "users" / "subdir").mkdir()
    (shared / "users" / "notes.txt").write_text("x")
    storage = tmp_path / "ads"
    private = _write_private(storage, identity, _session_start())

    selection = _reader(tmp_path, identity=identity, shared_dir=shared, storage_root=storage).select_sources()

    assert selection.kind is SourceKind.PRIVATE
    assert selection.paths == (private,)
    assert selection.fallback_reason == "no_shared_files"
    assert dict(selection.rejected) == {}


def test_select_sources_prefers_shared_and_never_combines_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    storage = tmp_path / "ads"
    shared_path = _write_shared(shared, "alice", _session_start())
    _write_private(storage, identity, _session_start(session_id=SESSION_B))
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    selection = _reader(tmp_path, identity=identity, shared_dir=shared, storage_root=storage).select_sources()

    assert selection.kind is SourceKind.SHARED
    assert selection.paths == (shared_path,)
    events = list(
        _reader(tmp_path, identity=identity, shared_dir=shared, storage_root=storage).iter_events(
            days=None
        )
    )
    assert len(events) == 1
    assert events[0].session_id == str(SESSION_A)


def test_select_sources_falls_back_private_when_intermediate_ancestor_is_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    storage = tmp_path / "ads"
    private = _write_private(storage, identity, _session_start(session_id=SESSION_B))

    victim = tmp_path / "victim"
    victim.mkdir(mode=0o0755)
    link = tmp_path / "autobench"
    link.symlink_to(victim)
    shared = link / "telemetry"
    shared_path = _write_shared(shared, "alice", _session_start())
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    reader = _reader(
        tmp_path, identity=identity, shared_dir=shared, storage_root=storage
    )
    selection = reader.select_sources()

    assert selection.kind is SourceKind.PRIVATE
    assert selection.paths == (private,)
    events = list(reader.iter_events(days=None))
    assert len(events) == 1
    assert events[0].session_id == str(SESSION_B)
    # Shared content must not be selected/read via the intermediate symlink path.
    assert shared_path.exists()
    assert all(p != shared_path for p in selection.paths)


def test_select_sources_relative_shared_dir_selects_shared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    monkeypatch.chdir(tmp_path)
    storage = tmp_path / "ads"
    shared_path = _write_shared(tmp_path / "shared", "alice", _session_start())
    _write_private(storage, identity, _session_start(session_id=SESSION_B))
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    selection = _reader(
        tmp_path,
        identity=identity,
        shared_dir=Path("shared"),
        storage_root=storage,
    ).select_sources()

    assert selection.kind is SourceKind.SHARED
    assert len(selection.paths) == 1
    assert os.path.samefile(selection.paths[0], shared_path)


def test_select_sources_relative_symlink_ancestor_falls_back_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    monkeypatch.chdir(tmp_path)
    storage = tmp_path / "ads"
    private = _write_private(storage, identity, _session_start(session_id=SESSION_B))

    victim = tmp_path / "victim"
    victim.mkdir(mode=0o0755)
    (tmp_path / "autobench").symlink_to(victim)
    shared_path = _write_shared(
        Path("autobench") / "telemetry", "alice", _session_start()
    )
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    selection = _reader(
        tmp_path,
        identity=identity,
        shared_dir=Path("autobench/telemetry"),
        storage_root=storage,
    ).select_sources()

    assert selection.kind is SourceKind.PRIVATE
    assert selection.paths == (private,)
    assert shared_path.exists()


def test_select_sources_escape_symlink_dotdot_falls_back_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    monkeypatch.chdir(tmp_path)
    storage = tmp_path / "ads"
    private = _write_private(storage, identity, _session_start(session_id=SESSION_B))

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (tmp_path / "escape").symlink_to(elsewhere)
    shared_path = _write_shared(tmp_path / "shared", "alice", _session_start())
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    reader = _reader(
        tmp_path,
        identity=identity,
        shared_dir=Path("escape/../shared"),
        storage_root=storage,
    )
    selection = reader.select_sources()
    assert selection.kind is SourceKind.PRIVATE
    assert selection.paths == (private,)
    assert shared_path.exists()
    # Captured absolute parent keeps escape; later chdir must not redirect.
    other = tmp_path / "othercwd"
    other.mkdir()
    monkeypatch.chdir(other)
    assert reader.select_sources().kind is SourceKind.PRIVATE


def test_select_sources_dotdot_through_real_dir_selects_shared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a").mkdir()
    storage = tmp_path / "ads"
    shared_path = _write_shared(tmp_path / "shared", "alice", _session_start())
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    selection = _reader(
        tmp_path,
        identity=identity,
        shared_dir=Path("a/../shared"),
        storage_root=storage,
    ).select_sources()

    assert selection.kind is SourceKind.SHARED
    assert len(selection.paths) == 1
    assert os.path.samefile(selection.paths[0], shared_path)


def test_select_sources_hostile_only_falls_back_to_private(
    tmp_path: Path,
) -> None:
    """Junk *.jsonl alone must not suppress private fallback (DoS)."""
    identity = _identity()
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    hostile = users / "not-a-valid-token.jsonl"
    hostile.write_bytes(_session_start())
    storage = tmp_path / "ads"
    private = _write_private(storage, identity, _session_start(session_id=SESSION_B))

    reader = _reader(
        tmp_path, identity=identity, shared_dir=shared, storage_root=storage
    )
    selection = reader.select_sources()

    assert selection.kind is SourceKind.PRIVATE
    assert selection.paths == (private,)
    events = list(reader.iter_events(days=None))
    assert len(events) == 1
    assert events[0].session_id == str(SESSION_B)


def test_select_sources_mixed_valid_and_hostile_shared_only_no_double_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    (users / "junk.jsonl").write_bytes(b"{not-json\n")
    valid = _write_shared(shared, "alice", _session_start())
    storage = tmp_path / "ads"
    _write_private(storage, identity, _session_start(session_id=SESSION_B))
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    reader = _reader(
        tmp_path, identity=identity, shared_dir=shared, storage_root=storage
    )
    selection = reader.select_sources()

    assert selection.kind is SourceKind.SHARED
    assert selection.paths == (valid,)
    events = list(reader.iter_events(days=None))
    assert len(events) == 1
    assert events[0].session_id == str(SESSION_A)


def test_select_sources_owner_token_mismatch_alone_falls_back_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    # Filename token for bob, record user alice → fails qualification.
    path = users / f"{encode_user_token('bob')}.jsonl"
    path.write_bytes(_session_start(user="alice"))
    storage = tmp_path / "ads"
    private = _write_private(storage, identity, _session_start(session_id=SESSION_B))
    monkeypatch.setattr(
        "core.telemetry.reader.lookup_uid",
        lambda username: identity.uid if username == "alice" else identity.uid + 1,
    )

    selection = _reader(
        tmp_path, identity=identity, shared_dir=shared, storage_root=storage
    ).select_sources()

    assert selection.kind is SourceKind.PRIVATE
    assert selection.paths == (private,)


def test_select_sources_sorted_qualifying_shared_excludes_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    bob = _write_shared(shared, "bob", _session_start(user="bob"))
    alice = _write_shared(shared, "alice", _session_start())
    link = users / "zzzz_link.jsonl"
    link.symlink_to(alice)
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    selection = _reader(tmp_path, identity=identity, shared_dir=shared).select_sources()

    assert selection.kind is SourceKind.SHARED
    assert selection.paths == tuple(sorted((alice, bob)))
    assert link not in selection.paths


def test_select_sources_user_absent_in_valid_fleet_returns_empty_shared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    storage = tmp_path / "ads"
    _write_shared(shared, "bob", _session_start(user="bob"))
    _write_private(storage, identity, _session_start(session_id=SESSION_B))
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    selection = _reader(
        tmp_path, identity=identity, shared_dir=shared, storage_root=storage
    ).select_sources(user="alice")

    assert selection.kind is SourceKind.SHARED
    assert selection.paths == ()
    events = list(
        _reader(
            tmp_path, identity=identity, shared_dir=shared, storage_root=storage
        ).iter_events(days=None, user="alice")
    )
    assert events == []


def test_select_sources_user_filter_only_if_qualifying_not_raw_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    # Raw username filename must never be selected by grammar alone.
    (users / "alice.jsonl").write_bytes(_session_start())
    expected = _write_shared(shared, "alice", _session_start())
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    selection = _reader(tmp_path, identity=identity, shared_dir=shared).select_sources(
        user="alice"
    )

    assert selection.kind is SourceKind.SHARED
    assert selection.paths == (expected,)
    assert (users / "alice.jsonl") not in selection.paths


def test_select_sources_user_with_only_raw_name_decoy_falls_back_private(
    tmp_path: Path,
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    (users / "alice.jsonl").write_bytes(_session_start())
    storage = tmp_path / "ads"
    private = _write_private(storage, identity, _session_start(session_id=SESSION_B))

    selection = _reader(
        tmp_path, identity=identity, shared_dir=shared, storage_root=storage
    ).select_sources(user="alice")

    assert selection.kind is SourceKind.PRIVATE
    assert selection.paths == (private,)


def test_qualification_closes_descriptors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    _write_shared(shared, "alice", _session_start())
    opened: list[int] = []
    closed: list[int] = []
    real_open = os.open
    real_close = os.close

    def spy_open(
        p: str | bytes | os.PathLike[str],
        flags: int,
        mode: int = 0o777,
        *args: Any,
        **kwargs: Any,
    ) -> int:
        fd = real_open(p, flags, mode, *args, **kwargs)
        opened.append(fd)
        return fd

    def spy_close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)
    monkeypatch.setattr("core.telemetry.reader.os.open", spy_open)
    monkeypatch.setattr("core.telemetry.reader.os.close", spy_close)

    _reader(tmp_path, identity=identity, shared_dir=shared).select_sources()

    assert opened
    assert closed == opened


def test_qualification_fifo_does_not_block(tmp_path: Path) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    fifo = users / "junk.jsonl"
    os.mkfifo(fifo)
    storage = tmp_path / "ads"
    private = _write_private(storage, identity, _session_start(session_id=SESSION_B))

    deadline = _deadline()
    selection = _reader(
        tmp_path, identity=identity, shared_dir=shared, storage_root=storage
    ).select_sources()
    _assert_before(deadline)

    assert selection.kind is SourceKind.PRIVATE
    assert selection.paths == (private,)


def test_select_sources_explicit_shared_dir_overrides_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    env_dir = tmp_path / "env_shared"
    _write_shared(env_dir, "alice", _session_start())
    explicit = tmp_path / "explicit"
    (explicit / "users").mkdir(parents=True)
    monkeypatch.setenv("AUTOBENCH_TELEMETRY_DIR", str(env_dir))

    selection = TelemetryReader(
        shared_dir=explicit,
        identity=identity,
        storage_root=tmp_path / "ads",
        now=FIXED_NOW,
    ).select_sources()

    assert selection.kind is SourceKind.PRIVATE


def test_select_sources_uses_env_when_shared_dir_omitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    env_dir = tmp_path / "env_shared"
    path = _write_shared(env_dir, "alice", _session_start())
    monkeypatch.setenv("AUTOBENCH_TELEMETRY_DIR", str(env_dir))
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)

    selection = TelemetryReader(
        identity=identity,
        storage_root=tmp_path / "ads",
        now=FIXED_NOW,
    ).select_sources()

    assert selection.kind is SourceKind.SHARED
    assert selection.paths == (path,)
    assert selection.fallback_reason is None


def test_select_sources_empty_env_falls_back_to_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    monkeypatch.setenv("AUTOBENCH_TELEMETRY_DIR", "   ")
    isolated_default = tmp_path / "isolated_default_shared"
    (isolated_default / "users").mkdir(parents=True)
    monkeypatch.setattr(
        "core.telemetry.reader.DEFAULT_SHARED_DIR", isolated_default
    )
    storage = tmp_path / "ads"
    private = _write_private(storage, identity, _session_start())

    selection = TelemetryReader(
        identity=identity,
        storage_root=storage,
        now=FIXED_NOW,
    ).select_sources()

    # Isolated empty default shared → private only; never touches real /ads_storage.
    assert selection.kind is SourceKind.PRIVATE
    assert selection.paths == (private,)


def test_select_sources_rejects_invalid_user(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _reader(tmp_path).select_sources(user="bad/name")



# ---------------------------------------------------------------------------
# Safe open
# ---------------------------------------------------------------------------


def test_required_open_flags_all_available() -> None:
    assert hasattr(os, "O_RDONLY")
    assert hasattr(os, "O_CLOEXEC")
    assert hasattr(os, "O_NONBLOCK")
    assert hasattr(os, "O_NOFOLLOW")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK | os.O_NOFOLLOW
    assert flags == READ_FLAGS


def test_open_uses_exact_flags_and_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    path = _write_shared(shared, "alice", _session_start())
    seen: dict[str, Any] = {}
    opened: list[int] = []
    closed: list[int] = []
    real_open = os.open
    real_close = os.close

    def spy_open(
        p: str | bytes | os.PathLike[str],
        flags: int,
        mode: int = 0o777,
        *args: Any,
        **kwargs: Any,
    ) -> int:
        seen["path"] = Path(os.fsdecode(p))
        seen["flags"] = flags
        fd = real_open(p, flags, mode, *args, **kwargs)
        opened.append(fd)
        return fd

    def spy_close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)
    monkeypatch.setattr("core.telemetry.reader.os.open", spy_open)
    monkeypatch.setattr("core.telemetry.reader.os.close", spy_close)

    events = list(
        _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(days=None)
    )

    assert len(events) == 1
    assert seen["path"] == path
    assert seen["flags"] == READ_FLAGS
    assert opened
    assert closed == opened


def test_rejects_symlink_under_deadline(tmp_path: Path) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    real = users / f"{encode_user_token('alice')}.jsonl"
    real.write_bytes(_session_start())
    link = users / "link.jsonl"
    link.symlink_to(real)
    # Only the symlink entry present as selection via user path override style:
    # list dir has both; force single symlink by user token path that is a symlink.
    link.unlink()
    token_link = users / f"{encode_user_token('alice')}.jsonl"
    real_file = tmp_path / "real.jsonl"
    real_file.write_bytes(_session_start())
    token_link.unlink()
    token_link.symlink_to(real_file)

    deadline = _deadline()
    events = list(
        _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(days=None)
    )
    _assert_before(deadline)
    assert events == []


def test_rejects_fifo_under_deadline(tmp_path: Path) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    fifo = users / f"{encode_user_token('alice')}.jsonl"
    os.mkfifo(fifo)

    deadline = _deadline()
    events = list(
        _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(days=None)
    )
    _assert_before(deadline)
    assert events == []


def test_rejects_directory_entry(tmp_path: Path) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    # A .jsonl-named directory should appear in selection then fail open/fstat.
    bad = users / "dir.jsonl"
    bad.mkdir()

    deadline = _deadline()
    events = list(
        _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(days=None)
    )
    _assert_before(deadline)
    assert events == []


def test_rejects_hardlink_nlink_gt_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    path = _write_shared(shared, "alice", _session_start())
    other = tmp_path / "other.jsonl"
    os.link(path, other)
    assert path.stat().st_nlink > 1

    deadline = _deadline()
    events = list(
        _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(days=None)
    )
    _assert_before(deadline)
    assert events == []

    # Also force via fstat stand-in when nlink cannot be created.
    path.unlink()
    other.unlink()
    path = _write_shared(shared, "alice", _session_start())
    real_fstat = os.fstat

    def fake_fstat(fd: int) -> SimpleNamespace:
        return _stat_standin(real_fstat(fd), nlink=2)

    monkeypatch.setattr("core.telemetry.reader.os.fstat", fake_fstat)
    assert list(
        _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(days=None)
    ) == []


def test_private_rejects_foreign_uid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    (shared / "users").mkdir(parents=True)
    storage = tmp_path / "ads"
    _write_private(storage, identity, _session_start())
    real_fstat = os.fstat
    opened: list[int] = []
    closed: list[int] = []
    real_open = os.open
    real_close = os.close

    def fake_fstat(fd: int) -> SimpleNamespace:
        return _stat_standin(real_fstat(fd), uid=identity.uid + 1)

    def spy_open(
        p: str | bytes | os.PathLike[str],
        flags: int,
        mode: int = 0o777,
        *args: Any,
        **kwargs: Any,
    ) -> int:
        fd = real_open(p, flags, mode, *args, **kwargs)
        opened.append(fd)
        return fd

    def spy_close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    monkeypatch.setattr("core.telemetry.reader.os.fstat", fake_fstat)
    monkeypatch.setattr("core.telemetry.reader.os.open", spy_open)
    monkeypatch.setattr("core.telemetry.reader.os.close", spy_close)

    events = list(
        _reader(
            tmp_path, identity=identity, shared_dir=shared, storage_root=storage
        ).iter_events(days=None)
    )
    assert events == []
    assert opened
    assert closed == opened


def test_close_errors_are_swallowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    _write_shared(shared, "alice", _session_start())
    real_close = os.close

    def boom_close(fd: int) -> None:
        real_close(fd)
        raise OSError(9, "bad")

    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)
    monkeypatch.setattr("core.telemetry.reader.os.close", boom_close)
    events = list(
        _reader(tmp_path, identity=identity, shared_dir=shared).iter_events(days=None)
    )
    assert len(events) == 1


# ---------------------------------------------------------------------------
# Explicit fallback: why shared files were not read (no silent private reads)
# ---------------------------------------------------------------------------


def test_copied_files_fall_back_with_owner_mismatch_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Files copied from another host are owned by the copier: owner_mismatch."""
    identity = _identity()
    shared = tmp_path / "copied"
    _write_shared(shared, "bob", _session_start(user="bob"))
    _write_shared(shared, "carol", _session_start(user="carol"))
    storage = tmp_path / "ads"
    private = _write_private(storage, identity, _session_start(session_id=SESSION_B))
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid + 1)
    warnings: list[str] = []
    reader = _reader(
        tmp_path, identity=identity, shared_dir=shared, storage_root=storage, warn=warnings.append
    )

    selection = reader.select_sources()
    assert isinstance(selection, SourceSelection)
    assert selection.kind is SourceKind.PRIVATE
    assert selection.paths == (private,)
    assert selection.fallback_reason == "all_shared_rejected"
    assert dict(selection.rejected) == {"owner_mismatch": 2}

    events = list(reader.iter_events(days=None))
    assert [e.user for e in events] == ["alice"]
    assert reader.last_selection is not None
    assert len(warnings) == 1
    message = warnings[0]
    assert "owner_mismatch=2" in message
    assert "private" in message
    assert str(shared / "users") in message
    for leaked in ("bob", "carol", encode_user_token("bob"), "session_start"):
        assert leaked not in message


@pytest.mark.parametrize(
    ("setup", "reason"),
    [
        ("unknown_user", "unknown_user"),
        ("bad_name", "name_mismatch"),
        ("garbage", "no_valid_record"),
        ("symlink", "unreadable"),
    ],
)
def test_each_rejection_reason_is_counted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, setup: str, reason: str
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    users = shared / "users"
    users.mkdir(parents=True)
    if setup == "unknown_user":
        _write_shared(shared, "ghost", _session_start(user="ghost"))

        def lookup(_user: str) -> int:
            raise KeyError("no such user")

        monkeypatch.setattr("core.telemetry.reader.lookup_uid", lookup)
    elif setup == "bad_name":
        (users / "renamed.jsonl").write_bytes(_session_start())
    elif setup == "garbage":
        (users / f"{encode_user_token('alice')}.jsonl").write_bytes(b"{not json\n")
    else:
        target = tmp_path / "elsewhere.jsonl"
        target.write_bytes(_session_start())
        (users / f"{encode_user_token('alice')}.jsonl").symlink_to(target)
    if setup != "unknown_user":
        monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)
    selection = _reader(tmp_path, identity=identity, shared_dir=shared).select_sources()
    assert selection.kind is SourceKind.PRIVATE
    assert dict(selection.rejected) == {reason: 1}


def test_partial_rejection_reads_shared_and_warns_with_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    good = _write_shared(shared, "alice", _session_start())
    (shared / "users" / "renamed.jsonl").write_bytes(_session_start())
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)
    warnings: list[str] = []
    reader = _reader(tmp_path, identity=identity, shared_dir=shared, warn=warnings.append)
    events = list(reader.iter_events(days=None))
    assert len(events) == 1
    assert reader.last_selection.paths == (good,)
    assert warnings == [
        f"skipped 1 shared telemetry file(s) in {shared / 'users'} that failed the "
        "owner/name check (name_mismatch=1). Files copied from another host fail "
        "the owner check."
    ]
    assert "renamed" not in warnings[0]


def test_missing_shared_dir_warns_before_private_fallback(tmp_path: Path) -> None:
    identity = _identity()
    storage = tmp_path / "ads"
    _write_private(storage, identity, _session_start())
    warnings: list[str] = []
    reader = _reader(
        tmp_path,
        identity=identity,
        shared_dir=tmp_path / "absent",
        storage_root=storage,
        warn=warnings.append,
    )
    assert len(list(reader.iter_events(days=None))) == 1
    assert reader.last_selection.fallback_reason == "no_shared_dir"
    assert len(warnings) == 1 and "not found" in warnings[0]


def test_skipped_records_are_counted_once_per_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    shared = tmp_path / "shared"
    future = b'{"schema_version":5,"ts":"2026-07-12T22:00:00Z","event":"x","user":"alice",' \
        b'"session_id":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","app_version":"9","props":{}}\n'
    unknown_event = _session_start().replace(b'"session_start"', b'"session_pause"')
    _write_shared(
        shared, "alice", _session_start(), future, future, unknown_event, _session_start()
    )
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)
    warnings: list[str] = []
    reader = _reader(tmp_path, identity=identity, shared_dir=shared, warn=warnings.append)
    assert len(list(reader.iter_events(days=None))) == 2
    assert len(warnings) == 2
    assert warnings[0].startswith("skipped 2 record(s) with an unsupported schema_version")
    assert "supports 1, 2, 3, 4" in warnings[0]
    assert warnings[1] == "skipped 1 record(s) that failed schema validation."


def test_rejected_file_contributes_no_skip_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Junk inside a file that fails the gate is neither read nor reported."""
    identity = _identity()
    shared = tmp_path / "shared"
    _write_shared(shared, "alice", _session_start())
    (shared / "users" / "renamed.jsonl").write_bytes(b"{junk\n" + _session_start())
    monkeypatch.setattr("core.telemetry.reader.lookup_uid", lambda _u: identity.uid)
    warnings: list[str] = []
    reader = _reader(tmp_path, identity=identity, shared_dir=shared, warn=warnings.append)
    list(reader.iter_events(days=None))
    assert not any("schema validation" in w for w in warnings)


