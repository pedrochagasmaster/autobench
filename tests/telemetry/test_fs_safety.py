"""Tests for core.telemetry.fs_safety path ancestor checks."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.telemetry.fs_safety import (
    absolute_path_prefixes,
    existing_ancestors_are_real_dirs,
    lexical_absolute_path,
)


def test_lexical_absolute_path_joins_cwd_without_resolve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    victim = tmp_path / "victim"
    victim.mkdir()
    link = tmp_path / "link"
    link.symlink_to(victim)

    # Must not follow link via Path.resolve(); keep lexical link component.
    abs_path = lexical_absolute_path(Path("link/users"))
    assert abs_path == tmp_path / "link" / "users"
    assert "link" in abs_path.parts
    assert abs_path.is_absolute()


def test_existing_ancestors_accepts_relative_safe_users_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    users = tmp_path / "shared" / "users"
    users.mkdir(parents=True)
    users.chmod(0o1777)

    assert existing_ancestors_are_real_dirs(Path("shared/users")) is True
    assert existing_ancestors_are_real_dirs(Path("./shared/./users")) is True


def test_existing_ancestors_normalizes_relative_dotdot_safely(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    users = tmp_path / "telem" / "users"
    users.mkdir(parents=True)

    assert (
        existing_ancestors_are_real_dirs(Path("telem/./nested/../users")) is True
    )
    # Lexical absolute form collapses ./ and ../ without resolve.
    assert lexical_absolute_path(Path("telem/./nested/../users")) == users


def test_existing_ancestors_rejects_relative_symlink_ancestor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    victim = tmp_path / "victim"
    victim.mkdir()
    link = tmp_path / "autobench"
    link.symlink_to(victim)
    users = link / "telemetry" / "users"
    users.mkdir(parents=True)

    assert existing_ancestors_are_real_dirs(Path("autobench/telemetry/users")) is False


def test_absolute_path_still_rejects_symlink_ancestor(tmp_path: Path) -> None:
    victim = tmp_path / "victim"
    victim.mkdir()
    link = tmp_path / "autobench"
    link.symlink_to(victim)
    users = link / "telemetry" / "users"
    users.mkdir(parents=True)

    assert existing_ancestors_are_real_dirs(users) is False


def test_absolute_path_prefixes_requires_absolute(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="absolute"):
        absolute_path_prefixes(Path("relative/users"))
