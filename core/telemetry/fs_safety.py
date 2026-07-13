"""Shared filesystem path-safety helpers for telemetry."""

from __future__ import annotations

import os
import stat
from pathlib import Path


def lexical_absolute_path(path: Path | str) -> Path:
    """Return a lexical absolute path using cwd + normpath (no symlink follow).

    Equivalent to ``Path(os.path.abspath(...))`` / ``normpath(join(cwd, path))``.
    Never calls ``Path.resolve`` and never follows symlinks while building the
    absolute string.
    """
    return Path(os.path.abspath(os.fspath(path)))


def absolute_path_prefixes(path: Path) -> tuple[Path, ...]:
    """Return lexical absolute prefixes from ``/`` through ``path`` (no resolve)."""
    if not path.is_absolute():
        raise ValueError(f"path must be absolute: {path}")
    parts = path.parts
    acc = Path(parts[0])
    out: list[Path] = [acc]
    for part in parts[1:]:
        acc = acc / part
        out.append(acc)
    return tuple(out)


def existing_ancestors_are_real_dirs(path: Path) -> bool:
    """Return True when every existing ancestor of ``path`` is a real directory.

    Relative paths are converted to a lexical absolute path via cwd +
    ``os.path.abspath`` / ``normpath`` (no ``Path.resolve``, no symlink follow
    during absolutization). Then each existing prefix is checked with ``lstat``.
    Missing components are allowed; the first missing prefix ends the walk.
    Never raises.
    """
    try:
        abs_path = lexical_absolute_path(path)
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
