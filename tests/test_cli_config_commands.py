"""Subprocess tests for benchmark.py config subcommands."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run_config(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "benchmark.py", "config", *args],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_config_list_includes_shipped_presets() -> None:
    result = _run_config(["list"])
    assert result.returncode == 0
    for preset in Path("presets").glob("*.yaml"):
        assert preset.stem in result.stdout


def test_config_validate_template_succeeds() -> None:
    result = _run_config(["validate", "config/template.yaml"])
    assert result.returncode == 0
    combined = f"{result.stdout}\n{result.stderr}".lower()
    assert "valid" in combined or "success" in combined


def test_config_generate_writes_valid_template(tmp_path: Path) -> None:
    output = tmp_path / "generated.yaml"
    result = _run_config(["generate", str(output)])
    assert result.returncode == 0
    assert output.exists()
    validate = _run_config(["validate", str(output)])
    assert validate.returncode == 0


def test_config_show_includes_tolerance() -> None:
    result = _run_config(["show", "balanced_default"])
    assert result.returncode == 0
    assert "tolerance" in result.stdout.lower()
