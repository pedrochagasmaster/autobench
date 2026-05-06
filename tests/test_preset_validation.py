from pathlib import Path

import pytest

from utils.preset_manager import PresetManager
from utils.validators import load_config


def test_all_shipped_presets_validate() -> None:
    for preset_path in sorted(Path("presets").glob("*.yaml")):
        config = load_config(preset_path)
        assert config["version"] == "3.0"


def test_runtime_preset_manager_rejects_invalid_preset_file(tmp_path: Path) -> None:
    invalid_preset = tmp_path / "broken.yaml"
    invalid_preset.write_text(
        "\n".join(
            [
                'version: "3.0"',
                'preset_name: "broken"',
                'compliance_posture: "strict"',
                "optimization:",
                "  subset_search:",
                "    max_attempts: 0",
            ]
        ),
        encoding="utf-8",
    )

    manager = PresetManager(preset_dir=tmp_path)

    assert "broken" not in manager.list_presets()
