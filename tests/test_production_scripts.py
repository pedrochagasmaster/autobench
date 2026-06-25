from __future__ import annotations

import subprocess
import sys
import shutil
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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
    assert "./run_tool.sh config list" in deploy
    assert "./run_tool.sh share --help" in deploy
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
    assert "bundle rebuild" in setup.lower() or "interpreter mismatch" in setup.lower()
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
        "requirements.txt": "pandas==1.0\n",
        "requirements-dev.txt": "pytest==8.0\n",
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

    result = subprocess.run(
        ["bash", "update.sh"],
        cwd=node_checkout,
        env={
            **dict(os.environ),
            "AUTOBENCH_GIT_REMOTE": "origin",
            "AUTOBENCH_GIT_BRANCH": "main",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "Install decision: install not required" in result.stdout
    assert "dependency inputs unchanged" in result.stdout


def test_update_sh_reports_install_recommended_for_version_or_launcher_changes(tmp_path: Path) -> None:
    node_checkout = _build_update_repo_scenario(
        tmp_path,
        "VERSION",
        "1.0.1\n",
    )

    result = subprocess.run(
        ["bash", "update.sh"],
        cwd=node_checkout,
        env={
            **dict(os.environ),
            "AUTOBENCH_GIT_REMOTE": "origin",
            "AUTOBENCH_GIT_BRANCH": "main",
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

    result = subprocess.run(
        ["bash", "update.sh"],
        cwd=node_checkout,
        env={
            **dict(os.environ),
            "AUTOBENCH_GIT_REMOTE": "origin",
            "AUTOBENCH_GIT_BRANCH": "main",
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
    assert "http.extraHeader=Authorization: Bearer" in script
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
    assert "does not match the expected" in output
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
