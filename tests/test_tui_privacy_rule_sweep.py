from __future__ import annotations

import asyncio
import logging

import pytest
from textual.widgets import Checkbox, Collapsible, Input
from unittest.mock import MagicMock

import tui_app
from core.contracts import (
    AnalysisArtifacts,
    AnalysisRunRequest,
    PrivacyOutputDecision,
    PrivacyRuleStrategy,
)
from tui_app import BenchmarkApp
from utils.logger import (
    DeferredFileHandler,
    finalize_deferred_logging,
    setup_deferred_logging,
)


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


def test_tui_citi_controls_live_in_compliance_declarations_group() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 55)) as pilot:
            compliance = pilot.app.query_one(
                "#compliance_declarations", Collapsible
            )

            assert compliance.collapsed
            assert compliance.query_one(
                "#citi_competitor_receives_output",
                Checkbox,
            )
            assert compliance.query_one("#citibank_entity_name", Input)

            advanced = pilot.app.query_one("#advanced_opt", Collapsible)
            assert not advanced.query("#citi_competitor_receives_output")
            assert not advanced.query("#citibank_entity_name")

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


def test_tui_reports_hard_privacy_denial_as_withheld(tmp_path) -> None:
    app = BenchmarkApp()
    app.call_from_thread = (  # type: ignore[method-assign]
        lambda fn, *args, **kwargs: fn(*args, **kwargs)
    )
    app._begin_run_ui = MagicMock()  # type: ignore[method-assign]
    app._end_run_ui = MagicMock()  # type: ignore[method-assign]
    app.notify = MagicMock()  # type: ignore[method-assign]
    artifacts = AnalysisArtifacts(
        metadata={},
        compliance_summary={
            "compliance_verdict": "blocked",
            "posture": "best_effort",
            "acknowledgement_state": "not_required",
        },
        report_paths=[],
        audit_log_output="denied_NON_PUBLISHABLE_control3_audit.json",
        privacy_output_decision=PrivacyOutputDecision(
            privacy_publication_authorized=False,
            hard_privacy_block=True,
            withholding_reason="control3_numeric_policy_blocked",
        ),
    )
    app._execute_run_for_tui = MagicMock(  # type: ignore[method-assign]
        return_value=artifacts
    )
    log = MagicMock()
    denied_log = tmp_path / "tui_denied.log"
    setup_deferred_logging(
        "INFO",
        str(denied_log),
        console_output=False,
    )

    app._execute_confirmed_analysis(
        AnalysisRunRequest(mode="share", metric="amount"),
        None,
        log,
    )

    end_args = app._end_run_ui.call_args.args
    assert end_args[0] == "blocked"
    assert "Publication withheld" in end_args[1]
    assert "control3_numeric_policy_blocked" in end_args[1]
    assert any(
        "Control 3 privacy denial" in call.args[0]
        for call in log.write.call_args_list
    )
    assert not denied_log.exists()
    assert not any(
        isinstance(handler, DeferredFileHandler)
        for handler in logging.getLogger().handlers
    )


def test_tui_authorized_run_flushes_deferred_log(tmp_path) -> None:
    app = BenchmarkApp()
    app.call_from_thread = (  # type: ignore[method-assign]
        lambda fn, *args, **kwargs: fn(*args, **kwargs)
    )
    app._begin_run_ui = MagicMock()  # type: ignore[method-assign]
    app._end_run_ui = MagicMock()  # type: ignore[method-assign]
    app.notify = MagicMock()  # type: ignore[method-assign]
    artifacts = AnalysisArtifacts(
        metadata={},
        compliance_summary={
            "compliance_verdict": "fully_compliant",
            "posture": "best_effort",
            "acknowledgement_state": "not_required",
        },
        report_paths=["authorized.xlsx"],
        privacy_output_decision=PrivacyOutputDecision(
            privacy_publication_authorized=True,
            hard_privacy_block=False,
        ),
        privacy_sink_authorized=True,
        privacy_log_authorized=True,
    )
    app._execute_run_for_tui = MagicMock(  # type: ignore[method-assign]
        return_value=artifacts
    )
    log = MagicMock()
    authorized_log = tmp_path / "tui_authorized.log"
    setup_deferred_logging(
        "INFO",
        str(authorized_log),
        console_output=False,
    )
    logging.getLogger("benchmark").info("authorized TUI run")

    app._execute_confirmed_analysis(
        AnalysisRunRequest(mode="share", metric="amount"),
        None,
        log,
    )

    assert authorized_log.exists()
    assert "authorized TUI run" in authorized_log.read_text(encoding="utf-8")
    assert app._end_run_ui.call_args.args[0] == "success"


def test_tui_modal_abandonment_discards_deferred_log_while_confirmation_keeps_it(
    tmp_path,
) -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 55)) as pilot:
            app = pilot.app
            log_widget = app.query_one("#log_output")
            request = AnalysisRunRequest(mode="share", metric="amount")

            cancelled_log = tmp_path / "cancelled.log"
            setup_deferred_logging(
                "INFO",
                str(cancelled_log),
                console_output=False,
            )
            app._handle_validation_modal_result(
                False,
                has_errors=False,
                should_abort=False,
                request=request,
                saved_df=None,
                log_widget=log_widget,
            )
            assert not cancelled_log.exists()
            assert not any(
                isinstance(handler, DeferredFileHandler)
                for handler in logging.getLogger().handlers
            )

            confirmed_log = tmp_path / "confirmed.log"
            setup_deferred_logging(
                "INFO",
                str(confirmed_log),
                console_output=False,
            )
            app.run_analysis = MagicMock()  # type: ignore[method-assign]
            app._handle_validation_modal_result(
                True,
                has_errors=False,
                should_abort=False,
                request=request,
                saved_df=None,
                log_widget=log_widget,
            )
            assert any(
                isinstance(handler, DeferredFileHandler)
                for handler in logging.getLogger().handlers
            )
            assert not confirmed_log.exists()
            app.run_analysis.assert_called_once()
            finalize_deferred_logging(
                logging.getLogger(),
                privacy_authorized=False,
            )

            invalid_launch_log = tmp_path / "invalid_launch.log"
            setup_deferred_logging(
                "INFO",
                str(invalid_launch_log),
                console_output=False,
            )
            original_call_from_thread = app.call_from_thread
            app.call_from_thread = (  # type: ignore[method-assign]
                lambda fn, *args, **kwargs: fn(*args, **kwargs)
            )
            app._fail_launch("missing required input")
            app.call_from_thread = original_call_from_thread  # type: ignore[method-assign]
            assert not invalid_launch_log.exists()
            assert not any(
                isinstance(handler, DeferredFileHandler)
                for handler in logging.getLogger().handlers
            )

    asyncio.run(scenario())
