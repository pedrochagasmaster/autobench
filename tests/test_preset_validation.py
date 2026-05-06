"""Tests that all shipped presets load and validate correctly."""

from pathlib import Path

import yaml


def test_all_shipped_presets_have_valid_version() -> None:
    for preset_path in sorted(Path("presets").glob("*.yaml")):
        with open(preset_path, "r") as f:
            config = yaml.safe_load(f)
        assert config is not None, f"Empty preset: {preset_path.name}"
        assert config.get("version") == "3.0", f"Invalid version in {preset_path.name}"


def test_all_shipped_presets_load_via_config_manager() -> None:
    from utils.config_manager import ConfigManager

    for preset_path in sorted(Path("presets").glob("*.yaml")):
        preset_name = preset_path.stem
        config = ConfigManager(preset=preset_name)
        opt = config.config.get("optimization", {})
        bounds = opt.get("bounds", {})
        assert bounds.get("max_weight", 10.0) > 0, f"Invalid max_weight in {preset_name}"
        assert bounds.get("min_weight", 0.01) > 0, f"Invalid min_weight in {preset_name}"
        assert bounds.get("max_weight", 10.0) > bounds.get("min_weight", 0.01), (
            f"max_weight must exceed min_weight in {preset_name}"
        )


def test_preset_subset_search_max_attempts_positive() -> None:
    from utils.config_manager import ConfigManager

    for preset_path in sorted(Path("presets").glob("*.yaml")):
        preset_name = preset_path.stem
        config = ConfigManager(preset=preset_name)
        opt = config.config.get("optimization", {})
        max_attempts = opt.get("subset_search", {}).get("max_attempts", 200)
        assert max_attempts > 0, f"Invalid max_attempts in {preset_name}: {max_attempts}"
