from pathlib import Path

from utils.preset_manager import PresetManager
from utils.validators import load_config


def test_all_shipped_presets_validate() -> None:
    for preset_path in sorted(Path("presets").glob("*.yaml")):
        config = load_config(preset_path)
        assert config["version"] == "3.0"


def test_preset_manager_reports_only_valid_presets() -> None:
    preset_manager = PresetManager()

    assert preset_manager.invalid_presets == {}
    assert set(preset_manager.list_presets()) == {
        preset_path.stem for preset_path in Path("presets").glob("*.yaml")
    }
