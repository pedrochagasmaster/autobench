# Dispatch — Implementation Plan v2

**Date:** 2026-05-15
**Supersedes:** `docs/plan.md` (v1, design-phase specification)
**Status:** Active

This document is a ground-truth implementation plan derived from auditing
every file in the repository. It catalogues what has been built, what is
broken or incomplete, and what remains to be done — with per-task
specifications detailed enough to implement without ambiguity.

Prerequisite reading: [`CONTEXT.md`](../CONTEXT.md), [`docs/adr/`](./adr/),
[`docs/plan.md`](./plan.md) (original design spec),
[`docs/ui-ux-report-2026-05-10.md`](./ui-ux-report-2026-05-10.md).

---

## 1. Current State Assessment

### 1.1 Milestone Completion Matrix

The original plan defined 11 PRs. Git history (`git log --oneline`) shows
commits tagged `[M1]` through `[M11]`. The following table records actual
completion status based on code inspection, not just commit presence.

| PR | Description | Commits | Code Present | Fully Functional | Notes |
|----|-------------|---------|--------------|------------------|-------|
| 1 | Mocks substrate | `758a88f`, `66137a6`, `eff1056`, `7633a42`, `6df3ebd` | Yes | **Mostly** | All 6 scenarios exist. SMTP catcher works. `impala-shell` mock handles `SHOW TABLES`, `DESCRIBE`, `DROP`, plus all scenarios. Missing: no automated scenario matrix test (the plan required a 6×3 validation table). |
| 2 | Package skeleton | `2d5d3ea` (merge) | Yes | **Yes** | `pyproject.toml`, `requirements.txt`, `vendor/` (empty — wheels not committed), `dispatch/` package all present. `python -m dispatch` launches the Textual app. |
| 3 | Manifest + runner | `19e3f7f`, `726ec18` | Yes | **Yes** | `manifest.py` has full schema, validation, `create_job`, `build_orchestrator_calls`. Runner has signal handling, SIGTERM→cancel, SIGHUP/SIGINT ignored. Atomic manifest writes via `.tmp` rename. |
| 4 | New Job wizard | `bac52e1`, `b607a34` | Yes | **Partial** | Source × Destination validation works. Kerberos pre-flight works. **Critical gap:** Source and Destination are free-text `Input` widgets, not constrained `Select`/`RadioButton`. Date defaults are hardcoded `2026-01-01`/`2026-01-31`. SQL file read errors crash the wizard (`_read_sql` has no try/except in `action_preview` or `action_launch`). |
| 5 | Dashboard | `a0b95d1`, `456e583` | Yes | **Partial** | Active/recent tables render. 2s refresh interval works. **Critical gap:** Job selection is via manual ID text input, not selectable table rows. `v` and `a` keybindings both map to `view_logs` but labels suggest distinct actions. |
| 6 | History view | Present | Yes | **Partial** | 7-day threshold in `jobs.py` (`ACTIVE_WINDOW = timedelta(days=7)`) correctly partitions active vs history. Search by table/date works. **Gap:** No column headers in output. Job selection is manual ID input. |
| 7 | Browser | `5511819` | Yes | **Partial** | `SHOW TABLES`, `DESCRIBE`, `DROP` all work via `impala.py`. **Gap:** Table selection is manual text input. No lazy `SHOW TABLE STATS` (plan §8). No confirmation dialog before `DROP`. |
| 8 | SQL preview + monthly preview | Present | Yes | **Partial** | `sql.py` has `table_wrapper` and `monthly_preview`. `PreviewScreen` exists but is minimal (plain `Static` text, no syntax highlighting, no scroll). |
| 9 | Install + VERSION | `1f0c89a` | Yes | **Yes** | `install.sh` is idempotent, creates venv, handles lockfile, preserves config on re-run. `VERSION` file exists. |
| 10 | scr/ de-duplication | `f01f3dd`, `04c45e6`, `70feb17` | Yes | **Yes** | `_common.py` has `classificar_erro_impala`, `send_email`, `cycle_through_pools`. Dead `--download` path removed. All three orchestrators import from `_common`. |
| 11 | Legacy delete + README | `c4d010d` | Yes | **Yes** | `run_query.ps1` and `run_query_engine.bat` are gone. README describes Dispatch. |

### 1.2 Gap Summary

Derived from the milestone matrix and the UX report:

| ID | Severity | Area | Description |
|----|----------|------|-------------|
| G-01 | **P0** | New Job | Source/Destination are free-text inputs allowing typos and unsupported values |
| G-02 | **P0** | New Job | `_read_sql()` raises unhandled `OSError` in `action_preview` and `action_launch` |
| G-03 | **P0** | Navigation | Inconsistent back keybinding: `Esc` in New Job, `b` in History/Detail/Browser |
| G-04 | **P1** | Dashboard | Job selection requires manual ID typing instead of selectable rows |
| G-05 | **P1** | History | Same manual-ID problem; also missing column headers |
| G-06 | **P1** | Browser | Table selection is manual text input; no DROP confirmation |
| G-07 | **P1** | Dashboard | `v` (view) and `a` (attach) both call `view_logs` — semantics are indistinguishable |
| G-08 | **P1** | App shell | Kerberos TTL not shown in persistent header (only checked on New Job mount) |
| G-09 | **P1** | App shell | Version-mismatch warning only in startup `Vertical`, not a persistent banner |
| G-10 | **P2** | New Job | Hardcoded date defaults (`2026-01-01`/`2026-01-31`) |
| G-11 | **P2** | Feedback | Single `Static` for warnings — no severity tiers, no color coding |
| G-12 | **P2** | Dashboard | No empty-state help text when zero jobs exist |
| G-13 | **P2** | Preview | Plain text only; no scrolling, no syntax highlighting |
| G-14 | **P2** | Terminal | No minimum terminal size detection or responsive degradation |
| G-15 | **P2** | Logging | No `dispatch.log` — plan §8 says startup failures should log to `~/.dispatch/dispatch.log` |
| G-16 | **P2** | Testing | Only one test (`test_ui_snapshots.py`); no unit tests for `manifest`, `sql`, `jobs`, `kerberos`, `runner` |
| G-17 | **P2** | Browser | No lazy `SHOW TABLE STATS` for Size/Rows columns (plan §8 wireframe) |
| G-18 | **P2** | New Job | `ExistingTable` input overlaps with schema/table inputs — UX is confusing |

### 1.3 Architecture Health

**Correct by design:**
- Runner is the sole orchestrator parent (ADR-0001 enforced).
- `process.py` is the single subprocess gateway (no other module calls `subprocess`).
- CSV output goes to launch-time CWD, uncompressed (ADR-0003).
- `Table+Csv` is decomposed into two calls, not `--download` (ADR-0003).
- Mock layer fakes all external systems (ADR-0004).
- `scr/` modifications follow ADR-0005: `_common.py` exists, `MAILHOST`
  externalised, dead code removed.

**Architectural debt:**
- `dispatch/app.py` `on_mount` pushes `DashboardScreen` immediately, but
  the startup `Vertical` with version info is never seen (it's behind the
  pushed screen). The version banner logic is dead code in practice.
- `runner.py` uses module-level `global` for `CURRENT_PROC`, `LOG`,
  `MANIFEST_PATH`. This works but is fragile for future testing.

---

## 2. Implementation Phases

Work is organised into three phases: **Stabilise** (fix broken/dangerous
things), **Complete** (fill gaps to match v1.0 spec), and **Harden** (tests,
logging, polish). Each phase contains numbered tasks with full specifications.

---

## Phase A — Stabilise (P0 fixes)

These must land before any new feature work. Each is a single PR.

### A-1: Replace free-text Source/Destination with constrained widgets

**Gap:** G-01
**File:** `dispatch/screens/new_job.py`

**Current behaviour:** Two `Input` widgets (`#source`, `#destination`) accept
arbitrary text. Validation catches illegal cells only at launch time, after the
user has filled an entire form.

**Target behaviour:** Replace with Textual `RadioSet` (or `RadioButton` group)
widgets. Source shows three options: `SqlFile`, `SqlTemplate`,
`ExistingTable`. Destination shows three options: `Table`, `Csv`, `Table+Csv`.
Illegal combinations are **dynamically disabled** (greyed out, not clickable)
when the user changes Source.

**Specification:**

1. Add `from textual.widgets import RadioButton, RadioSet` to imports.

2. Replace the two `Input` widgets in `compose()` with:
   ```python
   with RadioSet(id="source"):
       yield RadioButton("SqlFile", value=True, id="src-sqlfile")
       yield RadioButton("SqlTemplate", id="src-sqltemplate")
       yield RadioButton("ExistingTable", id="src-existingtable")
   with RadioSet(id="destination"):
       yield RadioButton("Table", id="dst-table")
       yield RadioButton("Csv", value=True, id="dst-csv")
       yield RadioButton("Table+Csv", id="dst-table-csv")
   ```

3. Add a `on_radio_set_changed` handler that:
   - Reads the selected Source.
   - For each Destination radio button, sets `disabled = True` if that
     `(source, destination)` pair is not in `manifest.LEGAL_CELLS`.
   - Also conditionally shows/hides fields:
     - `#schema`, `#table-name`: visible for `Table` and `Table+Csv`
       destinations, and for `SqlTemplate` source.
     - `#existing-table`: visible only when source is `ExistingTable`.
     - `#start-date`, `#end-date`: visible only when source is `SqlTemplate`.
     - `#email`, `#subject`: always visible.
     - `#sql-file`: visible when source is `SqlFile` or `SqlTemplate`.

4. Update `_input_value` helper and all call sites (`_validate`,
   `_source_destination`, `_params`, `action_preview`) to read from
   `RadioSet.pressed_button.id` instead of `Input.value`.

5. Auto-detection on mount: when `_detect_sql` runs and finds `SqlTemplate`,
   programmatically press the `SqlTemplate` radio button and let the
   `on_radio_set_changed` handler cascade the disabling.

**Acceptance criteria:**
- No free-text typing for Source or Destination anywhere in the wizard.
- Selecting `SqlTemplate` source auto-disables `Csv` and `Table+Csv`
  destination buttons.
- Selecting `ExistingTable` source auto-disables `Table` and `Table+Csv`.
- The `#existing-table` input only appears when `ExistingTable` is selected.
- Date range inputs only appear when `SqlTemplate` is selected.

---

### A-2: Safe SQL file reads with actionable error messages

**Gap:** G-02
**Files:** `dispatch/screens/new_job.py`

**Current behaviour:** `_read_sql()` calls `Path.read_text()` with no
try/except. If the file does not exist or is unreadable, `action_preview` and
`action_launch` raise an unhandled `OSError` that crashes the screen.

**Target behaviour:** All paths that call `_read_sql()` catch `OSError` and
display an actionable error in the `#warning` Static widget.

**Specification:**

1. Wrap `_read_sql` to return `str | None`:
   ```python
   def _read_sql(self) -> str | None:
       sql_path = Path(self._input_value("sql-file"))
       try:
           return sql_path.read_text(encoding="utf-8")
       except OSError as exc:
           self.query_one("#warning", Static).update(
               f"Cannot read SQL file: {sql_path}\n{exc}"
           )
           return None
   ```

2. Update every call site:
   - `_detect_sql`: already has a bare `except OSError: return` — keep it,
     but change to call the new `_read_sql` and check for `None`.
   - `_validate`: call `_read_sql()`; if `None`, return the error string
     `"SQL file is unreadable"`.
   - `action_preview`: call `_read_sql()`; if `None`, return early (don't
     push `PreviewScreen`).
   - `action_launch`: already goes through `_validate`, but also calls
     `_read_sql` independently for `create_job`; guard that too.

3. When source is `ExistingTable`, `_read_sql` is not needed — skip the
   read entirely.

**Acceptance criteria:**
- Entering a non-existent file path and pressing Preview shows
  `"Cannot read SQL file: /path/to/missing.sql\n[Errno 2] ..."` in the
  warning area, not a crash.
- Entering a non-existent file path and pressing Launch shows validation
  error, not a crash.
- Normal operation (valid file) is unchanged.

---

### A-3: Normalise back navigation across all screens

**Gap:** G-03
**Files:** `dispatch/screens/new_job.py`, `dispatch/screens/history.py`,
`dispatch/screens/job_detail.py`, `dispatch/screens/browser.py`,
`dispatch/screens/preview.py`

**Current behaviour:**
- New Job: `Esc` → back
- History: `b` → back
- Job Detail: `b` → back
- Browser: `b` → back
- Preview: `Esc` or `b` → back

**Target behaviour:** All non-root screens accept **both** `Esc` and `b` for
back. `Esc` is the universal Textual convention; `b` is the documented
shortcut in the dashboard footer.

**Specification:**

Add the missing binding to each screen's `BINDINGS` list:

| Screen | Has `escape` | Has `b` | Action |
|--------|-------------|---------|--------|
| `NewJobScreen` | Yes | No | Add `("b", "app.pop_screen", "Back")` |
| `HistoryScreen` | No | Yes | Add `("escape", "app.pop_screen", "Back")` |
| `JobDetailScreen` | No | Yes | Add `("escape", "app.pop_screen", "Back")` |
| `BrowserScreen` | No | Yes | Add `("escape", "app.pop_screen", "Back")` |
| `PreviewScreen` | Yes | Yes | Already complete |

Note: `NewJobScreen` also binds `e` for edit and `l` for launch, so adding
`b` does not conflict (no field starts with `b`).

**Acceptance criteria:**
- Every non-Dashboard screen can be dismissed with either `Esc` or `b`.
- No keybinding conflicts introduced.

---

## Phase B — Complete (fill v1.0 spec gaps)

These bring the implementation to parity with the original plan and the UX
report's P1 recommendations.

### B-1: Selectable job rows in Dashboard

**Gap:** G-04, G-07, G-12
**File:** `dispatch/screens/dashboard.py`

**Current behaviour:** Jobs render as plain text inside a `Static` widget.
The user must manually type a job ID into an `Input` to attach/cancel.

**Target behaviour:** Replace the two `Static` tables with Textual
`DataTable` widgets. Rows are selectable via arrow keys. The selected row's
job ID drives Attach, Cancel, and View Logs actions. Remove the manual
`#job-id` Input.

**Specification:**

1. Replace imports: add `from textual.widgets import DataTable`.

2. In `compose()`:
   - Replace `Static("", id="active")` with a `DataTable` with columns:
     `ID`, `Source`, `Destination`, `State`, `Elapsed`.
   - Replace `Static("", id="recent")` with a second `DataTable`.
   - Remove `Input(placeholder="Job id ...", id="job-id")`.

3. `refresh_jobs()`:
   - Clear and repopulate the `DataTable` rows on each 2s tick.
   - For "Elapsed", compute `datetime.now(utc) - started_at` for Running
     jobs, or `finished_at - started_at` for terminal jobs.

4. `_selected_job_id()`:
   - Read from the currently-focused `DataTable`'s selected row, first column.
   - If no row is selected, return `None` and show a status message.

5. Resolve `v`/`a` ambiguity (G-07):
   - Remove the `a` binding entirely (it was identical to `v`).
   - Keep `v` as "View Logs / Attach" — one action, one label.
   - Rename the button from `"View Logs"` to `"View / Attach"`.

6. Empty-state text (G-12):
   - When the Active table has zero rows, add a single row spanning all
     columns: `"No active Jobs — press N to create one"`.
   - When the Recent table has zero rows: `"No recently finished Jobs"`.

**Acceptance criteria:**
- Arrow keys move between job rows.
- Enter or `v` on a selected row opens `JobDetailScreen` for that job.
- `c` on a selected row opens `JobDetailScreen` with `cancel_on_mount=True`.
- No `Input` widget for job ID exists anywhere on the Dashboard.
- Empty tables show helpful guidance text.

---

### B-2: Selectable rows in History screen

**Gap:** G-05
**File:** `dispatch/screens/history.py`

**Current behaviour:** Same plain-text `Static` + manual `Input` pattern.

**Target behaviour:** `DataTable` with columns: `ID`, `Table`, `State`,
`Finished At`. Selectable rows. Search input filters rows live.

**Specification:**

1. Replace `Static("", id="history-table")` with `DataTable`.
2. Replace `Input(placeholder="Job id to view", id="job-id")` — remove it.
3. `refresh_history()` clears and repopulates the `DataTable`, applying the
   search filter from `#search`.
4. `action_view_logs()` reads the selected row's ID from the `DataTable`.
5. Add column headers: `ID | Table | State | Finished`.

**Acceptance criteria:**
- Column headers are always visible.
- Typing in search filters rows in real time.
- Enter on a selected row opens `JobDetailScreen`.
- No manual job-ID input widget.

---

### B-3: Selectable rows in Browser + DROP confirmation

**Gap:** G-06
**File:** `dispatch/screens/browser.py`

**Current behaviour:** `SHOW TABLES` output is dumped into a `Static`.
Table name for `DESCRIBE` / `DROP` must be typed manually. `DROP` has no
confirmation.

**Target behaviour:**
- `SHOW TABLES` populates a `DataTable` with one column: `Table Name`.
- Selecting a row populates the `#table` input automatically.
- `DROP` shows a confirmation dialog before executing.

**Specification:**

1. Replace `Static("", id="results")` with a `DataTable` (id=`"tables"`)
   for the table list, plus a separate `Static` (id=`"describe-output"`)
   for `DESCRIBE` results.

2. `action_show_tables()` populates the `DataTable`.

3. Add `on_data_table_row_selected` handler: sets `#table` input value to
   `schema.selected_table_name`.

4. `action_drop()`:
   - Before executing, push a small confirmation screen or use
     `self.app.push_screen` with a yes/no dialog:
     ```
     Drop aa_enc.my_table? This cannot be undone. [Y/N]
     ```
   - Only proceed on explicit `Y`.

**Acceptance criteria:**
- After `SHOW TABLES`, arrow keys select a table.
- `DESCRIBE` on a selected row shows column metadata.
- `DROP` requires explicit confirmation.
- A typo in the table name cannot accidentally drop a different table.

---

### B-4: Persistent Kerberos TTL in app header

**Gap:** G-08
**File:** `dispatch/app.py`, new file `dispatch/widgets/kerberos_indicator.py`
(or inline in `app.py`)

**Current behaviour:** Kerberos TTL is only checked when `NewJobScreen`
mounts. The app header shows Textual's default clock.

**Target behaviour:** A persistent widget in the header area shows
`Kerberos: 7h 32m` (or `Kerberos: MISSING`) and refreshes every 60 seconds.

**Specification:**

1. Create a small reactive widget:
   ```python
   class KerberosIndicator(Static):
       ttl_seconds: reactive[int | None] = reactive(None)

       def render(self) -> str:
           if self.ttl_seconds is None:
               return "Kerberos: MISSING"
           hours, remainder = divmod(self.ttl_seconds, 3600)
           minutes = remainder // 60
           return f"Kerberos: {hours}h {minutes:02d}m"
   ```

2. Mount it in `DispatchApp.compose()` — either as a subtitle in the
   `Header`, or as a separate `Static` right-aligned below the header.

3. In `DispatchApp.on_mount()`, start a 60-second timer that calls
   `kerberos.ticket_ttl_seconds()` and updates the widget.

4. Expose the indicator via `self.app.query_one(KerberosIndicator)` so
   screens like `NewJobScreen` can also force a refresh after `kinit`.

**Acceptance criteria:**
- Kerberos TTL is visible on every screen without navigating.
- The value refreshes automatically every 60 seconds.
- After `kinit` in the New Job screen, the header updates immediately.

---

### B-5: Persistent version-mismatch warning banner

**Gap:** G-09
**File:** `dispatch/app.py`

**Current behaviour:** `_version_banner()` renders in the startup `Vertical`,
but `on_mount` immediately pushes `DashboardScreen` over it, making the
banner invisible.

**Target behaviour:** If `installed_version != __version__`, a persistent
`Static` banner with warning styling appears at the top of every screen.

**Specification:**

1. In `DispatchApp.compose()`, yield a conditionally-visible warning
   `Static` with `id="version-warning"` **before** `Header`, styled with
   `background: $warning; color: $text;`.

2. In `on_mount()`, check the version. If mismatch, make `#version-warning`
   visible and set its text. If match, hide it (`display: none`).

3. Remove the startup `Vertical` (id=`"startup"`). It is never visible and
   its code is dead. The `launch_cwd` and version info can be shown in the
   Dashboard header or footer instead.

**Acceptance criteria:**
- When `installed_version` differs from `__version__`, a yellow/orange
  banner is visible on every screen.
- When versions match, no banner is shown.
- The dead startup `Vertical` is removed.

---

### B-6: Dynamic date defaults and conditional field visibility

**Gap:** G-10, G-18
**File:** `dispatch/screens/new_job.py`

**Current behaviour:** Start date defaults to `2026-01-01`, end date to
`2026-01-31`. All fields are always visible regardless of Source/Destination
selection, including `#existing-table` which overlaps semantically with
`#schema`/`#table-name`.

**Target behaviour:**
- Date defaults are context-aware: start = first day of current month,
  end = last day of current month.
- Fields are shown/hidden based on Source/Destination selection (ties into
  A-1's `on_radio_set_changed`).

**Specification:**

1. Replace hardcoded dates:
   ```python
   from datetime import date
   import calendar

   today = date.today()
   first_of_month = today.replace(day=1)
   last_of_month = today.replace(day=calendar.monthrange(today.year, today.month)[1])
   ```
   Use these as default values for `#start-date` and `#end-date`.

2. Field visibility rules (driven by `on_radio_set_changed` from A-1):

   | Field | Visible when |
   |-------|-------------|
   | `#sql-file` | Source is `SqlFile` or `SqlTemplate` |
   | `#existing-table` | Source is `ExistingTable` |
   | `#schema` | Destination contains `Table` (i.e., `Table` or `Table+Csv`), or Source is `SqlTemplate` |
   | `#table-name` | Same as `#schema` |
   | `#start-date` | Source is `SqlTemplate` |
   | `#end-date` | Source is `SqlTemplate` |
   | `#email` | Always |
   | `#subject` | Always |

3. Use Textual's `widget.display = True/False` or `add_class("hidden")`
   with CSS rule `.hidden { display: none; }`.

**Acceptance criteria:**
- Opening New Job in May 2026 shows `2026-05-01` and `2026-05-31`.
- Switching Source to `ExistingTable` hides SQL file, shows existing table
  input, hides date range, hides schema/table (unless Destination is Table).
- Switching Source to `SqlTemplate` shows date range, hides existing table.
- No irrelevant fields clutter the form.

---

### B-7: Feedback severity tiers and event trail

**Gap:** G-11
**Files:** `dispatch/screens/new_job.py`, `dispatch/screens/dashboard.py`

**Current behaviour:** A single `Static` widget (`#warning`) shows all
messages — errors, warnings, info — with the same styling.

**Target behaviour:** Messages are displayed with visual severity:
- **Error** (red background): validation failures, crashes, file-not-found.
- **Warning** (yellow text): TTL < 1 hour, CWD not writable.
- **Success** (green text): Job launched successfully.
- **Info** (dim text): auto-detection results, status updates.

**Specification:**

1. Define CSS classes in `DispatchApp.CSS`:
   ```css
   .msg-error { color: $error; }
   .msg-warning { color: $warning; }
   .msg-success { color: $success; }
   .msg-info { color: $text-muted; }
   ```

2. Create a helper method on screens (or a mixin):
   ```python
   def _show_message(self, text: str, severity: str = "info") -> None:
       widget = self.query_one("#warning", Static)
       widget.update(text)
       for cls in ("msg-error", "msg-warning", "msg-success", "msg-info"):
           widget.remove_class(cls)
       widget.add_class(f"msg-{severity}")
   ```

3. Replace all `self.query_one("#warning", Static).update(...)` calls with
   `self._show_message(text, severity)`.

4. On the Dashboard, add a small "last 3 events" trail widget below the
   tables:
   ```
   [16:45] Launched Job 2026…_a1b2c3 (success)
   [16:44] Kerberos refreshed: 7h 28m (info)
   [16:40] dispatch started (info)
   ```

**Acceptance criteria:**
- Error messages are visually distinct from success messages.
- The event trail on the Dashboard shows the last 3–5 actions with timestamps.

---

## Phase C — Harden (tests, logging, polish)

### C-1: Unit test suite for core modules

**Gap:** G-16
**Files:** New files under `tests/`

The only existing test is `test_ui_snapshots.py` (a single Textual SVG
snapshot). The core logic modules have zero test coverage.

**Specification:**

Create the following test files:

#### `tests/test_manifest.py`
- `test_new_job_id_format`: verify `YYYYMMDDTHHMMSSZ_6chars` pattern.
- `test_validate_rejects_missing_keys`: remove each required key, assert `ValueError`.
- `test_validate_rejects_illegal_cell`: test all 10 illegal `(Source, Destination)` pairs.
- `test_validate_accepts_legal_cells`: test all 5 legal cells.
- `test_create_job_writes_manifest_and_sql`: create a job in a temp dir, verify files exist and manifest is valid JSON.
- `test_build_orchestrator_calls_sqlfile_table`: verify exact argv for `(SqlFile, Table)`.
- `test_build_orchestrator_calls_sqlfile_csv`: verify exact argv for `(SqlFile, Csv)`.
- `test_build_orchestrator_calls_sqlfile_table_csv`: verify two calls in correct order for `(SqlFile, Table+Csv)`.
- `test_build_orchestrator_calls_sqltemplate`: verify argv includes `--start-date`, `--end-date`.
- `test_build_orchestrator_calls_existingtable`: verify argv for `(ExistingTable, Csv)`.
- `test_atomic_write_survives_crash`: write manifest, verify `.tmp` does not linger.
- `test_update_preserves_other_fields`: update only `state`, verify other fields unchanged.

#### `tests/test_sql.py`
- `test_detect_source_sqlfile`: SQL without `{date_*}` → `"SqlFile"`.
- `test_detect_source_sqltemplate`: SQL with both `{date_inicio}` and `{date_fim}` → `"SqlTemplate"`.
- `test_is_malformed_template_one_placeholder`: only `{date_inicio}` → `True`.
- `test_is_malformed_template_both`: both placeholders → `False`.
- `test_is_malformed_template_neither`: neither → `False`.
- `test_table_wrapper_generates_correct_ddl`: verify `DROP/CREATE/STORED AS PARQUET/LOCATION/AS` structure, including HDFS prefix extraction (`aa_enc` → `aa`).
- `test_month_range_single_month`: `2026-01-01` to `2026-01-31` → 1 month.
- `test_month_range_full_year`: `2026-01-01` to `2026-12-31` → 12 months.
- `test_month_range_cross_year`: `2025-11-01` to `2026-02-28` → 4 months.
- `test_monthly_preview_output_format`: verify header, per-month blocks with `date_inicio`/`date_fim` substituted.
- `test_to_orchestrator_date`: `"2026-05-15"` → `"05/15/2026"`.

#### `tests/test_jobs.py`
- `test_list_manifests_empty_dir`: returns `[]`.
- `test_list_manifests_skips_corrupt`: one valid, one corrupt manifest → returns only valid.
- `test_running_jobs_filters_state`: 3 jobs (Running, Succeeded, Failed) → returns only Running.
- `test_can_launch_under_cap`: 0 or 1 running → `True`.
- `test_can_launch_at_cap`: 2 running → `False`.
- `test_active_jobs_includes_recent_finished`: job finished 3 days ago → included.
- `test_active_jobs_excludes_old_finished`: job finished 10 days ago → excluded.
- `test_history_jobs_inverse_of_active`: job finished 10 days ago → in history, not active.

#### `tests/test_kerberos.py`
- `test_parse_ttl_seconds_valid_output`: sample klist output → correct TTL.
- `test_parse_ttl_seconds_expired`: expiry in the past → `0`.
- `test_parse_ttl_seconds_no_ticket_lines`: garbage input → `None`.

#### `tests/test_runner.py`
- `test_run_happy_path`: create a Pending manifest with a trivial orchestrator
  call (`echo hello`), run the runner, verify manifest reaches `Succeeded`.
- `test_run_rejects_non_pending`: create a Running manifest, verify exit code 4.
- `test_run_handles_corrupt_manifest`: write invalid JSON, verify exit code 3
  and `manifest.error.json` exists.
- `test_run_fails_on_bad_orchestrator`: orchestrator argv = `["false"]`,
  verify manifest reaches `Failed`.

#### `tests/test_config.py`
- `test_data_root_default`: without env var, returns `/ads_storage/<user>`.
- `test_data_root_override`: with `DISPATCH_DATA_ROOT` set, returns override.
- `test_read_write_config_roundtrip`: write and read back, values match.

**Acceptance criteria:**
- `python -m pytest tests/ -q` passes with zero failures.
- Coverage of `manifest.py`, `sql.py`, `jobs.py`, `kerberos.py` is ≥ 85%.

---

### C-2: Application logging to `dispatch.log`

**Gap:** G-15
**File:** `dispatch/app.py`, `dispatch/__init__.py`

**Current behaviour:** No file-based logging. Errors in startup are silent.

**Target behaviour:** A `logging.FileHandler` writes to
`~/.dispatch/dispatch.log` (or `$DISPATCH_DATA_ROOT/.dispatch/dispatch.log`).
Log rotation at 1 MB, keeping 3 backups.

**Specification:**

1. In `dispatch/__init__.py`, add a `setup_logging()` function:
   ```python
   import logging
   from logging.handlers import RotatingFileHandler
   from . import config

   def setup_logging() -> None:
       log_path = config.dispatch_home() / "dispatch.log"
       log_path.parent.mkdir(parents=True, exist_ok=True)
       handler = RotatingFileHandler(
           log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
       )
       handler.setFormatter(logging.Formatter(
           "%(asctime)s %(levelname)s %(name)s: %(message)s"
       ))
       logging.getLogger("dispatch").addHandler(handler)
       logging.getLogger("dispatch").setLevel(logging.INFO)
   ```

2. Call `setup_logging()` in `DispatchApp.__init__` (before `super().__init__`).

3. Add `logger = logging.getLogger(__name__)` to each module that needs it.

4. Log key events:
   - Startup: version, launch CWD, data root, installed version.
   - Job launch: job ID, source, destination.
   - Job cancel: job ID.
   - Kerberos TTL refresh results.
   - Any caught exception during startup or screen mount.

**Acceptance criteria:**
- After running `dispatch`, `~/.dispatch/dispatch.log` exists and contains
  startup entries.
- Exceptions during screen mount appear in the log, not just swallowed.

---

### C-3: Minimum terminal size detection

**Gap:** G-14
**File:** `dispatch/app.py`

**Current behaviour:** No minimum size check. On very small terminals, the
TUI renders broken layouts.

**Target behaviour:** If terminal is below 80×24, show a single-screen
message: `"Terminal too small (current: WxH, minimum: 80x24). Resize and
restart dispatch."` The app does not push the Dashboard.

**Specification:**

1. In `DispatchApp.on_mount()`, check `self.size`:
   ```python
   if self.size.width < 80 or self.size.height < 24:
       self.query_one("#startup", Static).update(
           f"Terminal too small ({self.size.width}×{self.size.height}). "
           f"Minimum: 80×24. Resize and restart dispatch."
       )
       return
   self.push_screen(DashboardScreen(self.launch_cwd))
   ```

2. Optionally, add an `on_resize` handler that shows a warning banner if the
   terminal shrinks below 80×24 mid-session.

**Acceptance criteria:**
- Running `dispatch` in a 40×12 terminal shows the size warning, not a
  broken dashboard.
- Resizing to 80×24 or larger and restarting works normally.

---

### C-4: Enhanced Preview screen with scrolling

**Gap:** G-13
**File:** `dispatch/screens/preview.py`

**Current behaviour:** `PreviewScreen` renders SQL as a plain `Static`
widget. Long SQL or monthly preview output is cut off with no scroll.

**Target behaviour:** Use Textual's `TextArea` (read-only mode) or
`RichLog` for scrollable, optionally syntax-highlighted SQL preview.

**Specification:**

1. Replace `Static(self.body, id="preview-body")` with:
   ```python
   from textual.widgets import TextArea
   yield TextArea(self.body, read_only=True, id="preview-body",
                  language="sql", theme="monokai")
   ```
   Textual's `TextArea` supports syntax highlighting for SQL out of the box
   via tree-sitter (if the grammar is available). If not, fall back to plain
   text — the read-only scrollable behaviour is the critical feature.

2. Add CSS for the preview body to take remaining vertical space:
   ```css
   #preview-body { height: 1fr; }
   ```

**Acceptance criteria:**
- A 200-line SQL file can be fully scrolled in the preview.
- Monthly preview with 12 months of partitions is fully scrollable.

---

### C-5: Mock scenario validation test (plan §12.1, PR 1 artefact)

**Gap:** The plan requires a 6×3 validation table for the mock layer.

**File:** `tests/test_mock_scenarios.py`

**Specification:**

Create an integration test that runs each of the 6 mock scenarios against
each of the 3 orchestrator scripts (where applicable) and asserts expected
outcomes:

| Scenario | `Query_Impala_Parametrized.py` | `download_to_csv.py` | `monthly_query_processor.py` |
|----------|-------------------------------|---------------------|------------------------------|
| `happy_path` | exit 0, email sent | exit 0, CSV created | exit 0, email sent |
| `syntax_error` | exit 1, fatal classified | exit 1, fatal classified | exit 1, fatal classified |
| `auth_error` | exit 1, fatal classified | exit 1, fatal classified | exit 1, fatal classified |
| `memory_exceeded` | exit 0 (after retries) | exit 0 (after retries) | exit 0 (after retries) |
| `all_queues_full` | hangs (kill after 10s) | hangs (kill after 10s) | hits max_cycles limit |
| `slow` | exit 0 (delayed) | exit 0 (delayed) | exit 0 (delayed) |

The test uses `source mocks/dev-env.sh` environment and runs each script
via subprocess with appropriate arguments, checking exit codes and the
presence of expected artefacts (email files, CSV files, log output).

**Acceptance criteria:**
- `pytest tests/test_mock_scenarios.py -q` passes.
- The test acts as a regression gate for mock layer drift.

---

### C-6: Browser lazy `SHOW TABLE STATS`

**Gap:** G-17
**File:** `dispatch/screens/browser.py`, `dispatch/impala.py`

The plan wireframe (§8) shows `Size` and `Rows` columns that populate
lazily when a row is selected.

**Specification:**

1. Add to `impala.py`:
   ```python
   async def table_stats(full_table: str) -> dict[str, str]:
       output = await query(f"SHOW TABLE STATS {full_table};")
       # Parse output for #Rows and Size — format is pipe-delimited
       ...
       return {"rows": rows_value, "size": size_value}
   ```

2. In the Browser `DataTable`, add `Size` and `Rows` columns, initially
   showing `?`.

3. On row selection (`on_data_table_row_selected`), call
   `impala.table_stats()` and update the selected row's `Size`/`Rows` cells.

4. Update the mock `impala-shell` to handle `SHOW TABLE STATS` queries,
   returning plausible mock data.

**Acceptance criteria:**
- `SHOW TABLES` results show `?` for Size/Rows.
- Selecting a row triggers a background `SHOW TABLE STATS` and fills in values.
- The cluster is not hammered on initial schema browse.

---

## 3. Task Dependency Graph

```
Phase A (Stabilise) — no dependencies between A-1, A-2, A-3; all can be
parallel. Phase B depends on Phase A completing.

A-1 ──┐
A-2 ──┼── Phase A complete ──┬── B-1 (Dashboard DataTable)
A-3 ──┘                      ├── B-2 (History DataTable)
                              ├── B-3 (Browser DataTable + DROP confirm)
                              ├── B-4 (Kerberos header)
                              ├── B-5 (Version banner)
                              ├── B-6 (Date defaults + field visibility)
                              │       └── depends on A-1 (RadioSet)
                              └── B-7 (Feedback tiers)

Phase C can begin as soon as any individual Phase B task lands:

B-1 ──┬── C-1 (Unit tests — can start anytime)
B-2 ──┤
B-3 ──┤── C-4 (Preview scroll)
B-4 ──┤── C-2 (Logging)
B-5 ──┤── C-3 (Terminal size)
B-6 ──┤── C-5 (Scenario tests)
B-7 ──┘── C-6 (Browser stats)
```

---

## 4. Definition of Done (all tasks)

Carried forward from the original plan with additions:

- [ ] All deliverables pass `python3.10 -m py_compile`.
- [ ] `flake8 . --max-line-length=120` clean on changed files.
- [ ] `pylint <changed-files> --disable=C0114,C0115,C0116,C0103,W0718 --max-line-length=120` clean.
- [ ] `python -m pytest tests/ -q` passes (existing + new tests).
- [ ] No `subprocess` calls outside `dispatch/process.py`.
- [ ] No orchestrator spawned directly from TUI (always via runner).
- [ ] No gzipped CSV output.
- [ ] No CSV stored under `~/.dispatch/`.
- [ ] PR description cross-references relevant ADRs and gap IDs from this plan.
- [ ] One commit per logical change.

---

## 5. Anti-patterns (unchanged from v1 plan)

- Spawning subprocesses outside `dispatch/process.py`.
- Spawning an orchestrator directly from the TUI.
- `subprocess.run(...)` in a Textual callback (use async).
- Backing Jobs with `tmux` / `screen`.
- Gzipping CSV output.
- Storing CSV under `~/.dispatch/`.
- Modifying `scr/` outside ADR-0005 rules.
- Installing deps into the system Python.
- Reading passwords in the TUI (use `App.suspend()` + `kinit`).
- Retrying fatal classified errors.
- Assuming `$HOME == /ads_storage/<user>/`.
- Blocking the Textual event loop on filesystem I/O.

---

## 6. Files Changed Per Task (quick reference)

| Task | Files modified | New files |
|------|---------------|-----------|
| A-1 | `dispatch/screens/new_job.py` | — |
| A-2 | `dispatch/screens/new_job.py` | — |
| A-3 | `dispatch/screens/new_job.py`, `history.py`, `job_detail.py`, `browser.py` | — |
| B-1 | `dispatch/screens/dashboard.py` | — |
| B-2 | `dispatch/screens/history.py` | — |
| B-3 | `dispatch/screens/browser.py`, `dispatch/impala.py` | — |
| B-4 | `dispatch/app.py` | `dispatch/widgets/kerberos_indicator.py` (optional) |
| B-5 | `dispatch/app.py` | — |
| B-6 | `dispatch/screens/new_job.py` | — |
| B-7 | `dispatch/app.py`, `dispatch/screens/new_job.py`, `dashboard.py` | — |
| C-1 | — | `tests/test_manifest.py`, `test_sql.py`, `test_jobs.py`, `test_kerberos.py`, `test_runner.py`, `test_config.py` |
| C-2 | `dispatch/__init__.py`, `dispatch/app.py` | — |
| C-3 | `dispatch/app.py` | — |
| C-4 | `dispatch/screens/preview.py` | — |
| C-5 | — | `tests/test_mock_scenarios.py` |
| C-6 | `dispatch/screens/browser.py`, `dispatch/impala.py` | — |

---

## 7. Out of Scope (carried forward)

- Auto-queueing of a 3rd Job.
- Cross-user Job visibility.
- Cluster / queue health dashboard.
- Mid-Job Kerberos auto-renewal.
- Staging-cluster integration test environment.
- Resume-from-failure for `Table+Csv` Jobs.
- Textual CSS theming for light/dark terminal detection (P3, deferred).
