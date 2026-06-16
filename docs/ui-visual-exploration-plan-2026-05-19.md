# Dispatch TUI Visual Exploration and Test Plan

**Date:** 2026-05-19  
**Scope:** Actual current TUI UI, captured from the running Textual app.  
**Primary methods:** Textual pilot SVG capture, Playwright SVG rasterization to PNG, targeted pilot interaction tests.

---

## 1. Objective

Establish a repeatable visual test loop for the Dispatch TUI that:

1. renders the real current UI,
2. captures representative screen states,
3. converts those renders into reviewable image artifacts,
4. exercises the highest-risk keyboard workflows,
5. produces a screen-by-screen UI/UX assessment.

This plan is for inspection of the real app, not static mockups.

---

## 2. Tooling

### Primary capture path

- **Textual pilot / `run_test()`**
  - source of truth for rendering current screens
  - emits SVG via `app.save_screenshot(...)`
- **Playwright**
  - rasterizes SVGs to PNG for human visual review
- **Pytest pilot tests**
  - validates interaction correctness for selection, pagination, confirmation, and visual closure fixes

### Implemented helper

- `tools/capture_ui_review.py`
  - captures the current representative screen set into:
    - `docs/screenshots/2026-05-19-ui-review/*.svg`

### Rasterization command

```powershell
Get-ChildItem docs\screenshots\2026-05-19-ui-review\*.svg | ForEach-Object {
  $png = [System.IO.Path]::ChangeExtension($_.FullName, '.png')
  npx playwright screenshot --timeout 30000 --viewport-size "1920,1200" ("file:///" + ($_.FullName -replace '\\','/')) $png
}
```

---

## 3. Coverage matrix

The visual pass should always include at least these states:

| Area | Required states |
|---|---|
| Dashboard | populated, empty |
| New Job | default form, legal source/destination controls visible |
| SQL Preview | rendered SQL with current highlight path |
| Job Detail | running job, logs visible, destructive action path validated |
| History | populated list, pagination visible |
| Browser | initial placeholder, tables loaded, drop confirmation modal |
| Global | help modal, global header/footer, focus states |

Current capture set:

1. `01_dashboard_jobs`
2. `02_dashboard_empty`
3. `03_new_job`
4. `04_preview`
5. `05_job_detail`
6. `06_history`
7. `07_browser_initial`
8. `08_browser_loaded`
9. `09_browser_drop_confirm`
10. `10_help`

---

## 4. Review dimensions

Each captured state should be reviewed against the same rubric.

### Layout and hierarchy

- is the primary task obvious?
- is the current context obvious?
- do major panels keep stable placement?
- is unused space acceptable vs. wasteful?

### Focus and keyboard affordance

- is focus visible?
- is selected row vs. focused row understandable?
- are primary bindings discoverable without reading docs?
- is the footer concise enough to parse quickly?

### Readability

- are titles, labels, and status text legible at a glance?
- do long paths or IDs break layout?
- are tables scannable?
- do syntax, logs, and metadata preserve hierarchy?

### Safety and feedback

- are destructive actions gated?
- do disabled or unavailable actions look disabled?
- do warnings explain what action is required?
- do empty states explain the next step?

### Workflow continuity

- can the user move from overview → create → preview → inspect → browse without mode confusion?
- does every screen expose a clear “what next?” action?

---

## 5. Execution sequence

### Step 1: Validate code and UI tests

Run:

```powershell
py -3 -m compileall dispatch scr
py -3 -m dispatch --help
py -3 -m pytest tests\test_ui_snapshots.py tests\test_ui_ux_closure.py tests\test_new_features.py
```

### Step 2: Capture fresh SVGs

Run:

```powershell
py -3 tools/capture_ui_review.py
```

### Step 3: Rasterize to PNG

Use Playwright to convert the SVGs to PNG for visual inspection.

### Step 4: Review screen-by-screen

For each PNG:

1. inspect first-pass visual hierarchy,
2. inspect focus visibility,
3. inspect primary action clarity,
4. inspect text overflow and density,
5. inspect empty/error/destructive affordances.

### Step 5: Record issues by severity

Severity buckets:

- **P0** safety / destructive / misleading behavior
- **P1** primary workflow friction
- **P2** clarity / navigation / consistency defects
- **P3** polish only

### Step 6: Convert findings into implementation checkpoints

Recommended checkpoint order:

1. global chrome and layout correctness
2. dashboard and history selection/readability
3. new-job form clarity and launch affordance
4. job-detail observability
5. browser metadata readability and action states
6. footer/help density polish

---

## 6. Acceptance criteria for a “good” visual pass

A visual review is complete only if:

- captures came from the current app, not mockup files,
- every core screen has at least one representative artifact,
- destructive flows were visually inspected,
- at least one empty state and one populated state were reviewed,
- findings were documented with file/state references,
- the report distinguishes real product issues from screenshot-fixture artifacts.

---

## 7. Known constraints

- Textual SVGs are authoritative for structure but not perfect substitutes for SSH terminal ergonomics.
- Review images were captured at a large viewport; narrow-terminal follow-up remains a separate pass.
- Mocked data can introduce artifacts, especially timestamps and long temp paths; those must be called out explicitly rather than misclassified as product defects.
