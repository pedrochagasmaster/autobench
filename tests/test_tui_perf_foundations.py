"""Phase 2 PR 2: TUI performance foundations (03 §1–§4, §6).

Each test pins the behaviour a performance fix must keep, plus the fix itself
(no repeated parse, no repeated reload, capped lists, worker scans).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import time
from pathlib import Path

import pytest
from textual.widgets import Select

import tui_app
from tui_app import SELECT_BLANK, BenchmarkApp, PresetCatalog
from utils.preset_manager import PresetManager

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "gate_demo.csv"


@pytest.fixture(autouse=True)
def _isolated_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tui_app, "SESSION_FILE", tmp_path / "session.yaml")


async def _settle(pilot, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    await pilot.pause()
    while pilot.app.entity_values_loading and time.monotonic() < deadline:
        await pilot.pause(0.02)
    await pilot.pause()


# ── 1.3 theme ─────────────────────────────────────────────────────────────


def test_theme_is_set_before_mount() -> None:
    app = BenchmarkApp()
    assert app.theme == "tokyo-night"

    async def scenario() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert pilot.app.theme == "tokyo-night"

    asyncio.run(scenario())


# ── 1.2 presets parsed once ───────────────────────────────────────────────


def test_presets_are_parsed_once_across_startup_and_advanced_expand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parses: list[Path] = []
    original = PresetManager._load_presets

    def counting(self: PresetManager) -> None:
        parses.append(self.preset_dir)
        original(self)

    monkeypatch.setattr(PresetManager, "_load_presets", counting)

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
            app = pilot.app
            await pilot.pause()
            startup = len(parses)
            # One PresetWorkflow parse, plus the ConfigManager builds that
            # resolve the default preset's config and release mode (each
            # ConfigManager owns a PresetManager; utils/ is unchanged). The
            # eager code did 4 here.
            assert startup <= 3, parses
            for _ in range(3):
                await app.run_action("toggle_advanced")
                await pilot.pause()
            assert len(parses) == startup, "Advanced expand re-parsed the presets"
            select = app.query_one("#preset_select", Select)
            default = select.value
            other = next(v for _, v in select._options if v not in (default, SELECT_BLANK))
            select.value = other
            await pilot.pause()
            after_switch = len(parses)
            select.value = default
            await pilot.pause()
            select.value = other
            await pilot.pause()
            assert len(parses) == after_switch, "revisiting a preset re-parsed the presets"

    asyncio.run(scenario())


def test_preset_catalog_reparses_when_a_preset_file_changes(tmp_path: Path) -> None:
    preset_dir = tmp_path / "presets"
    shutil.copytree(REPO_ROOT / "presets", preset_dir)
    catalog = PresetCatalog(preset_dir)
    first = catalog.workflow
    assert catalog.workflow is first  # unchanged files: same parse

    target = preset_dir / "balanced_default.yaml"
    stat = target.stat()
    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    assert catalog.workflow is not first  # edited preset: parsed again

    second = catalog.workflow
    (preset_dir / "low_distortion.yaml").unlink()
    assert catalog.workflow is not second  # removed preset: parsed again


def test_resolved_config_is_a_copy_and_matches_config_manager() -> None:
    from utils.config_manager import ConfigManager

    catalog = PresetCatalog()
    config = catalog.resolved_config("balanced_default")
    assert config == ConfigManager(preset="balanced_default").config
    config["optimization"] = "mutated"
    assert catalog.resolved_config("balanced_default")["optimization"] != "mutated"


def test_resolved_release_mode_tracks_the_override_file(tmp_path: Path) -> None:
    from utils.config_manager import ConfigManager

    override = tmp_path / "override.yaml"
    override.write_text("version: '3.0'\ncompliance_posture: strict\n", encoding="utf-8")
    catalog = PresetCatalog()
    expected = ConfigManager(config_file=str(override), preset="balanced_default").resolve()
    assert (
        catalog.resolved_release_mode("balanced_default", str(override))
        == expected.privacy_release_mode.value
    )
    override.write_text(
        "version: '3.0'\ncompliance_posture: strict\nprivacy_release_mode: verified-safe-coverage\n", encoding="utf-8"
    )
    stat = override.stat()
    os.utime(override, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    changed = ConfigManager(config_file=str(override), preset="balanced_default").resolve()
    assert (
        catalog.resolved_release_mode("balanced_default", str(override))
        == changed.privacy_release_mode.value
    )
