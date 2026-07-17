"""Capture real Autobench TUI footage for the promo video.

Drives the actual TUI with Textual's Pilot (no mocked screens), saving SVG
screenshots of key states to a working directory. Convert them to PNGs with
scripts/render_footage.sh afterwards.

Usage (from the repo root):
    python3 tools/promo_video/scripts/capture_footage.py
"""

import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
os.chdir(REPO_ROOT)

from textual.widgets import Input, Select, SelectionList  # noqa: E402

import tui_app  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "footage_svg"
OUT.mkdir(parents=True, exist_ok=True)

SIZE = (140, 42)


async def main() -> None:
    # Isolate session persistence so restored state from previous runs
    # doesn't leak into the "fresh app" footage.
    session_dir = tempfile.mkdtemp(prefix="promo_session_")
    tui_app.SESSION_FILE = Path(session_dir) / "session.yaml"

    app = tui_app.BenchmarkApp()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause(0.5)
        app.save_screenshot(str(OUT / "01_fresh.svg"))

        csv_input = app.query_one("#csv_path", Input)
        csv_input.value = "tests/fixtures/gate_demo.csv"
        app.load_csv_headers("tests/fixtures/gate_demo.csv")
        await pilot.pause(0.6)
        app.save_screenshot(str(OUT / "02_loaded.svg"))

        app.query_one("#entity_col", Select).value = "issuer_name"
        await pilot.pause(0.4)
        app.query_one("#entity_name", Select).value = "Target"
        app.query_one("#time_col", Select).value = "year_month"
        app.query_one("#preset_select", Select).value = "balanced_default"
        await pilot.pause(0.4)
        app.save_screenshot(str(OUT / "03_entity.svg"))

        app.query_one("#share_metric", Select).value = "txn_cnt"
        dims = app.query_one("#share_dims", SelectionList)
        dims.select("card_type")
        dims.select("channel")
        await pilot.pause(0.4)

        # `outputs/` is gitignored, and the short relative path reads well in
        # the "Last Run" panel that appears in the final frame.
        app.query_one("#output_file", Input).value = "outputs/issuers_q2_share.xlsx"
        app.query_one("#validate_input").value = False
        app.query_one("#compare_presets").value = False
        # Focus first so the config pane scrolls the button into view;
        # Pilot cannot click targets outside the visible region.
        app.query_one("#btn_run").focus()
        await pilot.pause(0.3)
        await pilot.click("#btn_run")

        deadline = time.time() + 90
        while time.time() < deadline:
            await pilot.pause(0.3)
            if getattr(app, "_run_state", "idle") == "success":
                break
        await pilot.pause(1.0)
        app.save_screenshot(str(OUT / "06_done.svg"))
        print("final run state:", getattr(app, "_run_state", "?"))
        print("SVG footage written to", OUT)


if __name__ == "__main__":
    asyncio.run(main())
