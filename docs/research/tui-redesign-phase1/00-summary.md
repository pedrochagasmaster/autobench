# TUI Redesign Phase 1: Summary and Phase 2 Plan

Phase 1 is a design spec. No production code changed. Every layout and
performance claim was checked with a throwaway Textual 7.5 prototype or a
micro-benchmark. The prototypes and screenshots stayed out of the repo; how
to regenerate them is described in each doc.

| Doc | Owns |
|---|---|
| [01 Interaction design](01-interaction-design.md) | Model, information architecture, 33 wireframes (80x24 and 120x40), keyboard map, states, compliance interaction rules, run experience, session restore, projected keystrokes |
| [02 Visual system](02-visual-system.md) | Design tokens (`.tcss`), status language, NO_COLOR/ANSI rules, checkbox affordance, density, copy guidelines and glossary |
| [03 Performance architecture](03-performance-architecture.md) | Fix per Phase 0 hotspot with measured effect, threading rule, final budgets, CI wiring for the probe |

## The design in one paragraph

One main screen with a **non-gated step rail** (Data → Entity → Analysis &
mode → Privacy & compliance → Review & run) as a single row at every width.
The active step shows only the fields every run needs, with "More options"
and a separate Expert settings screen (F8) for the rest. Compliance
declarations stay on the Privacy step, marked as never remembered. A one-row
**action bar** always shows readiness and the Run key. Results live in a
side column at 110+ columns and in a `^T` view below that, so the verdict and
report path are readable at 80x24. Consent and clearing-spend prompts come
after validation, follow the effective posture, and open with Cancel focused.

## Where the docs disagree, and what wins

| Topic | 01 says | 02/03 say | Decision |
|---|---|---|---|
| Status glyphs | `⏵` running, `⚠` attention, READY as a word, WITHHELD with `✗` | `▸`, `▲`, `●`, `◐`, each with an ASCII fallback | **02 wins.** Its set was verified under NO_COLOR and `textual-ansi`; 01's wireframes are illustrative. |
| Footer | Stock `Footer` content per context (01 §4.4) | App-owned key bar (03 §2): the stock Footer recomposes on every focus change and renders black-on-black under `textual-ansi` (02 §1.5) | **App-owned key bar**, showing the per-context content listed in 01 §4.4. |
| Running-state cancel | Cancel only before the engine starts; "Cancel n/a" afterwards | Same limit; an engine hook would be needed | Keep the limit. Replace the "Cancel n/a" label with a plain stage message until the owner answers Q1 below. |

## Projected outcomes

| Measure | Phase 0 baseline | Phase 1 projection | Source |
|---|---|---|---|
| Share run (J1) | 49 keys, 20.6 s | 40 keys, 18.8 s | 01 §9 |
| Rate run, fraud (J2) | 90 keys, 31.5 s | 62 keys, 25.9 s | 01 §9 |
| Re-run after restart (J3) | 61 keys, 20.3 s | 41 keys, 16.3 s | 01 §9 |
| Startup to idle | 1.16 s (same-session median) | 0.38 s | 03 §1 |
| Tab p95 | 313 ms | 44–55 ms | 03 §2 |
| Picker, 2,000 files | 9.2 s | 0.18 s | 03 §4 |
| 5,000 log records | 3.4–5.4 s | 0.14–0.21 s | 03 §5 |
| NO_COLOR at 80x24 | Status and checkbox state unreadable | All 12 states readable (glyph + word, reverse badges) | 02 §2.3 |

## What this needs outside `tui_app.py`

- **`core/`.** Two optional changes, both additive or behaviour-neutral.
  First, a lazy `core/__init__.py` facade, which saves about 0.3 s of import;
  the full suite passes with it. Second, a pure-data `core/labels.py` for the
  copy glossary. Engine-stage progress or cancel would need a hook in
  `execute_run`, which is open question 1.
- **Packaging.** The new `tui/styles/autobench.tcss` needs `pyproject`
  package-data and an `edge_deploy.yaml` `runtime_paths` entry. The
  `edge_deploy.yaml` change is a **Release Operator** step (AGENTS.md).
- **Tests.** `pytest-textual-snapshot` becomes a dev dependency (lockfile
  update). The lazy import of `core.analysis_run` needs an allow-list entry in
  `tests/telemetry/test_no_inline_imports.py`.
- **CI.** A paired base-vs-head performance check, path-filtered, Python 3.13
  only. It runs as **report-only for two weeks** before anyone considers
  making it required. Changing branch protection is a Release Operator
  action. A nightly absolute run covers the 1M-row budgets (03 §8.2).

## Phase 2 delivery plan

Each PR ships on its own, keeps `python -m pytest` and the gate test green,
and never changes `core/` privacy behaviour. Existing widget ids are kept
where tests depend on them, until the PR that replaces those widgets also
replaces those tests.

1. **Correctness fixes, before any redesign.**
   - D2: an override file is tied to the preset it was made for, and consent
     follows the effective posture.
   - D3: consent and confirmation dialogs open with Cancel focused.
   - D4: session restore applies column choices after the CSV loads.
   - D5: the duplicate debug-sheet control.
   - D6: log batching.
   - D7: a frozen `RunInputs` snapshot is built on the UI thread before the
     worker starts.
   - D8: entity loading uses the resolved CSV path.
   - Owner decisions 1, 4, 5 and 6: the engine cancel/stage hook, no
     `txn_cnt` Total default, balanced CSV off everywhere, and the rate sweep
     sent as shown.

   Each fix gets a regression test. (D10 was fixed in PR #75.)
2. **Performance foundations, with no visual change.**
   - Theme set in `__init__`.
   - Presets parsed once.
   - CSV reload only when (realpath, mtime, size) changes.
   - Picker built on `OptionList` with a worker scan.
   - `core.analysis_run` loaded lazily and pre-warmed in a thread.
   - The lazy `core/__init__.py` facade (owner decision 8).
   - Probe budgets updated, and the report-only CI job added.
3. **Visual system.**
   - The token stylesheet, the status language and NO_COLOR/ANSI rules.
   - Checkbox subclasses and the app-owned key bar.
   - `core/labels.py` and the copy rewrites.
   - Packaging (`pyproject`), with the `edge_deploy.yaml` request handed to
     the Release Operator.
4. **Layout shell.**
   - Step rail, action bar, and the results column or `^T` view.
   - Global bindings that work in any field (no `ctrl+a`/`ctrl+e`), plus the
     command palette, which is the only way to jump to a step (decision 7).
   - Only the active step is mounted.
   - Existing fields move into steps unchanged.
5. **Step contents.**
   - "More options" and the Expert settings screen.
   - The large-entity filter (above 2,000 values).
   - Prompts moved after validation.
   - The results view with copyable paths.
   - The session restore redesign.
6. **Verification.**
   - Snapshot tests at 80x24 and 120x40, under NO_COLOR and ANSI.
   - Keystroke re-measurement with the 02 Phase 0 script.
   - Performance before/after with `scripts/tui_perf_probe.py`.
   - A 5-user timed task script and SUS questionnaire for the owner to run.
   - A telemetry baseline window, using the schema v2 `friction` report.

**Phase 2 is done when:**
- Keystrokes are at or below the 01 §9 projections.
- `--budget` passes at 10k rows on the reference VM.
- All TUI, privacy and telemetry tests pass with no weakened assertions.
- Snapshots are approved at both sizes.

## Owner decisions (2026-10-14)

These answers replace the open questions that were listed here. Where a
decision changes a spec, this section wins over 01–03.

| # | Question | Decision | Effect on the plan |
|---|---|---|---|
| 1 | Engine cancel and progress hook in `core/` | **Add it.** An optional, additive `cancel_requested` callable plus a stage callback on the shared run seam. Core checks it at the configuration → input → analysis boundaries and before `output` starts. | Phase 2 PR 1. CLI behaviour is unchanged when no hook is passed. Log-gate finalisation still runs in `finally`. Cancel is offered until output writing starts. |
| 2 | Where advanced-override files live | **Keep as today**: written to the launch folder and left there. | No `PresetWorkflow` change. D2 is still fixed, because the file is regenerated from the current preset on every run (01 §8.2 items 1–4). 01 §8.2 item 2's "deleted after the run" is dropped. |
| 3 | Restore Verified safe coverage and the preset | **Keep restoring**, marked ↺ restored. | As 01 §8.1. |
| 4 | `txn_cnt` default for the rate Total column | **Drop it.** The clearing-spend basis is always an explicit choice. | Phase 2 PR 1. J2 projections gain the explicit selection. |
| 5 | Balanced-CSV export defaults | **Off everywhere** (TUI share, TUI rate, CLI). | Phase 2 PR 1. This is a behaviour change for TUI share runs, documented in the PR and README. The CLI default is already off. |
| 6 | Rate-mode sweep after Verified safe coverage | **Send the value shown, unlocked.** The lock applies only while VSC is active on a share run. | Phase 2 PR 1 (bug fix), with a regression test. |
| 7 | Step-jump keys | **Command palette only.** No F2–F6 and no Alt+1…5. Tab still flows through the steps. | 01 §4.1 step keys are dropped. Ctrl+P lists "Go to step: …" entries. Projections in 01 §9 are re-measured in PR 6, J3b most affected. |
| 8 | Lazy `core/__init__.py` facade | **Include it.** | Phase 2 PR 2, with an import-time check in the perf probe. |
| — | D10 (quit while a confirmation is open hangs) | **Fixed in PR #75.** | Removed from Phase 2 PR 1. |
| — | Phase 2 delivery | One short-lived branch and draft PR per Phase 2 PR, stacked on #75. Run all six. | Wave 1 (PRs 1–3) in parallel, then PR 4, PR 5 and PR 6 in sequence. |
