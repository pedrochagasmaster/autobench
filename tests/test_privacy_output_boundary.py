"""End-to-end tests for the non-overridable Control 3 disk-output gate."""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
import pytest

import benchmark
import core.analysis_run as analysis_run
from core.analysis_run import RunBlocked, execute_share_run
from core.contracts import (
    AnalysisRunRequest,
    PrivacyFailureReason,
    PrivacyEvaluationStatus,
    PrivacyOutputDecision,
    PrivacyRuleStrategy,
    PrivacySweepStatus,
)
from core.dimensional_analyzer import DimensionalAnalyzer
from core.privacy_output_policy import (
    _attest_privacy_output,
    build_non_publishable_privacy_audit,
    decide_privacy_output,
)
from core.telemetry.events import EventValidationError, build_record, decode_record
from utils.logger import setup_deferred_logging
from utils.logger import PrivacyRunLogGate


def _single_category_df(shares: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"issuer_name": f"P{index}", "segment": "all", "amount": share}
            for index, share in enumerate(shares, start=1)
        ]
    )


def _assert_no_sensitive_output(tmp_path: Path, artifacts: Any) -> None:
    assert artifacts.analysis_output_file is None
    assert artifacts.publication_output is None
    assert artifacts.csv_output is None
    assert artifacts.json_output is None
    assert artifacts.audit_package_output is None
    assert artifacts.report_paths == []
    assert not list(tmp_path.glob("*.xlsx"))
    assert not list(tmp_path.glob("*_balanced.csv"))
    assert not list(tmp_path.glob("*.zip"))


@pytest.mark.parametrize("posture", ["strict", "best_effort"])
@pytest.mark.parametrize("output_format", ["analysis", "publication", "both"])
def test_sweep_numeric_denial_withholds_every_sensitive_output_for_all_postures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    posture: str,
    output_format: str,
) -> None:
    export_called = False

    def fail_fit(*_args: Any, **_kwargs: Any) -> None:
        raise ValueError("forced optimizer failure")

    def capture_export(**_kwargs: Any) -> None:
        nonlocal export_called
        export_called = True

    monkeypatch.setattr(DimensionalAnalyzer, "fit_privacy_weights", fail_fit)
    monkeypatch.setattr(
        analysis_run.SHARE_MODE_SPEC,
        "export_balanced_csv_fn",
        capture_export,
    )
    output = tmp_path / f"{posture}_{output_format}.xlsx"
    request = AnalysisRunRequest(
        df=_single_category_df([25, 25, 20, 15, 15]),
        csv="",
        metric="amount",
        dimensions=["segment"],
        output=str(output),
        output_format=output_format,
        report_format="json",
        audit_package=True,
        export_balanced_csv=True,
        compliance_posture=posture,
        acknowledge_accuracy_first=posture == "accuracy_first",
        validate_input=False,
        privacy_rule_strategy=PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE,
    )

    artifacts = execute_share_run(request, logging.getLogger("test"))

    assert artifacts.analysis_output_file is None
    assert artifacts.publication_output is None
    assert artifacts.csv_output is None
    assert artifacts.json_output is None
    assert artifacts.audit_package_output is None
    assert artifacts.report_paths == []
    assert export_called is False
    assert artifacts.privacy_output_decision is not None
    assert artifacts.privacy_output_decision.hard_privacy_block
    assert artifacts.privacy_output_decision.withholding_reason == (
        "control3_numeric_policy_blocked"
    )
    assert artifacts.audit_log_output is not None
    assert list(tmp_path.glob("*.json")) == [Path(artifacts.audit_log_output)]
    assert artifacts.results == {}
    assert artifacts.weights_df is None
    assert artifacts.privacy_validation_df is None
    assert artifacts.analyzer is None
    assert artifacts.report_model is None


def test_acknowledged_accuracy_first_numeric_denial_writes_marked_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The consented accuracy_first exception writes only a marked workbook."""
    export_called = False

    def capture_export(**_kwargs: Any) -> None:
        nonlocal export_called
        export_called = True

    monkeypatch.setattr(
        DimensionalAnalyzer,
        "fit_privacy_weights",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("forced optimizer failure")
        ),
    )
    monkeypatch.setattr(
        analysis_run.SHARE_MODE_SPEC,
        "export_balanced_csv_fn",
        capture_export,
    )
    output = tmp_path / "accuracy_first_diag.xlsx"
    request = AnalysisRunRequest(
        df=_single_category_df([25, 25, 20, 15, 15]),
        csv="",
        metric="amount",
        dimensions=["segment"],
        output=str(output),
        output_format="both",
        audit_package=True,
        export_balanced_csv=True,
        compliance_posture="accuracy_first",
        acknowledge_accuracy_first=True,
        validate_input=False,
        privacy_rule_strategy=PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE,
    )

    artifacts = execute_share_run(request, logging.getLogger("test"))

    # The requested output path is never created; the diagnostic workbook
    # carries the non-publishable prefix and metadata marking.
    assert not output.exists()
    assert artifacts.analysis_output_file is not None
    diagnostic_path = Path(artifacts.analysis_output_file)
    assert diagnostic_path.exists()
    assert diagnostic_path.name == (
        "autobench_NON_PUBLISHABLE_accuracy_first_diag.xlsx"
    )
    assert artifacts.metadata["non_publishable_diagnostic"] is True
    # Every other sink stays withheld.
    assert artifacts.publication_output is None
    assert artifacts.csv_output is None
    assert artifacts.json_output is None
    assert artifacts.audit_package_output is None
    assert artifacts.report_paths == []
    assert export_called is False
    assert not list(tmp_path.glob("*_balanced.csv"))
    assert not list(tmp_path.glob("*.zip"))
    assert artifacts.privacy_sink_authorized is not True
    assert artifacts.privacy_output_decision is not None
    assert artifacts.privacy_output_decision.withholding_reason == (
        "control3_numeric_policy_blocked"
    )
    assert artifacts.audit_log_output is not None


def test_unacknowledged_accuracy_first_never_writes_diagnostic(
    tmp_path: Path,
) -> None:
    with pytest.raises(RunBlocked):
        execute_share_run(
            AnalysisRunRequest(
                df=_single_category_df([25, 25, 20, 15, 15]),
                csv="",
                metric="amount",
                dimensions=["segment"],
                output=str(tmp_path / "no_ack.xlsx"),
                compliance_posture="accuracy_first",
                acknowledge_accuracy_first=False,
                validate_input=False,
            ),
            logging.getLogger("test"),
        )
    assert not list(tmp_path.glob("*.xlsx"))


def test_non_publishable_audit_is_allow_listed_and_contains_no_peer_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        DimensionalAnalyzer,
        "fit_privacy_weights",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("P1 secret optimizer detail")
        ),
    )
    output = tmp_path / "SECRET_CLIENT_METRIC_denied.xlsx"
    artifacts = execute_share_run(
        AnalysisRunRequest(
            df=_single_category_df([25, 25, 20, 15, 15]),
            csv="",
            metric="amount",
            dimensions=["segment"],
            output=str(output),
            compliance_posture="best_effort",
            validate_input=False,
            privacy_rule_strategy=PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE,
        ),
        logging.getLogger("test"),
    )

    assert artifacts.audit_log_output is not None
    assert "secret_client_metric" not in Path(
        artifacts.audit_log_output
    ).name.casefold()
    payload = json.loads(
        Path(artifacts.audit_log_output).read_text(encoding="utf-8")
    )
    assert set(payload) == {
        "artifact_type",
        "publishable",
        "run_status",
        "withholding_reason",
        "strategy",
        "policy_provenance",
        "applicable_rules",
        "feasible_candidate_rules",
        "authorizing_rules",
        "candidate_attempt_evaluations",
        "emitted_output_evaluations",
        "mandatory_overlay_evaluations",
    }
    serialized = json.dumps(payload).casefold()
    for forbidden in (
        "p1",
        "weight",
        "maximum_share",
        "balanced_share",
        "rate_value",
        "raw_row",
        "category_result",
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    "strategy",
    [
        PrivacyRuleStrategy.SELECT_BY_PEER_COUNT,
        PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE,
    ],
)
@pytest.mark.parametrize(
    "posture",
    ["strict", "best_effort", "accuracy_first"],
)
def test_citi_denial_withholds_outputs_in_default_and_sweep_strategies(
    tmp_path: Path,
    strategy: PrivacyRuleStrategy,
    posture: str,
) -> None:
    df = _single_category_df([20, 20, 10, 10, 10, 6, 6, 6, 6, 6])
    df["secondary"] = [30, 20, 10, 10, 10, 5, 5, 4, 3, 3]
    artifacts = execute_share_run(
        AnalysisRunRequest(
            df=df,
            csv="",
            metric="amount",
            secondary_metrics=["secondary"],
            dimensions=["segment"],
            output=str(tmp_path / f"citi_{strategy.value}_{posture}.xlsx"),
            output_format="both",
            export_balanced_csv=True,
            compliance_posture=posture,
            acknowledge_accuracy_first=posture == "accuracy_first",
            validate_input=False,
            privacy_rule_strategy=strategy,
            citibank_entity_name="P1",
            citi_competitor_receives_output=True,
        ),
        logging.getLogger("test"),
    )

    assert artifacts.analysis_output_file is None
    assert artifacts.publication_output is None
    assert artifacts.csv_output is None
    assert artifacts.json_output is None
    assert artifacts.audit_package_output is None
    assert artifacts.report_paths == []
    assert artifacts.privacy_output_decision is not None
    assert artifacts.privacy_output_decision.withholding_reason == (
        "control3_mandatory_overlay_blocked"
    )


@pytest.mark.parametrize("posture", ["strict", "best_effort"])
def test_cli_privacy_denial_returns_nonzero_and_reports_withholding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    posture: str,
) -> None:
    monkeypatch.setattr(
        DimensionalAnalyzer,
        "fit_privacy_weights",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("forced optimizer failure")
        ),
    )
    csv_path = tmp_path / "input.csv"
    _single_category_df([25, 25, 20, 15, 15]).to_csv(csv_path, index=False)
    output = tmp_path / f"cli_denied_{posture}.xlsx"
    args = benchmark.create_parser().parse_args(
        [
            "share",
            "--csv",
            str(csv_path),
            "--metric",
            "amount",
            "--dimensions",
            "segment",
            "--compliance-posture",
            posture,
            "--output",
            str(output),
            "--privacy-rule-sweep",
        ]
    )

    exit_code = benchmark.run_share_analysis(args, logging.getLogger("test"))

    assert exit_code == benchmark.EXIT_STRICT_NON_COMPLIANT
    assert not output.exists()
    stdout = capsys.readouterr().out
    assert "PUBLICATION WITHHELD: control3_numeric_policy_blocked" in stdout
    assert "CONTROL 3 PRIVACY BLOCK" in stdout
    assert "ANALYSIS COMPLETE" not in stdout
    assert "Report:" not in stdout


def test_cli_acknowledged_accuracy_first_diagnostic_completes_with_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        DimensionalAnalyzer,
        "fit_privacy_weights",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("forced optimizer failure")
        ),
    )
    csv_path = tmp_path / "input.csv"
    _single_category_df([25, 25, 20, 15, 15]).to_csv(csv_path, index=False)
    output = tmp_path / "cli_accuracy_first.xlsx"
    args = benchmark.create_parser().parse_args(
        [
            "share",
            "--csv",
            str(csv_path),
            "--metric",
            "amount",
            "--dimensions",
            "segment",
            "--compliance-posture",
            "accuracy_first",
            "--acknowledge-accuracy-first",
            "--output",
            str(output),
            "--privacy-rule-sweep",
        ]
    )

    exit_code = benchmark.run_share_analysis(args, logging.getLogger("test"))

    assert exit_code == benchmark.EXIT_OK
    assert not output.exists()
    diagnostic = tmp_path / "autobench_NON_PUBLISHABLE_cli_accuracy_first.xlsx"
    assert diagnostic.exists()
    stdout = capsys.readouterr().out
    assert "NON-PUBLISHABLE DIAGNOSTIC" in stdout
    assert "must not be published" in stdout
    assert str(diagnostic) in stdout
    assert "ANALYSIS BLOCKED" not in stdout


def test_cli_authorized_run_flushes_deferred_log(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "gate_demo.csv"
    output = tmp_path / "authorized.xlsx"
    log_path = tmp_path / "benchmark_log_authorized.txt"
    logger = setup_deferred_logging(
        "INFO",
        str(log_path),
        console_output=False,
    )
    args = benchmark.create_parser().parse_args(
        [
            "share",
            "--csv",
            str(fixture),
            "--entity",
            "Target",
            "--metric",
            "txn_cnt",
            "--dimensions",
            "card_type",
            "channel",
            "--time-col",
            "year_month",
            "--preset",
            "balanced_default",
            "--compliance-posture",
            "strict",
            "--output",
            str(output),
        ]
    )

    exit_code = benchmark.run_share_analysis(args, logger)

    assert exit_code == benchmark.EXIT_OK
    assert output.exists()
    assert log_path.exists()
    assert "Starting share-based dimensional analysis" in log_path.read_text(
        encoding="utf-8"
    )


def test_cli_denied_run_quarantines_deferred_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        DimensionalAnalyzer,
        "fit_privacy_weights",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("P1 must never reach the log")
        ),
    )
    csv_path = tmp_path / "denied_input.csv"
    _single_category_df([25, 25, 20, 15, 15]).to_csv(csv_path, index=False)
    output = tmp_path / "denied.xlsx"
    log_path = tmp_path / "benchmark_log_denied.txt"
    logger = setup_deferred_logging(
        "INFO",
        str(log_path),
        console_output=False,
    )
    args = benchmark.create_parser().parse_args(
        [
            "share",
            "--csv",
            str(csv_path),
            "--metric",
            "amount",
            "--dimensions",
            "segment",
            "--compliance-posture",
            "best_effort",
            "--output",
            str(output),
            "--privacy-rule-sweep",
        ]
    )

    exit_code = benchmark.run_share_analysis(args, logger)

    assert exit_code == benchmark.EXIT_STRICT_NON_COMPLIANT
    assert not output.exists()
    # The intended log path must never be created, but the buffered
    # diagnostics are preserved in a clearly marked quarantine file.
    assert not log_path.exists()
    quarantined = list(
        tmp_path.glob("autobench_NON_PUBLISHABLE_run_log_*.log")
    )
    assert len(quarantined) == 1
    quarantine_text = quarantined[0].read_text(encoding="utf-8")
    assert "NON-PUBLISHABLE" in quarantine_text
    assert "Do not share" in quarantine_text
    assert "Starting share-based dimensional analysis" in quarantine_text


def test_denial_does_not_overwrite_or_report_preexisting_output_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        DimensionalAnalyzer,
        "fit_privacy_weights",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("forced optimizer failure")
        ),
    )
    output = tmp_path / "preexisting.xlsx"
    preexisting_paths = [
        output,
        tmp_path / "preexisting_publication.xlsx",
        tmp_path / "preexisting.json",
        tmp_path / "preexisting_balanced.csv",
        tmp_path / "preexisting_audit_package.zip",
    ]
    for path in preexisting_paths:
        path.write_bytes(b"PREEXISTING_USER_FILE")

    artifacts = execute_share_run(
        AnalysisRunRequest(
            df=_single_category_df([25, 25, 20, 15, 15]),
            csv="",
            metric="amount",
            dimensions=["segment"],
            output=str(output),
            output_format="both",
            report_format="json",
            audit_package=True,
            export_balanced_csv=True,
            compliance_posture="best_effort",
            validate_input=False,
            privacy_rule_strategy=PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE,
        ),
        logging.getLogger("test"),
    )

    assert artifacts.analysis_output_file is None
    assert artifacts.publication_output is None
    assert artifacts.csv_output is None
    assert artifacts.json_output is None
    assert artifacts.audit_package_output is None
    assert artifacts.report_paths == []
    for path in preexisting_paths:
        assert path.read_bytes() == b"PREEXISTING_USER_FILE"


def test_persistent_telemetry_contract_rejects_sensitive_run_properties() -> None:
    safe = build_record(
        "action_attempted",
        {"action": "share_analysis"},
        user="tester",
        session_id=uuid4(),
        app_version="test",
    )
    assert dict(decode_record(safe).props) == {"action": "share_analysis"}

    for sensitive_key in (
        "entity",
        "csv",
        "peer",
        "category",
        "share",
        "weight",
        "rate",
        "benchmark_value",
    ):
        with pytest.raises(EventValidationError):
            build_record(
                "action_attempted",
                {
                    "action": "share_analysis",
                    sensitive_key: "sensitive",
                },
                user="tester",
                session_id=uuid4(),
                app_version="test",
            )


def test_python_api_denial_discards_records_for_existing_caller_file_handler(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        DimensionalAnalyzer,
        "fit_privacy_weights",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("SECRET_PEER_SENTINEL")
        ),
    )
    log_path = tmp_path / "caller_owned.log"
    logger = logging.getLogger("test.python_api_privacy_gate")
    logger.handlers.clear()
    logger.propagate = False
    handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    logger.addHandler(handler)
    try:
        artifacts = execute_share_run(
            AnalysisRunRequest(
                df=_single_category_df([25, 25, 20, 15, 15]),
                csv="",
                metric="amount",
                dimensions=["segment"],
                output=str(tmp_path / "python_denied.xlsx"),
                compliance_posture="best_effort",
                validate_input=False,
                privacy_rule_strategy=(
                    PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE
                ),
            ),
            logger,
        )
    finally:
        handler.close()
        logger.removeHandler(handler)
        logger.propagate = True

    assert artifacts.privacy_output_decision is not None
    assert artifacts.privacy_output_decision.hard_privacy_block
    assert "secret_peer_sentinel" not in log_path.read_text(
        encoding="utf-8"
    ).casefold()
    assert handler.filters == []


def test_privacy_log_gate_does_not_suppress_other_threads_and_detaches_filters(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "thread_gate.log"
    logger = logging.getLogger("test.privacy_log_gate_threads")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    logger.addHandler(handler)
    gate = PrivacyRunLogGate()
    gate.start()
    try:
        logger.info("RUN_THREAD_SECRET")
        worker = threading.Thread(
            target=lambda: logger.info("UNRELATED_THREAD_RECORD")
        )
        worker.start()
        worker.join()
        gate.finish(privacy_authorized=False)
    finally:
        handler.close()
        logger.removeHandler(handler)
        logger.propagate = True

    text = log_path.read_text(encoding="utf-8")
    assert "UNRELATED_THREAD_RECORD" in text
    assert "RUN_THREAD_SECRET" not in text
    assert handler.filters == []


def test_privacy_log_gate_rejects_nested_same_thread_runs_without_leaking(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "nested_gate.log"
    logger = logging.getLogger("test.privacy_log_gate_nested")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    logger.addHandler(handler)
    outer = PrivacyRunLogGate()
    outer.start()
    try:
        logger.info("OUTER_AUTHORIZED_RECORD")
        inner = PrivacyRunLogGate()
        with pytest.raises(RuntimeError, match="Nested privacy-governed"):
            inner.start()
        outer.finish(privacy_authorized=True)
    finally:
        outer.finish(privacy_authorized=False)
        handler.close()
        logger.removeHandler(handler)
        logger.propagate = True

    text = log_path.read_text(encoding="utf-8")
    assert "OUTER_AUTHORIZED_RECORD" in text
    assert handler.filters == []


def test_privacy_log_gate_captures_handler_installed_after_start_on_denial(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "late_handler.log"
    logger = logging.getLogger("test.privacy_log_gate_late_handler")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.INFO)
    gate = PrivacyRunLogGate()
    gate.start()
    handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    logger.addHandler(handler)
    try:
        logger.info("SENTINEL_PEER_SHARE_99_PERCENT")
        gate.finish(privacy_authorized=False)
    finally:
        gate.finish(privacy_authorized=False)
        handler.close()
        logger.removeHandler(handler)
        logger.propagate = True

    assert log_path.read_text(encoding="utf-8") == ""
    assert logging.Logger.callHandlers.__name__ == "callHandlers"


def test_privacy_log_gate_uses_actual_dispatch_thread_not_record_metadata(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "forged_record_thread.log"
    logger = logging.getLogger("test.privacy_log_gate_record_thread")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    logger.addHandler(handler)
    gate = PrivacyRunLogGate()
    gate.start()
    try:
        record = logger.makeRecord(
            logger.name,
            logging.INFO,
            __file__,
            1,
            "FORGED_THREAD_SECRET",
            (),
            None,
        )
        record.thread = threading.get_ident() + 1000
        logger.handle(record)
        gate.finish(privacy_authorized=False)
    finally:
        gate.finish(privacy_authorized=False)
        handler.close()
        logger.removeHandler(handler)
        logger.propagate = True

    assert log_path.read_text(encoding="utf-8") == ""


def test_privacy_log_gate_preserves_current_dispatch_wrapper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log_path = tmp_path / "wrapped_dispatch.log"
    logger = logging.getLogger("test.privacy_log_gate_wrapper")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    logger.addHandler(handler)
    original_dispatch = logging.Logger.callHandlers
    dispatched: list[str] = []

    def wrapper(
        active_logger: logging.Logger,
        record: logging.LogRecord,
    ) -> None:
        dispatched.append(record.getMessage())
        original_dispatch(active_logger, record)

    monkeypatch.setattr(logging.Logger, "callHandlers", wrapper)
    gate = PrivacyRunLogGate()
    gate.start()
    try:
        logger.info("AUTHORIZED_WRAPPED_RECORD")
        gate.finish(privacy_authorized=True)
    finally:
        gate.finish(privacy_authorized=False)
        handler.close()
        logger.removeHandler(handler)
        logger.propagate = True

    assert logging.Logger.callHandlers is wrapper
    assert dispatched == ["AUTHORIZED_WRAPPED_RECORD"]
    assert "AUTHORIZED_WRAPPED_RECORD" in log_path.read_text(
        encoding="utf-8"
    )


def test_base_exception_always_detaches_privacy_log_filters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log_path = tmp_path / "base_exception.log"
    logger = logging.getLogger("test.privacy_log_gate_base_exception")
    logger.handlers.clear()
    logger.propagate = False
    handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    logger.addHandler(handler)
    monkeypatch.setattr(
        analysis_run,
        "_execute_run_impl",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            KeyboardInterrupt()
        ),
    )
    try:
        with pytest.raises(KeyboardInterrupt):
            execute_share_run(
                AnalysisRunRequest(
                    df=_single_category_df([20, 20, 20, 20, 20]),
                    csv="",
                    metric="amount",
                    dimensions=["segment"],
                    output=str(tmp_path / "never_written.xlsx"),
                ),
                logger,
            )
    finally:
        handler.close()
        logger.removeHandler(handler)
        logger.propagate = True

    assert handler.filters == []
    assert log_path.read_text(encoding="utf-8") == ""


def test_hard_privacy_denial_emits_refused_not_completed_telemetry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, tuple[Any, ...]]] = []
    monkeypatch.setattr(
        analysis_run,
        "action_attempted",
        lambda *args: events.append(("attempted", args)),
    )
    monkeypatch.setattr(
        analysis_run,
        "action_refused",
        lambda *args: events.append(("refused", args)),
    )
    monkeypatch.setattr(
        analysis_run,
        "action_completed",
        lambda *args: events.append(("completed", args)),
    )
    monkeypatch.setattr(
        DimensionalAnalyzer,
        "fit_privacy_weights",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("forced optimizer failure")
        ),
    )

    execute_share_run(
        AnalysisRunRequest(
            df=_single_category_df([25, 25, 20, 15, 15]),
            csv="",
            metric="amount",
            dimensions=["segment"],
            output=str(tmp_path / "telemetry_denied.xlsx"),
            compliance_posture="best_effort",
            validate_input=False,
            privacy_rule_strategy=PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE,
        ),
        logging.getLogger("test"),
    )

    assert events[0] == ("attempted", ("share_analysis",))
    assert events[-1] == (
        "refused",
        ("share_analysis", "compliance_policy"),
    )
    assert not any(name == "completed" for name, _args in events)


def test_sole_4_35_publication_completes_telemetry_while_logs_stay_withheld(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, tuple[Any, ...]]] = []
    monkeypatch.setattr(
        analysis_run,
        "action_attempted",
        lambda *args: events.append(("attempted", args)),
    )
    monkeypatch.setattr(
        analysis_run,
        "action_refused",
        lambda *args: events.append(("refused", args)),
    )
    monkeypatch.setattr(
        analysis_run,
        "action_completed",
        lambda *args: events.append(("completed", args)),
    )

    artifacts = execute_share_run(
        AnalysisRunRequest(
            df=_single_category_df([34, 22, 22, 22]),
            csv="",
            metric="amount",
            dimensions=["segment"],
            output=str(tmp_path / "merchant_publication.xlsx"),
            output_format="publication",
            compliance_posture="best_effort",
            validate_input=False,
            privacy_rule_strategy=PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE,
            is_anonymized_aggregated_merchant_spend=True,
        ),
        logging.getLogger("test"),
    )

    assert artifacts.privacy_sink_authorized is True
    assert artifacts.privacy_log_authorized is False
    assert events == [
        ("attempted", ("share_analysis",)),
        ("completed", ("share_analysis",)),
    ]


@pytest.mark.parametrize("forged_attestation", [None, object()])
def test_attestation_refusal_blocks_every_sink_and_normalizes_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    forged_attestation: object,
) -> None:
    export_called = False

    def capture_export(**_kwargs: Any) -> None:
        nonlocal export_called
        export_called = True

    monkeypatch.setattr(
        analysis_run,
        "_attest_privacy_output",
        lambda *_args: forged_attestation,
    )
    monkeypatch.setattr(
        analysis_run.SHARE_MODE_SPEC,
        "export_balanced_csv_fn",
        capture_export,
    )
    output = tmp_path / "attestation_refused.xlsx"
    artifacts = execute_share_run(
        AnalysisRunRequest(
            df=_single_category_df([20, 20, 20, 20, 20]),
            csv="",
            metric="amount",
            dimensions=["segment"],
            output=str(output),
            output_format="both",
            report_format="json",
            export_balanced_csv=True,
            audit_package=True,
            compliance_posture="best_effort",
            validate_input=False,
        ),
        logging.getLogger("test"),
    )

    assert artifacts.privacy_sink_authorized is False
    assert artifacts.privacy_log_authorized is False
    assert export_called is False
    _assert_no_sensitive_output(tmp_path, artifacts)
    assert artifacts.audit_log_output is not None
    assert list(tmp_path.glob("*.json")) == [
        Path(artifacts.audit_log_output)
    ]


def test_cli_attestation_refusal_discards_log_reports_withholding_and_refuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    events: list[str] = []
    monkeypatch.setattr(
        analysis_run,
        "_attest_privacy_output",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        analysis_run,
        "action_refused",
        lambda *_args: events.append("refused"),
    )
    monkeypatch.setattr(
        analysis_run,
        "action_completed",
        lambda *_args: events.append("completed"),
    )
    csv_path = tmp_path / "authorized_input.csv"
    _single_category_df([20, 20, 20, 20, 20]).to_csv(
        csv_path,
        index=False,
    )
    output = tmp_path / "attestation_cli.xlsx"
    log_path = tmp_path / "attestation_cli.log"
    logger = setup_deferred_logging(
        "INFO",
        str(log_path),
        console_output=False,
    )
    args = benchmark.create_parser().parse_args(
        [
            "share",
            "--csv",
            str(csv_path),
            "--metric",
            "amount",
            "--dimensions",
            "segment",
            "--output",
            str(output),
            "--compliance-posture",
            "best_effort",
        ]
    )

    exit_code = benchmark.run_share_analysis(args, logger)

    assert exit_code == benchmark.EXIT_STRICT_NON_COMPLIANT
    assert not output.exists()
    assert not log_path.exists()
    assert events == ["refused"]
    stdout = capsys.readouterr().out
    assert "PUBLICATION WITHHELD" in stdout
    assert "ANALYSIS COMPLETE" not in stdout


def test_safe_denial_audit_canonicalizes_every_untrusted_string(
    tmp_path: Path,
) -> None:
    artifacts = execute_share_run(
        AnalysisRunRequest(
            df=_single_category_df([80, 5, 5, 5, 5]),
            csv="",
            metric="amount",
            dimensions=["segment"],
            output=str(tmp_path / "unused.xlsx"),
            compliance_posture="best_effort",
            validate_input=False,
        ),
        logging.getLogger("test"),
    )
    result = artifacts.privacy_rule_strategy_result
    assert result is not None
    sentinel = "SENTINEL_PEER_PATH_SHARE_99"
    object.__setattr__(result, "strategy", sentinel)
    object.__setattr__(result, "policy_version", sentinel)
    object.__setattr__(result, "policy_source", sentinel)
    object.__setattr__(result, "rule_set_digest", sentinel)
    object.__setattr__(result, "feasible_candidate_rules", (sentinel,))
    object.__setattr__(result, "authorizing_rules", (sentinel,))
    evaluation = result.emitted_output_evaluations[0]
    object.__setattr__(evaluation, "rule_name", sentinel)
    object.__setattr__(evaluation, "status", sentinel)
    object.__setattr__(
        evaluation,
        "failure_reasons",
        (PrivacyFailureReason(sentinel, sentinel, sentinel),),
    )
    overlay = result.mandatory_overlay_evaluations[0]
    object.__setattr__(overlay, "overlay_name", sentinel)
    object.__setattr__(overlay, "status", sentinel)
    object.__setattr__(
        overlay,
        "failure_reasons",
        (PrivacyFailureReason(sentinel, sentinel, sentinel),),
    )
    payload = build_non_publishable_privacy_audit(
        result,
        PrivacyOutputDecision(
            privacy_publication_authorized=False,
            hard_privacy_block=True,
            withholding_reason=sentinel,
        ),
    )

    serialized = json.dumps(payload)
    assert sentinel not in serialized
    assert payload["withholding_reason"] == (
        "control3_invalid_privacy_evidence"
    )


def test_strategy_result_rejects_contradictory_exact_evidence(
    tmp_path: Path,
) -> None:
    artifacts = execute_share_run(
        AnalysisRunRequest(
            df=_single_category_df([20, 20, 20, 20, 20]),
            csv="",
            metric="amount",
            dimensions=["segment"],
            output=str(tmp_path / "authorized.xlsx"),
            compliance_posture="best_effort",
            validate_input=False,
        ),
        logging.getLogger("test"),
    )
    result = artifacts.privacy_rule_strategy_result
    assert result is not None
    emitted = result.emitted_output_evaluations[0]
    overlay = result.mandatory_overlay_evaluations[0]

    with pytest.raises(ValueError, match="contradictory"):
        replace(
            result,
            status=PrivacySweepStatus.INVALID_EVIDENCE,
            numeric_rules_passed=False,
        )
    with pytest.raises(ValueError, match="contradictory"):
        replace(
            result,
            emitted_output_evaluations=(
                replace(
                    emitted,
                    status=PrivacyEvaluationStatus.FAILED,
                    failure_reasons=(
                        PrivacyFailureReason(
                            "emitted_output_rule_failed",
                            "failed",
                        ),
                    ),
                ),
            ),
        )
    with pytest.raises(ValueError, match="contradictory"):
        replace(
            result,
            mandatory_overlay_evaluations=(
                replace(
                    overlay,
                    status=PrivacyEvaluationStatus.FAILED,
                    failure_reasons=(
                        PrivacyFailureReason(
                            "citibank_concentration_exceeded",
                            "failed",
                        ),
                    ),
                ),
            ),
        )
    with pytest.raises(ValueError, match="contradictory"):
        replace(
            result,
            candidate_attempt_evaluations=(
                *result.candidate_attempt_evaluations,
                result.candidate_attempt_evaluations[0],
            ),
        )


def test_attestation_rejects_forged_display_rule_and_overlay_cap(
    tmp_path: Path,
) -> None:
    artifacts = execute_share_run(
        AnalysisRunRequest(
            df=_single_category_df([20, 20, 20, 20, 20]),
            csv="",
            metric="amount",
            dimensions=["segment"],
            output=str(tmp_path / "sweep_authorized.xlsx"),
            compliance_posture="best_effort",
            validate_input=False,
            privacy_rule_strategy=(
                PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE
            ),
        ),
        logging.getLogger("test"),
    )
    result = artifacts.privacy_rule_strategy_result
    assert result is not None

    forged_display = replace(result, display_rule="insufficient")
    assert _attest_privacy_output(
        forged_display,
        decide_privacy_output(forged_display),
    ) is None

    overlay = result.mandatory_overlay_evaluations[0]
    forged_overlay = replace(
        result,
        mandatory_overlay_evaluations=(
            replace(overlay, maximum_share_percentage=99.0),
        ),
    )
    assert _attest_privacy_output(
        forged_overlay,
        decide_privacy_output(forged_overlay),
    ) is None
