"""Shared filesystem path-safety helpers for telemetry."""

from __future__ import annotations

import os
import stat
from pathlib import Path


class LexicalAbsolutePath(os.PathLike[str]):
    """Absolute path that preserves ``.``, ``..``, and symlink name components.

    pathlib ``Path`` collapses ``.`` on parse; this type keeps the raw lexical
    form for ancestor walks and subsequent open/lstat/listdir use.
    """

    __slots__ = ("_raw",)

    def __init__(self, raw: str) -> None:
        if not raw.startswith("/"):
            raise ValueError(f"path must be absolute: {raw}")
        self._raw = raw

    def __fspath__(self) -> str:
        return self._raw

    def __str__(self) -> str:
        return self._raw

    def __repr__(self) -> str:
        return f"LexicalAbsolutePath({self._raw!r})"

    def __hash__(self) -> int:
        return hash(self._raw)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, LexicalAbsolutePath):
            return self._raw == other._raw
        if isinstance(other, (str, Path)) or hasattr(other, "__fspath__"):
            try:
                return self._raw == os.fspath(other)
            except TypeError:
                return NotImplemented
        return NotImplemented

    @property
    def parts(self) -> tuple[str, ...]:
        if self._raw == "/":
            return ("/",)
        return ("/", *self._raw[1:].split("/"))

    @property
    def name(self) -> str:
        if self._raw == "/":
            return ""
        return self._raw.rsplit("/", 1)[-1]

    def is_absolute(self) -> bool:
        return True

    def exists(self) -> bool:
        try:
            os.stat(self._raw)
        except OSError:
            return False
        return True

    def stat(self) -> os.stat_result:
        return os.stat(self._raw)

    def read_bytes(self) -> bytes:
        with open(self._raw, "rb") as handle:
            return handle.read()

    def __truediv__(self, other: str | os.PathLike[str]) -> LexicalAbsolutePath:
        piece = os.fspath(other)
        if piece.startswith("/"):
            raise ValueError(f"cannot join absolute piece onto lexical path: {piece}")
        if piece == "":
            return LexicalAbsolutePath(self._raw)
        if self._raw.endswith("/"):
            return LexicalAbsolutePath(self._raw + piece)
        return LexicalAbsolutePath(f"{self._raw}/{piece}")


def lexical_absolute_path(
    path: Path | str | LexicalAbsolutePath | os.PathLike[str],
    *,
    cwd: Path | str | None = None,
) -> LexicalAbsolutePath:
    """Return an absolute path without collapsing ``.``, ``..``, or symlinks.

    Relative inputs are joined under ``cwd`` (default ``Path.cwd()``) by
    prepending the cwd string. Absolute inputs keep their raw components.
    Never calls ``Path.resolve``, ``os.path.abspath``, or ``os.path.normpath``.

    Note: constructing a ``pathlib.Path`` from a relative string that contains
    ``.`` collapses those components before this function sees them; pass a
    ``str`` (or an already-uncollapsed absolute form) to preserve ``.``.
    """
    if isinstance(path, LexicalAbsolutePath):
        return path
    raw = os.fspath(path)
    if raw.startswith("/"):
        return LexicalAbsolutePath(raw)
    if cwd is None:
        base = os.fspath(Path.cwd())
    else:
        base = os.fspath(cwd)
        if not base.startswith("/"):
            base = f"{os.fspath(Path.cwd())}/{base}"
    if raw == "" or raw == ".":
        return LexicalAbsolutePath(base if base != "/" else "/")
    if base.endswith("/"):
        return LexicalAbsolutePath(base + raw)
    return LexicalAbsolutePath(f"{base}/{raw}")


def absolute_path_prefixes(
    path: Path | LexicalAbsolutePath | str | os.PathLike[str],
) -> tuple[LexicalAbsolutePath, ...]:
    """Return lexical absolute prefixes from ``/`` through ``path`` (no resolve)."""
    if isinstance(path, LexicalAbsolutePath):
        abs_path = path
    else:
        raw = os.fspath(path)
        if not raw.startswith("/"):
            raise ValueError(f"path must be absolute: {path}")
        abs_path = LexicalAbsolutePath(raw)
    parts = abs_path.parts
    acc = LexicalAbsolutePath("/")
    out: list[LexicalAbsolutePath] = [acc]
    for part in parts[1:]:
        acc = acc / part
        out.append(acc)
    return tuple(out)


def existing_ancestors_are_real_dirs(
    path: Path | str | LexicalAbsolutePath | os.PathLike[str],
    *,
    cwd: Path | str | None = None,
) -> bool:
    """Return True when every existing uncollapsed ancestor is a real directory.

    Relative paths are converted via :func:`lexical_absolute_path` (cwd prepend,
    no collapse). Each existing prefix is inspected with ``lstat`` so a symlink
    before ``..`` is rejected. Missing components end the walk successfully.
    Never raises.
    """
    try:
        abs_path = lexical_absolute_path(path, cwd=cwd)
        for prefix in absolute_path_prefixes(abs_path):
            try:
                st = os.lstat(prefix)
            except FileNotFoundError:
                return True
            except OSError:
                return False
            if stat.S_ISLNK(st.st_mode):
                return False
            if not stat.S_ISDIR(st.st_mode):
                return False
        return True
    except Exception:
        return False
