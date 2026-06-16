from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from tools.prod_tui import controlled_job as cj
from tools.prod_tui import job_specs, levels


# --- impala result-row detection (false-positive guard) ---------------------


def test_result_row_equals_ignores_echoed_query_line() -> None:
    # impala-shell echoes the statement (which contains the table name) but
    # SHOW TABLES returned no rows: this must NOT count as the table existing.
    screen = (
        "Query: SHOW TABLES IN aa_enc LIKE 'dispatch_smoke_corr0'\n"
        "Fetched 0 row(s) in 0.70s\n"
    )
    assert cj._result_row_equals(screen, "dispatch_smoke_corr0") is False


def test_result_row_equals_matches_real_result_row() -> None:
    screen = (
        "Query: SHOW TABLES IN aa_enc LIKE 'dispatch_smoke_corr0'\n"
        "dispatch_smoke_corr0\n"
        "Fetched 1 row(s) in 0.30s\n"
    )
    assert cj._result_row_equals(screen, "dispatch_smoke_corr0") is True


# --- expected created-table name (orchestrator naming) ----------------------


def test_expected_table_name_plain_for_sqlfile_table() -> None:
    run = _dummy_run()  # level3_spec() -> SqlFile -> Table
    assert cj.expected_table_name(run) == run.table_name


def test_expected_table_name_fulljoin_for_template() -> None:
    run = cj.ControlledRun(
        config=None,  # type: ignore[arg-type]
        driver=None,  # type: ignore[arg-type]
        table_name="dispatch_smoke_t",
        spec=job_specs._SQLTEMPLATE_TABLE,
    )
    assert cj.expected_table_name(run) == "dispatch_smoke_t_fulljoin"


# --- job-id extraction -------------------------------------------------------


def test_extract_job_id_from_launch_toast() -> None:
    # Job-id tokens are base32-lowercase: [a-z2-7], never 0/1/8/9.
    screen = "\u2713 Launched Job 20260616T013000Z_ab2cde\nsome footer"
    assert cj.extract_job_id(screen) == "20260616T013000Z_ab2cde"


def test_extract_job_id_handles_ansi() -> None:
    screen = "\x1b[32m\u2713 Launched Job 20260616T013000Z_zz7qqr\x1b[0m"
    assert cj.extract_job_id(screen) == "20260616T013000Z_zz7qqr"


def test_extract_job_id_none_when_absent() -> None:
    assert cj.extract_job_id("Dashboard with no launch toast") is None


# --- manifest state poll command --------------------------------------------


def test_state_poll_command_uses_specific_manifest_when_job_id_given() -> None:
    run = _dummy_run()
    cmd = cj._state_poll_command(run, "20260616T013000Z_ab12cd")
    assert "20260616T013000Z_ab12cd/manifest.json" in cmd
    assert "/*/manifest.json" not in cmd  # no ambiguous glob


def test_state_poll_command_falls_back_to_table_glob() -> None:
    run = _dummy_run()
    cmd = cj._state_poll_command(run, None)
    assert "/*/manifest.json" in cmd
    assert run.table_name in cmd


# --- wait_for_job_completion: ignore stale state above fresh output ----------


class _FakeDriver:
    def __init__(self, screen: str) -> None:
        self._screen = screen

    def run_remote(self, _cmd: str, timeout: float = 40):  # noqa: ARG002
        return self._screen, 0


def _run_with_screen(screen: str) -> cj.ControlledRun:
    return cj.ControlledRun(
        config=SimpleNamespace(max_smoke_job_wait_seconds=30),  # type: ignore[arg-type]
        driver=_FakeDriver(screen),  # type: ignore[arg-type]
        table_name="dispatch_smoke_x",
        spec=job_specs.level3_spec(),
    )


def test_wait_for_completion_is_scoped_to_this_jobs_id() -> None:
    # THIS job is "Succeeded"; a *different* job's "Failed" line appears LOWER on
    # the pane. A naive last-match scan would wrongly return "Failed"; the
    # id-scoped match must return this job's own "Succeeded".
    this_id = "20260616T000000Z_aaaaaa"
    other_id = "20260616T000000Z_bbbbbb"
    screen = (
        f'DISPATCH_STATE {this_id} "state": "Succeeded"\n'
        f'DISPATCH_STATE {other_id} "state": "Failed"\n'
        f'__RC_abc123_0__\n'
    )
    run = _run_with_screen(screen)
    assert cj.wait_for_job_completion(run, job_id=this_id) == "Succeeded"


def test_wait_for_completion_ignores_other_job_while_running(monkeypatch) -> None:
    # THIS job is only "Running" while another job's "Failed" is on the pane:
    # must not return; it should time out rather than report the other's state.
    monkeypatch.setattr(cj.time, "sleep", lambda _s: None)
    this_id = "20260616T000000Z_aaaaaa"
    other_id = "20260616T000000Z_bbbbbb"
    screen = (
        f'DISPATCH_STATE {other_id} "state": "Failed"\n'
        f'DISPATCH_STATE {this_id} "state": "Running"\n'
        f'__RC_abc123_0__\n'
    )
    run = cj.ControlledRun(
        config=SimpleNamespace(max_smoke_job_wait_seconds=0.05),  # type: ignore[arg-type]
        driver=_FakeDriver(screen),  # type: ignore[arg-type]
        table_name="dispatch_smoke_x",
        spec=job_specs.level3_spec(),
    )
    with pytest.raises(TimeoutError):
        cj.wait_for_job_completion(run, job_id=this_id)


# --- CSV probe evaluation (uncompressed invariant) --------------------------


def test_evaluate_csv_probe_accepts_uncompressed() -> None:
    screen = "CSV_OK magic=736d bytes=42 rows=2"
    assert cj.evaluate_csv_probe(screen, "/tmp/x.csv") is screen


def test_evaluate_csv_probe_rejects_missing() -> None:
    with pytest.raises(RuntimeError, match="not found or empty"):
        cj.evaluate_csv_probe("CSV_MISSING", "/tmp/x.csv")


def test_evaluate_csv_probe_rejects_gzip_magic() -> None:
    screen = "CSV_OK magic=1f8b bytes=42 rows=2"
    with pytest.raises(RuntimeError, match="gzip-compressed"):
        cj.evaluate_csv_probe(screen, "/tmp/x.csv")


def test_csv_probe_command_quotes_path() -> None:
    cmd = cj.csv_probe_command("/tmp/dispatch smoke.csv")
    assert "'/tmp/dispatch smoke.csv'" in cmd
    assert "1f8b" not in cmd  # the magic check is done after, not baked in


# --- month bounds ------------------------------------------------------------


def test_month_bounds_returns_first_and_last_day() -> None:
    start, end = levels.month_bounds(date(2026, 2, 10))
    assert start == "2026-02-01"
    assert end == "2026-02-28"  # 2026 is not a leap year


# --- csv path derivation -----------------------------------------------------


def test_controlled_run_csv_path_in_launch_cwd() -> None:
    run = _dummy_run()
    run.launch_cwd = "/tmp"
    assert run.csv_path == f"/tmp/{run.table_name}.csv"


def _dummy_run() -> cj.ControlledRun:
    # A driver/config are not touched by the pure helpers under test.
    return cj.ControlledRun(
        config=None,  # type: ignore[arg-type]
        driver=None,  # type: ignore[arg-type]
        table_name="dispatch_smoke_tester_20260616_010101",
        spec=job_specs.level3_spec(),
    )
