# Implementation Plan — UI/UX Audit Remediation

**Source:** `docs/audits/2026-05-30-ui-ux-audit.md`  
**Approach:** Vertical slices grouped by risk and dependency, not by screen.

---

## Slice Overview

The 34 audit issues + 20 roadmap items are organized into **7 implementation
slices**, each independently shippable and testable. Slices are ordered by
production-safety criticality first, then user-facing impact.

| Slice | Title | Issues Addressed | Risk | Files Touched |
|-------|-------|-----------------|------|---------------|
| 1 | Async workers for event-loop safety | D-2, JD-1, #1, #2 | Low (isolated refactor) | `dashboard.py`, `job_detail.py` |
| 2 | Responsive layout & narrow-terminal polish | D-5, NJ-1, #3, #7, D-1 | Medium (CSS + conditional compose) | `app.py` (CSS), `sidebar.py`, `dashboard.py`, `new_job.py` |
| 3 | Job Detail UX: follow/pause, truncation, cancel guard | JD-2, JD-3, JD-5, JD-6, #5 | Low (additive) | `job_detail.py`, `dashboard.py` |
| 4 | Error classification & Clone Job | #4, #6, NJ-6 | Medium (new feature) | `manifest.py`, `jobs.py`, `dashboard.py`, `job_detail.py`, `new_job.py` |
| 5 | Browser & form hardening | BR-1, BR-4, NJ-2, NJ-3, NJ-4, NJ-5, NJ-7, #8, #9 | Low (small fixes) | `browser.py`, `new_job.py`, `sidebar.py`, `app.py` (CSS) |
| 6 | Navigation & keyboard power-user features | #12, JD-4, H-3, H-4, D-6, P-2, HP-1 | Low (additive bindings) | `job_detail.py`, `history.py`, `dashboard.py`, `preview.py`, `help.py` |
| 7 | Polish & notifications | #11, #13, #14, #16, #17, HP-2, HP-3, P-1, P-3, D-3, D-4, H-1, H-2, BR-2, BR-3, CM-1 | Low (cosmetic) | Multiple (incremental) |

---

## Slice 1: Async Workers for Event-Loop Safety

**Why first:** ADR-0002 explicitly requires async-safe subprocess/IO. These are
the only issues that violate an architectural decision record and could cause
visible UI freezes under real workloads (many manifests, large logs).

### Tasks

1. **Dashboard: wrap `refresh_jobs()` in a worker**
   - Create `@work(exclusive=True, name="refresh_jobs")` method
   - Worker calls `jobs.active_jobs()` (filesystem walk + JSON parse) off the event loop
   - On worker success, update tables + stats from the returned snapshot
   - On worker failure, show a transient notify
   - Keep `set_interval(2.0)` but target the worker-launcher, not the sync method
   - Cancel worker on screen unmount

2. **Job Detail: wrap `_update_log()` in a worker**
   - Create `@work(exclusive=True, name="tail_log")` method
   - Worker reads file bytes from `_tail_offset` → returns new lines
   - Main thread callback writes lines to `RichLog`
   - Keep `set_interval(1.0)` targeting the worker-launcher
   - Cancel worker on screen unmount

3. **Job Detail: wrap `refresh_detail()` manifest load in same or separate worker**
   - `manifest.load()` is a JSON file read — small but still IO
   - Can merge with the tail worker into a single "refresh" worker that returns `(manifest_dict, new_log_lines)`

### Acceptance Criteria

- `DISPATCH_MOCK_SCENARIO=slow` with 50+ manifest stubs: no UI jank
- Existing tests continue to pass (worker mocking may need `await pilot.pause()`)
- No synchronous file I/O remains in `set_interval` callbacks

### Estimated Complexity

Low. Pattern is mechanical: extract sync body → return data from worker → update UI in callback. Textual's `@work` decorator handles cancellation and exclusivity.

---

## Slice 2: Responsive Layout & Narrow-Terminal Polish

**Why second:** 80×24 is the documented minimum and a real-world SSH default.
The sidebar consuming 35% of width makes the app borderline unusable at minimum
size.

### Tasks

1. **Sidebar responsive collapse**
   - Add a reactive `collapsed` state to `Sidebar`
   - Collapsed mode: width 5, show only icons (⌂ ⊞ 📄 🕒 📂), hide brand + "? Help" text
   - Expanded mode: current 28-col layout
   - Auto-collapse: watch `app.size.width` via `on_resize`; collapse at < 100, expand at ≥ 100
   - Manual toggle: bind `ctrl+b` (non-conflicting) to toggle sidebar
   - CSS: add `.sidebar-collapsed` class with `width: 5` override

2. **Stat cards compact mode**
   - At width < 100: replace 4 bordered cards with a single `Static` line:
     ```
     ● Running: 0/2  ✓ Finished: 0  ✗ Failed: 0  🔑 Kerberos: 7h 59m
     ```
   - Use `on_resize` to switch between modes (or reactive tied to app width)
   - Fix D-1: add explicit `text-align: center` to stat card inner widgets

3. **New Job form: pinned action bar**
   - Dock a `Horizontal` containing validation summary + Preview + Launch buttons at the bottom of `#main-content` (outside the scrollable `#new-job-content`)
   - Validation summary: `"✓ Ready to launch"` or `"✗ N issues"` (addresses NJ-6)
   - Form content above scrolls independently; action bar is always visible

4. **80×24 rendering test**
   - Add pilot test at `size=(80, 24)` asserting:
     - Dashboard renders without crash
     - New Job form Launch button is visible (in docked bar)
     - Sidebar shows icons but not full text

### Acceptance Criteria

- At 80×24: sidebar collapses, stat cards compact, Launch button visible
- At 120×40: full layout with expanded sidebar
- `Ctrl+B` toggles sidebar at any width
- Existing 120 tests still pass

### Estimated Complexity

Medium. CSS changes are straightforward but the conditional compose/reactivity
for sidebar collapse requires careful watcher logic and test coverage.

---

## Slice 3: Job Detail UX Enhancements

**Why third:** Once async workers are in (Slice 1), the Job Detail screen can
be enhanced without risking event-loop issues.

### Tasks

1. **Follow/pause toggle (JD-2)**
   - Add reactive `follow_mode: bool = True`
   - When `follow_mode` is True, auto-scroll `RichLog` on new lines
   - When False, stop auto-scrolling; show `[PAUSED]` in `#log-streaming` indicator
   - Bind `Space` or `f` to toggle; add to footer bindings
   - Resume follow when user presses the key again or scrolls to bottom

2. **Truncation indicator (JD-3)**
   - When `_tail_lines` deque evicts old entries, track total evicted count
   - Show `[… N earlier lines not shown]` as first line in RichLog (or as a dim Static above log panel)
   - Update count on each truncation

3. **Cancel button guard (JD-5)**
   - In `refresh_detail()`, after loading manifest:
     ```python
     cancel_btn = self.query_one("#cancel", Button)
     cancel_btn.disabled = item["state"] != "Running"
     ```
   - When disabled, button shows at 40% opacity (existing CSS handles this)

4. **Unified elapsed format (JD-6)**
   - Extract `format_elapsed(started_at, finished_at, state)` into a shared utility (e.g., `dispatch/formatting.py`)
   - Always produce `Xs` (< 60s), `Xm Ys` (< 1h), `Xh Ym` (≥ 1h)
   - Replace bespoke `_elapsed()` in `dashboard.py` and `_format_elapsed()` in `job_detail.py`

### Acceptance Criteria

- Space toggles follow mode; indicator updates
- Scrolling up auto-pauses; pressing Space resumes
- Cancel button disabled on Succeeded/Failed/Cancelled jobs
- Elapsed format is identical between Dashboard and Job Detail

### Estimated Complexity

Low. All additive changes to existing Job Detail screen.

---

## Slice 4: Error Classification & Clone Job

**Why fourth:** This is the highest-impact user-facing feature gap. Users
currently must read raw logs to understand failures and manually re-create jobs.

### Tasks

1. **Error classifier module (`dispatch/errors.py`)**
   - Define known error patterns from orchestrator output:
     ```python
     PATTERNS = [
         ("SYNTAX_ERROR", r"AnalysisException.*Syntax error"),
         ("TABLE_NOT_FOUND", r"Table.*does not exist|TableNotFoundException"),
         ("MEMORY_EXCEEDED", r"Memory limit exceeded|MEMORY_LIMIT_EXCEEDED"),
         ("AUTH_ERROR", r"AuthorizationException|Kerberos.*expired"),
         ("QUEUE_FULL", r"Rejected.*pool|All pools busy|queue timeout"),
     ]
     ```
   - `classify(log_path: Path) -> str | None` — reads last 50 lines, matches first pattern
   - Return `None` if no known pattern matches

2. **Dashboard: error badge in table**
   - For failed jobs, call `errors.classify()` and show result in State column:
     ```
     ● FAILED (SYNTAX)
     ```
   - Cache classification per job-id (won't change once job is terminal)

3. **Job Detail: error summary banner**
   - When state == Failed and classifier returns a result:
     - Show a 2-line red-bordered Static above the log panel
     - Line 1: classification + first matched line from log
     - Line 2: suggestion text (hardcoded per classification)
   - When classifier returns None: show generic "Check log for details"

4. **Clone Job action**
   - Add button "Clone [R]" in Job Detail for terminal-state jobs
   - On press: read manifest → push `NewJobScreen` pre-populated with:
     - Same source type, SQL file path, table name, schema, email, subject
     - Same destination type
   - `NewJobScreen.__init__` gains optional `prefill: dict` parameter
   - If `prefill` is provided, override form defaults with those values

5. **Validation summary on New Job (NJ-6)**
   - Move from Slice 2 if not done there; add aggregate readiness indicator:
     ```
     ✓ Ready to launch (3/3 checks passing)
     ```
     or
     ```
     ✗ 1 issue: SQL file not found
     ```

### Acceptance Criteria

- `DISPATCH_MOCK_SCENARIO=syntax_error`: dashboard shows `● FAILED (SYNTAX)`
- Job Detail shows error banner with suggestion
- Clone button opens New Job pre-filled with original parameters
- Existing validation tests pass; new tests cover classifier

### Estimated Complexity

Medium. New module + integration into two screens + new nav path from Job Detail → New Job.

---

## Slice 5: Browser & Form Hardening

**Why fifth:** Collection of small, independent fixes that collectively improve
daily usability.

### Tasks

1. **Browser: auto-load tables on mount (BR-1)**
   - Call `action_show_tables()` from `on_mount()` (already async-safe via `run_exec`)
   - Remove explicit "SHOW TABLES" button requirement for first view

2. **Browser: auto-refresh after DROP (BR-4)**
   - After successful `impala.drop_table()`, call `await self.action_show_tables()`

3. **New Job: collapsible matrix (NJ-2)**
   - Wrap `#matrix-panel` in a `Collapsible` (Textual built-in) or custom toggle
   - Collapsed by default if `config.read_form_defaults()` contains a previous successful launch
   - Keyboard: `m` to toggle matrix visibility

4. **New Job: radio group visual separation (NJ-3)**
   - Add `border: round $primary-background-darken-2` to `.radio-group` in CSS

5. **New Job: disabled option hint (NJ-4)**
   - When a destination RadioButton is disabled, append dim text below the RadioSet:
     ```
     [dim]SqlTemplate supports Table only[/]
     ```
   - Update dynamically when Source selection changes

6. **New Job: email placeholder from env (NJ-5)**
   - Read `DISPATCH_EMAIL` env var for placeholder/default value
   - Fallback placeholder: `"user@example.com"`

7. **New Job: date format hint (NJ-7)**
   - Add `placeholder="YYYY-MM-DD"` (already done)
   - Add dim Static below date inputs: `"[dim]Format: YYYY-MM-DD[/]"`

8. **Sidebar: ASCII fallback for emoji (Issue #9)**
   - Detect terminal emoji support (check `TERM`, `LANG`, or provide config flag)
   - Fallback icons: `[*]` Overview, `[+]` New Job, `[>]` View Logs, `[h]` History, `[b]` Browse
   - Simplest approach: always use Unicode symbols from BMP (⌂ ⊞ ▸ ◷ ☰) instead of multi-byte emoji

### Acceptance Criteria

- Browser opens with tables already loaded
- DROP refreshes the list
- Matrix collapsed on subsequent visits after first launch
- All terminals render sidebar icons (no mojibake)
- Date inputs show format hint

### Estimated Complexity

Low per task, medium aggregate. Each is independent and can be merged separately.

---

## Slice 6: Navigation & Keyboard Power-User Features

**Why sixth:** Additive improvements that don't change existing behavior, only
add new keybindings.

### Tasks

1. **`j`/`k` navigation in DataTable (Issue #12)**
   - Add bindings `j` → cursor down, `k` → cursor up on screens with DataTable as primary widget
   - Applicable to: Dashboard, History, Browser table list
   - Guard: only when DataTable has focus (don't conflict with text input)

2. **`g`/`G` jump in log viewer (Issue #12)**
   - Job Detail: `g` scrolls RichLog to top, `G` scrolls to bottom
   - `G` also re-enables follow mode if paused

3. **`/` search in log viewer (JD-4)**
   - Show a transient `Input` at bottom of log panel
   - Filter/highlight matching lines in the RichLog
   - `Esc` dismisses search, `n`/`N` navigate matches
   - Scope: MVP can just highlight matches without filtering

4. **History: sort toggle (H-3)**
   - Add `s` binding to cycle sort: date (default), state, table name
   - Show current sort in a dim indicator: `"Sorted by: date ↓"`

5. **History: replace emoji in search placeholder (H-4)**
   - Change `🔍 table · date · job-id` → `Filter: table, date, or job-id`

6. **Dashboard: rename "View / Attach" button (D-6)**
   - Rename to `"View Logs [V]"`

7. **Preview: rename "Accept & Return" button (P-2)**
   - Rename to `"Back to Form [Enter]"`

8. **Help: color-coded sections (HP-1)**
   - Add `[bold $accent]` header per screen section
   - Add horizontal rules between sections
   - Consider: show current screen section first (HP-2)

### Acceptance Criteria

- `j`/`k` move cursor in tables
- `g`/`G` jump in logs
- `/` opens search overlay in Job Detail
- Button labels are clear and unambiguous

### Estimated Complexity

Low. All additive keybinding work with no architectural changes.

---

## Slice 7: Polish & Notifications

**Why last:** Cosmetic improvements and nice-to-haves that depend on earlier
slices being stable.

### Tasks

1. **Cross-screen job completion notification (Issue #14)**
   - When `refresh_jobs()` worker detects a state transition (Running → terminal), fire `app.notify()` regardless of active screen
   - Include job ID and new state in notification

2. **Collapsible matrix after first use (Issue #13)**
   - Covered in Slice 5 if not already shipped

3. **Manifest mtime caching (Issue #17)**
   - In `jobs.list_manifests()`: stat mtime before opening file; skip re-parse if unchanged since last read
   - Cache keyed by path → `(mtime, parsed_dict)`

4. **Copy-to-clipboard (Issue #16)**
   - Add `y` binding in Job Detail to copy job ID to clipboard (`pyperclip` or Textual's clipboard API if available)
   - Add `y` in Preview to copy generated SQL
   - Scope: best-effort — clipboard may not work over SSH; show notify on copy attempt

5. **SQL comment highlighting (P-1)**
   - In `_highlight_sql()`: detect `--` prefix → dim entire remainder of line

6. **Sort indicator in Dashboard (D-3)**
   - Add `"[dim]newest first[/]"` after section titles

7. **Unified ID display utility (H-2, D-4)**
   - Extract `format_job_id(job_id: str, style: str = "short") -> str` to `dispatch/formatting.py`
   - `"short"`: show token suffix; `"full"`: show complete ID

8. **Help scroll indicator (HP-3)**
   - Textual's `overflow-y: auto` should handle this — verify and add `scrollbar-size: 1 1` if needed

9. **Confirmation modal shortcut placement (CM-1)**
   - Move `[Y]`/`[N]` from button label to the `#confirm-help` line below

10. **Browser filter hint (BR-2)**
    - Add placeholder text: `"Filter (e.g., dispatch_*)"`

11. **Browser loading indicator (BR-3)**
    - Verify existing "Loading…" text is visible; add short spinner character if not (`⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏` animation)

### Acceptance Criteria

- Notifications appear on job completion from any screen
- Clipboard copy shows confirmation toast
- SQL comments render dimmed
- No visual regressions in existing tests

### Estimated Complexity

Low per item. This slice can be subdivided into individual PRs.

---

## Dependency Graph

```
Slice 1 (Async Workers)
    │
    ├── Slice 3 (Job Detail UX) ← depends on worker pattern from Slice 1
    │       │
    │       └── Slice 4 (Error Classification) ← uses enhanced Job Detail
    │
    └── Slice 2 (Responsive Layout) ← independent, but benefits from workers being stable
            │
            └── Slice 5 (Browser & Form) ← uses responsive patterns from Slice 2

Slice 6 (Keyboard) ← fully independent, can run in parallel with 3-5
Slice 7 (Polish) ← depends on all above being stable
```

**Parallelizable:** Slices 2 and 3 can be worked in parallel after Slice 1 ships. Slice 6 can be worked any time.

---

## Testing Strategy Per Slice

| Slice | Automated Tests | Manual Verification |
|-------|----------------|---------------------|
| 1 | Pilot test with `await pilot.pause()` after worker completes; assert table content | Profile 50-manifest directory refresh |
| 2 | Pilot at `(80, 24)` and `(120, 40)` asserting sidebar width, button visibility | Visual SVG screenshot comparison |
| 3 | Pilot: press Space → assert indicator changes; assert Cancel disabled for finished jobs | Interactive tmux session |
| 4 | Unit test `errors.classify()` with fixture logs; pilot test Clone button pre-fills form | Syntax_error scenario walkthrough |
| 5 | Pilot: verify browser has rows on mount; verify DROP triggers refresh | Interactive browser session |
| 6 | Pilot: press `j`/`k` → assert cursor moves; press `/` → assert input appears | Interactive session |
| 7 | Existing test suite regression; pilot for notifications | Visual review |

---

## Risk Notes

1. **Sidebar collapse (Slice 2)** is the highest-risk change — it touches global layout and every screen's compose tree. Consider feature-flagging via a config option initially.
2. **Error classifier (Slice 4)** depends on orchestrator log format stability. Document that patterns are best-effort and new patterns can be added without code changes (consider external pattern file).
3. **Clipboard (Slice 7)** is unreliable over SSH. Implement as best-effort with user-visible feedback regardless of success/failure.
4. **Worker migration (Slice 1)** may subtly change timing in existing pilot tests. Run full test suite after each worker conversion and add `await pilot.pause()` where needed.
