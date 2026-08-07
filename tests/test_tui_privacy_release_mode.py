"""Textual pilot tests for the privacy release mode TUI control (Plan 002 Commit 7).

Widget-level cases plus runtime shared-executor, safe summary, empty Release
Set denial, and suppressed-marker leak checks.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml
from textual.widgets import Checkbox, Label, Select, Static, TabbedContent

import tui_app
from core.contracts import (
    AnalysisArtifacts,
    AnalysisRunRequest,
    CoverageCertificate,
    PrivacyOutputDecision,
    PrivacyReleaseMode,
    PrivacyRuleStrategy,
)
from core.privacy_coverage_verifier import VERIFIER_RESULT_PASSED
from core.privacy_output_policy import CONTROL3_SAFE_COVERAGE_EMPTY
from tests.fixtures.safe_coverage_fixture import (
    build_safe_coverage_getnet_shaped_df,
    write_safe_coverage_bounds_config,
)
from tests.test_privacy_coverage_outputs import SUPPRESSED_MARKER, _seed_suppressed_marker
from tui_app import BenchmarkApp


@pytest.fixture(autouse=True)
def _isolated_tui_session(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tui_app, "SESSION_FILE", tmp_path / "session.yaml")


def test_privacy_release_mode_defaults_to_complete_output() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 55)) as pilot:
            app = pilot.app
            await pilot.pause()
            select = app.query_one("#privacy_release_mode", Select)
            assert select.value == PrivacyReleaseMode.COMPLETE_OUTPUT.value

    asyncio.run(scenario())


def test_privacy_release_mode_shows_both_visible_labels() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 55)) as pilot:
            app = pilot.app
            await pilot.pause()
            select = app.query_one("#privacy_release_mode", Select)
            labels = {label for label, _value in select._options}
            values = {value for _label, value in select._options}
            assert labels == {"Complete output", "Verified safe coverage"}
            assert values == {
                PrivacyReleaseMode.COMPLETE_OUTPUT.value,
                PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE.value,
            }
            hint = app.query_one("#privacy_release_mode_hint", Static)
            assert str(hint.render()) == (
                "Verified safe coverage publishes only verified safe units. "
                "Missing units are privacy-suppressed. "
                "Coverage is not a maximum claim."
            )

    asyncio.run(scenario())


def test_privacy_release_mode_visible_for_share_analysis() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 55)) as pilot:
            app = pilot.app
            await pilot.pause()
            tabs = app.query_one(TabbedContent)
            tabs.active = "share_tab"
            await pilot.pause()
            assert app._analysis_mode() == "share"
            for widget_id in (
                "privacy_release_mode_label",
                "privacy_release_mode",
                "privacy_release_mode_hint",
            ):
                assert not app.query_one(f"#{widget_id}").has_class("hidden")

    asyncio.run(scenario())


def test_privacy_release_mode_hidden_for_rate_analysis() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 55)) as pilot:
            app = pilot.app
            await pilot.pause()
            tabs = app.query_one(TabbedContent)
            tabs.active = "rate_tab"
            await pilot.pause()
            assert app._analysis_mode() == "rate"
            for widget_id in (
                "privacy_release_mode_label",
                "privacy_release_mode",
                "privacy_release_mode_hint",
            ):
                assert app.query_one(f"#{widget_id}").has_class("hidden")

    asyncio.run(scenario())


def test_verified_safe_coverage_enables_and_locks_rule_sweep() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 55)) as pilot:
            app = pilot.app
            await pilot.pause()
            sweep = app.query_one("#privacy_rule_sweep_mode", Checkbox)
            assert sweep.value is False
            assert sweep.disabled is False

            app.query_one("#privacy_release_mode", Select).value = (
                PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE.value
            )
            await pilot.pause()

            assert sweep.value is True
            assert sweep.disabled is True

    asyncio.run(scenario())


def test_return_to_complete_output_restores_sweep_control() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 55)) as pilot:
            app = pilot.app
            await pilot.pause()
            sweep = app.query_one("#privacy_rule_sweep_mode", Checkbox)
            release = app.query_one("#privacy_release_mode", Select)

            sweep.value = False
            await pilot.pause()
            release.value = PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE.value
            await pilot.pause()
            assert sweep.value is True
            assert sweep.disabled is True

            release.value = PrivacyReleaseMode.COMPLETE_OUTPUT.value
            await pilot.pause()
            assert sweep.disabled is False
            assert sweep.value is False

            sweep.value = True
            await pilot.pause()
            release.value = PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE.value
            await pilot.pause()
            release.value = PrivacyReleaseMode.COMPLETE_OUTPUT.value
            await pilot.pause()
            assert sweep.disabled is False
            assert sweep.value is True

    asyncio.run(scenario())


def test_yaml_refresh_updates_privacy_release_mode_selection(tmp_path: Path) -> None:
    config_path = tmp_path / "release_mode.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": "3.0",
                "compliance_posture": "strict",
                "privacy_release_mode": "verified-safe-coverage",
            }
        ),
        encoding="utf-8",
    )

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 55)) as pilot:
            app = pilot.app
            await pilot.pause()
            select = app.query_one("#privacy_release_mode", Select)
            assert select.value == PrivacyReleaseMode.COMPLETE_OUTPUT.value

            app.advanced_config_path = str(config_path)
            app._refresh_privacy_release_mode_from_config()
            await pilot.pause()

            assert select.value == PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE.value
            sweep = app.query_one("#privacy_rule_sweep_mode", Checkbox)
            assert sweep.value is True
            assert sweep.disabled is True

    asyncio.run(scenario())


def test_preset_refresh_shows_resolved_complete_output() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 55)) as pilot:
            app = pilot.app
            await pilot.pause()
            select = app.query_one("#privacy_release_mode", Select)
            select.value = PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE.value
            await pilot.pause()

            # Stock presets resolve to complete-output; preset load refreshes.
            app._refresh_privacy_release_mode_from_config()
            await pilot.pause()
            assert select.value == PrivacyReleaseMode.COMPLETE_OUTPUT.value

    asyncio.run(scenario())


def test_session_save_and_restore_privacy_release_mode(tmp_path: Path, monkeypatch) -> None:
    session_file = tmp_path / "session.yaml"
    monkeypatch.setattr(tui_app, "SESSION_FILE", session_file)

    async def save_scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 55)) as pilot:
            app = pilot.app
            await pilot.pause()
            app.query_one("#privacy_release_mode", Select).value = (
                PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE.value
            )
            await pilot.pause()
            app._save_session()

    asyncio.run(save_scenario())

    saved = yaml.safe_load(session_file.read_text(encoding="utf-8"))
    assert saved["privacy_release_mode"] == PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE.value

    async def restore_scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 55)) as pilot:
            app = pilot.app
            await pilot.pause(0.3)
            # Allow call_after_refresh bootstrap finalizer to re-assert session.
            await pilot.pause()
            select = app.query_one("#privacy_release_mode", Select)
            assert select.value == PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE.value
            sweep = app.query_one("#privacy_rule_sweep_mode", Checkbox)
            assert sweep.value is True
            assert sweep.disabled is True

    asyncio.run(restore_scenario())


def test_session_restore_rejects_stale_privacy_release_mode(
    tmp_path: Path, monkeypatch
) -> None:
    session_file = tmp_path / "session.yaml"
    session_file.write_text(
        yaml.safe_dump({"privacy_release_mode": "not-a-real-mode"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(tui_app, "SESSION_FILE", session_file)
    warnings: list[str] = []

    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 55)) as pilot:
            app = pilot.app
            original_notify = app.notify

            def capture_notify(message, *args, **kwargs):
                warnings.append(str(message))
                return original_notify(message, *args, **kwargs)

            app.notify = capture_notify  # type: ignore[method-assign]
            # Re-apply after notify patch so the warning is captured.
            app._restore_privacy_release_mode("not-a-real-mode")
            await pilot.pause()
            assert (
                app.query_one("#privacy_release_mode", Select).value
                == PrivacyReleaseMode.COMPLETE_OUTPUT.value
            )
            assert any("fell back to Complete output" in message for message in warnings)

    asyncio.run(scenario())


def test_from_widget_values_builds_privacy_release_mode_enum() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 55)) as pilot:
            app = pilot.app
            await pilot.pause()
            app.query_one("#privacy_release_mode", Select).value = (
                PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE.value
            )
            await pilot.pause()

            values = {
                "csv": "data.csv",
                "metric": "txn_cnt",
                "per_dimension_weights": False,
                **app._privacy_values_from_widgets(),
            }
            request = AnalysisRunRequest.from_widget_values("share", values)
            assert (
                request.privacy_release_mode
                is PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE
            )
            assert (
                request.privacy_rule_strategy
                is PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE
            )
            assert request.per_dimension_weights is False

    asyncio.run(scenario())


def test_hidden_verified_value_never_reaches_rate_request() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 55)) as pilot:
            app = pilot.app
            await pilot.pause()
            app.query_one("#privacy_release_mode", Select).value = (
                PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE.value
            )
            await pilot.pause()

            tabs = app.query_one(TabbedContent)
            tabs.active = "rate_tab"
            await pilot.pause()
            assert app._analysis_mode() == "rate"
            assert app.query_one("#privacy_release_mode").has_class("hidden")
            # Widget still holds verified safe coverage, but rate request construction must not.
            assert (
                app.query_one("#privacy_release_mode", Select).value
                == PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE.value
            )
            values = app._privacy_values_from_widgets()
            assert values["privacy_release_mode"] is None
            request = AnalysisRunRequest.from_widget_values(
                "rate",
                {
                    "csv": "data.csv",
                    "total_col": "total",
                    "approved_col": "approved",
                    **values,
                },
            )
            assert request.privacy_release_mode is None

    asyncio.run(scenario())


def test_privacy_release_mode_label_lives_in_analysis_options() -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 55)) as pilot:
            app = pilot.app
            await pilot.pause()
            section = app.query_one("#section_analysis")
            assert section.query_one("#privacy_release_mode", Select)
            assert section.query_one("#privacy_release_mode_label", Label)
            assert section.query_one("#privacy_rule_sweep_mode", Checkbox)

    asyncio.run(scenario())


def _msc_share_request(tmp_path: Path, df, *, output_name: str) -> AnalysisRunRequest:
    config_path = write_safe_coverage_bounds_config(tmp_path / "bounds.yaml")
    return AnalysisRunRequest(
        mode="share",
        df=df,
        metric="transaction_amount",
        secondary_metrics=["transaction_count", "merchant_count"],
        dimensions=["region", "sector"],
        time_col="quarter",
        entity_col="issuer_name",
        output=str(tmp_path / output_name),
        output_format="analysis",
        report_format=None,
        export_balanced_csv=False,
        audit_package=False,
        privacy_rule_strategy=PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE,
        privacy_release_mode=PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE,
        validate_input=False,
        compliance_posture="best_effort",
        config=str(config_path),
        preset=None,
        per_dimension_weights=False,
    )


def _client_certificate(
    *,
    candidate: int = 9,
    released: int = 4,
    cert_path: str | None = None,
) -> CoverageCertificate:
    suppressed = candidate - released
    visible = tuple(f"visible_unit_{i}" for i in range(released))
    return CoverageCertificate(
        privacy_release_mode=PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE,
        candidate_unit_count=candidate,
        released_unit_count=released,
        suppressed_unit_count=suppressed,
        coverage_percentage=0.0 if candidate == 0 else 100.0 * released / candidate,
        visible_publication_unit_keys=visible,
        authorizing_rules={key: "5/25" for key in visible},
        global_weights={"PeerA": 1.0},
        policy_version="v5",
        policy_source="docs",
        rule_set_digest="rules",
        solver_name="scipy.optimize.milp",
        solver_version="1.18.0",
        search_method="test-search-v1",
        search_state="search_complete",
        candidate_vectors_evaluated=10,
        artifact_hashes={"analysis": "abc"},
        certificate_digest="digest",
    )


def test_tui_maximize_executes_through_shared_executor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 55)) as pilot:
            app = pilot.app
            await pilot.pause()
            app.query_one("#privacy_release_mode", Select).value = (
                PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE.value
            )
            await pilot.pause()
            df = build_safe_coverage_getnet_shaped_df()
            request = _msc_share_request(tmp_path, df, output_name="tui_exec.xlsx")
            log = MagicMock()
            monkeypatch.setattr(
                app,
                "call_from_thread",
                lambda fn, *args, **kwargs: fn(*args, **kwargs),
            )
            artifacts = app._execute_run_for_tui(
                request,
                logging.getLogger("test_tui_msc_executor"),
                log,
            )
            assert artifacts.privacy_sink_authorized is True
            assert artifacts.coverage_certificate is not None
            assert artifacts.safe_coverage_result is not None
            assert (
                artifacts.safe_coverage_result.verifier_result
                == VERIFIER_RESULT_PASSED
            )
            assert len(artifacts.safe_coverage_result.candidate_universe) == 9
            assert len(artifacts.safe_coverage_result.release_set) == 4

    asyncio.run(scenario())


def test_tui_safe_result_summary(tmp_path: Path) -> None:
    cert_path = str(tmp_path / "out_coverage_certificate.json")
    certificate = _client_certificate(cert_path=cert_path)
    artifacts = AnalysisArtifacts(
        metadata={"compliance_summary": {}},
        compliance_summary={
            "compliance_verdict": "fully_compliant",
            "posture": "best_effort",
            "acknowledgement_state": "not_required",
        },
        report_paths=[str(tmp_path / "out.xlsx")],
        coverage_certificate=certificate,
        coverage_certificate_output=cert_path,
        privacy_output_decision=PrivacyOutputDecision(
            privacy_publication_authorized=True,
            hard_privacy_block=False,
        ),
        privacy_sink_authorized=True,
        privacy_log_authorized=True,
    )
    app = BenchmarkApp()
    app.call_from_thread = (  # type: ignore[method-assign]
        lambda fn, *args, **kwargs: fn(*args, **kwargs)
    )
    app._begin_run_ui = MagicMock()  # type: ignore[method-assign]
    app._end_run_ui = MagicMock()  # type: ignore[method-assign]
    app.notify = MagicMock()  # type: ignore[method-assign]
    app._execute_run_for_tui = MagicMock(return_value=artifacts)  # type: ignore[method-assign]
    log = MagicMock()

    app._execute_confirmed_analysis(
        AnalysisRunRequest(
            mode="share",
            metric="transaction_amount",
            privacy_release_mode=PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE,
            privacy_rule_strategy=PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE,
        ),
        None,
        log,
    )

    assert app._end_run_ui.call_args.args[0] == "success"
    summary = app._end_run_ui.call_args.args[1]
    assert "Verified safe coverage" in summary
    assert "4/9 released" in summary
    assert "5 suppressed" in summary
    assert cert_path in summary
    assert "Independent privacy verification passed" in summary
    log_text = "\n".join(
        str(call.args[0]) for call in log.write.call_args_list if call.args
    )
    assert "Privacy release mode: Verified safe coverage" in log_text
    assert "Candidate units: 9" in log_text
    assert "Released units: 4" in log_text
    assert "Suppressed units: 5" in log_text
    assert f"Coverage Certificate: {cert_path}" in log_text
    assert "Coverage is not a maximum claim." in log_text
    assert "visible_unit_0" not in summary
    assert "visible_unit_0" not in log_text


def test_tui_empty_release_set_denial(tmp_path: Path) -> None:
    artifacts = AnalysisArtifacts(
        metadata={},
        compliance_summary={
            "compliance_verdict": "blocked",
            "posture": "best_effort",
            "acknowledgement_state": "not_required",
        },
        report_paths=[],
        audit_log_output=str(tmp_path / "denied_NON_PUBLISHABLE_control3_audit.json"),
        privacy_output_decision=PrivacyOutputDecision(
            privacy_publication_authorized=False,
            hard_privacy_block=True,
            withholding_reason=CONTROL3_SAFE_COVERAGE_EMPTY,
        ),
        privacy_sink_authorized=False,
        coverage_certificate=None,
    )
    app = BenchmarkApp()
    app.call_from_thread = (  # type: ignore[method-assign]
        lambda fn, *args, **kwargs: fn(*args, **kwargs)
    )
    app._begin_run_ui = MagicMock()  # type: ignore[method-assign]
    app._end_run_ui = MagicMock()  # type: ignore[method-assign]
    app.notify = MagicMock()  # type: ignore[method-assign]
    app._execute_run_for_tui = MagicMock(return_value=artifacts)  # type: ignore[method-assign]
    log = MagicMock()

    app._execute_confirmed_analysis(
        AnalysisRunRequest(
            mode="share",
            metric="transaction_amount",
            privacy_release_mode=PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE,
            privacy_rule_strategy=PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE,
        ),
        None,
        log,
    )

    assert app._end_run_ui.call_args.args[0] == "blocked"
    summary = app._end_run_ui.call_args.args[1]
    assert "Verified safe coverage" in summary
    assert "Publication withheld" in summary
    assert CONTROL3_SAFE_COVERAGE_EMPTY in summary
    assert any(
        "Control 3 privacy denial" in str(call.args[0])
        for call in log.write.call_args_list
        if call.args
    )
    notify_messages = [
        str(call.args[0]) for call in app.notify.call_args_list if call.args
    ]
    assert any("publication withheld" in msg.lower() for msg in notify_messages)


def test_tui_no_suppressed_marker_in_widgets_or_notices(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        async with BenchmarkApp().run_test(size=(140, 55)) as pilot:
            app = pilot.app
            await pilot.pause()
            notices: list[str] = []
            original_notify = app.notify

            def capture_notify(message, *args, **kwargs):
                notices.append(str(message))
                return original_notify(message, *args, **kwargs)

            app.notify = capture_notify  # type: ignore[method-assign]
            monkeypatch.setattr(
                app,
                "call_from_thread",
                lambda fn, *args, **kwargs: fn(*args, **kwargs),
            )
            df = _seed_suppressed_marker(build_safe_coverage_getnet_shaped_df())
            request = _msc_share_request(
                tmp_path, df, output_name="tui_marker.xlsx"
            )
            log = MagicMock()
            artifacts = app._execute_run_for_tui(
                request,
                logging.getLogger("test_tui_msc_marker"),
                log,
            )
            assert artifacts.privacy_sink_authorized is True
            app._execute_run_for_tui = MagicMock(  # type: ignore[method-assign]
                return_value=artifacts
            )
            app._begin_run_ui = MagicMock()  # type: ignore[method-assign]
            app._end_run_ui = MagicMock()  # type: ignore[method-assign]
            confirmed_log = MagicMock()
            app._execute_confirmed_analysis(request, df, confirmed_log)

            summary = app._end_run_ui.call_args.args[1]
            log_text = "\n".join(
                str(call.args[0])
                for mock_log in (log, confirmed_log)
                for call in mock_log.write.call_args_list
                if call.args
            )
            assert SUPPRESSED_MARKER not in summary
            assert SUPPRESSED_MARKER not in log_text
            assert all(SUPPRESSED_MARKER not in msg for msg in notices)
            assert "Verified safe coverage" in summary

    asyncio.run(scenario())
