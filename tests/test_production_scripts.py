from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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
    for name in ("install.sh", "setup_remote_env.sh"):
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
