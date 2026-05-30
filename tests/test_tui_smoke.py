"""End-to-end TUI smoke tests for the documented first-run workflow."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest
from textual.widgets import Select, SelectionList

from tui_app import BenchmarkApp, LogHandler

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "gate_demo.csv"


async def _run_tui_share_smoke(output: Path) -> str:
    async with BenchmarkApp().run_test(size=(120, 40)) as pilot:
        app = pilot.app
        await pilot.pause()

        app.query_one("#csv_path").value = str(FIXTURE)
        app._try_load_csv_from_path_input()
        await pilot.pause()

        app.query_one("#entity_col", Select).value = "issuer_name"
        app.load_unique_entities("issuer_name")
        app.query_one("#entity_name", Select).value = "Target"
        app.query_one("#time_col", Select).value = "year_month"
        app.query_one("#share_metric", Select).value = "txn_cnt"
        app.query_one("#share_auto_dim").value = False
        share_dims = app.query_one("#share_dims", SelectionList)
        share_dims.select("card_type")
        share_dims.select("channel")
        app.query_one("#output_file").value = str(output)
        app.query_one("#validate_input").value = False

        app.run_analysis()
        log_text = ""
        for _ in range(120):
            await pilot.pause(0.5)
            log_text = "\n".join(app.query_one("#log_output").lines)
            if "Analysis completed successfully" in log_text:
                break
            if "Execution Blocked:" in log_text or "Execution Error:" in log_text:
                break
        return log_text


def _cleanup_tui_log_handlers() -> None:
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        if isinstance(handler, LogHandler):
            root_logger.removeHandler(handler)


def test_tui_share_smoke_with_gate_demo(tmp_path: Path) -> None:
    output = tmp_path / "tui_smoke_share.xlsx"
    try:
        log_text = asyncio.run(_run_tui_share_smoke(output))
    finally:
        _cleanup_tui_log_handlers()

    assert output.exists(), log_text
    assert "Analysis completed successfully" in log_text
