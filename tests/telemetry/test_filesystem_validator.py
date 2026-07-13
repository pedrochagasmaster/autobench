"""Focused tests for scripts/validate_telemetry_filesystem.py."""

from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts" / "validate_telemetry_filesystem.py"


def _provision_layout(parent: Path, *, parent_mode: int = 0o0755, users_mode: int = 0o1777) -> Path:
    users = parent / "users"
    parent.mkdir(parents=True, exist_ok=True)
    users.mkdir(parents=True, exist_ok=True)
    parent.chmod(parent_mode)
    users.chmod(users_mode)
    return parent


def _protected(tmp_path: Path, contents: str = "1\n") -> Path:
    path = tmp_path / "protected_hardlinks"
    path.write_text(contents, encoding="ascii")
    return path


def _import_validator():
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import validate_telemetry_filesystem as mod
    finally:
        # Keep importable; path already present is fine for subsequent tests.
        pass
    return mod


@pytest.fixture
def validator_mod():
    return _import_validator()


def test_validator_module_is_importable() -> None:
    assert VALIDATOR.is_file()
    mod = _import_validator()
    assert hasattr(mod, "main")
    assert hasattr(mod, "validate_filesystem")


def test_cli_help_includes_example_and_dir_flag() -> None:
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "--dir" in combined
    assert "Example" in combined
    assert "validate_telemetry_filesystem.py" in combined


def test_happy_path_pass_exit_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, validator_mod
) -> None:
    parent = _provision_layout(tmp_path / "telemetry")
    protected = _protected(tmp_path)
    monkeypatch.setattr(validator_mod.sys, "platform", "linux")

    code, lines = validator_mod.validate_filesystem(
        parent,
        protected_hardlinks_path=protected,
    )
    assert code == 0
    assert lines
    assert all(line.startswith("PASS:") for line in lines)
    assert not any(line.startswith("FAIL:") for line in lines)
    # No leftover probes under users/
    leftover = [p for p in (parent / "users").iterdir() if p.name.startswith(".")]
    assert leftover == []


def test_repeat_run_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, validator_mod
) -> None:
    parent = _provision_layout(tmp_path / "telemetry")
    protected = _protected(tmp_path)
    monkeypatch.setattr(validator_mod.sys, "platform", "linux")

    first = validator_mod.validate_filesystem(
        parent, protected_hardlinks_path=protected
    )
    second = validator_mod.validate_filesystem(
        parent, protected_hardlinks_path=protected
    )
    assert first[0] == 0
    assert second[0] == 0
    assert first[1] == second[1]


@pytest.mark.parametrize(
    ("parent_mode", "users_mode"),
    [
        (0o0755, 0o0777),
        (0o0775, 0o1777),
        (0o0700, 0o1777),
        (0o0755, 0o1755),
    ],
)
def test_wrong_modes_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    validator_mod,
    parent_mode: int,
    users_mode: int,
) -> None:
    parent = _provision_layout(
        tmp_path / "telemetry", parent_mode=parent_mode, users_mode=users_mode
    )
    protected = _protected(tmp_path)
    monkeypatch.setattr(validator_mod.sys, "platform", "linux")

    code, lines = validator_mod.validate_filesystem(
        parent, protected_hardlinks_path=protected
    )
    assert code == 1
    assert any(line.startswith("FAIL:") for line in lines)
    assert not any("Traceback" in line for line in lines)


def test_symlink_parent_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, validator_mod
) -> None:
    real = _provision_layout(tmp_path / "real_telemetry")
    parent = tmp_path / "telemetry"
    parent.symlink_to(real)
    protected = _protected(tmp_path)
    monkeypatch.setattr(validator_mod.sys, "platform", "linux")

    code, lines = validator_mod.validate_filesystem(
        parent, protected_hardlinks_path=protected
    )
    assert code == 1
    assert any("symlink" in line.lower() for line in lines if line.startswith("FAIL:"))


def test_symlink_users_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, validator_mod
) -> None:
    parent = tmp_path / "telemetry"
    parent.mkdir()
    parent.chmod(0o0755)
    real_users = tmp_path / "real_users"
    real_users.mkdir()
    real_users.chmod(0o1777)
    (parent / "users").symlink_to(real_users)
    protected = _protected(tmp_path)
    monkeypatch.setattr(validator_mod.sys, "platform", "linux")

    code, lines = validator_mod.validate_filesystem(
        parent, protected_hardlinks_path=protected
    )
    assert code == 1
    assert any("symlink" in line.lower() for line in lines if line.startswith("FAIL:"))


def test_missing_protected_hardlinks_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, validator_mod
) -> None:
    parent = _provision_layout(tmp_path / "telemetry")
    missing = tmp_path / "missing_protected"
    monkeypatch.setattr(validator_mod.sys, "platform", "linux")

    code, lines = validator_mod.validate_filesystem(
        parent, protected_hardlinks_path=missing
    )
    assert code == 1
    assert any(
        "protected_hardlinks" in line.lower() for line in lines if line.startswith("FAIL:")
    )


def test_protected_hardlinks_not_one_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, validator_mod
) -> None:
    parent = _provision_layout(tmp_path / "telemetry")
    protected = _protected(tmp_path, "0\n")
    monkeypatch.setattr(validator_mod.sys, "platform", "linux")

    code, lines = validator_mod.validate_filesystem(
        parent, protected_hardlinks_path=protected
    )
    assert code == 1
    assert any(
        "protected_hardlinks" in line.lower() for line in lines if line.startswith("FAIL:")
    )


def test_lock_child_semantics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, validator_mod
) -> None:
    parent = _provision_layout(tmp_path / "telemetry")
    protected = _protected(tmp_path)
    monkeypatch.setattr(validator_mod.sys, "platform", "linux")

    code, lines = validator_mod.validate_filesystem(
        parent, protected_hardlinks_path=protected
    )
    assert code == 0
    assert any("flock" in line.lower() or "lock" in line.lower() for line in lines)


def test_fifo_timeout_logic_does_not_hang(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, validator_mod
) -> None:
    parent = _provision_layout(tmp_path / "telemetry")
    protected = _protected(tmp_path)
    monkeypatch.setattr(validator_mod.sys, "platform", "linux")

    started = time.monotonic()
    code, lines = validator_mod.validate_filesystem(
        parent, protected_hardlinks_path=protected
    )
    elapsed = time.monotonic() - started
    assert code == 0
    assert elapsed < 5.0
    assert any("fifo" in line.lower() or "nonblock" in line.lower() for line in lines)


def test_cleanup_after_injected_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, validator_mod
) -> None:
    parent = _provision_layout(tmp_path / "telemetry")
    protected = _protected(tmp_path)
    monkeypatch.setattr(validator_mod.sys, "platform", "linux")

    real_fchmod = os.fchmod

    def boom(fd: int, mode: int) -> None:
        raise OSError("injected fchmod failure")

    monkeypatch.setattr(validator_mod.os, "fchmod", boom)

    code, lines = validator_mod.validate_filesystem(
        parent, protected_hardlinks_path=protected
    )
    assert code == 1
    users = parent / "users"
    leftovers = list(users.iterdir())
    assert leftovers == [], leftovers
    # restore sanity for other tests
    monkeypatch.setattr(validator_mod.os, "fchmod", real_fchmod)


def test_cli_exit_codes_are_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, validator_mod, capsys
) -> None:
    parent = _provision_layout(tmp_path / "telemetry")
    protected = _protected(tmp_path)
    monkeypatch.setattr(validator_mod.sys, "platform", "linux")
    monkeypatch.setattr(validator_mod, "DEFAULT_PROTECTED_HARDLINKS", protected)

    assert validator_mod.main(["--dir", str(parent)]) == 0
    out_ok = capsys.readouterr().out
    assert "PASS:" in out_ok
    assert "FAIL:" not in out_ok

    bad_parent = _provision_layout(
        tmp_path / "bad", parent_mode=0o0700, users_mode=0o1777
    )
    assert validator_mod.main(["--dir", str(bad_parent)]) == 1
    out_bad = capsys.readouterr().out
    assert "FAIL:" in out_bad

    bad_args = subprocess.run(
        [sys.executable, str(VALIDATOR), "--dir"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert bad_args.returncode != 0
    assert "Traceback" not in (bad_args.stderr or "")


@pytest.mark.parametrize(
    "raw",
    [
        "relative-telemetry",
        "./telemetry",
        "/",
        "///",
        "{base}/./telem",
        "{base}/other/../telem",
        "{base}/./telem/",
        "{base}/other/../telem///",
    ],
)
def test_validator_rejects_unsafe_dir_before_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    validator_mod,
    raw: str,
    capsys,
) -> None:
    """Absolute/no-dot/non-root policy must fail before any filesystem probe."""
    protected = _protected(tmp_path)
    monkeypatch.setattr(validator_mod.sys, "platform", "linux")
    monkeypatch.setattr(validator_mod, "DEFAULT_PROTECTED_HARDLINKS", protected)

    base = tmp_path / "base"
    base.mkdir(mode=0o0700)
    # Real layout at the resolved destination so a missing lexical check would probe.
    real = _provision_layout(base / "telem")
    (base / "other").mkdir(mode=0o0700)
    target = raw.format(base=str(base))
    before_mode = stat.S_IMODE(base.stat().st_mode)
    before_real_mode = stat.S_IMODE(real.stat().st_mode)
    before_users = set((real / "users").iterdir())

    probed: list[object] = []

    real_probe = validator_mod._probe_file_ops

    def tracking_probe(*args, **kwargs):
        probed.append(True)
        return real_probe(*args, **kwargs)

    monkeypatch.setattr(validator_mod, "_probe_file_ops", tracking_probe)

    code = validator_mod.main(["--dir", target])
    out = capsys.readouterr()
    combined = (out.out + out.err).lower()
    assert code == 1
    assert "FAIL:" in (out.out + out.err)
    assert "traceback" not in combined
    assert probed == [], "filesystem probe must not run for unsafe --dir"
    assert stat.S_IMODE(base.stat().st_mode) == before_mode
    assert stat.S_IMODE(real.stat().st_mode) == before_real_mode
    assert set((real / "users").iterdir()) == before_users
    assert not (tmp_path / "users").exists()
    assert any(
        token in combined
        for token in ("absolute", "unsafe", "refusing", "dot", "root", "empty", "invalid")
    )


def test_normalize_operator_dir_preserves_lexical_dots_from_raw_string(
    validator_mod,
) -> None:
    with pytest.raises(validator_mod.InvalidTelemetryDirError) as excinfo:
        validator_mod.normalize_operator_telemetry_dir("/tmp/./x")
    assert "dot" in str(excinfo.value).lower() or "." in str(excinfo.value)

    with pytest.raises(validator_mod.InvalidTelemetryDirError):
        validator_mod.normalize_operator_telemetry_dir("/tmp/x/../y")

    with pytest.raises(validator_mod.InvalidTelemetryDirError):
        validator_mod.normalize_operator_telemetry_dir("relative")

    with pytest.raises(validator_mod.InvalidTelemetryDirError):
        validator_mod.normalize_operator_telemetry_dir("/")


def test_validator_accepts_absolute_trailing_and_repeated_slashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, validator_mod, capsys
) -> None:
    parent = _provision_layout(tmp_path / "telem")
    protected = _protected(tmp_path)
    monkeypatch.setattr(validator_mod.sys, "platform", "linux")
    monkeypatch.setattr(validator_mod, "DEFAULT_PROTECTED_HARDLINKS", protected)

    weird = str(tmp_path) + "///telem///"
    normalized = validator_mod.normalize_operator_telemetry_dir(weird)
    assert normalized == parent
    assert ".." not in normalized.parts
    assert "." not in normalized.parts

    code = validator_mod.main(["--dir", weird])
    out = capsys.readouterr().out
    assert code == 0
    assert "PASS:" in out
    assert "FAIL:" not in out


def test_run_internal_child_timeout_kills_process_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, validator_mod
) -> None:
    """Timeout path must return promptly, attempt killpg, and bound the second wait."""
    killpg_calls: list[tuple[int, int]] = []
    communicate_timeouts: list[float | None] = []
    closed: list[str] = []

    class StubPopenClose:
        def __init__(self, *args, **kwargs):
            assert kwargs.get("start_new_session") is True
            self.pid = 4242
            self.stdout = type("P", (), {"close": lambda self: closed.append("stdout")})()
            self.stderr = type("P", (), {"close": lambda self: closed.append("stderr")})()
            self.returncode = None

        def communicate(self, timeout=None):
            communicate_timeouts.append(timeout)
            raise subprocess.TimeoutExpired(cmd="stub", timeout=timeout)

        def kill(self):
            raise AssertionError("proc.kill should not be needed when killpg works")

    monkeypatch.setattr(validator_mod.subprocess, "Popen", StubPopenClose)
    monkeypatch.setattr(
        validator_mod.os,
        "killpg",
        lambda pid, sig: killpg_calls.append((pid, sig)),
    )

    started = time.monotonic()
    status, detail = validator_mod._run_internal_child(
        "lock-contend", tmp_path / "x", timeout_s=0.05
    )
    elapsed = time.monotonic() - started

    assert status == "timeout"
    assert detail is None
    assert elapsed < 1.0
    assert killpg_calls and killpg_calls[0][0] == 4242
    assert len(communicate_timeouts) >= 2
    assert communicate_timeouts[0] == 0.05
    assert communicate_timeouts[1] is not None and communicate_timeouts[1] <= 1.0
    assert "stdout" in closed and "stderr" in closed


def test_run_internal_child_timeout_returns_without_unbounded_wait(
    monkeypatch: pytest.MonkeyPatch, validator_mod, tmp_path: Path
) -> None:
    waits: list[float | None] = []

    class StubbornPopen:
        def __init__(self, *args, **kwargs):
            self.pid = 99
            self.stdout = type("P", (), {"close": lambda self: waits.append("close-out")})()
            self.stderr = type("P", (), {"close": lambda self: waits.append("close-err")})()
            self.returncode = None

        def communicate(self, timeout=None):
            waits.append(timeout)
            raise subprocess.TimeoutExpired(cmd=["stub"], timeout=timeout or 0)

    monkeypatch.setattr(validator_mod.subprocess, "Popen", StubbornPopen)
    monkeypatch.setattr(validator_mod.os, "killpg", lambda *a, **k: None)

    started = time.monotonic()
    status, _ = validator_mod._run_internal_child(
        validator_mod._INTERNAL_FIFO, tmp_path / "f", timeout_s=0.02
    )
    assert status == "timeout"
    assert time.monotonic() - started < 1.0
    # First timeout + bounded second communicate; no None/unbounded wait.
    assert waits[0] == 0.02
    assert isinstance(waits[1], (int, float)) and waits[1] <= 1.0
    assert "close-out" in waits and "close-err" in waits


def test_run_internal_child_normal_success_no_zombie(
    tmp_path: Path, validator_mod, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = _provision_layout(tmp_path / "telemetry")
    probe = parent / "users" / ".lock-probe"
    fd = os.open(
        str(probe),
        os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_CLOEXEC | os.O_NONBLOCK,
        0o0600,
    )
    try:
        status, detail = validator_mod._run_lock_child(probe, timeout_s=2.0)
        assert status == "locked"
        assert detail == 0
    finally:
        os.close(fd)
        probe.unlink(missing_ok=True)


def test_fifo_probe_fails_on_unexpected_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, validator_mod
) -> None:
    parent = _provision_layout(tmp_path / "telemetry")
    protected = _protected(tmp_path)
    monkeypatch.setattr(validator_mod.sys, "platform", "linux")

    def fake_fifo(_path):
        return ("opened", 0)

    monkeypatch.setattr(validator_mod, "_run_fifo_child", fake_fifo)
    code, lines = validator_mod.validate_filesystem(
        parent, protected_hardlinks_path=protected
    )
    assert code == 1
    assert any(
        "fifo" in line.lower() and line.startswith("FAIL:") for line in lines
    )


def test_does_not_read_telemetry_payloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, validator_mod
) -> None:
    parent = _provision_layout(tmp_path / "telemetry")
    users = parent / "users"
    payload = users / "existing-user.jsonl"
    payload.write_text('{"event":"session_start"}\n', encoding="utf-8")
    payload.chmod(0o0644)
    protected = _protected(tmp_path)
    monkeypatch.setattr(validator_mod.sys, "platform", "linux")

    before = payload.read_bytes()
    code, _ = validator_mod.validate_filesystem(
        parent, protected_hardlinks_path=protected
    )
    assert code == 0
    assert payload.read_bytes() == before
    assert payload.exists()


def test_probe_names_are_unpredictable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, validator_mod
) -> None:
    parent = _provision_layout(tmp_path / "telemetry")
    protected = _protected(tmp_path)
    monkeypatch.setattr(validator_mod.sys, "platform", "linux")

    seen: list[str] = []
    real_open = os.open

    def tracking_open(path, flags, mode=0o777, *args, **kwargs):
        name = os.fsdecode(path) if isinstance(path, (bytes, os.PathLike)) else str(path)
        if "/users/" in name.replace("\\", "/"):
            seen.append(Path(name).name)
        return real_open(path, flags, mode, *args, **kwargs)

    monkeypatch.setattr(validator_mod.os, "open", tracking_open)
    code, _ = validator_mod.validate_filesystem(
        parent, protected_hardlinks_path=protected
    )
    assert code == 0
    assert seen
    for name in seen:
        assert name not in {"probe", "test", "tmp", "fifo"}
        assert re.fullmatch(r"[A-Za-z0-9._-]{8,}", name) or name.startswith(".")


def test_non_linux_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, validator_mod
) -> None:
    parent = _provision_layout(tmp_path / "telemetry")
    protected = _protected(tmp_path)
    monkeypatch.setattr(validator_mod.sys, "platform", "darwin")

    code, lines = validator_mod.validate_filesystem(
        parent, protected_hardlinks_path=protected
    )
    assert code == 1
    assert any("linux" in line.lower() for line in lines if line.startswith("FAIL:"))


def test_source_has_no_inline_imports() -> None:
    import ast

    tree = ast.parse(VALIDATOR.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if child is node:
                    continue
                if isinstance(child, (ast.Import, ast.ImportFrom)):
                    # Allow only if nested function definitions aren't walking
                    # into nested scopes incorrectly — check lineno within body.
                    if (
                        node.body
                        and child.lineno >= node.body[0].lineno
                        and child.lineno <= (node.end_lineno or child.lineno)
                    ):
                        # Nested functions have their own body; skip if child is
                        # inside a nested function.
                        nested = False
                        for sub in node.body:
                            if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                if (
                                    sub.lineno
                                    <= child.lineno
                                    <= (sub.end_lineno or sub.lineno)
                                ):
                                    nested = True
                                    break
                        if nested:
                            continue
                        pytest.fail(
                            f"inline import in {node.name} at line {child.lineno}"
                        )
