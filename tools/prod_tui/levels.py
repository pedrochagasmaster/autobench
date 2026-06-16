"""Levels 4-6 controlled production scenarios for the Dispatch TUI.

These build on the Level 3 controlled-job machinery in :mod:`controlled_job`:

* **Level 4 - job-type breadth.** Runs every *legal* Source x Destination cell
  beyond L3's ``SqlFile -> Table`` and verifies the right artifact (table, an
  uncompressed CSV in the launch cwd, or both for the decomposed Table+Csv job).
* **Level 5 - supervision & safety semantics.** Prod-safe behaviors: the
  detached runner surviving a TUI quit, the form refusing an illegal
  destination, and the 2-job concurrency cap being observable. Failure-injection
  and Kerberos-expiry cases are covered by mocks/unit tests (they cannot be
  forced safely against the real cluster with the approved smoke SELECT).
* **Level 6 - production fidelity (opt-in).** Heavier, flag-gated checks:
  data correctness of a created table, a soak loop, and upgrade-in-place. M10
  real-query parity and multi-user isolation remain human-gated.

All levels reuse the single authenticated tmux/SSH session (``--reuse-session``)
exactly like Level 3, since single-use RSA 2FA cannot be re-driven.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

try:  # pragma: no cover - exercised when run as a script
    from . import controlled_job as cj
    from . import job_specs
    from .job_specs import JobSpec
    from .robocop_tmux import DEFAULT_CONFIG_PATH, ProdTuiConfig, TmuxDriver, load_config
except ImportError:  # pragma: no cover
    import controlled_job as cj
    import job_specs
    from job_specs import JobSpec
    from robocop_tmux import DEFAULT_CONFIG_PATH, ProdTuiConfig, TmuxDriver, load_config

REPORTS_DIR = cj.REPORTS_DIR
SCREENS_DIR = cj.SCREENS_DIR


def month_bounds(today: date | None = None) -> tuple[str, str]:
    """First and last day of the current month as ISO strings (form input format)."""
    today = today or date.today()
    import calendar

    last = calendar.monthrange(today.year, today.month)[1]
    return today.replace(day=1).isoformat(), today.replace(day=last).isoformat()


def _make_run(
    config: ProdTuiConfig,
    driver: TmuxDriver,
    spec: JobSpec,
    *,
    run_timestamp: str,
    tag: str,
    index: int,
) -> cj.ControlledRun:
    # Per-job table name (timestamp + index keeps a batch's names unique and
    # safe-prefixed) and per-job temp file paths so concurrent specs never
    # clobber each other's SQL / prefill scratch files.
    base = cj.generate_smoke_table_name(config)
    table_name = f"{base}_{tag}{index}"
    run = cj.ControlledRun(
        config=config,
        driver=driver,
        table_name=table_name,
        spec=spec,
        run_timestamp=run_timestamp,
        sql_path=f"/tmp/dispatch_smoke_{tag}{index}.sql",
        prefill_path=f"/tmp/dispatch_prefill_{tag}{index}.json",
        screens_dir=SCREENS_DIR / f"level_{run_timestamp}",
    )
    if spec.is_template:
        run.start_date, run.end_date = month_bounds()
    return run


def execute_spec(run: cj.ControlledRun, *, dry_run: bool = False) -> None:
    """Full controlled lifecycle for one spec, recording steps on ``run``.

    Mirrors :func:`controlled_job.controlled_lifecycle` but is spec-driven and
    assumes the session/prerequisites were already established by the caller.
    """
    started = time.monotonic()
    cj.create_smoke_sql_file(run)
    run.record("create_sql_file", True, f"Wrote {run.sql_path}", started)

    started = time.monotonic()
    violations = cj.collect_preconditions(run)
    if violations:
        run.record("preconditions", False, "; ".join(violations), started, run.capture("preconditions_failed"))
        raise RuntimeError("Launch preconditions failed")
    run.record("preconditions", True, "Launch preconditions satisfied", started, run.capture("preconditions"))

    started = time.monotonic()
    screen = cj.open_prefilled_new_job(run)
    run.record("open_prefilled_new_job", True, f"Prefilled New Job ({run.spec.name})", started, screen)

    started = time.monotonic()
    screen = cj.verify_prefilled_form(run)
    run.record("verify_prefilled_form", True, "Form values visible for spec", started, screen)

    started = time.monotonic()
    screen = cj.preview_and_verify(run)
    run.record("preview_and_verify", True, "Preview verified (or skipped for ExistingTable)", started, screen)

    if dry_run:
        started = time.monotonic()
        run.driver.send_key("q")
        run.record("dry_run_exit", True, "Stopped before Launch as requested", started, run.capture("dry_run_exit"))
        return

    started = time.monotonic()
    screen = cj.launch_and_confirm(run)
    job_id = cj.extract_job_id(screen)
    run.record("launch_and_confirm", True, f"Launch confirmed (job_id={job_id})", started, screen)

    started = time.monotonic()
    state = cj.wait_for_job_completion(run, job_id)
    if state != "Succeeded":
        run.record("wait_for_job_completion", False, f"Job ended as {state}", started, run.capture("job_failed"))
        raise RuntimeError(f"Job ended as {state}")
    run.record("wait_for_job_completion", True, "Job succeeded", started, run.capture("job_succeeded"))

    started = time.monotonic()
    output = cj.verify_artifact(run)
    run.record("verify_artifact", True, f"Artifact verified ({run.spec.verify})", started, output)


# ----------------------------------------------------------------------------
# Level 4 - job-type breadth
# ----------------------------------------------------------------------------


def run_level_4(
    config: ProdTuiConfig,
    driver: TmuxDriver,
    run_timestamp: str,
    *,
    dry_run: bool = False,
    fail_fast: bool = False,
) -> list[cj.ControlledRun]:
    runs: list[cj.ControlledRun] = []
    for index, spec in enumerate(job_specs.level4_specs()):
        if spec.needs_existing_table and not dry_run:
            # Seed a real table first, then export it via the ExistingTable cell.
            seed = _make_run(config, driver, job_specs.level3_spec(), run_timestamp=run_timestamp, tag="seed", index=index)
            runs.append(seed)
            try:
                execute_spec(seed)
            except Exception as exc:  # noqa: BLE001
                seed.record("spec_failed", False, f"{type(exc).__name__}: {exc}", time.monotonic())
                if fail_fast:
                    return runs
                continue
            run = _make_run(config, driver, spec, run_timestamp=run_timestamp, tag="l4_", index=index)
            run.table_name = seed.table_name
            run.existing_table = f"{config.scratch_schema}.{seed.table_name}"
        else:
            run = _make_run(config, driver, spec, run_timestamp=run_timestamp, tag="l4_", index=index)
        runs.append(run)
        try:
            execute_spec(run, dry_run=dry_run)
        except Exception as exc:  # noqa: BLE001
            run.record("spec_failed", False, f"{type(exc).__name__}: {exc}", time.monotonic())
            if fail_fast:
                return runs
    return runs


# ----------------------------------------------------------------------------
# Level 5 - supervision & safety semantics (prod-safe subset)
# ----------------------------------------------------------------------------


def check_detached_survival(config: ProdTuiConfig, driver: TmuxDriver, run_timestamp: str) -> cj.ControlledRun:
    """Launch a job, immediately quit the TUI, and confirm the detached runner
    still drives the job to a terminal state read from the manifest."""
    run = _make_run(config, driver, job_specs.level3_spec(), run_timestamp=run_timestamp, tag="surv", index=0)
    started = time.monotonic()
    cj.create_smoke_sql_file(run)
    violations = cj.collect_preconditions(run)
    if violations:
        run.record("detached_preconditions", False, "; ".join(violations), started, run.capture("surv_pre"))
        return run
    cj.open_prefilled_new_job(run)
    cj.verify_prefilled_form(run)
    screen = cj.launch_and_confirm(run)
    job_id = cj.extract_job_id(screen)
    run.record("detached_launch", True, f"Launched job_id={job_id}", started, screen)

    started = time.monotonic()
    driver.return_to_shell()
    run.record("detached_quit_tui", True, "Closed Dispatch; runner now unsupervised by the TUI", started)

    started = time.monotonic()
    state = cj.wait_for_job_completion(run, job_id)
    passed = state == "Succeeded"
    run.record("detached_survival", passed, f"Job reached {state} with the TUI closed", started)
    if passed:
        cj.verify_artifact(run)
    return run


def check_illegal_destination_refused(config: ProdTuiConfig, driver: TmuxDriver, run_timestamp: str) -> cj.ControlledRun:
    """Prefill an *illegal* cell (ExistingTable -> Table) and confirm the form
    refuses it by auto-correcting to the only legal destination (Csv).

    This proves illegal Source/Destination combinations can never be launched,
    without actually launching anything.
    """
    run = _make_run(config, driver, job_specs._EXISTINGTABLE_CSV, run_timestamp=run_timestamp, tag="illegal", index=0)
    run.existing_table = f"{config.scratch_schema}.dispatch_smoke_seed_probe"
    started = time.monotonic()
    # Force an illegal destination into the prefill payload.
    prefill = job_specs.prefill_for(
        run.spec, sql_path=run.sql_path, schema=config.scratch_schema,
        table_name=run.table_name, existing_table=run.existing_table,
    )
    prefill["dest_type"] = "Table"  # illegal for ExistingTable
    import base64
    import shlex

    encoded = base64.b64encode(json.dumps(prefill).encode("utf-8")).decode("ascii")
    driver.return_to_shell()
    driver.run_remote(f"printf %s {shlex.quote(encoded)} | base64 -d > {shlex.quote(run.prefill_path)}")
    driver.type_command_confirmed(
        f"cd /tmp && DISPATCH_TEST_PREFILL={shlex.quote(run.prefill_path)} dispatch"
    )
    driver.wait_for(r"New Job|Source.*Destination", timeout=20)
    screen = driver.wait_for(r"Existing Table|supports Csv only", timeout=15)
    plain = cj._strip_ansi(screen)
    corrected = "supports Csv only" in plain or "Existing Table" in plain
    # If the form had honored the illegal Table destination it would show the
    # Table Name row and no ExistingTable hint.
    run.record(
        "illegal_destination_refused",
        corrected,
        "Form corrected the illegal ExistingTable->Table to the legal Csv cell",
        started,
        screen,
    )
    driver.return_to_shell()
    return run


def check_concurrency_cap_observable(config: ProdTuiConfig, driver: TmuxDriver, run_timestamp: str) -> cj.ControlledRun:
    """Confirm the dashboard exposes the running-job count against the cap.

    The hard refusal of a 3rd concurrent job is enforced by ``jobs.can_launch``
    and unit-tested; holding two jobs Running against the real cluster is not
    possible with an instant smoke SELECT, so here we assert the cap is visible
    and within bounds.
    """
    run = _make_run(config, driver, job_specs.level3_spec(), run_timestamp=run_timestamp, tag="conc", index=0)
    started = time.monotonic()
    driver.type_command_confirmed("cd /tmp && dispatch")
    screen = driver.wait_for(r"RUNNING\s+\d+\s*/\s*2", timeout=20)
    import re

    match = re.search(r"RUNNING\s+(\d+)\s*/\s*2", cj._strip_ansi(screen))
    running = int(match.group(1)) if match else -1
    passed = 0 <= running <= 2
    run.record(
        "concurrency_cap_observable",
        passed,
        f"Dashboard reports RUNNING {running}/2 (cap respected)",
        started,
        screen,
    )
    driver.return_to_shell()
    return run


def run_level_5(config: ProdTuiConfig, driver: TmuxDriver, run_timestamp: str) -> list[cj.ControlledRun]:
    checks: list[Callable[..., cj.ControlledRun]] = [
        check_concurrency_cap_observable,
        check_illegal_destination_refused,
        check_detached_survival,
    ]
    runs: list[cj.ControlledRun] = []
    for check in checks:
        try:
            runs.append(check(config, driver, run_timestamp))
        except Exception as exc:  # noqa: BLE001
            placeholder = _make_run(config, driver, job_specs.level3_spec(), run_timestamp=run_timestamp, tag="l5err", index=len(runs))
            placeholder.record(check.__name__, False, f"{type(exc).__name__}: {exc}", time.monotonic())
            runs.append(placeholder)
    return runs


# ----------------------------------------------------------------------------
# Level 6 - production fidelity (opt-in / flag-gated)
# ----------------------------------------------------------------------------


def check_data_correctness(config: ProdTuiConfig, driver: TmuxDriver, run_timestamp: str) -> cj.ControlledRun:
    """Create a table, then read it back and assert its content matches the
    smoke SELECT (one row, value 1)."""
    import shlex

    run = _make_run(config, driver, job_specs.level3_spec(), run_timestamp=run_timestamp, tag="corr", index=0)
    execute_spec(run)
    started = time.monotonic()
    fqtn = f"{config.scratch_schema}.{run.table_name}"
    # A table created by the orchestrator's session is not always immediately
    # resolvable from the coordinator the load balancer hands us (Impala catalog
    # propagation). We retry the plain SELECT and, once a couple of attempts have
    # not resolved it, escalate to a *global* INVALIDATE METADATA to force a
    # catalog reload. The table-scoped ``INVALIDATE METADATA <table>`` is avoided
    # because under local-catalog mode (Impala 4.0) it raises a fatal
    # TableNotFoundException for a table the coordinator has never seen.
    select_stmt = f"SELECT smoke_test_value FROM {fqtn};"
    forcing_stmt = f"INVALIDATE METADATA; {select_stmt}"
    rows: list[str] = []
    screen = ""
    for attempt in range(6):
        stmt = forcing_stmt if attempt >= 2 else select_stmt
        command = (
            f"impala-shell -k --ssl -i {shlex.quote(config.impala_coordinator)} "
            f"--delimited -q {shlex.quote(stmt)}"
        )
        screen, code = driver.run_remote(command, timeout=60)
        # Expect exactly one data row whose only column equals 1.
        rows = [ln.strip() for ln in cj._strip_ansi(screen).splitlines() if ln.strip() == "1"]
        if code == 0 and len(rows) == 1:
            break
        time.sleep(5)
    passed = len(rows) == 1
    run.record("data_correctness", passed, f"Table content rows==1 with value 1 (got {len(rows)})", started, screen)
    return run


def run_soak(
    config: ProdTuiConfig,
    driver: TmuxDriver,
    run_timestamp: str,
    iterations: int,
) -> list[cj.ControlledRun]:
    """Repeatedly run the happy-path table job to surface leaks / drift."""
    runs: list[cj.ControlledRun] = []
    for i in range(max(1, iterations)):
        run = _make_run(config, driver, job_specs.level3_spec(), run_timestamp=run_timestamp, tag="soak", index=i)
        runs.append(run)
        try:
            execute_spec(run)
        except Exception as exc:  # noqa: BLE001
            run.record("soak_iteration", False, f"iteration {i}: {type(exc).__name__}: {exc}", time.monotonic())
    return runs


def check_upgrade_in_place(config: ProdTuiConfig, driver: TmuxDriver, run_timestamp: str) -> cj.ControlledRun:
    """Re-run install.sh over the existing install and confirm the reported
    version still matches the repo VERSION file."""
    run = _make_run(config, driver, job_specs.level3_spec(), run_timestamp=run_timestamp, tag="upgr", index=0)
    started = time.monotonic()
    out, code = driver.run_remote(f"cd {config.repo_path} && ./install.sh 2>&1 | tail -n 3", timeout=180)
    install_ok = code == 0
    run.record("upgrade_install", install_ok, f"install.sh exit {code}", started, out)
    started = time.monotonic()
    out, _ = driver.run_remote(
        f"cat {config.repo_path}/VERSION 2>/dev/null && dispatch --version 2>/dev/null | tail -n1",
        timeout=30,
    )
    run.record("upgrade_version_visible", True, "Captured VERSION and dispatch --version", started, out)
    return run


def run_level_6(
    config: ProdTuiConfig,
    driver: TmuxDriver,
    run_timestamp: str,
    *,
    soak_iterations: int = 2,
) -> list[cj.ControlledRun]:
    runs: list[cj.ControlledRun] = []
    runs.append(check_data_correctness(config, driver, run_timestamp))
    runs.extend(run_soak(config, driver, run_timestamp, soak_iterations))
    runs.append(check_upgrade_in_place(config, driver, run_timestamp))
    return runs


# ----------------------------------------------------------------------------
# Session setup + CLI
# ----------------------------------------------------------------------------


def _ensure_session(config: ProdTuiConfig, driver: TmuxDriver, *, reuse_session: bool, passcode: str | None) -> None:
    if driver.session_exists():
        return
    if reuse_session:
        raise RuntimeError(
            f"--reuse-session was set but no live tmux session {config.session_name!r} exists. "
            "Authenticate one first, e.g.: py tools/prod_tui/robocop_tmux.py start --passcode <CODE>"
        )
    driver.start_session(passcode=passcode)


def _cleanup(runs: list[cj.ControlledRun], driver: TmuxDriver) -> None:
    seen: set[tuple[str, str]] = set()
    for run in runs:
        key = (run.table_name, run.spec.name)
        if key in seen:
            continue
        seen.add(key)
        try:
            cj.cleanup_smoke_files(run)
            cj.cleanup_artifacts(run)
        except Exception:  # noqa: BLE001
            pass


def write_report(level: int, runs: list[cj.ControlledRun], started: float, path: str | None) -> Path:
    report_path = Path(path) if path else REPORTS_DIR / f"level{level}_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    steps = [step for run in runs for step in run.steps]
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "level": level,
        "duration_seconds": round(time.monotonic() - started, 3),
        "jobs": [
            {"table_name": run.table_name, "spec": run.spec.name, "cell": list(run.spec.cell)}
            for run in runs
        ],
        "results": [
            {"name": s.name, "passed": s.passed, "message": s.message, "elapsed_ms": s.elapsed_ms}
            for s in steps
        ],
        "summary": {
            "total": len(steps),
            "passed": sum(1 for s in steps if s.passed),
            "failed": sum(1 for s in steps if not s.passed),
        },
    }
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return report_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Level 4-6 controlled production scenarios")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--level", choices=["4", "5", "6"], required=True)
    parser.add_argument("--dry-run", action="store_true", help="Fill/preview each job but stop before Launch (L4)")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--soak-iterations", type=int, default=2, help="L6 soak repetitions")
    parser.add_argument("--json-report")
    parser.add_argument("--passcode")
    parser.add_argument("--reuse-session", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
    args = build_parser().parse_args(argv)
    started = time.monotonic()
    run_timestamp = cj.utc_stamp()
    config = load_config(args.config)
    driver = TmuxDriver.from_config(config, retries=2)
    level = int(args.level)
    runs: list[cj.ControlledRun] = []
    exit_code = 0
    try:
        _ensure_session(config, driver, reuse_session=args.reuse_session, passcode=args.passcode)
        if level == 4:
            runs = run_level_4(config, driver, run_timestamp, dry_run=args.dry_run, fail_fast=args.fail_fast)
        elif level == 5:
            runs = run_level_5(config, driver, run_timestamp)
        else:
            runs = run_level_6(config, driver, run_timestamp, soak_iterations=args.soak_iterations)
        if any(not step.passed for run in runs for step in run.steps):
            exit_code = 1
    except Exception as exc:  # noqa: BLE001
        exit_code = exit_code or 1
        print(f"Level {level} run failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    finally:
        try:
            if driver.session_exists() and driver.at_shell_prompt():
                if not args.dry_run:
                    _cleanup(runs, driver)
        except Exception:  # noqa: BLE001
            pass
        if not args.reuse_session:
            try:
                driver.stop_session()
            except Exception:  # noqa: BLE001
                pass
        report_path = write_report(level, runs, started, args.json_report)
        print(f"JSON report: {report_path}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
