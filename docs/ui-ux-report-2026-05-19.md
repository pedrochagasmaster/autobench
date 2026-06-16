# Dispatch TUI UI/UX Report

**Date:** 2026-05-19  
**Method:** Current-app SVG capture via Textual pilot, PNG rasterization via Playwright, manual review of rendered screens.  
**Artifacts reviewed:** `docs/screenshots/2026-05-19-ui-review/01` through `10`.  
**Validation run:** `compileall`, `dispatch --help`, and the focused UI test suites all passed on 2026-05-19.

---

## Executive summary

The TUI is materially safer and more usable than the earlier screenshot-review baseline. The highest-value improvements are present:

- destructive browser actions now require typed confirmation,
- preview semantics are no longer misleading,
- history pagination exists,
- browser empty/detail states are clearer,
- keyboard help exists,
- row selection is visually present in tables.

That said, the current UI still has several meaningful issues in the actual rendered product:

### Most important current issues

1. **Duplicate top-level chrome is being rendered**: the app header is effectively shown twice on normal screens.
2. **Job Detail is layout-brittle**: long paths can consume the summary panel and push live logs out of view.
3. **New Job still has an awkward form layout**: hidden fields leave a sparse, misaligned form; radio focus vs. selected state is visually confusing.
4. **Dashboard empty state is functional but still table-row-shaped** instead of a true guided empty-state panel.
5. **Action availability is not always visually truthful**: buttons such as Browser `DESCRIBE` / `DROP` appear actionable even when no selection exists.

Overall status:

- **Safety:** good
- **Keyboard-first usability:** good
- **Layout consistency:** mixed
- **Readability and density:** mixed
- **UI polish:** adequate, not finished

---

## What is working well

### 1. Safety posture is substantially better

Evidence:

- `09_browser_drop_confirm.png`
- tested by `tests/test_ui_ux_closure.py`

What changed well:

- destructive browser actions now use a real modal,
- typed confirmation is explicit and strong enough for irreversible actions,
- modal copy is direct and clear.

Assessment:

- this is the biggest UX/safety improvement in the product.

### 2. SQL Preview is now honest and readable

Evidence:

- `04_preview.png`

What works:

- preview is clearly a review step,
- `Accept & Return` is semantically correct,
- syntax highlighting and line numbers materially improve scanability,
- breadcrumb context is clear.

### 3. Browser empty and loaded states are understandable

Evidence:

- `07_browser_initial.png`
- `08_browser_loaded.png`

What works:

- initial detail pane now explains what to do,
- loaded state auto-fills the right pane,
- split-pane model is stable and appropriate for metadata browsing.

### 4. History is much more usable than before

Evidence:

- `06_history.png`
- tested by `tests/test_ui_ux_closure.py`

What works:

- row selection is visible,
- keyboard page navigation exists,
- page info is legible,
- table scanability is reasonable.

### 5. Help is now discoverable and real

Evidence:

- `10_help.png`

What works:

- `?` is no longer a phantom affordance,
- shortcut inventory is readable,
- grouping by screen is the right model.

---

## Findings by screen

## 1. Dashboard

Evidence:

- `01_dashboard_jobs.png`
- `02_dashboard_empty.png`

### Strengths

- operational summary cards are compact and readable,
- row highlight makes table selection visible,
- active vs. recent split is easy to understand,
- primary actions are centered and obvious.

### Findings

| ID | Severity | Finding |
|---|---|---|
| DASH-01 | High | **Duplicate top header**. The current render shows the app title twice at the top, which wastes vertical space and makes the chrome feel broken. |
| DASH-02 | Medium | **Empty state is still rendered as a table row**. It is improved copy-wise, but still looks like data rather than a purpose-built empty state. |
| DASH-03 | Medium | **Footer density is high**. Sidebar help, footer bindings, and the command-palette hint compete at the bottom of the screen. |
| DASH-04 | Low | **Event trail placement is weak**. The single-line event feed sits between tables and buttons without clear panel framing. |

### Notes

The negative elapsed times shown in the review capture are a fixture artifact caused by seeded future timestamps, but they also expose a real resilience gap: the UI does not guard against future/clock-skew timestamps gracefully.

---

## 2. New Job

Evidence:

- `03_new_job.png`

### Strengths

- legal-cell matrix is clear,
- source and destination are constrained controls rather than free text,
- inline validation is present,
- top-line Kerberos status is explicit.

### Findings

| ID | Severity | Finding |
|---|---|---|
| NJ-01 | High | **Form layout is still awkward after field hiding**. The lower half becomes sparse and visually disconnected because labels remain on the left and inputs stack on the right with large empty gaps. |
| NJ-02 | High | **Radio focus vs. selected state is confusing**. In the screenshot, the destination group shows one row highlighted while a different row carries the selected dot. That is technically correct but visually ambiguous. |
| NJ-03 | Medium | **Long SQL file paths are not handled well**. The file path is clipped hard inside the input and dominates the field. |
| NJ-04 | Medium | **Disabled launch affordance is not visually strong enough**. With low Kerberos, the screen explains the problem, but the launch button still reads as active at a glance. |
| NJ-05 | Low | **The matrix remains visually expensive** for a screen whose core task is form completion. |

### Assessment

This screen is functionally much better than before, but it still needs a layout pass rather than another validation pass.

---

## 3. SQL Preview

Evidence:

- `04_preview.png`

### Strengths

- best-composed screen in the product,
- strong focus on one task,
- line numbering + color treatment work well,
- button copy is correct.

### Findings

| ID | Severity | Finding |
|---|---|---|
| PREV-01 | Low | **There is a lot of unused body space for short SQL**. Not wrong, but the screen feels oversized for small queries. |
| PREV-02 | Low | **Footer duplication remains** because the global chrome pattern is still heavy. |

### Assessment

No major UX blocker here.

---

## 4. Job Detail

Evidence:

- `05_job_detail.png`

### Strengths

- breadcrumb is clear,
- summary labels are understandable,
- cancel action is now isolated by color and confirmation flow.

### Findings

| ID | Severity | Finding |
|---|---|---|
| JD-01 | Critical | **Live logs are effectively absent in the reviewed render**. The summary panel expands enough that the log panel is pushed below the fold or visually collapsed. This breaks the main purpose of the screen. |
| JD-02 | High | **Long source and CSV paths blow up the summary layout**. Absolute paths wrap aggressively and consume scarce vertical space. |
| JD-03 | Medium | **Summary density is low relative to screen size**. A large bordered panel holds relatively little signal while the important live region loses space. |
| JD-04 | Medium | **Elapsed-time rendering should defend against clock skew**. The current behavior can show negative elapsed values when timestamps are ahead of local render time. |

### Assessment

This is currently the weakest main workflow screen. The product promise here is “inspect the running job and its logs,” and the current layout does not reliably privilege the logs panel.

---

## 5. History

Evidence:

- `06_history.png`

### Strengths

- keyboard path is clear,
- pagination state is visible,
- scanability is decent,
- search placement is correct.

### Findings

| ID | Severity | Finding |
|---|---|---|
| HIST-01 | Medium | **Bottom controls are still busy**. Page text, action buttons, and footer bindings all compete in the same band. |
| HIST-02 | Low | **The search field does not advertise scope clearly enough** beyond the placeholder. |
| HIST-03 | Low | **Long IDs still dominate the first column** even after truncation improvements. |

### Assessment

Usable and materially improved. No blocking issue.

---

## 6. Browser

Evidence:

- `07_browser_initial.png`
- `08_browser_loaded.png`
- `09_browser_drop_confirm.png`

### Strengths

- best information architecture after Preview,
- placeholder copy is good,
- selection state is obvious,
- confirmation flow is strong.

### Findings

| ID | Severity | Finding |
|---|---|---|
| BR-01 | Medium | **`DESCRIBE` and `DROP` appear active even when there is no selection** in the initial state. No-op actions should usually be visibly disabled. |
| BR-02 | Medium | **The DESCRIBE rendering is still a faux table**. It is more readable than raw pipes, but comments visually fall below names, which makes the structure weaker than a real three-column table widget. |
| BR-03 | Low | **`SHOW TABLES` visually dominates the left pane** more than necessary after initial load. |

### Assessment

Strong overall. The remaining work is mostly action-state truthfulness and metadata presentation quality.

---

## 7. Help modal

Evidence:

- `10_help.png`

### Strengths

- real and useful,
- consistent visual treatment,
- keyboard-first framing is correct.

### Findings

| ID | Severity | Finding |
|---|---|---|
| HELP-01 | Low | **The modal is dense and scroll-heavy**. Good for completeness, but not ideal for quick lookup under pressure. |

---

## Cross-cutting findings

| ID | Severity | Finding |
|---|---|---|
| X-01 | High | **Global chrome duplication**. Normal screens visually render duplicate title/header chrome. This is the highest-value non-safety fix now. |
| X-02 | High | **Bottom-of-screen information density is too high**. Sidebar footer copy, Textual footer bindings, and palette hint collectively create clutter. |
| X-03 | Medium | **Long path handling needs productized truncation rules**. Inputs and summary fields should preserve useful suffixes instead of raw full-path wrapping. |
| X-04 | Medium | **Several screens rely on no-op buttons instead of disabled buttons** when prerequisite context is missing. |

---

## Priority order for follow-up implementation

### P0

1. Fix duplicate header/global chrome composition.
2. Rework Job Detail so the log panel always remains visible and dominant.

### P1

3. Re-layout New Job field groups after conditional field hiding.
4. Clarify radio selected-state vs. focused-state visuals.
5. Disable Browser actions when no table is selected.

### P2

6. Replace dashboard table-row empty states with real empty-state panels.
7. Reduce footer/bottom chrome clutter.
8. Improve long-path display rules across inputs and summaries.
9. Consider rendering Browser DESCRIBE output with a real `DataTable`.

---

## Validation evidence

Commands run:

```powershell
py -3 -m compileall dispatch scr
py -3 -m dispatch --help
py -3 -m pytest tests\test_ui_snapshots.py tests\test_ui_ux_closure.py tests\test_new_features.py
py -3 tools/capture_ui_review.py
```

Additional artifact generation:

```powershell
Get-ChildItem docs\screenshots\2026-05-19-ui-review\*.svg | ForEach-Object {
  $png = [System.IO.Path]::ChangeExtension($_.FullName, '.png')
  npx playwright screenshot --timeout 30000 --viewport-size "1920,1200" ("file:///" + ($_.FullName -replace '\\','/')) $png
}
```

Result:

- focused UI suites passed,
- current screenshots were captured successfully,
- PNG review artifacts were generated successfully.

---

## Bottom line

The product has crossed the threshold from “prototype with obvious UX hazards” to “usable TUI with a few real layout defects still remaining.” The next work should stop chasing feature breadth and instead close the remaining actual-render issues:

1. duplicated chrome,
2. weak Job Detail layout,
3. awkward New Job layout,
4. action-state truthfulness,
5. bottom-of-screen clutter.
