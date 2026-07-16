"""Shared runtime and launcher contracts."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _metadata(digest: str) -> dict[str, object]:
    return {"bundle_digest": digest, "pip_check": "passed"}


def _copy_launchers(root: Path) -> tuple[Path, Path]:
    target_bin = root / "bin"
    target_bin.mkdir(parents=True)
    for name in ("autobench", "autobench-cli", "runtime_check.sh"):
        shutil.copy2(ROOT / "bin" / name, target_bin / name)
        (target_bin / name).chmod(0o755)
    return target_bin / "autobench", target_bin / "autobench-cli"


def _active_runtime(root: Path, tmp_path: Path) -> tuple[Path, Path]:
    runtime = root / ".venv" / "releases" / ("a" * 64)
    (runtime / "bin").mkdir(parents=True)
    (runtime / ".complete.json").write_text(
        json.dumps(_metadata(runtime.name)), encoding="utf-8"
    )
    capture = tmp_path / "capture.txt"
    fake_python = runtime / "bin" / "python"
    fake_python.write_text(
        "#!/usr/bin/env sh\n"
        'printf \'%s\\n\' "$PWD" "$PYTHONPATH" "$AUTOBENCH_RUNTIME" "$@" > "$CAPTURE"\n',
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    try:
        (root / ".venv" / "current").symlink_to(
            Path("releases") / runtime.name, target_is_directory=True
        )
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")
    return runtime, capture


@pytest.mark.parametrize(
    ("launcher_name", "entrypoint"),
    [("autobench", "tui_app.py"), ("autobench-cli", "benchmark.py")],
)
def test_shared_launchers_forward_arguments_preserve_cwd_and_resolve_runtime(
    tmp_path: Path, launcher_name: str, entrypoint: str
) -> None:
    if shutil.which("sh") is None:
        pytest.skip("shared launcher smoke requires sh")
    root = tmp_path / "autobench-root"
    launchers = dict(zip(("autobench", "autobench-cli"), _copy_launchers(root)))
    runtime, capture = _active_runtime(root, tmp_path)
    launch_cwd = tmp_path / "work"
    launch_cwd.mkdir()
    env = os.environ.copy()
    env["CAPTURE"] = capture.resolve().as_posix()

    result = subprocess.run(
        ["sh", launchers[launcher_name].resolve().as_posix(), "--help", "two words"],
        cwd=launch_cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    lines = capture.read_text(encoding="utf-8").splitlines()
    assert Path(lines[0]).resolve() == launch_cwd.resolve()
    assert Path(lines[1]).resolve() == root.resolve()
    assert Path(lines[2]).resolve() == runtime.resolve()
    assert Path(lines[3]).resolve() == (root / entrypoint).resolve()
    assert lines[4:] == ["--help", "two words"]


def test_shared_launcher_fails_clearly_without_active_runtime(tmp_path: Path) -> None:
    if shutil.which("sh") is None:
        pytest.skip("shared launcher smoke requires sh")
    launcher, _cli = _copy_launchers(tmp_path / "root")

    result = subprocess.run(
        ["sh", launcher.resolve().as_posix()],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "shared runtime is not active" in result.stderr


def test_shared_launcher_rejects_corrupt_completion_metadata(tmp_path: Path) -> None:
    if shutil.which("sh") is None:
        pytest.skip("shared launcher smoke requires sh")
    root = tmp_path / "root"
    launcher, _cli = _copy_launchers(root)
    runtime = root / ".venv" / "releases" / ("c" * 64)
    (runtime / "bin").mkdir(parents=True)
    (runtime / "bin" / "python").write_text("", encoding="utf-8")
    (runtime / "bin" / "python").chmod(0o755)
    (runtime / ".complete.json").write_text("{}\n", encoding="utf-8")
    try:
        (root / ".venv" / "current").symlink_to(
            Path("releases") / runtime.name, target_is_directory=True
        )
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    result = subprocess.run(
        ["sh", launcher.resolve().as_posix()],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "completion metadata is corrupt" in result.stderr


def test_shared_launcher_rejects_runtime_outside_release_root(tmp_path: Path) -> None:
    if shutil.which("sh") is None:
        pytest.skip("shared launcher smoke requires sh")
    root = tmp_path / "root"
    launcher, _cli = _copy_launchers(root)
    rogue = tmp_path / "rogue"
    (rogue / "bin").mkdir(parents=True)
    (rogue / "bin" / "python").write_text("", encoding="utf-8")
    (rogue / "bin" / "python").chmod(0o755)
    (rogue / ".complete.json").write_text(
        json.dumps(_metadata(rogue.name)), encoding="utf-8"
    )
    (root / ".venv").mkdir(parents=True)
    try:
        (root / ".venv" / "current").symlink_to(rogue, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    result = subprocess.run(
        ["sh", launcher.resolve().as_posix()],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "resolves outside the release root" in result.stderr
