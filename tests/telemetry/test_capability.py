"""Tests for shared telemetry writer capability gate."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.telemetry.capability import shared_writer_supported


def _make_users_dir(path: Path, mode: int = 0o1777) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(mode)
    return path


def test_shared_writer_supported_true_when_all_conditions_met(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    users = _make_users_dir(tmp_path / "users")
    protected = tmp_path / "protected_hardlinks"
    protected.write_text("1\n", encoding="ascii")
    monkeypatch.setattr("core.telemetry.capability.sys.platform", "linux")

    assert (
        shared_writer_supported(users, protected_hardlinks_path=protected) is True
    )


def test_shared_writer_supported_false_when_intermediate_ancestor_is_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("core.telemetry.capability.sys.platform", "linux")
    protected = tmp_path / "protected_hardlinks"
    protected.write_text("1\n", encoding="ascii")

    victim = tmp_path / "victim"
    victim.mkdir(mode=0o0755)
    link = tmp_path / "autobench"
    link.symlink_to(victim)
    users = link / "telemetry" / "users"
    users.mkdir(parents=True)
    users.chmod(0o1777)

    assert (
        shared_writer_supported(users, protected_hardlinks_path=protected) is False
    )


def test_shared_writer_supported_false_when_ancestor_is_nondirectory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("core.telemetry.capability.sys.platform", "linux")
    protected = tmp_path / "protected_hardlinks"
    protected.write_text("1\n", encoding="ascii")

    file_ancestor = tmp_path / "notadir"
    file_ancestor.write_text("x", encoding="utf-8")
    users = file_ancestor / "telemetry" / "users"

    assert (
        shared_writer_supported(users, protected_hardlinks_path=protected) is False
    )


def test_shared_writer_supported_true_for_relative_safe_users_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("core.telemetry.capability.sys.platform", "linux")
    monkeypatch.chdir(tmp_path)
    protected = tmp_path / "protected_hardlinks"
    protected.write_text("1\n", encoding="ascii")
    users = _make_users_dir(tmp_path / "shared" / "users")

    assert (
        shared_writer_supported(
            Path("shared/users"), protected_hardlinks_path=protected
        )
        is True
    )


def test_shared_writer_supported_normalizes_relative_dotdot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("core.telemetry.capability.sys.platform", "linux")
    monkeypatch.chdir(tmp_path)
    protected = tmp_path / "protected_hardlinks"
    protected.write_text("1\n", encoding="ascii")
    _make_users_dir(tmp_path / "telem" / "users")

    assert (
        shared_writer_supported(
            Path("telem/./x/../users"), protected_hardlinks_path=protected
        )
        is True
    )


def test_shared_writer_supported_false_for_relative_symlink_ancestor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("core.telemetry.capability.sys.platform", "linux")
    monkeypatch.chdir(tmp_path)
    protected = tmp_path / "protected_hardlinks"
    protected.write_text("1\n", encoding="ascii")

    victim = tmp_path / "victim"
    victim.mkdir(mode=0o0755)
    link = tmp_path / "autobench"
    link.symlink_to(victim)
    users = link / "telemetry" / "users"
    users.mkdir(parents=True)
    users.chmod(0o1777)

    assert (
        shared_writer_supported(
            Path("autobench/telemetry/users"),
            protected_hardlinks_path=protected,
        )
        is False
    )


def test_shared_writer_supported_false_on_non_linux(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    users = _make_users_dir(tmp_path / "users")
    protected = tmp_path / "protected_hardlinks"
    protected.write_text("1\n", encoding="ascii")
    monkeypatch.setattr("core.telemetry.capability.sys.platform", "darwin")

    assert (
        shared_writer_supported(users, protected_hardlinks_path=protected) is False
    )


@pytest.mark.parametrize(
    "attr",
    [
        "O_APPEND",
        "O_CREAT",
        "O_WRONLY",
        "O_CLOEXEC",
        "O_NONBLOCK",
        "O_NOFOLLOW",
    ],
)
def test_shared_writer_supported_false_when_os_flag_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, attr: str
) -> None:
    users = _make_users_dir(tmp_path / "users")
    protected = tmp_path / "protected_hardlinks"
    protected.write_text("1\n", encoding="ascii")
    monkeypatch.setattr("core.telemetry.capability.sys.platform", "linux")
    monkeypatch.delattr(os, attr, raising=True)

    assert (
        shared_writer_supported(users, protected_hardlinks_path=protected) is False
    )


@pytest.mark.parametrize("attr", ["flock", "LOCK_EX", "LOCK_NB"])
def test_shared_writer_supported_false_when_fcntl_primitive_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, attr: str
) -> None:
    users = _make_users_dir(tmp_path / "users")
    protected = tmp_path / "protected_hardlinks"
    protected.write_text("1\n", encoding="ascii")
    monkeypatch.setattr("core.telemetry.capability.sys.platform", "linux")

    import fcntl as real_fcntl

    fake = SimpleNamespace(
        **{
            name: getattr(real_fcntl, name)
            for name in dir(real_fcntl)
            if not name.startswith("_") and name != attr
        }
    )
    monkeypatch.setattr("core.telemetry.capability.fcntl", fake)

    assert (
        shared_writer_supported(users, protected_hardlinks_path=protected) is False
    )


@pytest.mark.parametrize("contents", ["0\n", "2\n", "1 1\n", "", "true\n", " 0 \n"])
def test_shared_writer_supported_false_when_protected_hardlinks_not_exactly_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, contents: str
) -> None:
    users = _make_users_dir(tmp_path / "users")
    protected = tmp_path / "protected_hardlinks"
    protected.write_text(contents, encoding="ascii")
    monkeypatch.setattr("core.telemetry.capability.sys.platform", "linux")

    assert (
        shared_writer_supported(users, protected_hardlinks_path=protected) is False
    )


def test_shared_writer_supported_accepts_stripped_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    users = _make_users_dir(tmp_path / "users")
    protected = tmp_path / "protected_hardlinks"
    protected.write_text(" 1 \n", encoding="ascii")
    monkeypatch.setattr("core.telemetry.capability.sys.platform", "linux")

    assert (
        shared_writer_supported(users, protected_hardlinks_path=protected) is True
    )


def test_shared_writer_supported_false_when_protected_file_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    users = _make_users_dir(tmp_path / "users")
    protected = tmp_path / "missing_protected"
    monkeypatch.setattr("core.telemetry.capability.sys.platform", "linux")

    assert (
        shared_writer_supported(users, protected_hardlinks_path=protected) is False
    )


def test_shared_writer_supported_false_when_users_dir_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    protected = tmp_path / "protected_hardlinks"
    protected.write_text("1\n", encoding="ascii")
    monkeypatch.setattr("core.telemetry.capability.sys.platform", "linux")

    assert (
        shared_writer_supported(
            tmp_path / "users", protected_hardlinks_path=protected
        )
        is False
    )


def test_shared_writer_supported_false_when_users_is_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    users = tmp_path / "users"
    users.write_text("not-a-dir", encoding="utf-8")
    protected = tmp_path / "protected_hardlinks"
    protected.write_text("1\n", encoding="ascii")
    monkeypatch.setattr("core.telemetry.capability.sys.platform", "linux")

    assert (
        shared_writer_supported(users, protected_hardlinks_path=protected) is False
    )


def test_shared_writer_supported_false_when_users_is_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = _make_users_dir(tmp_path / "real_users")
    users = tmp_path / "users"
    users.symlink_to(real)
    protected = tmp_path / "protected_hardlinks"
    protected.write_text("1\n", encoding="ascii")
    monkeypatch.setattr("core.telemetry.capability.sys.platform", "linux")

    assert (
        shared_writer_supported(users, protected_hardlinks_path=protected) is False
    )


@pytest.mark.parametrize(
    "mode",
    [
        0o0777,  # missing sticky
        0o1775,  # missing world write
        0o1776,  # missing world search
        0o0755,
        0o0700,
    ],
)
def test_shared_writer_supported_false_when_mode_lacks_sticky_world_write_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: int
) -> None:
    users = _make_users_dir(tmp_path / "users", mode=mode)
    protected = tmp_path / "protected_hardlinks"
    protected.write_text("1\n", encoding="ascii")
    monkeypatch.setattr("core.telemetry.capability.sys.platform", "linux")

    assert (
        shared_writer_supported(users, protected_hardlinks_path=protected) is False
    )


def test_shared_writer_supported_never_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("core.telemetry.capability.sys.platform", "linux")

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("unexpected")

    monkeypatch.setattr("core.telemetry.capability.os.lstat", boom)

    assert (
        shared_writer_supported(
            tmp_path / "users",
            protected_hardlinks_path=tmp_path / "protected_hardlinks",
        )
        is False
    )


def test_shared_writer_supported_does_not_create_users_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    users = tmp_path / "users"
    protected = tmp_path / "protected_hardlinks"
    protected.write_text("1\n", encoding="ascii")
    monkeypatch.setattr("core.telemetry.capability.sys.platform", "linux")

    assert shared_writer_supported(users, protected_hardlinks_path=protected) is False
    assert not users.exists()
