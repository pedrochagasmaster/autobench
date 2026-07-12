"""Effective-UID identity resolution and filename token encoding."""

from __future__ import annotations

import base64
import os
import pwd
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,172}$")
_MAX_USERNAME_BYTES = 128


@dataclass(frozen=True)
class Identity:
    uid: int
    username: str
    token: str


def validate_username(username: str) -> str:
    if not isinstance(username, str):
        raise ValueError("username must be a string")
    if not username:
        raise ValueError("username must be nonempty")
    if username in (".", ".."):
        raise ValueError("username must not be '.' or '..'")
    if "/" in username or "\\" in username:
        raise ValueError("username must not contain path separators")
    if any(unicodedata.category(ch).startswith("C") for ch in username):
        raise ValueError("username must not contain control characters")
    if len(username.encode("utf-8")) > _MAX_USERNAME_BYTES:
        raise ValueError(f"username must be at most {_MAX_USERNAME_BYTES} UTF-8 bytes")
    return username


def encode_user_token(username: str) -> str:
    validated = validate_username(username)
    token = base64.urlsafe_b64encode(validated.encode("utf-8")).rstrip(b"=").decode("ascii")
    if not _TOKEN_RE.fullmatch(token):
        raise ValueError("encoded username token is invalid")
    return token


def resolve_identity(
    *,
    geteuid: Callable[[], int] = os.geteuid,
    getpwuid: Callable[[int], Any] = pwd.getpwuid,
) -> Identity:
    uid = geteuid()
    pw_entry = getpwuid(uid)
    username = validate_username(pw_entry.pw_name)
    return Identity(uid=uid, username=username, token=encode_user_token(username))


def lookup_uid(username: str) -> int:
    validated = validate_username(username)
    return pwd.getpwnam(validated).pw_uid
