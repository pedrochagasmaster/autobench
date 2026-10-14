# TUI Redesign Phase 0: 02 Main-Path Journeys and Keystroke Baseline

Scope: `tui_app.py` in the current working tree (2659 lines), Textual 7.5.0.
This is evidence only. No repo code was changed. Line references are
`tui_app.py:N` unless another file is named.

**How the numbers were measured.** A headless Pilot script
(`app.run_test(size=...)`) drove the real `BenchmarkApp` with real key presses
against a copy of `docs/autobench_demo.csv` (7 entities, 9 columns). Each
press was counted, and the script checked that focus or value reached its
target after each step. `tui_app.execute_run` was monkeypatched to return a
fake `fully_compliant` `AnalysisArtifacts`. Validation still runs for real
(`prepare_run_data`, `validate_analysis_input`), which is what lets J4 reach
the real `ValidationModal`. The run used isolated `HOME`, `SESSION_FILE`,
`AUTOBENCH_LOG_DIR` and cwd, with `AUTOBENCH_TELEMETRY=0`, so nothing was
written to the repo or the user's home.

Script (reuse it for the Phase 2 before/after comparison; see the Appendix):
`/tmp/claude-0/-home-user-autobench/d13cb994-08e3-5f72-b4d1-86adf775fd7d/scratchpad/journeys/measure_journeys.py`

## Summary: baseline numbers

"Minimal keyboard path" means the fewest keys that complete the journey. Defaults
are accepted wherever they are correct. Focus moves by whichever of Tab or
Shift+Tab is shorter, and Ctrl+R launches the run. In **Arrow** mode, Select
overlays are navigated with arrow keys only. **Type-ahead** mode first types the
option's first letter. The Textual 7 `SelectOverlay` supports this, but the UI
never says so.

KLM uses K = 0.2 s per keystroke and M = 1.35 s per mental-preparation step,
both counted per journey. System response time R (CSV load, validation,
engine) is excluded. Typed characters are the CSV path (`data/autobench_demo.csv`,
23 characters) plus type-ahead letters.

| Journey | Size | Total keys (arrow) | Typed chars | Tab / Arrow / Enter / Space / Chord | M | **KLM s (arrow)** | Keys / KLM s (type-ahead) |
|---|---|---:|---:|---|---:|---:|---|
| J1 Share, minimal (defaults) | 120x40 | **49** | 23 | 9 / 11 / 3 / 2 / 1 | 8 | **20.6** | 43 / 19.4 |
| J1 Share, minimal | 80x24 | **49** | 23 | same | 8 | **20.6** | 43 / 19.4 |
| J1 Share + time column (README parity) | both | 55 | 23 | 11 / 13 / 5 / 2 / 1 | 9 | 23.1 | 48 / 21.8 |
| J1 Share via Ctrl+O picker (no typing) | both | 27 | 0 | 9 / 11 / 3 / 2 / 2 | 8 | 16.2 | 21 / 15.0 |
| J1 Share, Tab to Run button + Enter | both | 50 | 23 | 10 / 11 / 4 / 2 / 0 | 8 | 20.8 | 44 / 19.6 |
| J1 Share, forward Tab only (naive) | both | 63 (derived) | 23 | 23 / 11 / 3 / 2 / 1 | 8 | 23.4 | n/a |
| J2 Rate, approval only | both | **78** | 23 | 24 / 21 / 7 / 2 / 1 | 8 | **26.4** | 66 / 24.0 |
| J2 Rate, fraud (ClearingSpendConfirmScreen) | both | **90** | 23 | 24 / 30 / 10 / 2 / 1 | 10 | **31.5** | 70 / 27.5 |
| J2 Rate, fraud + accuracy_first preset (`low_distortion`) | both | **96** | 23 | 26 / 31 / 13 / 2 / 1 | 12 | **35.4** | 76 / 31.4 |
| J3 Re-run after restart (session restore) + change preset | both | 61 | 23 | 15 / 15 / 5 / 2 / 1 | 6 | 20.3 | 58 / 19.7 |
| J3b Re-run in same process, change preset | both | 17 | 0 | 10 / 4 / 2 / 0 / 1 | 3 | 7.5 | n/a |
| J4a Preflight block (no dims) then recover | both | 41 | 23 | 2 / 10 / 3 / 1 / 2 | 5 | 15.0 | 35 / 13.8 |
| J4b ValidationModal error, cancel, fix file, re-run | both | 75 | 40 | 14 / 11 / 4 / 2 / 4 | 7 | 24.5 | 69 / 23.2 |

Headline findings:

- **Keystroke counts are identical at 80x24 and 120x40.** Focus auto-scrolls the
  config pane. What changes at 80x24 is *legibility*: the activity pane is
  pushed off-screen. Run Status, Last Run and the Log show **15 of 40 columns**,
  so the verdict and report path cannot be read (details below).
- **Rate costs about 60% more keys than Share (78 vs 49).** The fraud and
  accuracy_first modals add 12 to 18 more.
- **Session restore saves 0 keystrokes.** J3 after a restart (61) is J1 (49) plus
  the 12 keys to change the preset. The only cheap re-run is J3b in the same process (17).
- **The minimal J1 path depends on a backwards wrap.** Target entity to
  Dimensions is 21 Tabs forward, or 7 Shift+Tabs backwards through the scroll
  container, the Log and the Run button.
- **No journey requires the mouse to complete.** The mouse is effectively
  required only to *copy* the report path out of the Last Run panel or a toast,
  and nothing can recover the clipped activity pane at 80x24.
- KLM sensitivity: with K = 0.28 s (average typist), J1 = 24.5 s and J2-fraud =
  38.7 s.

Recorded key sequences (arrow mode, 120x40; `×n` = repeated, `type(n)` = n
printable characters):

```
J1   type(23) enter tab×2 enter down×7 enter shift+tab×7 down×3 space down space ctrl+r
J2   type(23) enter tab×2 enter down×7 enter shift+tab×13 right tab enter down enter tab enter down×8 enter tab×7 down×3 space down space ctrl+r
J2f  ... tab enter down×8 enter tab enter down×9 enter tab×6 down×3 space down space ctrl+r enter
J2af type(23) enter tab×2 enter down×7 enter tab×3 enter down enter tab×12 right ... ctrl+r enter×2
J3   type(23) enter tab×2 enter down×7 enter tab×3 enter down×4 enter shift+tab×10 down×3 space down space ctrl+r
J3b  tab×10 enter down×4 enter ctrl+r
J4a  type(23) enter tab×2 enter down×7 enter ctrl+r down×3 space ctrl+r
J4b  type(17) enter tab×2 enter down×7 enter shift+tab×7 down×3 space down space ctrl+r escape tab×5 ctrl+u type(23) enter ctrl+r
```

## Recorded Tab focus order (main screen, Share tab, first launch)

Recorded by pressing Tab from initial focus (`csv_path`, set at 1138) until the
cycle repeated. Both sizes have the same 28 stops. "Visible cols" is the
widget's width clipped to its pane and the screen.

| # | Widget | 120x40 visible cols | 80x24 visible cols | Flag |
|---:|---|---|---|---|
| 0 | `Input#csv_path` (initial focus) | 42/42 | 37/37 | |
| 1 | `Select#entity_col` | 28/28 | 26/26 | |
| 2 | `Select#entity_name` | 29/29 | 26/26 | Label "Target entity (blank = peer-only)" truncated to "...peer-on" (120) / "...peer" (80) |
| 3 | `Select#time_col` | ok | ok | Optional field, but it sits ahead of the required fields |
| 4 | `Input#output_file` | ok | ok | Optional |
| 5 | `Select#preset_select` | ok | ok | |
| 6 | `Button#btn_preset_help` | ok | ok | Duplicates F1 |
| 7 | `Checkbox#analyze_distortion` | ok | ok | |
| 8 | `Checkbox#compare_presets` | ok | ok | |
| 9 | `Checkbox#validate_input` | **18/23** | **13/23** | **Clipped** on the right ("Valida..." in screenshot) |
| 10 | `Checkbox#include_calculated` | ok | ok | |
| 11 | `Select#output_format` | ok | ok | |
| 12 | `Select#privacy_release_mode` | ok | ok | Hidden (removed from chain) on Rate tab (2052-2067) |
| 13 | `Checkbox#privacy_rule_sweep_mode` | ok | ok | Disabled and skipped when Verified Safe Coverage is selected |
| 14 | `Checkbox#privacy_merchant_spend_scope` | **65/68** | **60/68** | Clipped |
| 15 | `CollapsibleTitle` (Compliance Declarations) | ok | ok | Title only. Collapsed children are correctly *not* in the chain |
| 16 | `CollapsibleTitle` (Advanced Optimization) | ok | ok | Same |
| 17 | `ContentTabs` (Share / Rate) | ok | ok | **Mode switch is stop 17 of 28.** It is the most consequential choice but sits below all options |
| 18 | `Select#share_metric` | ok | ok | |
| 19 | `SelectionList#share_secondary` | ok | ok | Optional, but placed before the required dims |
| 20 | `Checkbox#share_auto_dim` | ok | ok | |
| 21 | `Checkbox#share_debug` | ok | ok | |
| 22 | `Checkbox#share_export_csv` | **13/28** | **8/28** | **Clipped**: three-checkbox row overflows the pane |
| 23 | `SelectionList#share_dims` | ok | ok | **Only required decision in the section; last stop before Run** |
| 24 | `Button#btn_run` | ok | ok | 110 rows down the scroll content (pane is 38 / 22 rows) |
| 25 | `Log#log_output` | 49/49 | **15/40** | **Non-form stop**. At 80x24 it is mostly off-screen |
| 26 | `VerticalScroll#config_pane` | ok | ok | **Container is a focus stop** (VerticalScroll `can_focus`) |
| 27 | `Button#btn_browse_csv` | ok | ok | Comes *after* the wrap; precedes `csv_path` visually but not in Tab order from start |

On the Rate tab, stops 18–23 become `rate_total`, `rate_approved`, `rate_fraud`,
`rate_secondary`, four checkboxes and `rate_dims`. The release-mode Select is
dropped from the chain.

Illogical or costly order items:

1. Required fields come last. Dimensions (stop 23) and the Share/Rate mode
   (stop 17) sit after 12 optional or advanced controls. Forward Tab from
   Target to Dimensions takes 21 presses.
2. The Log (25) and the scroll container (26) are focus stops, so every
   wrap-around costs two dead stops. The minimal J1 path actually *relies* on
   wrapping backwards through them.
3. The Browse button comes after the path Input in the initial Tab sequence,
   because focus starts on `csv_path`. That is harmless, but Browse is only
   reachable by Shift+Tab or Ctrl+O.
4. Nothing hidden or collapsed takes focus. Collapsible children are excluded
   correctly, and `.hidden` release-mode widgets drop out on the Rate tab.
5. **Ctrl+A / Ctrl+E are shadowed while an `Input` has focus.** Textual's
   `Input` binds `ctrl+a` to home and `ctrl+e` to end. Measured: Ctrl+A pressed
   in `csv_path` did *not* toggle Advanced. The footer hides `^a`/`^e` while an
   Input is focused, yet the start-up toast advertises both (1139-1144), and
   initial focus is an Input.

## 80x24 vs 120x40: what becomes hidden or unreachable

- **The activity pane overflows the screen.** `#config_pane` has `min-width: 64`
  (520) and `#activity_pane` has `min-width: 42` (628). 64 + 42 = 106 > 80. The
  activity pane is placed at x=64 to 106, and only **16 of 42 columns** are on
  screen. Run Status reads "Mode shar", "Preset comp". Last Run reads
  "Verdictful" (from "Verdict fully_compliant") and the report path is cut to
  about 13 characters per line. `Horizontal#app_body` does not scroll
  horizontally, so the panel **cannot be reached by keyboard or mouse**. Only
  the Log can be panned with Left/Right, 15 columns at a time.
- **Vertical scrolling.** The form is about 113 rows tall. The 22-row viewport
  at 80x24 shows only Browse, `csv_path`, `entity_col` and `entity_name` at
  launch (5+ screens to the Run button). At 120x40 it is 38 rows (3 screens).
  Keyboard focus auto-scrolls, so key counts do not change, but the user
  cannot see the defaults they are accepting (metric, preset blurb, dims)
  without moving focus or scrolling.
- **Horizontal clipping inside the config pane happens at both sizes:**
  `validate_input`, `share_export_csv` / `rate_export_csv` row and
  `privacy_merchant_spend_scope` (table above). `VerticalScroll` hides x-overflow.
- **Modals:** `ConfirmScreen` is a fixed `width: 60`, so it fits. The validation
  modal (80%) and picker (84%) shrink but stay usable.

## Journey maps

Notation: **Know** = what the user must already know. **Decide** = decision
point. **Err** = where it can fail. **FB** = feedback the UI gives.

### J1: Share analysis run

| # | Step | Screen / widget | Know / Decide | Err / FB |
|---|---|---|---|---|
| 0 | Launch `autobench` from the work dir (onboarding.md "Launch") | Main screen. Focus is on `csv_path` (1138). A toast lists shortcuts for 6 s (1139-1144) | Know: the cwd matters (quick picks and relative paths, 1592-1600) | FB: toast disappears. Footer shows only `^o ^r f1 ^l` while the Input is focused |
| 1 | Type CSV path + Enter (or Tab away) | `csv_path`. Load fires on submit (1726-1729) **and on blur** (1731-1744) | Know: path relative to launch dir. Alternative: Ctrl+O picker (1952-1961). Quick picks are preselected, so Ctrl+O, Enter = 2 keys | Err: missing file gives an error toast "Invalid Path" plus a log line (1607-1615). Blur means *any* Tab-away re-triggers load/validation of a half-typed path. FB: success toast "Loaded N columns" (1672-1677) and `csv_meta` "✓ file · N columns · size + preview" (1683-1698) |
| 2 | Entity column | `entity_col`. Auto-defaults to `issuer_name` if present (1659-1668). Setting it loads the entity list (2178-2180, 2147-2170) | Decide: accept default (0 keys) | Err: a wrong column is only caught at validation. FB: none beyond the Select value |
| 3 | Target entity | `entity_name` (allow_blank, "blank = peer-only") | Decide: entity or peer-only. Measured: Tab×2, Enter, Down×7, Enter (or Enter, "T", Enter with type-ahead) | Err: none at this step. FB: value shown. The label is truncated |
| 4 | Time column (optional) | `time_col` | Decide: README step 4 sets `year_month` (+6 keys) | none |
| 5 | Preset | `preset_select`. Default is `compliance_strict` (`core/contracts.py:13`, set at 1756-1764). Blurb from preset YAML (1771-1783). Guide via F1 / button (2125, 313-391) | Know: preset semantics (Preset Guide modal). Decide: accept default (0 keys) | Changing it refreshes advanced fields and release mode (2188-2196). FB: Run Status "Preset" line updates (1349-1371) |
| 6 | Metric | `share_metric`. Defaults to `txn_cnt` if present (1659-1668) | Decide: accept (0 keys). Must verify off-screen | Err: if absent, preflight "Primary metric is required" (2324-2326) |
| 7 | Dimensions | `share_dims` SelectionList (all CSV columns, unfiltered, 1650-1656) or `share_auto_dim` | Decide: which columns are dimensions. Measured: Shift+Tab×7, Down×3, Space, Down, Space | Err: none selected and auto off gives preflight block (2331-2336) → J4a. Selecting the entity or metric column as a "dimension" is allowed by the UI |
| 8 | Run | Ctrl+R (502-508, 1963) or `btn_run` (1086) | none | Button becomes "Validating…" (1373-1391), then "Running…" (1393-1405). The session is saved at both points (1391, 1405) |
| 9 | Validation (real) | Only if `validate_input` is on (default on, 901). `ValidationModal` opens only if issues exist (2404-2451) | Demo data has no issues, so no modal | → J4b |
| 10 | Read result | Right pane: Run Status badge, **Last Run** panel (1407-1425, content 2565-2571), toast "Report saved: path" for 10 s (2611-2622), Log | Know: the verdict vocabulary (`fully_compliant`, etc.) | At 80x24 the panel is unreadable (above). The path can only be copied with the mouse |

### J2: Rate analysis (approval, fraud, accuracy_first)

| # | Step | Screen / widget | Know / Decide | Err / FB |
|---|---|---|---|---|
| 1–3 | As J1 steps 1–3 | | | |
| 4 | Switch to Rate | `ContentTabs` at Tab stop 17: Shift+Tab×13 then Right | Know: Rate lives in a tab at the bottom of the form. Not restored across sessions | FB: Run Status "Mode rate". Release-mode controls hide (2052-2067, 2202-2206) |
| 5 | Total column | `rate_total`. **Defaults to `txn_cnt`** (1659-1668). For the demo the denominator is `total` | Decide: must override (Enter, Down, Enter) | Err: preflight "Total column is required" if blank (2350-2352). A wrong denominator is not detectable by the UI |
| 6 | Approved column | `rate_approved`. Default `app_cnt` is not in the demo, so blank | Decide: pick `approved` (Down×8) | Err: neither approved nor fraud gives preflight block, focus to `rate_approved` (2357-2359) |
| 7 | Fraud column (variant) | `rate_fraud` (Down×9) | Know: the Total column must be **clearing spend** (README 580-590) | |
| 8 | Dims + Run | As J1 step 7, Tab×6–7 forward | | Preflight (2364-2369) |
| 9a | **accuracy_first consent** (preset `low_distortion` / `minimal_distortion`) | `ConfirmScreen` pushed from the worker (2313-2319, 1457-1482). **Initial focus = "I understand — proceed"** | Decide: consent (per run, never persisted, 117-121) | Cancel: `_fail_launch("accuracy_first run cancelled…")` toast "Cannot run" (2315-2318). Asked **before** metric/dims preflight, so a run blocked later re-asks consent |
| 9b | **Clearing-spend attestation** (fraud selected) | `ClearingSpendConfirmScreen(total_col)` (302-310, 2376-2383). **Initial focus = Confirm** (`btn_confirm_yes`, 292) | Decide: attest that `total` is clearing spend | Cancel/Escape: log "Analysis cancelled by user." and back to idle, no toast (2378-2382). Asked again on every attempt (by design; `tests/test_tui_ux.py:387`) |
| 10 | Validation, run, read | As J1 9–10 | | |

Measured cost: approval 78 keys. The fraud Select adds 12 keys, the dims are one Tab closer, and the modal
needs one Enter, for 90. The accuracy_first preset Select adds 6, the mode tab
is one Tab closer, and the consent modal needs one Enter, for 96. One reflexive Enter is enough to attest or consent. That
is cheap in keystrokes but is a compliance-UX concern (friction #6).

### J3: Re-run with a changed parameter after a previous session

| # | Step | Behaviour (measured) | Code |
|---|---|---|---|
| 1 | Previous session quits with Ctrl+Q | `action_quit` saves the session (1971-1985). Also saved at every run attempt (1391, 1405) | `SESSION_SELECT_IDS` 115-125 includes `entity_col`, `time_col`, `share_metric`, `rate_*`. Lists include `share_dims` etc. (141) |
| 2 | Relaunch | Measured restored state at mount: `csv_path=''`, `entity_col=BLANK`, `time_col=BLANK`, `share_dims=[]`, **only `preset` (and checkboxes / output format / release mode) survive** | `_apply_session` runs at mount (1133) **before any CSV is loaded**. Column Selects have no options, so `select.value = …` raises and is swallowed (1264-1267). SelectionLists filter by available options, which is the empty set (1287-1293). `tests/test_tui_ux.py:155-163` asserts this blank result |
| 3 | Re-enter CSV path | Required by design ("must choose the dataset afresh", 1251-1253) | |
| 4 | After reload | `entity_col` / `share_metric` come back only via *smart defaults* (1659-1668), not the session. **Dims are lost**, **target entity is never saved** (by design). The **active tab is not saved**, so Rate users re-switch every time | |
| 5 | Change parameter (preset) + re-choose dims + Ctrl+R | 61 keys total | |

Net: a relaunch costs the full J1 path plus the change. Saved column values
are written but can never apply. Phase 1 should decide whether that is intended
(privacy) or a bug, given that `SESSION_SELECT_IDS` deliberately lists them.
**In the same process** (J3b), all selections persist. Changing the preset and
re-running costs 17 keys (Tab×10 wraps from `share_dims` through Run, Log,
container, Browse and path up to the preset).

### J4: Recovering from failures

**J4a: Preflight block (`_fail_launch`, 1439-1455).** Measured on "no dimensions":

- FB: toast "Cannot run" (error severity), log line `ERROR: Select at least one
  dimension or enable auto-detect.`, run button re-enabled, state `idle`, and
  **focus jumps to the offending widget** (`share_dims`). This was verified:
  recovery cost only Down×3, Space, Ctrl+R (5 keys).
- Weaknesses: checks run one at a time in a fixed order (csv 2272 →
  accuracy_first consent 2313 → metric 2324 → dims 2331 / rate checks
  2350-2369), so a user with two omissions needs two attempts. A missing CSV
  path focuses `csv_path`, but that check lives in the worker and only fires
  after the button has flickered to "Validating…". The consent prompt can
  appear before a block the user could have fixed first.

**J4b: Validation failure (`ValidationModal`, 393-441).** Fixture: demo CSV with
one negative `txn_cnt`, which produces an `ERROR negative_values`.

- FB: modal "Data Validation Results", counts of errors and warnings, issue list
  with `Rows: …` (first 10 DataFrame indices, 427-428). **Proceed is disabled**
  when errors exist (417). Measured focus chain: `issue_list`, `btn_cancel`.
  Initial focus is on `issue_list`.
- Escape or Cancel triggers `_handle_validation_modal_result` (1173-1195): log
  "Analysis cancelled by user.", UI reset, and focus returns to the
  previously focused widget (`share_dims`). There is no toast and no
  indication of which file or column to fix beyond the message text.
- Recovery must happen outside the TUI. The user fixes the data, then goes back
  to `csv_path` (Tab×5 wrap), presses Ctrl+U and retypes the path. Reload
  **preserves** entity and dims (1642-1656, measured). Total 75 keys, 40 of
  them typed.
- Warnings-only case (derived from code, not measured here): Proceed is
  enabled, but initial focus is on the issue list, so proceeding takes Tab,
  Enter. A reflexive Escape *cancels* the run.
- Validation *exception* (e.g. bad column types): toast "Validation failed. Fix
  the data and retry.", state Failed, and the error appears only in the Log
  (2452-2460).

## Friction points ranked by impact

| Rank | Friction | Evidence | Impact |
|---:|---|---|---|
| 1 | **80x24: the results/status pane is mostly off-screen and cannot be scrolled to.** Verdict and report path are unreadable | `min-width` 64+42 > 80. Measured 15/40 visible columns. Screenshot `result_J1-share-min_80x24.svg` | Blocks "read result" at the most common SSH default size. The user must fall back to the filesystem |
| 2 | **Required inputs sit at the end of the Tab order** (mode tab = stop 17, dims = stop 23 of 28). Optional and advanced controls come first | Tab order table. 21 forward Tabs Target→Dims, 13 back to the mode tab | +14 keys on J1 if the user tabs forward, and most of J2's 24 Tabs. Users must scroll past options to find what is mandatory |
| 3 | **Session restore cannot restore column choices, dims or the active tab** | J3 measured. 1133, 1264-1267, 1287-1293 | Every relaunch costs a full setup (61 vs 17 in-process). Rate users pay the most |
| 4 | **Rate mode is about 60% more expensive** (78–96 vs 49): hidden tab, wrong defaults (`txn_cnt`, `app_cnt`), three Selects at 3–11 keys each | J2 table. Defaults at 1659-1668 | Slowest and most error-prone journey. A wrong denominator is silent |
| 5 | **Dimension list is every CSV column, with no filtering or type-ahead** (entity, time and metric columns included) | 1650-1656. SelectionList has only `space` binding | Errors such as choosing `issuer_name` as a dimension. Long lists cost one arrow per row |
| 6 | **Attestation and consent modals focus the affirmative button**. They are asked before preflight and validation and re-asked on every retry | Measured initial focus `btn_confirm_yes`. 2313-2319, 2376-2383 | One Enter attests clearing spend or accepts NON-PUBLISHABLE output. Repeated prompts train reflexive Enter |
| 7 | **Ctrl+A / Ctrl+E dead while an Input is focused**, including at launch. The footer hides them and the toast advertises them | Measured Ctrl+A no-op in `csv_path`. Input BINDINGS | Advertised shortcuts appear broken. Discoverability loss |
| 8 | **Preflight reports one problem per attempt.** Consent is asked before the field checks | 2272-2369 | Extra attempts and repeated modals |
| 9 | **Validation-error recovery has no in-TUI path**: no guidance, Proceed disabled, must retype the CSV path | J4b, 75 keys / 40 typed | Slow loop for the commonest data problem |
| 10 | **Horizontal clipping at both sizes** (`validate_input`, export-CSV checkbox, merchant-spend checkbox, Target label) | Tab order table, screenshots | Hidden state on a compliance-relevant checkbox (merchant-spend 4/35) and on validation |
| 11 | **Dead focus stops**: Log and `VerticalScroll` container in the cycle. `btn_preset_help` duplicates F1 | Stops 25–26, 6 | +2 to 3 keys per wrap. The minimal path depends on wrapping |
| 12 | **Select type-ahead exists but is undiscoverable** | Type-ahead column: −6 to −20 keys | Free win if surfaced |
| 13 | **Result extraction needs the mouse**: the report path is shown only as text in Last Run and a 10 s toast | 2565-2571, 2611-2622 | Copying the path requires terminal mouse selection |
| 14 | **Load-on-blur for `csv_path`** means a half-typed path fires an "Invalid Path" error when tabbing away | 1731-1744, 1607-1615 | Noise and spurious error toasts |
| 15 | **README says "Click Run Analysis"** (README.md:141, 343) | Docs | Mouse-centric guidance for an SSH keyboard tool |

## KLM baseline (for Phase 1/2 targets)

`T = n_K × 0.2 + n_M × 1.35` (R excluded; no H/P because the paths are keyboard-only).

| Journey | n_K | n_M | T (s) | M steps counted |
|---|---:|---:|---:|---|
| J1 minimal | 49 | 8 | 20.6 | locate CSV, verify entity col, choose target, accept preset, verify metric, choose dims, initiate, read result |
| J1 via picker | 27 | 8 | 16.2 | same |
| J2 approval | 78 | 8 | 26.4 | locate CSV, target, switch tab, total, approved, dims, initiate, read |
| J2 fraud | 90 | 10 | 31.5 | + fraud column, + read/confirm clearing spend |
| J2 fraud + accuracy_first | 96 | 12 | 35.4 | + choose preset, + read/accept consent |
| J3 restart + change | 61 | 6 | 20.3 | locate CSV, target, change preset, re-pick dims, initiate, read |
| J3b same process | 17 | 3 | 7.5 | change preset, initiate, read |
| J4a preflight recover | 41 | 5 | 15.0 | locate CSV, target, initiate, read toast, re-run (incl. 1 dim) |
| J4b validation recover | 75 | 7 | 24.5 | locate CSV, target, dims, initiate, read issues, re-point CSV, re-run |

M placement follows Card/Moran/Newell heuristics: one M per decision and one
per read-and-understand. It is deliberately conservative. KLM ignores visual
search, which the 80x24 scroll and clipping make substantially worse.

## Reproducing / Phase 2 reuse

```bash
cd /tmp/claude-0/-home-user-autobench/d13cb994-08e3-5f72-b4d1-86adf775fd7d/scratchpad/journeys
/usr/local/bin/uv run --project /home/user/autobench python measure_journeys.py --json results_arrows.json
/usr/local/bin/uv run --project /home/user/autobench python measure_journeys.py --typeahead --json results_typeahead.json
# subset: --only J1 J2-rate-fraud    (J3 needs J1-share-min to run first in the same invocation)
# against a redesigned checkout: AUTOBENCH_REPO=/path/to/checkout ...
```

Outputs: per-journey summary lines (keys by category, M, KLM, run-length key
sequence, notes) and JSON. Each size also writes SVG screenshots
(`screen_WxH.svg`, `result_<journey>_80x24.svg`) next to the script. A full run
takes about 8–10 minutes. Phase 2 must update only the widget ids used in the
`j*` functions if the redesign renames them. The `Driver.go/pick/check` helpers
are id-agnostic.

Caveats: the fake engine returns `privacy_log_authorized=False`, so the log
reports a quarantined run log. That path is in the scratch `logs/`. The minimal
path is computed per step (shorter of Tab and Shift+Tab), not as a global
optimum. Type-ahead types only the first letter, then arrows.

## Appendix: measurement script (verbatim)

```python
"""Phase 0 keystroke measurement for the Autobench TUI (tui_app.py).

Drives the real BenchmarkApp headlessly with Textual Pilot, counting every key
press on the minimal keyboard-only path for each journey. The analysis engine
(``execute_run``) is monkeypatched to return a fake success, so nothing is
analysed and no report is written. HOME, the session file, log dir and the
working directory all point into this scratch folder. Telemetry is off.

Usage (from anywhere):
    /usr/local/bin/uv run --project /home/user/autobench python measure_journeys.py [--typeahead] [--json out.json]

Reuse in Phase 2: point REPO at the redesigned checkout and re-run; the journey
functions only depend on widget ids, so update ids in the J* functions if the
redesign renames them.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(os.environ.get("AUTOBENCH_REPO", "/home/user/autobench"))
S = Path(__file__).resolve().parent
WORK = S / "work"                       # cwd for the app (quick picks, override files)
(WORK / "data").mkdir(parents=True, exist_ok=True)
shutil.copy(REPO / "docs" / "autobench_demo.csv", WORK / "data" / "autobench_demo.csv")
# J4 fixture: demo data with one negative metric value -> ValidationSeverity.ERROR
_rows = (REPO / "docs" / "autobench_demo.csv").read_text().splitlines()
_bad = _rows[:2] + [_rows[2].replace(",120,1200,", ",-120,1200,")] + _rows[3:]
(WORK / "data" / "bad_demo.csv").write_text("\n".join(_bad) + "\n")

os.environ["HOME"] = str(S / "home")
os.environ["AUTOBENCH_TELEMETRY"] = "0"
os.environ["AUTOBENCH_LOG_DIR"] = str(S / "logs")
os.chdir(WORK)
sys.path.insert(0, str(REPO))

import tui_app  # noqa: E402
from core.contracts import AnalysisArtifacts  # noqa: E402
from textual.widgets import Select, SelectionList  # noqa: E402
from textual.widgets._select import SelectOverlay  # noqa: E402

tui_app.SESSION_FILE = S / "home" / "session.yaml"
EXECUTED: list = []


def _fake_execute_run(request, logger):
    EXECUTED.append(request)
    return AnalysisArtifacts(
        metadata={},
        compliance_summary={"posture": request.compliance_posture or "strict",
                            "compliance_verdict": "fully_compliant",
                            "acknowledgement_state": "n/a"},
        report_paths=[str(S / "FAKE_report_not_written.xlsx")],
        privacy_sink_authorized=True,
        privacy_log_authorized=False,
    )


tui_app.execute_run = _fake_execute_run
ARROWS = {"up", "down", "left", "right"}


@dataclass
class Meter:
    name: str
    keys: list = field(default_factory=list)      # (key, category, note)
    mental: list = field(default_factory=list)    # labels of M operators
    notes: list = field(default_factory=list)

    @staticmethod
    def cat(k: str) -> str:
        if k in ("tab", "shift+tab"):
            return "tab"
        if k in ARROWS:
            return "arrow"
        if k == "enter":
            return "enter"
        if k == "space":
            return "space"
        if len(k) == 1:
            return "typed"
        return "chord"  # ctrl+r, escape, f1 ...

    def summary(self) -> dict:
        c: dict = {}
        for _, cat, _ in self.keys:
            c[cat] = c.get(cat, 0) + 1
        k = len(self.keys)
        m = len(self.mental)
        return {"journey": self.name, "total_keys": k, **{f"n_{x}": c.get(x, 0) for x in
                ("tab", "arrow", "enter", "space", "typed", "chord")},
                "M": m, "klm_seconds": round(k * 0.2 + m * 1.35, 1), "notes": self.notes,
                "seq": self.rle()}

    def rle(self) -> str:
        """Run-length key sequence, typed text collapsed: 'type(23) enter tab×2 ...'."""
        out, prev, n = [], None, 0
        for k, cat, _ in self.keys + [(None, None, None)]:
            tok = "type" if cat == "typed" else k
            if tok == prev:
                n += 1
                continue
            if prev is not None:
                out.append(f"{prev}({n})" if prev == "type" else (f"{prev}×{n}" if n > 1 else prev))
            prev, n = tok, 1
        return " ".join(out)


class Driver:
    def __init__(self, pilot, meter: Meter, typeahead: bool):
        self.p, self.app, self.m, self.typeahead = pilot, pilot.app, meter, typeahead

    async def press(self, *keys: str, note: str = ""):
        for k in keys:
            self.m.keys.append((k, Meter.cat(k), note))
            await self.p.press(k)
        await self.p.pause()

    async def type(self, text: str, note: str = ""):
        await self.press(*list(text), note=note)

    def M(self, label: str):
        self.m.mental.append(label)

    def fid(self):
        f = self.app.focused
        return None if f is None else (f.id or type(f).__name__)

    async def go(self, target: str, note: str = ""):
        """Move focus to widget id (or class name) via the shorter of tab / shift+tab."""
        chain = [w.id or type(w).__name__ for w in self.app.screen.focus_chain]
        if target not in chain:
            raise RuntimeError(f"{target} not in focus chain: {chain}")
        cur = self.fid()
        i, j, n = (chain.index(cur) if cur in chain else -1), chain.index(target), len(chain)
        fwd, back = (j - i) % n, (i - j) % n
        key, steps = ("tab", fwd) if fwd <= back else ("shift+tab", back)
        await self.press(*[key] * steps, note=note or f"to {target}")
        assert self.fid() == target, (self.fid(), target)

    async def pick(self, select_id: str, value, note: str = ""):
        """Focused Select: open overlay, move to option, Enter."""
        await self.go(select_id, note)
        sel = self.app.query_one(f"#{select_id}", Select)
        await self.press("enter", note=f"open {select_id}")
        overlay = sel.query_one(SelectOverlay)
        values = [v for _, v in sel._options]
        prompts = [str(p) for p, _ in sel._options]
        tgt = values.index(value)
        if self.typeahead and str(value)[:1].isalnum():
            await self.press(str(prompts[tgt])[0], note="type-ahead")
        cur = overlay.highlighted if overlay.highlighted is not None else 0
        d = tgt - cur
        await self.press(*(["down"] * d if d > 0 else ["up"] * -d), note=f"seek {value}")
        await self.press("enter", note=f"choose {value}")
        await self.p.pause(0.1)
        assert sel.value == value, (select_id, sel.value, value)

    async def check(self, list_id: str, values, note: str = ""):
        await self.go(list_id, note)
        sl = self.app.query_one(f"#{list_id}", SelectionList)
        for v in values:
            idx = next(i for i in range(sl.option_count) if sl.get_option_at_index(i).value == v)
            guard = 0
            while sl.highlighted != idx and guard < 60:
                cur = -1 if sl.highlighted is None else sl.highlighted
                await self.press("down" if idx > cur else "up", note=f"seek {v}")
                guard += 1
            await self.press("space", note=f"toggle {v}")
        assert set(values) <= set(sl.selected), (list_id, sl.selected)

    async def wait_screen(self, cls_name: str, timeout=20.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if type(self.app.screen).__name__ == cls_name:
                await self.p.pause(0.1)
                return True
            await self.p.pause(0.05)
        return False

    async def wait_done(self, timeout=60.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.app._run_state in ("success", "error", "blocked"):
                return self.app._run_state
            if type(self.app.screen).__name__ != "Screen":
                return "modal:" + type(self.app.screen).__name__
            await self.p.pause(0.1)
        return self.app._run_state

    async def confirm_modal(self, button_id: str, note: str):
        """Activate a modal button from wherever the modal put initial focus."""
        if self.fid() != button_id:
            await self.go(button_id, note=f"{note}: focus {button_id}")
        await self.press("enter", note=note)

    def visible(self, wid: str) -> str:
        w = self.app.query_one(f"#{wid}")
        r, scr = w.region, self.app.screen.region
        inter = r.intersection(scr)
        return f"{wid}: region={tuple(r)} visible_cols={inter.width}/{w.outer_size.width}"


# ───────────────────────────── Journeys ──────────────────────────────
CSV = "data/autobench_demo.csv"


async def load_csv(d: Driver, path=CSV, via_picker=False):
    d.M("recall/locate CSV path")
    if via_picker:
        await d.press("ctrl+o", note="open picker")
        await d.p.pause(0.2)
        d.m.notes.append(f"picker initial focus: {d.fid()}")
        # quick-pick list: first item is the only CSV under cwd/ data/
        lv = d.app.screen.query_one("#picker_quick_list")
        items = [c.file_path for c in lv.children]
        if d.fid() != "picker_quick_list":
            await d.go("picker_quick_list")
        tgt = items.index(path)
        cur = lv.index if lv.index is not None else 0
        await d.press(*["down"] * (tgt - cur), note="seek file")
        await d.press("enter", note="pick file")
    else:
        assert d.fid() == "csv_path"
        await d.type(path, note="type CSV path")
        await d.press("enter", note="load headers")
    await d.p.pause(0.3)


async def j1_share(d: Driver, *, via_picker=False, time_col=False, run_key="ctrl+r"):
    await load_csv(d, via_picker=via_picker)
    d.M("verify entity column default (issuer_name)")
    d.M("choose target entity")
    await d.pick("entity_name", "Target")
    if time_col:
        d.M("decide time column")
        await d.pick("time_col", "year_month")
    d.M("decide preset (accept default compliance_strict)")
    d.M("verify metric default (txn_cnt)")
    d.M("choose dimensions")
    await d.check("share_dims", ["card_type", "input_mode"])
    d.M("initiate run")
    if run_key == "button":
        await d.go("btn_run")
        await d.press("enter", note="run")
    else:
        await d.press(run_key, note="run")
    state = await d.wait_done()
    if state.startswith("modal:"):
        d.m.notes.append(f"unexpected modal {state}")
    d.M("read result panel")
    return state


async def j2_rate(d: Driver, *, fraud=False, preset=None):
    await load_csv(d)
    d.M("choose target entity")
    await d.pick("entity_name", "Target")
    if preset:
        d.M(f"choose preset {preset}")
        await d.pick("preset_select", preset)
    d.M("switch to Rate tab")
    await d.go("ContentTabs")
    await d.press("right", note="Rate tab")
    await d.p.pause(0.2)
    assert tui_app.BenchmarkApp._analysis_mode(d.app) == "rate"
    d.M("choose Total (default txn_cnt is wrong for this file)")
    await d.pick("rate_total", "total")
    d.M("choose Approved column")
    await d.pick("rate_approved", "approved")
    if fraud:
        d.M("choose Fraud column")
        await d.pick("rate_fraud", "fraud")
    d.M("choose dimensions")
    await d.check("rate_dims", ["card_type", "input_mode"])
    d.M("initiate run")
    await d.press("ctrl+r", note="run")
    for _ in range(3):
        state = await d.wait_done()
        if state == "modal:ConfirmScreen":
            d.m.notes.append(f"accuracy-first consent modal, initial focus={d.fid()}")
            d.M("read + accept accuracy_first consent")
            await d.confirm_modal("btn_confirm_yes", "accept consent")
        elif state == "modal:ClearingSpendConfirmScreen":
            d.m.notes.append(f"clearing-spend modal, initial focus={d.fid()}")
            d.M("read + confirm clearing-spend basis")
            await d.confirm_modal("btn_confirm_yes", "confirm clearing spend")
        elif state == "modal:ValidationModal":
            d.m.notes.append(f"validation modal, initial focus={d.fid()}")
            d.M("read validation issues")
            await d.confirm_modal("btn_proceed", "proceed")
        else:
            break
        await d.p.pause(0.2)
    d.M("read result panel")
    return state


async def j3_rerun(d: Driver):
    """Second process after J1 + ctrl+q: change preset and re-run."""
    restored = {
        "csv_path": d.app.query_one("#csv_path").value,
        "entity_col": str(d.app.query_one("#entity_col").value),
        "preset": str(d.app.query_one("#preset_select").value),
        "share_dims": list(d.app.query_one("#share_dims").selected),
        "time_col": str(d.app.query_one("#time_col").value),
    }
    d.m.notes.append(f"restored at mount: {restored}")
    await load_csv(d)
    restored2 = {
        "entity_col": str(d.app.query_one("#entity_col").value),
        "share_metric": str(d.app.query_one("#share_metric").value),
        "share_dims": list(d.app.query_one("#share_dims").selected),
    }
    d.m.notes.append(f"after CSV reload: {restored2}")
    d.M("re-choose target entity (never restored)")
    await d.pick("entity_name", "Target")
    d.M("change the parameter: preset -> strategic_consistency")
    await d.pick("preset_select", "strategic_consistency")
    d.M("re-choose dimensions (lost)")
    await d.check("share_dims", ["card_type", "input_mode"])
    d.M("initiate run")
    await d.press("ctrl+r", note="run")
    state = await d.wait_done()
    d.M("read result panel")
    return state


async def j3b_same_process(d: Driver):
    """J1 then, in the same process, change preset and re-run (no restart)."""
    await j1_share(d)
    k0, m0 = len(d.m.keys), len(d.m.mental)
    d.m.notes.append(f"focus after run 1: {d.fid()}")
    d.M("change the parameter: preset -> strategic_consistency")
    await d.pick("preset_select", "strategic_consistency")
    d.M("initiate run")
    await d.press("ctrl+r", note="run")
    state = await d.wait_done()
    d.M("read result panel")
    d.m.keys, d.m.mental = d.m.keys[k0:], d.m.mental[m0:]  # count only the re-run
    return state


async def j4_preflight(d: Driver):
    """Forget dimensions -> _fail_launch -> recover."""
    await load_csv(d)
    d.M("choose target entity")
    await d.pick("entity_name", "Target")
    d.M("initiate run (dims forgotten)")
    await d.press("ctrl+r", note="run")
    await d.p.pause(1.0)
    log = "\n".join(d.app.query_one("#log_output").lines)
    d.m.notes.append(f"after block: state={d.app._run_state} focus={d.fid()} "
                     f"log_has_error={'ERROR: Select at least one dimension' in log}")
    d.M("read toast, understand what is missing")
    await d.check("share_dims", ["card_type"])
    d.M("re-run")
    await d.press("ctrl+r", note="run")
    return await d.wait_done()


async def j4_validation(d: Driver):
    """Negative metric -> ValidationModal with ERROR -> cancel -> fix file -> rerun."""
    await load_csv(d, path="data/bad_demo.csv")
    d.M("choose target entity")
    await d.pick("entity_name", "Target")
    d.M("choose dimensions")
    await d.check("share_dims", ["card_type", "input_mode"])
    d.M("initiate run")
    await d.press("ctrl+r", note="run")
    state = await d.wait_done()
    d.m.notes.append(f"first state={state} modal_focus={d.fid()}")
    if state == "modal:ValidationModal":
        proceed = d.app.screen.query_one("#btn_proceed")
        d.m.notes.append(f"Proceed disabled={proceed.disabled}; chain="
                         f"{[w.id or type(w).__name__ for w in d.app.screen.focus_chain]}")
        d.M("read issue list")
        await d.press("escape", note="cancel validation")
        await d.p.pause(0.3)
        d.m.notes.append(f"after cancel: state={d.app._run_state} focus={d.fid()}")
    # recovery: point at the corrected file (user fixed data outside the TUI)
    d.M("fix data outside TUI, re-point CSV path")
    await d.go("csv_path")
    await d.press("ctrl+u", note="clear path")
    await d.type(CSV, note="type corrected path")
    await d.press("enter", note="reload headers")
    await d.p.pause(0.3)
    d.m.notes.append(f"after reload: entity_name={d.app.query_one('#entity_name').value} "
                     f"dims={list(d.app.query_one('#share_dims').selected)}")
    d.M("re-run")
    await d.press("ctrl+r", note="run")
    return await d.wait_done()


async def tab_order(size):
    out = []
    async with tui_app.BenchmarkApp().run_test(size=size) as pilot:
        app = pilot.app
        await pilot.pause(0.3)
        seen = []
        for _ in range(40):
            f = app.focused
            key = id(f)
            if key in seen:
                break
            seen.append(key)
            pane = next((a for a in f.ancestors_with_self if a.id in ("config_pane", "activity_pane")), None)
            clip = app.screen.region if pane is None else pane.region.intersection(app.screen.region)
            r = f.region.intersection(clip)
            out.append({"i": len(seen) - 1, "widget": f"{type(f).__name__}#{f.id}",
                        "parent": f"{type(f.parent).__name__}#{f.parent.id}",
                        "visible_cols": f"{r.width}/{f.region.width}"})
            await pilot.press("tab")
            await pilot.pause()
        geo = {}
        for wid in ("config_pane", "activity_pane", "run_status", "results_panel", "log_output",
                    "share_export_csv", "privacy_merchant_spend_scope", "validate_input"):
            w = app.query_one(f"#{wid}")
            r = w.region
            pane = next((a for a in w.ancestors if a.id in ("config_pane", "activity_pane")), None)
            clip = app.screen.region if pane is None else pane.region.intersection(app.screen.region)
            geo[wid] = {"region": tuple(r), "on_screen_cols": r.intersection(clip).width}
        app.save_screenshot(str(S / f"screen_{size[0]}x{size[1]}.svg"))
        # Ctrl+A shadowing check: initial focus is an Input
        app.query_one("#csv_path").focus()
        await pilot.press("ctrl+a")
        await pilot.pause()
        geo["ctrl+a_from_input_toggles_advanced"] = not app.query_one("#advanced_opt").collapsed
    return out, geo


async def _run_journey(name, fn, size, typeahead, fresh_session=True, **kw):
    if fresh_session and tui_app.SESSION_FILE.exists():
        tui_app.SESSION_FILE.unlink()
    m = Meter(f"{name}@{size[0]}x{size[1]}")
    EXECUTED.clear()
    async with tui_app.BenchmarkApp().run_test(size=size) as pilot:
        await pilot.pause(0.3)
        d = Driver(pilot, m, typeahead)
        state = await fn(d, **kw)
        m.notes.append(f"final state={state}; engine calls={len(EXECUTED)}")
        res = str(pilot.app.query_one("#results_panel").content)
        rp = pilot.app.query_one("#results_panel")
        m.notes.append(f"results_panel lines={len(res.splitlines())} region={tuple(rp.region)} "
                       f"on_screen_cols={rp.region.intersection(pilot.app.screen.region).width}")
        if name.startswith("J1") and fresh_session:
            await pilot.press("ctrl+q")  # saves session for J3
            await pilot.pause(0.2)
        if size == (80, 24):
            pilot.app.save_screenshot(str(S / f"result_{name}_{size[0]}x{size[1]}.svg"))
    return m.summary()


ONLY: set = set()


async def run_journey_filtered(name, *a, **kw):
    if ONLY and not any(name.startswith(o) for o in ONLY):
        return None
    return await _run_journey(name, *a, **kw)


async def main(typeahead: bool):
    results, orders = [], {}
    for size in ((120, 40), (80, 24)):
        orders[f"{size[0]}x{size[1]}"] = await tab_order(size)
        results.append(await run_journey_filtered("J3b-rerun-same-process", j3b_same_process, size, typeahead))
        results.append(await run_journey_filtered("J1-share-min", j1_share, size, typeahead))
        results.append(await run_journey_filtered("J3-rerun-after-restore", j3_rerun, size, typeahead,
                                         fresh_session=False))
        results.append(await run_journey_filtered("J1-share+time", j1_share, size, typeahead, time_col=True))
        results.append(await run_journey_filtered("J1-share-picker", j1_share, size, typeahead, via_picker=True))
        results.append(await run_journey_filtered("J1-share-tab-to-button", j1_share, size, typeahead,
                                         run_key="button"))
        results.append(await run_journey_filtered("J2-rate-approval", j2_rate, size, typeahead))
        results.append(await run_journey_filtered("J2-rate-fraud", j2_rate, size, typeahead, fraud=True))
        results.append(await run_journey_filtered("J2-rate-fraud-accuracy-first", j2_rate, size, typeahead,
                                         fraud=True, preset="low_distortion"))
        results.append(await run_journey_filtered("J4-preflight-recover", j4_preflight, size, typeahead))
        results.append(await run_journey_filtered("J4-validation-recover", j4_validation, size, typeahead))
    return results, orders


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--typeahead", action="store_true")
    ap.add_argument("--json", default=str(S / "results.json"))
    ap.add_argument("--only", nargs="*", default=[], help="journey name prefixes to run")
    a = ap.parse_args()
    ONLY.update(a.only)
    a.json = str(Path(a.json).resolve()) if os.path.isabs(a.json) else str(S / a.json)
    res, orders = asyncio.run(main(a.typeahead))
    res = [r for r in res if r]
    Path(a.json).write_text(json.dumps({"results": res, "tab_order": orders}, indent=1, default=str))
    for r in res:
        print(f"{r['journey']:42s} keys={r['total_keys']:3d} typed={r['n_typed']:2d} "
              f"tab={r['n_tab']:2d} arrow={r['n_arrow']:2d} M={r['M']:2d} KLM={r['klm_seconds']}s | {r['seq']}")
        for n in r["notes"]:
            print("      -", n)
```
