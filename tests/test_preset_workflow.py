"""Tests for the shared preset workflow used by the TUI and `--compare-presets`."""

from __future__ import annotations

import yaml

from core.preset_workflow import PresetWorkflow
from utils.config_manager import ConfigManager


def test_load_preset_data_returns_dict_for_shipped_preset() -> None:
    workflow = PresetWorkflow()

    preset_data = workflow.load_preset_data("balanced_default")

    assert isinstance(preset_data, dict)
    assert preset_data.get("preset_name") == "balanced_default"


def test_load_preset_data_returns_empty_dict_for_missing_preset() -> None:
    workflow = PresetWorkflow()

    preset_data = workflow.load_preset_data("does_not_exist_xyz")

    # Caller-defensive `or {}` keeps downstream code from receiving None and
    # crashing with `TypeError: argument of type 'NoneType' is not iterable`.
    assert preset_data == {}


def test_write_override_file_emits_valid_v3_override_with_posture() -> None:
    workflow = PresetWorkflow()
    override_data = {
        "optimization": {
            "linear_programming": {"tolerance": 2.5},
        },
    }

    override_path = workflow.write_override_file(override_data, posture="strict")
    try:
        with open(override_path, encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle)

        assert loaded["version"] == "3.0"
        assert loaded["compliance_posture"] == "strict"
        assert loaded["optimization"]["linear_programming"]["tolerance"] == 2.5

        config = ConfigManager(config_file=str(override_path), preset="balanced_default")
        assert config.get("compliance_posture") == "strict"
        assert config.get("optimization", "linear_programming", "tolerance") == 2.5
    finally:
        override_path.unlink(missing_ok=True)
