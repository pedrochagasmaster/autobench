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
from textual.widgets import Input, OptionList, Select, Static

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
            # PR 5: F8 opens (and closes) the Expert settings screen. Startup
            # no longer resolves the preset's expert values; the first open
            # does, once, and later opens reuse it.
            await app.run_action("toggle_advanced")
            await pilot.pause()
            first_open = len(parses)
            assert first_open <= 3, parses
            for _ in range(3):
                await app.run_action("toggle_advanced")
                await pilot.pause()
            assert len(parses) == first_open, "Opening Expert settings re-parsed the presets"
            await app.ensure_step("privacy")
            select = app.query_one("#preset_select", Select)
            default = select.value
            other = next(v for _, v in select._options if v not in (default, SELECT_BLANK))
            select.value = other
            await pilot.pause()
            # PR 5: startup no longer resolves the default preset's release
            # mode; the first switch back does. Visit both once, then revisit.
            select.value = default
            await pilot.pause()
            after_switch = len(parses)
            select.value = other
            await pilot.pause()
            select.value = default
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
        # Header (+ PR 5: a small sample for numeric columns) reads; the
        # entity worker reads one column with usecols.
        if kwargs.get("nrows") is not None:
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
            # PR 5 (01 §5.3): a load is never toasted; the meta line under the
            # path is the confirmation.
            assert "CSV loaded" not in toasts, toasts
            meta = app.query_one("#csv_meta", Static)
            first_meta = str(meta.content)
            assert "data.csv" in first_meta

            # The same file edited on disk reloads on the next tab-out. (PR 5:
            # Enter moved focus on to Target entity, so go back to the path.)
            with open(csv_path, "a", encoding="utf-8") as handle:
                handle.write("P9,2024-01,CREDIT,Online,1,10,9,0\n")
            path_input.focus()
            await pilot.pause()
            await pilot.press("tab")
            await _settle(pilot)
            assert len(header_reads) == 2
            assert "data.csv" in str(meta.content)
            assert "CSV loaded" not in toasts, toasts

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
            # PR 5 (01 §5.3): reported inline under the path, not as a toast.
            assert toasts == []
            meta = str(app.query_one("#csv_meta", Static).content)
            assert "Not found:" in meta and "missing.csv" in meta

    asyncio.run(scenario())


# ── 4. CSV picker ─────────────────────────────────────────────────────────


async def _open_picker(pilot):
    from tui_app import CsvPickerScreen

    await pilot.press("ctrl+o")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        await pilot.pause(0.02)
        screen = pilot.app.screen
        # Both lists fill from thread workers (PR 6: quick picks too).
        if isinstance(screen, CsvPickerScreen) and screen._browse_entries and screen._quick_loaded:
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


# ── 6. Large entity lists ─────────────────────────────────────────────────


def _write_entity_csv(path: Path, entities: int, *, alt: int = 5) -> Path:
    width = len(str(entities - 1))
    lines = ["issuer_name,alt_entity,card_type,txn_cnt"]
    for index in range(entities):
        lines.append(f"ENT_{index:0{width}d},ALT_{index % alt},CREDIT,{index + 1}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


async def _load_entities(pilot, csv_path: Path) -> None:
    app = pilot.app
    app.query_one("#csv_path", Input).value = str(csv_path)
    app.load_csv_headers(str(csv_path))
    await _settle(pilot)
    await app.ensure_step("entity")  # PR 5: step 2 mounts on first show


def test_entity_index_prefix_substring_and_cap() -> None:
    from tui_app import EntityIndex

    values = sorted([f"ENT_{i:05d}" for i in range(5000)] + ["acme", "Acme Corp", "zeta"])
    index = EntityIndex(values)
    shown, total = index.matches("ent_0009", limit=200)
    assert total == 10 and shown == [f"ENT_{i:05d}" for i in range(90, 100)]
    shown, total = index.matches("ENT_", limit=200)
    assert total == 5000 and len(shown) == 200
    shown, total = index.matches("corp")  # no prefix match: substring fallback
    assert (shown, total) == (["Acme Corp"], 1)
    shown, total = index.matches("acme")
    assert total == 2 and set(shown) == {"acme", "Acme Corp"}
    assert index.matches("") == (values[:200], len(values))
    assert index.first_with_prefix("ze") == "zeta"
    assert index.first_with_prefix("nope") is None


@pytest.mark.parametrize("count", [tui_app.ENTITY_SELECT_MAX, tui_app.ENTITY_SELECT_MAX + 1])
def test_entity_chooser_switches_above_the_threshold(tmp_path: Path, count: int) -> None:
    csv_path = _write_entity_csv(tmp_path / "entities.csv", count)
    large = count > tui_app.ENTITY_SELECT_MAX

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 45)) as pilot:
            app = pilot.app
            await pilot.pause()
            await _load_entities(pilot, csv_path)
            select = app.query_one("#entity_name", Select)
            picker = app.query_one("#entity_picker")
            assert select.has_class("hidden") is large
            assert picker.has_class("hidden") is not large
            assert len(app.entity_choices) == count
            if large:
                matches = app.query_one("#entity_matches", OptionList)
                assert matches.option_count == 1 + tui_app.ENTITY_MATCH_LIMIT
                assert matches.get_option_at_index(0).id == "peer-only"
                assert len(select._options) <= 1  # the Select never holds the big list
            else:
                assert len([v for _, v in select._options if v != SELECT_BLANK]) == count
            assert app._target_entity_for_run() == (None, None)  # blank = peer-only

    asyncio.run(scenario())


def test_large_entity_picker_only_accepts_exact_values(tmp_path: Path) -> None:
    csv_path = _write_entity_csv(tmp_path / "entities.csv", 5000)

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 45)) as pilot:
            app = pilot.app
            await pilot.pause()
            await _load_entities(pilot, csv_path)
            entity_filter = app.query_one("#entity_filter", Input)
            matches = app.query_one("#entity_matches", OptionList)

            entity_filter.focus()
            await pilot.press(*"ent_0099")
            await pilot.pause()
            assert matches.option_count == 1 + 1
            # Typed text in the wrong case is not an entity: the run is blocked.
            entity, error = app._target_entity_for_run()
            assert entity is None and "not found in issuer_name" in error

            # Accept the inline suggestion: it completes to the real value.
            await pilot.press("right")
            await pilot.pause()
            assert entity_filter.value == "ENT_0099"
            assert app._target_entity_for_run() == ("ENT_0099", None)

            # Choosing from the list sets the exact value.
            entity_filter.value = "ENT_012"
            await pilot.pause()
            matches.focus()
            matches.highlighted = 3
            await pilot.press("enter")
            await pilot.pause()
            assert entity_filter.value == "ENT_0122"
            assert app._target_entity_for_run() == ("ENT_0122", None)

            # The explicit peer-only option clears the choice.
            matches.focus()
            matches.highlighted = 0
            await pilot.press("enter")
            await pilot.pause()
            assert entity_filter.value == ""
            assert app._target_entity_for_run() == (None, None)

            # A value that is no entity at all is blocked, never peer-only.
            entity_filter.value = "NOPE"
            await pilot.pause()
            assert app._target_entity_for_run()[0] is None
            assert app._target_entity_for_run()[1]

    asyncio.run(scenario())


def test_large_entity_typo_blocks_the_launch(tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    csv_path = _write_entity_csv(tmp_path / "entities.csv", 5000)

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 45)) as pilot:
            app = pilot.app
            await pilot.pause()
            await _load_entities(pilot, csv_path)
            app.query_one("#entity_filter", Input).value = "ENT_00x9"
            await pilot.pause()
            fail = MagicMock()
            app._fail_launch = fail  # type: ignore[method-assign]
            app.run_analysis()
            deadline = time.monotonic() + 10
            while not fail.called and time.monotonic() < deadline:
                await pilot.pause(0.02)
            assert fail.call_count == 1
            message = fail.call_args.args[0]
            assert "Target entity not found" in message and "ENT_00x9" not in message
            # Schema v3: the no-match block now records a closed reason
            # (it recorded nothing before); the typed text never does.
            assert fail.call_args.kwargs == {
                "focus_id": "entity_filter",
                "block_reason": "entity_not_found",
            }

    asyncio.run(scenario())


def test_large_entity_choice_survives_reload_and_small_lists_restore_the_select(
    tmp_path: Path,
) -> None:
    big = _write_entity_csv(tmp_path / "big.csv", 5000)
    bigger = _write_entity_csv(tmp_path / "bigger.csv", 6000)

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 45)) as pilot:
            app = pilot.app
            await pilot.pause()
            await _load_entities(pilot, big)
            app.query_one("#entity_filter", Input).value = "ENT_0042"
            await pilot.pause()
            # Another file with the same column: the choice is pending while it
            # loads (launch blocked by the existing guard), then re-applied.
            app.query_one("#csv_path", Input).value = str(bigger)
            app.load_csv_headers(str(bigger))
            await _settle(pilot)
            assert app._target_entity_for_run() == ("ENT_0042", None)
            assert len(app.entity_choices) == 6000

            # A small column goes back to the Select.
            app.query_one("#entity_col", Select).value = "alt_entity"
            await _settle(pilot)
            assert app.query_one("#entity_picker").has_class("hidden")
            assert not app.query_one("#entity_name", Select).has_class("hidden")
            assert app.entity_choices == [f"ALT_{i}" for i in range(5)]
            assert app._target_entity_for_run() == (None, None)

    asyncio.run(scenario())


def test_large_entity_reload_shows_the_disabled_select_while_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    big = _write_entity_csv(tmp_path / "big.csv", 5000)
    other = _write_entity_csv(tmp_path / "other.csv", 5000)
    release = threading.Event()
    real_reader = tui_app.read_unique_entity_values

    def gated(csv_path: str, column: str):
        if csv_path == str(other):
            release.wait(timeout=10)
        return real_reader(csv_path, column)

    monkeypatch.setattr(tui_app, "read_unique_entity_values", gated)

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 45)) as pilot:
            app = pilot.app
            await pilot.pause()
            await _load_entities(pilot, big)
            app.query_one("#entity_filter", Input).value = "ENT_0007"
            await pilot.pause()
            app.query_one("#csv_path", Input).value = str(other)
            app.load_csv_headers(str(other))
            await pilot.pause()
            try:
                select = app.query_one("#entity_name", Select)
                assert app.query_one("#entity_picker").has_class("hidden")
                assert select.disabled and select.prompt == tui_app.ENTITY_LOADING_PROMPT
                assert app.entity_selection_pending  # the existing launch block applies
            finally:
                release.set()
            await _settle(pilot)
            assert app._target_entity_for_run() == ("ENT_0007", None)

    asyncio.run(scenario())


# ── 2. focus-change cost ──────────────────────────────────────────────────


def test_no_focus_within_rule_on_large_containers() -> None:
    import re

    css = re.sub(r"/\*.*?\*/", "", BenchmarkApp.CSS, flags=re.S)
    rules = re.findall(r"([^{}]+):focus-within", css)
    assert rules == [], f":focus-within restyles a whole subtree on every Tab: {rules}"


def test_more_options_disclosure_carries_no_focus_within_rule() -> None:
    """Stock ``Collapsible`` tints ``&:focus-within``; More options must not."""
    from textual.widgets import Collapsible

    from tui.form_widgets import Disclosure

    assert issubclass(Disclosure, Collapsible)
    # Every DEFAULT_CSS the widget inherits (inherit_css=False stops at itself).
    css = "".join(base.DEFAULT_CSS for base in Disclosure._css_bases(Disclosure))
    assert "Disclosure {" in css
    assert "focus-within" not in css
