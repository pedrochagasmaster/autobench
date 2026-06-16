# UI/UX Closure Handoff — 2026-05-17

This document is for the next agent picking up the Dispatch UI/UX closure work after PR #12.

## Current state

- Branch state to start from: `main`
- PR already merged: [#12](https://github.com/pedrochagasmaster/robocop/pull/12) `Polish remaining UI closure interactions`
- Main now includes:
  - stronger Browser `DROP TABLE` confirmation
  - Browser right-pane placeholder and first-table auto-describe
  - working History pagination via `[` / `]`
  - History `Enter` using the full durable row key instead of the truncated visible ID
  - focused regression coverage for those interactions

## Source documents

Read these first:

1. `AGENTS.md`
2. `CONTEXT.md`
3. `.agents/skills/dispatch-textual-tui/SKILL.md`
4. `docs/ui-ux-screenshot-review-2026-05-16.md`
5. `docs/prototype-to-production-plan.md`
6. `docs/goal-ui-ux-closure-loop.md`

## What was addressed already

These high-value findings are already materially improved in code:

- `BD-1`: Browser `DROP TABLE` now requires typing the exact full table name.
- `B-1`: Browser no longer shows a blank detail pane on initial load.
- `BT-1`: Browser auto-describes the first loaded table after `SHOW TABLES`.
- `H-1`: History paging works with keyboard bindings.
- `H-2`: History row action uses the full job ID instead of the truncated visible cell.
- `JD-1`: Cancel Job confirmation exists.
- `SP-1`: Preview no longer pretends to launch the job directly.
- `NJ-1`: Source/Destination are no longer free-text.
- `NJ-3`: Date defaults are dynamic for the current month.
- `E-1`: Dashboard empty state is no longer a meaningless `(none)` row.

## Remaining work

Treat this as bounded polish, not a new broad rewrite.

### Preview

- `SP-2`: add SQL syntax highlighting
- `SP-3`: footer metadata should reflect the actual source/destination context

### New Job

- `NJ-2`: form/tab-flow polish; current grid can still be improved
- `NJ-4`: info/warning copy is still generic
- `NJ-5`: email guidance and validation feedback are still minimal
- `NJ-6`: matrix still consumes a lot of vertical space
- `NJ-7`: persist last-used form defaults instead of hardcoding schema/email-related defaults
- production-plan follow-up:
  - dim/disable Launch when Kerberos is missing or TTL < 5 minutes
  - inline field validation markers

### Feedback / discoverability

- implement `?` help or remove any hint that implies it exists
- add toast notifications where inline warning text is currently easy to miss

### Browser

- `BT-2`: improve filter placeholder copy
- `B-3`: remove or enrich the static `Type` column
- `BD-2`: render `DESCRIBE` output in a more structured format than numbered raw lines
- `BD-3`: reduce duplicated detail-header information

### History

- `H-3`: filtering is still basic substring search
- `H-4`: IDs are still truncated visually
- `H-5`: no sorting support
- page controls are still static text, even though keyboard paging works

### Job Detail / Dashboard

- `JD-2`: improve elapsed-time presentation in Job Detail
- `JD-3`: visually separate timestamps in logs
- `JD-4`: conditionally present CSV path more clearly
- `JD-5`: safer visual separation between Cancel and Back
- `D-1`, `D-3`, `D-5`, `D-6`: dashboard copy/affordance polish remains

## Files most likely to change next

- `dispatch/app.py`
- `dispatch/screens/dashboard.py`
- `dispatch/screens/new_job.py`
- `dispatch/screens/preview.py`
- `dispatch/screens/job_detail.py`
- `dispatch/screens/history.py`
- `dispatch/screens/browser.py`
- `dispatch/config.py`

## Tests already added for this line of work

- `tests/test_phase1_safety.py`
- `tests/test_ui_ux_closure.py`

The current focused coverage proves:

- Browser typed-drop confirmation is enforced
- confirm-button path does not bypass typed confirmation
- Browser placeholder + auto-describe behavior works
- History paging works
- History `Enter` resolves the full row-key job ID

## Validation baseline

Before claiming completion on any follow-up checkpoint, run:

```bash
PYTHONPATH=. .venv/bin/python -m compileall dispatch scr
PYTHONPATH=. .venv/bin/python -m dispatch --help
PYTHONPATH=. .venv/bin/pytest -q
source mocks/dev-env.sh
DISPATCH_MOCK_SCENARIO=happy_path .venv/bin/python -m dispatch
```

For UI-only smoke work, use a timeout if you only need to confirm startup:

```bash
source mocks/dev-env.sh
DISPATCH_MOCK_SCENARIO=happy_path timeout 5s .venv/bin/python -m dispatch
```

## Recommended next order

1. Preview syntax/highlighting + footer metadata
2. New Job inline validation + persisted defaults + Launch disabled on missing Kerberos
3. Help/toast discoverability work
4. Browser `DESCRIBE` rendering and low-friction copy cleanup
5. Job Detail and Dashboard presentation polish

## Notes for the next agent

- Stay within Dispatch v1.0 invariants from `AGENTS.md` and `CONTEXT.md`.
- Do not touch `scr/` unless a requirement truly forces it.
- Prefer focused checkpoints with tests added first.
- Do not assume passing tests cover the screenshot-review requirements; audit against the issue IDs directly.
