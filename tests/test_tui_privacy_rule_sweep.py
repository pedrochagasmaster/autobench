from __future__ import annotations

import asyncio

import pytest
from textual.widgets import Checkbox, Input

import tui_app
from core.contracts import PrivacySweepStatus
from core.privacy_policy import evaluate_privacy_rule_sweep
from tui_app import BenchmarkApp


@pytest.fixture(autouse=True)
def _isolated_tui_session(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tui_app, "SESSION_FILE", tmp_path / "session.yaml")


def test_tui_privacy_sweep_mode_reveals_form_and_builds_public_request() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 55)) as pilot:
            app = pilot.app
            mode = app.query_one("#privacy_rule_sweep_mode", Checkbox)
            mode.value = True
            await pilot.pause()

            assert not app.query_one("#privacy_sweep_form").has_class("hidden")
            assert app.query_one("#section_mode").has_class("hidden")

            values = {
                "privacy_participant_count": "10",
                "privacy_maximum_share": "22",
                "privacy_count_7": "10",
                "privacy_count_8": "8",
                "privacy_count_10": "3",
                "privacy_count_15": "1",
                "privacy_count_20": "1",
            }
            for widget_id, value in values.items():
                app.query_one(f"#{widget_id}", Input).value = value

            request = app._privacy_sweep_request_from_widgets()
            result = evaluate_privacy_rule_sweep(request)

            assert result.status == PrivacySweepStatus.NUMERICALLY_COMPLIANT
            assert result.authorizing_rules == ("5/25", "6/30")

    asyncio.run(scenario())


def test_tui_privacy_sweep_mode_is_off_by_default() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 55)) as pilot:
            app = pilot.app
            assert not app.query_one("#privacy_rule_sweep_mode", Checkbox).value
            assert app.query_one("#privacy_sweep_form").has_class("hidden")

    asyncio.run(scenario())
