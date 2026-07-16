"""Release installation and per-user onboarding integration contracts."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from bundle_helpers import make_bundle

ROOT = Path(__file__).resolve().parents[1]


def _path(path: Path) -> str:
    return path.resolve().as_posix()


def _install_root(tmp_path: Path) -> Path:
    root = tmp_path / "autobench-root"
    for relative in (
        "install.sh",
        "onboard.sh",
        "shared_runtime.py",
        "bin/autobench",
        "bin/autobench-cli",
        "bin/runtime_check.sh",
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
        target.chmod(0o755)
    return root


def _approved_python(tmp_path: Path) -> Path:
    fake = tmp_path / "approved-python"
    fake.write_text(
        """#!/usr/bin/env sh
set -eu
case "${1:-}" in
  *shared_runtime.py) exec "__REAL_PYTHON__" "$@" ;;
esac
if [ "${1:-}" = "-m" ] && [ "${2:-}" = "venv" ]; then
  target=$3
  mkdir -p "$target/bin"
  cat > "$target/bin/python" <<'EOF'
#!/usr/bin/env sh
set -eu
printf '%s\n' "$*" >> "${RUNTIME_CALLS:?}"
if [ "${1:-}" = "-c" ]; then
  case "${2:-}" in
    *platform.python_version*) printf '3.10.99\n' ;;
  esac
fi
exit 0
EOF
  chmod 755 "$target/bin/python"
  exit 0
fi
exit 2
""".replace("__REAL_PYTHON__", _path(Path(sys.executable))),
        encoding="utf-8",
    )
    fake.chmod(0o755)
    return fake


def _install(
    root: Path, bundle: Path, approved: Path, calls: Path
) -> subprocess.CompletedProcess[str]:
    calls.touch()
    env = os.environ.copy()
    env.update(
        {
            "EDGE_DEPLOY_BUNDLE_DIR": _path(bundle),
            "AUTOBENCH_PYTHON_BIN": _path(approved),
            "RUNTIME_CALLS": _path(calls),
        }
    )
    return subprocess.run(
        ["sh", "install.sh"],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_release_installer_and_onboarding_have_separate_responsibilities() -> None:
    install = (ROOT / "install.sh").read_text(encoding="utf-8")
    onboard = (ROOT / "onboard.sh").read_text(encoding="utf-8")

    assert "AUTOBENCH_DATA_ROOT" not in install
    assert "shared_runtime.py" in install
    assert "installed_version" not in install
    assert "pip install" not in install
    assert "AUTOBENCH_DATA_ROOT" in onboard
    assert ".autobench/config" not in onboard  # paths are rooted through the variable
    assert " -m venv " not in onboard
    assert "pip install" not in onboard
    assert "EDGE_DEPLOY_BUNDLE_DIR" not in onboard


def test_release_install_builds_offline_runtime_without_user_state(tmp_path: Path) -> None:
    if shutil.which("sh") is None or os.name == "nt":
        pytest.skip("Linux install smoke requires POSIX executables and symlinks")
    root = _install_root(tmp_path)
    bundle, digest = make_bundle(
        tmp_path,
        {
            "requirements/requirements.txt": b"demo==1.0\n",
            "wheels/demo.whl": b"wheel",
        },
    )
    calls = tmp_path / "runtime-calls"

    result = _install(root, bundle, _approved_python(tmp_path), calls)

    assert result.returncode == 0, result.stderr
    runtime = root / ".venv" / "releases" / digest
    assert (runtime / ".complete.json").is_file()
    assert (root / ".venv" / "current").resolve() == runtime.resolve()
    commands = calls.read_text(encoding="utf-8")
    assert "pip install --no-index" in commands
    assert "pip check" in commands
    assert "import pandas; import numpy; import openpyxl" in commands
    assert not (tmp_path / ".autobench").exists()


def _prepare_onboarding_root(tmp_path: Path) -> tuple[Path, Path]:
    root = _install_root(tmp_path)
    runtime = root / ".venv" / "releases" / ("b" * 64)
    (runtime / "bin").mkdir(parents=True)
    (runtime / ".complete.json").write_text(
        json.dumps(
            {
                "bundle_digest": runtime.name,
                "pip_check": "passed",
                "required_imports": [
                    "pandas",
                    "numpy",
                    "openpyxl",
                    "yaml",
                    "scipy",
                    "textual",
                ],
            }
        ),
        encoding="utf-8",
    )
    python = runtime / "bin" / "python"
    python.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
    python.chmod(0o755)
    try:
        (root / ".venv" / "current").symlink_to(
            Path("releases") / runtime.name, target_is_directory=True
        )
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")
    return root, runtime


def _onboard(root: Path, home: Path, data_root: Path) -> subprocess.CompletedProcess[str]:
    home.mkdir(parents=True, exist_ok=True)
    data_root.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "HOME": _path(home),
            "USER": data_root.name,
            "AUTOBENCH_DATA_ROOT": _path(data_root),
        }
    )
    return subprocess.run(
        ["sh", "onboard.sh"],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_onboarding_migrates_launchers_without_touching_private_state(
    tmp_path: Path,
) -> None:
    if shutil.which("sh") is None:
        pytest.skip("onboarding smoke requires sh")
    root, _runtime = _prepare_onboarding_root(tmp_path)
    home = tmp_path / "home"
    data_root = tmp_path / "ads_storage" / "alice"
    private = data_root / ".autobench"
    for name in ("config", "logs", "cache", "telemetry"):
        (private / name).mkdir(parents=True, exist_ok=True)
        (private / name / "kept.txt").write_text(name, encoding="utf-8")
    personal_python = private / "venv" / "bin" / "python"
    personal_python.parent.mkdir(parents=True)
    personal_python.write_text("old", encoding="utf-8")
    stale = home / ".local" / "bin" / "autobench"
    stale.parent.mkdir(parents=True)
    stale.write_text(f'exec "{_path(personal_python)}" "$@"\n', encoding="utf-8")

    result = _onboard(root, home, data_root)

    assert result.returncode == 0, result.stderr
    for name in ("config", "logs", "cache", "telemetry"):
        assert (private / name / "kept.txt").read_text(encoding="utf-8") == name
        if os.name != "nt":
            assert stat.S_IMODE((private / name).stat().st_mode) == 0o700
    assert personal_python.read_text(encoding="utf-8") == "old"
    assert _path(root / "bin" / "autobench") in stale.read_text(encoding="utf-8")
    assert _path(root / "bin" / "autobench-cli") in (
        home / ".local" / "bin" / "autobench-cli"
    ).read_text(encoding="utf-8")


def test_two_users_share_runtime_and_keep_distinct_private_homes(tmp_path: Path) -> None:
    if shutil.which("sh") is None:
        pytest.skip("onboarding smoke requires sh")
    root, runtime = _prepare_onboarding_root(tmp_path)
    launcher_bodies = []
    for username in ("alice", "bob"):
        home = tmp_path / f"home-{username}"
        data_root = tmp_path / "ads_storage" / username
        result = _onboard(root, home, data_root)
        assert result.returncode == 0, result.stderr
        launcher_bodies.append(
            (home / ".local" / "bin" / "autobench-cli").read_text(encoding="utf-8")
        )
        assert (data_root / ".autobench" / "config").is_dir()

    assert launcher_bodies[0] == launcher_bodies[1]
    assert (root / ".venv" / "current").resolve() == runtime.resolve()


def test_onboarding_fails_before_state_changes_without_active_runtime(
    tmp_path: Path,
) -> None:
    if shutil.which("sh") is None:
        pytest.skip("onboarding smoke requires sh")
    root = _install_root(tmp_path)
    data_root = tmp_path / "ads_storage" / "alice"
    data_root.mkdir(parents=True)

    result = _onboard(root, tmp_path / "home", data_root)

    assert result.returncode != 0
    assert "shared runtime is not active" in result.stderr
    assert not (data_root / ".autobench").exists()
