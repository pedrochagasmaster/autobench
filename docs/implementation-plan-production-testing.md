# Production Testing Implementation Plan

**Date:** 2026-05-19
**Scope:** End-to-end production validation harness for Dispatch TUI on the Hadoop Edge Node
**Source:** `docs/production_testing.md`

---

## 1. Overview

Dispatch is a Textual TUI that runs on a Hadoop Edge Node over SSH. Local pytest/Textual-pilot tests cover deterministic regression but cannot validate the real production environment: corporate SSH chains, Kerberos authentication, real `/ads_storage/` mounts, `impala-shell` connectivity, and Textual rendering over remote terminals.

This plan delivers a **tmux-based remote harness** (`tools/prod_tui/`) that an operator or agent can use to drive the real TUI over SSH and validate it at three safety levels before any production merge.

---

## 2. Deliverables

| # | Deliverable | Path |
|---|---|---|
| D1 | Remote tmux driver module | `tools/prod_tui/robocop_tmux.py` |
| D2 | Smoke-test runner (Level 1 + 2) | `tools/prod_tui/smoke_test.py` |
| D3 | Controlled job runner (Level 3) | `tools/prod_tui/controlled_job.py` |
| D4 | Safety-policy module | `tools/prod_tui/safety.py` |
| D5 | Configuration file | `tools/prod_tui/config.yaml` |
| D6 | README with operator instructions | `tools/prod_tui/README.md` |

---

## 3. Architecture

```
Local machine / CI agent
  |
  |  SSH (corporate chain)
  v
Edge Node
  |
  +-- tmux session "robocop-prod-test" (120x40)
       |
       +-- Dispatch TUI (real Textual app)
       +-- Real klist, impala-shell, /ads_storage
```

The driver never embeds Dispatch in-process. It shells out over SSH to a persistent tmux session and interacts exclusively through `send-keys` and `capture-pane`. This preserves the exact environment a real user encounters.

---

## 4. Phase 1 — tmux Driver Module (`robocop_tmux.py`)

### 4.1 Public API

```python
class TmuxDriver:
    def __init__(self, host: str, session: str, repo_path: str,
                 width: int = 120, height: int = 40): ...
    def start_session(self) -> None: ...
    def send_keys(self, keys: str, *, literal: bool = False) -> None: ...
    def send_text(self, text: str) -> None: ...
    def capture_screen(self, history_lines: int = 200) -> str: ...
    def attach(self) -> None: ...
    def stop_session(self) -> None: ...
    def wait_for(self, pattern: str, timeout: float = 10.0,
                 poll_interval: float = 0.5) -> str: ...
```

### 4.2 Implementation Tasks

| # | Task | Detail |
|---|---|---|
| 4.2.1 | Create `tools/prod_tui/` directory structure | `__init__.py`, `robocop_tmux.py`, `config.yaml` |
| 4.2.2 | Implement `start_session()` | SSH to host, kill any existing session with the same name, create a new detached tmux session at `width x height`, `cd` to `repo_path`, verify with `tmux has-session` |
| 4.2.3 | Implement `send_keys()` | `ssh $HOST "tmux send-keys -t $SESSION '$keys' Enter"`. When `literal=True`, use `-l` flag (no Enter appended) to send raw characters for TUI navigation (Tab, arrow keys, etc.) |
| 4.2.4 | Implement `send_text()` | Convenience wrapper: `send_keys(text, literal=True)` followed by `send_keys("Enter")` |
| 4.2.5 | Implement `capture_screen()` | `ssh $HOST "tmux capture-pane -t $SESSION -p -S -$history_lines"`. Return the captured text stripped of trailing whitespace |
| 4.2.6 | Implement `wait_for()` | Poll `capture_screen()` every `poll_interval` seconds. Return screen content when `pattern` (regex) matches. Raise `TimeoutError` after `timeout` seconds with last captured screen in the exception message |
| 4.2.7 | Implement `attach()` | `ssh -t $HOST "tmux attach -t $SESSION"` — interactive, blocks until the user detaches |
| 4.2.8 | Implement `stop_session()` | `ssh $HOST "tmux kill-session -t $SESSION"`. Tolerate "session not found" |
| 4.2.9 | SSH command builder helper | Internal `_ssh(cmd, interactive=False)` that constructs the full SSH invocation, handles quoting, and runs via `subprocess.run` (blocking) or `subprocess.Popen` (interactive). Support `SSH_OPTIONS` from config for ProxyJump, identity files, etc. |
| 4.2.10 | Unit tests for command building | Verify that `_ssh()` produces correct shell strings for each operation without actually connecting. Use `unittest.mock` to patch `subprocess.run` |

### 4.3 Configuration (`config.yaml`)

```yaml
host: "your-user@edge-node"
repo_path: "/ads_storage/dispatch"
session_name: "robocop-prod-test"
terminal_width: 120
terminal_height: 40
ssh_options: "-o StrictHostKeyChecking=no"
smoke_query_sql: "SELECT 1 AS smoke_test_value"
scratch_schema: "aa_enc"
table_prefix: "dispatch_smoke"
max_smoke_job_wait_seconds: 120
```

### 4.4 Acceptance Criteria

- [ ] `start_session` + `capture_screen` returns a bash prompt from the Edge Node
- [ ] `send_keys "ls"` + `capture_screen` shows directory listing
- [ ] `wait_for` correctly times out and raises with diagnostic context
- [ ] `stop_session` is idempotent (no error on second call)
- [ ] `attach` opens an interactive terminal the operator can use

---

## 5. Phase 2 — Safety Policy Module (`safety.py`)

### 5.1 Action Classification

```python
class ActionTier(Enum):
    SAFE = "safe"
    CONTROLLED = "controlled"
    BLOCKED = "blocked"

SAFE_ACTIONS: set[str] = {
    "navigate", "preview", "capture", "inspect_logs",
    "inspect_history", "run_help", "compileall", "quit",
    "kinit", "klist", "show_tables", "describe_table",
}

CONTROLLED_ACTIONS: set[str] = {
    "launch_smoke_query",
}

BLOCKED_ACTIONS: set[str] = {
    "drop_table", "run_arbitrary_sql", "modify_scr",
    "delete_files", "launch_unknown_sql",
}
```

### 5.2 Implementation Tasks

| # | Task | Detail |
|---|---|---|
| 5.2.1 | Define `ActionTier` enum and classification sets | Hard-code the three tiers as above |
| 5.2.2 | Implement `classify(action: str) -> ActionTier` | Lookup in sets; default to `BLOCKED` for unknown actions |
| 5.2.3 | Implement `is_safe_table_name(name: str) -> bool` | Must start with the configured `table_prefix` (e.g. `dispatch_smoke_`) |
| 5.2.4 | Implement `is_safe_sql(sql_text: str) -> bool` | Whitelist: must be the exact configured `smoke_query_sql` or match `SELECT ... AS smoke_test_value` pattern. Reject any DDL (`DROP`, `CREATE`, `ALTER`, `INSERT`, `DELETE`, `UPDATE`, `TRUNCATE`) |
| 5.2.5 | Implement `check_launch_preconditions(kerberos_ttl: int | None, running_jobs: int, table_name: str, sql_text: str) -> list[str]` | Returns a list of violation messages. Empty list means all clear. Checks: (a) kerberos_ttl is not None and >= 300, (b) running_jobs < 2, (c) `is_safe_table_name(table_name)`, (d) `is_safe_sql(sql_text)` |
| 5.2.6 | Unit tests for all safety functions | Cover edge cases: empty table name, sql with embedded comments containing DDL, borderline TTL values |

### 5.3 Acceptance Criteria

- [ ] `classify("navigate")` returns `SAFE`
- [ ] `classify("drop_table")` returns `BLOCKED`
- [ ] `classify("unknown_thing")` returns `BLOCKED`
- [ ] `check_launch_preconditions` rejects missing Kerberos, low TTL, non-smoke table names, and unsafe SQL
- [ ] `check_launch_preconditions` passes for the happy path with valid smoke parameters

---

## 6. Phase 3 — Smoke Test Runner (`smoke_test.py`) — Levels 1 & 2

### 6.1 Test Structure

The smoke runner is a sequential script (not pytest) that uses `TmuxDriver` to execute checks and reports pass/fail for each. It is designed to be run by a human operator or a CI agent.

### 6.2 Level 1 — Safe Production Smoke (No Job Launch)

| # | Check | How |
|---|---|---|
| 6.2.1 | SSH connectivity | `start_session()` succeeds |
| 6.2.2 | tmux geometry | `capture_screen()` returns content; verify width/height via `tmux display -p '#{window_width} #{window_height}'` |
| 6.2.3 | Dispatch opens | `send_keys("dispatch")`, `wait_for("RUNNING\|KERBEROS\|Active Jobs", timeout=15)` |
| 6.2.4 | Dashboard renders | Captured screen contains "Active Jobs", "RUNNING", stat cards |
| 6.2.5 | Kerberos status appears | Screen contains "Kerberos:" with a time value or "MISSING" |
| 6.2.6 | Navigation: New Job | `send_keys("n")`, `wait_for("New Job\|Source.*Destination")` |
| 6.2.7 | Navigation: back to dashboard | `send_keys("escape")` or `send_keys("b")`, `wait_for("Active Jobs")` |
| 6.2.8 | SQL browser opens | `send_keys("b")`, `wait_for("Browse Impala")` |
| 6.2.9 | Navigation: back from browser | `send_keys("b")`, `wait_for("Active Jobs")` |
| 6.2.10 | History opens | `send_keys("h")`, `wait_for("History")` |
| 6.2.11 | Navigation: back from history | `send_keys("b")`, `wait_for("Active Jobs")` |
| 6.2.12 | Preview screen opens | Navigate to New Job, `send_keys("p")`, `wait_for("Preview\|SQL Preview")` |
| 6.2.13 | Quit works cleanly | `send_keys("q")`, verify tmux session still alive but Dispatch exited (bash prompt visible) |
| 6.2.14 | `python -m compileall` passes | Before launching Dispatch, run `python -m compileall dispatch scr` and assert exit code 0 in the captured output |

### 6.3 Level 2 — Real Environment Checks (No Job Launch)

| # | Check | How |
|---|---|---|
| 6.3.1 | `install.sh` runs cleanly | `send_keys("./install.sh")` in the repo dir (with `DISPATCH_EMAIL` pre-set), `wait_for("Dispatch installed")` |
| 6.3.2 | `dispatch` shortcut resolves | `send_keys("which dispatch")`, `wait_for(".local/bin/dispatch")` |
| 6.3.3 | `klist` is detected | `send_keys("klist -s && echo KRB_OK")`, `wait_for("KRB_OK")` — or capture the error and report |
| 6.3.4 | `impala-shell` is on PATH | `send_keys("which impala-shell")`, assert output is a valid path |
| 6.3.5 | Python version check | `send_keys("python3.10 --version")`, `wait_for("Python 3.10")` |
| 6.3.6 | CWD captured correctly | Launch Dispatch from a known directory, open New Job, verify the SQL file input reflects that directory |
| 6.3.7 | `/ads_storage/<user>` writable | `send_keys("touch /ads_storage/$USER/.dispatch/.smoke_test && echo WRITE_OK")`, `wait_for("WRITE_OK")` |
| 6.3.8 | Textual renders over SSH | Verify `capture_screen()` contains box-drawing characters and styled text (not garbled escape codes) |
| 6.3.9 | Version file matches | Compare `installed_version` file content against `VERSION` file in the repo |

### 6.4 Implementation Tasks

| # | Task | Detail |
|---|---|---|
| 6.4.1 | Create `smoke_test.py` with CLI entry point | `argparse` with `--config`, `--level` (1, 2, or "all"), `--verbose` flags |
| 6.4.2 | Implement `SmokeResult` dataclass | `name: str`, `passed: bool`, `message: str`, `screen_capture: str` |
| 6.4.3 | Implement Level 1 check functions | One function per check (6.2.1–6.2.14), each returns `SmokeResult` |
| 6.4.4 | Implement Level 2 check functions | One function per check (6.3.1–6.3.9), each returns `SmokeResult` |
| 6.4.5 | Implement result reporter | Print pass/fail summary to stdout. On failure, include the last captured screen for diagnostics. Optionally write a JSON report to `tools/prod_tui/reports/` |
| 6.4.6 | Add `--save-screens` flag | Dump every screen capture to `tools/prod_tui/screens/` with timestamped filenames for post-mortem review |
| 6.4.7 | Handle Dispatch already running | Before each check sequence, ensure a clean state: quit Dispatch if it's running, return to bash prompt |
| 6.4.8 | Handle flaky SSH | Wrap each SSH call in a retry (max 2 retries, 3s backoff) for transient network failures |

### 6.5 Acceptance Criteria

- [ ] `python tools/prod_tui/smoke_test.py --config config.yaml --level 1` runs all Level 1 checks and prints a summary
- [ ] Failing checks include the screen capture in the error output
- [ ] `--level 2` runs Level 2 checks
- [ ] `--level all` runs both levels sequentially
- [ ] All checks are independent (a failure in check N does not prevent check N+1 from running)

---

## 7. Phase 4 — Controlled Job Runner (`controlled_job.py`) — Level 3

### 7.1 Preconditions (All Must Pass)

Before pressing Launch, the runner must programmatically verify:

1. Kerberos TTL >= 5 minutes (parse from TUI header or `klist` output)
2. Running jobs < 2 (parse from dashboard stat card)
3. Target schema is the configured `scratch_schema`
4. Table name starts with `dispatch_smoke_${USER}_YYYYMMDD_HHMMSS`
5. SQL file contains exactly the configured `smoke_query_sql`
6. Safety module `check_launch_preconditions()` returns no violations

### 7.2 Job Lifecycle

```
1. Start tmux session
2. Run Level 1 + 2 smoke (abort if any fail)
3. Create a temp SQL file on the Edge Node:
     echo "SELECT 1 AS smoke_test_value" > /tmp/dispatch_smoke_test.sql
4. cd to /tmp (so CSV lands there)
5. Launch Dispatch
6. Navigate to New Job
7. Set Source = SqlFile
8. Set Destination = Table
9. Fill form:
     SQL File = /tmp/dispatch_smoke_test.sql
     Schema = <scratch_schema>
     Table = dispatch_smoke_<user>_<timestamp>
     Email = <configured email>
10. Press Preview, verify SQL looks correct
11. Press Back
12. Press Launch
13. Confirm the launch dialog
14. Wait for job to appear in dashboard as Running
15. Poll dashboard until job reaches Succeeded or Failed (timeout: max_smoke_job_wait_seconds)
16. If Succeeded:
      a. Verify table exists via Browser screen (SHOW TABLES, filter dispatch_smoke_*)
      b. Clean up: DROP the smoke table via Browser screen
      c. Remove /tmp/dispatch_smoke_test.sql
17. If Failed:
      a. Capture job detail screen (logs)
      b. Report failure with full log capture
18. Quit Dispatch
19. Stop tmux session
```

### 7.3 Implementation Tasks

| # | Task | Detail |
|---|---|---|
| 7.3.1 | Implement `generate_smoke_table_name()` | `dispatch_smoke_{user}_{YYYYMMDD}_{HHMMSS}` using `config.current_user()` and UTC time |
| 7.3.2 | Implement `create_smoke_sql_file()` | Write the smoke SQL to a temp file on the Edge Node via SSH |
| 7.3.3 | Implement `navigate_to_new_job()` | From dashboard, press `n`, wait for New Job screen |
| 7.3.4 | Implement `fill_job_form()` | Use Tab navigation and text input to fill each form field. Clear existing values first with Ctrl+A then type new value. Verify each field after entry via screen capture |
| 7.3.5 | Implement `preview_and_verify()` | Press `p`, capture preview screen, verify it contains the expected SQL and table name, press `b` to return |
| 7.3.6 | Implement `launch_and_confirm()` | Press `l`, wait for confirmation dialog, press `y` or Enter to confirm. Verify "Launched Job" message appears |
| 7.3.7 | Implement `wait_for_job_completion()` | Return to dashboard, poll `capture_screen()` every 5s. Parse job state from the active table. Timeout after `max_smoke_job_wait_seconds`. Return final state |
| 7.3.8 | Implement `verify_table_exists()` | Press `b` for Browser, enter schema and filter `dispatch_smoke_*`, press SHOW TABLES, verify smoke table appears in the list |
| 7.3.9 | Implement `cleanup_smoke_table()` | In Browser, select the smoke table, press `d` for DROP, type the full table name in the confirmation dialog, confirm. Verify drop succeeded |
| 7.3.10 | Implement `cleanup_smoke_files()` | Remove the temp SQL file on the Edge Node |
| 7.3.11 | Orchestrate the full lifecycle | Main function that chains steps 1–19 with proper error handling: always attempt cleanup even on failure |
| 7.3.12 | Add `--dry-run` flag | Run everything up to (but not including) Launch. Verify form is correctly filled and preview is correct, then quit without launching |

### 7.4 TUI Navigation Helpers

The hardest part of Level 3 is reliably filling form fields in the Textual TUI via tmux keystrokes. Implement these helpers:

| Helper | Keys | Purpose |
|---|---|---|
| `clear_input()` | `Home`, `Shift+End`, `Delete` | Clear current input field |
| `type_into_field(text)` | `clear_input()` + literal text | Replace field content |
| `tab_to_field(n)` | `Tab` x n | Navigate to the nth form field |
| `select_radio(group, option)` | Arrow keys within radio set | Select a radio button option |
| `press_button(label)` | Navigate to button area, Tab to button, Enter | Activate a specific button |
| `verify_field_value(expected)` | Capture screen, parse field region | Assert a field contains the expected value |

### 7.5 Acceptance Criteria

- [ ] `--dry-run` fills the form correctly and exits without launching
- [ ] Full run creates a job, waits for completion, verifies the table, and cleans up
- [ ] Cleanup always runs (even on mid-test failure)
- [ ] A clear pass/fail report is produced with timing information
- [ ] Screen captures are saved at each major step for post-mortem review

---

## 8. Phase 5 — CLI Wrapper and Operator UX

### 8.1 Unified CLI

```bash
python tools/prod_tui/robocop_tmux.py start
python tools/prod_tui/robocop_tmux.py send "dispatch"
python tools/prod_tui/robocop_tmux.py keys tab enter
python tools/prod_tui/robocop_tmux.py capture
python tools/prod_tui/robocop_tmux.py attach
python tools/prod_tui/robocop_tmux.py stop
```

### 8.2 Implementation Tasks

| # | Task | Detail |
|---|---|---|
| 8.2.1 | Add `argparse` subcommands to `robocop_tmux.py` | `start`, `send`, `keys`, `capture`, `attach`, `stop` |
| 8.2.2 | `start` subcommand | Calls `TmuxDriver.start_session()`, prints session info |
| 8.2.3 | `send` subcommand | Takes a string argument, calls `send_keys()` with Enter |
| 8.2.4 | `keys` subcommand | Takes space-separated key names (tab, enter, escape, up, down, left, right, ctrl-a, ctrl-c), sends each as a tmux key |
| 8.2.5 | `capture` subcommand | Calls `capture_screen()`, prints to stdout. `--raw` flag disables any post-processing |
| 8.2.6 | `attach` subcommand | Calls `attach()` — hands terminal over to the operator |
| 8.2.7 | `stop` subcommand | Calls `stop_session()` |
| 8.2.8 | All subcommands read `--config` | Default `tools/prod_tui/config.yaml` |

### 8.3 Acceptance Criteria

- [ ] An operator can manually drive a Dispatch session using only the CLI subcommands
- [ ] `capture` output is clean and readable (no encoding artifacts)
- [ ] `attach` works and the operator can interact with the TUI directly

---

## 9. Phase 6 — Agent Loop Integration

### 9.1 The Reasoning Loop

When an AI agent uses the harness, it follows this loop:

```
1. capture screen
2. reason about current UI state
3. decide next action (classify via safety module)
4. if action is BLOCKED → refuse and explain
5. if action is CONTROLLED → verify preconditions
6. send key/action
7. capture screen again
8. assert expected visible state
9. repeat
```

### 9.2 Implementation Tasks

| # | Task | Detail |
|---|---|---|
| 9.2.1 | Create `agent_loop.py` | Defines `AgentStep` protocol: `observe(screen) -> Action`, `verify(screen) -> bool` |
| 9.2.2 | Implement screen parser | Extract structured data from tmux captures: current screen name (Dashboard/New Job/Browser/History/Preview/Confirm), Kerberos TTL, running job count, form field values, table contents |
| 9.2.3 | Implement `ScreenState` dataclass | `screen_name: str`, `kerberos_ttl: int | None`, `running_jobs: int`, `active_jobs: list[dict]`, `form_fields: dict[str, str]`, `raw_text: str` |
| 9.2.4 | Screen detection heuristics | Match known UI patterns: "Active Jobs" → Dashboard, "New Job" → NewJob, "Browse Impala" → Browser, "History" → History, "SQL Preview" → Preview, confirm dialog border → Confirm |
| 9.2.5 | Safety gate in the loop | Every action passes through `safety.classify()`. BLOCKED actions raise `BlockedActionError`. CONTROLLED actions call `check_launch_preconditions()` first |
| 9.2.6 | Logging and audit trail | Every step logs: timestamp, screen state summary, chosen action, safety classification, result. Write to `tools/prod_tui/logs/agent_run_<timestamp>.jsonl` |

### 9.3 Acceptance Criteria

- [ ] Agent loop can navigate from Dashboard → New Job → Preview → Back → Quit without human intervention
- [ ] BLOCKED actions are refused with clear error messages
- [ ] Every step is logged in the audit trail
- [ ] Screen parser correctly identifies all six screen types

---

## 10. Phase 7 — Reporting and CI Integration

### 10.1 Report Format

```json
{
  "timestamp": "2026-05-19T02:30:00Z",
  "host": "user@edge-node",
  "levels_run": [1, 2, 3],
  "duration_seconds": 87,
  "results": [
    {"name": "ssh_connectivity", "level": 1, "passed": true, "message": "OK", "elapsed_ms": 1200},
    {"name": "dispatch_opens", "level": 1, "passed": true, "message": "Dashboard visible in 3.2s", "elapsed_ms": 3200}
  ],
  "summary": {"total": 23, "passed": 23, "failed": 0},
  "screen_captures": "tools/prod_tui/screens/run_20260519_023000/"
}
```

### 10.2 Implementation Tasks

| # | Task | Detail |
|---|---|---|
| 10.2.1 | Implement JSON report writer | Write structured report after each run |
| 10.2.2 | Implement summary printer | Human-readable pass/fail table to stdout |
| 10.2.3 | Add `--json-report` flag to smoke and controlled runners | Specify output path for the JSON report |
| 10.2.4 | Add `--fail-fast` flag | Stop on first failure instead of running all checks |
| 10.2.5 | Exit code semantics | Exit 0 if all checks pass, exit 1 if any check fails, exit 2 for harness errors (SSH failure, tmux failure) |
| 10.2.6 | `.gitignore` entries | Ignore `tools/prod_tui/screens/`, `tools/prod_tui/reports/`, `tools/prod_tui/logs/` |

### 10.3 Acceptance Criteria

- [ ] JSON report is written after every run
- [ ] Exit codes are correct for pass/fail/error scenarios
- [ ] Screen captures directory is organized by run timestamp

---

## 11. File Tree (Final State)

```
tools/prod_tui/
  __init__.py
  robocop_tmux.py        # D1: tmux driver + CLI subcommands
  safety.py              # D4: action classification and precondition checks
  smoke_test.py          # D2: Level 1 + 2 smoke runner
  controlled_job.py      # D3: Level 3 controlled job runner
  agent_loop.py          # Agent reasoning loop and screen parser
  config.yaml            # D5: default configuration
  README.md              # D6: operator instructions
  screens/               # .gitignored — screen captures
  reports/               # .gitignored — JSON reports
  logs/                  # .gitignored — agent audit logs
  tests/
    test_safety.py       # Unit tests for safety module
    test_tmux_commands.py # Unit tests for SSH command construction
    test_screen_parser.py # Unit tests for screen state extraction
```

---

## 12. Dependency and Environment Requirements

| Requirement | Where | Notes |
|---|---|---|
| Python >= 3.10 | Local + Edge Node | Already required by Dispatch |
| `tmux` | Edge Node | Must be installed; check with `which tmux` |
| `ssh` | Local machine | Standard OpenSSH client |
| `PyYAML` | Local machine (dev dep) | For config parsing; add to a `tools/prod_tui/requirements.txt` |
| SSH key auth | Local → Edge Node | Password auth not supported by the harness (no interactive stdin) |
| Kerberos ticket | Edge Node | Required for Level 2+ checks; `kinit` must have been run |

No new dependencies are added to the main Dispatch `requirements.txt`. The harness is a standalone tool.

---

## 13. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| tmux not installed on Edge Node | Harness cannot run | Level 2 check 6.3.1 (`install.sh`) can install tmux as a prerequisite, or the README documents the manual install step |
| SSH ProxyJump chain adds latency | `wait_for` timeouts too aggressive | All timeouts are configurable in `config.yaml`; defaults are generous (10–15s for UI, 120s for job completion) |
| Textual escape sequences garble tmux capture | Screen parser fails | `capture-pane` with `-p` strips most escape codes; parser should strip remaining ANSI sequences with a regex filter |
| Controlled job leaves orphaned table on failure | Schema pollution | Cleanup runs in a `finally` block; additionally, smoke tables use a timestamped naming convention so old orphans are identifiable and can be batch-cleaned |
| Corporate SSH requires 2FA/MFA | Automated runs blocked | Document that the harness requires key-based auth or a pre-authenticated SSH agent; 2FA must be satisfied before starting |
| Concurrent operators run smoke tests | Table name collision | Table name includes `$USER` and a seconds-precision timestamp, making collisions practically impossible |

---

## 14. Implementation Order and Estimated Effort

| Phase | Depends On | Estimated Effort | Priority |
|---|---|---|---|
| Phase 1 — tmux driver | Nothing | 4–6 hours | P0 (everything depends on this) |
| Phase 2 — Safety module | Nothing | 2–3 hours | P0 (gating logic for Phase 4) |
| Phase 3 — Smoke tests (L1+L2) | Phase 1 | 4–6 hours | P0 (pre-merge requirement) |
| Phase 4 — Controlled job (L3) | Phases 1, 2, 3 | 6–8 hours | P1 (validates real Impala path) |
| Phase 5 — CLI wrapper | Phase 1 | 2–3 hours | P1 (operator UX) |
| Phase 6 — Agent loop | Phases 1, 2 | 4–6 hours | P2 (agent automation) |
| Phase 7 — Reporting/CI | Phases 3, 4 | 2–3 hours | P2 (CI integration) |

**Total estimated effort: 24–35 hours**

---

## 15. Definition of Done

The production testing harness is complete when:

1. An operator can run `python tools/prod_tui/smoke_test.py --level all` against the real Edge Node and get a clean pass/fail report.
2. An operator can run `python tools/prod_tui/controlled_job.py --dry-run` to verify form-filling without launching.
3. An operator can run `python tools/prod_tui/controlled_job.py` to execute a real smoke query and verify the full lifecycle.
4. All safety checks prevent BLOCKED actions from executing.
5. Every run produces a structured JSON report and saved screen captures.
6. The `tools/prod_tui/README.md` is sufficient for a new team member to run the harness without additional guidance.
7. Unit tests for the safety module and command builder pass in CI without SSH access.
