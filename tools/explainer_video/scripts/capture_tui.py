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
    """The onboarding run, one beat per thing the analyst actually does."""

    async def open_picker(app: Any, pilot: Any) -> None:
        await pilot.press("ctrl+o")

    async def choose_file(app: Any, pilot: Any) -> None:
        from textual.widgets import ListView

        picker = app.screen
        quick = picker.query_one("#picker_quick_list", ListView)
        if quick.children:
            quick.index = 0
            app.set_focus(quick)
            await pilot.press("enter")
        else:
            picker.dismiss(str(Path.cwd() / DEMO_CSV))

    async def set_entity_column(app: Any, pilot: Any) -> None:
        app.query_one("#entity_col").value = "issuer_name"

    async def set_target(app: Any, pilot: Any) -> None:
        app.query_one("#entity_name").value = "Target"

    async def set_time_column(app: Any, pilot: Any) -> None:
        app.query_one("#time_col").value = "year_month"

    async def set_preset(app: Any, pilot: Any) -> None:
        app.query_one("#preset_select").value = "compliance_strict"

    async def set_metric(app: Any, pilot: Any) -> None:
        app.query_one("#share_metric").value = "txn_cnt"

    async def set_dimensions(app: Any, pilot: Any) -> None:
        from textual.widgets import SelectionList

        dims = app.query_one("#share_dims", SelectionList)
        for value in EXPECTED_DIMENSIONS:
            dims.select(value)

    async def open_preset_guide(app: Any, pilot: Any) -> None:
        await pilot.press("f1")

    async def close_preset_guide(app: Any, pilot: Any) -> None:
        await pilot.press("escape")

    async def show_rate_tab(app: Any, pilot: Any) -> None:
        from textual.widgets import TabbedContent

        app.query_one(TabbedContent).active = "rate_tab"

    async def back_to_share(app: Any, pilot: Any) -> None:
        from textual.widgets import TabbedContent

        app.query_one(TabbedContent).active = "share_tab"

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
        # The log keeps its scroll position; the closing lines are the point.
        app.query_one("#log_output", Log).scroll_end(animate=False)
        await settle(pilot, 4)

    async def hold(app: Any, pilot: Any) -> None:
        await settle(pilot, 4)

    return [
        Beat(
            "launch",
            "Launch autobench from the directory holding your CSV. Four numbered "
            "sections on the left, run activity on the right.",
        ),
        Beat(
            "browse",
            "Ctrl+O opens Browse…, which lists the CSV files in the directory you "
            "launched from.",
            action=open_picker,
        ),
        Beat(
            "loaded",
            "Picking the file loads the header row, and every selector below is "
            "populated from those columns.",
            action=choose_file,
            focus=("#section_data",),
            reveal="#section_data",
        ),
        Beat(
            "entity_column",
            "Entity ID column is the identifier shared by the target and its peers: "
            "issuer_name here.",
            action=set_entity_column,
            focus=("#entity_col",),
            reveal="#section_entity",
        ),
        Beat(
            "target",
            "Target entity is case-sensitive. Name it to compare one client, or leave "
            "it blank for a market view.",
            action=set_target,
            focus=("#entity_name",),
            reveal="#section_entity",
        ),
        Beat(
            "time_column",
            "The time period column is optional. The demo groups by year_month, and "
            "privacy constraints are enforced within every period.",
            action=set_time_column,
            focus=("#time_col",),
            reveal="#section_analysis",
        ),
        Beat(
            "preset",
            "compliance_strict is already selected: it is the default preset. Keep it "
            "unless a reviewed requirement justifies another one.",
            action=set_preset,
            focus=("#preset_select",),
            reveal="#section_analysis",
        ),
        Beat(
            "preset_guide",
            "F1 opens the Preset Guide, which describes every preset without leaving "
            "the terminal.",
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
            reveal="#analyze_distortion",
        ),
        Beat(
            "metric",
            "On the Share tab, the primary metric is the one the weights are optimized "
            "on.",
            action=set_metric,
            focus=("#share_metric",),
            reveal="#section_mode",
        ),
        Beat(
            "dimensions",
            "Every dimension you tick adds privacy constraints. Pick only the cuts the "
            "request actually needs.",
            action=set_dimensions,
            focus=("#share_dims",),
            reveal="#share_dims",
        ),
        Beat(
            "rate_tab",
            "The Rate tab asks for a denominator and numerators instead. Same engine, "
            "same privacy enforcement.",
            action=show_rate_tab,
            focus=("#rate_total",),
            reveal="#section_mode",
        ),
        Beat(
            "running",
            "Back on Share, Ctrl+R starts the run. Input validation happens before the "
            "analysis, not after it.",
            action=lambda app, pilot: _run_share(app, pilot, back_to_share, start_run),
            focus=("#run_status",),
            settle=0,
        ),
        Beat(
            "log_tail",
            "The execution log ends with Analysis completed successfully, followed by "
            "the posture and the verdict.",
            action=wait_for_finish,
            focus=("#log_output",),
            settle=10,
        ),
        Beat(
            "done",
            "Last Run repeats the verdict and gives the output path. fully_compliant "
            "under a strict posture is a good run.",
            action=hold,
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

            svg = strip_font_faces(app.export_screenshot())
            filename = f"{index:02d}_{beat.slug}.svg"
            (output_dir / filename).write_text(svg, encoding="utf-8")
            if "citi" in svg.lower() or "santander" in svg.lower():
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
    from textual.widgets import SelectionList

    checks = {
        "entity column": (app.query_one("#entity_col").value, EXPECTED_ENTITY_COL),
        "target entity": (app.query_one("#entity_name").value, EXPECTED_TARGET),
        "time column": (app.query_one("#time_col").value, EXPECTED_TIME_COL),
        "preset": (app.query_one("#preset_select").value, EXPECTED_PRESET),
        "primary metric": (app.query_one("#share_metric").value, EXPECTED_METRIC),
    }
    for label, (actual, expected) in checks.items():
        if actual != expected:
            raise SystemExit(f"capture aborted: {label} is {actual!r}, expected {expected!r}")

    selected = tuple(app.query_one("#share_dims", SelectionList).selected)
    if selected != EXPECTED_DIMENSIONS:
        raise SystemExit(
            f"capture aborted: dimensions are {selected!r}, expected {EXPECTED_DIMENSIONS!r}"
        )

    run_state = getattr(app, "_run_state", "unknown")
    if run_state != "success":
        raise SystemExit(f"capture aborted: TUI run state is {run_state!r}, expected 'success'")

    print("run state: success · configuration matches the onboarding walkthrough")


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
