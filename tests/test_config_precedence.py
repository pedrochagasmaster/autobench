"""Direct tests for ConfigManager merge precedence (CLI > config file > preset > defaults)."""

from __future__ import annotations

import yaml

from utils.config_manager import ConfigManager

_DEFAULT_TOLERANCE = 1.0


def _write_tolerance_config(tmp_path, tolerance: float) -> str:
    path = tmp_path / "override.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": "3.0",
                "compliance_posture": "strict",
                "optimization": {"linear_programming": {"tolerance": tolerance}},
            }
        ),
        encoding="utf-8",
    )
    return str(path)


def test_default_baseline_tolerance() -> None:
    config = ConfigManager()
    assert config.get("optimization", "linear_programming", "tolerance") == _DEFAULT_TOLERANCE


def test_preset_beats_default() -> None:
    config = ConfigManager(preset="compliance_strict")
    assert config.get("optimization", "linear_programming", "tolerance") == 0.0


def test_config_file_beats_preset(tmp_path) -> None:
    config_path = _write_tolerance_config(tmp_path, 7.5)
    config = ConfigManager(config_file=config_path, preset="compliance_strict")
    assert config.get("optimization", "linear_programming", "tolerance") == 7.5


def test_cli_beats_config_file_and_preset(tmp_path) -> None:
    config_path = _write_tolerance_config(tmp_path, 7.5)
    config = ConfigManager(
        config_file=config_path,
        preset="compliance_strict",
        cli_overrides={"tolerance": 3.25},
    )
    assert config.get("optimization", "linear_programming", "tolerance") == 3.25


def test_cli_none_does_not_override(tmp_path) -> None:
    config_path = _write_tolerance_config(tmp_path, 7.5)
    config = ConfigManager(
        config_file=config_path,
        preset="compliance_strict",
        cli_overrides={"tolerance": None},
    )
    assert config.get("optimization", "linear_programming", "tolerance") == 7.5


def test_cli_multiple_paths() -> None:
    config = ConfigManager(cli_overrides={"debug": True, "max_weight": 5.0})
    assert config.get("output", "include_debug_sheets") is True
    assert config.get("optimization", "bounds", "max_weight") == 5.0


def test_resolved_config_agrees_with_cli_override(tmp_path) -> None:
    config_path = _write_tolerance_config(tmp_path, 7.5)
    config = ConfigManager(
        config_file=config_path,
        preset="compliance_strict",
        cli_overrides={"tolerance": 3.25},
    )
    resolved = config.resolve()
    assert resolved.linear_programming.tolerance == 3.25
