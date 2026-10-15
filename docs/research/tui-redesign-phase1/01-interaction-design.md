# TUI Redesign Phase 1: 01 Interaction Design

Phase 1 is a design spec. No repo code changes. It builds on the Phase 0
evidence in [`../tui-redesign-phase0/`](../tui-redesign-phase0/00-summary.md).
Colour tokens, glyph sets, copy style and the token layer are in
`02-visual-system.md`. Mounting, worker and latency budgets are in
`03-performance-architecture.md`. This document covers structure, flow, keys,
states and the compliance interaction rules.

**Evidence base for this spec.** A throwaway Textual 7.5 prototype (stock
widgets plus three small custom ones) rendered every state below at 80x24 and
120x40, and a Pilot script drove it to measure the projected keystroke paths.
Two probes checked how cancel and quit behave. None of these files are in the
repo:

| Artefact | Path (scratchpad) |
|---|---|
| Prototype app | `…/scratchpad/phase1/proto/proto_app.py` |
| Screenshot capture (23 states × 2 sizes) | `…/scratchpad/phase1/proto/capture.py` → `shots/*.svg`, `png/*.png` |
| NO_COLOR captures | `…/scratchpad/phase1/proto/capture_nocolor.py` → `png_nocolor/*.png` |
| Keystroke measurement (Pilot, asserts every step) | `…/scratchpad/phase1/proto/measure_proto.py` → `keystrokes.json` |
| Wireframe generator (checks every frame is exactly 80x24 or 120x40) | `…/scratchpad/phase1/frames.py` |
| Thread-worker cancel/exit probe | `…/scratchpad/phase1/exit_probe.py` |
| Quit-during-attestation probe (real `tui_app.py`) | `…/scratchpad/phase1/quitprobe/quit_probe.py` |

`…` is `/tmp/claude-0/-home-user-autobench/d13cb994-08e3-5f72-b4d1-86adf775fd7d`.

## Decision summary

- **Model: a non-gated step rail on one main screen**, with a status/results
  column at 110 columns and wider, which becomes a toggled view (`^T`) below 110.
  The steps are Data, Entity, Analysis & mode, Privacy & compliance, and
  Review & run. There is no Next button and no gating: Tab flows from one step
  into the next, F2–F6 jump straight to a step, and `^R` runs from anywhere.
  A one-row action bar always shows readiness and the Run key.
- **What changed from the working hypothesis**, based on the prototype:
  1. The rail is a **single horizontal row at every width**. A vertical rail at
     120x40 took 30 columns, repeated the status column's summary, and squeezed
     the form to 58 columns, so Review lines wrapped. That was the first
     prototype iteration; its screenshots were overwritten by the final ones.
  2. The breakpoint is **110 columns, not 100**. The status column needs 42
     columns for a readable verdict and a path wrapped at `/ _` boundaries, and the form
     needs at least 66 for label + field + hint. 100 − 42 = 58 is too narrow.
  3. **The Review step is optional.** `^R` from any step runs when the form is
     ready. Review exists to check things, not as a gate.
  4. **Attestations move after validation**, so consent is never asked for a
     run that data validation would stop anyway (02 friction #8).
- **Rejected alternatives.** A strict wizard adds a Next press per step, and
  re-runs (J3b) would walk the whole sequence. A single long page fits 120x40
  but not 80x24, the size where Phase 0 found the worst problems (02 friction
  #1). It also brings back nested scroll traps (03 T7). One mental model at
  both sizes was worth more than the extra visibility at 120x40.

---

## 1. Design principles

| # | Principle | Phase 0 evidence | What it forces |
|---|---|---|---|
| P1 | **Run is one key from anywhere, and it says what it will run.** | Run sits at row 110, off-screen at both sizes (01 E.20). The label lags the sweep box (01 E.8). | A persistent action bar with `^R Run share analysis` / `… privacy sweep`. When the form is not ready, `^R` jumps to the first blocker. |
| P2 | **Every-run fields come first. Sometimes-fields sit behind one disclosure. Expert fields get their own screen. Compliance fields are never in any of those tiers.** | 59 widgets, 27 at launch. 19 Advanced inputs are mixed into the form. Mode is Tab stop 17 of 28 (02). Declarations are collapsed and split up (01 E.12). | IA in §2. Every privacy and compliance field is visible in step 4 and repeated in Review. |
| P3 | **If it can't be read at 80x24, it doesn't ship.** | Activity pane shows 15 of 40 columns. Verdict and report path can't be read (02 friction #1, 03 T1). | Below 110 columns there is one column. Status and results become a full-width view. The report path is always shown whole in the action bar. |
| P4 | **Keys work whatever has focus, avoid multiplexer prefixes, and appear on screen.** | `^A`/`^E` are dead inside an `Input` and clash with screen/tmux. The keys are only listed in a 6 s toast. Type-ahead exists but is never mentioned (01 #1, 03 T2/F21). | §4. Global bindings use `priority=True` with keys no stock widget binds. The footer changes with context and shows `a-z Jump` on lists. |
| P5 | **Attestations take a deliberate action, apply to one run, and are never pre-filled.** | Confirm has initial focus, so one Enter attests (D3, 03 F11). Overrides skip consent (D2). Attestations are already never restored (01 A.4). | Dialogs open on Cancel. The affirmative button names the act. Consent follows the *effective* posture. Asked after validation, on every attempt. |
| P6 | **Status is label + symbol + colour. Internal codes are secondary.** | Under NO_COLOR, "Blocked" and "withheld" vanish (03 T5). Checked and unchecked look the same (T4). Raw `fully_compliant`, `posture=strict` (F06). | Every state has a word and a glyph (`✓ DONE`, `✗ WITHHELD`, `! NOT READY`). Codes appear on a dimmed second line. Glyph pairs `[x]`/`[ ]`. |
| P7 | **Say what the run is doing and what cancel can actually do.** | No progress, no cancel, raw tracebacks (03 F01/F09/F28). A probe shows `Worker.cancel()` does not stop a thread worker (§7). | Four visible stages. Cancel works before the engine starts and is labelled unavailable after. Results say where every file went. |

---

## 2. Information architecture

### 2.1 Steps

| Step | Purpose | Required to run | Rail glyph rules |
|---|---|---|---|
| 1 Data | Choose and load the CSV | a loaded file | `!` no file or load error · `✓` loaded |
| 2 Entity | Entity column and target (or peer-only) | nothing beyond a loaded file (blank target = peer-only, as today) | `○` before load · `✓` |
| 3 Analysis & mode | Share or Rate, the metric/rate columns, dimensions; disclosure for sometimes-fields; link to Expert | share: metric + (dims or auto) · rate: total + (approved or fraud) + (dims or auto) | `!` a required field is missing · `↺` holds restored values · `✓` |
| 4 Privacy & compliance | Preset and its effective posture, release mode, rule strategy, run declarations | Citibank entity when the Citi box is ticked (new live pre-check of a rule core already enforces) | `!` blocker · `⚠` non-strict posture, or a declaration is ticked · `✓` strict, nothing declared |
| 5 Review & run | Read-only summary, list of blockers, Run button, Clear restored values | — | `!` N things to fix · `✓` ready |

The current step is drawn in reverse video with a `▸` prefix, so it is visible
under NO_COLOR. The rail is not focusable: no dead Tab stops (02 friction #11).

### 2.2 Field placement

Tiers: **E** = shown in the step body · **M** = "More options" disclosure in
step 3 (collapsed by default, with a summary line such as `all default` or
`2 changed`) · **X** = Expert settings screen · **PC** = privacy or
compliance-critical: shown in the step body and in Review, never in M or X.
Ids in this table are today's ids. Where controls merge, the new single
control takes over both session keys (§8).

| Today (01 inventory) | New place | Tier | Notes |
|---|---|---|---|
| `btn_browse_csv` | Step 1 `[Browse ^O]` | E | Comes before the path field in Tab order. Reachable with Shift+Tab from the path, or with `^O`. |
| `csv_path` | Step 1 | E | Initial focus. Suggester over the quick-pick list (→ accepts). Loads on Enter, on a picker choice, or on blur only when the text changed and names an existing file. An unchanged path is never reloaded. This removes the Tab-out reload (02 friction #14, 04 #2). |
| `csv_meta` | Step 1 | — | `✓ name · N columns · K numeric · size`, plus the column list with `#` on numeric columns. Errors appear inline here, not as a toast. |
| `entity_col` | Step 2 | E | Smart default `issuer_name`, as today. Options: non-numeric columns. |
| `entity_name` | Step 2 | E | Select with type-ahead up to 2,000 values. Above that, a filter Input + capped OptionList (200 rows), per 00-summary. Blank = peer-only, and the rail and Review say "peer-only". Never restored. |
| `ContentTabs` (Share/Rate) | Step 3 `Mode` | E | One focus stop, ←→ switch at once. First field of step 3. Now restored from the session (§8). |
| `share_metric` | Step 3 | E | Numeric columns only. Smart default `txn_cnt`, as today. |
| `rate_total` | Step 3 | E | Numeric columns. **No smart default** (open question Q4). The hint says it must be the governed clearing-spend column when fraud is used. |
| `rate_approved` | Step 3 | E | Numeric. Smart default `app_cnt`, as today. |
| `rate_fraud` | Step 3 | E, PC | Numeric. Picking it shows the hint that the clearing-spend attestation will be asked. |
| `share_dims` + `rate_dims` | Step 3 `Dimensions` | E | **Merged into one list.** Columns already assigned to a role (entity, time, metric, total, approved, fraud) are hidden. Numeric columns are marked `#`. Typing a letter moves to the next matching column. |
| `share_auto_dim` + `rate_auto_dim` | Step 3, under the list | E | Merged. When on, the list collapses to one line `Auto-detect: on`. |
| `share_secondary` + `rate_secondary` | M `Secondary metrics` | M | Merged. Numeric columns not assigned to a role. |
| `time_col` | M | M | Optional, as the label says today. |
| `output_format` | M | M | Analysis / Publication / Both. |
| `output_file` | M | M | Placeholder shows the auto name pattern. Review shows the resolved full path (03 F20). |
| `validate_input` | M | M | Default on. When off, Review shows `⚠ Input check off` and the rail marks step 3 `⚠`. |
| `analyze_distortion` | M `Analyze impact (distortion summary)` | M | |
| `compare_presets` | M `Compare all presets (slower)` | M | |
| `share_export_csv` + `rate_export_csv` | M `Export balanced CSV (written only if privacy allows)` | M | Merged. Keeps today's per-mode default (share on, rate off) until Q5 is answered. |
| `include_calculated` | M, nested under Export balanced CSV | M | Disabled unless export is on (01 E.11). |
| `fraud_in_bps` | M, nested under Output format | M | Enabled only in rate mode, with a fraud column, and with format Publication or Both. Otherwise it shows `(disabled here)` and the reason (01 E.11). |
| `preset_select` | Step 4 `Preset` | E, PC | First field of step 4. Changing it while expert changes exist opens the reset dialog (§8.2). |
| `preset_blurb` + posture lookup | Step 4 `Posture` line | PC | Read-only, for example `✓ Strict — only publishable output is written · from preset`. Comes from the **effective** config (§8.2). |
| `btn_preset_help` | Removed as a button | — | Replaced by F1 Help → Presets tab, a palette entry, and the posture line hint `F1 explains every preset`. Removes a duplicate stop (02 friction #11). |
| `privacy_release_mode` (+ label, hint) | Step 4 `Release mode` | PC | Share only. In rate mode the row reads `not used for rate analysis`. The hint describes the selected mode only (01 E.7). Restored as today, with a visible `↺`. |
| `privacy_rule_sweep_mode` | Step 4 `Rule strategy` | PC | Locked on, with the reason shown, while Verified safe coverage is selected in share mode. In rate mode it is unlocked and shows exactly the value that will be sent (01 E.6, Q6). |
| `privacy_merchant_spend_scope` | Step 4 Declarations box | PC | Never restored. Full label, no clipping (02 friction #10). |
| `citi_competitor_receives_output` | Step 4 Declarations box | PC | Never restored. |
| `citibank_entity_name` | Step 4 Declarations box | PC | **A Select over the loaded entity values**, not free text (01 E.13). Required when the box above is ticked, as a live readiness blocker. Disabled, but visible, otherwise. Never restored. |
| The other 17 `adv_*` fields | Expert settings screen | X | Grouped as today. Labels say which value they are ("LP max iterations" vs "Bayesian max iterations", 01 E.9). `adv_subset_strategy` becomes a Select (01 E.17). Blank means "inherit the preset" and the source column says `preset` / `engine default` / `● changed` (01 E.16). |
| `adv_output_debug_sheets` + `share_debug` + `rate_debug` | Expert → Output sheets `Debug sheets` | X | **One control** (D5, 01 E.1). It sends the `debug` request field as today, so CLI-override precedence is unchanged. |
| `adv_output_privacy_validation` | Expert → Output sheets | X | Shown as `(always included while debug sheets are on)` and enabled only when debug is off (01 E.2). |
| `btn_apply_advanced` | Removed | — | Expert edits are an in-memory diff. They apply at Run and are written to an override file only then (§8.2). |
| `btn_export_advanced` | Expert `[Export to file…]` and a palette entry | X | Shows the full written path (03 T9). |
| `compliance_posture` (no widget today) | Step 4 Posture line (read-only) | PC | |
| `acknowledge_accuracy_first` | Consent dialog only | PC | Per run, never persisted. |
| `btn_run` | Action bar `^R Run …` + Review button | E | |
| `run_status`, `results_panel` | Status/results column (≥110) or view (`^T`, <110) + action bar | — | One status component (03 F02). |
| `log_output` | Run log screen (from Results `Show run log`) | — | Not in the main Tab chain. No destructive `^L`. Earlier runs this session stay listed. |
| Header | Removed | — | Gains a row. The terminal title carries the app and run state (03 T12). |
| `log_level`, `per_dimension_weights`, `lean`, `audit_package`, `validate_export`, `report_format` | Not exposed | — | Unchanged from today (01 A.8). |

**Field counts.** Main-screen interactive widgets drop from 59 to 35:

| Where | Interactive widgets |
|---|---:|
| Step 1 | 2 |
| Step 2 | 2 |
| Step 3, including 11 in More options | 19 |
| Step 4 | 6 |
| Review | 2 |
| Results | 4 |

The 19 expert fields leave the main screen. Five share/rate pairs merge.
The Apply, Export and Preset Guide buttons go. At first launch there are 2
focus stops.

---

## 3. Layout and wireframes

### 3.1 Regions

| Region | Rows / columns | Content |
|---|---|---|
| Step rail | row 1, full width | `glyph number label`, current step reversed. At ≥110 each step also shows its F-key. |
| Step body | rows 2…H−2 | One step at a time (`ContentSwitcher`). Scrolls inside the step body only, never nested lists in a scroll, and lists cap at 8 rows (03 T7). |
| Status/results | ≥110: right column 42 wide. <110: a full-width view toggled by `^T`, which replaces the step body | Idle: readiness and a frozen run summary. Running: stages. After a run: outcome card. |
| Action bar | row H−1, full width | Left: `glyph STATE message`. Right: the run key label, or `^G Cancel run` / `Cancel unavailable` while running. After a successful run, the full report path. |
| Footer | row H | Context keys (§4.4) |

Breakpoints: `HORIZONTAL_BREAKPOINTS = [(0, "-narrow"), (110, "-wide")]`
(stock in Textual 7.5). At 120x40 the form column is 78 columns wide, the same
as the 80x24 form. **So every 80x24 step wireframe below is also the
120x40 form column, verbatim.** The 120x40 frames in §3.4 show the full screen
and the right column per state.

Modal sizes are fixed in columns and capped at 96%, so they keep the same
layout at both sizes: dialogs 64 columns, validation 68, picker and help 78,
centred. Toasts never cover a modal (§5.3).

### 3.2 Steps at 80x24 (also the 120x40 form column)

Step 1 Data at launch. Focus is on the path (`▏`).

```text
▸!1 Data  ○2 Entity  ○3 Analysis  ○4 Privacy  !5 Review
1 · Data — which file?

 [Browse ^O] ▏path/to/data.csv  (relative to the launch folder)
             No file loaded. Type a path and press Enter, or press ^O.
             → accepts the grey suggestion (from ., data/, tests/fixtures/)

 Launch folder  /home/analyst/work
                Relative paths and reports are resolved from here.













! NOT READY  Open a CSV file                               ^R Run share analysis
^R Run  ^O Open CSV  F2-6 Steps  ^T Status  F1 Help  ^Q Quit      ^P Commands
```

Step 1 after a load (what you see if you return to it), with the inline error variant:

```text
▸✓1 Data  ✓2 Entity  ✓3 Analysis  ✓4 Privacy  ✓5 Review
1 · Data — which file?

 [Browse ^O]  data/autobench_demo.csv
             ✓ autobench_demo.csv · 9 columns · 4 numeric (#) · 2.1 KB
               issuer_name · year_month · card_type · input_mode ·
               card_type_input_mode · txn_cnt# · total# · approved# · fraud#

 Launch folder  /home/analyst/work
                Relative paths and reports are resolved from here.

 Error variant (inline, focus stays in the field, no toast):
             ✗ Not found: data/autobnch.csv
               Check the spelling, or press ^O to browse.








✓ READY  share analysis · Target                           ^R Run share analysis
^R Run  ^O Open CSV  F2-6 Steps  ^T Status  F1 Help  ^Q Quit      ^P Commands
```

Step 2 Entity, with the large-list variant:

```text
 ✓1 Data ▸✓2 Entity  !3 Analysis  ✓4 Privacy  !5 Review
2 · Entity — who is benchmarked?

 Entity column    issuer_name                                            ▾
 Target entity   ▏Target                                                 ▾
                  ↑↓ or type letters to jump · blank = peer-only benchmark
                  Chosen fresh every run. Never restored from a session.

 7 entities in issuer_name.

 Large-list variant (> 2,000 values): a filter field, not a dropdown
 Target entity   ▏ent_04█                                    5,000 values
                  › ENT_04_0001
                    ENT_04_0002
                    ENT_04_0003               112 matches · first 8 shown







! NOT READY  Choose dimensions (step 3)                    ^R Run share analysis
↵ Open  a-z Jump  ^R Run  F2-6 Steps  ^T Status  F1 Help  ^Q Quit   ^P Commands
```

Step 3 Analysis & mode, share. `›` is the list cursor and `▏` the focused widget.

```text
 ✓1 Data  ✓2 Entity ▸✓3 Analysis & mode  ✓4 Privacy  ✓5 Review
3 · Analysis & mode

 Mode             (●) Share  ( ) Rate                     ←→ to switch
 Metric           txn_cnt                                                ▾
 Dimensions       ␣ toggles · a-z jumps · columns used elsewhere are hidden
                ▏[ ] year_month
                  [x] card_type
                › [x] input_mode
                  [ ] card_type_input_mode
                  [ ] total #          (# = numeric column)
                  [ ] approved #
                  [ ] fraud #
                  [ ] Auto-detect dimensions instead
 ▸ More options   time column · secondary metrics · outputs     all default
 [Expert settings… F8]   optimizer tuning · 0 changed from preset






✓ READY  share analysis · Target · 2 dims                  ^R Run share analysis
␣ Toggle  a-z Jump  ^R Run  F2-6 Steps  ^T Status  F1 Help  ^Q Quit  ^P Commands
```

Step 3, rate:

```text
 ✓1 Data  ✓2 Entity ▸!3 Analysis & mode  ✓4 Privacy  !5 Review
3 · Analysis & mode

 Mode             ( ) Share  (●) Rate                     ←→ to switch
 Total (denom.)  ▏total                                                  ▾
                  No default: pick the governed clearing-spend column.
 Approved column  approved                                               ▾
 Fraud column     fraud                                                  ▾
                  Approved or fraud is required. Fraud asks you to confirm
                  that Total is clearing spend on every run.
 Dimensions       ␣ toggles · a-z jumps · columns used elsewhere are hidden
                  [ ] year_month
                  [ ] card_type
                  [ ] input_mode
                  [ ] card_type_input_mode
                  [ ] txn_cnt #
                  [ ] Auto-detect dimensions instead
 ▸ More options   time column · secondary metrics · outputs     all default
 [Expert settings… F8]   optimizer tuning · 0 changed from preset



! NOT READY  Choose dimensions or Auto-detect               ^R Run rate analysis
↵ Open  a-z Jump  ^R Run  F2-6 Steps  ^T Status  F1 Help  ^Q Quit   ^P Commands
```

Step 3 with More options open (the step body scrolls; the rail and action bar stay put):

```text
 ✓1 Data  ✓2 Entity ▸✓3 Analysis & mode  ✓4 Privacy  ✓5 Review
3 · Analysis & mode                                        (scrolled ▲ 9 rows)
 ▾ More options   time column · secondary metrics · outputs     2 changed
   Time column        year_month                                         ▾
   Secondary metrics  [ ] total #   [ ] approved #   [ ] fraud #
   Output format      Analysis workbook                                  ▾
   Output file       ▏auto: benchmark_share_Target_<time>.xlsx
                      → launch folder (full path in Review)
   [x] Validate input before running (recommended)
   [x] Analyze impact (distortion summary)
   [ ] Compare all presets (slower: runs every preset)
   [x] Export balanced CSV (written only if privacy allows)
       [ ] include calculated metrics in the CSV
   Rate + fraud + publication only:
       [x] Fraud in basis points (publication workbook)   (disabled here)
 [Expert settings… F8]   optimizer tuning · 0 changed from preset






✓ READY  share analysis · Target · 2 dims                  ^R Run share analysis
^R Run  ^O Open CSV  F2-6 Steps  ^T Status  F1 Help  ^Q Quit      ^P Commands
```

Step 4 Privacy & compliance (strict preset, Citi declared, Citibank entity missing):

```text
 ✓1 Data  ✓2 Entity  ✓3 Analysis ▸!4 Privacy & compliance  !5 Review
4 · Privacy & compliance

 Preset          ▏compliance_strict                                      ▾
 Posture          ✓ Strict — only publishable output is written
                  from preset · F1 explains every preset
 Release mode     Complete output                                        ▾
                  Writes every output the privacy rules allow.
 Rule strategy    [ ] Sweep every applicable privacy rule
╭─ Declarations ─ check before every run · never saved between sessions ───╮
│ [ ] Data is anonymized, aggregated merchant spend (enables rule 4/35)    │
│ [x] A Citi competitor will receive this output (adds the 25% Citi cap)   │
│     Citibank entity  pick from the entity values                       ▾ │
│     ! Required: choose the exact Citibank value                          │
╰──────────────────────────────────────────────────────────────────────────╯







! NOT READY  Pick the exact Citibank entity                ^R Run share analysis
^R Run  ^O Open CSV  F2-6 Steps  ^T Status  F1 Help  ^Q Quit      ^P Commands
```

Step 4 with an accuracy_first preset, Verified safe coverage restored from the session, and the rate-mode variant:

```text
 ✓1 Data  ✓2 Entity  ✓3 Analysis ▸⚠4 Privacy & compliance  ✓5 Review
4 · Privacy & compliance

 Preset           low_distortion                                         ▾
 Posture          ⚠ Accuracy first — asks for consent on every run;
                    output may be a NON-PUBLISHABLE diagnostic
                  from preset · F1 explains every preset
 Release mode    ▏Verified safe coverage                                 ▾
                  Publishes only units verified safe; the rest is
                  suppressed. Rule sweep is forced on.  ↺ restored
 Rule strategy    [x] Sweep every applicable privacy rule  (locked by
                      Verified safe coverage)
╭─ Declarations ─ check before every run · never saved between sessions ───╮
│ [ ] Data is anonymized, aggregated merchant spend (enables rule 4/35)    │
│ [ ] A Citi competitor will receive this output (adds the 25% Citi cap)   │
│     Citibank entity  (only needed when the box above is ticked)          │
╰──────────────────────────────────────────────────────────────────────────╯
 Rate mode shows instead:  Release mode   not used for rate analysis




✓ READY  share privacy sweep · consent asked at run           ^R Run share sweep
↵ Open  a-z Jump  ^R Run  F2-6 Steps  ^T Status  F1 Help  ^Q Quit   ^P Commands
```

Step 5 Review & run, ready, with restored values:

```text
 ✓1 Data  ✓2 Entity  ↺3 Analysis  ✓4 Privacy ▸✓5 Review & run
5 · Review & run

 ✓ Ready to run share analysis

 Data      autobench_demo.csv · 9 columns  (/home/analyst/work/data/)
 Entity    issuer_name → Target
 Analysis  Share · metric txn_cnt · dims card_type, input_mode   ↺
 Privacy   compliance_strict · ✓ Strict · Complete output · sweep off
 Declared  merchant spend: No · Citi competitor: No
 Checks    input validation on · impact on · preset comparison off
 Output    Analysis workbook → ./benchmark_share_Target_<time>.xlsx
 Expert    0 changes from preset
 ↺ Restored from last session: mode, metric, dims, preset

 [Run share analysis ^R]   [Clear restored values]






✓ READY  share analysis · Target · 2 dims                  ^R Run share analysis
^R Run  ^O Open CSV  F2-6 Steps  ^T Status  F1 Help  ^Q Quit      ^P Commands
```

Step 5, blocked. Each blocker is a button that jumps to its field.

```text
 ✓1 Data  ✓2 Entity  !3 Analysis  !4 Privacy ▸!5 Review & run
5 · Review & run

 ! 3 things to fix before this rate analysis can run
   ! Choose the Total column                         step 3 · F4
   ! Choose dimensions or Auto-detect                step 3 · F4
   ! Pick the exact Citibank entity                  step 4 · F5
   Each line is a button: ↵ jumps to the field.

 Data      autobench_demo.csv · 9 columns
 Entity    issuer_name → Target
 Analysis  Rate · total ? · approved approved · fraud –
 Privacy   compliance_strict · ✓ Strict · sweep off
 Declared  merchant spend: No · Citi competitor: Yes (entity missing)

 [Run rate analysis ^R]  (jumps to the first item while not ready)






! NOT READY  Choose the Total column (+2 more)              ^R Run rate analysis
^R Run  ^O Open CSV  F2-6 Steps  ^T Status  F1 Help  ^Q Quit      ^P Commands
```

Expert settings (a full screen pushed over the main screen, Esc returns):

```text
Expert settings · preset compliance_strict · 1 changed · posture stays Strict
Applies to runs in this session. Changing the preset resets these. Esc = done
 [Reset all to preset]  [Export to file…]
 Linear programming
   Tolerance (pp)              ▏0.0          preset
   LP max iterations            1000         preset
   Lambda penalty               ·            engine default
   Volume weighting exponent    ·            engine default
   Volume-weighted penalties    [ ] off      engine default
 Constraints and bounds
   Volume preservation (0–1)    0.85         ● changed · preset 0.9
   Min weight                   0.5          preset
   Max weight                   2.0          preset
 Subset search
   Enabled                      [x] on       preset
   Strategy                     greedy     ▾ preset
   Max attempts                 50           preset
   …  ↓ 9 more: slack, Bayesian fallback, analysis, output sheets

 Empty field = inherit the preset value. ● marks a change.



Esc Done  Tab Next  ↵ Edit  F1 Help                                ^P Commands
```

### 3.3 Status and results view at 80x24 (`^T`, or automatic on run start and finish)

Running, before the engine starts (cancel available):

```text
 ✓1 Data  ✓2 Entity  ✓3 Analysis  ✓4 Privacy ▸✓5 Review & run
Status · run 1 of this session                     ^T back to setup (locked)

 ⏵ RUNNING  rate analysis · low_distortion · Target

   ✓ 1 Check inputs                              0.0 s
   ⏵ 2 Load and validate data                    00:03
   ○ 3 Confirmations                             consent, clearing spend
   ○ 4 Engine: optimise, check privacy, write

 Nothing has been written yet. ^G cancels safely.

 [Show run log]









⏵ RUNNING  2/4 Loading and validating data                         ^G Cancel run
^G Cancel run  ^T Setup  F1 Help  ^Q Quit                          ^P Commands
```

Running, engine stage (cancel unavailable, §7.2):

```text
 ✓1 Data  ✓2 Entity  ✓3 Analysis  ✓4 Privacy ▸✓5 Review & run
Status · run 2 of this session                     ^T back to setup (locked)

 ⏵ RUNNING  share analysis · compliance_strict · Target

   ✓ 1 Check inputs                              0.0 s
   ✓ 2 Load and validate data                    0.4 s
   – 3 Confirmations                             none needed
   ⏵ 4 Engine: optimise, check privacy, write    00:12

   Last engine message
   Built privacy validation data: 42 validation entries

 Setup is locked: this run uses the values shown in Review.
 Cancel is not available once the engine has started: the engine cannot
 stop safely mid-run. ^Q offers to quit when the run finishes.

 [Show run log]




⏵ RUNNING  4/4 Engine · 00:12                                 Cancel unavailable
^T Setup  F1 Help  ^Q Quit                                         ^P Commands
```

Success. The full report path is the focused, selectable line, and the action bar repeats the filename.

```text
 ✓1 Data  ✓2 Entity  ✓3 Analysis  ✓4 Privacy ▸✓5 Review & run
Result · run 1 of this session                             ^T back to setup

 ✓ DONE — Fully compliant
   Share · compliance_strict · Target · 4.2 s
   verdict fully_compliant · posture strict

 Report
 ▏/home/analyst/work/benchmark_share_Target_20261014_101530.xlsx

 Balanced CSV
   …/work/benchmark_share_Target_20261014_101530_balanced.csv
 Log
   …/outputs/logs/benchmark_log_20261014_101530.txt

 [Copy report path ^Y]  [Run again ^R]  [Show run log]  [Earlier runs (0)]






✓ DONE  Fully compliant · benchmark_share_Target_20261014_101530.xlsx         ^Y
^Y Copy path  ^R Run again  ^T Setup  F2-6 Steps  F1 Help  ^Q Quit  ^P Commands
```

Withheld by privacy rules (blocked):

```text
 ✓1 Data  ✓2 Entity  ✓3 Analysis  ✓4 Privacy ▸✓5 Review & run
Result · run 1 of this session                             ^T back to setup

 ✗ WITHHELD — privacy rules blocked publication
   Share · compliance_strict · Target · 3.9 s
   reason control3_numeric_policy_blocked · verdict violations_detected

 No benchmark output was written.

 Try next
   • fewer or coarser dimensions (step 3 · F4)
   • Verified safe coverage or rule sweep (step 4 · F5)
   • a different preset; F1 compares them

 Non-publishable run log — do not share
   /home/analyst/.autobench/quarantine/benchmark_log_20261014_101530.txt

 [Show details]  [Run again ^R]  [Copy log path ^Y]




✗ WITHHELD  privacy rules blocked publication              ^R Run share analysis
^Y Copy path  ^R Run again  ^T Setup  F2-6 Steps  F1 Help  ^Q Quit  ^P Commands
```

Unexpected error. The traceback stays in the log file (03 F28).

```text
 ✓1 Data  ✓2 Entity  ✓3 Analysis  ✓4 Privacy ▸✓5 Review & run
Result · run 1 of this session                             ^T back to setup

 ✗ FAILED — the run stopped with an unexpected error
   Share · compliance_strict · Target · 1.1 s
   KeyError 'card_type_input_mode' · phase analysis

 No report was written.

 Try next
   • check that the chosen dimension columns exist in this file
   • run again; if it repeats, send the diagnostic log to support

 Diagnostic log (the traceback is in this file, not on screen)
   /home/analyst/work/outputs/logs/benchmark_log_20261014_101530.txt

 [Copy log path ^Y]  [Run again ^R]  [Show run log]





✗ FAILED  unexpected error · see Status (^T)               ^R Run share analysis
^Y Copy path  ^R Run again  ^T Setup  F2-6 Steps  F1 Help  ^Q Quit  ^P Commands
```

Cancelled:

```text
 ✓1 Data  ✓2 Entity  ✓3 Analysis  ✓4 Privacy ▸✓5 Review & run
Result · run 3 of this session                             ^T back to setup

 ■ CANCELLED — stopped before the engine started
   Rate · low_distortion · Target · at stage 3 Confirmations

 Nothing was written. Consent and attestations were not recorded.

 [Run again ^R]  [Show run log]













■ CANCELLED  nothing was written                            ^R Run rate analysis
^Y Copy path  ^R Run again  ^T Setup  F2-6 Steps  F1 Help  ^Q Quit  ^P Commands
```

### 3.4 Full screen at 120x40

Idle on step 3, with the status column showing readiness and the run summary:

```text
 ✓1 Data F2   ✓2 Entity F3  ▸✓3 Analysis & mode F4   ✓4 Privacy & compliance F5   ✓5 Review & run F6
3 · Analysis & mode                                                           │ Status · no runs yet in this session
                                                                              │
 Mode             (●) Share  ( ) Rate                         ←→ to switch    │ ✓ Ready  ^R runs it
 Metric           txn_cnt                                                   ▾ │
 Dimensions       ␣ toggles · a-z jumps · columns used elsewhere are hidden   │ Run summary
                ▏[ ] year_month                                               │  Data     autobench_demo.csv
                  [x] card_type                                               │  Entity   issuer_name → Target
                › [x] input_mode                                              │  Mode     Share · txn_cnt
                  [ ] card_type_input_mode                                    │  Dims     card_type, input_mode
                  [ ] total #          (# = numeric column)                   │  Preset   compliance_strict
                  [ ] approved #                                              │  Posture  ✓ Strict
                  [ ] fraud #                                                 │  Release  Complete output
                  [ ] Auto-detect dimensions instead                          │  Sweep    off
 ▸ More options   time column · secondary metrics · outputs        all default│  Declared merchant: No · Citi: No
 [Expert settings… F8]   optimizer tuning · 0 changed from preset             │  Output   Analysis workbook
                                                                              │  Expert   0 changes
                                                                              │
                                                                              │ Outcome, report path and log appear
                                                                              │ here after a run.
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
✓ READY  share analysis · Target · 2 dims                                                          ^R Run share analysis
^R Run  ^O Open CSV  F2-F6 Steps  ^T Results  F8 Expert  F1 Help  ^Q Quit                                    ^P Commands
```

Running. The form is locked (dimmed and not focusable) and the summary is frozen:

```text
 ✓1 Data F2   ✓2 Entity F3  ▸✓3 Analysis & mode F4   ✓4 Privacy & compliance F5   ✓5 Review & run F6
3 · Analysis & mode  ·  locked while running                                  │ ⏵ RUNNING  share · compliance_strict
                                                                              │
 Mode             (●) Share  ( ) Rate                         ←→ to switch    │  ✓ 1 Check inputs              0.0 s
 Metric           txn_cnt                                                   ▾ │  ✓ 2 Load and validate data    0.4 s
 Dimensions       ␣ toggles · a-z jumps · columns used elsewhere are hidden   │  – 3 Confirmations       none needed
                ▏[ ] year_month                                               │  ⏵ 4 Engine                    00:12
                  [x] card_type                                               │
                › [x] input_mode                                              │ Last engine message
                  [ ] card_type_input_mode                                    │  Built privacy validation data: 42
                  [ ] total #          (# = numeric column)                   │  validation entries
                  [ ] approved #                                              │
                  [ ] fraud #                                                 │ Setup is locked: this run uses the
                  [ ] Auto-detect dimensions instead                          │ values in the run summary below.
 ▸ More options   time column · secondary metrics · outputs        all default│ Cancel is not available once the
 [Expert settings… F8]   optimizer tuning · 0 changed from preset             │ engine has started (spec §7).
                                                                              │
                                                                              │ Run summary (frozen)
                                                                              │  Share · txn_cnt · card_type,
                                                                              │  input_mode · compliance_strict ·
                                                                              │  ✓ Strict · Complete output ·
                                                                              │  sweep off · merchant No · Citi No
                                                                              │
                                                                              │ [Show run log]
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
⏵ RUNNING  4/4 Engine · 00:12                                                                         Cancel unavailable
^T Results  F1 Help  ^Q Quit                                                                                 ^P Commands
```

Success. The action bar carries the full unbroken path:

```text
 ✓1 Data F2   ✓2 Entity F3  ▸✓3 Analysis & mode F4   ✓4 Privacy & compliance F5   ✓5 Review & run F6
3 · Analysis & mode                                                           │ ✓ DONE — Fully compliant
                                                                              │   Share · compliance_strict · 4.2 s
 Mode             (●) Share  ( ) Rate                         ←→ to switch    │   verdict fully_compliant
 Metric           txn_cnt                                                   ▾ │
 Dimensions       ␣ toggles · a-z jumps · columns used elsewhere are hidden   │ Report  (^Y copies the full path)
                ▏[ ] year_month                                               │ ▏benchmark_share_Target_
                  [x] card_type                                               │   20261014_101530.xlsx
                › [x] input_mode                                              │   in /home/analyst/work/ (launch dir)
                  [ ] card_type_input_mode                                    │
                  [ ] total #          (# = numeric column)                   │ Balanced CSV
                  [ ] approved #                                              │   …_Target_20261014_101530_balanced.csv
                  [ ] fraud #                                                 │ Log
                  [ ] Auto-detect dimensions instead                          │   …/logs/benchmark_log_20261014_1015…
 ▸ More options   time column · secondary metrics · outputs        all default│
 [Expert settings… F8]   optimizer tuning · 0 changed from preset             │ [Copy path ^Y] [Run again ^R]
                                                                              │ [Show run log] [Earlier runs (1)]
                                                                              │
                                                                              │ Earlier runs this session
                                                                              │  10:12 ✗ WITHHELD share · strict
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
✓ DONE  Fully compliant · /home/analyst/work/benchmark_share_Target_20261014_101530.xlsx                    ^Y Copy path
^Y Copy path  ^R Run again  ^T Results  F2-F6 Steps  F1 Help  ^Q Quit                                        ^P Commands
```

Withheld:

```text
 ✓1 Data F2   ✓2 Entity F3  ▸✓3 Analysis & mode F4   ✓4 Privacy & compliance F5   ✓5 Review & run F6
3 · Analysis & mode                                                           │ ✗ WITHHELD — privacy rules blocked
                                                                              │   publication
 Mode             (●) Share  ( ) Rate                         ←→ to switch    │   Share · compliance_strict · 3.9 s
 Metric           txn_cnt                                                   ▾ │   reason control3_numeric_policy_
 Dimensions       ␣ toggles · a-z jumps · columns used elsewhere are hidden   │   blocked · verdict violations_
                ▏[ ] year_month                                               │   detected
                  [x] card_type                                               │
                › [x] input_mode                                              │ No benchmark output was written.
                  [ ] card_type_input_mode                                    │
                  [ ] total #          (# = numeric column)                   │ Try next
                  [ ] approved #                                              │  • fewer or coarser dimensions (F4)
                  [ ] fraud #                                                 │  • Verified safe coverage or rule
                  [ ] Auto-detect dimensions instead                          │    sweep (F5)
 ▸ More options   time column · secondary metrics · outputs        all default│  • another preset (F1 compares)
 [Expert settings… F8]   optimizer tuning · 0 changed from preset             │
                                                                              │ Non-publishable run log — do not share
                                                                              │  …/quarantine/benchmark_log_2026101
                                                                              │  4_101530.txt
                                                                              │
                                                                              │ [Show details] [Run again ^R]
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
✗ WITHHELD  privacy rules blocked publication · see Results                                        ^R Run share analysis
^Y Copy path  ^R Run again  ^T Results  F2-F6 Steps  F1 Help  ^Q Quit                                        ^P Commands
```

Error:

```text
 ✓1 Data F2   ✓2 Entity F3  ▸✓3 Analysis & mode F4   ✓4 Privacy & compliance F5   ✓5 Review & run F6
3 · Analysis & mode                                                           │ ✗ FAILED — unexpected error
                                                                              │   Share · compliance_strict · 1.1 s
 Mode             (●) Share  ( ) Rate                         ←→ to switch    │   KeyError 'card_type_input_mode'
 Metric           txn_cnt                                                   ▾ │   phase analysis
 Dimensions       ␣ toggles · a-z jumps · columns used elsewhere are hidden   │
                ▏[ ] year_month                                               │ No report was written.
                  [x] card_type                                               │
                › [x] input_mode                                              │ Try next
                  [ ] card_type_input_mode                                    │  • check the dimension columns exist
                  [ ] total #          (# = numeric column)                   │  • run again; if it repeats, send the
                  [ ] approved #                                              │    diagnostic log to support
                  [ ] fraud #                                                 │
                  [ ] Auto-detect dimensions instead                          │ Diagnostic log (traceback inside)
 ▸ More options   time column · secondary metrics · outputs        all default│  …/logs/benchmark_log_20261014_1015
 [Expert settings… F8]   optimizer tuning · 0 changed from preset             │  30.txt
                                                                              │
                                                                              │ [Copy log path ^Y] [Run again ^R]
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
                                                                              │
✗ FAILED  unexpected error · see Results                                                           ^R Run share analysis
^Y Copy path  ^R Run again  ^T Results  F2-F6 Steps  F1 Help  ^Q Quit                                        ^P Commands
```

Expert settings at 120x40 (two group columns):

```text
Expert settings · preset compliance_strict · 1 changed · posture stays ✓ Strict (from preset)
Applies to runs in this session. Changing the preset resets these. Empty field = inherit the preset. Esc = done
 [Reset all to preset]  [Export to file…]

 Linear programming                                         Subset search
   Tolerance (pp)            ▏0.0        preset               Enabled                [x] on      preset
   LP max iterations          1000       preset               Strategy               greedy    ▾ preset
   Lambda penalty             ·          engine default       Max attempts           50          preset
   Volume weighting exponent  ·          engine default       Max slack threshold    0.05        preset
   Volume-weighted penalties  [ ] off    engine default       Trigger on slack       [x] on      preset
                                                              Prefer slacks first    [ ] off     preset
 Constraints and bounds
   Volume preservation (0–1)  0.85       ● changed (0.9)      Bayesian fallback
   Min weight                 0.5        preset               Bayesian max iter.     100         preset
   Max weight                 2.0        preset               Learning rate          0.01        preset

 Analysis                                                     Output sheets
   Best-in-class percentile   0.85       preset               Debug sheets           [x] on      preset
                                                              Privacy validation     [x] on      (always
                                                                sheet                  included while debug on)

 Exported files go to the launch folder and the full path is shown here after export.

















Esc Done  Tab Next  ↵ Edit  F1 Help                                ^P Commands
```

### 3.5 Modals (80x24; the same boxes are centred at 120x40)

CSV picker. The filter has initial focus; ↑↓ move the quick-pick highlight from the filter; Enter opens it. Capped at 200 quick picks (04 #12–13).

```text
▸!1 Data  ○2 Entity  ○3 Analysis  ○4 Privacy  !5 Review
╭─ Open CSV ─ from /home/analyst/work ───────────────────────────────────────╮
│ ▏Filter: demo█                                                             │
│ Quick picks (2 of 2412 · capped at 200)  │ Browse workspace                │
│ › data/autobench_demo.csv        2.1 KB  │ ▾ .                             │
│   tests/fixtures/gate_demo.csv   3.4 KB  │   ▸ data                        │
│                                          │   ▸ tests                       │
│                                          │   ▸ outputs                     │
│                                          │                                 │
│                                          │                                 │
│                                          │                                 │
│                                          │                                 │
│                                          │                                 │
│                                          │                                 │
│                                          │                                 │
│                                          │                                 │
│                                          │                                 │
│                                          │                                 │
│ ↑↓ move · ↵ open · Tab list/tree · Esc cancel                              │
╰────────────────────────────────────────────────────────────────────────────╯



↑↓ Move  ↵ Open  Tab List/tree  Esc Cancel
```

Accuracy-first consent. Initial focus is **Cancel run** (`▸…◂`).

```text
 ✓1 Data  ✓2 Entity  ✓3 Analysis  ✓4 Privacy ▸✓5 Review & run
5 · Review & run




        ╭─ Consent needed: accuracy-first run ─────────────────────────╮
        │                                                              │
        │ Preset low_distortion uses the Accuracy first posture. It    │
        │ favours analytical fidelity over strict compliance. If the   │
        │ privacy rules are not met, the report is a NON-PUBLISHABLE   │
        │ diagnostic.                                                  │
        │                                                              │
        │ You are asked on every run. Your answer is never saved.      │
        │ posture accuracy_first · source preset low_distortion        │
        │                                                              │
        │            [▸Cancel run◂]   [ I consent for this run ]       │
        ╰──────────────────────────────────────────────────────────────╯




⏵ RUNNING  3/4 Waiting for your confirmation                       ^G Cancel run
Tab Move  ↵ Choose  Esc Cancel run
```

Clearing-spend attestation. Initial focus is **Cancel run**.

```text
 ✓1 Data  ✓2 Entity  ✓3 Analysis  ✓4 Privacy ▸✓5 Review & run
5 · Review & run




        ╭─ Confirm: Total is clearing spend ───────────────────────────╮
        │                                                              │
        │ Fraud rates use the Total column “total” as the              │
        │ clearing-spend basis. Autobench checks the numbers, but it   │
        │ cannot prove where the column came from.                     │
        │                                                              │
        │ Is “total” the governed clearing-spend column?               │
        │ Asked on every run. Never saved.                             │
        │ attestation fraud_clearing_spend_basis · source tui_modal    │
        │                                                              │
        │       [▸Cancel run◂]   [ Yes, total is clearing spend ]      │
        ╰──────────────────────────────────────────────────────────────╯




⏵ RUNNING  3/4 Waiting for your confirmation                       ^G Cancel run
Tab Move  ↵ Choose  Esc Cancel run
```

Validation results, errors present. Every issue is listed with a text severity:

```text
 ✓1 Data  ✓2 Entity  ✓3 Analysis  ✓4 Privacy ▸✓5 Review & run
5 · Review & run



      ╭─ Input check: 1 error, 2 warnings (all 3 shown) ─────────────────╮
      │                                                                  │
      │ ▸ ✗ ERROR    Column txn_cnt has negative values                  │
      │              data rows 3, 17, 31 (1 = first data row)            │
      │              check negative_values                               │
      │   ⚠ WARNING  2 periods have fewer than 3 peers                   │
      │              2024-03, 2024-07 · check sparse_periods             │
      │   ⚠ WARNING  Entity P6 appears in only 1 period                  │
      │              check entity_coverage                               │
      │                                                                  │
      │ Proceed is unavailable while there are errors. Fix the CSV,      │
      │ then press Enter in step 1 to reload the same path.              │
      │                                                                  │
      │    [ Cancel run ]   [ Proceed with warnings ] (disabled)         │
      ╰──────────────────────────────────────────────────────────────────╯


⏵ RUNNING  3/4 Waiting for your confirmation                       ^G Cancel run
↑↓ Read issues  Tab Buttons  Esc Cancel run
```

Validation results, warnings only, longer than the viewport. Proceed unlocks once the last issue has been shown:

```text
 ✓1 Data  ✓2 Entity  ✓3 Analysis  ✓4 Privacy ▸✓5 Review & run
5 · Review & run




      ╭─ Input check: 0 errors, 30 warnings ─────────────────────────────╮
      │                                                                  │
      │ ▸ ⚠ WARNING  2 periods have fewer than 3 peers                   │
      │              2024-03, 2024-07 · check sparse_periods             │
      │   ⚠ WARNING  Entity P6 appears in only 1 period                  │
      │              check entity_coverage                               │
      │   ⚠ WARNING  …                                 ▼ 27 more         │
      │                                                                  │
      │ Warnings do not stop the run. Read to the end of the list        │
      │ (3 of 30 seen) before you can proceed.                           │
      │                                                                  │
      │    [ Cancel run ]   [ Proceed with warnings ] (disabled)         │
      ╰──────────────────────────────────────────────────────────────────╯



⏵ RUNNING  3/4 Waiting for your confirmation                       ^G Cancel run
↑↓ Read issues  PgDn Page  Tab Buttons  Esc Cancel run
```

Help, Presets tab (replaces the Preset Guide; generated from `presets/*.yaml`, 03 F33):

```text
 ✓1 Data  ✓2 Entity  ✓3 Analysis ▸✓4 Privacy & compliance  ✓5 Review
╭─ Help ─ [Keys]  [Presets]  [Privacy terms] ────────────────────────────────╮
│ Presets (from presets/*.yaml)   posture          consent                   │
│ › balanced_default              ⚠ Best effort    no                        │
│     Balance of compliance and consistency                                  │
│   compliance_strict  (default)  ✓ Strict         no                        │
│     Zero tolerance for violations                                          │
│   low_distortion                ⚠ Accuracy first every run                 │
│     Tight weight bounds                                                    │
│   minimal_distortion            ⚠ Accuracy first every run                 │
│     Very high tolerance                                                    │
│   research_exploratory          ⚠ Best effort    no                        │
│     Maximum flexibility for difficult datasets                             │
│   strategic_consistency         ⚠ Best effort    no                        │
│     Global weights with minimised violations                               │
│                                                                            │
│ Strict: only publishable output. Best effort: may finish with labelled     │
│ non-compliant output. Accuracy first: consent each run; may be             │
│ NON-PUBLISHABLE.                                                           │
│ ↵ use highlighted preset · ←→ tabs · Esc close                             │
╰────────────────────────────────────────────────────────────────────────────╯


↑↓ Move  ↵ Use preset  ←→ Tabs  Esc Close
```

Quit while the engine is running (§7.2):

```text
 ✓1 Data  ✓2 Entity  ✓3 Analysis  ✓4 Privacy ▸✓5 Review & run
5 · Review & run





        ╭─ Quit while the engine is running? ──────────────────────────╮
        │                                                              │
        │ The engine cannot be stopped safely mid-run. It keeps        │
        │ running even if this window closes, and it still writes      │
        │ its outputs (the privacy rules still apply).                 │
        │                                                              │
        │ Quit when finished closes Autobench as soon as the run       │
        │ ends and prints the outcome in the terminal.                 │
        │                                                              │
        │    [▸Keep running◂]   [ Quit when finished ]                 │
        ╰──────────────────────────────────────────────────────────────╯




⏵ RUNNING  4/4 Engine · 00:41                                 Cancel unavailable
Tab Move  ↵ Choose  Esc Keep running
```

Quit while a run is waiting for a confirmation (resolves D10, §7.2):

```text
 ✓1 Data  ✓2 Entity  ✓3 Analysis  ✓4 Privacy ▸✓5 Review & run
5 · Review & run






        ╭─ Quit Autobench? ────────────────────────────────────────────╮
        │                                                              │
        │ A run is waiting for your confirmation. Quitting cancels     │
        │ it first. Nothing has been written, and no consent or        │
        │ attestation is recorded.                                     │
        │                                                              │
        │         [▸Keep working◂]   [ Cancel run and quit ]           │
        ╰──────────────────────────────────────────────────────────────╯






⏵ RUNNING  3/4 Waiting for your confirmation                       ^G Cancel run
Tab Move  ↵ Choose  Esc Keep working
```

Preset change with expert edits (D2, §8.2):

```text
 ✓1 Data  ✓2 Entity  ✓3 Analysis ▸✓4 Privacy & compliance  ✓5 Review
4 · Privacy & compliance






        ╭─ Change preset and reset expert settings? ───────────────────╮
        │                                                              │
        │ You changed 3 expert settings on compliance_strict.          │
        │ Switching to low_distortion resets them to that preset's     │
        │ values, and its posture becomes Accuracy first (consent      │
        │ on every run).                                               │
        │                                                              │
        │   [▸Keep compliance_strict◂]   [ Reset and switch ]          │
        ╰──────────────────────────────────────────────────────────────╯





✓ READY  share analysis · Target                           ^R Run share analysis
Tab Move  ↵ Choose  Esc Keep current preset
```

Validation at 120x40 (same box, more room for issues: up to 12 visible):

```text
 ✓1 Data F2   ✓2 Entity F3  ▸✓3 Analysis & mode F4   ✓4 Privacy & compliance F5   ✓5 Review & run F6











                          ╭─ Input check: 1 error, 2 warnings (all 3 shown) ─────────────────╮
                          │                                                                  │
                          │ ▸ ✗ ERROR    Column txn_cnt has negative values                  │
                          │              data rows 3, 17, 31 (1 = first data row)            │
                          │              check negative_values                               │
                          │   ⚠ WARNING  2 periods have fewer than 3 peers                   │
                          │              2024-03, 2024-07 · check sparse_periods             │
                          │   ⚠ WARNING  Entity P6 appears in only 1 period                  │
                          │              check entity_coverage                               │
                          │                                                                  │
                          │ Proceed is unavailable while there are errors. Fix the CSV,      │
                          │ then press Enter in step 1 to reload the same path.              │
                          │                                                                  │
                          │    [ Cancel run ]   [ Proceed with warnings ] (disabled)         │
                          ╰──────────────────────────────────────────────────────────────────╯











⏵ RUNNING  2/4 Input check needs you                                                                       ^G Cancel run
↑↓ Read issues  Tab Buttons  Esc Cancel run
```

### 3.6 Prototype screenshots

Each name exists as `<name>_80x24` and `<name>_120x40` in
`…/scratchpad/phase1/shots/*.svg` and `…/scratchpad/phase1/png/*.png`:
`launch`, `data_loaded`, `entity`, `analysis_share`, `analysis_rate`,
`more_options`, `privacy`, `review`, `blocked_ready`, `running`, `success`,
`blocked`, `error`, `consent`, `clearing`, `validation`, `validation_warn`,
`picker`, `guide`, `quit_running`, `expert`, `preset_reset`,
`cancel_confirm`. NO_COLOR captures are in `…/scratchpad/phase1/png_nocolor/`
(`analysis_share_80x24`, `privacy_80x24`, `success_80x24`, `consent_80x24`,
`validation_80x24`, `blocked_120x40`, `review_120x40`).

What the prototype proved:

- Every step fits at 80x24 with the rail, action bar and footer always
  visible. Run is visible on every screen.
- The verdict and the full report path can be read at 80x24
  (`png/success_80x24.png`).
- Under NO_COLOR, `[x]`/`[ ]`, `✓`/`!`/`⚠`, `✗ WITHHELD` and the focused
  dialog button can all be read (`png_nocolor/*`).

What it also showed:

- The prototype's simplified CSS still lets some hints wrap.
- The prototype's 42-column right column breaks a long report filename. This
  is why the full path goes in the action bar.
- A focused but unhighlighted SelectionList is not visible under NO_COLOR.
  The focus token in 02-visual-system must include a glyph (`▏`).

---

## 4. Keyboard

### 4.1 Global bindings (`priority=True`, work in any field)

Chosen from keys that no Textual 7.5 stock widget binds. `Input` takes
`^A ^E ^D ^W ^U ^F ^K ^X ^C ^V`; `App` takes `^Q ^C`; `Screen` takes Tab and
`^C`. The set also avoids `^A` (GNU screen), `^B` (tmux), `^S`/`^Q` flow
control, `^Z`, `^L` as a destructive key, and F1/F10/F11, which GNOME Terminal
takes. F1 stays as a convenience with palette and `?` fallbacks.

| Key | Action | Notes |
|---|---|---|
| `^R` | Run | Ready → starts the run. Not ready → focuses the first blocker (step order), and the action bar names it and counts the rest. Running → no-op, and the action bar flashes `Already running`. |
| `^G` | Cancel run | Only during stages 1–3 (§7.2). During the engine stage the action bar says `Cancel unavailable — the engine can't stop safely`. |
| `^O` | Open CSV picker | |
| `F2`–`F6` | Go to step 1–5 | Focus lands on the first blocker in that step, otherwise the first field. Also switches back from the results view. `Alt+1`…`Alt+5` are aliases (GNOME Terminal uses Alt+digit for its own tabs, so they are a fallback only). |
| `^T` | Toggle setup ⇄ status/results | <110: swaps the view. ≥110: moves focus into the status column and back. |
| `^Y` | Copy report path (or log path after a withheld or failed run) | `App.copy_to_clipboard` (OSC 52) plus a toast "Copied". The full path is always on screen in case OSC 52 is blocked. |
| `F8` | Expert settings | Also a button in step 3 and a palette entry. |
| `F1` | Help (tabs: Keys, Presets, Privacy terms) | `?` opens it too when focus is not in a text field. |
| `^P` | Command palette | Textual default. |
| `^Q` | Quit | Asks first while a run is active (§7.2). Shown in the footer (01 E.21). |

Removed: `^A` (advanced), `^E` (export), `^L` (clear log), `F1` as "Preset Guide".

### 4.2 Keys inside widgets

| Widget | Keys |
|---|---|
| Path Input | Enter = load, and on success focus moves to Target entity. → accepts the grey suggestion. `^U` clears. |
| Select (all) | Enter/Space/↑↓ open. **Type letters to jump** (stock `SelectOverlay` substring search, 0.7 s reset). Esc closes. The footer shows `a-z Jump` whenever a Select is focused. |
| Large entity filter | Type to filter. ↑↓ move. Enter chooses. Esc clears the filter. |
| Dimensions list | ↑↓ move. Space toggles. Letters jump to the next matching column (a small subclass of `SelectionList`). |
| Mode switch | ← Share, → Rate, Space toggles. |
| More options (Collapsible title) | Enter toggles. |
| Dialogs | Tab/Shift+Tab or ←→ move between buttons. Enter chooses. Esc = the safe choice. |
| Validation list | ↑↓/PgUp/PgDn read. Tab to the buttons. Esc = cancel run. |
| Results view | Enter on a button. Paths are focusable read-only lines, so terminal selection works. |

### 4.3 Focus order and initial focus

Tab and Shift+Tab move within the visible step. **From the last stop, Tab
shows the next step and focuses its first stop. Shift+Tab from the first stop
goes to the previous step's last stop. Review wraps to Data.** Non-form
containers (log, scroll containers, rail) are never stops (02 friction #11).
This keeps the Phase 0 counting rules valid and means a forward-only Tab user
still reaches everything.

| Step | Tab order (share / rate differences noted) |
|---|---|
| 1 | Browse → path. Initial focus: path. |
| 2 | Entity column → Target entity |
| 3 | Mode → Metric (share) *or* Total → Approved → Fraud (rate) → Dimensions list → Auto-detect → More options title → [More options fields when open: Time column → Secondary metrics → Output format → Fraud in bps (when enabled) → Output file → Validate → Impact → Compare → Export CSV → Include calculated (when enabled)] → Expert settings button |
| 4 | Preset → Release mode (share only) → Rule sweep (skipped while locked) → Merchant-spend → Citi competitor → Citibank entity (when enabled) |
| 5 | Each blocker line (when present) → Run → Clear restored values (when present) |
| Results | Report path line → Copy → Run again → Show run log → Earlier runs |

Initial focus rules:

1. Launch: the path field (step 1).
2. After a successful load (Enter or picker): **Target entity**. It is the one
   field chosen fresh on every run (01 D).
3. Step jump (F-key, palette, mouse on the rail): the first blocker in that
   step, otherwise its first stop.
4. `^R` while not ready: the first blocker overall.
5. Run start (<110): the status view, with no focus inside it. The setup view
   is locked. Run end: <110 switches to Results, focus on the report path line
   (success) or the first "Try next" item (withheld or failed). ≥110: focus
   stays where it was, and the action bar announces the outcome.
6. Any consent or attestation dialog: **Cancel run**.
7. Validation dialog: the first issue.
8. Closing a dialog: focus returns to the widget focused before. Exception:
   cancelling validation with errors goes to the path field with the path kept,
   so Enter reloads the corrected file. J4b recovery drops from `^U` + 23 typed
   characters to 1 key.

### 4.4 Footer per context

The footer holds one row (80 columns). Contents per context:

| Context | Footer |
|---|---|
| Setup, text field focused | `^R Run  ^O Open CSV  F2-6 Steps  ^T Status  F1 Help  ^Q Quit      ^P Commands` |
| Setup, Select focused | `↵ Open  a-z Jump  ^R Run  F2-6 Steps  ^T Status  F1 Help  ^Q Quit   ^P Commands` |
| Setup, dimensions list | `␣ Toggle  a-z Jump  ^R Run  F2-6 Steps  ^T Status  F1 Help  ^Q Quit  ^P Commands` |
| Running, before the engine | `^G Cancel run  ^T Setup  F1 Help  ^Q Quit                          ^P Commands` |
| Running, engine | `^T Setup  F1 Help  ^Q Quit                                         ^P Commands` |
| Results | `^Y Copy path  ^R Run again  ^T Setup  F2-6 Steps  F1 Help  ^Q Quit  ^P Commands` |
| Consent / attestation dialog | `Tab Move  ↵ Choose  Esc Cancel run` |
| Validation dialog | `↑↓ Read issues  Tab Buttons  Esc Cancel run` |
| Picker | `↑↓ Move  ↵ Open  Tab List/tree  Esc Cancel` |
| Expert | `Esc Done  Tab Next  ↵ Edit  F1 Help                                ^P Commands` |
| ≥110 columns | adds `F8 Expert`; `^T` reads `Results` |

The `a-z Jump` and `␣ Toggle` entries are display-only bindings
(`Binding(..., key_display=...)`) on small widget subclasses, so the stock
`Footer` renders them. **No launch toast.** The footer and F1 replace it.

### 4.5 Command palette entries

A `Provider` registered in `App.COMMANDS` (03 F25):

- Run analysis · Cancel run · Open CSV… · Reload current CSV
- Go to: Data / Entity / Analysis & mode / Privacy & compliance / Review & run
- Switch mode to Share / Rate · Choose preset… · Preset guide
- Expert settings · Reset expert settings to preset · Export expert settings to file…
- Clear restored values · Copy report path · Copy log path · Show run log ·
  Show earlier runs · Toggle status view
- Help: keyboard shortcuts · Quit

Plus the stock system commands (theme and so on).

---

## 5. States

### 5.1 Per region

| Region | Empty | Loading | Error | Blocked | Disabled |
|---|---|---|---|---|---|
| Rail | Before a load, steps 2–3 show `○` and step 1 shows `!` | Unchanged | Step 1 shows `!` after a load error | Each blocking step shows `!`, Review shows `!` | Never disabled. While running every glyph is frozen, and the current-step marker moves to Review |
| Step 1 | `No file loaded. Type a path and press Enter, or press ^O.` | `Reading headers…` on the meta line (spinner glyph `⏵`) | Inline `✗ Not found: …` / `✗ Not a CSV: …` / `✗ Can't read: <reason>`, with focus kept | — | Locked while running |
| Step 2 | Selects read `Load a CSV first` and are disabled | `Loading entities…` prompt. If the target was set before the reload, Run is blocked with `Target entity values are still loading` (existing rule) | `✗ Couldn't read entity values` plus a retry hint | — | Locked while running |
| Step 3 | Same as step 2 | — | — | Missing required field: inline `! Required` under it, plus the rail and action bar | Rate-only fields are hidden in share mode, and the other way round. Dependent options are disabled with the reason in `(…)` |
| Step 4 | Shows defaults (preset `compliance_strict`) even before a load | Posture line: `Resolving posture…` (worker, §8.2) | Preset YAML unreadable: `✗ Preset couldn't be read · run blocked`, a blocker | Citibank entity missing | Sweep locked by VSC, with the reason. Citibank entity disabled until the box is ticked |
| Review | `! Not ready — open a CSV file first (F2)` | — | — | List of blockers as buttons | — |
| Status/results | Idle: `no runs yet in this session` plus readiness | Stage list | Outcome card (§7.3) | Idle readiness list | — |
| Action bar | `! NOT READY Open a CSV file` | `⏵ RUNNING n/4 <stage>` | `✗ FAILED …`, `✗ WITHHELD …` | `! NOT READY <first blocker> (+N more)`. The run label is dimmed but `^R` still works (it jumps) | Never disabled |

### 5.2 Run states

`idle → checking → validating → (input check dialog) → awaiting confirmation → engine → done | withheld | failed | cancelled`.
"Awaiting confirmation" is a state of its own (03 F02). The status no longer
reads "Validating" while a consent dialog waits.

| State | Action bar left | Right | Glyph |
|---|---|---|---|
| ready | `✓ READY  share analysis · Target · 2 dims` | `^R Run share analysis` | ✓ |
| not ready | `! NOT READY  Choose dimensions (+1 more)` | `^R Run …` (dimmed) | ! |
| checking / validating | `⏵ RUNNING  2/4 Loading and validating data` | `^G Cancel run` | ⏵ |
| awaiting | `⏵ RUNNING  3/4 Waiting for your confirmation` | `^G Cancel run` | ⏵ |
| engine | `⏵ RUNNING  4/4 Engine · 00:12` | `Cancel unavailable` | ⏵ |
| done | `✓ DONE  Fully compliant · <report filename or path>` | `^Y Copy path` | ✓ |
| done (labelled non-compliant, best_effort) | `⚠ DONE  Labelled non-compliant · <path>` | `^Y Copy path` | ⚠ |
| done (accuracy_first diagnostic) | `⚠ DONE  NON-PUBLISHABLE diagnostic · <path>` | `^Y Copy path` | ⚠ |
| withheld | `✗ WITHHELD  privacy rules blocked publication` | `^R Run …` | ✗ |
| failed | `✗ FAILED  <one-line reason> · see Results` | `^R Run …` | ✗ |
| cancelled | `■ CANCELLED  nothing was written` | `^R Run …` | ■ |

The terminal title mirrors the state: `Autobench — ✓ DONE`, `Autobench — ⏵ 4/4`.

### 5.3 Toast policy

1. **At most 2 visible.** A third replaces the oldest. Keep our own deque and
   dismiss the oldest before `notify`. Textual 7.5 has no public per-toast
   dismiss (`_unnotify` is private), so wrap it in one helper.
2. **Placement: top right, below the rail.** `ToastRack { dock: top; align: right top; }`,
   with a max width of 40 columns (50% at 80). The rail, action bar and footer
   are never covered.
3. **Suppressed while any ModalScreen is open.** Messages raised then are
   queued and shown after the modal closes. Anything older than 10 s is
   dropped. Toasts can therefore never cover a modal button (03 F04).
4. **Toasts only for transient confirmations:** `Report path copied`,
   `Expert settings exported to <full path>`,
   `Restored 4 values from last session` (once per process). Timeouts: 3 s
   info, 6 s warning.
5. **Never toast-only:** errors, run outcomes, load failures and validation
   failures. These live inline, in the action bar and in Results. No duplicate
   "CSV loaded" (03 F04): the meta line is the confirmation.

---

## 6. Compliance interaction rules

These are UI rules. Core enforcement is unchanged. The TUI never sets an
attestation or acknowledgement field without the operator's action in that
run attempt.

1. **Default focus on the safe choice.** Accuracy-first consent, clearing-spend
   attestation, quit, preset-reset and cancel dialogs all open on the
   non-committing button. Enter on open = Cancel. Affirming takes a move
   (Tab or →) and then Enter. Esc = Cancel. (D3)
2. **The affirmative names the act.** `I consent for this run`,
   `Yes, total is clearing spend`. Not "Confirm". Attestation buttons use the
   primary role, not the destructive red role. Red is reserved for
   destructive acts such as "Discard" (03 F12, 01 E.22).
3. **Per attempt, never saved, never pre-filled.** Consent and the
   clearing-spend attestation are asked on every run attempt (today's rule,
   `tests/test_tui_ux.py:387`). Their answers are never written to the session
   file. The merchant-spend and Citi declarations and the Citibank entity are
   never restored. The step 4 box says so in its title.
4. **Ask once the run could otherwise proceed.** Order: live readiness →
   stage 1 checks (all problems at once, not one per attempt) → stage 2 load +
   validation (+ input check dialog) → stage 3 confirmations (consent, then
   clearing spend) → engine. A cancel at any dialog leaves nothing recorded.
5. **Consent follows the effective posture.** Resolve the posture with the
   same configuration the run will use: `build_run_config(request.to_namespace())`
   then `.get('compliance_posture')`, which is what
   `enforce_compliance_preconditions` reads. This applies **whether or not
   expert overrides are present**. If the result is `accuracy_first`, ask.
   This closes the D2 dead end. Core still blocks a run without the
   acknowledgement.
6. **Validation shows every issue.** One row per issue with a text severity
   (`✗ ERROR`, `⚠ WARNING`), counts in the title (`1 error, 2 warnings (all 3 shown)`),
   the message markup-escaped (03 F31), and rows labelled
   `data rows 3, 17 (1 = first data row)` when the frame has the default
   RangeIndex; otherwise `row index 3, 17`, as today. The internal check code goes on a
   dimmed second line.
   - **Errors:** Proceed is disabled and the reason is stated.
   - **Warnings only:** Proceed stays disabled until every issue has been
     scrolled into view, and the button says `(3 of 30 seen)`. (D1)
7. **Status = label + symbol + colour**, everywhere: action bar, rail, Results,
   posture line, dialogs. Colour comes from theme tokens only (02-visual-system).
8. **Plain language first, internal codes second.** For example,
   `✗ WITHHELD — privacy rules blocked publication` and, dimmed below it,
   `reason control3_numeric_policy_blocked · verdict violations_detected`.
   Codes stay visible for support and audit, never as the only text (03 F06).
   The plain-language label table belongs in `core/` so the CLI shares it.
   That is a non-behavioural addition, tracked in 02-visual-system.
9. **Non-strict posture is visible before the run.** Step 4's posture line,
   the rail `⚠`, the Review line and the run summary all show
   `⚠ Best effort` / `⚠ Accuracy first` with what it means. Today the
   best_effort warning only appears in the log after Run (03 copy audit).
10. **Non-publishable artefacts are labelled where the path is shown.**
    `Non-publishable run log — do not share`, and
    `⚠ DONE NON-PUBLISHABLE diagnostic` for consented accuracy_first output.
    `^Y` copies the path, but the label stays on screen next to it.
11. **Publishable-output validation and privacy release coupling are
    untouched.** VSC forces sweep for share requests. Rate requests never
    carry a release mode (`_privacy_values_from_widgets`). Core's denial path
    and log quarantine run as today. The UI only reports them.

---

## 7. Run experience

### 7.1 Stages

| # | Stage | Where it runs today | What the UI shows | Exact or inferred |
|---|---|---|---|---|
| 1 | Check inputs | `run_analysis` preflight (`_fail_launch` chain) | ✓ instantly, or the full list of blockers | Exact. Becomes a pure function over a **request snapshot taken on the UI thread at `^R`**. That fixes D7 (worker reading widgets) and defines the frozen summary. |
| 2 | Load and validate data | `prepare_run_data` + `validate_analysis_input` in the TUI worker, only when `validate_input` is on | Elapsed time, then the input check dialog if there are issues | Exact |
| 3 | Confirmations | consent and clearing-spend dialogs | `none needed` or the dialogs in turn | Exact |
| 4 | Engine: optimise, check privacy, write | `execute_run` → `core.analysis_run._execute_run_impl` | Elapsed time plus the last engine log line (from the existing `LogHandler`) | **Inferred.** Core tracks `configuration → input → analysis → output` in `_PhaseTracker`, which is private and used only for telemetry. The TUI can't see it without a core change (Q1). |

### 7.2 Cancel: what is safely possible

Findings:

- **Textual thread workers can't be interrupted.** `@work(thread=True)` runs
  in the asyncio default executor. `Worker.cancel()` only sets
  `is_cancelled`. The probe (`exit_probe.py`) cancelled a 3 s thread worker at
  0.31 s and exited the app. The worker still ran to 3.02 s, and
  `asyncio.run` did not return until it finished. A quit during the engine
  therefore does not stop the engine, and the process stays alive, without its
  UI, until the outputs are written.
- **Core has no cooperative cancellation points.** `_execute_run_impl` runs
  configuration → input → analysis → output with no hook, and the output phase
  writes workbooks, balanced CSV, coverage certificates and the log through
  `PrivacyRunLogGate` (`log_gate.finish` in `finally`). Interrupting it, for
  example by killing a subprocess, could leave partial files or skip the
  log-gate finalisation. That is not acceptable.
- **New defect D10: quitting while a confirmation dialog waits hangs the
  process.** `_confirm_accuracy_first_consent` and
  `_confirm_clearing_spend_basis` block the worker on `threading.Event.wait()`
  with no timeout. Probe on the real `tui_app.py` (`quit_probe.py`): rate +
  fraud → clearing-spend dialog → `^Q` → confirm Quit. The app context
  exited at 3.4 s with thread `asyncio_0` still alive, and the process never
  exited (killed by `timeout 40`). The engine was not called, so privacy was
  not affected.

Design:

| Stage | `^G` Cancel | Effect |
|---|---|---|
| 1 Check | Available (instant) | Back to idle |
| 2 Load and validate | Available | Sets a cancel flag. The file read cannot be interrupted, so the bar shows `■ Cancelling… waiting for the file read` and the worker checks `is_cancelled` before opening any dialog or calling the engine. Deferred logging is finalised with `privacy_authorized=False`, as today's failure paths do. Emits the existing `action_cancelled`. Result: `■ CANCELLED nothing was written`. |
| 3 Confirmations | Available. Each dialog's Cancel and Esc do the same thing | As above, and nothing is recorded |
| 4 Engine | **Not available.** Shown as `Cancel unavailable` with the reason | The run finishes. Outputs are written under the normal privacy rules |

Quit (`^Q`):

- Idle: quit and save the session (today's behaviour).
- Stages 1–3: dialog `[Keep working] [Cancel run and quit]`, default Keep. On
  quit, **every pending confirmation `Event` is set with `False`** (resolves
  D10). An `on_unmount` safety net does the same.
- Engine: dialog `[Keep running] [Quit when finished]`, default Keep.
  Quit-when-finished sets a flag. When the worker ends, the app exits and
  prints a one-line outcome to the terminal: verdict label + report path. For
  withheld runs, the label only, never a quarantine path. A second `^Q` in
  that state just repeats the dialog. Nothing in the UI promises a hard stop.
- Phase 3 option (Q1): an optional `cancel_requested` callable on the shared
  run seam, checked by core at the `configuration → input → analysis` phase
  boundaries **and before `output` starts**. That makes "cancel before
  anything is written" possible during most of the engine stage. It is an
  additive core change and needs owner approval. Until then the UI makes no
  such promise.

### 7.3 Results

- **One outcome card** per run: state label + glyph, mode · preset · entity ·
  duration, the internal verdict and posture dimmed, then every artefact path
  on its own line: report(s), publication workbook, balanced CSV, coverage
  certificate (VSC), log or quarantined log, each labelled (03 T9).
  - VSC facts (candidate, released and suppressed counts, coverage %) appear
    as in today's `_format_safe_coverage_summary_*`.
- **Paths are whole.** They wrap only at `/ _ - .` boundaries, never
  mid-token. The full unbroken report path is in the action bar after success
  (≥110) or on its own focusable line (<110). `^Y` copies it. Paths are never
  basenames only (03 T9).
- **Copy:** `^Y` / `[Copy report path]` → `copy_to_clipboard`. When there is no
  report (withheld or failed), `^Y` copies the log path and the button says so.
- **Next steps** for withheld and failed runs map reason → action (03 F30). The
  table lives in `core/` with the label map (02-visual-system).
- **Run again** (`^R` or the button) re-runs with the current form values. It
  repeats stage 1–3 checks and dialogs. Re-runs are never automatic.
  Restored-value markers clear after the first run.
- **Earlier runs this session** (in memory only, never persisted): time,
  glyph, state, mode, preset, report path. Enter shows that run's card.
- **Run log:** a full-screen `Log` view from `[Show run log]`. Short
  `HH:MM:SS` stamps and level glyphs (03 T8), wrapped. No clear key. Each run
  keeps its own log section.

---

## 8. Session restore, D2 and D3

### 8.1 Session restore (fixes D4)

Rule: **never store governed data references or attestations. Store column
roles and preferences. Apply them after the first CSV header load in the
process, and only where the column exists in the newly loaded file. Show
everything that was restored.**

| Setting | Stored? | Restored when | Shown as |
|---|---|---|---|
| CSV path, output filename | **No** (today's rule: "the operator must choose the dataset afresh") | — | — |
| Target entity | **No** (privacy rule) | — | — |
| Merchant-spend, Citi competitor, Citibank entity | **No** (attestations) | — | — |
| Accuracy-first consent, clearing-spend attestation | **No** | — | — |
| Expert overrides | **No** (today an override path resets on launch) | — | — |
| Mode (share/rate) | **Yes, new** | at mount | `↺` on rail step 3, `Restored` line in Review |
| Entity column, metric, total, approved, fraud, time column | Yes (already stored today) | **after the first header load**, if the column exists | `↺` beside each field. Review lists them |
| Dimensions, secondary metrics, auto-detect | Yes (merged keys) | after the first header load, intersected with the file's columns | `↺` |
| Preset | Yes (today) | at mount | `↺` beside Preset. The posture line updates. A restored non-strict posture shows `⚠` on the rail |
| Privacy release mode, rule sweep | Yes (today's behaviour, kept; Q3) | at mount, with today's coupling order | `↺ restored` in the hint line under the field, and in Review |
| Output format, the M-tier checkboxes, debug sheets | Yes (today) | at mount | `↺` only when different from the default |

- A one-time toast `Restored 6 values from last session · F6 to review`
  appears after the first load. **[Clear restored values]** (Review and
  palette) resets those fields to their defaults.
- A file that lacks a stored column silently drops that one value. Review
  lists `Not restored: rate_total (column "total" not in this file)`.
- Restored values never skip a dialog. Consent and attestations are asked as
  usual.
- Legacy session keys (`share_dims`, `rate_dims`, `share_debug`, …) are read
  and mapped to the merged controls. The new mode key is additive.

### 8.2 D2: stale advanced overrides and skipped consent

Decision:

1. **Expert edits are an in-memory diff against the current preset.** There is
   no Apply button and no override file sitting around between runs.
2. At **run time** (stage 1), if the diff is not empty, the override YAML is
   written once through `PresetWorkflow.write_override_file(...)`, with
   `posture=` taken from **the currently selected preset**, and sent as
   `config`. Because the file is created from the current preset at each run,
   its posture can't go stale. The TUI deletes the file after the run; Q2 asks
   whether it may move out of the CWD.
3. Changing the preset when the diff is not empty opens the reset dialog
   (default **Keep current preset**). If accepted, the diff resets to the new
   preset's values. With no diff, the preset changes silently, as today.
4. Consent is decided from the **effective** posture (§6 rule 5), so the
   "override present → consent skipped → core `RunBlocked` with no way to
   consent" path no longer exists.
5. Step 4's posture line shows its source: `from preset` or
   `from preset + 3 expert changes`. The expert screen header repeats the
   effective posture.
6. Export writes `exported_<preset>_overrides.yaml` as today (CWD; Q2) and
   shows the full path in a toast and on the expert screen.

### 8.3 D3: consent default focus

Decided as §6 rules 1–4. Initial focus is Cancel. Affirming needs a move plus
Enter (2 keys). The affirmative names the act. Neutral primary styling. The
order is after validation. Per attempt, never saved. The prototype asserts
default focus `dlg_no` on every dialog in every measured journey.

---

## 9. Projected keystrokes

Counting rules are the same as 02. Every press counts. Typed characters count
1 each. Arrow mode navigates Select overlays with arrows. Type-ahead mode types
the shortest unique prefix first. KLM uses K = 0.2 s and M = 1.35 s, with the
**same M operators as the baseline** (no credit taken for decisions the design
removes, except J3's "re-pick dims", which becomes "verify restored values").
R is excluded. The sequences were **driven and asserted on the prototype with
Pilot at both 80x24 and 120x40**. Counts were identical at both sizes
(`keystrokes.json`). Same demo file (`data/autobench_demo.csv`, 7 entities).

| Journey | Baseline keys (arrow) | Baseline KLM s | **Projected keys (arrow)** | **Projected KLM s** | Δ keys | Type-ahead: baseline → projected |
|---|---:|---:|---:|---:|---:|---|
| J1 Share, typed path | 49 | 20.6 | **40** | **18.8** | −9 (−18%) | 43 → 34 |
| J1 Share, Tab only (no step-jump keys) | 49 | 20.6 | 42 | 19.2 | −7 | — |
| J1 Share, path suggestion (`d` →) | — | — | 19 | 14.6 | −30 vs typed baseline | — |
| J1 Share via `^O` picker | 27 | 16.2 | **18** | **14.4** | −9 (−33%) | 21 → — |
| J2 Rate, approval | 78 | 26.4 | **53** | **21.4** | −25 (−32%) | 66 → 45 |
| J2 Rate, fraud (clearing-spend attestation) | 90 | 31.5 | **62** | **25.9** | −28 (−31%) | 70 → 51 |
| J2 Rate, fraud + accuracy_first | 96 | 35.4 | **68** | **29.8** | −28 (−29%) | 76 → 57 |
| J3 Re-run after restart, change preset | 61 | 20.3 | **41** | **16.3** | −20 (−33%) | 58 → 33 |
| J3b Re-run in the same process, change preset | 17 | 7.5 | **8** | **5.7** | −9 (−53%) | — |

Counted sequences (arrow mode; `×n` = repeated; `type(n)` = n printable
characters):

```text
J1    type(23) enter | enter down×7 enter | f4 | down×2 space down space | ctrl+r                     = 40
        load (focus jumps to Target) | Target | jump to Dimensions | card_type, input_mode | run
J1-tab type(23) enter | enter down×7 enter | tab×3 | down×2 space down space | ctrl+r                   = 42
J1-sug type(1) right enter | enter down×7 enter | f4 | down×2 space down space | ctrl+r                  = 19
J1-pkr ctrl+o enter | enter down×7 enter | f4 | down×2 space down space | ctrl+r                        = 18
J2    type(23) enter | enter down×7 enter | tab right | tab enter down×2 enter | tab enter down×3 enter
        | f4 | down×2 space down space | ctrl+r                                                         = 53
J2f   … approved | tab enter down×4 enter (fraud) | f4 | dims | ctrl+r | tab enter (attest)             = 62
J2af  … fraud | f5 enter down enter (low_distortion) | f4 | dims | ctrl+r | tab enter (consent)
        | tab enter (attest)                                                                           = 68
J3    type(23) enter | enter down×7 enter | f5 enter down×4 enter | ctrl+r                             = 41
        (mode, metric, dims, preset restored after the load; Target is never restored)
J3b   f5 enter down×4 enter | ctrl+r                                                                  = 8
```

Where the savings come from (each row checked against the baseline sequences in 02):

| Saving | Mechanism | J1 | J2 fraud | J3 |
|---|---|---:|---:|---:|
| Focus moves to Target after a load (baseline `tab×2`) | §4.3 rule 2 | −2 | −2 | −2 |
| Step-jump key to the field (F4 → first blocker, F5 → preset) instead of Tab walks through dead stops | §4.1, §4.3 | −6 | −5 | −2 |
| Dimension list hides role columns (card_type is row 2, not 3) | §2.2 | −1 | −1 | — |
| Mode is the first stop of step 3 (baseline `shift+tab×13 right` → `tab right`) | §2.1 | — | −12 | — |
| Rate selects list numeric columns only (approved −5, fraud −5) | §2.2 | — | −10 | — |
| Total has no smart default (Q4) | §2.2 | — | +1 | — |
| Dimensions restored after the load (baseline re-picks: `shift+tab×10` + 6) | §8.1 | — | — | −16 |
| Attestation needs a move before Enter (D3) | §6 | — | +1 | — |
| **Total** | | **−9** | **−28** | **−20** |

Not counted: J4b validation recovery drops from `escape tab×5 ctrl+u type(23) enter`
(31 keys) to `escape enter` (2 keys), because focus returns to the kept path
(§4.3 rule 8). Rate's Total has no smart default (Q4). That costs 1 key over
"default txn_cnt then down 1", and it is already in the J2 numbers.

---

## 10. Open questions for the repo owner

1. **Core cooperative cancel (Q1).** May Phase 3 add an optional, additive
   `cancel_requested` callable (and a phase callback for exact stage 4
   progress) to the shared run seam, checked at core's phase boundaries and
   before `output`? Without it, cancel stops runs only before the engine.
2. **Override file location (Q2).** `PresetWorkflow.write_override_file` and
   `export_override_file` write to the CWD (01 E.18). May they take a
   directory argument (non-behavioural core change), or should the TUI only
   delete the temp file after each run?
3. **Restoring privacy release mode and preset (Q3).** Today both carry over
   between sessions. This spec keeps that and makes it visible (`↺`). Should
   Verified safe coverage instead reset to Complete output on each launch?
4. **Rate Total default (Q4).** Drop the `txn_cnt` smart default so the
   clearing-spend basis is always an explicit choice?
5. **Balanced-CSV default (Q5).** Share on, rate off, CLI off. Should all
   three be aligned to off?
6. **Sweep in rate mode after VSC (Q6).** Confirm that rate requests should
   send the sweep value shown, unlocked, rather than today's leftover lock
   (01 E.6).
7. **Step keys (Q7).** Are F2–F6 reliable on the analysts' terminals
   (PuTTY/Citrix)? If not, which fallback do you prefer: `Alt+1…5` or
   palette-only?
