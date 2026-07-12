"""Runtime capability gate for the shared telemetry writer."""

from __future__ import annotations

import fcntl
import os
import stat
import sys
from pathlib import Path

_REQUIRED_OS_FLAGS = (
    "O_APPEND",
    "O_CREAT",
    "O_WRONLY",
    "O_CLOEXEC",
    "O_NONBLOCK",
    "O_NOFOLLOW",
)
_REQUIRED_FCNTL_ATTRS = ("flock", "LOCK_EX", "LOCK_NB")
_STICKY_WORLD_WRITE_SEARCH = stat.S_ISVTX | stat.S_IWOTH | stat.S_IXOTH


def shared_writer_supported(
    users_dir: Path,
    *,
    protected_hardlinks_path: Path = Path("/proc/sys/fs/protected_hardlinks"),
) -> bool:
    """Return whether shared telemetry append is safe on this host.

    Never raises. Returns False unless Linux, required open/lock primitives
    exist, protected_hardlinks is enabled, and ``users_dir`` is an existing
    non-symlink directory with sticky + world-write + world-search mode.
    """
    try:
        if sys.platform != "linux":
            return False
        for name in _REQUIRED_OS_FLAGS:
            if not hasattr(os, name):
                return False
        for name in _REQUIRED_FCNTL_ATTRS:
            if not hasattr(fcntl, name):
                return False
        raw = protected_hardlinks_path.read_text(encoding="ascii")
        if raw.strip() != "1":
            return False
        st = os.lstat(users_dir)
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
            return False
        if (stat.S_IMODE(st.st_mode) & _STICKY_WORLD_WRITE_SEARCH) != (
            _STICKY_WORLD_WRITE_SEARCH
        ):
            return False
        return True
    except Exception:
        return False
