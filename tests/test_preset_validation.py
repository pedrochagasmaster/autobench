from pathlib import Path

from utils.validators import load_config


def test_all_shipped_presets_validate() -> None:
    for preset_path in sorted(Path("presets").glob("*.yaml")):
        config = load_config(preset_path)
        assert config["version"] == "3.0"
