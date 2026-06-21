"""Capture TUI screenshots for documentation (SVG -> PNG)."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright
from textual.widgets import Select, SelectionList, TabbedContent

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tui_app import BenchmarkApp, LogHandler

FIXTURE = ROOT / "tests" / "fixtures" / "gate_demo.csv"
OUT_DIR = ROOT / "outputs" / "tui_screenshots"


def svg_to_png(svg_text: str, path: Path) -> None:
    svg_path = path.with_suffix(".svg")
    svg_path.write_text(svg_text, encoding="utf-8")
    uri = svg_path.resolve().as_uri()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.goto(uri)
        page.locator("svg").screenshot(path=str(path))
        browser.close()


async def capture() -> list[tuple[str, str]]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frames: list[tuple[str, str]] = []

    async def snap(app: BenchmarkApp, name: str) -> None:
        frames.append((name, app.export_screenshot(title=name.replace("_", " ").title())))

    async with BenchmarkApp().run_test(size=(140, 45)) as pilot:
        app = pilot.app
        await pilot.pause()
        await snap(app, "01_initial_launch")

        app.query_one("#csv_path").value = str(FIXTURE)
        app.load_csv_headers(str(FIXTURE))
        await pilot.pause()
        await snap(app, "02_csv_loaded")

        app.query_one("#entity_col", Select).value = "issuer_name"
        app.load_unique_entities("issuer_name")
        app.query_one("#entity_name", Select).value = "Target"
        app.query_one("#time_col", Select).value = "year_month"
        app.query_one("#share_metric", Select).value = "txn_cnt"
        share_dims = app.query_one("#share_dims", SelectionList)
        share_dims.select("card_type")
        share_dims.select("channel")
        app.query_one("#output_file").value = str(OUT_DIR / "demo_output.xlsx")
        await pilot.pause()
        await snap(app, "03_share_configured")

        tabs = app.query_one(TabbedContent)
        tabs.active = "rate_tab"
        await pilot.pause()
        await snap(app, "04_rate_tab")

        app.action_open_file()
        await pilot.pause()
        await snap(app, "05_csv_picker_modal")
        app.pop_screen()
        await pilot.pause()

        app.action_show_help()
        await pilot.pause()
        await snap(app, "06_preset_help_modal")
        app.pop_screen()
        await pilot.pause()

        app.query_one("#validate_input").value = False
        tabs.active = "share_tab"
        await pilot.pause()
        app.run_analysis()
        for _ in range(120):
            await pilot.pause(0.5)
            log_text = "\n".join(app.query_one("#log_output").lines)
            if "Analysis completed successfully" in log_text:
                break
        await pilot.pause()
        await snap(app, "07_analysis_complete")

    return frames


def export_pngs(frames: list[tuple[str, str]]) -> list[Path]:
    saved: list[Path] = []
    for name, svg_text in frames:
        (OUT_DIR / f"{name}.svg").write_text(svg_text, encoding="utf-8")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        for name, svg_text in frames:
            svg_path = OUT_DIR / f"{name}.svg"
            png_path = OUT_DIR / f"{name}.png"
            page.goto(svg_path.resolve().as_uri())
            page.locator("svg").screenshot(path=str(png_path))
            saved.append(png_path)
        browser.close()
    return saved


def main() -> None:
    try:
        frames = asyncio.run(capture())
        paths = export_pngs(frames)
    finally:
        root_logger = logging.getLogger()
        for handler in list(root_logger.handlers):
            if isinstance(handler, LogHandler):
                root_logger.removeHandler(handler)

    print("Saved screenshots:")
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
