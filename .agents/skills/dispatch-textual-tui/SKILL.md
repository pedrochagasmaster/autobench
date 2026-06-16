---
name: dispatch-textual-tui
description: Build and review Dispatch Textual TUI changes with production-safe UI, performance, design-system, and mock-development discipline.
---

# Dispatch Textual TUI skill

Use this skill for any work touching the Dispatch terminal UI, including `dispatch/app.py`, `dispatch/screens/`, `dispatch/widgets/`, `dispatch/process.py`, `dispatch/runner.py`, job manifests, local mocks, UI styling, and interaction tests.

Dispatch is a server-side Textual TUI for launching and supervising Impala jobs from a Hadoop Edge Node. Users run `dispatch` from the directory containing SQL files. Jobs must survive terminal disconnects because the detached runner, not the TUI process, owns orchestrator execution.

This skill consolidates project-specific Dispatch rules with the strongest external TUI guidance found in skill registries:

- `skills.sh/johnlarkin1/claude-code-extensions/textual`: concise Textual lifecycle, data-flow, worker, and testing patterns.
- `skills.sh/aperepel/textual-tui-skill/textual-tui`: strongest worker/thread-safety and production Textual coverage.
- `skills.sh/ypares/agent-skills/textual-builder`: best reference-routing structure for basics, widgets, layout, styling, and interactivity.
- `skills.sh/kyleking/vcr-tui/textual`: strongest compact Textual coding-practice checklist.
- `skills.sh/hyperb1iss/hyperskills/tui-design`: strongest opinionated framework-agnostic terminal design system.
- `skills.sh/tristanmanchester/agent-skills/textual-tui`: checked, but the accessible mirrored repo did not contain a Textual skill.

The Dispatch product invariants below override any generic outside guidance.

## Read first

Before editing, read:

1. `README.md`
2. `AGENTS.md`
3. `docs/adr/` if present
4. `dispatch/app.py`
5. The relevant file in `dispatch/screens/` or `dispatch/widgets/`
6. `dispatch/process.py`, `dispatch/runner.py`, and `dispatch/models.py` before touching process, job, or manifest behavior
7. `mocks/dev-env.sh` and `mocks/scenarios/` before changing local development flows

Do not rely on old Windows GUI assumptions. The legacy PowerShell GUI is removed from the v1.0 product direction.

## Product invariants

Keep these invariants intact:

- The TUI is a supervisor and launcher, not the durable job owner.
- The launch-time current working directory is captured once and used for CSV destinations for the session.
- Job state is stored in manifests under the configured Dispatch data root.
- CSV outputs for CSV and Table + CSV jobs are plain, uncompressed files in the user's launch-time working directory.
- Table + CSV jobs are decomposed into table creation followed by a separate CSV export.
- The TUI must hard-refuse invalid source/destination combinations, missing Kerberos tickets, tickets with less than five minutes remaining, and more than two simultaneous Running jobs.
- `scr/` orchestrator changes are high risk. Do not change them unless the task explicitly requires it and the ADRs allow it.

## Opinionated design target

Dispatch should feel like a focused terminal IDE, not a dressed-up script menu.

Primary layout paradigm:

- Use an IDE three-panel / persistent multi-panel model for the core app: stable sidebar or navigation zone, primary work area, and detail/log/preview zone.
- Preserve spatial consistency. Panels should keep their role and position across screens so users build muscle memory.
- Use header + scrollable list patterns for history, logs, and job tables.
- Use drill-down navigation only for deep objects such as job detail, file preview, or nested manifest/log inspection.

Design principles:

- Keyboard-first, mouse-optional. Every feature must be reachable without a mouse.
- Spatial consistency over clever rearrangement.
- Progressive disclosure: footer shows only essential shortcuts, `?` or help surfaces the full context-specific map.
- Async everything. The UI must show feedback quickly and never freeze on process, file, or log operations.
- Semantic color. Color communicates state, not decoration.
- Contextual intelligence. Footer/help/actions should reflect the active panel and current mode.
- Design in layers: monochrome usable first, 16 ANSI readable second, richer color only as enhancement.

## Textual architecture rules

Prefer this structure:

- `dispatch/app.py` owns the app shell, global bindings, theme/CSS registration, launch CWD capture, and startup routing.
- `dispatch/screens/*.py` own screen-level layout, bindings, and orchestration.
- `dispatch/widgets/*.py` own reusable visual components.
- Service/process logic stays outside widget code.
- Long-running work runs through async-safe helpers, Textual workers, or background-safe process abstractions. Never block the Textual event loop with `subprocess.run`, long file scans, sleep loops, network calls, or heavy computation inside event handlers.

Use Textual-native primitives first:

- `Screen`, `App`, `ComposeResult`, `Header`, `Footer`
- `DataTable`, `RichLog`, `Input`, `Button`, `Static`, `Label`, `Tree`, `MarkdownViewer`, `TabbedContent`, `ProgressBar` when appropriate
- `BINDINGS`, actions, and the command palette for keyboard-first workflows
- reactive state for UI state that affects rendering
- `set_interval`, timers, or workers for refresh loops, with cleanup on unmount

Component communication:

- Prefer attributes down, messages up.
- Parent screens configure child widgets through constructor arguments or attributes.
- Child widgets communicate user intent through typed Textual messages, not direct parent mutation.
- Keep business rules in services/models; widgets should render, validate immediate input, and emit intent.
- Use selector-filtered handlers or dedicated message classes for repeated widgets instead of brittle ID branching.

Lifecycle rules:

- `__init__`: assign immutable constructor inputs and call `super().__init__()`; do not trigger expensive work.
- `compose`: build child widgets only.
- `on_mount`: safe place for focus setup, intervals, reactive initialization, and first refresh.
- `on_show` / `on_hide`: use for screen visibility refresh or pause/resume behavior.
- `on_unmount`: stop intervals, cancel workers, close file handles, and release tailers/watchers.
- Avoid modifying reactives directly in `__init__`; use `set_reactive` or initialize in `on_mount`.

Reactive-state rules:

- Use `reactive()` for state that directly affects the rendered UI.
- Use non-refreshing internal state for caches, raw data snapshots, or values that should not trigger repaint.
- Use validators to constrain state, such as selected index bounds or percentage ranges.
- Use watchers to update child widgets or CSS classes; keep watchers fast and side-effect-light.
- If footer bindings depend on state, wire that state so bindings refresh predictably.

## Styling and visual system

The app keeps its stylesheet in `dispatch/app.tcss` (loaded via `CSS_PATH`). Keep styling changes there; do not reintroduce an inline `APP_CSS` block in `app.py`. The stylesheet doubles as the design system: quiet base colors, accent reserved for focus/selection/primary actions, semantic state colors only, and a shared `.action-bar` pattern for the docked bottom bar on every screen.

Style for a production SSH terminal:

- Do not optimize only for screenshots. It must remain readable over SSH, small terminals, and limited color themes.
- Preserve keyboard focus clarity.
- Keep status, errors, warnings, running, queued, and success states visually distinct.
- Avoid decorative elements that reduce density or legibility.
- Use Textual theme variables and semantic classes where possible; use hard-coded colors sparingly and consistently.
- Ensure narrow terminal fallbacks do not hide critical controls.

Semantic color rules:

- Define color by purpose: default text, muted metadata, emphasis, selection, primary accent, success, warning, error, info.
- Never rely on red vs green alone. Pair status color with labels, symbols, position, or typography.
- Respect `NO_COLOR` where practical. The interface must remain understandable without color.
- Use bold/dim/border/focus state as part of hierarchy; color is not the whole hierarchy.
- Keep roughly 80% of content visually quiet. Reserve accent colors for focus, actions, and state.

Chrome rules:

- Borders must clarify grouping or focus; they are not decoration.
- Prefer background layering and whitespace where borders create clutter.
- Use stable titles for panels so users always know the active context.
- Logs and tables should prioritize density and scanability over visual flair.
- Use CSS classes for state (`running`, `failed`, `queued`, `selected`, `stale`) rather than building styled strings everywhere.

## Responsive terminal rules

Terminals resize and Dispatch runs over SSH. Handle it gracefully.

- Define a usable minimum, normally around 80x24. Below it, show a clear resize message instead of a broken layout.
- Test or reason through 80x24, 120x40, and wide terminals.
- Use proportional/flexible constraints (`1fr`, ratios, min/max heights) instead of absolute layouts where possible.
- Collapse by priority: hide or compress secondary preview/detail zones before hiding primary actions/status.
- Never allow resize to crash, lose focus, or corrupt displayed state.
- Keep critical state visible on small terminals: current screen, selected job/file, primary action, and error/status line.

## Interaction model

Keyboard layers:

- L0 universal keys: arrows, Enter, Esc, q, Tab. These should be visible in footer/help.
- L1 fluent keys: `/` search, `?` help, `j/k` movement where natural, `g/G` top/bottom where tables/logs support it.
- L2 context actions: mnemonic single keys for launch, cancel, refresh, open detail, copy path, inspect logs.
- L3 power actions: command palette or typed commands for less common actions.

Keybinding rules:

- Do not steal terminal-reserved signals such as Ctrl+C, Ctrl+Z, or Ctrl+\\.
- `Tab` and `Shift+Tab` should move focus predictably between panels.
- The focused panel must be obvious through border, color, cursor, or title state.
- Context-sensitive footer text should show only actions available now.
- `?` should show current-screen help, not a global wall of unrelated actions.
- Keep bindings stable; do not make the same key mean incompatible things across nearby screens.

Search and filtering:

- `/` should open search or filter where lists, logs, or tables are central.
- Search should update results live when feasible.
- Show match count and current match where applicable.
- `Esc` exits search/filter mode without losing the previous selection.
- For exact matching, prefer a documented prefix or command-palette action rather than hidden behavior.

Dialogs and confirmations:

- Reversible actions may show a status-bar confirmation.
- Moderate destructive actions require inline confirmation.
- Severe or irreversible actions require a modal confirmation that names the exact resource.
- Modal dialogs must trap focus and make the exit path clear.

## Data display rules

Tables:

- Align numbers right and text left.
- Keep columns stable across refreshes.
- Truncate long values with an ellipsis and expose the full value in detail/preview.
- Preserve selection across refresh when the underlying row still exists.
- Avoid wholesale table rebuilds when only a few rows changed.
- Keep row keys tied to durable identifiers such as job IDs, not transient row indexes.

Logs:

- Use timestamp + level + message consistently.
- Use level labels even when color is unavailable.
- Tail by default; provide a clear way to pause/follow if implemented.
- Cap displayed log history unless the user explicitly asks for more.
- Never load multi-MB logs synchronously into the UI thread.
- Show truncation or sampling explicitly; never silently omit relevant failures.

Progress and loading:

- Use spinners for indeterminate operations after a short delay so fast operations do not flicker.
- Use progress bars only when determinate progress exists.
- Always show what operation is running and whether it can be cancelled.
- Surface worker or process errors both in a concise status area and in a detail/log area.

## Worker and thread-safety rules

Always use workers or async-safe helpers for:

- subprocess calls
- network requests
- file I/O and filesystem walks
- database or Impala interactions
- log tailing
- CPU-intensive parsing/formatting
- anything likely to take more than roughly 100ms

Worker discipline:

- Use `exclusive=True` to prevent duplicate refresh/fetch workers where stale runs are harmful.
- Name workers for debugging.
- Group related workers when batch cancellation is needed.
- Store worker references when the user can cancel the operation.
- Cancel workers on screen exit when their result no longer matters.
- Ignore stale worker results if the user navigated away or selected a different job.
- Handle worker success, cancellation, and failure explicitly.

Thread safety:

- Never mutate widgets directly from thread workers.
- Use `call_from_thread()` or a main-thread callback for UI updates from thread workers.
- Prefer immutable result snapshots returned by workers instead of shared mutable state.
- Clean up files, subprocess handles, and locks in `finally` blocks.

## Performance rules

Performance is part of the UI contract.

- Do not re-read every manifest or full log file on every paint.
- Prefer incremental refreshes and cached parsed state with explicit invalidation.
- For log display, tail only the necessary window unless the user requests full history.
- Avoid rebuilding large `DataTable`s wholesale if only a few rows changed.
- Keep dashboard refresh work bounded and cancellable.
- Large file previews must cap bytes/lines and clearly show truncation.
- Avoid synchronous filesystem walks in event handlers.
- Cache expensive formatting/rendering where practical.
- Use immutable snapshots for data passed into widgets so refreshes are predictable.
- Batch UI updates when processing multiple changes.

## Code quality rules

Composition over inheritance:

- Build screens from small focused widgets rather than one giant screen class.
- Extract repeated panels, rows, cards, or status elements into widgets.
- Avoid introducing generic abstractions until at least two concrete usages exist.

Async correctness:

- Await async Textual APIs such as mounting/removal when required by the API.
- Use workers or async-safe process helpers for subprocesses, file reads, and polling.
- Surface worker failure to the UI with an actionable message.
- Cancel or ignore stale worker results when the user leaves the screen.
- Use `await asyncio.sleep()` in async code, never `time.sleep()` on the UI path.

Testing discipline:

- Prefer Textual `run_test()` / pilot-style tests for UI behavior.
- After `pilot.press()` or `pilot.click()`, pause before asserting state when message processing is involved.
- Test state and widget contents, not brittle terminal escape output.
- Add regression tests for keybindings, focus movement, illegal combinations, and worker error display when test infrastructure exists.

Debugging discipline:

- Use Textual devtools/console logging during development.
- Prefer structured logs with relevant locals over print debugging.
- Remove noisy debug logs before merging unless they are intentionally part of operational logging.

## Reference-routing hints

When an agent is unsure, consult the relevant kind of reference before changing code:

- Basics: app structure, reactivity, watchers, widget querying, messages, and event propagation.
- Widgets: widget catalog, custom widgets, `DataTable`, `RichLog`, `Input`, `Button`, and containers.
- Layout: vertical/horizontal/grid, docked areas, scrolling, sizing, and responsive behavior.
- Styling: selectors, semantic classes, borders, theme variables, focus and hover states.
- Interactivity: key bindings, action methods, dynamic bindings, mouse events, focus movement, and notifications.
- Workers: cancellation, progress, error handling, thread-safe UI updates, and worker groups.

## Mock-development rules

Local development must work without Hadoop, Kerberos, SMTP, or `/ads_storage/` by using mocks.

Recommended local flow:

```bash
source mocks/dev-env.sh
export DISPATCH_MOCK_SCENARIO=happy_path
python -m dispatch
```

Exercise at least these scenarios when touching launch, status, log, or error UI:

- `happy_path`
- `all_queues_full`
- `memory_exceeded`
- `syntax_error`
- `auth_error`
- `slow`

When behavior differs between mock and Edge Node, document it in the PR.

## Validation checklist

Before proposing a PR, run the strongest available subset:

```bash
python -m compileall dispatch scr
source mocks/dev-env.sh
DISPATCH_MOCK_SCENARIO=happy_path python -m dispatch
```

If automated Textual tests exist or are added, prefer:

```bash
pytest
```

For TUI behavior tests, use Textual's test pilot style rather than brittle terminal-output string comparisons. Validate at least:

- the app starts
- keyboard navigation works
- illegal launch combinations are refused
- mock scenarios surface clear status/errors
- running jobs do not block UI interaction
- narrow terminal layouts remain usable
- `NO_COLOR` or low-color terminals remain understandable where practical
- resize does not crash or hide critical controls
- worker cancellation/error paths are visible and recoverable

Manual compatibility checklist for UI-heavy changes:

- 80x24 minimum terminal remains usable or shows a clear resize message.
- 120x40 and wide terminals use space productively.
- All primary actions are keyboard-accessible.
- Focus is always visible.
- SSH/tmux-style usage is considered.
- Mouse support, if added, does not replace keyboard support.

## Review checklist

A Dispatch TUI PR is not ready if it:

- blocks the event loop
- changes job durability semantics
- writes CSVs outside the launch-time CWD without explicit product approval
- hides Kerberos or queue/pool failure reasons
- changes `scr/` casually
- adds UI polish without testing it in a mock scenario
- relies on local-only paths or corporate-only paths without fallbacks
- creates a screenshot-perfect layout that breaks over SSH or narrow terminals
- uses color as the only indicator of meaning
- introduces undiscoverable keybindings with no footer/help path
- rebuilds tables/logs in a way that will degrade with realistic job history volume
- mutates widgets from worker threads
- leaves workers running after the screen that owns them exits

## Output expectations for agents

When reporting work, include:

- files changed
- behavior changed
- validation run and result
- mock scenario used
- terminal/layout assumptions tested or reasoned through
- known gaps, especially anything requiring real Edge Node smoke testing
