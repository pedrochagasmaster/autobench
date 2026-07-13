from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
requires_linux_filesystem = pytest.mark.skipif(
    sys.platform != "linux",
    reason="requires Linux paths, mode bits, and unprivileged symlink semantics",
)


def _powershell_command() -> list[str]:
    if shell := shutil.which("pwsh"):
        return [shell, "-NoProfile", "-File"]
    if shell := shutil.which("powershell"):
        return [shell, "-NoProfile", "-File"]
    raise RuntimeError("PowerShell is required for this test")


def test_run_tool_routes_cli_subcommands_to_benchmark() -> None:
    script = (ROOT / "run_tool.sh").read_text(encoding="utf-8")

    assert "BENCHMARK_APP=" in script
    assert "share|rate|config" in script
    assert 'python "$BENCHMARK_APP"' in script


def test_run_tool_shell_syntax_is_valid() -> None:
    result = subprocess.run(
        ["bash", "-n", str(ROOT / "run_tool.sh")],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_install_and_setup_shell_syntax_is_valid() -> None:
    for name in ("install.sh", "setup_remote_env.sh", "update.sh"):
        result = subprocess.run(
            ["bash", "-n", str(ROOT / name)],
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, f"{name}: {result.stderr}"


def test_installer_matches_interpreter_to_offline_wheel_abi() -> None:
    """Guards the cp310-wheels-vs-python3.11 deployment break.

    install.sh must derive the required CPython version from the bundled wheel
    ABI tag and refuse a mismatched interpreter, rather than preferring 3.11
    unconditionally and failing later inside pip.
    """
    script = (ROOT / "install.sh").read_text(encoding="utf-8")

    assert "required_wheel_python" in script
    assert "cp3" in script
    assert "REQUIRED_PY" in script
    # The wheel-ABI detection must come before the online python3.11 fallback,
    # so bundled binary wheels dictate the interpreter version.
    assert script.index("required_wheel_python") < script.index("python3.11")


def test_textual_75_node_bundle_is_supported() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    constraints = (ROOT / "constraints.txt").read_text(encoding="utf-8")

    assert '"textual>=0.40.0,<8"' in pyproject
    assert "textual>=0.40.0,<8" in requirements
    assert "textual==7.5.0" in constraints


def test_installer_requires_core_verified_dependency_bundle() -> None:
    script = (ROOT / "install.sh").read_text(encoding="utf-8")

    assert "EDGE_DEPLOY_BUNDLE_DIR" in script
    assert "manifest.json" in script
    assert "--no-index" in script
    assert "AUTOBENCH_PIP_INDEX_URL" not in script


def test_update_permissions_do_not_recurse_through_runtime_directories() -> None:
    script = (ROOT / "update.sh").read_text(encoding="utf-8")

    assert "chmod -R" not in script
    assert "$CHANGED_FILES" in script


def test_update_sh_provisions_shared_telemetry_directories() -> None:
    script = (ROOT / "update.sh").read_text(encoding="utf-8")
    helper = (ROOT / "scripts" / "provision_telemetry_dirs.sh").read_text(encoding="utf-8")

    assert 'TELEMETRY_DIR="${AUTOBENCH_TELEMETRY_DIR:-/ads_storage/autobench/telemetry}"' in script
    assert "provision_shared_telemetry_dirs" in script
    assert "provision_telemetry_dirs.sh" in script
    assert "Telemetry permission evidence" in script or "telemetry permission" in script.lower()
    assert script.index("git reset --hard") < script.index("provision_shared_telemetry_dirs")

    assert "mkdir -p --" in helper
    assert "mkdir --" in helper
    assert 'chmod -- 0755 "$TELEMETRY_DIR"' in helper
    assert 'chmod -- 1777 "$USERS_DIR"' in helper
    assert "-L" in helper
    # Must not chmod through a users symlink.
    assert "symlink" in helper.lower()


@requires_linux_filesystem
def test_provision_telemetry_dirs_rejects_users_symlink_without_chmodding_victim(
    tmp_path: Path,
) -> None:
    """users -> victim must fail; victim mode must remain 0700."""
    helper = ROOT / "scripts" / "provision_telemetry_dirs.sh"
    assert helper.is_file(), "extract testable scripts/provision_telemetry_dirs.sh"

    parent = tmp_path / "telemetry"
    parent.mkdir(mode=0o0755)
    victim = tmp_path / "victim"
    victim.mkdir(mode=0o0700)
    users = parent / "users"
    users.symlink_to(victim)

    before = stat.S_IMODE(victim.stat().st_mode)
    assert before == 0o0700

    result = subprocess.run(
        [
            "bash",
            "-c",
            'set -euo pipefail; . "$1"; provision_shared_telemetry_dirs "$2"',
            "provision-test",
            str(helper),
            str(parent),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, result.stdout
    assert "symlink" in (result.stderr + result.stdout).lower()
    assert stat.S_IMODE(victim.stat().st_mode) == 0o0700
    assert users.is_symlink()


@requires_linux_filesystem
def test_provision_telemetry_dirs_rejects_telemetry_dir_symlink(
    tmp_path: Path,
) -> None:
    helper = ROOT / "scripts" / "provision_telemetry_dirs.sh"
    real = tmp_path / "real"
    real.mkdir(mode=0o0755)
    link = tmp_path / "telemetry"
    link.symlink_to(real)

    result = subprocess.run(
        [
            "bash",
            "-c",
            'set -euo pipefail; . "$1"; provision_shared_telemetry_dirs "$2"',
            "provision-test",
            str(helper),
            str(link),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "symlink" in (result.stderr + result.stdout).lower()
    assert stat.S_IMODE(real.stat().st_mode) == 0o0755


@requires_linux_filesystem
@pytest.mark.parametrize("suffix", ["/", "////"])
def test_provision_telemetry_dirs_rejects_trailing_slash_symlink_without_chmodding_victim(
    tmp_path: Path, suffix: str
) -> None:
    """Trailing slashes must not bypass -L; victim mode stays 0700."""
    helper = ROOT / "scripts" / "provision_telemetry_dirs.sh"
    victim = tmp_path / "victim"
    victim.mkdir(mode=0o0700)
    link = tmp_path / "link"
    link.symlink_to(victim)
    assert stat.S_IMODE(victim.stat().st_mode) == 0o0700

    result = subprocess.run(
        [
            "bash",
            "-c",
            'set -euo pipefail; . "$1"; provision_shared_telemetry_dirs "$2"',
            "provision-test",
            str(helper),
            str(link) + suffix,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, result.stdout or result.stderr
    assert "symlink" in (result.stderr + result.stdout).lower()
    assert stat.S_IMODE(victim.stat().st_mode) == 0o0700
    assert link.is_symlink()


@requires_linux_filesystem
@pytest.mark.parametrize("bad", ["", ".", "/", "///"])
def test_provision_telemetry_dirs_rejects_unsafe_roots(tmp_path: Path, bad: str) -> None:
    """Empty, '.', and '/' (incl. slash-only) must never chmod root or create /users."""
    helper = ROOT / "scripts" / "provision_telemetry_dirs.sh"
    marker = tmp_path / "untouched"
    marker.mkdir(mode=0o0700)
    users_at_root = Path("/users")
    users_existed_before = users_at_root.exists()

    fail = subprocess.run(
        [
            "bash",
            "-c",
            '. "$1"; provision_shared_telemetry_dirs "$2"',
            "provision-test",
            str(helper),
            bad,
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(tmp_path),
    )
    assert fail.returncode != 0
    combined = (fail.stderr + fail.stdout).lower()
    assert any(
        token in combined
        for token in ("refusing", "unsafe", "invalid", "empty", "root", "absolute")
    )
    assert stat.S_IMODE(marker.stat().st_mode) == 0o0700
    if not users_existed_before:
        assert not users_at_root.exists()
    assert not (tmp_path / "users").exists()


@pytest.mark.parametrize(
    "alias",
    [
        "{base}/./x",
        "{base}/x/../y",
        "{base}/./x/",
        "{base}/x/../y///",
        "foo/..",
        "../",
        "./.",
        "relative-telemetry",
        "./telemetry",
    ],
)
def test_provision_telemetry_dirs_rejects_dot_aliases_without_mutating(
    tmp_path: Path, alias: str
) -> None:
    """Reject relative paths and any lexical '.'/'..' component before mutation."""
    helper = ROOT / "scripts" / "provision_telemetry_dirs.sh"
    base = tmp_path / "base"
    base.mkdir(mode=0o0700)
    cwd_mode_before = stat.S_IMODE(tmp_path.stat().st_mode)
    parent_mode_before = stat.S_IMODE(base.stat().st_mode)
    target = alias.format(base=str(base))

    maybe_x = base / "x"
    maybe_y = base / "y"
    maybe_users_cwd = tmp_path / "users"
    maybe_users_base = base / "users"
    maybe_users_x = base / "x" / "users"
    maybe_users_y = base / "y" / "users"

    fail = subprocess.run(
        [
            "bash",
            "-c",
            '. "$1"; provision_shared_telemetry_dirs "$2"',
            "provision-test",
            str(helper),
            target,
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(tmp_path),
    )
    assert fail.returncode != 0, fail.stdout or fail.stderr
    combined = (fail.stderr + fail.stdout).lower()
    assert any(
        token in combined
        for token in ("refusing", "unsafe", "invalid", "absolute", "dot")
    )
    assert stat.S_IMODE(tmp_path.stat().st_mode) == cwd_mode_before
    assert stat.S_IMODE(base.stat().st_mode) == parent_mode_before
    assert not maybe_x.exists()
    assert not maybe_y.exists()
    assert not maybe_users_cwd.exists()
    assert not maybe_users_base.exists()
    assert not maybe_users_x.exists()
    assert not maybe_users_y.exists()


@requires_linux_filesystem
def test_provision_telemetry_dirs_accepts_absolute_with_repeated_slashes(
    tmp_path: Path,
) -> None:
    helper = ROOT / "scripts" / "provision_telemetry_dirs.sh"
    parent = tmp_path / "telem"
    weird = str(tmp_path) + "///telem///"

    result = subprocess.run(
        [
            "bash",
            "-c",
            'set -euo pipefail; . "$1"; provision_shared_telemetry_dirs "$2"',
            "provision-test",
            str(helper),
            weird,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert parent.is_dir() and not parent.is_symlink()
    assert (parent / "users").is_dir()
    assert stat.S_IMODE(parent.stat().st_mode) == 0o0755
    assert stat.S_IMODE((parent / "users").stat().st_mode) == 0o1777


@requires_linux_filesystem
def test_provision_telemetry_dirs_trailing_slash_override_still_provisions(
    tmp_path: Path,
) -> None:
    """Harmless trailing slash on a real dir keeps exact override semantics."""
    helper = ROOT / "scripts" / "provision_telemetry_dirs.sh"
    parent = tmp_path / "telemetry"

    result = subprocess.run(
        [
            "bash",
            "-c",
            'set -euo pipefail; . "$1"; provision_shared_telemetry_dirs "$2"',
            "provision-test",
            str(helper),
            str(parent) + "///",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert parent.is_dir() and not parent.is_symlink()
    assert (parent / "users").is_dir()
    assert stat.S_IMODE(parent.stat().st_mode) == 0o0755
    assert stat.S_IMODE((parent / "users").stat().st_mode) == 0o1777


@requires_linux_filesystem
def test_provision_telemetry_dirs_creates_layout_idempotently(tmp_path: Path) -> None:
    helper = ROOT / "scripts" / "provision_telemetry_dirs.sh"
    parent = tmp_path / "telemetry"

    def run_once() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "bash",
                "-c",
                'set -euo pipefail; . "$1"; provision_shared_telemetry_dirs "$2"',
                "provision-test",
                str(helper),
                str(parent),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    first = run_once()
    assert first.returncode == 0, first.stderr or first.stdout
    users = parent / "users"
    assert parent.is_dir() and not parent.is_symlink()
    assert users.is_dir() and not users.is_symlink()
    assert stat.S_IMODE(parent.stat().st_mode) == 0o0755
    assert stat.S_IMODE(users.stat().st_mode) == 0o1777

    parent.chmod(0o0700)
    users.chmod(0o0755)
    second = run_once()
    assert second.returncode == 0, second.stderr or second.stdout
    assert stat.S_IMODE(parent.stat().st_mode) == 0o0755
    assert stat.S_IMODE(users.stat().st_mode) == 0o1777


@requires_linux_filesystem
def test_provision_telemetry_dirs_rejects_intermediate_symlink_ancestor(
    tmp_path: Path,
) -> None:
    """parent/autobench -> victim must fail before victim mutation or users create."""
    helper = ROOT / "scripts" / "provision_telemetry_dirs.sh"
    parent = tmp_path / "parent"
    parent.mkdir(mode=0o0755)
    victim = parent / "victim"
    victim.mkdir(mode=0o0700)
    link = parent / "autobench"
    link.symlink_to(victim)
    target = parent / "autobench" / "telemetry"

    assert stat.S_IMODE(victim.stat().st_mode) == 0o0700
    before_victim_entries = set(victim.iterdir())

    for suffix in ("", "/", "///"):
        result = subprocess.run(
            [
                "bash",
                "-c",
                '. "$1"; provision_shared_telemetry_dirs "$2"',
                "provision-test",
                str(helper),
                str(target) + suffix,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0, result.stdout or result.stderr
        combined = (result.stderr + result.stdout).lower()
        assert "symlink" in combined
        assert stat.S_IMODE(victim.stat().st_mode) == 0o0700
        assert set(victim.iterdir()) == before_victim_entries
        assert not (victim / "telemetry").exists()
        assert not (victim / "users").exists()
        assert link.is_symlink()


def test_install_sh_does_not_provision_shared_telemetry_parents() -> None:
    script = (ROOT / "install.sh").read_text(encoding="utf-8")

    assert "/ads_storage/autobench/telemetry" not in script
    assert "TELEMETRY_DIR" not in script
    assert "1777" not in script
    assert 'mkdir -p "$AUTOBENCH_HOME/config"' in script


@requires_linux_filesystem
def test_update_sh_idempotently_creates_telemetry_layout(tmp_path: Path) -> None:
    node_checkout = _build_update_repo_scenario(
        tmp_path / "scenario",
        "benchmark.py",
        "print('source-only change')\n",
    )
    telemetry_dir = tmp_path / "telemetry_home"

    env = {
        **dict(os.environ),
        "AUTOBENCH_GIT_REMOTE": "origin",
        "AUTOBENCH_GIT_BRANCH": "main",
        "AUTOBENCH_TELEMETRY_DIR": str(telemetry_dir),
    }
    first = subprocess.run(
        ["bash", "update.sh"],
        cwd=node_checkout,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert first.returncode == 0, first.stderr or first.stdout
    users = telemetry_dir / "users"
    assert telemetry_dir.is_dir()
    assert users.is_dir()
    assert stat.S_IMODE(telemetry_dir.stat().st_mode) == 0o0755
    assert stat.S_IMODE(users.stat().st_mode) == 0o1777
    assert "Permission evidence" in first.stdout or "telemetry" in first.stdout.lower()

    # Corrupt modes then re-run to prove idempotent normalization.
    telemetry_dir.chmod(0o0700)
    users.chmod(0o0755)
    second = subprocess.run(
        ["bash", "update.sh"],
        cwd=node_checkout,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert second.returncode == 0, second.stderr or second.stdout
    assert stat.S_IMODE(telemetry_dir.stat().st_mode) == 0o0755
    assert stat.S_IMODE(users.stat().st_mode) == 0o1777


def test_update_sh_completes_when_telemetry_provisioning_fails(tmp_path: Path) -> None:
    """Telemetry is best-effort: provisioning failure must not abort the sync."""
    node_checkout = _build_update_repo_scenario(
        tmp_path / "scenario",
        "benchmark.py",
        "print('source-only change')\n",
    )
    # A regular-file ancestor makes provisioning fail before any mkdir/chmod.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory\n", encoding="utf-8")
    telemetry_dir = blocker / "telemetry"

    result = subprocess.run(
        ["bash", "update.sh"],
        cwd=node_checkout,
        env={
            **dict(os.environ),
            "AUTOBENCH_GIT_REMOTE": "origin",
            "AUTOBENCH_GIT_BRANCH": "main",
            "AUTOBENCH_TELEMETRY_DIR": str(telemetry_dir),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "WARNING: shared telemetry provisioning failed" in result.stderr
    assert "Update complete" in result.stdout
    assert not telemetry_dir.exists()


def test_offline_bundle_targets_python_310_cp310() -> None:
    """deploy_and_install.ps1 and setup_remote_env.sh must agree on Python 3.10."""
    deploy = (ROOT / "deploy_and_install.ps1").read_text(encoding="utf-8")
    setup = (ROOT / "setup_remote_env.sh").read_text(encoding="utf-8")

    assert "--abi cp310" in deploy
    assert "--python-version 3.10" in deploy
    assert "/sys_apps_01/python/python310/bin/python3.10" in setup


def test_deploy_and_install_script_records_bundle_report_contract() -> None:
    deploy = (ROOT / "deploy_and_install.ps1").read_text(encoding="utf-8")

    assert "Source commit" in deploy
    assert "Bundle SHA256" in deploy
    assert "Extraction path" in deploy
    assert "Runtime Python" in deploy
    assert "Wrapper smoke" in deploy
    assert "Drift result" in deploy
    assert "Smoke level" in deploy
    assert "Permission evidence" in deploy
    assert "ls -ld ." in deploy
    assert "ls -l run_tool.sh setup_alias.sh" in deploy
    assert "./run_tool.sh config list" in deploy
    assert "./run_tool.sh share --help" in deploy
    assert "permission_evidence=reported" in deploy
    assert "SUMMARY bundle=" in deploy


def test_setup_remote_env_runs_wrapper_checks_and_emits_summary_contract() -> None:
    setup = (ROOT / "setup_remote_env.sh").read_text(encoding="utf-8")

    assert "-m compileall benchmark.py tui_app.py core utils scripts tools" in setup
    assert "-m tools.prod_tui drift --local . --remote /ads_storage/autobench" in setup
    assert "./run_tool.sh config list" in setup
    assert "./run_tool.sh share --help" in setup
    assert "INSTALL_RESULT=" in setup
    assert "WRAPPER_CHECKS=" in setup
    assert "DRIFT_RESULT=" in setup
    assert "SMOKE_LEVEL=" in setup
    assert "PERMISSION_EVIDENCE=" in setup
    assert 'ls -ld "$BUNDLE_PATH"' in setup
    assert "ls -l run_tool.sh setup_alias.sh" in setup
    assert "bundle rebuild" in setup.lower() or "interpreter mismatch" in setup.lower()
    assert "permission_evidence=$PERMISSION_EVIDENCE" in setup
    assert "SUMMARY bundle_path=" in setup


def _build_update_repo_scenario(tmp_path: Path, changed_path: str, changed_contents: str) -> Path:
    remote_bare = tmp_path / "remote.git"
    seed_repo = tmp_path / "seed"
    node_checkout = tmp_path / "node"

    subprocess.run(["git", "init", "--bare", str(remote_bare)], check=True)
    subprocess.run(["git", "init", "-b", "main", str(seed_repo)], check=True)
    subprocess.run(["git", "-C", str(seed_repo), "config", "user.name", "Seed User"], check=True)
    subprocess.run(
        ["git", "-C", str(seed_repo), "config", "user.email", "seed@example.com"],
        check=True,
    )

    tracked_files = {
        "update.sh": (ROOT / "update.sh").read_text(encoding="utf-8"),
        "install.sh": (ROOT / "install.sh").read_text(encoding="utf-8"),
        "setup_remote_env.sh": (ROOT / "setup_remote_env.sh").read_text(encoding="utf-8"),
        "scripts/provision_telemetry_dirs.sh": (
            ROOT / "scripts" / "provision_telemetry_dirs.sh"
        ).read_text(encoding="utf-8"),
        "requirements.txt": "pandas==1.0\n",
        "constraints.txt": "pandas==1.0\n",
        "VERSION": "1.0.0\n",
        "benchmark.py": "print('baseline')\n",
    }

    for relative_path, contents in tracked_files.items():
        path = seed_repo / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    subprocess.run(["git", "-C", str(seed_repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(seed_repo), "commit", "-m", "baseline"], check=True)
    subprocess.run(["git", "-C", str(seed_repo), "remote", "add", "origin", str(remote_bare)], check=True)
    subprocess.run(["git", "-C", str(seed_repo), "push", "origin", "main"], check=True)

    subprocess.run(["git", "clone", "--branch", "main", str(remote_bare), str(node_checkout)], check=True)

    changed_file = seed_repo / changed_path
    changed_file.parent.mkdir(parents=True, exist_ok=True)
    changed_file.write_text(changed_contents, encoding="utf-8")
    subprocess.run(["git", "-C", str(seed_repo), "add", changed_path], check=True)
    subprocess.run(["git", "-C", str(seed_repo), "commit", "-m", f"change {changed_path}"], check=True)
    subprocess.run(["git", "-C", str(seed_repo), "push", "origin", "main"], check=True)

    return node_checkout


def test_update_sh_reports_install_not_required_for_source_only_changes(tmp_path: Path) -> None:
    node_checkout = _build_update_repo_scenario(
        tmp_path,
        "benchmark.py",
        "print('source-only change')\n",
    )
    telemetry_dir = tmp_path / "telemetry_not_required"

    result = subprocess.run(
        ["bash", "update.sh"],
        cwd=node_checkout,
        env={
            **dict(os.environ),
            "AUTOBENCH_GIT_REMOTE": "origin",
            "AUTOBENCH_GIT_BRANCH": "main",
            "AUTOBENCH_TELEMETRY_DIR": str(telemetry_dir),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "Install decision: install not required" in result.stdout
    assert "dependency inputs unchanged" in result.stdout
    assert "Permission evidence: reported" in result.stdout
    assert "Repo root permissions:" in result.stdout
    assert "Entrypoint permissions:" in result.stdout


def test_update_sh_repairs_corrupt_remote_tracking_ref(tmp_path: Path) -> None:
    node_checkout = _build_update_repo_scenario(
        tmp_path,
        "benchmark.py",
        "print('source-only change')\n",
    )
    remote_ref = node_checkout / ".git" / "refs" / "remotes" / "origin" / "main"
    remote_ref.parent.mkdir(parents=True, exist_ok=True)
    remote_ref.write_text("", encoding="utf-8")
    telemetry_dir = tmp_path / "telemetry_repair"

    result = subprocess.run(
        ["bash", "update.sh"],
        cwd=node_checkout,
        env={
            **dict(os.environ),
            "AUTOBENCH_GIT_REMOTE": "origin",
            "AUTOBENCH_GIT_BRANCH": "main",
            "AUTOBENCH_TELEMETRY_DIR": str(telemetry_dir),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "Detected stale remote-tracking ref" in result.stderr
    assert "Update complete" in result.stdout


def test_update_sh_reports_install_recommended_for_version_or_launcher_changes(tmp_path: Path) -> None:
    node_checkout = _build_update_repo_scenario(
        tmp_path,
        "VERSION",
        "1.0.1\n",
    )
    telemetry_dir = tmp_path / "telemetry_recommended"

    result = subprocess.run(
        ["bash", "update.sh"],
        cwd=node_checkout,
        env={
            **dict(os.environ),
            "AUTOBENCH_GIT_REMOTE": "origin",
            "AUTOBENCH_GIT_BRANCH": "main",
            "AUTOBENCH_TELEMETRY_DIR": str(telemetry_dir),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "Install decision: install recommended" in result.stdout
    assert "VERSION" in result.stdout


def test_update_sh_reports_install_required_for_dependency_inputs(tmp_path: Path) -> None:
    node_checkout = _build_update_repo_scenario(
        tmp_path,
        "requirements.txt",
        "pandas==2.0\n",
    )
    telemetry_dir = tmp_path / "telemetry_required"

    result = subprocess.run(
        ["bash", "update.sh"],
        cwd=node_checkout,
        env={
            **dict(os.environ),
            "AUTOBENCH_GIT_REMOTE": "origin",
            "AUTOBENCH_GIT_BRANCH": "main",
            "AUTOBENCH_TELEMETRY_DIR": str(telemetry_dir),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "Install decision: install required" in result.stdout
    assert "requirements.txt" in result.stdout


def test_publish_snapshot_script_has_safe_remote_and_auth_defaults() -> None:
    script = (ROOT / "tools" / "dev" / "publish_bitbucket_snapshot.ps1").read_text(
        encoding="utf-8"
    )

    assert "https://scm.mastercard.int/stash/scm/~e176097/autobench.git" in script
    assert "GIT_TERMINAL_PROMPT" in script
    assert "--config-env=http.extraHeader=" in script
    assert "Authorization: Bearer" in script
    assert "--force" not in script
    assert "user takeover" in script.lower() or "handoff" in script.lower()


def test_publish_snapshot_script_creates_bitbucket_parented_snapshot_and_restores_branch(
    tmp_path: Path,
) -> None:
    ps = _powershell_command()
    remote_bare = tmp_path / "remote.git"
    remote_seed = tmp_path / "remote-seed"
    local_repo = tmp_path / "local"
    script = ROOT / "tools" / "dev" / "publish_bitbucket_snapshot.ps1"

    subprocess.run(["git", "init", "--bare", str(remote_bare)], check=True)

    subprocess.run(["git", "init", "-b", "main", str(remote_seed)], check=True)
    subprocess.run(["git", "-C", str(remote_seed), "config", "user.name", "Remote Seed"], check=True)
    subprocess.run(
        ["git", "-C", str(remote_seed), "config", "user.email", "seed@example.com"],
        check=True,
    )
    (remote_seed / "README.md").write_text("remote seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(remote_seed), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(remote_seed), "commit", "-m", "seed"], check=True)
    subprocess.run(["git", "-C", str(remote_seed), "remote", "add", "origin", str(remote_bare)], check=True)
    subprocess.run(["git", "-C", str(remote_seed), "push", "origin", "main"], check=True)
    remote_parent = subprocess.run(
        ["git", "-C", str(remote_seed), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    subprocess.run(["git", "init", "-b", "main", str(local_repo)], check=True)
    subprocess.run(["git", "-C", str(local_repo), "config", "user.name", "Local User"], check=True)
    subprocess.run(
        ["git", "-C", str(local_repo), "config", "user.email", "local@example.com"],
        check=True,
    )
    (local_repo / "app.txt").write_text("local main tree\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(local_repo), "add", "app.txt"], check=True)
    subprocess.run(["git", "-C", str(local_repo), "commit", "-m", "local main"], check=True)
    local_main = subprocess.run(
        ["git", "-C", str(local_repo), "rev-parse", "main"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    local_tree = subprocess.run(
        ["git", "-C", str(local_repo), "rev-parse", f"{local_main}^{{tree}}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    subprocess.run(["git", "-C", str(local_repo), "checkout", "-b", "feature/test"], check=True)
    subprocess.run(["git", "-C", str(local_repo), "remote", "add", "bitbucket", str(remote_bare)], check=True)

    result = subprocess.run(
        [
            *ps,
            str(script),
            "-ExpectedUrl",
            str(remote_bare),
        ],
        cwd=local_repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "Source commit:" in result.stdout
    assert "Bitbucket parent SHA:" in result.stdout
    assert "New snapshot SHA:" in result.stdout
    assert "Push result:" in result.stdout

    current_branch = subprocess.run(
        ["git", "-C", str(local_repo), "branch", "--show-current"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert current_branch == "feature/test"

    remote_head = subprocess.run(
        ["git", "--git-dir", str(remote_bare), "rev-parse", "main"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    remote_head_parent = subprocess.run(
        ["git", "--git-dir", str(remote_bare), "rev-parse", f"{remote_head}^"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    remote_head_tree = subprocess.run(
        ["git", "--git-dir", str(remote_bare), "rev-parse", f"{remote_head}^{{tree}}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    assert remote_head_parent == remote_parent
    assert remote_head_tree == local_tree


def test_publish_snapshot_script_refuses_unexpected_remote_url_before_mutating_repo(
    tmp_path: Path,
) -> None:
    ps = _powershell_command()
    remote_bare = tmp_path / "remote.git"
    local_repo = tmp_path / "local"
    script = ROOT / "tools" / "dev" / "publish_bitbucket_snapshot.ps1"

    subprocess.run(["git", "init", "--bare", str(remote_bare)], check=True)
    subprocess.run(["git", "init", "-b", "main", str(local_repo)], check=True)
    subprocess.run(["git", "-C", str(local_repo), "config", "user.name", "Local User"], check=True)
    subprocess.run(
        ["git", "-C", str(local_repo), "config", "user.email", "local@example.com"],
        check=True,
    )
    (local_repo / "app.txt").write_text("local main tree\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(local_repo), "add", "app.txt"], check=True)
    subprocess.run(["git", "-C", str(local_repo), "commit", "-m", "local main"], check=True)
    subprocess.run(["git", "-C", str(local_repo), "checkout", "-b", "feature/test"], check=True)
    subprocess.run(["git", "-C", str(local_repo), "remote", "add", "bitbucket", str(remote_bare)], check=True)

    result = subprocess.run(
        [
            *ps,
            str(script),
            "-ExpectedUrl",
            "https://scm.mastercard.int/stash/scm/~e176097/autobench.git",
        ],
        cwd=local_repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    output = (result.stderr + result.stdout).lower()
    normalized_output = " ".join(output.split())
    assert "does not match the expected" in normalized_output
    assert "autobench.git" in output
    current_branch = subprocess.run(
        ["git", "-C", str(local_repo), "branch", "--show-current"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert current_branch == "feature/test"


def test_offline_bundle_checksum_manifest_round_trips(tmp_path: Path) -> None:
    package_dir = tmp_path / "offline_packages"
    package_dir.mkdir()
    wheel = package_dir / "demo-1.0-py3-none-any.whl"
    wheel.write_bytes(b"demo wheel")
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("pandas\n", encoding="utf-8")
    manifest = tmp_path / "SHA256SUMS"
    script = ROOT / "scripts" / "offline_bundle_checksums.py"

    write_result = subprocess.run(
        [
            sys.executable,
            str(script),
            "write",
            str(package_dir),
            str(requirements),
            "--output",
            str(manifest),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert write_result.returncode == 0, write_result.stderr or write_result.stdout
    assert manifest.exists()
    assert "offline_packages/demo-1.0-py3-none-any.whl" in manifest.read_text(encoding="utf-8")

    verify_result = subprocess.run(
        [sys.executable, str(script), "verify", "--manifest", str(manifest)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert verify_result.returncode == 0, verify_result.stderr or verify_result.stdout

    wheel.write_bytes(b"tampered")
    tampered_result = subprocess.run(
        [sys.executable, str(script), "verify", "--manifest", str(manifest)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert tampered_result.returncode == 1
    assert "checksum mismatch" in tampered_result.stdout.lower()


def test_master_context_split_types_generates_docs_and_code_outputs(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "build_master_context.py"
    output = tmp_path / "master.md"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--output",
            str(output),
            "--split-types",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    docs_output = tmp_path / "master_docs.md"
    code_output = tmp_path / "master_code.md"

    assert result.returncode == 0, result.stderr or result.stdout
    assert not output.exists()
    assert docs_output.exists()
    assert code_output.exists()

    docs_text = docs_output.read_text(encoding="utf-8")
    code_text = code_output.read_text(encoding="utf-8")

    assert "| Current Documentation | `README.md` |" in docs_text
    assert "| Configuration | `config/template.yaml` |" in docs_text
    assert "| Entrypoints | `benchmark.py` |" not in docs_text
    assert "| Verification Surface | `scripts/build_master_context.py` |" not in docs_text

    assert "| Entrypoints | `benchmark.py` |" in code_text
    assert "| Relevant Source | `core/privacy_validator.py` |" in code_text
    assert "| Verification Surface | `scripts/build_master_context.py` |" in code_text
    assert "| Current Documentation | `README.md` |" not in code_text
