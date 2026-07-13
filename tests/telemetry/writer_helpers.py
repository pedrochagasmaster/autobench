"""Shared fixtures/helpers for the telemetry writer test modules."""

from __future__ import annotations

import os
import time
from types import SimpleNamespace


from core.telemetry.identity import Identity, encode_user_token

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


def _stat_standin(st: os.stat_result, *, uid: int) -> SimpleNamespace:
    """Stand-in preserving fields the writer reads (stat_result has no replace())."""
    return SimpleNamespace(
        st_mode=st.st_mode,
        st_uid=uid,
        st_nlink=st.st_nlink,
        st_gid=st.st_gid,
        st_ino=st.st_ino,
        st_dev=st.st_dev,
        st_size=st.st_size,
    )

