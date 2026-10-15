# TUI Redesign Phase 0: Summary

Phase 0 collects evidence before any redesign work. This page summarises the
five studies below and lists what Phase 1 (the design spec) has to answer. All
measurements are from a headless Textual Pilot on a shared 4-vCPU VM
(Python 3.13, Textual 7.5.0). Treat timings as relative, not absolute.

| Doc | Question it answers |
|---|---|
| [01 Widget inventory](01-widget-inventory.md) | What is on screen, what each field controls, which fields every run needs |
| [02 Journeys and keystrokes](02-journeys-keystrokes.md) | How many keys the main tasks take today, and where people stall |
| [03 Heuristic review](03-heuristic-review.md) | Nielsen's 10 heuristics plus terminal, CSS and copy audits (45 findings) |
| [04 Performance baseline](04-performance-baseline.md) | Where the UI blocks, and the proposed performance budgets |
| [05 Telemetry friction](05-telemetry-friction.md) | What telemetry can and cannot see, and how to pull it |

## Baseline numbers

| Measure | Today |
|---|---|
| Interactive widgets on the main screen | 59 (27 shown at launch) |
| Visible without scrolling | 11 at 120x40, 4 at 80x24 |
| Run button position | Row 110 of the scroll pane, off-screen at both sizes |
| Share run, minimal keyboard path | 49 keys, KLM ≈ 20.6 s |
| Rate run, fraud + accuracy_first | 96 keys, KLM ≈ 35.4 s |
| Re-run after restart | 61 keys (session restore saves nothing) |
| Startup to idle | 1.3–3.1 s, with 0.7–2.4 s UI stalls |
| Keypress-to-idle p95 (Tab between fields) | 0.2–1.5 s |
| Phase 1 budgets missed (`--budget`, 10k rows) | 11 of 15 |

## Cross-cutting findings

1. **The main path is buried.** Run sits off-screen, Share/Rate mode is Tab
   stop 17 of 28, and the log and the scroll container are dead Tab stops.
   Fields every run needs are interleaved with expert fields (19 Advanced
   inputs, duplicate output toggles).
2. **The keyboard model is broken.** Ctrl+A and Ctrl+E are captured by the
   focused `Input` at launch, and Ctrl+A is also the GNU screen and a common
   tmux prefix. Dropdown type-ahead works, but nothing in the UI mentions it.
3. **Compliance moments are fragile in the UI.** Core still enforces every
   privacy rule; none of these weaken it. But the operator can miss
   information or hit dead ends:
   - The validation modal shows 1 of N issues.
   - Consent dialogs open with Confirm focused.
   - Under NO_COLOR, "Blocked" and "Publication withheld" become near-invisible.
   - Raw internal codes (`violations_detected`, `posture=strict`) appear as copy.
4. **There is little feedback during and after a run.** No progress, no
   cancel, raw tracebacks, and toasts pile up over modal buttons. At 80x24 the
   results pane is clipped, so the verdict and report path can't be read.
5. **Performance is lost in a few specific places:**
   - About 233 widgets are mounted up front.
   - Presets are parsed 4 times at startup and again on every Advanced expand.
   - `scipy` is pulled in at import (0.8 s).
   - Tabbing out of the CSV path re-reads the CSV.
   - The picker builds one widget per file (5.5–7 s with 2,000 CSVs).
   - `LogHandler` batching doesn't work (one flush per record).
6. **Telemetry can't see pre-run friction.** The 7 launch guards, CSV load
   errors and validation errors emit nothing, so Phase 2 success metrics need
   either a new enum-only `launch_blocked` event or a proxy.

## Defects found (independent of the redesign)

These are bugs, not design opinions. Each one can be fixed in a small PR
before or during Phase 2.

| # | Defect | Evidence | Severity |
|---|---|---|---|
| D1 | `ValidationModal` lists only the first issue. Rich swallows the `[error]`/`[warning]` prefix, and issue text (which contains column names) is not markup-escaped. With warnings only, Proceed is enabled past unseen warnings. | 03 F29, `tui_app.py:425-430` | 4 |
| D2 | A stale advanced-override file survives a preset change and keeps the old preset's `compliance_posture`. Because the config is set, the accuracy_first consent modal is skipped, and core then blocks with no way to consent. | 01 #2, 03 F16, `tui_app.py:1765, 2293, 2304` | 3 |
| D3 | Consent and clearing-spend dialogs open with Confirm focused, so a single Enter attests. | 02 | 3 |
| D4 | Session restore applies column choices before any CSV is loaded, so they are dropped. Dims and the active tab are lost. | 01 #5, 02 | 2 |
| D5 | The Advanced "Include Debug Sheets" checkbox has no effect; the tab-level checkbox always overrides it. | 01 #4 | 2 |
| D6 | `LogHandler` batching makes one `call_from_thread` per record. | 04 | 2 |
| D7 | The `run_analysis` worker reads widget values from its own thread. | fix agent follow-up | 2 |
| D8 | Entity loading checks the raw `#csv_path` text, while header loading uses `_resolve_csv_path`. A path with surrounding spaces loads headers but no entities. | fix agent follow-up | 1 |
| D9 | `benchmark.py telemetry summary` "Actions" counts attempts twice. | 05 | 1 |

## Fix shipped in Phase 0: entity values load in a background worker

`load_unique_entities` used to read the whole entity column with pandas on the
UI thread. It now runs in an exclusive thread worker that discards stale
results, shows a "Loading entities…" state, and blocks launch only while a
previously chosen entity is waiting to be re-applied, so a run never silently
goes peer-only. Entity selections are still never restored from the session
file; that is an intentional privacy rule, now covered by a test.

Measured with `scripts/tui_perf_probe.py --rows 1000000 --cardinality 50 5000
--repeat 3 --phases csv entity` (`ddea32c` vs this branch). Median, with max in
parentheses:

| 1M rows | Metric | Before | After |
|---|---|---|---|
| 50 entities | UI freeze on entity-column change | 481 ms (483) | 29 ms (44) |
| 50 entities | UI freeze on CSV load | 539 ms (666) | 46 ms (51) |
| 5,000 entities | UI freeze on entity-column change | 551 ms (650) | 29 ms (31) |
| 5,000 entities | UI freeze on CSV load | 582 ms (652) | 57 ms (72) |
| 5,000 entities | Time until entity options appear | 0.56 s | 0.73 s |

The time until options appear is unchanged or slightly longer, because the
worker shares the GIL with the UI thread. What changes is that the UI stays
usable while the list loads. Large lists are still slow inside Textual's
`Select` itself: opening the dropdown takes 0.6 s at 10k options and 5.1 s at
100k. That is a Phase 1 input (see below).

## What Phase 1 must decide

- **Information architecture.** Use 01's every run / sometimes / expert sort.
  Keep compliance-critical fields explicit and visible, and never tucked into
  "expert".
- **Layout.** It must work at 80x24 with no clipped verdict or report path.
  Run must always be reachable in one key.
- **Keyboard map.** Bindings must work regardless of focus and avoid
  `ctrl+a`/`ctrl+e`. Make type-ahead visible and use a command palette.
- **Compliance interaction rules:**
  - Consent dialogs default to Cancel.
  - The validation modal shows every issue with severity text, not colour only.
  - Every status uses a label and a symbol as well as colour (NO_COLOR-safe).
  - Plain-language copy, with internal codes shown as secondary detail.
- **Run experience.** Show stages, allow cancel, keep tracebacks out of the
  main view, and limit how many toasts can stack.
- **Large entity lists.** Use a filtered input with suggestions or a capped
  OptionList above about 2k values.
- **Performance budgets** (the probe's `--budget` defaults, from 04):
  - startup ≤ 1.0 s
  - keypress p95 ≤ 100 ms
  - max UI stall ≤ 100 ms during interaction (500 ms at startup)
  - CSV headers ≤ 0.1 s
  - picker ≤ 0.2 s
- **Success metrics.** Fewer keys for J1, J2 and J3 (02). Telemetry run-intent
  success rate going up while compliance-policy refusals stay flat (05). A
  timed 5-user task test with SUS.

## Reproducing

```bash
uv sync --extra dev --extra release
# Performance baseline (add --repo <path> to probe another checkout)
uv run python scripts/tui_perf_probe.py --rows 10000 100000 1000000 --cardinality 50 5000 --repeat 3
uv run python scripts/tui_perf_probe.py --budget   # exits 1 if over budget
```

The keystroke measurement script is in the appendix of
[02](02-journeys-keystrokes.md). The telemetry pull script and `jq` commands
are in [05 §5](05-telemetry-friction.md). Screenshots from 03 were not committed;
regenerate them with the method described there.
