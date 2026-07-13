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

    abs_path = lexical_absolute_path(Path("link/users"))
    assert abs_path == tmp_path / "link" / "users"
    assert "link" in abs_path.parts
    assert abs_path.is_absolute()


def test_lexical_absolute_path_preserves_dot_and_dotdot_components(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Pass str: pathlib.Path collapses "." before we can preserve it.
    monkeypatch.chdir(tmp_path)
    lex = lexical_absolute_path("a/./b/../c")
    assert os.fspath(lex) == f"{tmp_path.as_posix()}/a/./b/../c"
    assert "." in lex.parts
    assert ".." in lex.parts


def test_lexical_absolute_path_preserves_absolute_raw_components(
    tmp_path: Path,
) -> None:
    # Construct with uncollapsed string so Path keeps components.
    uncollapsed = Path(str(tmp_path) + "/a/../b")
    assert lexical_absolute_path(uncollapsed) == uncollapsed
    assert ".." in lexical_absolute_path(uncollapsed).parts


def test_existing_ancestors_accepts_relative_safe_users_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    users = tmp_path / "shared" / "users"
    users.mkdir(parents=True)
    users.chmod(0o1777)

    assert existing_ancestors_are_real_dirs(Path("shared/users")) is True


def test_existing_ancestors_accepts_dotdot_through_real_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a").mkdir()
    users = tmp_path / "shared" / "users"
    users.mkdir(parents=True)

    rel = Path("a/../shared/users")
    assert existing_ancestors_are_real_dirs(rel) is True
    lex = lexical_absolute_path(rel)
    assert ".." in lex.parts
    assert "a" in lex.parts


def test_existing_ancestors_rejects_symlink_before_dotdot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """escape/../shared must not collapse past a symlink ancestor."""
    monkeypatch.chdir(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    escape = tmp_path / "escape"
    escape.symlink_to(elsewhere)
    users = tmp_path / "shared" / "users"
    users.mkdir(parents=True)
    users.chmod(0o1777)

    rel = Path("escape/../shared/users")
    # Kernel target differs from lexical shared/users; must fail closed.
    assert existing_ancestors_are_real_dirs(rel) is False
    assert "escape" in lexical_absolute_path(rel).parts


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


def test_lexical_absolute_path_cwd_captured_not_later_chdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    captured = lexical_absolute_path(Path("shared/users"), cwd=tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(other)
    assert lexical_absolute_path(Path("shared/users"), cwd=tmp_path) == captured
    assert captured == tmp_path / "shared" / "users"


def test_absolute_path_prefixes_requires_absolute(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="absolute"):
        absolute_path_prefixes(Path("relative/users"))


def test_absolute_path_prefixes_keeps_dotdot(tmp_path: Path) -> None:
    path = Path(str(tmp_path) + "/a/../b")
    prefixes = absolute_path_prefixes(path)
    assert any(p.name == ".." or ".." in p.parts for p in prefixes)
