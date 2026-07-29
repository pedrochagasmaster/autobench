from __future__ import annotations

import asyncio

import pytest
from textual.widgets import Checkbox
from unittest.mock import MagicMock

import tui_app
from core.contracts import AnalysisRunRequest, PrivacyRuleStrategy
from tui_app import BenchmarkApp


@pytest.fixture(autouse=True)
def _isolated_tui_session(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tui_app, "SESSION_FILE", tmp_path / "session.yaml")


def test_tui_privacy_sweep_mode_keeps_normal_analysis_form_visible() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 55)) as pilot:
            app = pilot.app
            mode = app.query_one("#privacy_rule_sweep_mode", Checkbox)
            mode.value = True
            await pilot.pause()

            assert not app.query_one("#section_mode").has_class("hidden")
            assert app.query_one("#btn_run").label == "▶  Run Analysis"

    asyncio.run(scenario())


def test_tui_privacy_sweep_mode_is_off_by_default() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 55)) as pilot:
            app = pilot.app
            assert not app.query_one("#privacy_rule_sweep_mode", Checkbox).value

    asyncio.run(scenario())


def test_tui_sweep_request_executes_through_shared_executor(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        fixture = tui_app.Path(__file__).parent / "fixtures" / "gate_demo.csv"
        async with BenchmarkApp().run_test(size=(140, 55)) as pilot:
            app = pilot.app
            app.query_one("#privacy_rule_sweep_mode", Checkbox).value = True
            await pilot.pause()
            request = AnalysisRunRequest.from_widget_values(
                "share",
                {
                    "csv": str(fixture),
                    "entity": "Target",
                    "metric": "txn_cnt",
                    "dimensions": ["card_type", "channel"],
                    "time_col": "year_month",
                    "preset": "balanced_default",
                    "compliance_posture": "strict",
                    "output": str(tmp_path / "tui_sweep.xlsx"),
                    **app._privacy_strategy_values_from_widgets(),
                },
            )
            log = MagicMock()
            monkeypatch.setattr(
                app,
                "call_from_thread",
                lambda fn, *args: fn(*args),
            )

            artifacts = app._execute_run_for_tui(
                request,
                __import__("logging").getLogger("test"),
                log,
            )

            assert artifacts.privacy_rule_strategy_result is not None
            assert (
                artifacts.privacy_rule_strategy_result.strategy
                == PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE
            )

    asyncio.run(scenario())
