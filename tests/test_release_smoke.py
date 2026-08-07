"""Contract tests for the native release smoke path."""

from __future__ import annotations

from scripts.release_smoke import run


def test_release_smoke_solves_and_verifies_fixture() -> None:
    message = run()
    assert message.startswith("release smoke passed:")
    assert "verify=passed" in message
    assert "certificate=passed" in message
    assert "highspy=" in message
    assert "numpy=" in message
    assert "scipy=" in message
