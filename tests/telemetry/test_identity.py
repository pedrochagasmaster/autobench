"""Tests for telemetry identity resolution and token encoding."""

from __future__ import annotations

import base64
import re
from typing import Any

import pytest

from core.telemetry.constants import (
    DATA_CAPACITY,
    DEFAULT_DAYS,
    DEFAULT_SHARED_DIR,
    DISABLED_VALUES,
    FUTURE_SKEW_S,
    MAX_RECORD_BYTES,
    PHYSICAL_QUEUE_CAPACITY,
    SCHEMA_VERSION,
    SHARED_GATE_SCAN_MAX_BYTES,
    SHUTDOWN_BUDGET_S,
)
from core.telemetry.identity import (
    Identity,
    encode_user_token,
    lookup_uid,
    resolve_identity,
    validate_username,
)

TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,172}$")


def test_constants_match_approved_design() -> None:
    assert SCHEMA_VERSION == 1
    assert MAX_RECORD_BYTES == 8192
    assert SHARED_GATE_SCAN_MAX_BYTES == 64 * 1024
    assert DATA_CAPACITY == 256
    assert PHYSICAL_QUEUE_CAPACITY == DATA_CAPACITY + 2
    assert SHUTDOWN_BUDGET_S == 0.250
    assert FUTURE_SKEW_S == 300
    assert DEFAULT_DAYS == 30
    assert DEFAULT_SHARED_DIR.as_posix() == "/ads_storage/autobench/telemetry"
    assert DISABLED_VALUES == frozenset({"0", "false", "off", "no"})


@pytest.mark.parametrize(
    "username",
    [
        "alice",
        "bob_user",
        "a" * 128,
        "user-name",
        "café",  # multi-byte UTF-8 within 128-byte limit
    ],
)
def test_validate_username_accepts_valid_names(username: str) -> None:
    assert validate_username(username) == username


@pytest.mark.parametrize(
    "username",
    [
        "",
        ".",
        "..",
        "has/slash",
        "has\\backslash",
        "bad\nname",
        "bad\x00name",
        "bad\x1fname",
        "bad\u007fname",
        "bad\u200bname",  # zero-width space (Cf)
        "a" * 129,
        "é" * 65,  # 130 UTF-8 bytes
    ],
)
def test_validate_username_rejects_invalid_names(username: str) -> None:
    with pytest.raises(ValueError):
        validate_username(username)


def test_encode_user_token_is_deterministic_unpadded_reversible() -> None:
    username = "alice"
    token = encode_user_token(username)
    assert TOKEN_RE.fullmatch(token)
    assert "=" not in token
    assert encode_user_token(username) == token
    padded = token + "=" * ((4 - len(token) % 4) % 4)
    decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    assert decoded == username


@pytest.mark.parametrize(
    "username",
    ["alice", "bob", "charlie", "user_1", "café", "a" * 128],
)
def test_encode_user_token_matches_grammar(username: str) -> None:
    token = encode_user_token(username)
    assert TOKEN_RE.fullmatch(token)


def test_encode_user_token_collision_free_for_fixture_set() -> None:
    names = ["alice", "bob", "charlie", "user_1", "café", "a" * 128, "a" * 127]
    tokens = [encode_user_token(n) for n in names]
    assert len(tokens) == len(set(tokens))


def test_encode_user_token_rejects_invalid_username() -> None:
    with pytest.raises(ValueError):
        encode_user_token("")


def test_resolve_identity_uses_effective_uid_not_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("USER", "env-user")
    monkeypatch.setenv("LOGNAME", "env-logname")

    class FakePw:
        pw_name = "real-nss-user"

    calls: dict[str, Any] = {}

    def fake_geteuid() -> int:
        calls["geteuid"] = True
        return 4242

    def fake_getpwuid(uid: int) -> Any:
        calls["uid"] = uid
        assert uid == 4242
        return FakePw()

    identity = resolve_identity(geteuid=fake_geteuid, getpwuid=fake_getpwuid)
    assert identity == Identity(
        uid=4242,
        username="real-nss-user",
        token=encode_user_token("real-nss-user"),
    )
    assert calls["geteuid"] is True
    assert calls["uid"] == 4242
    assert identity.username not in ("env-user", "env-logname")


def test_resolve_identity_rejects_invalid_nss_name() -> None:
    class FakePw:
        pw_name = "bad/name"

    with pytest.raises(ValueError):
        resolve_identity(geteuid=lambda: 1, getpwuid=lambda _uid: FakePw())


def test_identity_is_frozen() -> None:
    identity = Identity(uid=1, username="alice", token=encode_user_token("alice"))
    with pytest.raises(Exception):
        identity.uid = 2  # type: ignore[misc]


def test_lookup_uid_uses_nss(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakePw:
        pw_uid = 99

    def fake_getpwnam(name: str) -> Any:
        assert name == "alice"
        return FakePw()

    monkeypatch.setattr("core.telemetry.identity.pwd.getpwnam", fake_getpwnam)
    assert lookup_uid("alice") == 99


def test_lookup_uid_rejects_invalid_username() -> None:
    with pytest.raises(ValueError):
        lookup_uid(".")


def test_lookup_uid_propagates_keyerror(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getpwnam(name: str) -> Any:
        raise KeyError(name)

    monkeypatch.setattr("core.telemetry.identity.pwd.getpwnam", fake_getpwnam)
    with pytest.raises(KeyError):
        lookup_uid("missing-user")
