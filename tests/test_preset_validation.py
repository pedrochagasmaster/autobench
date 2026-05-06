from pathlib import Path

import yaml


def test_all_shipped_presets_are_valid_yaml() -> None:
    for preset_path in sorted(Path("presets").glob("*.yaml")):
        with open(preset_path) as f:
            config = yaml.safe_load(f)
        assert config is not None, f"Preset {preset_path.name} is empty"
        assert config.get("version") == "3.0", f"Preset {preset_path.name} missing version 3.0"
