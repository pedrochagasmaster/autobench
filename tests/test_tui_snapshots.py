"""SVG snapshot tests for the redesigned TUI (Phase 2 PR 6).

Every step, the Expert screen, the dialogs, the run states and the results
view, each at 80x24 and 120x40, in colour and under NO_COLOR. Scenes and the
determinism rules (fixed clock, log stamps, paths and engine) live in
``tests/tui_scenes.py``. Snapshots are stored by pytest-textual-snapshot
under ``tests/__snapshots__/test_tui_snapshots/``.

Update after an intended visual change, then review the SVG diffs:

    uv run python -m pytest tests/test_tui_snapshots.py --snapshot-update
"""

from __future__ import annotations

from pathlib import Path

import pytest

import tui_app
from tests import tui_scenes

SIZES = {"80x24": (80, 24), "120x40": (120, 40)}


@pytest.fixture(autouse=True)
def _release_stub_engine():
    yield
    tui_scenes.release_running()


@pytest.mark.parametrize("color", ["color", "nocolor"])
@pytest.mark.parametrize("size", list(SIZES))
@pytest.mark.parametrize("scene", list(tui_scenes.SCENES))
def test_tui_snapshot(
    scene: str, size: str, color: str, snap_compare, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tui_scenes.install_determinism(monkeypatch, tmp_path)
    if color == "nocolor":
        monkeypatch.setenv("NO_COLOR", "1")
    else:
        monkeypatch.delenv("NO_COLOR", raising=False)
    assert snap_compare(
        tui_app.BenchmarkApp(),
        terminal_size=SIZES[size],
        run_before=tui_scenes.SCENES[scene],
    )
