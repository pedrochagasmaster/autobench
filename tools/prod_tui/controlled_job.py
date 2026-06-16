"""Controlled Level 3 production smoke job runner."""

from __future__ import annotations

import argparse
import base64
import json
import re
import shlex
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

try:  # pragma: no cover - exercised when run as a script
    from . import job_specs, safety
    from .agent_loop import parse_screen
    from .job_specs import JobSpec
    from .robocop_tmux import DEFAULT_CONFIG_PATH, ProdTuiConfig, TmuxDriver, load_config
    from .smoke_test import RunContext, SmokeResult, selected_levels, checks_for_level, run_check, utc_stamp
except ImportError:  # pragma: no cover
    import job_specs
    import safety
    from agent_loop import parse_screen
    from job_specs import JobSpec
    from robocop_tmux import DEFAULT_CONFIG_PATH, ProdTuiConfig, TmuxDriver, load_config
    from smoke_test import RunContext, SmokeResult, selected_levels, checks_for_level, run_check, utc_stamp

HARNESS_DIR = Path(__file__).resolve().parent
REPORTS_DIR = HARNESS_DIR / "reports"
SCREENS_DIR = HARNESS_DIR / "screens"


def _safe_print(text: str) -> None:
    """Print text that may contain box-drawing/Unicode on a cp1252 console."""
    try:
        print(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(text.encode(enc, "replace").decode(enc))


@dataclass
class ControlledStep:
    name: str
    passed: bool
    message: str
    elapsed_ms: int = 0
    screen_capture: str = ""


@dataclass
class ControlledRun:
    config: ProdTuiConfig
    driver: TmuxDriver
    table_name: str
    sql_path: str = "/tmp/dispatch_smoke_test.sql"
    prefill_path: str = "/tmp/dispatch_prefill.json"
    run_timestamp: str = field(default_factory=utc_stamp)
    save_screens: bool = True
    screens_dir: Path | None = None
    steps: list[ControlledStep] = field(default_factory=list)
    passcode: str | None = None
    reuse_session: bool = False
    # Level 3 covers exactly one cell; Levels 4+ vary the spec per job.
    spec: JobSpec = field(default_factory=job_specs.level3_spec)
    # Source table for an ExistingTable->Csv job (schema.table).
    existing_table: str = ""
    # ISO dates for a SqlTemplate job; the form converts them for the orchestrator.
    start_date: str = ""
    end_date: str = ""
    # Launch-time cwd Dispatch is started from (CSV outputs land here).
    launch_cwd: str = "/tmp"

    @property
    def csv_path(self) -> str:
        """Where a Csv/Table+Csv job writes its uncompressed export."""
        return f"{self.launch_cwd.rstrip('/')}/{self.table_name}.csv"

    def capture(self, name: str) -> str:
        screen = self.driver.capture_screen()
        if self.save_screens:
            if self.screens_dir is None:
                self.screens_dir = SCREENS_DIR / f"controlled_{self.run_timestamp}"
            self.screens_dir.mkdir(parents=True, exist_ok=True)
            safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_")
            (self.screens_dir / f"{len(self.steps):02d}_{safe_name}.txt").write_text(
                screen + "\n",
                encoding="utf-8",
            )
        return screen

    def record(self, name: str, passed: bool, message: str, started: float, screen: str = "") -> ControlledStep:
        step = ControlledStep(
            name=name,
            passed=passed,
            message=message,
            elapsed_ms=int((time.monotonic() - started) * 1000),
            screen_capture=screen,
        )
        self.steps.append(step)
        status = "PASS" if passed else "FAIL"
        _safe_print(f"[{status}] {name}: {message}")
        if not passed and screen:
            _safe_print("--- last screen ---")
            _safe_print(screen)
            _safe_print("--- end screen ---")
        return step


def generate_smoke_table_name(config: ProdTuiConfig, now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d_%H%M%S")
    user = re.sub(r"[^A-Za-z0-9_]+", "_", config.current_user()).strip("_") or "dispatch"
    return f"{config.table_prefix.rstrip('_')}_{user}_{timestamp}"


def create_smoke_sql_file(run: ControlledRun) -> None:
    # Encode the SQL as base64 so the write command is always a single line with
    # no shell-special characters. Embedding the raw SQL (which ends in a
    # newline, and may contain quotes) would split the command across lines and
    # strand the pane at a quote-continuation ">" prompt.
    payload = (run.spec.sql_body().rstrip("\n") + "\n").encode("utf-8")
    encoded = base64.b64encode(payload).decode("ascii")
    command = f"printf %s {shlex.quote(encoded)} | base64 -d > {shlex.quote(run.sql_path)}"
    _, code = run.driver.run_remote(command)
    if code != 0:
        raise RuntimeError(f"Failed to write smoke SQL file {run.sql_path} (exit {code})")


def cleanup_smoke_files(run: ControlledRun) -> None:
    # Best-effort cleanup through the authenticated pane (no second SSH).
    run.driver.run_remote(f"rm -f {shlex.quote(run.sql_path)} {shlex.quote(run.prefill_path)}")


def build_prefill(run: ControlledRun) -> dict:
    return job_specs.prefill_for(
        run.spec,
        sql_path=run.sql_path,
        schema=run.config.scratch_schema,
        table_name=run.table_name,
        existing_table=run.existing_table,
        email=run.config.operator_email or "",
        subject=f"Dispatch smoke {run.table_name}",
        start_date=run.start_date,
        end_date=run.end_date,
    )


def write_prefill_file(run: ControlledRun) -> None:
    # base64 so the remote write is a single line with no shell-special chars
    # (the JSON contains quotes and braces).
    payload = json.dumps(build_prefill(run)).encode("utf-8")
    encoded = base64.b64encode(payload).decode("ascii")
    command = f"printf %s {shlex.quote(encoded)} | base64 -d > {shlex.quote(run.prefill_path)}"
    _, code = run.driver.run_remote(command)
    if code != 0:
        raise RuntimeError(f"Failed to write prefill file {run.prefill_path} (exit {code})")


def cleanup_smoke_table(run: ControlledRun) -> None:
    # Cleanup is intentionally explicit and limited to the generated smoke table.
    if not safety.is_safe_table_name(run.table_name, table_prefix=run.config.table_prefix):
        raise ValueError(f"Refusing to cleanup unsafe table name: {run.table_name}")
    sql = f"DROP TABLE IF EXISTS {run.config.scratch_schema}.{run.table_name};"
    command = (
        f"impala-shell -k --ssl -i {shlex.quote(run.config.impala_coordinator)} "
        f"-q {shlex.quote(sql)}"
    )
    run.driver.run_remote(command, timeout=60)


_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def press_button(run: ControlledRun, label: str) -> None:
    shortcuts = {"preview": "p", "launch": "l", "back": "b"}
    run.driver.send_key(shortcuts.get(label.lower(), "Enter"))


def _value_beside_label(screen: str, label: str, value: str) -> bool:
    """True when ``value`` appears on the same rendered row as ``label``.

    The New Job form renders each field as a single ``Label  ▊ value ▎`` row, so
    a value sitting next to its own label proves it landed in the intended
    Input (not merely somewhere else on screen).
    """
    plain = _strip_ansi(screen)
    for line in plain.splitlines():
        if label in line and value in line.split(label, 1)[1]:
            return True
    return False


def open_prefilled_new_job(run: ControlledRun) -> str:
    """Open the New Job screen pre-filled via the app's opt-in test seam.

    Driving the Source/Destination radio sets blind over a high-latency SSH PTY
    proved unreliable (dropped Up/Space keystrokes, an unobservable highlight,
    and a dropped Tab risking Source corruption). Instead we write a prefill
    JSON file and launch Dispatch with DISPATCH_TEST_PREFILL pointing at it, so
    the form opens deterministically with source=SqlFile, dest=Table, and the
    schema/table/SQL fields populated.
    """
    run.driver.return_to_shell()
    write_prefill_file(run)
    command = (
        f"cd {shlex.quote(run.launch_cwd)} && "
        f"DISPATCH_TEST_PREFILL={shlex.quote(run.prefill_path)} dispatch"
    )
    run.driver.type_command_confirmed(command)
    run.driver.wait_for(r"New Job|Source.*Destination", timeout=20)
    # The prefill applies the source/destination via call_after_refresh, so the
    # destination-specific rows render a beat after the screen first appears.
    # Wait for the spec's marker before verifying, otherwise we snapshot too early.
    return run.driver.wait_for(job_specs.ready_marker(run.spec), timeout=15)


def verify_prefilled_form(run: ControlledRun) -> str:
    screen = run.capture("filled_form")
    plain = _strip_ansi(screen)
    expected = job_specs.expected_visible_fields(
        run.spec,
        sql_path=run.sql_path,
        schema=run.config.scratch_schema,
        table_name=run.table_name,
        existing_table=run.existing_table,
        start_date=run.start_date,
        end_date=run.end_date,
    )
    for label in expected:
        if label not in plain:
            raise RuntimeError(
                f"Prefill did not render the expected '{label}' row for "
                f"{run.spec.source_type}->{run.spec.dest_type}"
            )
    missing = [
        f"{label}={value!r}"
        for label, value in expected.items()
        if not _value_beside_label(screen, label, value)
    ]
    if missing:
        raise RuntimeError(f"Prefilled form missing expected values beside their labels: {missing}")
    return screen


def preview_and_verify(run: ControlledRun) -> str:
    # Preview is not available for an ExistingTable source (the app shows a
    # warning instead of a Preview screen), so skip it for that cell.
    if run.spec.source_type == "ExistingTable":
        return run.capture("preview_skipped_existing_table")
    # The prefilled New Job focuses a non-Input (Source radio set) so the "p"
    # mnemonic fires the screen-level Preview binding.
    press_button(run, "preview")
    # Match a marker unique to the SQL Preview screen. The New Job screen's
    # footer shows the "Preview SQL" button label, so a bare "Preview" pattern
    # would match before navigation and capture the wrong screen.
    run.driver.wait_for(r"SQL Preview|review before launching", timeout=15)
    # The preview RichLog paints the SQL a beat after the screen frame appears,
    # and the lag grows under cluster load (e.g. after a prior job launch), so
    # poll until both the smoke SELECT and the table name have rendered rather
    # than trusting the first frame that merely matched the screen title.
    deadline = time.monotonic() + 12
    screen = ""
    while time.monotonic() < deadline:
        screen = run.driver.capture_screen()
        if run.config.smoke_query_sql in screen and run.table_name in screen:
            break
        time.sleep(0.5)
    else:
        raise RuntimeError("Preview did not contain the smoke SQL and table name")
    if run.spec.is_template:
        # monthly_preview substitutes {date_inicio}/{date_fim} with ISO dates, so
        # the prefilled dates must appear and the raw placeholders must be gone.
        # This verifies the template dates landed (the form's Start/End Date rows
        # sit below a single SSH pane's fold) and were rendered correctly.
        plain = _strip_ansi(screen)
        if run.start_date not in plain or run.end_date not in plain:
            raise RuntimeError(
                f"Template preview missing substituted dates {run.start_date}..{run.end_date}"
            )
        if "{date_inicio}" in plain or "{date_fim}" in plain:
            raise RuntimeError("Template preview still shows unsubstituted date placeholders")
    run.driver.send_key("b")
    run.driver.wait_for(r"illegal destinations are disabled|pick one to fill", timeout=10)
    return screen


def launch_and_confirm(run: ControlledRun) -> str:
    press_button(run, "launch")
    # The confirm modal is titled "Launch Job" and shows a "Target table" row;
    # match those rather than a bare "Launch" (which is also the New Job button
    # label) so we wait for the modal instead of matching the form behind it.
    screen = run.driver.wait_for(r"Launch Job|Target table", timeout=15)
    run.driver.send_key("y")
    # _launch_flow stays on the New Job screen and shows a "Launched Job" toast;
    # it does not auto-navigate. Confirm the toast, then return to the dashboard
    # so job status rows become observable.
    screen = run.driver.wait_for(r"Launched Job", timeout=20)
    run.driver.send_key("escape")
    run.driver.wait_for(
        r"running first|No jobs in the last 7 days|FINISHED 7D|RUNNING|Succeeded|Failed",
        timeout=15,
    )
    return screen


_JOB_ID_RE = re.compile(r"(\d{8}T\d{6}Z_[a-z2-7]{6})")


def extract_job_id(screen: str) -> str | None:
    """Pull the launched job id out of the 'Launched Job <id>' toast/message.

    Polling a specific manifest by id is unambiguous, unlike grepping every
    manifest for a table name (multiple jobs in a batch can share one name).
    """
    match = _JOB_ID_RE.search(_strip_ansi(screen))
    return match.group(1) if match else None


def _state_poll_command(run: ControlledRun, job_id: str | None) -> str:
    # Emit a single self-identifying line, ``DISPATCH_STATE <id> "state": "..."``,
    # so the poll's result can be tied to *this* job. ``run_remote`` returns the
    # whole pane, which can still show a previous job's state line; matching on
    # the unique id (job-id, or table name for the L3 fallback) makes a stale
    # line from another job impossible to mistake for this one.
    base = "${DISPATCH_DATA_ROOT:-/ads_storage/$USER}/.dispatch/jobs"
    if job_id:
        manifest_path = f"{base}/{job_id}/manifest.json"
        return (
            f"printf 'DISPATCH_STATE {job_id} '; "
            f"( [ -f {manifest_path} ] && grep -o '\"state\": *\"[^\"]*\"' {manifest_path} "
            f"|| echo NO_JOB ) | tr -d '\\n'; echo"
        )
    # Fallback: locate by table name (used by Level 3's single-job run).
    return (
        f"d=$(grep -l '{run.table_name}' {base}/*/manifest.json 2>/dev/null | head -n1); "
        f"printf 'DISPATCH_STATE {run.table_name} '; "
        f"( [ -n \"$d\" ] && grep -o '\"state\": *\"[^\"]*\"' \"$d\" || echo NO_JOB ) "
        f"| tr -d '\\n'; echo"
    )


def wait_for_job_completion(run: ControlledRun, job_id: str | None = None) -> str:
    # Poll the on-disk job manifest rather than scraping the dashboard: the
    # dashboard truncates the schema.table cell to 26 chars (so the full table
    # name never appears) and the detached runner keeps going after the TUI is
    # closed, so reading the authoritative manifest state is reliable.
    cmd = _state_poll_command(run, job_id)
    marker = re.escape(job_id if job_id else run.table_name)
    # Match only the state tied to THIS job's id (or table name). ``run_remote``
    # returns the whole pane and the completion regex ignores the "Running"
    # intermediate, so a previous job's stale "Failed"/"Succeeded" line would
    # otherwise be the only match. Take the last id-scoped match for safety.
    pattern = rf'DISPATCH_STATE {marker} "state":\s*"(Succeeded|Failed|Cancelled)"'
    deadline = time.monotonic() + run.config.max_smoke_job_wait_seconds
    last_output = ""
    while time.monotonic() < deadline:
        last_output, _ = run.driver.run_remote(cmd, timeout=40)
        matches = re.findall(pattern, last_output)
        if matches:
            return matches[-1]
        time.sleep(5)
    raise TimeoutError(f"Timed out waiting for smoke job completion. Last output:\n{last_output}")


def _result_row_equals(screen: str, value: str) -> bool:
    """True when a standalone --delimited result line equals ``value``.

    impala-shell echoes the statement as ``Query: ...`` (which also contains the
    table name), so an ``in`` check produces false positives. Matching a line
    that *equals* the value ignores the echo and only trusts an actual result
    row.
    """
    return any(line.strip() == value for line in _strip_ansi(screen).splitlines())


def expected_table_name(run: ControlledRun) -> str:
    """The table the orchestrator actually creates for this spec.

    ``monthly_query_processor.py`` (SqlTemplate -> Table) joins per-month temp
    tables into ``<table>_fulljoin``, whereas the wrapped SqlFile -> Table path
    creates ``<table>`` directly.
    """
    if run.spec.is_template:
        return f"{run.table_name}_fulljoin"
    return run.table_name


def verify_table_exists(run: ControlledRun) -> str:
    # Connect the same way the production orchestrator does (Kerberos + SSL to a
    # named coordinator); a bare ``impala-shell`` defaults to localhost:21000
    # and cannot reach the cluster from the edge node.
    #
    # A table just created by the orchestrator's impala-shell session may not yet
    # be visible on the coordinator we reach through the load balancer (Impala
    # catalog propagation). We confirm an actual SHOW TABLES *result row* names
    # our table -- not merely the echoed query line, which also contains the
    # name -- and retry to ride out propagation.
    #
    # We do NOT use the table-scoped ``INVALIDATE METADATA <table>``: under this
    # cluster's local-catalog mode (Impala 4.0) it raises TableNotFoundException
    # for a table the coordinator has never seen, which aborts the batch before
    # SHOW TABLES runs. Instead we retry plain SHOW TABLES and, once a couple of
    # attempts have not yet seen the table, escalate to a *global* INVALIDATE
    # METADATA (which never throws) to force the coordinator to reload its list.
    db = run.config.scratch_schema
    table = expected_table_name(run)
    fqtn = f"{db}.{table}"
    show_stmt = f"SHOW TABLES IN {db} LIKE '{table}';"
    forcing_stmt = f"INVALIDATE METADATA; {show_stmt}"
    last = ""
    for attempt in range(6):
        stmt = forcing_stmt if attempt >= 2 else show_stmt
        command = (
            f"impala-shell -k --ssl -i {shlex.quote(run.config.impala_coordinator)} "
            f"--delimited -q {shlex.quote(stmt)}"
        )
        screen, _code = run.driver.run_remote(command, timeout=60)
        last = screen
        if _result_row_equals(screen, table):
            return screen
        time.sleep(5)
    raise RuntimeError(f"Smoke table {fqtn} was not visible in Impala after retries: {last}")


def csv_probe_command(csv_path: str) -> str:
    """Shell that reports a CSV's presence, leading magic bytes, size and rows."""
    q = shlex.quote(csv_path)
    return (
        f"if [ -s {q} ]; then "
        f"magic=$(head -c2 {q} | od -An -tx1 | tr -d ' '); "
        f"bytes=$(wc -c < {q}); "
        f"rows=$(wc -l < {q}); "
        f"echo CSV_OK magic=$magic bytes=$bytes rows=$rows; "
        f"else echo CSV_MISSING; fi"
    )


def evaluate_csv_probe(screen: str, csv_path: str) -> str:
    """Validate a csv_probe_command result; raise on missing/empty/compressed.

    Pure (no I/O) so the uncompressed-invariant logic is unit-testable. The
    product invariant is that CSV outputs are written *uncompressed* to the
    launch-time working directory, so the file must exist, have content, and not
    begin with the gzip magic bytes (1f 8b).
    """
    if "CSV_OK" not in screen:
        raise RuntimeError(f"CSV export not found or empty at {csv_path}: {screen}")
    magic = re.search(r"magic=([0-9a-f]*)", screen)
    if magic and magic.group(1).startswith("1f8b"):
        raise RuntimeError(f"CSV export at {csv_path} is gzip-compressed (violates uncompressed invariant)")
    return screen


def verify_csv_artifact(run: ControlledRun) -> str:
    csv = run.csv_path
    screen, _ = run.driver.run_remote(csv_probe_command(csv), timeout=40)
    return evaluate_csv_probe(screen, csv)


def verify_artifact(run: ControlledRun) -> str:
    """Verify the job's output according to its destination type."""
    if run.spec.verify == job_specs.VERIFY_TABLE:
        return verify_table_exists(run)
    if run.spec.verify == job_specs.VERIFY_CSV:
        return verify_csv_artifact(run)
    if run.spec.verify == job_specs.VERIFY_TABLE_AND_CSV:
        table_out = verify_table_exists(run)
        csv_out = verify_csv_artifact(run)
        return f"{table_out}\n{csv_out}"
    raise ValueError(f"Unknown verify kind: {run.spec.verify}")


def cleanup_artifacts(run: ControlledRun) -> None:
    """Drop the smoke table and/or remove the CSV export, per the spec.

    Table drops are guarded by the safe-name policy and limited to the
    generated smoke table (plus any ``_temp_*`` partition tables a template job
    may create).
    """
    if run.spec.produces_csv:
        run.driver.run_remote(f"rm -f {shlex.quote(run.csv_path)}", timeout=20)
    if not run.spec.produces_table and not run.spec.is_template:
        return
    if not safety.is_safe_table_name(run.table_name, table_prefix=run.config.table_prefix):
        raise ValueError(f"Refusing to cleanup unsafe table name: {run.table_name}")
    schema = run.config.scratch_schema
    statements = [f"DROP TABLE IF EXISTS {schema}.{run.table_name};"]
    if run.spec.is_template:
        # monthly_query_processor.py creates <table>_fulljoin plus one
        # <table>_temp_<YYYYMM> per month in the window; drop all of them.
        statements.append(f"DROP TABLE IF EXISTS {schema}.{run.table_name}_fulljoin;")
        month = run.start_date.replace("-", "")[:6] if run.start_date else ""
        if month:
            statements.append(f"DROP TABLE IF EXISTS {schema}.{run.table_name}_temp_{month};")
    sql = " ".join(statements)
    command = (
        f"impala-shell -k --ssl -i {shlex.quote(run.config.impala_coordinator)} "
        f"-q {shlex.quote(sql)}"
    )
    run.driver.run_remote(command, timeout=60)


def parse_klist_ttl_seconds(screen: str) -> int | None:
    match = re.search(r"KRB_TTL=(\d+)", screen)
    return int(match.group(1)) if match else None


_KRB_TTL_SCRIPT = (
    "import subprocess, datetime\n"
    "p = subprocess.run(['klist'], capture_output=True, text=True)\n"
    "ttl = None\n"
    "if p.returncode == 0:\n"
    "    now = datetime.datetime.now()\n"
    "    for line in p.stdout.splitlines():\n"
    "        parts = line.split()\n"
    "        if len(parts) >= 4:\n"
    "            try:\n"
    "                exp = datetime.datetime.strptime(parts[2] + ' ' + parts[3], '%m/%d/%Y %H:%M:%S')\n"
    "            except ValueError:\n"
    "                continue\n"
    "            ttl = max(0, int((exp - now).total_seconds()))\n"
    "            break\n"
    "print('KRB_TTL=' + (str(ttl) if ttl is not None else 'MISSING'))\n"
)
# Resolve a supported interpreter the same way the Level 2 checks do.
_PY = "$(command -v python3.11 || command -v python3.10 || echo /sys_apps_01/python/python310/bin/python3.10)"


def collect_preconditions(run: ControlledRun) -> list[str]:
    # Deliver the TTL probe as a base64 script so it runs from any cwd and never
    # depends on importing the dispatch package (which needs the repo on the
    # path). Single-line, no shell-special characters.
    encoded = base64.b64encode(_KRB_TTL_SCRIPT.encode("utf-8")).decode("ascii")
    ttl_command = f"printf %s {shlex.quote(encoded)} | base64 -d | {_PY} -"
    screen, _ = run.driver.run_remote(ttl_command, timeout=20)
    ttl = parse_klist_ttl_seconds(screen)
    run.driver.type_command_confirmed("cd /tmp && dispatch")
    dashboard = run.driver.wait_for(
        r"running first|No jobs in the last 7 days|FINISHED 7D|RUNNING", timeout=20
    )
    state = parse_screen(dashboard)
    running_jobs = state.running_jobs
    violations = []
    approved_schemas = {"aa_enc", "coe_enc"}
    if run.config.scratch_schema not in approved_schemas:
        violations.append(
            "Configured schema must be one of the approved schemas: aa_enc, coe_enc"
        )
    violations.extend(
        safety.check_launch_preconditions(
            ttl,
            running_jobs,
            run.table_name,
            run.config.smoke_query_sql,
            table_prefix=run.config.table_prefix,
            smoke_query_sql=run.config.smoke_query_sql,
        )
    )
    return violations


def run_level_1_and_2(
    config: ProdTuiConfig,
    driver: TmuxDriver,
    run_timestamp: str,
    fail_fast: bool,
    passcode: str | None = None,
    reuse_session: bool = False,
) -> list[SmokeResult]:
    ctx = RunContext(
        config=config,
        driver=driver,
        run_timestamp=run_timestamp,
        save_screens=True,
        screens_dir=SCREENS_DIR / f"controlled_prereq_{run_timestamp}",
        passcode=passcode,
        reuse_session=reuse_session,
    )
    for level in selected_levels("all"):
        for check in checks_for_level(level):
            result = run_check(ctx, level, check)
            if fail_fast and not result.passed:
                return ctx.results
    return ctx.results


def write_json_report(run: ControlledRun, prereq_results: list[SmokeResult], started: float, path: str | None = None) -> Path:
    report_path = Path(path) if path else REPORTS_DIR / f"controlled_{run.run_timestamp}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "host": run.config.host,
        "levels_run": [1, 2, 3],
        "duration_seconds": round(time.monotonic() - started, 3),
        "table_name": run.table_name,
        "dry_run_supported": True,
        "results": [asdict(result) for result in prereq_results] + [asdict(step) for step in run.steps],
        "summary": {
            "total": len(prereq_results) + len(run.steps),
            "passed": sum(1 for result in prereq_results if result.passed) + sum(1 for step in run.steps if step.passed),
            "failed": sum(1 for result in prereq_results if not result.passed) + sum(1 for step in run.steps if not step.passed),
        },
        "screen_captures": str(run.screens_dir) if run.screens_dir else None,
    }
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return report_path


def controlled_lifecycle(run: ControlledRun, *, dry_run: bool) -> None:
    started = time.monotonic()
    # Reuse the session opened by the Level 1/2 prerequisites (or one the
    # operator authenticated manually). Restarting it would require a second
    # RSA passcode, which single-use 2FA cannot satisfy.
    if run.driver.session_exists():
        run.record("start_session", True, "Reusing authenticated tmux session", started, run.capture("start_session"))
    elif run.reuse_session:
        raise RuntimeError(
            f"--reuse-session was set but no live tmux session {run.config.session_name!r} exists. "
            "Authenticate one first, e.g.: "
            "py tools/prod_tui/robocop_tmux.py start --passcode <CODE>"
        )
    else:
        run.driver.start_session(passcode=run.passcode)
        run.record("start_session", True, "Remote tmux session started", started, run.capture("start_session"))

    started = time.monotonic()
    create_smoke_sql_file(run)
    run.record("create_smoke_sql_file", True, f"Wrote {run.sql_path}", started)

    started = time.monotonic()
    violations = collect_preconditions(run)
    if violations:
        run.record("preconditions", False, "; ".join(violations), started, run.capture("preconditions_failed"))
        raise RuntimeError("Launch preconditions failed")
    run.record("preconditions", True, "Launch preconditions satisfied", started, run.capture("preconditions"))

    started = time.monotonic()
    screen = open_prefilled_new_job(run)
    run.record("open_prefilled_new_job", True, "Prefilled New Job screen opened", started, screen)

    started = time.monotonic()
    screen = verify_prefilled_form(run)
    run.record("verify_prefilled_form", True, "Smoke form values are visible (source=SqlFile, dest=Table)", started, screen)

    started = time.monotonic()
    screen = preview_and_verify(run)
    run.record("preview_and_verify", True, "Preview contains smoke SQL and table", started, screen)

    if dry_run:
        started = time.monotonic()
        run.driver.send_key("q")
        run.record("dry_run_exit", True, "Stopped before Launch as requested", started, run.capture("dry_run_exit"))
        return

    started = time.monotonic()
    screen = launch_and_confirm(run)
    run.record("launch_and_confirm", True, "Launch confirmed", started, screen)

    started = time.monotonic()
    state = wait_for_job_completion(run)
    if state != "Succeeded":
        run.record("wait_for_job_completion", False, f"Job ended as {state}", started, run.capture("job_failed"))
        raise RuntimeError(f"Smoke job ended as {state}")
    run.record("wait_for_job_completion", True, "Smoke job succeeded", started, run.capture("job_succeeded"))

    started = time.monotonic()
    output = verify_table_exists(run)
    run.record("verify_table_exists", True, "Smoke table exists in Impala", started, output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a controlled production Dispatch smoke job")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--dry-run", action="store_true", help="Fill and preview the form, then exit before Launch")
    parser.add_argument("--json-report", help="Write JSON report to this path")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--skip-level12", action="store_true", help="Skip Level 1/2 prerequisite smoke checks")
    parser.add_argument("--passcode", help="Passcode for SSH authentication")
    parser.add_argument(
        "--reuse-session",
        action="store_true",
        help=(
            "Reuse an already-authenticated tmux session instead of logging in. "
            "Start one first with: py tools/prod_tui/robocop_tmux.py start --passcode <CODE>"
        ),
    )
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
    prereq_results: list[SmokeResult] = []
    config = load_config(args.config)
    driver = TmuxDriver.from_config(config, retries=2)
    run = ControlledRun(config=config, driver=driver, table_name=generate_smoke_table_name(config))
    run.passcode = args.passcode
    run.reuse_session = args.reuse_session
    exit_code = 0
    try:
        if not args.skip_level12:
            prereq_results = run_level_1_and_2(
                config, driver, run.run_timestamp, args.fail_fast,
                passcode=args.passcode, reuse_session=args.reuse_session,
            )
            if any(not result.passed for result in prereq_results):
                exit_code = 1
                raise RuntimeError("Level 1/2 prerequisite checks failed")
        controlled_lifecycle(run, dry_run=args.dry_run)
    except Exception as exc:  # noqa: BLE001
        exit_code = exit_code or 1
        print(f"Controlled run failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    finally:
        cleanup_started = time.monotonic()
        # Remote cleanup runs commands in the pane; only attempt it when the
        # session actually reached a shell. If auth failed (pane stuck at the
        # PASSCODE prompt) there is nothing to clean and run_remote would hang.
        shell_reachable = False
        try:
            shell_reachable = driver.session_exists() and driver.at_shell_prompt()
        except Exception:  # noqa: BLE001
            shell_reachable = False
        if not shell_reachable:
            run.record(
                "cleanup", True,
                "Skipped remote cleanup — no authenticated shell (nothing was created)",
                cleanup_started,
            )
        else:
            try:
                cleanup_smoke_files(run)
                if not args.dry_run:
                    cleanup_smoke_table(run)
                run.record("cleanup", True, "Cleanup attempted for smoke files/table", cleanup_started)
            except Exception as exc:  # noqa: BLE001
                exit_code = 2
                run.record("cleanup", False, f"Cleanup failed: {exc}", cleanup_started)
        try:
            # Leave an operator-owned session alive so they can attach or
            # re-run without burning another single-use passcode.
            if not args.reuse_session:
                driver.stop_session()
        except Exception:
            pass
        report_path = write_json_report(run, prereq_results, started, args.json_report)
        print(f"JSON report: {report_path}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
