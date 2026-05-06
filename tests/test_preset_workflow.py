"""Tests for the shared preset workflow used by the TUI and `--compare-presets`.

The audit complement (§2.2) flagged that ``PresetWorkflow.load_preset_data``
called a non-existent ``PresetManager.load_preset`` method, raising
``AttributeError`` whenever it executed. Both the alias-on-manager fix and
the defensive ``or {}`` in the workflow caller are exercised here.
"""

from __future__ import annotations

from core.preset_workflow import PresetWorkflow


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


def test_preset_manager_load_preset_alias_matches_get_preset() -> None:
    from utils.preset_manager import PresetManager

    pm = PresetManager()
    via_get = pm.get_preset("compliance_strict")
    via_load = pm.load_preset("compliance_strict")
    assert via_get == via_load
