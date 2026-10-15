# TUI Redesign Phase 0 — 01 Widget / Field Inventory

Scope: `tui_app.py` at the current working tree (2659 lines), Textual 7.5.0.
Evidence only: no code was changed. Line references are `tui_app.py:N` unless
another file is named. Headless measurements came from Pilot probes
(`app.run_test(size=...)`, using `screen._compositor.visible_widgets`) run with
an isolated `HOME`, telemetry disabled, and no repo writes.

## Summary

**Totals (main screen, `BenchmarkApp.compose()` at 853–1107)**

| Measure | Count |
|---|---|
| Interactive widgets, all (incl. 2 tabs, 2 collapsible toggles) | **59** |
| Value-bearing fields (Input/Select/Checkbox/SelectionList) | **50** |
| Buttons | 5 (`btn_browse_csv`, `btn_preset_help`, `btn_apply_advanced`, `btn_export_advanced`, `btn_run`) |
| Displayed at first launch (share tab, both collapsibles collapsed) | 27 |
| Visible without scrolling at **120x40** | **11** (10 fully, `validate_input` partly) |
| Visible without scrolling at **80x24** | **4** (`btn_browse_csv`, `csv_path`, `entity_col`, `entity_name`) |
| Config pane: virtual height / viewport height (120x40) | 113 / 38 rows (203 with both collapsibles open) |
| `btn_run` position | y=110 in the scroll pane: off-screen at both sizes |

Per section (interactive widgets): 1 Data Source 2 · 2 Entity 2 · 3 Analysis
Options 12 · Compliance Declarations 1 toggle + 2 · Advanced Optimization
1 toggle + 19 fields + 2 buttons · 4 Analysis Mode 2 tabs + Share 6 + Rate 9 ·
Run button 1.

**The 5 most important findings**

1. **Ctrl+A and Ctrl+E do nothing at launch.** Focus starts on `csv_path`
   (1138), and Textual's `Input` binds `ctrl+a`→`home` and `ctrl+e`→`end`. With
   focus there the probe saw no app bindings for those keys, the Footer showed only
   4 keys, and pressing Ctrl+A did not toggle `#advanced_opt`. The startup toast
   (1139–1144) and README.md:350–351 still advertise both keys.
   *Implication:* shortcuts have to work no matter which widget has focus.
2. **A stale advanced-override file silently beats a later preset change,
   including its compliance posture.** `advanced_config_path` is reset only in
   `load_presets` (1765). Changing the preset (2188–2196) refreshes the
   `adv_*` widgets, but the old override YAML, written with the *old* preset's
   `compliance_posture` (1888–1900, `core/preset_workflow.py:30`), is still sent as
   `config` (2293). Probe: apply on `low_distortion` → switch to
   `compliance_strict` → widgets show tolerance 0.0, file still has 10.0 and
   posture `accuracy_first`. Because `config` is set, the TUI also skips the
   posture lookup and the accuracy_first consent modal (2304–2319), so core
   fails with `RunBlocked` (`core/analysis_run.py:1240–1246`). The opposite
   order applies a `strict` posture to an accuracy_first preset without saying so.
   *Implication:* the effective posture and override source must be visible and
   reset when the preset changes.
3. **Privacy and compliance controls are below the fold or collapsed.** At
   120x40, `privacy_release_mode`, `privacy_rule_sweep_mode`,
   `privacy_merchant_spend_scope`, the Share/Rate tabs and `btn_run` all need
   scrolling. The Citi declarations sit in a Collapsible that starts collapsed
   (944) and are not displayed at launch. The merchant-spend declaration
   (936–939) is in a different section from the other declarations.
   *Implication:* declarations need one explicit location that is always visible.
4. **Duplicate and inert output controls.** `share_debug`/`rate_debug` always
   send a bool `debug`, which maps to `output.include_debug_sheets`
   (`utils/config_manager.py:641`, CLI overrides have the highest priority:
   `config_manager.py:330–333`). So `adv_output_debug_sheets` (1028) never takes
   effect. `adv_output_privacy_validation` (1029) is redundant whenever debug is
   on (`core/analysis_run.py:1070,1079`). `include_calculated` (903) only acts
   when balanced CSV export is on (`core/analysis_run.py:3297`,
   `core/balanced_export.py:391`). `fraud_in_bps` (1081) only acts on the
   publication workbook (`core/output_artifacts.py:397–431`), and the default
   output format is `analysis`.
   *Implication:* each output concept should have exactly one control and show
   what it depends on.
5. **Most session "restore" is a no-op, but privacy release mode *is* restored.**
   The column Selects and SelectionLists in `SESSION_SELECT_IDS` and
   `SESSION_SELECTION_LIST_IDS` (114–143) are restored at mount before any CSV
   has loaded, so the value setters fail silently (1264–1267, 1287–1293).
   The probe confirmed `entity_col`, `share_metric` and `share_dims` come back
   empty. Meanwhile `privacy_release_mode` (VSC) and the locked sweep checkbox
   *are* restored from the previous session (1277–1278), and so is the preset
   (and with it the posture). Attestations, by contrast, are deliberately not
   restored (125–128).
   *Implication:* the redesign should decide on purpose which privacy choices may
   carry over between sessions, and show them when they do.

---

## A. Main screen inventory (`BenchmarkApp.compose`, 853–1107)

Legend. **Vis**: where and when the widget is shown. "Launch-120" / "Launch-80" means
visible without scrolling at that size. **Feeds**: the `values[...]` key in
`run_analysis` (2288–2373), which goes to `AnalysisRunRequest.from_widget_values`
(`core/contracts.py:805`). From there it becomes a config path via `build_run_config`
(`core/analysis_run.py:637`) and `ConfigManager._apply_cli_overrides`
(`utils/config_manager.py:638–669`).

### A.1 Section "1 · Data Source" (864–870)

| id | type | label / text | default | vis | feeds (downstream) | CLI |
|---|---|---|---|---|---|---|
| `btn_browse_csv` | Button | "Browse…" | — | always; Launch-120, Launch-80 | opens `CsvPickerScreen` (1939, 1952–1961), sets `csv_path` and loads headers | — |
| `csv_path` | Input | label "CSV file path"; placeholder "path/to/data.csv" | "" (initial focus 1138) | always; Launch-120, Launch-80 | `csv` (2271–2274, 2289); blur/Enter loads headers (1726–1744) and repopulates 10 widgets (1642–1656) | `--csv` (benchmark.py:80, required) |
| `csv_meta` | Static | "No file loaded." → "✓ file · N columns · size + 6-column preview" (1696) | — | always | informational | — |

### A.2 Section "2 · Entity" (872–880)

| id | type | label | default | vis | feeds | CLI |
|---|---|---|---|---|---|---|
| `entity_col` | Select | "Entity ID column" | blank; smart default `issuer_name` after CSV load (1660) | always; Launch-120, Launch-80 | `entity_col` (2278–2279, falls back to `"issuer_name"`) → `input.entity_col` (config_manager.py:639); a change loads unique values into `entity_name` (2178–2180, 2147–2170, reading the full column from the CSV) | `--entity-col` (benchmark.py:102, default issuer_name) |
| `entity_name` | Select (allow_blank) | "Target entity (blank = peer-only)" | blank | always; Launch-120, Launch-80 | `entity` (2276–2277); resolved in core (`core/analysis_run.py` `resolve_target_entity`) | `--entity` (benchmark.py:101) |

### A.3 Section "3 · Analysis Options" (882–939)

| id | type | label | default | vis | feeds | CLI |
|---|---|---|---|---|---|---|
| `time_col` | Select (allow_blank) | "Time period column (optional)" | blank | always; Launch-120 | `time_col` (2283–2284) → `input.time_col` (config_manager.py:640) | `--time-col` (benchmark.py:109) |
| `output_file` | Input | "Output filename"; placeholder "Auto-generated if blank" | "" | always; Launch-120 | `output` (2282, 2294) | `--output/-o` (benchmark.py:103) |
| `preset_select` | Select | "Optimization preset" | `compliance_strict` (`DEFAULT_PRESET_NAME`, core/contracts.py:13; 1756–1761) | always; Launch-120 | `preset` (2280–2281); also sets `compliance_posture` from preset YAML when no override file (2304–2310); refreshes adv widgets (2190), blurb (2191) and release mode (2193) | `--preset` (benchmark.py:112) |
| `btn_preset_help` | Button | "Preset Guide" | — | always; Launch-120 | opens `PresetHelpScreen` (1945–1946) | `config list/show` (benchmark.py:320–326) |
| `preset_blurb` | Static | preset YAML `description` (1771–1783) | compliance_strict description | always | informational | — |
| `analyze_distortion` | Checkbox | "Analyze impact" | **True** | always; Launch-120 | `analyze_distortion` (2298) → `output.include_impact_summary` (config_manager.py:659; analysis_run.py:647–650) | `--analyze-impact` (benchmark.py:152); `--analyze-distortion` deprecated alias (153) |
| `compare_presets` | Checkbox | "Compare presets" | False | always; Launch-120 | `compare_presets` (2299) → `output.include_preset_comparison` (config_manager.py:658) | `--compare-presets` (benchmark.py:151) |
| `validate_input` | Checkbox | "Validate input" | True | always; Launch-120 (partly) | `validate_input` (2297) → `input.validate_input` (config_manager.py:657); also gates the TUI pre-run validation + `ValidationModal` (2404–2451) | `--validate-input` / `--no-validate-input` (benchmark.py:154, 161) |
| `include_calculated` | Checkbox | "Include calc. metrics (CSV)" | False | always | `include_calculated` (2300) → `output.include_calculated_metrics` (config_manager.py:662); used only in balanced CSV export (analysis_run.py:2120, 2157) | `--include-calculated` (benchmark.py:194) |
| `output_format` | Select | "Output format": Analysis / Publication / Both | `analysis` | always | `output_format` (2301) → `output.output_format` (config_manager.py:661); chooses the workbooks written (core/output_artifacts.py:386–392) | `--output-format` (benchmark.py:181), `--publication-format` (187) |
| `privacy_release_mode_label` | Label | "Privacy release mode" | — | **share tab only** (2052–2067) | — | — |
| `privacy_release_mode` | Select | "Complete output" / "Verified safe coverage" (489–492) | `complete-output` | **share tab only**; refreshed from preset/override config (2097–2123) | share: `privacy_release_mode` enum (2044–2045); rate: forced `None` (2046–2049). Precedence: request → YAML → default (core/analysis_run.py resolve_privacy_release_mode). VSC locks sweep on (2069–2086) and needs global weights + sweep (analysis_run.py:1350–1366) | `--privacy-release-mode` (benchmark.py:269, share only) |
| `privacy_release_mode_hint` | Static | "Verified safe coverage publishes only verified safe units. Missing units are privacy-suppressed. Coverage is not a maximum claim." | — | share tab only; shown even when Complete output is selected | informational | — |
| `privacy_rule_sweep_mode` | Checkbox | "Privacy rule sweep mode" | False | always (both tabs); **disabled + forced True while VSC is selected** (2075–2079) | `privacy_rule_strategy` = `SWEEP_ANY_APPLICABLE` or `SELECT_BY_PEER_COUNT` (2026–2030) → `_fit_privacy_strategy` (analysis_run.py:360, 2591); sets the run-status mode label to "privacy-sweep" (1383, 1397) | `--privacy-rule-sweep` (benchmark.py:81; core/contracts.py:800–801) |
| `privacy_merchant_spend_scope` | Checkbox | "Anonymized aggregated merchant-spend context (enables 4/35)" | False; **never restored** (125–128) | always | `is_anonymized_aggregated_merchant_spend` (2031–2034) → `analysis.merchant_mode` override + `merchant_spend_scope` (analysis_run.py:2409–2412, 2483–2489) | `--anonymized-aggregated-merchant-spend` (benchmark.py:86) |

### A.4 Collapsible "Compliance Declarations" (944–954), `collapsed=True`

| id | type | label | default | vis | feeds | CLI |
|---|---|---|---|---|---|---|
| (title) | CollapsibleTitle | "Compliance Declarations" | collapsed | below the fold at 120x40 | toggles | — |
| — | Label | "Citi Privacy Overlay" (946) | — | when expanded | — | — |
| `citi_competitor_receives_output` | Checkbox | "A Citi competitor receives the output" | False; **never restored** | when expanded (not displayed at launch) | `citi_competitor_receives_output` (2039–2042) → Citi ≤25% overlay (analysis_run.py:307–330, 485, 1524); without a name it raises ValueError (analysis_run.py:227–230) **after data load**, with no TUI pre-check | `--citi-competitor-receives-output` (benchmark.py:96) |
| `citibank_entity_name` | Input | placeholder "Exact Citibank entity name (required for Citi overlay)" | ""; **never restored** | when expanded | `citibank_entity_name` (2035–2038); must exactly match one governed peer (analysis_run.py:231–246). Free text, although `entity_name` already lists every entity value | `--citibank-entity-name` (benchmark.py:92) |

### A.5 Collapsible "Advanced Optimization Parameters" (959–1034), `collapsed=True`

Every `adv_*` field is filled from `ConfigManager(preset).config` (1832–1872) and
mapped by `utils/config_overrides.py:22–47`. "Apply Overrides" writes a temp YAML
containing `compliance_posture` (1881–1913, `core/preset_workflow.py:26–40`, written
to the **CWD**), which is sent as `config` (2293). Nothing reaches the run until
Apply or Export has been pressed. "Presets" = how many of the 6 `presets/*.yaml`
set the key explicitly. Where a preset is silent, the ConfigManager defaults
(`utils/config_manager.py:493–545`) fill the widget, except where noted.

| id | type | label | config path | presets | CLI |
|---|---|---|---|---|---|
| `adv_lp_tolerance` | Input | "Tolerance (pp)" | optimization.linear_programming.tolerance | 6/6 | none (config only) |
| `adv_lp_max_iterations` | Input | "Max Iterations" | optimization.linear_programming.max_iterations | 6/6 | none |
| `adv_lp_lambda_penalty` | Input | "Lambda Penalty" | optimization.linear_programming.lambda_penalty | 3/6, no default → **blank** for compliance_strict / balanced_default / research_exploratory | none |
| `adv_lp_volume_weighting_exponent` | Input | "Volume Weighting Exponent" | …linear_programming.volume_weighting_exponent | 3/6, blank otherwise | none |
| `adv_lp_volume_weighted_penalties` | Checkbox | "Enable Volume-Weighted Penalties" | …linear_programming.volume_weighted_penalties (`always_write`) | 3/6. Defaults to False, and Apply writes an explicit `false` | none |
| `adv_constraints_volume_preservation` | Input | "Volume Preservation" (placeholder "0.0 - 1.0") | optimization.constraints.volume_preservation | 6/6 | none |
| `adv_bounds_min_weight` | Input | "Min Weight" | optimization.bounds.min_weight | 6/6 | none |
| `adv_bounds_max_weight` | Input | "Max Weight" | optimization.bounds.max_weight | 6/6 | none |
| `adv_subset_enabled` | Checkbox | "Enable Subset Search" | optimization.subset_search.enabled | 6/6 | `--auto-subset-search` (benchmark.py:195) |
| `adv_subset_strategy` | Input (free text) | "Strategy"; placeholder "greedy / random" | optimization.subset_search.strategy | 6/6 | none |
| `adv_subset_max_attempts` | Input | "Max Attempts" | optimization.subset_search.max_attempts (reads `max_tests` alias) | 6/6 | `--subset-search-max-tests` (benchmark.py:196) |
| `adv_subset_max_slack_threshold` | Input | "Max Slack Threshold" | optimization.subset_search.max_slack_threshold | 6/6 | `--max-cap-slack` (benchmark.py:198) |
| `adv_subset_trigger_on_slack` | Checkbox | "Trigger on Slack" | optimization.subset_search.trigger_on_slack | 6/6 | `--trigger-subset-on-slack` (benchmark.py:197) |
| `adv_subset_prefer_slacks_first` | Checkbox | "Prefer Slacks First" | optimization.subset_search.prefer_slacks_first | 6/6 | none |
| `adv_bayes_max_iterations` | Input | "Max Iterations" (second widget with this label; see C.9) | optimization.bayesian.max_iterations | 6/6 | none |
| `adv_bayes_learning_rate` | Input | "Learning Rate" | optimization.bayesian.learning_rate | 6/6 | none |
| `adv_analysis_bic_percentile` | Input | "Best-in-Class Percentile" | analysis.best_in_class_percentile | 6/6 (all 0.85) | none |
| `adv_output_debug_sheets` | Checkbox | "Include Debug Sheets" | output.include_debug_sheets | 6/6 (all true) | `--debug`, but **always overridden by `share_debug`/`rate_debug`** (C.1) |
| `adv_output_privacy_validation` | Checkbox | "Include Privacy Validation" | output.include_privacy_validation | 0/6 (default True) | none |
| `btn_apply_advanced` | Button | "Apply Overrides" | writes override YAML (1947–1948, 1881) | — | `--config` (benchmark.py:110) |
| `btn_export_advanced` | Button | "Export Config" | writes `exported_<preset>_overrides.yaml` to the CWD (2233–2251, preset_workflow.py:42–51) | — | `config generate` (benchmark.py:336) |
| — | Label | "Values override preset when applied." (1034) | — | — | — |

Group labels (`adv-group-title`): Linear Programming, Constraints, Weight
Bounds, Subset Search, Bayesian Optimization (Fallback), Analysis Settings,
Output Settings (961–1026).

### A.6 Section "4 · Analysis Mode" (1039–1084): TabbedContent, initial `share_tab`

The active tab *is* the analysis mode (`_analysis_mode`, 1987–1992). Tabs are
below the fold at both sizes.

**Share tab** (`share_tab`, 1042–1058)

| id | type | label | default | vis | feeds | CLI |
|---|---|---|---|---|---|---|
| `share_metric` | Select | "Primary metric column" | smart default `txn_cnt` (1661) | share tab | `metric` (2322–2326, **required**) | `share --metric` (benchmark.py:265, required) |
| `share_secondary` | SelectionList (h=7) | "Secondary metrics (optional)" | none; excludes the primary (2182–2183) | share tab | `secondary_metrics` (2327–2328) | `--secondary-metrics` (benchmark.py:267) |
| `share_auto_dim` | Checkbox | "Auto-detect dimensions" | False | share tab | `auto` (2329) → `analysis.auto_detect_dimensions` (config_manager.py:651); hides `share_dims` (2131–2137) | `--auto` (benchmark.py:107) |
| `share_debug` | Checkbox | "Debug sheets" | **True** | share tab | `debug` (2338) → `output.include_debug_sheets` (config_manager.py:641); analysis_run.py:2490 | `--debug` (benchmark.py:135) |
| `share_export_csv` | Checkbox | "Export balanced CSV" | **True** | share tab | `export_balanced_csv` (2339); written only if privacy-authorized (analysis_run.py:3296–3299) | `--export-balanced-csv` (benchmark.py:143, default False) |
| `share_dims_label` | Label | "Manual dimension selection" | — | hidden when auto | — | — |
| `share_dims` | SelectionList (h=7) | — | none | share tab, hidden when auto | `dimensions` (2330–2337); at least one, or auto, is **required** (2331–2336) | `--dimensions` (benchmark.py:106) |
| (hard-coded) | — | — | — | — | `per_dimension_weights=False` (2342–2346) | `--per-dimension-weights` (benchmark.py:137), not exposed |

**Rate tab** (`rate_tab`, 1060–1084)

| id | type | label | default | vis | feeds | CLI |
|---|---|---|---|---|---|---|
| `rate_total` | Select | "Total column (denominator)" | smart default `txn_cnt` | rate tab | `total_col` (2348–2352, **required**); also the clearing-spend modal (2376–2383) | `rate --total-col` (benchmark.py:294) |
| `rate_approved` | Select (allow_blank) | "Approved column" | smart default `app_cnt` if present | rate tab | `approved_col` (2353–2354); approved or fraud is **required** (2357–2359) | `--approved-col` (benchmark.py:298) |
| `rate_fraud` | Select (allow_blank) | "Fraud column" | blank | rate tab | `fraud_col` (2355–2356); triggers `ClearingSpendConfirmScreen` on every run (2376–2383) | `--fraud-col` (benchmark.py:300) |
| `rate_secondary` | SelectionList | "Secondary metrics (optional)" | none; excludes total (2185–2186) | rate tab | `secondary_metrics` (2360–2361) | `--secondary-metrics` (benchmark.py:296) |
| `rate_auto_dim` | Checkbox | "Auto-detect dimensions" | False | rate tab | `auto` (2362) | `--auto` |
| `rate_debug` | Checkbox | "Debug sheets" | True | rate tab | `debug` (2371) | `--debug` |
| `rate_export_csv` | Checkbox | "Export balanced CSV" | **False** (share default is True) | rate tab | `export_balanced_csv` (2372) | `--export-balanced-csv` |
| `fraud_in_bps` | Checkbox | "Fraud in BPS" | True | rate tab | `fraud_in_bps` (2373) → `extra_config_overrides` (analysis_run.py:3472) → publication workbook only (output_artifacts.py:397–431) | `--fraud-in-bps` / `--no-fraud-in-bps` (benchmark.py:302, 305) |
| `rate_dims_label` / `rate_dims` | Label / SelectionList | "Manual dimension selection" | none | hidden when auto (2139–2145) | `dimensions` (2363–2370, required unless auto) | `--dimensions` |

### A.7 Run button and activity pane (1086–1105)

| id | type | text | notes |
|---|---|---|---|
| `btn_run` | Button | "▶  Run Analysis"; "Validating…" / "Running…"; "▶  Run Privacy Sweep" after a run if sweep is on (1419, 1436) | at y=110 in the scroll pane, off-screen at launch. The label is **not** updated when the sweep checkbox is toggled (probe: still "Run Analysis"), only after a run ends or resets |
| `run_status` | Static, border "Run Status" | badge + Mode + Preset (+ Elapsed) (1349–1371) | refreshed on tab and preset change |
| `results_panel` | Static, border "Last Run" | "No runs yet." → verdict, report paths, VSC coverage facts, withheld status (2565–2615) | max-height 14 |
| `log_output` | Log, border "Execution Log" | max 2000 lines (1103) | Ctrl+L clears it |
| Header | Header | "Privacy-Compliant Peer Benchmark" / "Control 3.2 dimensional analysis" (850–851, 857) | no clock |
| Footer | Footer | shows bindings where `show=True` | see B |

### A.8 TUI fields with no widget, and CLI flags the TUI cannot reach

- `TUI_UNSUPPORTED_FIELDS` (480–487): `lean`, `audit_package`, `validate_export`,
  `report_format` (plus `df`, `prepared_dataset`). CLI: `--lean` (benchmark.py:145),
  `--audit-package` (144), `--validate-export` (162), `--report-format` (175).
- `compliance_posture`: no widget. It comes from the preset YAML (2309–2310) or the
  override file. CLI: `--compliance-posture` (benchmark.py:120).
- `acknowledge_accuracy_first`: no widget. Set by the consent modal (2313–2319). CLI:
  `--acknowledge-accuracy-first` (benchmark.py:125).
- `log_level`: hard-coded "INFO" (2296). CLI: `--log-level` (136).
- `per_dimension_weights`: hard-coded False for share (2342), defaults to False for rate.
- An arbitrary `--config` YAML cannot be loaded. The only `config` source is the
  generated override file.

---

## B. Bindings and Footer

| Scope | Key | Action | Footer shows | Notes |
|---|---|---|---|---|
| App (501–508) | ctrl+o | open_file ("Open CSV") | yes | |
| App | ctrl+r | run_analysis ("Run") | yes | the only way to run without scrolling to `btn_run` |
| App | f1 | show_help ("Preset Guide") | yes | |
| App | ctrl+a | toggle_advanced ("Advanced") | **only when no Input is focused** | shadowed by `Input` `ctrl+a`→home. Initial focus is an Input (1138), so the key is dead at launch (probe) |
| App | ctrl+e | export_advanced ("Export Adv") | **only when no Input is focused** | shadowed by `Input` `ctrl+e`→end. Also expands, applies and exports in one go (2220–2231), which creates an override file |
| App | ctrl+l | clear_log ("Clear Log") | yes | |
| Textual default | ctrl+q | quit → overridden `action_quit` (1971–1985): confirms if a run is active, saves the session | **no** (show=False) | the Footer offers no visible Quit |
| Textual default | ctrl+p | command palette | no | |
| `CsvPickerScreen` (238) | escape | cancel_picker | — | hint label "Enter to select · Escape to cancel" (257–260) |
| `ConfirmScreen` (281) | escape | cancel_confirm → False | — | inherited by `ClearingSpendConfirmScreen` |
| `PresetHelpScreen` (316) | escape | close_help | — | |
| `ValidationModal` (396) | escape | cancel_validation → False | — | False emits `action_cancelled` telemetry (1187–1189) |

Footer at launch (focus on `csv_path`), probe at 120x40 and 80x24: `ctrl+o Open
CSV · ctrl+r Run · f1 Preset Guide · ctrl+l Clear Log`. The mount toast lists
all six keys (1139–1144). README.md:347–351 lists five, without Ctrl+L.

---

## C. Modal screens

| Screen | Widgets (id, type, label, default) | Opened by | Effect downstream |
|---|---|---|---|
| `CsvPickerScreen` (235–275) | `picker_title` Label "Select a CSV file"; `picker_quick_list` ListView of `*.csv`, `data/*.csv`, `tests/fixtures/*.csv` (1592–1600); `picker_tree` CsvDirectoryTree at CWD (dirs + .csv only, 221–232); `btn_picker_cancel` Button "Cancel" | `btn_browse_csv`, ctrl+o | sets `csv_path` + `load_csv_headers` (1955–1959) |
| `ConfirmScreen` (278–299) | `confirm_message` Label; `btn_confirm_yes` Button (variant **error**, label varies); `btn_confirm_no` "Cancel" | (a) quit during a run (1979–1982, "Quit"); (b) **accuracy_first consent** (1457–1482, "I understand — proceed") | (b) sets `acknowledge_accuracy_first=True` (2319). **Privacy-critical**: per-run, never persisted. Only reached when no override file is in use (2304) |
| `ClearingSpendConfirmScreen` (302–310) | same as ConfirmScreen; message "Confirm clearing-spend basis … Total column `X` …"; button "Confirm" | every rate run with `fraud_col` (2376–2383) | sets `_fraud_confirmation_source="tui_modal"` → `fraud_privacy_evidence` metadata (analysis_run.py:2066–2075). **Privacy-critical attestation** |
| `PresetHelpScreen` (313–390) | Label "Preset Guide"; `help_text` Markdown (hard-coded text for 6 presets, 349–382); `btn_close_help` "Close" | `btn_preset_help`, f1 | informational. Text differs from the preset YAML (C.7) |
| `ValidationModal` (393–441) | `validation_title` "Data Validation Results"; error/warning count Labels; `issue_list` ListView (up to 10 row indices per issue); `btn_proceed` "Proceed" (disabled if errors); `btn_cancel` "Cancel" | `validate_input` on, with issues present (2436–2451) | Proceed → `run_analysis(confirmed=True)` unless `should_abort` (1184) |

Toasts (`notify`) carry real state as well: CSV loaded, advanced overrides
applied with their file name, preset refresh, release-mode fallback (1313–1319),
"Publication Withheld" (2603–2609).

---

## D. Classification

Frequency: **E** = every run, **S** = sometimes, **X** = expert. **PC** = privacy
or compliance-critical: it must stay explicit and visible in any redesign.

| Field | Class | PC | Reason grounded in code |
|---|---|---|---|
| `csv_path` (+ Browse) | E | | required by preflight (2272–2274) and never restored from the session (1251–1253) |
| `entity_col` | E | | has a smart default (`issuer_name`, 1660) and a fallback (2279), but defines the peer population |
| `entity_name` | E | | chosen each run (blank means peer-only); never restored; drives the output file name |
| `preset_select` | E | **PC** | defaults to compliance_strict (1756). Decides `compliance_posture` (2309), which can trigger consent (2313) or labelled non-compliant output (2311–2312). 4 of 6 presets are not `strict` |
| Share/Rate tab | E | | the tab *is* the mode (1987–1992). Today it sits below the fold |
| `share_metric` / `rate_total` | E | | required by preflight (2324–2326 / 2350–2352); has a smart default |
| `rate_approved` / `rate_fraud` | E (rate) | fraud: **PC** | at least one is required (2357–2359); fraud triggers the clearing-spend attestation (2376–2383) |
| `share_dims`/`rate_dims` or `*_auto_dim` | E | | one of the two is required (2331–2336 / 2364–2369) |
| `privacy_release_mode` | S | **PC** | share only (2044–2049); defaults to complete-output; locks sweep (2075–2079); is restored from the session (1277) |
| `privacy_rule_sweep_mode` | S | **PC** | changes the rule strategy (2026–2030); forced on by VSC |
| `privacy_merchant_spend_scope` | S | **PC** | per-run declaration, never restored (125–128); enables 4/35 (analysis_run.py:2409–2412) |
| `citi_competitor_receives_output` | S | **PC** | per-run declaration, never restored; enforces the ≤25% overlay |
| `citibank_entity_name` | S | **PC** | required when the box above is checked (analysis_run.py:227–230); must match exactly (231–246) |
| accuracy_first consent modal | S | **PC** | required by core (analysis_run.py:1240–1246); only shown when no override file is in use (2304) |
| clearing-spend modal | S | **PC** | per fraud run (2376–2383) |
| `output_format` | S | (publication is the client-facing output) | default `analysis`; selects which workbooks are written (output_artifacts.py:386–392) |
| `time_col` | S | | optional (label says so); a blank is valid |
| `output_file` | S | | auto-generated if blank (890) |
| `share_secondary` / `rate_secondary` | S | | optional; the label says so |
| `share_export_csv` / `rate_export_csv` | S | | gated by privacy authorization (analysis_run.py:3296–3299); defaults differ between tabs |
| `validate_input` | S | (data-quality gate) | default on, matching the config default (config_manager.py:453); turning it off skips the pre-run modal |
| `analyze_distortion` | S | | default on (matches config default `include_impact_summary: True`, config_manager.py:476) |
| `compare_presets` | S | | default off; reruns every preset (output.include_preset_comparison) |
| `share_debug` / `rate_debug` | X | | default True, and all 6 presets already set `include_debug_sheets: true`; only affects debug and diagnostic sheets (analysis_run.py:1070–1079, 2490) |
| `fraud_in_bps` | X | | only affects the publication workbook (output_artifacts.py:397) and needs a fraud column |
| `include_calculated` | X | | only acts on balanced CSV export (analysis_run.py:2120, 2157) |
| all `adv_*` inputs and checkboxes | X | | preset-provided (presets fill 16 of 19 for every preset; see A.5); no CLI flag for 14 of 19; inert until Apply is pressed (1881) |
| `adv_output_debug_sheets` | X (inert) | | always overridden by `share_debug`/`rate_debug` (C.1) |
| `btn_apply_advanced` / `btn_export_advanced` | X | posture side-effect | write YAML with a posture taken from the preset (1888–1900) |
| `btn_preset_help` | S | | informational |

---

## E. Redundancies and inconsistencies

Each entry gives the evidence followed by a one-line *implication*.

1. **Debug sheets set in two places, one of them inert.** `share_debug`/`rate_debug`
   (1054, 1079) always send a bool `debug` → `output.include_debug_sheets`
   (config_manager.py:641), and CLI overrides outrank the config file
   (config_manager.py:330–333). `adv_output_debug_sheets` (1028) is overwritten
   whenever an override file is applied. *Implication:* keep one control.
2. **Privacy validation sheet is coupled to debug.** `include_privacy_validation
   or debug_mode` (analysis_run.py:1070, 1079), so `adv_output_privacy_validation`
   is inert while debug is on (the default). *Implication:* show the dependency or
   merge the two.
3. **Stale override file survives preset changes and carries a posture** (Finding 2;
   2188–2196, 1765, 2293, 2304). Probe-confirmed. *Implication:* show which
   preset and posture are effective, and invalidate the override when the preset
   changes.
4. **Consent is skipped when an override file is in use.** The posture/consent
   branch only runs when `preset and not values["config"]` (2304). If the
   override declares `accuracy_first`, core blocks the run (analysis_run.py:1240–1246)
   and the operator is never asked. *Implication:* derive consent from the resolved
   posture, not from the preset YAML alone.
5. **Shortcuts are shadowed by Input focus** (Finding 1). *Implication:* fix the
   binding precedence, or use keys the Input does not own, before advertising them.
6. **Sweep stays locked on the rate tab when VSC was chosen on share.** Probe: after
   choosing VSC and switching to rate, `privacy_release_mode` is hidden and sent
   as `None` (2046–2049), yet `privacy_rule_sweep_mode` stays `value=True,
   disabled=True`, and the rate request is sent with `SWEEP_ANY_APPLICABLE`.
   `_sync_privacy_release_mode_visibility` (2052–2067) does not re-run the coupling.
   *Implication:* a control hidden on one tab should not lock a control on another.
7. **Release-mode hint is shown in Complete-output mode.** The hint (924–930) always
   describes VSC behaviour. *Implication:* the hint should match the selected mode.
8. **Run button label lags behind the sweep checkbox.** The label switches to "Run
   Privacy Sweep" only in `_end_run_ui`/`_reset_run_ui` (1419, 1436), and
   `on_checkbox_changed` (2129–2145) ignores the sweep box. Probe-confirmed.
   *Implication:* the primary action should always say what will run.
9. **Duplicate and ambiguous labels.** Two "Max Iterations" inputs (967 LP, 1014
   Bayesian), told apart only by group headings. "Analyze impact" feeds
   `analyze_distortion` (899, 2298), while the CLI calls the flag `--analyze-impact`
   and marks `--analyze-distortion` deprecated (benchmark.py:152–153). "Debug
   sheets" in the tabs vs "Include Debug Sheets" in Advanced. "Validate input" vs
   CLI `--no-validate-input`. *Implication:* use one vocabulary that matches the
   CLI and README.
10. **Balanced-CSV defaults differ by tab, and the CLI differs again.** Share
    `share_export_csv=True` (1055), rate `rate_export_csv=False` (1080), CLI
    `--export-balanced-csv` defaults to False (benchmark.py:143).
    *Implication:* align the defaults, or explain why they differ.
11. **Fields that are visible but inert in some modes.** `include_calculated`
    (shared section, 903) has no effect unless the active tab's export box is
    checked. `fraud_in_bps` has no effect unless `output_format` ∈
    {publication, both} *and* a fraud column is set. Its label says neither.
    *Implication:* show dependent options next to the option they depend on.
12. **Declarations are split and hidden.** Merchant-spend (936) is in "Analysis
    Options". The Citi declarations are in a separate Collapsible that starts
    collapsed (944). The Collapsible is titled "Compliance Declarations" but
    holds only Citi. *Implication:* put all declarations in one location that is
    always visible.
13. **Citibank name is free text** (951–954), although `entity_name` already
    lists every exact entity value (2147–2170). A mismatch only fails after
    data load inside core (analysis_run.py:231–246). The Citi checkbox with an
    empty name also fails only in core (227–230). *Implication:* check this before
    the run, or pick the name from the loaded values.
14. **Session restore is mostly inert, yet restores privacy mode** (Finding 5).
    Probe: `entity_col`, `share_metric`, `share_dims` come back empty;
    `preset_select`, `output_format`, `share_debug` and the VSC + locked sweep
    *are* restored. *Implication:* declare which settings persist, and show any
    privacy-relevant carry-over.
15. **Preset guide text disagrees with the preset YAML.** `PresetHelpScreen` says
    low_distortion means "low distortion while keeping privacy constraints"
    (366–369), while `presets/low_distortion.yaml` says "even at the cost of some
    privacy violations" and `compliance_posture: accuracy_first`. The guide never
    mentions postures or consent, and duplicates the YAML `description` that
    `preset_blurb` already shows (1771–1783). *Implication:* generate guide text
    from the preset data.
16. **Advanced fields go blank for some presets.** `adv_lp_lambda_penalty` and
    `adv_lp_volume_weighting_exponent` are empty for 3 of 6 presets, because the
    ConfigManager defaults lack these keys. `adv_lp_volume_weighted_penalties`
    shows False and Apply writes it as an explicit `false` (`always_write`,
    config_overrides.py:27). *Implication:* a blank field looks like "unset" but
    actually means "engine default".
17. **Free-text enum.** `adv_subset_strategy` is an `Input` with placeholder
    "greedy / random" (999) and no validation in the TUI. *Implication:* use a
    constrained choice.
18. **Override and export files land in the CWD.** Temp override files go to
    `dir="."` and are never cleaned up (preset_workflow.py:31–37); exports go to
    `exported_<preset>_overrides.yaml` in the CWD (preset_workflow.py:48). Ctrl+E
    creates both. In a repo checkout these are generated artifacts that AGENTS.md
    says must not be committed. *Implication:* write them to an output directory.
19. **Layout overflows at 80x24.** `config_pane` min-width 64 plus `activity_pane`
    min-width 42 gives 106 columns (518–521, 626–629). Probe: `app_body` virtual
    width is 106 at 80 columns, so the activity pane starts at x=64 and is mostly
    clipped. *Implication:* narrow terminals need a single-column or tabbed layout.
20. **The primary action is off-screen.** `btn_run` is at y=110 of a pane 113 rows
    tall, with a 38-row viewport at 120x40. README step 6 still says "Click Run
    Analysis" (README.md:343). Ctrl+R is the only run path visible at launch.
    *Implication:* keep the run action and its preconditions visible at all times.
21. **The Footer has no Quit.** ctrl+q quit is hidden (show=False). The app's
    `action_quit` (1971) protects running jobs, but nothing advertises it.
    *Implication:* list Quit in the Footer.
22. **Every confirm uses a red "error" button** (292), including the consent and
    attestation affirmations. *Implication:* style destructive actions differently
    from attestations.
23. **README shortcut list is incomplete** (README.md:347–351 omits Ctrl+L), and its
    Browse description ("current directory and `data/`") omits `tests/fixtures`
    (1594). *Implication:* derive the docs from `BINDINGS`.

---

## Appendix: probe method

The scripts are in the session scratchpad, not the repo:
`visibility_probe.py`, `behavior_probe.py`, `layout_probe.py`. They were run as
`HOME=<scratch>/home AUTOBENCH_TELEMETRY=0 AUTOBENCH_LOG_DIR=<scratch>/logs
uv run python <script>` from the repo root. "Visible" means present in
`screen._compositor.visible_widgets` after a 0.3–0.5 s pause. "Fully visible"
means the widget region is contained in its clip. Override files written during
the probe were redirected to the scratchpad by monkeypatching
`PresetWorkflow.write_override_file`.
