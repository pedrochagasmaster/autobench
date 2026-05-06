from scripts.run_cli_sweep_cases import (
    build_summary,
    detect_output_path,
    resolve_verification_output_path,
)


def test_detect_output_path_returns_first_report_path() -> None:
    stdout = "Starting run\nReport: /tmp/analysis.xlsx, /tmp/publication.xlsx\nDone\n"

    assert detect_output_path(stdout) == "/tmp/analysis.xlsx"


def test_resolve_verification_output_path_prefers_output_base_expectation() -> None:
    case = {
        "expectations": ["publication_workbook", "output_base=/tmp/base.xlsx"],
    }
    stdout = "Report: /tmp/base_publication.xlsx\n"

    assert resolve_verification_output_path(case, stdout) == "/tmp/base.xlsx"


def test_build_summary_counts_case_statuses_by_suite() -> None:
    records = [
        {"suite": "share", "status": "passed"},
        {"suite": "share", "status": "verification_failed"},
        {"suite": "rate", "status": "failed"},
    ]

    summary = build_summary(records, elapsed_seconds=1.25)

    assert summary["total_cases"] == 3
    assert summary["passed"] == 1
    assert summary["verification_failed"] == 1
    assert summary["failed"] == 1
    assert summary["suites"]["share"]["total"] == 2
    assert summary["suites"]["rate"]["failed"] == 1
