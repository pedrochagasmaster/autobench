# Dispatch TUI — UI/UX Audit

**Date:** 2026-05-30  
**Tested version:** 1.1.0  
**Terminal sizes tested:** 80×24, 120×40, 200×50  
**Mock scenarios exercised:** `happy_path`, `slow`, `syntax_error`, `auth_error` (no Kerberos)  
**Test suite:** 120/120 passing, 1 skipped

---

## Executive Summary

Dispatch is a well-structured Textual TUI with solid architectural foundations.
The codebase demonstrates good separation of concerns, proper use of Textual
primitives, and thoughtful keyboard-first interaction design. However, several
areas need polish and enhancement to reach production-grade quality for daily
use by data engineers over SSH.

**Overall grade: B+** — Strong bones, needs polish in information density, state
visibility, responsive narrowing, and progressive-disclosure refinement.

---

## 1. Architecture & Code Quality (Strengths)

| Area | Assessment |
|------|-----------|
| Screen/widget separation | Clean: each screen in its own file, sidebar shared |
| CSS organization | Single `APP_CSS` block is acceptable for current size; ready to extract to `.tcss` when it grows |
| Event-loop safety | No blocking subprocess calls in UI path; `process.run_exec` is async |
| Detached runner model | Excellent: TUI supervises via manifests, runner owns processes |
| Message-based nav | Sidebar uses proper Textual message → `NavItem.Selected` pattern |
| Reactive state | Used correctly for Kerberos TTL, sidebar highlight |
| Confirmation modals | Safety hierarchy is well-designed (simple Y/N vs typed confirmation for DROP) |
| Test coverage | 120 tests including pilot-style UI tests, mock contract, runner integration |

---

## 2. Screen-by-Screen Findings

### 2.1 Dashboard

**What works:**
- Stat cards provide at-a-glance capacity awareness (Running 0/2, Failed count)
- Empty-state messaging is clear with actionable hint ("Press N to create one")
- Event trail at bottom provides temporal context
- Two-table layout (Active/Recently Finished) maps cleanly to job lifecycle

**Issues:**

| ID | Severity | Issue | Recommendation |
|----|----------|-------|----------------|
| D-1 | Medium | Stat cards are center-aligned but text within is left-heavy; content-align center middle may not apply well to multi-line Static | Use `text-align: center` explicitly on each `.stat-value`, `.stat-label`, `.stat-sub` |
| D-2 | Medium | `refresh_jobs()` is synchronous and calls `jobs.active_jobs()` (filesystem walk + JSON parse) in a `set_interval(2.0)` callback — no worker | Move to a dedicated Textual worker with `exclusive=True` to avoid potential jank with many manifests |
| D-3 | Low | Table columns (ID, Source, Destination, State, Elapsed) don't indicate which is sorted | Add a visual sort indicator or document that newest-first is fixed |
| D-4 | Low | `_display_id()` strips first 9 chars if ID > 20, showing timestamp suffix — this may confuse users who see partial IDs | Show full 8-char token suffix with date prefix as tooltip in detail view |
| D-5 | Medium | On narrow terminals (80×24), the stat cards squish together and labels wrap | Add a responsive breakpoint: collapse stat cards to a single row of compact `RUNNING: 0/2 | FAILED: 0 | KERBEROS: 8h` on terminals < 100 wide |
| D-6 | Low | "View / Attach [V]" button label is vague for new users | Rename to "Job Logs [V]" or "View Logs [V]" for clarity |

### 2.2 New Job Screen

**What works:**
- Legal-cells matrix is prominently displayed, preventing invalid selections before users commit
- Auto-detection of SQL source type reduces cognitive load
- Inline validation shows ✓/✗ for SQL file, email, Kerberos in real time
- Dynamic field visibility (hiding irrelevant fields based on Source selection) is excellent
- Path hint beneath SQL file input gives immediate feedback

**Issues:**

| ID | Severity | Issue | Recommendation |
|----|----------|-------|----------------|
| NJ-1 | High | The form is long — on 80×24 terminals, Launch button may be below fold with no scroll indicator | Add a visible scroll indicator or pin the Launch button at the bottom of the viewport (dock: bottom) |
| NJ-2 | Medium | Matrix table occupies ~6 rows of vertical space on every visit; power users don't need it after learning | Make it collapsible (collapsed by default after first successful launch, or toggle with a key) |
| NJ-3 | Medium | Radio buttons use `RadioSet` but there's no visual grouping border around the two RadioSets side-by-side | Add light border or background tint to each `.radio-group` to visually separate Source from Destination |
| NJ-4 | Medium | When an illegal destination is disabled, user gets no explanation of *why* | Add a dim hint like "SqlTemplate → Table only" next to disabled options |
| NJ-5 | Low | Email placeholder is `dataops@company.com` — too specific for a generic tool | Use `user@example.com` or pull from `DISPATCH_EMAIL` env var |
| NJ-6 | Medium | The `_validate()` method is called only on Launch press; inline validation only shows field-level status but doesn't aggregate a "ready to launch" indicator | Add a green/red status line above Launch: "✓ Ready to launch" or "✗ 2 issues — fix before launching" |
| NJ-7 | Low | Date defaults (first/last day of current month) are fine for SqlTemplate but inputs are always shown when `SqlTemplate` is selected — no calendar helper for SSH | Add hint: "Format: YYYY-MM-DD" and validate date format on blur |

### 2.3 SQL Preview

**What works:**
- Line numbers with `│` separator
- Keyword highlighting (SELECT, FROM, WHERE bold cyan)
- Clear header showing target schema.table
- Accept returns to form without launching (safe preview workflow)

**Issues:**

| ID | Severity | Issue | Recommendation |
|----|----------|-------|----------------|
| P-1 | Low | String literals highlighted green but comments (`--`) are not dimmed | Add comment detection (`--` to end of line → dim styling) |
| P-2 | Low | "Accept & Return" button label is ambiguous — accept what? | Rename to "Back to Form [Enter]" or "Looks Good [Enter]" |
| P-3 | Medium | No word-wrap on very long SQL lines; user must scroll horizontally | Add horizontal scroll indicator or soft-wrap toggle |

### 2.4 Job Detail

**What works:**
- Two-column summary grid (source/dest/state on left, started/elapsed/table on right)
- Live log tail with auto-scroll
- Streaming indicator ("Streaming logs… ●" in green when running)
- Dimmed timestamps in log lines improve readability
- Cancel flow routes through confirmation modal

**Issues:**

| ID | Severity | Issue | Recommendation |
|----|----------|-------|----------------|
| JD-1 | High | Log is read synchronously in `set_interval(1.0)` — not via a worker | Use a Textual worker or async file read to prevent UI jank with large logs |
| JD-2 | Medium | No way to pause auto-scroll to inspect earlier log lines | Add Space or `f` to toggle "follow" mode; show `[FOLLOWING]` / `[PAUSED]` indicator |
| JD-3 | Medium | Log lines capped at 200 in deque but no indication that older lines were dropped | Show "[… N earlier lines truncated]" when truncation occurs |
| JD-4 | Low | No log search capability | Add `/` to open search filter within the log panel |
| JD-5 | Low | The "Cancel Job [C]" button is always visible even when job is in terminal state (Succeeded/Failed) | Disable or hide Cancel button when `state != Running` |
| JD-6 | Low | Elapsed time format differs from Dashboard (`3m 45s` vs `3m`) | Unify format: always show `Xm Ys` for < 1h, `Xh Ym` for >= 1h |

### 2.5 History

**What works:**
- Live search filters by job-id, table, date
- Pagination with page controls ([ ] keys)
- Empty state with hint
- Focus moves to search when table is empty

**Issues:**

| ID | Severity | Issue | Recommendation |
|----|----------|-------|----------------|
| H-1 | Low | Page controls show as static text `❮ Prev    Page X of Y    Next ❯` rather than clickable buttons | Make prev/next into actual `Button` widgets or add clearer keyboard affordance |
| H-2 | Low | History `_display_id()` uses different truncation logic than Dashboard — inconsistent | Unify ID display logic into a shared utility function |
| H-3 | Medium | No sort options — always newest first | Allow toggling sort by date, state, or table name (at minimum document the fixed order) |
| H-4 | Low | Search placeholder uses emoji (🔍) which may not render in all terminals | Use text prefix `[Search]` or `/ filter` instead of emoji |

### 2.6 Browser

**What works:**
- Split-panel layout (3:2 ratio) mirrors IDE conventions
- DESCRIBE results parsed into structured DataTable
- DROP requires typed full table name — strongest safety pattern
- Buttons disable when no table is selected

**Issues:**

| ID | Severity | Issue | Recommendation |
|----|----------|-------|----------------|
| BR-1 | Medium | SHOW TABLES is not auto-triggered on mount — user must click the button first | Auto-load tables on mount or show prominent CTA: "Press Enter to load tables" |
| BR-2 | Low | Filter input defaults to `*` which is fine but glob semantics aren't documented | Add hint: "Supports * wildcard (e.g., dispatch_*)" |
| BR-3 | Low | No loading spinner when SHOW TABLES or DESCRIBE is executing | Add "[dim]Loading…[/]" or spinner in detail panel during async operations (already partially done, but verify it's perceptible) |
| BR-4 | Medium | After DROP, the table list doesn't auto-refresh — dropped table still appears in the list | Auto-refresh table list after successful DROP |

### 2.7 Help Modal

**What works:**
- Organized by screen (Global, Dashboard, New Job, etc.)
- Quick reference strip at top
- Dismissible with Esc or ?

**Issues:**

| ID | Severity | Issue | Recommendation |
|----|----------|-------|----------------|
| HP-1 | Medium | Help is a static wall of text — hard to scan for specific shortcuts | Add color-coding to shortcut groups, or tabbed sections per screen |
| HP-2 | Low | No context-sensitivity — shows same help regardless of current screen | Consider highlighting the current screen's section, or showing context-relevant help first |
| HP-3 | Low | Modal max-height is 80% but on 80×24 that's only 19 rows — may truncate content | Ensure scroll indicator appears when content overflows |

### 2.8 Confirmation Modal

**What works:**
- Danger variant with red double border
- Typed confirmation for DROP (requires exact table name)
- Clear keyboard shortcuts (Y/Enter = confirm, N/Esc = cancel)
- Focus properly trapped

**Issues:**

| ID | Severity | Issue | Recommendation |
|----|----------|-------|----------------|
| CM-1 | Low | Button labels `[Y]` and `[N]` in the button text may confuse: is the whole button the key, or just the letter? | Move shortcut hints to separate dim text below buttons, or into the help line |

---

## 3. Cross-Cutting Concerns

### 3.1 Responsive Design / Narrow Terminal

**Tested at 80×24:**
- Sidebar (28 cols) consumes 35% of horizontal space → only 52 cols for content
- Stat cards compress heavily; labels may wrap
- Form fields on New Job screen extend below the fold
- DataTable columns truncate aggressively

**Recommendations:**
1. **Sidebar collapsing:** At widths < 100, collapse sidebar to icon-only (3-4 cols wide) with hover-expand or toggle key
2. **Stat cards responsive:** Below 100 cols, switch to a single-line compact summary
3. **Minimum-size gate:** The 80×24 warning notify is good; add a dim banner instead of a transient notification so it persists
4. **Form layout:** On narrow terminals, stack radio groups vertically instead of side-by-side

### 3.2 Color & Accessibility

**Strengths:**
- Uses Textual theme variables ($surface, $accent, $success, $error) — respects user themes
- State labels always include text + symbol (● RUNNING, ✓ SQL file found) — not color-alone
- Monochrome-first: layout is understandable without color

**Gaps:**
- `NO_COLOR` env var is not explicitly handled — relies on Textual's default behavior
- Some status colors (green for both "RUNNING" and "SUCCEEDED") may be ambiguous — consider blue for Running
- The emoji in sidebar nav (📄, 🕒, 📂) may not render in minimal terminals; use ASCII fallbacks

### 3.3 Performance

**Strengths:**
- Log tail reads incrementally (offset-based)
- Active jobs limited to 2 concurrent
- History pagination caps display at 17 per page

**Gaps:**
- `refresh_jobs()` on Dashboard does full filesystem walk + JSON parse every 2s synchronously
- `refresh_detail()` on JobDetail does manifest JSON parse every 1s synchronously
- Browser SHOW TABLES/DESCRIBE uses `run_exec()` async subprocess — good
- No caching layer for manifest reads — repeated parse of unchanged files

**Recommendations:**
1. Move manifest polling to a worker with `exclusive=True`
2. Add manifest mtime caching — only re-parse if file changed
3. Cap log file reads to last 64KB before switching to tail-only mode

### 3.4 Error Presentation

**Strengths:**
- Failed jobs clearly marked with red ● FAILED label
- Job detail shows exit code in status line
- Validation errors shown inline + as notify toasts (dual feedback)
- Kerberos missing state prominently shown with disabled Launch button

**Gaps:**
- Failed job logs show the raw orchestrator error but no classification or suggested fix
- No "retry" action available — user must manually create a new job with same parameters
- When queue is full (all_queues_full scenario), error message may be buried in log with no dashboard-level summary

**Recommendations:**
1. Parse common error patterns (SYNTAX_ERROR, TABLE_NOT_FOUND, MEMORY_EXCEEDED) and show a one-line human-readable summary in job detail header
2. Add "Clone Job" action: pre-populate New Job form from a finished/failed job's parameters
3. Show error classification badge in the dashboard table (e.g., "SYNTAX" / "AUTH" / "RESOURCE")

### 3.5 Keyboard Interaction Model

**Strengths:**
- Consistent `Esc`/`B` for Back across all screens
- Mnemonic shortcuts (N=New, H=History, B=Browse/Back, V=View, C=Cancel)
- Footer always shows available actions for current context
- `?` help is always accessible

**Gaps:**
- `B` is overloaded: means "Back" on most screens but "Browse" on Dashboard — potential muscle-memory conflict
- No `Tab` cycling between panels (sidebar → content → buttons) is explicitly documented
- No `j/k` vim-style navigation in tables (only arrow keys)
- No `/` search in DataTable on Dashboard or Job Detail log
- No `g/G` jump to top/bottom in logs

**Recommendations:**
1. Reserve `B` for "Back" universally; use another key for Browser (consider `Ctrl+B` or just sidebar click)
2. Add `j/k` as alternative to ↑/↓ in DataTable navigation
3. Add `/` search in log viewer and History table
4. Add `g/G` for top/bottom jump in log viewer
5. Document `Tab`/`Shift+Tab` panel cycling behavior

---

## 4. Production-Readiness Gap Analysis

### 4.1 Critical (Must-Fix for Production)

| # | Gap | Impact | Effort |
|---|-----|--------|--------|
| 1 | Dashboard `refresh_jobs()` runs synchronously in event loop | UI freezes with large job directories | Low — wrap in worker |
| 2 | Job Detail log read is synchronous | UI freezes with large logs | Low — use worker |
| 3 | No sidebar collapse for narrow terminals | Unusable at 80×24 with current 28-col sidebar | Medium — add responsive CSS + toggle |
| 4 | No "Clone Job" action | Users must manually re-type parameters after failure, error-prone | Medium — add action + pre-populate |

### 4.2 High Priority (Should-Fix Before Release)

| # | Gap | Impact | Effort |
|---|-----|--------|--------|
| 5 | No log follow/pause toggle | Users can't inspect earlier output during long-running jobs | Low — add state + key |
| 6 | No error classification in dashboard | Users must drill into detail to understand failure type | Medium — parse patterns |
| 7 | New Job form overflow on 80×24 | Launch button hidden, users may think form is incomplete | Medium — dock buttons or collapsible matrix |
| 8 | Browser doesn't auto-refresh after DROP | Stale state misleads user | Low — call action_show_tables() |
| 9 | Emoji in sidebar may not render on all terminals | Broken display on minimal terminal emulators | Low — use ASCII fallback |
| 10 | No progress/elapsed counter updating per-second on running jobs in dashboard | Users must enter detail to see elapsed time | Low — already refresh every 2s, ensure elapsed column updates |

### 4.3 Nice-to-Have (Polish)

| # | Gap | Impact |
|---|-----|--------|
| 11 | Context-sensitive help (highlight current screen section) | Faster shortcut discovery |
| 12 | `j/k/g/G//` vim-style navigation in tables and logs | Power-user efficiency |
| 13 | Collapsible matrix table after first use | Reduced visual noise for power users |
| 14 | Notification for job completion while on another screen | Users don't miss completions |
| 15 | Dark/light theme toggle | Corporate environments may prefer light |
| 16 | Copy-to-clipboard for CSV path, job ID, error message | Faster troubleshooting |
| 17 | Manifest mtime caching | Reduced I/O with many historical jobs |
| 18 | Horizontal scroll indicator in SQL preview | Very long SQL lines are accessible |
| 19 | Tabbed help modal by screen | Easier navigation in long help text |
| 20 | "Re-run" action for succeeded jobs | Convenient repeat execution |

---

## 5. Proposed Design Improvements

### 5.1 Sidebar (narrow terminal handling)

```
Current (28 cols):          Proposed collapsed (5 cols):
┌──────────────────────┐    ┌───┐
│ robocop / Dispatch   │    │ ⌂ │  ← tooltip on hover
│                      │    │ ⊞ │
│ ⌂ Overview           │    │ 📄│
│ ⊞ New Job            │    │ 🕒│
│ 📄 View Logs         │    │ 📂│
│ 🕒 History           │    └───┘
│ 📂 Browse            │
│                      │
│ ? Help               │
└──────────────────────┘
```

Toggle with `Ctrl+S` or auto-collapse at width < 100.

### 5.2 Dashboard stat cards (narrow mode)

```
Current (4 separate bordered cards):
┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│ RUNNING │ │FINISHED │ │ FAILED  │ │KERBEROS │
│  0 / 2  │ │    0    │ │    0    │ │  479m   │
│running/c│ │last 7 d │ │last 7 d │ │remaining│
└─────────┘ └─────────┘ └─────────┘ └─────────┘

Proposed compact (single-line at width < 100):
 ● Running: 0/2  ✓ Finished: 0  ✗ Failed: 0  🔑 Kerberos: 7h 59m
```

### 5.3 New Job form — pinned action bar

```
Current: buttons buried at bottom of scrollable form
Proposed: Dock action bar (preview + launch) at bottom of #main-content:

┌─────────────────────────────────────────────────────┐
│ [scrollable form content above]                     │
│                                                     │
├─────────────────────────────────────────────────────┤
│ ✓ Ready to launch    [Preview SQL P]  [Launch L]    │  ← always visible
└─────────────────────────────────────────────────────┘
```

### 5.4 Job Detail — error classification banner

```
Current (failed job):
  State: ● FAILED
  [raw log below]

Proposed:
  State: ● FAILED
  ┌─ Error ────────────────────────────────────────────┐
  │ SYNTAX_ERROR: Column 'nonexistent' not found       │
  │ Suggestion: Check column names in query line 3     │
  │                                    [Clone Job]     │
  └────────────────────────────────────────────────────┘
  [log below]
```

### 5.5 Log viewer — follow/pause mode

```
┌─ Live Logs ──────────────────── [FOLLOWING ●] ───────┐
│ [22:01:05] Connecting to impala-shell...             │
│ [22:01:06] Query submitted to pool adhoc_fast       │
│ [22:01:07] Processing...                            │▐
│                                                     │▐
└──────────────────────────────────────────────────────┘
  Space: pause/follow  /: search  g/G: top/bottom
```

---

## 6. Prioritized Implementation Roadmap

### Phase 1: Production Safety (blocks release)
1. Async workers for dashboard refresh and log tailing
2. Sidebar responsive collapse
3. Pinned action bar on New Job screen
4. Disable Cancel button on terminal-state jobs

### Phase 2: User Experience (first month post-release)
5. Log follow/pause toggle
6. Error classification banner
7. Clone Job action
8. Browser auto-refresh after DROP
9. j/k/g/G/search in tables and logs
10. ASCII fallback for emoji nav icons

### Phase 3: Polish (ongoing)
11. Collapsible matrix table
12. Context-sensitive help
13. Cross-screen job completion notifications
14. Manifest mtime caching
15. Copy-to-clipboard actions

---

## 7. Test Validation Summary

| Check | Result |
|-------|--------|
| `python -m compileall dispatch scr` | ✓ Clean |
| `pytest tests/ -q` | ✓ 120 passed, 1 skipped |
| 80×24 rendering (via Textual pilot) | ✓ Renders, sidebar compresses content |
| 120×40 rendering | ✓ Comfortable layout |
| 200×50 rendering | ✓ Uses space well, no stretched elements |
| Dashboard empty state | ✓ Clear hint, no broken layout |
| Dashboard with running job | ✓ Active table appears, stat updates |
| Dashboard with failed job | ✓ Red ● FAILED in recent table |
| New Job form validation | ✓ Inline ✓/✗ indicators work |
| SQL Preview highlighting | ✓ Keywords cyan bold, line numbers dim |
| Job Detail log tail | ✓ Streams, timestamps dimmed |
| History pagination | ✓ [ ] navigate pages, search filters |
| Browser SHOW/DESCRIBE | ✓ Async, table list → detail panel |
| Help modal | ✓ Overlays, Esc dismisses |
| No-Kerberos state | ✓ Launch disabled, warning prominent |
| Slow scenario (3s jobs) | ✓ Running state visible in dashboard |
| Syntax error scenario | ✓ Failed state, error in log |
