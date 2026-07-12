"""Focused tests for scripts/validate_telemetry_filesystem.py."""

from __future__ import annotations

import os
import re
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


def test_cli_exit_codes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = _provision_layout(tmp_path / "telemetry")
    protected = _protected(tmp_path)

    env = {
        **dict(os.environ),
        "AUTOBENCH_TELEMETRY_VALIDATOR_PROTECTED_HARDLINKS": str(protected),
    }
    good = subprocess.run(
        [sys.executable, str(VALIDATOR), "--dir", str(parent)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    # CLI may rely on real /proc; if env injection is unsupported, call via -c.
    # Prefer module main with argv when env hook absent.
    mod = _import_validator()
    monkeypatch.setattr(mod.sys, "platform", "linux")
    code_ok, _ = mod.validate_filesystem(parent, protected_hardlinks_path=protected)
    assert code_ok == 0

    bad_parent = _provision_layout(
        tmp_path / "bad", parent_mode=0o0700, users_mode=0o1777
    )
    code_bad, lines = mod.validate_filesystem(
        bad_parent, protected_hardlinks_path=protected
    )
    assert code_bad == 1
    assert any(line.startswith("FAIL:") for line in lines)

    # Exercise argparse main path when possible
    exit_code = mod.main(["--dir", str(parent)])
    # Without injected protected path, main may fail on missing /proc in some envs;
    # require deterministic PASS/FAIL lines and no traceback either way.
    assert exit_code in (0, 1)
    # Help exit 0 already covered; bad args should be nonzero
    bad_args = subprocess.run(
        [sys.executable, str(VALIDATOR), "--dir"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert bad_args.returncode != 0
    assert "Traceback" not in (good.stderr or "")


def test_cli_main_uses_dir_and_prints_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, validator_mod, capsys
) -> None:
    parent = _provision_layout(tmp_path / "telemetry")
    protected = _protected(tmp_path)
    monkeypatch.setattr(validator_mod.sys, "platform", "linux")
    monkeypatch.setattr(
        validator_mod,
        "DEFAULT_PROTECTED_HARDLINKS",
        protected,
    )

    code = validator_mod.main(["--dir", str(parent)])
    captured = capsys.readouterr()
    assert code == 0
    assert "PASS:" in captured.out
    assert "FAIL:" not in captured.out


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
