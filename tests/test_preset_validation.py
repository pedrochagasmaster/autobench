"""Tests verifying every shipped preset validates against the schema."""

from __future__ import annotations

from pathlib import Path

import pytest

from utils.validators import load_config


PRESET_DIR = Path(__file__).resolve().parents[1] / "presets"


@pytest.mark.parametrize("preset_path", sorted(PRESET_DIR.glob("*.yaml")), ids=lambda p: p.name)
def test_all_shipped_presets_validate(preset_path: Path) -> None:
    config = load_config(preset_path)
    assert config["version"] == "3.0"


def test_preset_workflow_load_returns_dict() -> None:
    from core.preset_workflow import PresetWorkflow

    workflow = PresetWorkflow()
    presets = workflow.list_presets()
    assert presets, "expected at least one shipped preset"

    data = workflow.load_preset_data(presets[0])

    assert isinstance(data, dict)
    assert data.get("version") == "3.0"
