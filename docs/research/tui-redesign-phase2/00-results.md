# TUI Redesign Phase 2: Results

Phase 2 shipped the redesign in six PRs (#75–#80 and this one, PR 6). This
page is the evidence that it met its goals, and an honest list of where it
did not. Every number below was measured on one shared 4-vCPU VM (Python
3.13, Textual 7.5.0), base and head on the same machine and, for performance,
interleaved. Treat timings as relative.

| | Commit |
|---|---|
| Base (original `main`) | `ddea32c` |
| Head (measured) | `tui-p2-6-verify` at `d06af81` (keystrokes, heuristics, performance). Later commits change only the focus-restore race fix and tests; J1 and J4b were re-measured on them with identical counts |

How to reproduce:

```bash
uv sync --extra dev --extra release
# Keystrokes (any checkout; picks the legacy or step journeys itself)
uv run python scripts/tui_journeys.py --repo <checkout> --json out.json [--typeahead]
# Performance (head's probe against any checkout)
uv run python scripts/tui_perf_probe.py --repo <checkout> --rows 10000 100000 --cardinality 50 5000 --repeat 3 --budget
# Snapshots (72 baselines; review SVG diffs after an intended change)
uv run python -m pytest tests/test_tui_snapshots.py [--snapshot-update]
```

## 1. Phase 2 "done when" criteria

| Criterion (Phase 1 summary) | Result |
|---|---|
| Keystrokes at or below the 01 §9 projections | **Met for J1 and J2, met for J3 only with the command palette.** J1 40 keys with the Ctrl+R jump (projection 40; 42 by Tab alone). J2 fraud 62 (projection 62). J3 39 with Ctrl+P (projection 41), 47 by Tab alone, because owner decision 7 removed the step keys the projection assumed. See §2 |
| `--budget` passes at 10k rows on the reference VM | **Met**: 0 failures at 10k in both rounds (base: 21–22). At 100k, 1–2 marginal failures per round (§3.3) |
| All TUI, privacy and telemetry tests pass, no weakened assertions | Met. Full suite green apart from the two known local-only PowerShell tests; changed tests are listed in the PR |
| Snapshots approved at both sizes | 72 snapshots committed (18 states × 80x24 / 120x40 × colour / NO_COLOR), stable across 5 consecutive parallel runs and a serial run. **Approval is the owner's**: review `tests/__snapshots__/test_tui_snapshots/` |

## 2. Keystrokes (J1–J4), base vs head

Measured with `scripts/tui_journeys.py` (arrow mode: Select overlays move by
arrows). The base run reproduces every Phase 0 number exactly, so the method
is unchanged. Counts are identical at 80x24 and 120x40, except J3b at 80x24
(+1: Ctrl+T back from the results view). KLM: K = 0.2 s, M = 1.35 s.

| Journey | Base keys / KLM s | Phase 1 projection | Head keys / KLM s | Head, best alternative | Change |
|---|---:|---:|---:|---|---:|
| J1 Share, minimal | 49 / 20.6 | 40 / 18.8 | 42 / 19.2 | **40 / 18.8** (Ctrl+R jumps to the dimensions) | −14% (−18%) |
| J1 Share + time column | 55 / 23.1 | — | 52 / 22.6 | | −5% |
| J1 Share via Ctrl+O picker | 27 / 16.2 | — | 22 / 15.2 | | −19% |
| J2 Rate, approval | 78 / 26.4 | — | 54 / 21.6 | | −31% |
| J2 Rate, fraud | 90 / 31.5 | 62 / 25.9 | **62 / 25.9** | | −31% |
| J2 Rate, fraud + accuracy_first | 96 / 35.4 | — | 71 / 30.4 | 70 / 30.2 (palette) | −26% |
| J3 Re-run after restart, change preset | 61 / 20.3 | 41 / 16.3 | 47 / 18.9 | **39 / 17.2** (Ctrl+P "step 4") | −23% (−36%) |
| J3b Re-run in the same process | 17 / 7.5 | — | 11 / 6.3 (12 at 80x24) | 10 / 6.1 (palette) | −35% |
| J4a Preflight block, recover | 41 / 15.0 | — | 38 / 14.4 | | −7% |
| J4b Validation error, fix file, re-run | 75 / 24.5 | — | 68 / 23.1 | | −9% |

With type-ahead (first letter, then arrows), base → head: J1 43 → 36,
J2 fraud 70 → 51, J2 fraud + accuracy_first 76 → 60, J3 58 → 44 (40 with the
palette), J4b 69 → 62.

What the numbers mean:
- **J1** saves the 7 Shift+Tabs of the Phase 0 backwards wrap: after the CSV
  loads, focus moves straight to Target entity, and Dimensions is three Tabs
  on. The projection's 40 is reached with Ctrl+R, which jumps to the first
  blocker (the dimensions list) instead of running.
- **J2** gains most: Rate is a Left/Right switch on step 3 instead of tab stop
  17, there is one dimensions list, and the wrong Total default is gone
  (owner decision 4), so the explicit Total choice costs 3 keys instead of a
  correction.
- **J3** no longer re-picks the dimensions (column choices now restore
  after the CSV loads), but by Tab the preset is 7 stops away. The
  projection assumed a step key; owner decision 7 made the command palette
  the only step jump, which reaches it in 4 keys.
- **J4b** stays expensive (40 typed characters): recovering from a bad file
  still means retyping the path. A "reload the same path" action is in §6.

## 3. Performance, base `ddea32c` vs head

`scripts/tui_perf_probe.py` (head's probe for both sides), all phases,
`--rows 10000 100000 --cardinality 50 5000 --repeat 3`, two interleaved
rounds (base, head, base, head), so n = 6 per cell; plus `--rows 1000000`
for the CSV and entity phases. Medians, with the maximum in parentheses.
One short snapshot run (4 tests) overlapped the first base round; nothing
else ran on the VM during the rounds.

### 3.1 Interaction and startup (n = 6 per cell)

| Metric | 10k × 50: base | head | 10k × 5,000: base | head | 100k × 50: base | head | 100k × 5,000: base | head |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Startup to idle (s) | 1.08 (1.79) | **0.16** (0.25) | 1.14 (2.68) | **0.19** (0.27) | 1.35 (2.14) | **0.19** (0.43) | 1.57 (2.42) | **0.17** (0.19) |
| Startup stall (ms) | 610 (1340) | **65** (111) | 653 (1989) | **86** (188) | 829 (1679) | **82** (324) | 987 (1755) | **71** (91) |
| Key latency p95 (ms) | 191 (953) | **74** (93) | 332 (1437) | **60** (225) | 846 (1577) | **86** (104) | 222 (1345) | **66** (337) |
| Key stall max (ms) | 94 (809) | **70** (126) | 241 (1238) | **77** (269) | 750 (1343) | **69** (271) | 103 (1257) | **71** (313) |
| CSV headers ready (s) | 0.022 | 0.044 | 0.022 | 0.052 | 0.021 | 0.069 | 0.020 | 0.064 |
| CSV entities ready (s) | 0.071 (1.109) | 0.094 (0.111) | 0.056 (1.155) | 0.114 (0.281) | 0.117 | 0.195 | 0.150 (1.114) | 0.217 (0.426) |
| CSV-load stall (ms) | 32 (1046) | 39 (57) | 47 (1111) | 42 (209) | 64 (77) | 57 (67) | 89 (1089) | 41 (237) |
| Entity column change (s) | 0.011 | 0.035 | 0.021 | 0.066 | 0.066 | 0.122 | 0.098 | 0.149 |
| Entity change stall (ms) | 10 (50) | 14 (31) | 18 (24) | 22 (40) | 63 (82) | **21** (32) | 95 (110) | **23** (36) |
| Step 3 first show (s) | — | 0.053 (0.078) | — | 0.062 (0.093) | — | 0.070 (0.283) | — | 0.075 (0.277) |
| Advanced (base) / Expert (head) open (s) | 0.219 | 0.241 | 0.257 | 0.251 | 0.194 | 0.274 (0.611) | 0.303 | 0.262 |
| Picker open (s), 2,000 CSVs | 0.378 | **0.009** | 0.536 | **0.009** | 0.580 | **0.009** | 0.554 | **0.009** |
| Picker list ready (s) | 3.31 (4.24) | **0.133** | 3.72 (4.47) | **0.173** | 3.88 (4.26) | **0.198** (0.461) | 3.75 (4.08) | **0.168** |
| Picker stall (ms) | 4823 (5417) | **54** (67) | 4818 (5306) | **73** (173) | 5360 (5783) | **166** (371) | 4609 (5572) | **62** (195) |
| 5,000 log lines (s) | 5.99 (7.10) | **0.213** | 6.05 (7.34) | **0.246** | 5.39 (5.85) | **0.272** | 6.23 (6.62) | **0.239** |
| Log flood stall (ms) | 60 (848) | 42 (45) | 39 (953) | 45 (75) | 32 (869) | 49 (87) | 51 (1005) | 39 (72) |
| Large-entity filter, key max (ms) | — | 31 | — | 32 | — | 30 | — | 27 |

### 3.2 Import and 1M rows

| Metric | Base | Head | Change |
|---|---:|---:|---:|
| `import tui_app` (s, n = 6) | 1.217 (1.358) | **0.588** (0.627) | −52% |
| `import core` (s) | 0.591 (0.655) | **0.043** (0.052) | −93% |
| 1M × 50: CSV-load stall (ms) | 553 (622) | **41** (99) | −93% |
| 1M × 50: entity change stall (ms) | 502 (546) | **34** (37) | −93% |
| 1M × 50: entities ready after load (s) | 0.603 | 0.741 | +23% |
| 1M × 5,000: CSV-load stall (ms) | 602 (712) | **47** (62) | −92% |
| 1M × 5,000: entity change stall (ms) | 614 (720) | **38** (74) | −94% |
| 1M × 5,000: entities ready after load (s) | 0.600 | 0.775 | +29% |

Reading the regressions honestly: headers, entity lists and an entity-column
change now take 20–60 ms longer to *finish*, because the work moved off the UI
thread (workers share the GIL) and a load now also samples numeric columns
and mounts the next step. In exchange the UI never freezes for them: every
corresponding stall fell (1M rows: 0.5–0.6 s → 34–47 ms). All are inside
the 0.1 s headers budget.

### 3.3 Budgets (`--budget`, Phase 1 defaults)

| Run | Failures at 10k rows | Failures at 100k rows |
|---|---:|---:|
| Base, round 1 / 2 | 21 / 22 | 21 / 23 |
| Head, round 1 / 2 | **0 / 0** | 1 / 2 |

The head's 100k failures are each in one round only and just over the line:
Expert open 0.304 s (budget 0.3), key stall 100.9 ms (100) and picker stall
262 ms (200, one slow round). **`--budget` passes at 10k rows in both
rounds**, which is the Phase 2 criterion.

### 3.4 The PR 5 gaps and the CI picker report

| Gap | Before | After | Cause and fix |
|---|---|---|---|
| Step 3 first show, 10k × 50 (PR 4 0.10 s) | 0.131 s | **0.056 s** | Frame quantisation, not work: at 20 FPS the display switch was only noticed after the next frame, so the step waited one extra 50 ms frame for its layout. Switching steps now requests the screen layout at once. (At 60 FPS both were 0.08 s, which is how the cause was isolated.) |
| Background-mount stall (think window) | 31–35 ms | **22–27 ms** median, max 43 | Later steps' widget CSS was parsed (and the rules map rebuilt) on their first mount; it is now registered once in an idle tick after startup. Mounts also wait for 0.25 s without input, so they no longer land inside typing. The rest is Textual composing ~25 widgets; splitting further was not worth it |
| Random 65–220 ms stalls (CSV, entity, key windows) | gen-2 GC walking ~1M engine objects | `gc.freeze()` once after the pre-warm import | Found with `gc.callbacks` timelines |
| CI: Ctrl+O 0.41 s, picker stall 405 ms (#80) | Reproduced: the first picker open in a process took 175–226 ms before the screen appeared | **0.009–0.011 s** | The engine pre-warm import (scipy) was still running on its thread; each of the quick-pick list's 2,000 `stat` calls released the GIL and queued behind it. CI runs `--repeat 1`, so every CI run was a "first" run. Quick picks are now gathered on a thread worker. The probe also now waits for the import itself (it only waited for a worker it had not seen yet) |
| CI: key stall 163 ms at 10k × 5,000 (#80) | PR 5 170 ms (239), CI-style single runs | head **83 ms** (115) | Same import overlap plus a background step mount landing in the keys window; fixed by the two changes above |

CI-style check (head's probe, `--repeat 1`, fresh process per run, 4 rounds,
CI phases), PR 5 `6051116` vs head: picker open 0.016 → 0.010 s (10k × 50)
and 0.015 → 0.009 s (10k × 5,000); picker stall 80 → 75 ms and 63 → 80 ms
(both well inside 200 ms); key stall 50 → 56 ms and **170 → 83 ms**.

## 4. Heuristic re-review (Phase 0 method, all 45 findings)

Method as in Phase 0 [03](../tui-redesign-phase0/03-heuristic-review.md):
the real app driven headlessly into each state (stub engine, isolated
session, logs and cwd), screenshots at 80x24 and 120x40, in colour, under
NO_COLOR and with the `textual-ansi` theme (24 states × 2 sizes × 3 modes =
144 PNGs, regenerated by the PR 6 scratch capture from `tests/tui_scenes.py`;
not committed). Evidence below cites the committed snapshot SVGs
(`snap:<state>-<size>-<color|nocolor>` =
`tests/__snapshots__/test_tui_snapshots/test_tui_snapshot[<state>-<size>-<mode>].svg`)
and code as `file:line` at `d06af81`.

Scoring is strict: **Resolved** means the finding's problem no longer occurs
anywhere we looked; **Partial** means the main harm is gone but part of the
finding still holds; **Not resolved** means it holds as written.

### 4.1 Scorecard

| Status | Count | Sev 4 | Sev 3 | Sev 2 | Sev 1 | Sev 0 |
|---|---:|---:|---:|---:|---:|---:|
| Resolved | 28 | 0 | 8 | 12 | 7 | 1 |
| Partially resolved | 14 | 1 | 2 | 10 | 1 | 0 |
| Not resolved | 3 | 0 | 0 | 2 | 1 | 0 |
| **Total** | **45** | 1 | 10 | 24 | 9 | 1 |
| New issues from the redesign | 9 | 0 | 1 | 3 | 5 | — |

All ten Phase 0 top-10 issues are resolved or partially resolved; F29
(severity 4) is partial only because row numbers still do not say whether
they are 0- or 1-based.

### 4.2 Finding by finding

| ID | Sev | Status | Evidence |
|---|---|---|---|
| F01 | 3 | Resolved | The action bar and Run status show the stage, elapsed time and `^G Cancel run` from anywhere (snap:running-80x24-color; `tui_app.py:2600-2611`) |
| F02 | 2 | Partial | A distinct "? WAITING FOR YOU" state covers dialogs (snap:consent-80x24-nocolor). The outcome is still stated three times: Run status, Last run and the action bar (snap:success-120x40-color) |
| F03 | 2 | Partial | Short `HH:MM:SS LEVEL` stamps (`tui_app.py:366`) and a separate outcome card. The log still does not wrap: long lines are cut (snap:success-120x40-color, run log); multi-line engine records leave bare `INFO` lines |
| F04 | 2 | Resolved | At most 2 toasts (`tui_app.py:1209`), queued while a dialog is open, moved off the focused field (`tui_app.py:2960`); a reload of the same CSV no longer re-announces |
| F05 | 1 | Resolved | Step 1 leads with the file name (`✓ gate_demo.csv · 8 columns`, snap:step1_data_loaded-80x24-color); Review shows the name only (PR 6) |
| F06 | 3 | Partial | Verdicts, postures and reasons are plain words with the code as secondary text (`core/labels.py`; snap:withheld-120x40-color). Raw ids remain as primary text in the preset Select (`compliance_strict`, snap:step4_privacy-80x24-color), the consent dialog ("(accuracy_first)"), the RunBlocked "Why" (core message verbatim, snap:blocked-80x24-color) and the log's `verdict fully_compliant` |
| F07 | 2 | Partial | Rule strategy and release mode now have hints; "enables rule 4/35", "Tolerance (pp)" and "Lambda penalty" are still unexplained (snap:step4_privacy-80x24-color; snap:expert-80x24-color) |
| F08 | 1 | Resolved | Dimension and secondary lists hide the role columns and mark numeric ones `#` (snap:step3_analysis_share-120x40-color) |
| F09 | 3 | Resolved | `^G` cancels until output writing starts (core hook, owner decision 1); `cancel_during_run` telemetry |
| F10 | 2 | Not resolved | `^L` still clears the log with no undo (`tui_app.py:1187`) and every run clears it (`tui_app.py:4362`) |
| F11 | 2 | Resolved | Every ConfirmScreen focuses Cancel (`tui_app.py:804-807`; snap:consent-*, snap:clearing_spend-*) |
| F12 | 2 | Not resolved | Affirmative buttons are still `variant="error"` (red) for consent and the clearing-spend attestation (`tui_app.py:800`, default variant), and the validation dialog still has a green Proceed and a red Cancel (`tui_app.py:960-961`) |
| F13 | 2 | Resolved | Five numbered steps, More options and Expert settings as explicit tiers, a fixed action bar (snap:step3_analysis_share-*) |
| F14 | 1 | Partial | One term per concept for Expert settings and sentence case throughout; Help still says "Close" where dialogs say "Cancel", and the key bar says "Export expert" where the button says "Export to file… F9" |
| F16 | 3 | Resolved | Consent follows the effective posture, override included (PR 1, D2; `tui_app.py` `_collect_run_inputs`) |
| F17 | 2 | Resolved | Live readiness in the action bar, the rail and a Review list of every blocker that jumps to its field (snap:review_blocked-*); the last gap (Citi entity) closed in PR 6 |
| F18 | 2 | Partial | Expert settings show where each value comes from (`preset`, `engine default`, `● changed · preset 10.0`), so inherited and set values are distinct (snap:expert-80x24-color). Fields are still free text, Strategy is still free text ("greedy / random") and non-numbers are still kept by `try_parse_number` (`tui/expert.py:28-60`) |
| F19 | 2 | Resolved | The form is locked during a run with a note saying why (snap:consent-80x24-nocolor, top line) |
| F20 | 1 | Resolved | Review shows the resolved output path (snap:step5_review-120x40-color) |
| F21 | 3 | Resolved | App-owned key bar on every screen, per context, `^Q Quit` and `F1 Help` included; F1 lists every key (snap:*; help screen) |
| F22 | 2 | Resolved | One checkbox per row; nothing clipped at 80x24 (snap:step4_privacy-80x24-color) |
| F23 | 1 | Resolved | Labels in their own column (snap:step2_entity-80x24-color) |
| F24 | 2 | Resolved | Steps, Ctrl+R to the first blocker, Ctrl+P "Go to step" |
| F25 | 1 | Resolved | App commands in the palette (`tui/commands.py:38`; palette screenshot) |
| F26 | 2 | Resolved | One-row inputs; Expert settings on their own screen |
| F27 | 1 | Resolved | One title in the header, no subtitle; legacy "(formerly …)" stripped from preset blurbs (`core/labels.py` `strip_preset_description`) |
| F28 | 3 | Partial | Unexpected errors get a card with what happened, what to do and the log path (unexpected-error screenshot). The raw traceback is still written into the run log view (`tui_app.py:4828`) |
| F29 | 4 | Partial | Every issue is listed with a glyph + word severity, the header says why Proceed is disabled (snap:validation-80x24-nocolor). "Rows: 4" still does not say whether rows are 0- or 1-based |
| F30 | 2 | Resolved | Withheld, blocked and failed cards have "Why" and "Next" lines (snap:withheld-*, snap:blocked-*) |
| F31 | 2 | Resolved | Dynamic text goes in as `Text`/escaped markup (validation dialog renders `[bold]` literally; `tests/test_tui_ux.py`) |
| F32 | 1 | Resolved | A failed data check names the check and the reason (`labels.DATA_CHECK_FAILED` card) |
| F33 | 2 | Partial | Step 4 shows the preset's posture and blurb from the preset YAML and says when consent is needed; the F1 preset guide is still hard-coded Markdown with no postures or consent rules (`tui_app.py:853-890`) |
| F34 | 2 | Partial | F1 help with keys and presets, per-field hints. No link to `onboarding.md` or the PT-BR preset guide |
| T1 | 3 | Resolved | Single column below 110 columns with Results on Ctrl+T; verdict and report path readable at 80x24 (snap:results_view-80x24-color) |
| T2 | 3 | Resolved | F8/F9 replace Ctrl+A/Ctrl+E; ^G/^T/^Y are priority bindings no Input takes (`tui_app.py:1186-1197`). (^L is F10) |
| T3 | 2 | Resolved | Focus changes the border shape (round → heavy) and reverses the field label, readable under NO_COLOR (`tui/styles.py:101,129-140`; snap:*-nocolor) |
| T4 | 3 | Resolved | `[x]` / `[ ]` checkboxes (snap:step3_analysis_share-*-nocolor) |
| T5 | 3 | Resolved | Status = glyph + word, reverse badge under NO_COLOR (snap:withheld-120x40-nocolor) |
| T6 | 2 | Partial | `textual-ansi` renders the key bar and badges (ANSI screenshots), but the theme is still forced to tokyo-night and ignores the user's choice (`tui_app.py:1217`) |
| T7 | 2 | Partial | Short lists size to their content (PR 6), so the dimensions list no longer scrolls inside the step. Nested scrolling remains: lists above 8 options, and at 120x40 the results column scrolls as a whole with the log below the card |
| T8 | 2 | Partial | Short stamps and a level column; no soft wrap; tool messages and engine records still interleave (§6) |
| T9 | 2 | Partial | Ctrl+Y copies the path (OSC 52) and every path is shown whole. In the 42-column results column it still wraps mid-token (snap:withheld-120x40-color), which defeats mouse selection |
| T10 | 2 | Resolved | Tab flows through the steps, Ctrl+P jumps, Ctrl+R jumps to the blocker |
| T11 | 0 | Resolved (kept) | FPS cap, no animation or clock, batched log, lazy steps; still true |
| T12 | 1 | Not resolved | The terminal title never shows the run state |

### 4.3 New issues the redesign introduced

| # | Sev | Issue | Evidence | Status |
|---|---|---|---|---|
| N1 | 3 | "A Citi competitor will receive this output" ticked with no Citibank entity said READY; core refused the run only after it started | `tui/readiness.py` | **Fixed in PR 6** (readiness blocker, telemetry v4) |
| N2 | 2 | Cancelling the validation review left nothing focused; Tab restarted from the top of the step | found by `scripts/tui_journeys.py` J4b | **Fixed in PR 6** (`tests/test_tui_verification.py`) |
| N3 | 2 | Ctrl+O could take 0.2–0.48 s to open while the engine pre-warm import held the GIL | §3, picker | **Fixed in PR 6** (quick picks on a worker) |
| N4 | 1 | The empty run log drew both scrollbars | snapshots | **Fixed in PR 6** |
| N5 | 1 | Review repeated the CSV's full folder path in parentheses | PR 5 review | **Fixed in PR 6** (file name; full path in step 1 and the log) |
| N6 | 2 | After a run, Review still says "● Ready to run …" beside a FAILED or WITHHELD badge, which reads as a contradiction | snap:withheld-120x40-color | Open |
| N7 | 1 | The run log's line order is not guaranteed: the worker's direct lines ("Analysis completed successfully.") can land before buffered engine records | found while making snapshots deterministic | Open |
| N8 | 1 | CSV picker: long file names wrap mid-word in Quick picks, and "Browse <folder>" truncates the folder at 80 columns | picker screenshot | Open |
| N9 | 1 | At 120x40 the card and the log share one scrolling column; after an error the log is below the fold | unexpected-error screenshot | Open |

Most informative screenshots (scratch, not committed):
`…/scratchpad/p2-6/heur/png/` `validation_80x24_nocolor.png`,
`withheld_120x40_nocolor.png`, `unexpected_error_120x40_normal.png`,
`step4_privacy_80x24_normal.png`, `picker_80x24_normal.png`,
`step3_analysis_share_80x24_ansi.png`.

## 5. What met target and what did not

Met:
- J1 and J2 at the projection; every journey shorter than base, by 5–35%.
- 80x24 is a first-class size: verdict and report path readable, nothing
  clipped, Run always one key away.
- Compliance moments: Cancel focused on every attestation, consent per run
  and after validation, NO_COLOR-safe statuses, every validation issue shown.
- Performance: startup 1.1 s → 0.16 s, key p95 191 → 74 ms, picker 3.3 s → 0.13 s, 5,000 log lines 6 s → 0.2 s, a 1M-row CSV load or entity change freezes the UI for under 50 ms (median; was 0.5–0.6 s); `--budget` clean at 10k.
- 72 deterministic snapshots in CI.

Not met:
- J3 by Tab (47 vs 41): only the palette path (39) beats the projection.
- The Phase 0 findings still open or partial (F10, F12, T12; F06, F28, F33
  and the rest of §4.2).
- Usability with real users is unmeasured until the owner runs the
  [test kit](usability-test-kit.md).

## 6. Remaining known issues

1. **F12 button roles**: consent and attestation buttons are red; the
   validation dialog's Cancel is red and Proceed green.
2. **F10 log loss**: Ctrl+L and every new run clear the log; no per-run history.
3. **F28 traceback in the log view**: keep it in the file log only.
4. **F06 raw ids** in the preset Select, the consent text and RunBlocked "Why".
5. **F33 preset guide** is hard-coded; generate it from `presets/*.yaml`.
6. **J4b recovery** needs the path retyped; add "reload the same file".
7. **N6–N9** above.
8. **Theme** is forced to tokyo-night (T6).
9. **Stalls the budget does not see**: CSV-load stall at 5,000 entities and
   the background step mount (§3) are below the 500 ms startup budget but
   above the 100 ms interaction budget in some runs.
10. **Widget CSS**: `Disclosure`, `ModeSwitch`, `EntityChooser`, `StepRail`
    and `KeyBar` keep small `DEFAULT_CSS` blocks for structure;
    `tui/styles.py` holds every token and colour rule.
11. **Core**: with Verified safe coverage, `core/privacy_coverage.py:142`
    builds no Citi overlay when the Citibank entity is blank. Today that run
    is refused earlier by `_fit_privacy_strategy`/the RunBlocked path, and
    the TUI now blocks it at readiness, but core's own guard depends on
    ordering. Worth a core-side check (not changed here: no `core/` privacy
    behaviour change in this PR).

## 7. Release Operator notes

- **`tui/` package (since PR 3).** The TUI is now `tui_app.py` plus the
  `tui/` package. `edge_deploy.yaml` already lists `"tui/**/*.py"` in
  `runtime_paths` and `tui` in `compile_targets`; `pyproject.toml` packages
  `tui*`; `setup_remote_env.sh` compiles `tui`. A bundle without `tui/`
  fails at import. Check this in the first bundle you build.
- **Ctrl+C.** Textual 7.5 binds Ctrl+C to copy. The app owns it as a
  priority binding: copy when there is a selection, otherwise quit like
  Ctrl+Q (`tui_app.py:2907`). The release tooling's `tui_exit: ctrl_c`
  (Escape, then Ctrl+C) keeps working.
- **Telemetry readers.** Records are now written as schema v4
  (`session_start`/`session_end` still v1). A node that still runs a v3, v2
  or v1 reader keeps working: it skips newer records with a counted warning
  ("upgrade Autobench to read them") and still counts sessions. Upgrade the
  reader on any node that produces friction reports before comparing
  windows across the upgrade. v4 adds only `launch_blocked.reason =
  citi_entity_missing`; when comparing a pre-v4 window, add those blocks back
  to the compliance-policy refusals (05 §8.11).
- **Dependencies.** `pytest-textual-snapshot` is a dev-only dependency
  (`uv.lock`); `requirements.txt` and `constraints.txt` are unchanged.
- **CI.** `python -m pytest` now runs 72 snapshot tests (about 1 minute
  serial). On a failure the plugin writes `snapshot_report.html` (ignored by
  git); attach it when reporting a visual regression.
- **Perf CI** (`tui-perf.yml`) stays report-only. The probe now waits for the
  engine pre-warm import itself, so pre- and post-PR-6 CI runs are not
  directly comparable on the first phases.

## 8. User-visible changes (release notes)

- The TUI is one screen with five steps (Data, Entity, Analysis & mode,
  Privacy & compliance, Review & run) and a bar at the bottom that always
  says whether the run is ready and what is missing.
- Ctrl+R runs, or jumps to the first thing to fix. Ctrl+P opens commands,
  including "Go to step". Tab flows through the steps.
- After a CSV loads, focus moves to the next field you need; numeric columns
  are listed first; one Dimensions list serves both modes.
- Rate mode has no Total default: choose the clearing-spend basis explicitly.
- Balanced-CSV export is off by default everywhere.
- Expert settings (F8) replace the Advanced section; changes are kept for the
  session and written once per run; F9 exports them.
- Consent and the clearing-spend attestation are asked for every run, after
  validation, and open with **Cancel** focused.
- Ctrl+G cancels a run until output writing starts; nothing is written.
- Results: a side column at 110+ columns, Ctrl+T below that. Ctrl+Y copies the
  report path. Status is readable without colour.
- Session restore brings back the preset, mode and column choices (marked ↺);
  never the target entity, the declarations, paths or consent.
- With "A Citi competitor will receive this output" ticked, the run is not
  ready until the Citibank entity is chosen.
- Large entity lists (above 2,000 values) use a filter instead of a dropdown.

## 9. Operator guide: what changed

| You used to… | Now |
|---|---|
| Scroll a long form | Work through 5 steps; the rail at the top shows ✓ done, ! needs attention, ↺ restored |
| Look for the Run button | Press **Ctrl+R** anywhere. If something is missing, it takes you there and the bottom bar says what |
| Press Ctrl+A for Advanced | Press **F8** for Expert settings (F9 exports them) |
| Quit to stop a run | Press **Ctrl+G** (Cancel). It works until the report starts being written |
| Squint at the right pane at 80x24 | Press **Ctrl+T** for Results; **Ctrl+Y** copies the report path |
| Hunt for a section | **Ctrl+P**, type "step", pick one |
| Wonder what keys exist | Read the key bar at the bottom, or press **F1** |
| Press Enter on a consent dialog | Cancel is focused: move to the confirm button deliberately |
| Re-pick columns after a restart | They come back after the CSV loads (↺). Target entity and declarations never do, on purpose |
