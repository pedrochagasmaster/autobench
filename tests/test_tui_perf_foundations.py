"""Phase 2 PR 2: TUI performance foundations (03 §1–§4, §6).

Each test pins the behaviour a performance fix must keep, plus the fix itself
(no repeated parse, no repeated reload, capped lists, worker scans).
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest
from textual.widgets import Input, OptionList, Select

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
    assert changed.privacy_release_mode != expected.privacy_release_mode
    assert (
        catalog.resolved_release_mode("balanced_default", str(override))
        == changed.privacy_release_mode.value
    )


# ── 1.4 lazy core.analysis_run ────────────────────────────────────────────


def test_analysis_run_is_prewarmed_off_the_ui_thread_after_mount(tmp_path: Path) -> None:
    """Import stays light; a thread worker loads the engine once the app is up."""
    code = textwrap.dedent(
        f"""
        import asyncio, json, os, sys, threading, time
        os.environ["AUTOBENCH_TELEMETRY"] = "0"
        from pathlib import Path
        import tui_app
        tui_app.SESSION_FILE = Path({str(tmp_path / "session.yaml")!r})
        result = {{"at_import": "core.analysis_run" in sys.modules}}
        importers = []
        original = tui_app.importlib.import_module

        def tracking(name, *args, **kwargs):
            if name == "core.analysis_run":
                importers.append(threading.current_thread() is threading.main_thread())
            return original(name, *args, **kwargs)

        tui_app.importlib.import_module = tracking

        async def scenario():
            async with tui_app.BenchmarkApp().run_test(size=(120, 40)) as pilot:
                deadline = time.monotonic() + 60
                while tui_app._ANALYSIS_RUN is None and time.monotonic() < deadline:
                    await pilot.pause(0.05)
                module = sys.modules["core.analysis_run"]
                result["prewarmed"] = tui_app._ANALYSIS_RUN is not None
                result["same_module"] = tui_app._analysis_run() is module
                result["run_blocked"] = tui_app.RunBlocked is module.RunBlocked

        asyncio.run(scenario())
        result["importers_on_main_thread"] = importers
        print(json.dumps(result))
        """
    )
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    assert out.returncode == 0, out.stderr
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result == {
        "at_import": False,
        "prewarmed": True,
        "same_module": True,
        "run_blocked": True,
        "importers_on_main_thread": [False],
    }


# ── 3. CSV path: reload only when the file changed ────────────────────────


def _spy_notifications(app: BenchmarkApp) -> list:
    titles: list = []
    original = app.notify

    def spy(message, *args, **kwargs):
        titles.append(kwargs.get("title"))
        return original(message, *args, **kwargs)

    app.notify = spy  # type: ignore[method-assign]
    return titles


def test_csv_tab_out_reloads_only_when_the_file_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    csv_path = tmp_path / "data.csv"
    shutil.copy(FIXTURE, csv_path)
    header_reads: list = []
    real_read_csv = tui_app.pd.read_csv

    def counting_read_csv(path, *args, **kwargs):
        if kwargs.get("nrows") == 0:
            header_reads.append(str(path))
        return real_read_csv(path, *args, **kwargs)

    monkeypatch.setattr(tui_app.pd, "read_csv", counting_read_csv)

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 45)) as pilot:
            app = pilot.app
            await pilot.pause()
            toasts = _spy_notifications(app)
            path_input = app.query_one("#csv_path", Input)
            path_input.focus()
            path_input.value = str(csv_path)
            await pilot.press("enter")
            await _settle(pilot)
            assert header_reads == [str(csv_path)]

            for _ in range(4):
                path_input.focus()
                await pilot.pause()
                await pilot.press("tab")
                await _settle(pilot)
            path_input.focus()
            await pilot.press("enter")  # Enter on the unchanged path: no-op too
            await _settle(pilot)
            assert header_reads == [str(csv_path)], "unchanged CSV was re-read"
            assert toasts.count("CSV Loaded") == 1, toasts

            # The same file edited on disk reloads on the next tab-out.
            with open(csv_path, "a", encoding="utf-8") as handle:
                handle.write("P9,2024-01,CREDIT,Online,1,10,9,0\n")
            await pilot.press("tab")
            await _settle(pilot)
            assert len(header_reads) == 2
            assert toasts.count("CSV Loaded") == 2

    asyncio.run(scenario())


def test_csv_tab_out_still_reports_a_missing_file(tmp_path: Path) -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 45)) as pilot:
            app = pilot.app
            await pilot.pause()
            toasts = _spy_notifications(app)
            path_input = app.query_one("#csv_path", Input)
            path_input.focus()
            path_input.value = str(tmp_path / "missing.csv")
            await pilot.pause()
            await pilot.press("tab")
            await pilot.pause()
            assert toasts == ["Invalid Path"]

    asyncio.run(scenario())


# ── 4. CSV picker ─────────────────────────────────────────────────────────


async def _open_picker(pilot):
    from tui_app import CsvPickerScreen

    await pilot.press("ctrl+o")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        await pilot.pause(0.02)
        screen = pilot.app.screen
        if isinstance(screen, CsvPickerScreen) and screen._browse_entries:
            break
    await pilot.pause()
    return pilot.app.screen


def test_csv_picker_caps_quick_picks_and_lists_the_cwd_in_a_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    from tui_app import QUICK_PICK_LIMIT

    for index in range(QUICK_PICK_LIMIT + 70):
        (tmp_path / f"file_{index:03d}.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (tmp_path / "UPPER.CSV").write_text("a\n1\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    (tmp_path / ".hidden.csv").write_text("a\n1\n", encoding="utf-8")
    for name in ("sub", ".git", "__pycache__"):
        (tmp_path / name).mkdir()
    (tmp_path / "sub" / "inner.csv").write_text("a\n1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    on_main_thread: list = []
    real_scan = tui_app.scan_csv_directory

    def tracking_scan(directory: str):
        on_main_thread.append(threading.current_thread() is threading.main_thread())
        return real_scan(directory)

    monkeypatch.setattr(tui_app, "scan_csv_directory", tracking_scan)

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 45)) as pilot:
            app = pilot.app
            picked: list = []
            app.load_csv_headers = lambda path, **_kw: picked.append(path)  # type: ignore[method-assign]
            await pilot.pause()
            screen = await _open_picker(pilot)

            quick = screen.query_one("#picker_quick_list", OptionList)
            total = QUICK_PICK_LIMIT + 70  # *.csv glob is case-sensitive: UPPER.CSV is browse-only
            assert quick.option_count == QUICK_PICK_LIMIT
            assert f"of {total}" in str(screen.query_one("#picker_quick_title").render())

            browse = screen.query_one("#picker_browse_list", OptionList)
            ids = [browse.get_option_at_index(i).id for i in range(browse.option_count)]
            assert ids[0] == f"d:{tmp_path.parent}"  # ".." first
            assert ids[1] == f"d:{tmp_path / 'sub'}"  # directories before files
            files = {i[2:] for i in ids if i.startswith("f:")}
            assert files == {str(tmp_path / f"file_{n:03d}.csv") for n in range(total)} | {
                str(tmp_path / "UPPER.CSV")
            }
            assert on_main_thread == [False]

            # Filter narrows both lists.
            screen.query_one("#picker_filter", Input).value = "file_119"
            await pilot.pause()
            assert quick.option_count == 1
            assert [browse.get_option_at_index(i).id for i in range(browse.option_count)] == [
                f"d:{tmp_path.parent}",
                f"f:{tmp_path / 'file_119.csv'}",
            ]
            screen.query_one("#picker_filter", Input).value = ""
            await pilot.pause()

            # Keyboard: Enter on a directory opens it, Enter on a file picks it.
            browse.focus()
            browse.highlighted = 1
            await pilot.press("enter")
            deadline = time.monotonic() + 10
            while screen._browse_dir != str(tmp_path / "sub") or browse.option_count != 2:
                assert time.monotonic() < deadline
                await pilot.pause(0.02)
            browse.highlighted = 1
            await pilot.press("enter")
            await pilot.pause()
            assert picked == [str(tmp_path / "sub" / "inner.csv")]
            assert app.query_one("#csv_path", Input).value == picked[0]

            # Escape cancels without loading anything.
            screen = await _open_picker(pilot)
            await pilot.press("escape")
            await pilot.pause()
            assert app.screen is not screen
            assert len(picked) == 1

            # Enter on a quick pick picks it (newest first).
            newest = tmp_path / "file_005.csv"
            stat = newest.stat()
            os.utime(newest, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10_000_000_000))
            screen = await _open_picker(pilot)
            assert app.focused is screen.query_one("#picker_quick_list", OptionList)
            await pilot.press("enter")
            await pilot.pause()
            assert picked[-1] == "file_005.csv"

    asyncio.run(scenario())


def test_quick_picks_are_deduplicated_across_patterns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "a.csv").write_text("a\n", encoding="utf-8")
    (tmp_path / "data" / "b.csv").write_text("a\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tui_app, "QUICK_PICK_PATTERNS", ("*.csv", "data/*.csv", "*.csv"))
    picks = BenchmarkApp()._quick_pick_files()
    assert sorted(picks) == ["a.csv", "data/b.csv"]
    assert len(picks) == len(set(picks))


# ── 2. focus-change cost ──────────────────────────────────────────────────


def test_no_focus_within_rule_on_large_containers() -> None:
    import re

    css = re.sub(r"/\*.*?\*/", "", BenchmarkApp.CSS, flags=re.S)
    rules = re.findall(r"([^{}]+):focus-within", css)
    assert rules == [], f":focus-within restyles a whole subtree on every Tab: {rules}"
