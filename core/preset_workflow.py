"""Preset workflow helper for TUI preset loading and override file management."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from utils.preset_manager import PresetManager


class PresetWorkflow:
    """Convenience wrapper used by the TUI for preset operations."""

    def __init__(self) -> None:
        self._pm = PresetManager()

    def list_presets(self) -> List[str]:
        return self._pm.list_presets()

    def load_preset_data(self, preset_name: str) -> Dict[str, Any]:
        result = self._pm.get_preset(preset_name)
        if result is None:
            raise ValueError(f"Preset '{preset_name}' not found")
        return result

    def write_override_file(self, data: Dict[str, Any]) -> Path:
        tmp = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            prefix="adv_override_",
            delete=False,
            dir=".",
        )
        yaml.dump(data, tmp, default_flow_style=False)
        tmp.close()
        return Path(tmp.name)

    def export_override_file(
        self,
        content: Dict[str, Any],
        preset_name: Optional[str] = None,
    ) -> Path:
        name = preset_name or "custom"
        path = Path(f"exported_{name}_overrides.yaml")
        with open(path, "w", encoding="utf-8") as fh:
            yaml.dump(content, fh, default_flow_style=False)
        return path
