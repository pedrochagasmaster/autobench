"""Telemetry must import and degrade gracefully without POSIX modules.

The runtime capability gate is the single platform policy: on hosts without
``fcntl``/``pwd`` (or the safe ``os.O_*`` flags), telemetry imports cleanly,
helpers stay no-ops, and writes/reads fail closed instead of raising.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import core.telemetry as telemetry
from core.telemetry import capability, identity, writer
from core.telemetry.identity import resolve_identity

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_package_imports_and_degrades_without_posix_modules() -> None:
    """Block fcntl/pwd in a subprocess and confirm import + fail-closed paths."""
    code = textwrap.dedent(
        """
        import sys

        class _BlockPosix:
            def find_spec(self, name, path=None, target=None):
                if name in {"fcntl", "pwd"}:
                    raise ImportError(f"{name} blocked for portability test")
                return None

        sys.meta_path.insert(0, _BlockPosix())
        for mod in ("fcntl", "pwd"):
            sys.modules.pop(mod, None)

        import core.telemetry as telemetry
        from core.telemetry import capability, reader, writer

        assert capability.fcntl is None
        assert capability.shared_writer_supported("/nonexistent-telemetry") is False
        assert (
            writer.append_one(
                __import__("pathlib").Path("/nonexistent-telemetry/events.jsonl"),
                b'{"x":1}\\n',
                expected_uid=0,
                final_mode=0o600,
                create_private_parents=False,
            )
            is False
        )
        # Public helpers must stay silent no-ops (identity resolution raises
        # OSError internally; the helper wrappers swallow it).
        telemetry.start_session("tui")
        telemetry.end_session()
        # The CLI import chain must survive end to end.
        import benchmark  # noqa: F401
        print("portable-telemetry-ok")
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "portable-telemetry-ok" in proc.stdout


def test_capability_gate_false_when_fcntl_module_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("core.telemetry.capability.fcntl", None)
    assert capability.shared_writer_supported(tmp_path / "users") is False


def test_append_one_fails_closed_when_open_flags_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("core.telemetry.writer._OPEN_FLAGS", None)
    target = tmp_path / "events.jsonl"
    assert (
        writer.append_one(
            target,
            b'{"x":1}\n',
            expected_uid=0,
            final_mode=0o600,
            create_private_parents=False,
        )
        is False
    )
    assert not target.exists()


def test_append_one_fails_closed_when_fcntl_module_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("core.telemetry.writer.fcntl", None)
    target = tmp_path / "events.jsonl"
    assert (
        writer.append_one(
            target,
            b'{"x":1}\n',
            expected_uid=0,
            final_mode=0o600,
            create_private_parents=False,
        )
        is False
    )
    assert not target.exists()


def test_identity_raises_oserror_without_pwd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("core.telemetry.identity.pwd", None)
    with pytest.raises(OSError):
        resolve_identity()
    with pytest.raises(OSError):
        identity.lookup_uid("alice")


def test_public_helpers_no_op_without_pwd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("core.telemetry.identity.pwd", None)
    telemetry._reset_for_tests()
    try:
        telemetry.start_session("tui")
        telemetry.surface_viewed("share")
        telemetry.end_session()
    finally:
        telemetry._reset_for_tests()
