# TUI Redesign Phase 0 — 03 Expert Heuristic Review

**Scope.** `tui_app.py` (Textual 7.5.0), reviewed against Nielsen's 10 usability heuristics, plus terminal-specific criteria, a CSS/token audit and a copy audit.
**Method.** I ran the app headlessly with `App.run_test(size=…, notifications=True)` at 120x40 and 80x24 and saved SVG screenshots with `save_screenshot()`. I converted them to PNG with Chromium and inspected each one. `execute_run` was replaced with stubs for success, privacy denial, `RunBlocked`, `RunAborted`, an unexpected exception, and a run that blocks on an event. Telemetry functions were no-op'd, and `SESSION_FILE`, `AUTOBENCH_LOG_DIR` and the CWD were all isolated in the scratch dir. No repo code was changed. NO_COLOR=1 and the `textual-ansi` theme were captured at 120x40.
**Severity scale (Nielsen).** 0 = not a problem / positive note · 1 = cosmetic · 2 = minor · 3 = major · 4 = catastrophe.
**Note on notifications.** `run_test()` disables toasts by default (`notifications=False`), so the existing UX tests never see toast pile-up. I enabled toasts for these captures.

---

## Summary

| Severity | Count |
|---|---|
| 4 – catastrophe | 1 |
| 3 – major | 10 |
| 2 – minor | 24 |
| 1 – cosmetic | 9 |
| 0 – positive note | 1 |
| **Total** | **45** |

### Top 10 issues (ranked)

| # | ID | Sev | Issue | Evidence |
|---|---|---|---|---|
| 1 | F29 | 4 | **The validation modal hides issues.** The first `ListItem(Vertical(...))` grows to fill the list, so only 1 of 3 issues shows, even at 120x40. Rich also swallows the `[error]`/`[warning]` severity prefix as a markup tag. The operator can press **Proceed** past warnings they never saw. | `tui_app.py:425-430`; `11_modal_validation_120x40.png`, `11_modal_validation_80x24.png` |
| 2 | T1 | 3 | **The layout breaks at 80x24.** `#config_pane` `min-width: 64` plus `#activity_pane` `min-width: 42` adds up to 106 columns, more than 80. The status/log pane is clipped off the right edge ("Mode shar", "Preset comp"), and the footer is truncated. | `tui_app.py:519-520, 628`; `01_launch_80x24.png`, `19_preflight_error_no_dims_80x24.png` |
| 3 | T2/F21 | 3 | **`ctrl+a` / `ctrl+e` don't work while a text field has focus.** `Input` binds `home,ctrl+a` and `end,ctrl+e`, and initial focus is the CSV path `Input`. Pressing `ctrl+a` left Advanced collapsed. The Footer hides both bindings until focus leaves an Input. `ctrl+a` is also the GNU screen prefix and a common tmux prefix. | `tui_app.py:501-507, 1138`; `05_advanced_expanded_120x40.png` (still collapsed), `01_launch_120x40.png` vs `21_focus_after_6_tabs_120x40.png` (footer differs) |
| 4 | T5 | 3 | **Under NO_COLOR the key privacy outcome becomes nearly invisible.** Hard-coded Rich `[red]`/`[green]`/`[yellow]` markup renders as dark grey on dark grey: "Blocked", "violations_detected", "Publication withheld". | `tui_app.py:1340-1347, 2560-2592`; `15_blocked_privacy_denial_120x40_nocolor.png` |
| 5 | T4 | 3 | **Checked vs unchecked looks the same apart from colour.** Checkbox and SelectionList draw an "X" in both states, and only the colour/brightness changes. This is close to unreadable in NO_COLOR and the ANSI theme. | `03_share_tab_120x40_nocolor.png`, `03_share_tab_120x40_ansi.png` |
| 6 | F16 | 3 | **An `accuracy_first` preset plus Apply Overrides leads to a dead end.** Consent is only asked `if preset and not values["config"]`. With overrides applied, the modal is skipped and core raises `RunBlocked("accuracy_first compliance_posture requires explicit acknowledgement…")`. The operator has no way to give consent. Privacy itself is not weakened: core still blocks the run. | `tui_app.py:2304-2319`; `core/analysis_run.py:1238-1245` |
| 7 | F28 | 3 | **Unexpected exceptions dump a raw Python traceback into the log.** No toast appears. Last Run shows only the bare `repr`, e.g. `'card_type_input_mode'`. | `tui_app.py:2633-2637`; `18_error_unexpected_exception_120x40.png` |
| 8 | F09 | 3 | **A running analysis can't be cancelled.** The only exit is Quit, which has its own confirm and kills the whole app. | `tui_app.py:1971-1985`; `12_running_*`, `13_modal_quit_while_running_*` |
| 9 | F01 | 3 | **A run gives no progress feedback.** The status pane shows only "Running" and elapsed seconds, with no stage or step. The Run button is usually scrolled off-screen, and the form stays editable. | `tui_app.py:1349-1363, 1393-1405`; `12_running_120x40.png` |
| 10 | F06 | 3 | **Raw internal identifiers appear in user-facing copy.** Examples: `fully_compliant`, `violations_detected`, `control3_numeric_policy_blocked`, `posture=strict`, and log line `Compliance: posture=… verdict=… acknowledgement=…`. | `tui_app.py:2553-2583`; `14_success_*`, `15_blocked_*` |

Runner-up: **F04 toast pile-up**. At 80x24, three or four toasts cover more than half the screen, including modal buttons such as Cancel (`13_modal_quit_while_running_80x24.png`, `07_modal_csv_picker_80x24.png`).

---

## 1. Findings by heuristic

### H1 — Visibility of system status

| ID | Sev | Finding | Evidence | Redesign implication |
|---|---|---|---|---|
| F01 | 3 | The running state shows only `● Running` and `Elapsed Ns`, with no stage, step count or spinner. Once the config pane is scrolled, the Run button (the only other state cue) is off-screen. | `tui_app.py:1349-1363, 1393-1405`; `12_running_120x40.png` | Add a persistent run bar with stage text (validate, load, solve, write) that is visible wherever the user has scrolled. |
| F02 | 2 | "Run Status" and "Last Run" both show the same badge, which is redundant. The status reads **Validating** while the clearing-spend attestation modal waits for an answer, so the state label doesn't match what's happening. | `tui_app.py:1373-1391, 1422-1425`; `14_success_120x40.png`, `09_modal_clearing_spend_120x40.png` | Use one status component. Add an explicit "Awaiting confirmation" state. |
| F03 | 2 | The log doesn't wrap. On a 120-col screen, about 30 of the ~55 visible columns go to `YYYY-MM-DD HH:MM:SS,mmm - INFO - `. Outcome lines are cut off, e.g. "Control 3 privacy denial: all benchmark-bea…" and "Non-publishable run log (do not share): /tm…". | `tui_app.py:1103, 1919, 2400`; `15_blocked_privacy_denial_120x40.png` | Wrap the log, use a short `HH:MM:SS` stamp, and show the level as a glyph. Put outcome lines in a separate result card, not only in the log. |
| F04 | 2 | Toasts pile up. The 6 s "Keyboard shortcuts" toast, "CSV Loaded", a **duplicate** "CSV Loaded" (blurring `#csv_path` reloads the headers) and the run result all stack. At 80x24 they cover the modal Cancel buttons and the focused field. | `tui_app.py:1139-1144, 1672-1677, 1731-1744`; `19_preflight_error_no_dims_80x24.png`, `21_focus_after_6_tabs_120x40.png`, `13_modal_quit_while_running_80x24.png` | Reserve toasts for transient events. Don't re-announce an unchanged CSV. Pause or hide toasts while a modal is open. |
| F05 | 1 | The CSV path `Input` shows the start of the path (`/tmp/claude-0/-home-user-autobe…`), not the filename. The meta line underneath makes up for it. | `02_loaded_top_80x24.png` | Show the filename prominently and keep the full path secondary. |

### H2 — Match between system and the real world

| ID | Sev | Finding | Evidence | Redesign implication |
|---|---|---|---|---|
| F06 | 3 | Enum and snake_case values are shown verbatim: verdicts, `posture=strict`, withholding reason codes, preset IDs. | `tui_app.py:2553, 2558-2567, 2581-2583`; `15_blocked_privacy_denial_120x40.png` | Add a label map in `core/` that turns verdicts and reasons into plain language, and show the code only as secondary text. |
| F07 | 2 | Several labels are unexplained jargon: "Privacy rule sweep mode", "Anonymized aggregated merchant-spend context (enables 4/35)", "Fraud in BPS", "Analyze impact", "Tolerance (pp)", "Lambda Penalty", and the subtitle "Control 3.2 dimensional analysis". | `tui_app.py:851, 899, 903, 932, 937, 1081, 965-975` | Every non-obvious control needs a one-line hint or tooltip. Rename controls by outcome, not by mechanism. |
| F08 | 1 | Secondary-metric and dimension lists offer every column, including the entity and time columns (`issuer_name`, `year_month`), with no type hint. | `tui_app.py:1649-1656`; `03_share_tab_120x40.png` | Filter or annotate column candidates by role or type (numeric vs categorical). |

### H3 — User control and freedom

| ID | Sev | Finding | Evidence | Redesign implication |
|---|---|---|---|---|
| F09 | 3 | A run can't be cancelled. Quit is the only way out, and it ends the app. | `tui_app.py:1971-1985`; `13_modal_quit_while_running_120x40.png` | Add a cooperative cancel to the shared run seam, with a Cancel run action. |
| F10 | 2 | `ctrl+l` clears the log immediately with no undo, and every new run also clears it (`log_widget.clear`). The log is the only place the quarantined-log path and tracebacks appear. | `tui_app.py:1967-1969, 2266` | Keep per-run history (collapsible runs). Make clearing explicit or undoable. |
| F11 | 2 | Every `ConfirmScreen` puts initial focus on the affirmative, red-variant button, so Enter confirms "Quit", "Confirm" (the clearing-spend attestation) and "I understand — proceed". | `tui_app.py:290-293`; `09_modal_clearing_spend_120x40.png`, `13_modal_quit_while_running_80x24.png` | Focus the safe choice by default for attestations and destructive actions. Require a deliberate keypress to attest. |

### H4 — Consistency and standards

| ID | Sev | Finding | Evidence | Redesign implication |
|---|---|---|---|---|
| F12 | 2 | Button variants carry no consistent meaning. All confirms are `variant="error"` (red), including a benign attestation. In ValidationModal, Proceed is green and **Cancel is red**. | `tui_app.py:292, 417-418`; `11_modal_validation_120x40.png` | Define button roles (primary, secondary, destructive) once and apply them consistently. |
| F13 | 2 | The numbered sections "1–4" are broken up by two unnumbered collapsibles (Compliance Declarations, Advanced) between 3 and 4. The Run button sits outside every section. | `tui_app.py:865, 873, 883, 944, 959, 1040, 1086`; `06_compliance_expanded_120x40.png` | Rework the information architecture: steps, then an optional or advanced area, then a fixed action bar. |
| F14 | 1 | Naming and casing are inconsistent: "Export Adv" / "Advanced Export" / "Export Config" / "Advanced Overrides". The Advanced pane uses Title Case labels while the rest is sentence case. The log uses "..." where other UI uses "…". Modals mix "Close" and "Cancel". | `tui_app.py:506, 1033, 2224, 2249, 2267` | Write a copy style guide: sentence case, one term per concept. |

### H5 — Error prevention

| ID | Sev | Finding | Evidence | Redesign implication |
|---|---|---|---|---|
| F16 | 3 | Applying advanced overrides bypasses the posture lookup and consent modal. An `accuracy_first` preset then fails late in core with `RunBlocked` and can't be recovered from the UI. (Core enforcement holds, so privacy is not weakened.) | `tui_app.py:2304-2319`; `core/analysis_run.py:1238-1245`; `core/preset_workflow.py:26-40` (posture is written into the override YAML) | Resolve the posture from the *effective* config, not only the preset. Ask for consent in both paths. |
| F17 | 2 | Required fields are checked only on Run, one at a time, and appear as a toast plus a log line. Fields carry no required markers or inline errors. | `tui_app.py:2270-2369`; `19_preflight_error_no_dims_120x40.png` | Validate live and show a readiness checklist. Keep Run disabled, with the reason shown, until the form is complete. |
| F18 | 2 | Advanced fields are free text with no type or range checks; `try_parse_number` quietly keeps non-numeric strings. "Strategy" is free text for an enum ("greedy / random"). Placeholders ("e.g., 100") look like preset values, so empty and inherited fields can't be told apart. | `tui_app.py:963-1030`; `utils/config_overrides.py:89-100`; `05b_advanced_expanded_direct_80x24.png` | Use typed inputs (`Input(type="number")`, validators, Select for enums). Show inherited values distinctly. |
| F19 | 2 | During a run, the form stays fully editable; only the Run button is disabled, so it's unclear which values the run used. | `tui_app.py:1393-1405`; `12_running_120x40.png` | Lock the form during a run, or show a frozen summary of the run's inputs. |
| F20 | 1 | The output filename field gives no guidance on extension or directory, only "Auto-generated if blank". | `tui_app.py:890` | Show the resolved output path before the run. |

### H6 — Recognition rather than recall

| ID | Sev | Finding | Evidence | Redesign implication |
|---|---|---|---|---|
| F21 | 3 | Bindings are only fully listed in a 6 s launch toast. The Footer leaves out `^a`/`^e` whenever an Input has focus (which it does at launch). At 80 cols the Footer truncates. `ctrl+q` (Quit) is never shown. | `tui_app.py:501-507, 1139-1144`; `01_launch_120x40.png`, `21_focus_after_6_tabs_120x40.png`, `19_preflight_error_no_dims_80x24.png` | Add a persistent `?` key-help screen and use bindings that Input doesn't shadow. Pick bindings that fit an 80-col Footer. |
| F22 | 2 | Checkbox rows overflow their row and get cut off. At 120x40, "Validate input" becomes "Valida…", "Export balanced CSV" becomes "E", and "Fraud in BPS" is entirely off-screen on the Rate tab. | `tui_app.py:897-903, 1052-1055, 1077-1081`; `01_launch_120x40.png`, `03_share_tab_120x40.png`, `04_rate_tab_120x40.png` | Stack checkboxes vertically or use a compact toggle list. Never put more than two per row. |
| F23 | 1 | Labels collide or truncate: "Time period column (optional)Output filename" and "Target entity (blank = peer-on". | `tui_app.py:879, 886`; `01_launch_120x40.png` | Put labels above fields with a gutter, and keep label text short. |

### H7 — Flexibility and efficiency of use

| ID | Sev | Finding | Evidence | Redesign implication |
|---|---|---|---|---|
| F24 | 2 | The form is long (about 3 screens at 120x40) with no way to jump between sections, and Run sits at the very bottom. `ctrl+r` helps, but `ctrl+a`/`ctrl+e` are broken in practice (T2). | `03_share_tab_120x40.png`, `05b_advanced_expanded_direct_120x40.png` | Add section jump keys (e.g. `1`–`4` or `alt+n`) and a fixed action bar. |
| F25 | 1 | The command palette (`^p`) is present but the app registers no commands of its own. | Footer in all shots | Register app actions (run, open, toggle advanced, show help) as palette commands. |

### H8 — Aesthetic and minimalist design

| ID | Sev | Finding | Evidence | Redesign implication |
|---|---|---|---|---|
| F26 | 2 | Density is low: 3-row Input/Select widgets, `margin-bottom: 1` on almost everything (22 declarations), and the Advanced section adds about 20 fields in the same vertical form. | CSS audit §3; `05b_advanced_expanded_direct_120x40.png` | Use a compact form style with 1-row inputs and move Advanced to a separate screen or tab. |
| F27 | 1 | The header shows the title twice (the terminal title plus "Title — Subtitle"). The preset blurb includes legacy noise such as "(formerly strict_privacy)". | `tui_app.py:850-851, 857`; `presets/*.yaml` descriptions | Trim the chrome and strip legacy aliases from the descriptions shown in the UI. |

### H9 — Help users recognize, diagnose, and recover from errors

| ID | Sev | Finding | Evidence | Redesign implication |
|---|---|---|---|---|
| F29 | **4** | ValidationModal shows 1 of N issues (see Top 10 #1). The severity tag `[error]` is parsed as markup and disappears. "Rows: 4, 17, 31" doesn't say whether rows are 0- or 1-based. Proceed is disabled with no explanation. The list's `padding: 1` plus the border wastes 4 rows. | `tui_app.py:405-433, 741-753`; `11_modal_validation_120x40.png`, `11_modal_validation_80x24.png` | Use a dense, scrollable table with one row per issue and a severity glyph. Explain why Proceed is unavailable. Escape all content inserted into markup. |
| F28 | 3 | An unexpected exception writes `traceback.format_exc()` into the user log, sends no toast, and puts `[red]{exc}[/red]` into Last Run. A `KeyError` then shows as just `'card_type_input_mode'`. | `tui_app.py:2633-2637`; `18_error_unexpected_exception_120x40.png` | Use a friendly error card (what happened, what to try, where the diagnostic log is) and keep tracebacks in the file log. |
| F30 | 2 | Blocked and denied outcomes say *what* happened but not *what to do next*, e.g. "Publication withheld (control3_numeric_policy_blocked)" with no remediation. | `tui_app.py:2572-2609`; `15_blocked_privacy_denial_120x40.png`, `16_blocked_runblocked_120x40.png` | Map each withholding reason to a next step, such as fewer dimensions, a different preset, or a documentation link. |
| F31 | 2 | **Markup injection.** Exception text, report paths, CSV filenames and validation messages are put into Rich markup without escaping. Content containing `[...]` gets mangled, as F29 shows, or can raise a `MarkupError`. | `tui_app.py:425, 1560, 1697, 2570, 2591, 2626, 2631, 2637` | Run all dynamic text through `rich.markup.escape`, or build `Content`/`Text` objects in the shared formatting layer. |
| F32 | 1 | "Validation failed. Fix the data and retry." is a generic toast with no title and no pointer to the failing field or row. | `tui_app.py:2458` | Name the failing check and link to the log line. |

### H10 — Help and documentation

| ID | Sev | Finding | Evidence | Redesign implication |
|---|---|---|---|---|
| F33 | 2 | The only help is the "Preset Guide", which is hard-coded Markdown that has drifted from `presets/*.yaml`. It never says that `low_distortion` and `minimal_distortion` are `accuracy_first` and need per-run consent, and it shows no postures. At 80x24 only about 6 lines are visible above a 3-row Close button. | `tui_app.py:339-381`; `presets/low_distortion.yaml:3-4`; `10_modal_preset_help_80x24.png` | Generate preset help from the preset YAML through `core/preset_workflow`, and show posture and consent requirements. |
| F34 | 2 | Fields have no contextual help, there's no general help or `?` screen, and nothing links to `docs/` (onboarding or the PT-BR preset guide). | — | Add a help screen with key bindings, a workflow overview and the privacy concepts. Add per-field hint text. |

---

## 2. Terminal-specific findings

| ID | Sev | Criterion | Finding | Evidence | Implication |
|---|---|---|---|---|---|
| T1 | 3 | Behaviour at 80x24 | The two-pane minimum widths (64 + 42) exceed 80 columns, so the activity pane is clipped and Run Status/Log can't be read. The Footer drops entries. Modals overflow: the CSV picker's quick list shows 3 rows and its Cancel button is pushed out or covered, Preset help shows about 6 lines, and Validation shows 1 issue. | `tui_app.py:519-520, 628, 725-732, 769-776, 324-331`; `01_launch_80x24.png`, `07_modal_csv_picker_80x24.png`, `10_modal_preset_help_80x24.png` | Add a responsive breakpoint below about 110 columns (single pane, with status as a 1–3 line bar and the log on a separate tab). Size modals in rows, not percentages. |
| T2 | 3 | Binding conflicts | `ctrl+a` and `ctrl+e` are shadowed by `Input` (readline home/end; confirmed by the Textual 7.5 `Input.BINDINGS` dump and `05_advanced_expanded_*`). `ctrl+a` is the GNU screen prefix and a widely used tmux prefix. `ctrl+l` is conventionally *redraw*, but here it destructively clears the log. `F1` is taken by GNOME Terminal and some other emulators for their own help. `ctrl+q`/`ctrl+s` can be eaten by XON/XOFF on misconfigured links. `ctrl+o`/`ctrl+r` are fine in raw mode. | `tui_app.py:501-507`; `.venv/.../textual/widgets/_input.py` BINDINGS | Choose bindings that work inside text fields and don't clash with multiplexers, e.g. `f2`–`f5` with letter mnemonics, or make Run a `priority=True` binding. Use `?` for help. Don't bind `ctrl+l` to anything destructive. |
| T3 | 2 | Focus visibility | Focus is shown by a subtle tint: `.form-section:focus-within` goes from `$primary 40%` to `$primary`, and a focused Button only inverts its label (Preset Guide in `21_focus_after_6_tabs_120x40.png`). In NO_COLOR, focus is almost invisible. | `tui_app.py:534-536, 613-615` | Define a focus token (border style change plus a glyph or inverse), not only a colour shift. |
| T4 | 3 | Colour independence (state) | The Checkbox/SelectionList "X" glyph is drawn in both states. | `03_share_tab_120x40_nocolor.png`, `03_share_tab_120x40_ansi.png` | Use `[x]`/`[ ]` or `☑`/`☐` glyph pairs. |
| T5 | 3 | Colour independence (status) | Hard-coded Rich colour names (`[red]` ×16, `[green]` ×7, `[yellow]` ×5, `[cyan]` ×3) ignore the theme and NO_COLOR handling. Under NO_COLOR they render as near-invisible grey: Blocked, the verdict and Publication withheld. The status dot `●` is the same glyph for every state, so only the word that follows tells them apart. | `tui_app.py:1340-1347, 2560-2592`; `15_blocked_privacy_denial_120x40_nocolor.png` | Give each status a distinct glyph (✓ ✗ ⚠ ⏵ ■) and colour it through theme variables (`[$error]`), never named colours. |
| T6 | 2 | Theme robustness | With the `textual-ansi` theme, Footer descriptions disappear and only `^o ^r f1 ^l` remain. The app also forces `self.theme = "tokyo-night"` on mount, which overrides the user's choice and the terminal palette. | `tui_app.py:1115`; `03_share_tab_120x40_ansi.png`, `15_blocked_privacy_denial_120x40_ansi.png` | Respect a `TEXTUAL_THEME` or user setting, and test an ANSI or 16-colour theme in CI snapshots. |
| T7 | 2 | Scroll traps (by inspection) | Nested scrollers sit inside `#config_pane` (`VerticalScroll`): four `SelectionList`s at `height: 7`, `#results_panel` (`max-height: 14; overflow-y: auto`) and Markdown in help. The mouse wheel over a list scrolls the list, not the page, and `Log` scrolls only with focus or the mouse. | `tui_app.py:607-611, 642-651`; `03_share_tab_120x40.png` | Avoid nested scroll regions in a form. Use a dedicated picker for long lists. |
| T8 | 2 | Log readability | `highlight=False` (deliberate, for performance) means no level colouring. Lines are prefixed with a 30-char timestamp, never wrap, and are capped at `max_lines=2000`. Tool messages ("Starting analysis sequence...") and logger lines are mixed with no distinction. | `tui_app.py:1100-1103, 1919, 2400`; `14_success_120x40.png` | Keep the cheap rendering, but use short stamps, a level glyph column and soft wrap, and keep a structured outcome separate from the raw log. |
| T9 | 2 | Copyability of output paths | Report paths in Last Run wrap mid-token (`…benchmark_shar` / `e_Target…`). Log paths are truncated at the pane edge. Mouse-mode terminals need shift-drag, which picks up border characters. Export and override toasts show **only the basename** (`export_path.name`, `tmp_path.name`), so the full path isn't shown anywhere. Override temp files are written to the CWD (`dir="."`). | `tui_app.py:1907, 2249, 2570`; `core/preset_workflow.py:31-37`; `14_success_120x40.png` | Put each path on its own unwrapped line and add a "copy path" action (`App.copy_to_clipboard`, which uses OSC 52). Always show the full path. |
| T10 | 2 | Keyboard-only operability | Everything can be reached by Tab, and modals bind Escape. However, a hidden section can only be reached by scrolling or Tab-walking through every field (about 25 Tab stops before the Rate tab). Collapsibles toggle with Enter, but nothing hints at that. Tab order follows the DOM order, including the off-screen Advanced fields once it's expanded. | `21_focus_after_6_tabs_120x40.png` | Add section hotkeys and a visible key hint per section. |
| T11 | 0 | Remote friendliness (positive) | Smooth scroll and animations are off, FPS is capped, the clock is removed, log records are batched, and `batch_update()` is used on bulk changes. | `tui_app.py:23-29, 140-201, 857, 1640` | Keep these constraints as non-functional requirements for the redesign. |
| T12 | 1 | Terminal title | The window title equals the header title. No run state is reflected in the terminal or tab title. | `tui_app.py:850` | Optionally put the run state in the terminal title (useful with tmux). |

---

## 3. CSS and design-token audit

**Inventory** (`BenchmarkApp.CSS` at `tui_app.py:511-847` and `PresetHelpScreen.CSS` at `tui_app.py:318-342`): 2 blocks, 63 rules, 166 declarations.

### Colours
- **Theme variables used (13 distinct forms):** `$primary` ×5, `$primary 40%` ×6, `$primary 50%` ×1, `$surface` ×5, `$text-accent` ×5, `$text-muted` ×4, `$text` ×2, `$warning` ×2, `$warning 60%` ×1, `$accent 60%` ×1, `$error` ×2, `$secondary` ×1, `$boost` ×2.
- **Hard-coded colours in CSS:** `rgba(0,0,0,0.7)` ×4 (modal backdrop, repeated in `PresetHelpScreen`, `ValidationModal`, `CsvPickerScreen` and `ConfirmScreen`).
- **Hard-coded colours outside CSS (Rich markup in Python):** `[dim]` ×34, `[red]` ×16, `[green]` ×7, `[b]` ×7, `[yellow]` ×5, `[cyan]` ×3. These bypass the theme entirely and cause T5.
- **Ad-hoc opacity steps:** 40%, 50%, 60% (three alpha levels with no stated meaning).
- **Semantic misuse:** `.adv-group-title` uses `color: $warning` as a decorative heading colour, the Compliance border uses `$warning 60%`, and Advanced uses `$accent 60%`. Warning colour is spent on non-warnings.

### Spacing and sizing
- `margin-bottom: 1` ×22, `0` ×5. `margin-top: 1` ×7, `0` ×2. `margin-right: 1` ×2, `2` ×2. `margin: 0 0 1 0` ×1.
- Padding variants: `1 2` ×4, `0 1` ×5, `0 2` ×3, `1` ×1 (**4 distinct values**).
- Widths: `58%`, `70%`, `80%`, `84%`, `40%`, `60`, `100%` ×6, `1fr` ×4. Max-widths `100`, `110`, `120`. Min-widths `64`, `42`, `28`, `16`.
- Heights: `80%` ×2, `70%`, `auto` ×12, `1fr` ×6. Magic numbers: `7` (multi-select), `14` (results max), `5` and `8` (min-heights).
- **About 25 distinct ad-hoc literal values** across width, height, padding, margin and min/max.
- **Duplication:** the trio `border: round $primary 40%; border-title-color: $text-accent; border-title-style: bold` repeats 4 times (`.form-section`, `#run_status`, `#results_panel`, `#log_output`). The modal backdrop and centring repeat 4 times. `.input-group Input, .input-group Select` and `.split-inputs …` are identical. Styling is mostly ID-based (about 30 `#id` selectors), so nothing is reusable.
- `Input { margin-bottom: 1 }` and `Select { margin-bottom: 1 }` are global, and they contribute to F22/F26 density and overflow.

### What a design-token layer needs to cover
1. **Semantic colour tokens**, mapped to theme variables and usable from both TCSS and content markup (`[$token]`): `status-ready`, `status-running`, `status-validating`, `status-awaiting`, `status-success`, `status-warning`, `status-blocked`, `status-error`; `surface-0/1/2`; `border-subtle`, `border-strong`, `border-focus`; `text`, `text-muted`, `text-accent`; `backdrop`; `danger`, `primary-action`.
2. **Status glyphs** that don't depend on colour (✓ ✗ ⚠ ⏵ ■ ●, `[x]`/`[ ]`), with an ASCII fallback set.
3. **Spacing scale:** `space-0` = 0, `space-1` = 1, `space-2` = 2. Gutter tokens for panes, sections and fields.
4. **Size tokens:** modal `sm` (~60), `md` (~90), `lg` (~120) cols, with row-based heights. Pane min-widths. A list height. A single layout breakpoint (about 110 cols) for one pane versus two.
5. **Component classes** in place of ID rules: `.panel` (titled border), `.modal`, `.field`, `.field-hint`, `.section-title`, `.button-row`, `.status-line`.
6. **Focus token:** border style and colour plus an inverse treatment, readable in NO_COLOR.
7. **Typography roles:** title, section, label, hint, code/path (no wrap, selectable).

---

## 4. Copy and microcopy audit

### Worst offenders (verbatim)

| Location | Text | Problem |
|---|---|---|
| `tui_app.py:2553` | `Compliance: posture={posture} verdict={…} acknowledgement={…}` | Debug key=value format shown to the user, with raw enums. |
| `tui_app.py:2518-2527` | `Control 3 privacy denial: all benchmark-bearing outputs withheld (control3_numeric_policy_blocked).` | Internal control ID and reason code, no next step, and truncated in the log pane. |
| `tui_app.py:2605` | toast `Control 3 privacy denial: publication withheld.` (title `Publication Withheld`) | Gives no reason and no action. |
| `tui_app.py:2636` | `traceback.format_exc()` written to the user log | Raw Python traceback. |
| `tui_app.py:2637` | Last Run `[red]{exc}[/red]` | For `KeyError` this shows just `'card_type_input_mode'`, and the text isn't escaped. |
| `tui_app.py:425` | `f"[{issue.severity.value}] {issue.message}"` | `[error]` is eaten as markup and never shows. |
| `tui_app.py:1140` | `Ctrl+O browse · Ctrl+R run · Ctrl+A advanced · Ctrl+E export adv · Ctrl+L clear log · F1 preset guide` | Transient (6 s), abbreviated ("export adv"), and lists keys that don't work while a field has focus. |
| `tui_app.py:1788` | `Advanced widget missing: {widget_id}` | Shows an internal widget ID (e.g. `adv_lp_tolerance`). |
| `tui_app.py:2251` | `Failed export: {e}` | Ungrammatical, with a raw exception. |
| `tui_app.py:1913` | `Failed to write overrides: {e}` | Raw exception, no path. |
| `tui_app.py:2458` | `Validation failed. Fix the data and retry.` | Generic, with no pointer to the failing check. |
| `tui_app.py:2470` / `2471` | `Initialization Error: {exc}` / `Initialization error: {exc}` | Casing differs for the same event in the log and the panel. |
| `tui_app.py:2625`, `2630` | `Execution Blocked: {exc}` / `Execution Error: {exc}` | Title Case prefixes; the toast says "Failed". |
| `tui_app.py:2312` | `WARNING: best_effort posture may complete with labeled non-compliant outputs.` | Only in the log, with a raw enum. Users should see this before they run, not after. |
| `tui_app.py:1473-1477` | `This preset uses the accuracy_first compliance posture: … NON-PUBLISHABLE diagnostic report.` / button `I understand — proceed` | Raw enum, and the default-focused button is red (F11). |
| `tui_app.py:307-309` | `Fraud analysis requires Total column \`{total_col}\` to contain clearing-spend amounts. Continue?` / button `Confirm` | Markdown backticks render literally in a Label. "Confirm" is vague for an attestation; it should name the act, e.g. "Yes, it is clearing spend". |
| `tui_app.py:937` | `Anonymized aggregated merchant-spend context (enables 4/35)` | Opaque, since "4/35" is unexplained, and it reads like an attestation but sits among options. |
| `tui_app.py:932` | `Privacy rule sweep mode` | Mechanism name with no explanation. When Verified safe coverage is selected, the checkbox is silently locked on. |
| `tui_app.py:899`, `903`, `1081` | `Analyze impact` · `Include calc. metrics (CSV)` · `Fraud in BPS` | Vague, abbreviated and jargon. |
| `tui_app.py:879` | `Target entity (blank = peer-only)` | Truncated at 120 cols, and the parenthetical works as an instruction. |
| `tui_app.py:851` | `Control 3.2 dimensional analysis` | Internal control number as the subtitle. |
| `tui_app.py:925-927` | `Verified safe coverage publishes only verified safe units. Missing units are privacy-suppressed. Coverage is not a maximum claim.` | "Coverage is not a maximum claim" is legalistic and unclear to operators. |
| `tui_app.py:2224` | `Expanding advanced section to ensure values are current` (title `Export Adv`) | Narrates implementation details. |
| `tui_app.py:1034` | `Values override preset when applied.` | Doesn't say that overrides persist for later runs or how to clear them. |
| `tui_app.py:2267` | `Starting analysis sequence...` | ASCII ellipsis while other copy uses "…"; "sequence" adds nothing. |

### Copy patterns to fix in the redesign
- One voice: sentence case, verbs on buttons ("Run analysis", "Cancel run", "Yes, it's clearing spend"), no Title Case log prefixes.
- Never show enums or reason codes as primary text. Map them through a shared `core/` label table, which the CLI can use as well.
- Every error message should state **what happened, why, and what to do next**, plus the full diagnostic-log path (with a copy action).
- Escape every dynamic string that goes into markup.

---

## 5. Screenshots (scratch only — NOT committed)

Directory (SVG): `/tmp/claude-0/-home-user-autobench/d13cb994-08e3-5f72-b4d1-86adf775fd7d/scratchpad/heuristics/shots/`
Directory (PNG): `/tmp/claude-0/-home-user-autobench/d13cb994-08e3-5f72-b4d1-86adf775fd7d/scratchpad/heuristics/png/`
Capture script: `/tmp/claude-0/-home-user-autobench/d13cb994-08e3-5f72-b4d1-86adf775fd7d/scratchpad/heuristics/capture.py` (`--only`, `--sizes`, `--theme`, `--suffix`). PNG converter: `…/heuristics/topng.js`. CSS audit: `…/heuristics/css_audit.py`.

Each name below exists as `<name>_120x40` and `<name>_80x24`, in both `.svg` (in `shots/`) and `.png` (in `png/`):

| Name | State |
|---|---|
| `01_launch` | initial launch |
| `02_loaded_top` | after loading `autobench_demo.csv` |
| `03_share_tab` / `04_rate_tab` | Analysis Mode tabs |
| `05_advanced_expanded` | **ctrl+a pressed with Input focused — section stays collapsed** |
| `05b_advanced_expanded_direct` / `05c_advanced_bottom` | Advanced expanded programmatically |
| `06_compliance_expanded` | Compliance Declarations open |
| `07_modal_csv_picker` | CSV picker |
| `08_modal_confirm_accuracy_first` | accuracy_first consent confirm |
| `09_modal_clearing_spend` | clearing-spend confirm (real flow via Run) |
| `10_modal_preset_help` | Preset Guide |
| `11_modal_validation` | Validation modal, 1 error and 2 warnings (only 1 visible) |
| `12_running` / `13_modal_quit_while_running` | running state / quit confirm |
| `14_success` | success |
| `15_blocked_privacy_denial` | hard privacy block (withheld) |
| `16_blocked_runblocked` | `RunBlocked` |
| `17_error_runaborted` | `RunAborted` |
| `18_error_unexpected_exception` | unhandled exception (traceback) |
| `19_preflight_error_no_dims` | preflight refusal |
| `20_bad_csv_path` | non-existent CSV path |
| `21_focus_after_6_tabs` | keyboard focus walk |

Colour variants (120x40 only), with suffix `_nocolor` (NO_COLOR=1) and `_ansi` (`textual-ansi` theme): `01_launch`, `02_loaded_top`, `03_share_tab`, `04_rate_tab`, `11_modal_validation`, `14_success`, `15_blocked_privacy_denial`, `17_error_runaborted`.

Most informative:
- `/tmp/claude-0/-home-user-autobench/d13cb994-08e3-5f72-b4d1-86adf775fd7d/scratchpad/heuristics/png/11_modal_validation_120x40.png`
- `/tmp/claude-0/-home-user-autobench/d13cb994-08e3-5f72-b4d1-86adf775fd7d/scratchpad/heuristics/png/01_launch_80x24.png`
- `/tmp/claude-0/-home-user-autobench/d13cb994-08e3-5f72-b4d1-86adf775fd7d/scratchpad/heuristics/png/15_blocked_privacy_denial_120x40_nocolor.png`
- `/tmp/claude-0/-home-user-autobench/d13cb994-08e3-5f72-b4d1-86adf775fd7d/scratchpad/heuristics/png/19_preflight_error_no_dims_80x24.png`
