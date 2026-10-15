#!/usr/bin/env python3
"""Drive the real Autobench TUI and export one SVG per onboarding step.

The explainer video shows the actual `tui_app.BenchmarkApp`, not a mock, so the
screens in the video cannot drift from the app. This walks the flow documented
under "5 · Your first run" in `docs/autobench-onboarding.html`, using the same
`docs/autobench_demo.csv` a new analyst downloads, and writes:

    public/tui/NN_slug.svg   one screenshot per step
    public/tui/manifest.json step order, captions, and highlight rectangles

Run it from the project directory:

    python3 scripts/capture_tui.py

The analysis really executes, so the final screenshots show a real log and a
real compliance verdict. Everything is written to a scratch directory that is
deleted afterwards; nothing lands in the repository.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
REPO_ROOT = PROJECT_DIR.parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Rich renders SVG screenshots on a fixed cell grid; these are its constants,
# needed to turn Textual widget regions into overlay rectangles.
CHAR_HEIGHT = 20.0
FONT_ASPECT_RATIO = 0.61
CHAR_WIDTH = CHAR_HEIGHT * FONT_ASPECT_RATIO
LINE_HEIGHT = CHAR_HEIGHT * 1.22
ORIGIN_X = 1 + 8  # margin_left + padding_left
ORIGIN_Y = 1 + 40  # margin_top + padding_top

# A realistic terminal that still leaves each character ~17px tall once the
# screenshot is fitted into a 1080p frame. Taller terminals shrink the text
# below what a viewer can read.
TERMINAL_COLUMNS = 140
TERMINAL_ROWS = 40

DEMO_CSV = "autobench_demo.csv"

# The run the video teaches, straight out of "5 · Your first run".
EXPECTED_ENTITY_COL = "issuer_name"
EXPECTED_TARGET = "Target"
EXPECTED_TIME_COL = "year_month"
EXPECTED_PRESET = "compliance_strict"
EXPECTED_METRIC = "txn_cnt"
EXPECTED_DIMENSIONS = ("card_type", "input_mode", "card_type_input_mode")


@dataclass
class Beat:
    """One captured screen, with the teaching caption that goes beside it."""

    slug: str
    caption: str
    action: Optional[Callable[[Any, Any], Awaitable[None]]] = None
    focus: tuple[str, ...] = field(default_factory=tuple)
    """Widget scrolled into view before the screenshot is taken."""
    reveal: Optional[str] = None
    settle: int = 6


async def settle(pilot: Any, ticks: int = 6) -> None:
    for _ in range(ticks):
        await pilot.pause()
        await asyncio.sleep(0.02)


async def reveal(app: Any, pilot: Any, selector: str) -> None:
    """Scroll a widget into view, the way a user tabbing through would."""
    try:
        widget = app.query_one(selector)
    except Exception:
        return
    widget.scroll_visible(animate=False, top=True)
    await settle(pilot, 4)


def widget_rect(app: Any, selector: str) -> Optional[dict[str, float]]:
    """Pixel rectangle of a widget inside the exported SVG."""
    try:
        widget = app.query_one(selector)
    except Exception:
        return None
    region = widget.region
    if region.width <= 0 or region.height <= 0:
        return None
    return {
        "x": ORIGIN_X + region.x * CHAR_WIDTH,
        "y": ORIGIN_Y + region.y * LINE_HEIGHT,
        "width": region.width * CHAR_WIDTH,
        "height": region.height * LINE_HEIGHT,
    }


def build_beats() -> list[Beat]:
    """The onboarding run, one beat per thing the analyst actually does.

    The redesigned TUI (Phase 2) is one screen with five steps: Data, Entity,
    Analysis & mode, Privacy & compliance, Review & run. Values are set on the
    form model (``app.form``), the same state the widgets bind to; each beat
    shows the step that holds the field it teaches.
    """

    async def show(app: Any, pilot: Any, step: str, focus: Any = "entry") -> None:
        await app.ensure_step(step)
        app._show_step(step, focus=focus)
        await settle(pilot, 4)

    async def open_picker(app: Any, pilot: Any) -> None:
        await pilot.press("ctrl+o")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            screen = app.screen
            if type(screen).__name__ == "CsvPickerScreen" and getattr(screen, "_quick_loaded", True):
                break
            await settle(pilot, 1)

    async def choose_file(app: Any, pilot: Any) -> None:
        from textual.widgets import OptionList

        picker = app.screen
        quick = picker.query_one("#picker_quick_list", OptionList)
        if quick.option_count:
            quick.highlighted = 0
            app.set_focus(quick)
            await pilot.press("enter")
        else:
            picker.dismiss(str(Path.cwd() / DEMO_CSV))
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and (not app._csv_loaded or app.entity_values_loading):
            await settle(pilot, 1)
        await show(app, pilot, "data", focus="csv_path")

    async def set_entity_column(app: Any, pilot: Any) -> None:
        app.form.entity_col = EXPECTED_ENTITY_COL
        await show(app, pilot, "entity", focus="entity_col")

    async def set_target(app: Any, pilot: Any) -> None:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and app.entity_values_loading:
            await settle(pilot, 1)
        app.form.entity = EXPECTED_TARGET
        await show(app, pilot, "entity", focus="entity_name")

    async def set_time_column(app: Any, pilot: Any) -> None:
        app.form.time_col = EXPECTED_TIME_COL
        await app.open_more_options()
        await show(app, pilot, "analysis", focus="time_col")

    async def set_preset(app: Any, pilot: Any) -> None:
        app.form.preset = EXPECTED_PRESET
        await show(app, pilot, "privacy", focus="preset_select")

    async def open_preset_guide(app: Any, pilot: Any) -> None:
        await pilot.press("f1")

    async def close_preset_guide(app: Any, pilot: Any) -> None:
        await pilot.press("escape")
        await show(app, pilot, "analysis", focus="analyze_distortion")

    async def set_metric(app: Any, pilot: Any) -> None:
        app.form.metric = EXPECTED_METRIC
        await show(app, pilot, "analysis", focus="share_metric")

    async def set_dimensions(app: Any, pilot: Any) -> None:
        app.form.dimensions = EXPECTED_DIMENSIONS
        await show(app, pilot, "analysis", focus="dims")

    async def show_rate_mode(app: Any, pilot: Any) -> None:
        app.form.mode = "rate"
        await show(app, pilot, "analysis", focus="mode_switch")

    async def back_to_share(app: Any, pilot: Any) -> None:
        app.form.mode = "share"
        await show(app, pilot, "review", focus="btn_run")

    async def start_run(app: Any, pilot: Any) -> None:
        await pilot.press("ctrl+r")
        await settle(pilot, 1)

    async def wait_for_finish(app: Any, pilot: Any) -> None:
        from textual.widgets import Log

        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            state = getattr(app, "_run_state", "idle")
            if state in ("success", "error", "blocked"):
                break
            screen = app.screen
            if type(screen).__name__ == "ValidationModal":
                try:
                    screen.query_one("#btn_proceed").press()
                except Exception:
                    pass
            await settle(pilot, 4)
        await settle(pilot, 10)
        app.clear_notifications()
        # The full-width run log; it keeps its scroll position, and the
        # closing lines are the point.
        app.action_show_log()
        await settle(pilot, 4)
        app.query_one("#log_output", Log).scroll_end(animate=False)
        await settle(pilot, 4)

    async def show_results(app: Any, pilot: Any) -> None:
        app.action_show_log()  # back to the form and the results column
        await settle(pilot, 4)

    return [
        Beat(
            "launch",
            "Launch autobench from the directory holding your CSV. Five steps run "
            "across the top; the bar at the bottom always says whether the run is ready.",
        ),
        Beat(
            "browse",
            "Ctrl+O opens the file picker: quick picks from the launch folder, and a "
            "browser for everything else.",
            action=open_picker,
        ),
        Beat(
            "loaded",
            "Picking the file loads the header row, and every column choice in the "
            "later steps is filled from those columns.",
            action=choose_file,
            focus=("#csv_path",),
        ),
        Beat(
            "entity_column",
            "Step 2: the entity column is the identifier shared by the target and its "
            "peers: issuer_name here.",
            action=set_entity_column,
            focus=("#entity_col",),
        ),
        Beat(
            "target",
            "Target entity is case-sensitive. Name it to compare one client, or leave "
            "it blank for a market view. It is never remembered between sessions.",
            action=set_target,
            focus=("#entity_name",),
        ),
        Beat(
            "time_column",
            "The time column is optional and lives under More options in step 3. The "
            "demo groups by year_month; privacy constraints hold within every period.",
            action=set_time_column,
            focus=("#time_col",),
        ),
        Beat(
            "preset",
            "Step 4: compliance_strict is the default preset. Keep it unless a reviewed "
            "requirement justifies another one.",
            action=set_preset,
            focus=("#preset_select",),
        ),
        Beat(
            "preset_guide",
            "F1 opens help, including the preset guide, without leaving the terminal.",
            action=open_preset_guide,
            settle=8,
        ),
        Beat(
            "options",
            "Analyze impact and Validate input are on by default. Leave them on: "
            "validation catches bad input before the run, and impact analysis shows "
            "what the balancing cost.",
            action=close_preset_guide,
            focus=("#analyze_distortion", "#validate_input"),
        ),
        Beat(
            "metric",
            "In Share mode, the primary metric is the one the weights are optimized on.",
            action=set_metric,
            focus=("#share_metric",),
        ),
        Beat(
            "dimensions",
            "Every dimension you tick adds privacy constraints. Pick only the cuts the "
            "request actually needs.",
            action=set_dimensions,
            focus=("#dims",),
        ),
        Beat(
            "rate_tab",
            "Rate mode asks for a denominator and numerators instead. Same engine, "
            "same privacy enforcement.",
            action=show_rate_mode,
            focus=("#mode_switch",),
        ),
        Beat(
            "running",
            "Back in Share mode, step 5 reviews the run and Ctrl+R starts it. Input "
            "validation happens before the analysis, not after it.",
            action=lambda app, pilot: _run_share(app, pilot, back_to_share, start_run),
            focus=("#run_status",),
            settle=0,
        ),
        Beat(
            "log_tail",
            "The run log ends with Analysis completed successfully, followed by the "
            "posture and the verdict.",
            action=wait_for_finish,
            focus=("#log_output",),
            settle=10,
        ),
        Beat(
            "done",
            "Last run repeats the verdict in plain words and gives the report path; "
            "Ctrl+Y copies it.",
            action=show_results,
            focus=("#results_panel",),
        ),
    ]


async def _run_share(app: Any, pilot: Any, back: Any, run: Any) -> None:
    await back(app, pilot)
    await settle(pilot, 4)
    await run(app, pilot)


async def capture(output_dir: Path) -> list[dict[str, Any]]:
    from tui_app import BenchmarkApp

    app = BenchmarkApp()
    manifest: list[dict[str, Any]] = []

    async with app.run_test(size=(TERMINAL_COLUMNS, TERMINAL_ROWS)) as pilot:
        await settle(pilot, 10)

        for index, beat in enumerate(build_beats()):
            if beat.action is not None:
                await beat.action(app, pilot)
            await settle(pilot, beat.settle)
            if beat.reveal:
                await reveal(app, pilot, beat.reveal)
            app.clear_notifications()
            await settle(pilot, 2)

            svg = strip_font_faces(app.export_screenshot())
            filename = f"{index:02d}_{beat.slug}.svg"
            (output_dir / filename).write_text(svg, encoding="utf-8")
            if names_an_institution(svg):
                raise SystemExit(
                    f"capture aborted: {filename} contains a named institution"
                )

            rects = [widget_rect(app, selector) for selector in beat.focus]
            manifest.append(
                {
                    "slug": beat.slug,
                    "file": f"tui/{filename}",
                    "caption": beat.caption,
                    "highlights": [rect for rect in rects if rect],
                }
            )
            print(f"captured {filename}")

        assert_run_matches_onboarding(app)

    return manifest


def assert_run_matches_onboarding(app: Any) -> None:
    """Fail the capture unless the app really ran the documented configuration.

    The screenshots are shown to new analysts as the run they should copy, so a
    silently mis-configured capture is worse than no capture.
    """
    form = app.form
    checks = {
        "entity column": (form.entity_col, EXPECTED_ENTITY_COL),
        "target entity": (form.entity, EXPECTED_TARGET),
        "time column": (form.time_col, EXPECTED_TIME_COL),
        "preset": (form.preset, EXPECTED_PRESET),
        "primary metric": (form.metric, EXPECTED_METRIC),
        "mode": (form.mode, "share"),
    }
    for label, (actual, expected) in checks.items():
        if actual != expected:
            raise SystemExit(f"capture aborted: {label} is {actual!r}, expected {expected!r}")

    selected = tuple(form.dimensions)
    if selected != EXPECTED_DIMENSIONS:
        raise SystemExit(
            f"capture aborted: dimensions are {selected!r}, expected {EXPECTED_DIMENSIONS!r}"
        )

    run_state = getattr(app, "_run_state", "unknown")
    if run_state != "success":
        raise SystemExit(f"capture aborted: TUI run state is {run_state!r}, expected 'success'")

    print("run state: success · configuration matches the onboarding walkthrough")


# The privacy step's own copy names the Citi declaration (a compliance
# control, not data). Only these UI phrases are allowed (a modal may clip the
# first one); any other mention, such as an entity value in the demo data,
# still aborts the capture.
UI_PHRASES = (
    re.compile(r"A Citi competitor will[^<]*"),
    re.compile(r"25% Citi cap"),
    re.compile(r"Citi competitor:"),
    re.compile(r"Citibank entity"),
    re.compile(r"Pick the exact Citibank value"),
)


def names_an_institution(svg: str) -> bool:
    text = svg.replace("&#160;", " ").replace("&#x27;", "'")
    for phrase in UI_PHRASES:
        text = phrase.sub("", text)
    lowered = text.lower()
    return "citi" in lowered or "santander" in lowered


def strip_font_faces(svg: str) -> str:
    """Drop Rich's CDN @font-face blocks.

    The video loads Fira Code itself, and a render should not depend on a
    network fetch buried inside an inlined SVG.
    """
    out = []
    depth = 0
    index = 0
    while index < len(svg):
        if depth == 0 and svg.startswith("@font-face", index):
            depth = 1
            index = svg.index("{", index) + 1
            continue
        if depth:
            char = svg[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            index += 1
            continue
        out.append(svg[index])
        index += 1
    return "".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_DIR / "public" / "tui",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for stale in args.output_dir.glob("*.svg"):
        stale.unlink()

    work = Path(tempfile.mkdtemp(prefix="autobench-tui-capture-"))
    demo_source = REPO_ROOT / "docs" / DEMO_CSV
    if not demo_source.exists():
        raise SystemExit(f"demo fixture missing: {demo_source}")
    shutil.copy(demo_source, work / DEMO_CSV)

    previous_cwd = Path.cwd()
    os.environ.setdefault("TERM", "xterm-256color")
    # The video is rendered with a Unicode font: use the Unicode status glyphs.
    os.environ.setdefault("AUTOBENCH_GLYPHS", "unicode")
    os.chdir(work)
    try:
        manifest = asyncio.run(capture(args.output_dir))
    finally:
        os.chdir(previous_cwd)
        shutil.rmtree(work, ignore_errors=True)

    (args.output_dir / "manifest.json").write_text(
        json.dumps(
            {
                "columns": TERMINAL_COLUMNS,
                "rows": TERMINAL_ROWS,
                "width": round(TERMINAL_COLUMNS * CHAR_WIDTH + 16) + 2,
                "height": TERMINAL_ROWS * LINE_HEIGHT + 48 + 2,
                "steps": manifest,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(manifest)} screenshots to {args.output_dir}")


if __name__ == "__main__":
    main()
