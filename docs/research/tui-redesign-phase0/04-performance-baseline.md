# TUI Redesign Phase 0: Performance Baseline

**Scope:** what the current `tui_app.py` costs at runtime (revision `ddea32c`, Textual 7.5.0), measured headlessly with the reusable probe `scripts/tui_perf_probe.py`. `tui_app.py` and `core/` were not changed.

**Machine:** 4 vCPU, Intel Xeon @ 2.80 GHz (shared cloud VM), Linux 6.18, Python 3.13.16, pandas 2.3.3, Textual 7.5.0, terminal 120x40. The numbers only make sense relative to this machine. The VM is noisy: startup varies about 2.5x between identical runs, so compare medians and re-run the baseline on the same box before comparing.

## Headline

| Area | Baseline (median / worst) | What causes it |
|---|---|---|
| Cold `import tui_app` | **1.40 s** / 1.51 s | `core.analysis_run` takes 0.81 s, of which `scipy.stats` is 0.45 s through `core.privacy_coverage_solver`. pandas takes 0.45 s. |
| Startup to idle | **1.3–3.1 s** / 3.3 s | Compose/mount and CSS of about 233 widgets. Presets are parsed 4 times. |
| Longest UI freeze at startup | **0.74–2.4 s** | Mount and stylesheet application all happen in one block. |
| Entity column change, 1M rows | **0.60–0.92 s** freeze | `load_unique_entities` runs synchronous `pd.read_csv(usecols=…)` on the UI thread. |
| Tab out of `#csv_path`, 1M rows | **0.8–1.5 s** | The blur handler re-reads the headers and resets `entity_col`, which re-reads the whole entity column. |
| Tab between other fields | **20–350 ms** | `.form-section:focus-within` restyle plus Footer recompose on every focus change. |
| Typing in an Input | **4–6 ms** | Fine. |
| Ctrl+A (Advanced) | **0.20–0.48 s** | `ConfigManager` re-parses all presets on every expand. |
| Ctrl+O picker, 2000 CSVs in cwd | **5.5–7 s** freeze (200 files: 0.66 s) | One `ListItem` widget per quick-pick file, plus 2000 tree nodes populated on the UI thread. |
| 5000 log lines from a worker | **4–9 s** to drain | `LogHandler` batching does not work: one `call_from_thread` round-trip per record (2008 flushes for 2000 records). |

## Summary table (metric × dataset)

Each cell is the median / max of 3 fresh app sessions. Columns are rows / distinct entities. Entity columns are `issuer_name` (default, prefix `ENT_`) and `alt_entity` (`ALT_`). CSV sizes are 0.7 MB, 7 MB and 70–74 MB. Units are `*_s` in seconds and `*_ms` in milliseconds.

| metric | 10k / 50 | 10k / 5000 | 100k / 50 | 100k / 5000 | 1M / 50 | 1M / 5000 |
|---|---|---|---|---|---|---|
| `import_s` (subprocess) | 1.40 / 1.51 | (same) | (same) | (same) | (same) | (same) |
| `startup_idle_s` | 2.64 / 3.22 | 2.35 / 2.94 | 1.26 / 1.51 | 1.66 / 2.72 | 3.12 / 3.25 | 2.48 / 3.32 |
| `startup_stall_max_ms` | 1336 / 1485 | 1609 / 1628 | 741 / 823 | 955 / 2211 | 2431 / 2653 | 1753 / 1775 |
| `csv_headers_ready_s` | 0.03 / 0.04 | 0.03 / 0.04 | 0.02 / 0.02 | 0.02 / 0.07 | 0.03 / 0.07 | 0.02 / 0.04 |
| `csv_entities_ready_s` | 0.11 / 0.14 | 0.15 / 0.16 | 0.18 / 0.33 | 0.14 / 0.23 | 0.71 / 0.86 | 1.06 / 1.21 |
| `csv_stall_max_ms` | 58 / 80 | 75 / 88 | 80 / 224 | 104 / 114 | 635 / 747 | 942 / 1073 |
| `entity_change_s` | 0.02 / 0.05 | 0.08 / 0.09 | 0.11 / 0.14 | 0.08 / 0.08 | 0.60 / 0.72 | 0.92 / 1.20 |
| `entity_change_stall_max_ms` | 11 / 39 | 37 / 51 | 107 / 129 | 78 / 92 | 602 / 715 | 917 / 1191 |
| `key_latency_p50_ms` | 54 / 86 | 92 / 120 | 44 / 53 | 23 / 27 | 24 / 26 | 48 / 103 |
| `key_latency_p95_ms` | 346 / 509 | 219 / 503 | 647 / 1593 | 1467 / 1597 | 842 / 848 | 1099 / 1507 |
| `key_stall_max_ms` | 256 / 431 | 102 / 468 | 567 / 1440 | 1272 / 1504 | 591 / 619 | 821 / 1198 |
| `advanced_expand_s` | 0.20 / 0.25 | 0.33 / 0.72 | 0.45 / 1.89 | 0.26 / 0.47 | 0.29 / 0.78 | 0.48 / 1.00 |
| `picker_open_s` (2000 files) | 0.54 / 0.81 | 0.83 / 0.84 | 0.75 / 0.91 | 0.68 / 0.72 | 0.84 / 0.99 | 0.94 / 1.22 |

The picker and log-flood costs do not depend on the dataset. They were measured separately with 3 repeats each (`picker_log_{200,2000}.json`):

| metric | 200 files in cwd | 2000 files in cwd |
|---|---|---|
| `picker_open_s` (modal screen active) | 0.03 / 0.04 | 0.73 / 1.62 |
| `picker_tree_ready_s` (DirectoryTree populated) | 0.27 / 0.32 | 3.63 / 4.27 |
| `picker_stall_max_ms` | 664 / 978 | **5574 / 6877** |
| `log_flood_s` (5000 records from a thread) | 3.90 / 6.76 | 6.64 / 8.73 |
| `log_flood_stall_max_ms` | 25 / 50 | 49 / 1019 |

Notes on the numbers:

- **Key latency** is the time from posting a key event until every message pump (app, screens, widgets) has an empty queue. The probe does not use `pilot.press()`/`pilot.pause()`, because those add a harness floor of at least 40 ms per key (two `wait_for_idle` sleeps of 20 ms or more, plus a `_wait_for_screen` round-trip over every widget). The sequence is 6× Tab from `#csv_path`, 6 typed characters plus Backspace in `#output_file`, and 2× Shift+Tab. On 1M-row data, p95 and max are always the Tab out of `#csv_path`. Typing never exceeds about 6 ms when the machine is quiet.
- **Stall** is how late an asyncio task that sleeps 5 ms wakes up. It is the longest stretch during which the UI could not repaint or take input.
- **Row count:** the CSV and entity paths scale linearly with rows. At 1M rows they cost 0.6–1.2 s whatever the cardinality. Cardinality adds roughly 0.1–0.3 s at 5000 options (sorting plus `Select.set_options`).
- **Startup** does not depend on the dataset (no CSV is loaded at startup). The spread across columns is VM noise.
- The `log_flood_stall_max_ms` row in `baseline.json` is invalid: an early probe version had a `thread.join` bug, fixed before the separate run. The numbers above come from that re-run.

## Blocking-call audit (UI thread)

Every row runs on the Textual event-loop thread unless marked otherwise. Cost scaling: R = CSV rows, U = unique entities, C = CSV columns, P = preset files, F = entries in the cwd, L = log records, W = widgets.

| # | `tui_app.py:LINE` | Trigger | Blocking work | Scaling | Measured |
|---|---|---|---|---|---|
| 1 | `:2159` `load_unique_entities` | `on_select_changed` for `entity_col` (`:2179`). This fires on a manual change, when `load_csv_headers` auto-defaults `entity_col=issuer_name` (`:1668`), and when it re-asserts the previous value after `set_options` (`:1647`). | `pd.read_csv(path, usecols=[col])` reads the whole file, then `dropna().unique()`, `sorted()`, `Select.set_options`, and an `in` scan of a list (`:2166`). | O(R) I/O+parse, plus O(U log U), plus O(U) widget options | 1M rows: 0.6–1.2 s freeze. The profile shows `read_csv` at 0.62–0.81 s and `unique` at 0.1 s. |
| 2 | `:1731` `on_input_blurred` → `_try_load_csv_from_path_input` → `load_csv_headers` | **Every** focus change away from `#csv_path`, including plain Tab navigation | Re-reads the header (`pd.read_csv(nrows=0)`, `:1634`), repopulates 6 Selects and 4 SelectionLists, and re-sets `entity_col`, which re-runs #1 | O(C) + O(R) through #1 | 1M rows: Tab costs 0.8–1.5 s |
| 3 | `:1726` `on_input_submitted` → `load_csv_headers` `:1626` | Enter in `#csv_path`, or a file picked in the picker (`:1959`) | `os.path.isfile`, `pd.read_csv(nrows=0)`, `os.path.getsize` (`:1686`), widget repopulation in `batch_update` | O(C) (header only), plus #1 | Headers 20–70 ms. The first entity list arrives after 0.11 s (10k) and 1.06 s (1M). |
| 4 | `:1130` `on_mount` → `load_presets` `:1750` | Startup | `PresetWorkflow()` → `PresetManager._load_presets` globs and `yaml.safe_load`s every preset (`utils/preset_manager.py:43`) | O(P) YAML parses | About 40 ms per full parse with P=6 |
| 5 | `:1763` → `update_advanced_parameters` `:1849` → `_load_advanced_parameter_data` `:1832` | Startup, again on the deferred `preset_select` Changed (`:2190`), on every Ctrl+A expand (`:2215`), on Ctrl+E (`:2228`), and on every preset change | `ConfigManager(preset=…)` builds a **new** `PresetManager` (all presets re-parsed, `utils/config_manager.py:562`), then sets about 20 Inputs/Checkboxes | O(P) YAML per call | Startup has **4** full preset-directory parses (about 0.18 s in total). Ctrl+A takes 0.20–0.48 s. |
| 6 | `:1764`/`:2191` `_update_preset_blurb` | Startup and preset change | `load_preset_data` (cached in the workflow; cheap) | O(1) | negligible |
| 7 | `:2193` `_refresh_privacy_release_mode_from_config` | User-driven preset change; `apply_advanced_overrides` | `ConfigManager(config_file, preset).resolve()`: another full preset parse, plus reading the override file | O(P) | About 80 ms per call in the profile |
| 8 | `:1881` `apply_advanced_overrides` | "Apply Overrides" button, Ctrl+E | `write_override_file` (temp-file write), `_config_file_declares_privacy_release_mode` `:2088` (`open` + `yaml.safe_load` of that file), then possibly #7 | O(file) + O(P) | small, but synchronous disk I/O |
| 9 | `:2233` `export_advanced_overrides` | Ctrl+E, "Export Config" | `open` + `yaml.safe_load` of the temp file (`:2244`), then `export_override_file` writes a timestamped YAML | O(file) | small, but synchronous disk I/O |
| 10 | `:1236` `_restore_session` | Startup | `SESSION_FILE.is_file()` + `yaml.safe_load` + applying about 25 widget values | O(session) | small. On a slow `$HOME` (NFS) this is a synchronous stat and read. |
| 11 | `:1227` `_save_session` | Quit (`:1976`/`:1984`), and at every run start in `_begin_validation_ui`/`_begin_run_ui` (`:1391`/`:1405`) | `mkdir` + `yaml.safe_dump` | O(session) | small |
| 12 | `:1592` `_quick_pick_files` | Ctrl+O / Browse (`:1961`) | `glob.glob("*.csv")`, `data/*.csv`, `tests/fixtures/*.csv`, with an O(n) `match not in seen` **list** check per match | O(F²) in the worst case | Contributes to #13 |
| 13 | `:244` `CsvPickerScreen.compose` | Ctrl+O | One `FileListItem(Label)` **widget per quick-pick file** (no cap). Each widget's CSS is applied and laid out. | O(F) widgets | 2000 files: `compose` 1.65 s, then stylesheet/layout of the new widgets. **5.5–7 s freeze.** |
| 14 | `:256` `CsvDirectoryTree(os.getcwd())` | Ctrl+O | `iterdir` + `filter_paths` (`path.is_dir()` stat per entry, `:224`) run in a Textual thread worker (fine). `_populate_node` then runs on the UI thread with another `_safe_is_dir` stat per entry, plus one TreeNode per entry. | O(F) stats + nodes on the UI thread | Tree ready after 3.6 s at 2000 files |
| 15 | `:1113`–`:1148` `compose` + `on_mount` | Startup | About 233 widgets mounted at once (all tabs, collapsed Advanced and Compliance forms included). The stylesheet is applied to every widget, and a `notify` toast is shown. | O(W) | 0.74–2.4 s worst stall. Startup is dominated by Textual `Stylesheet.apply`/`get_rule` (about 0.8 s self time under the profiler). |
| 16 | `:534` CSS `.form-section:focus-within` (and `:613` `.multi-select:focus`) | Every focus change | `Screen._update_focus_styles` restyles each section's subtree. The Footer recomposes its key bindings. | O(W in section) | Tab costs 20–350 ms even without a CSV (profile: `set_focus` 0.42 s over 8 tabs, `FooterKey.update_node_styles` 0.25 s) |
| 17 | `:180` `LogHandler.emit` | Any `logging` call while the app is up (root handler, INFO) | In a worker thread it calls `app.call_from_thread(self._flush)`, which **blocks the emitting thread until the UI runs the flush**. The emitter cannot append while blocked, so each flush carries about 1 record and the batching never coalesces. On the UI thread it flushes synchronously. | O(L) UI round-trips | 2000 records → 2008 flushes. 5000 records take 4–9 s to drain and throttle the analysis worker. |
| 18 | `:146` `write_log_message` | Validation-modal cancel and other call sites | Unbatched `call_from_thread(log_widget.write)`. It blocks the caller the same way. | O(messages) | small in practice |
| 19 | `:2266`–`:2556` `run_analysis` worker | Ctrl+R | Runs in a thread worker (fine). It makes about 40 `call_from_thread(log_widget.write, …)` calls, each a blocking round-trip. `_execute_run_for_tui` (`:1512`) uses process-global `redirect_stdout`/`redirect_stderr` from a worker thread, so prints from other threads are captured too. | O(lines) | n/a (no analysis run in the probe) |
| 20 | `:1103` `Log(max_lines=2000, highlight=False)` | Long runs | Growth is bounded at 2000 lines and highlighting is off, so memory and re-render stay flat. Each `Log.write` still triggers `refresh`, `Text.render` and compositor work (top self time in the log profile is `rich.Text.render` at 1.7 s and `add_widget` at 1.4 s). | O(1) per line after the cap | No unbounded growth. The cost is per-write overhead, which #17 multiplies. |
| 21 | `:420` `ValidationModal.on_mount` | After validation, if there are issues | Appends one `ListItem` (plus a nested `Vertical`/`Label`) per issue | O(issues) widgets | not measured. Same pattern as #13. |
| 22 | `:1150` `on_unmount` | Quit | `finalize_deferred_logging` and telemetry `end_session()`, which waits up to `SHUTDOWN_BUDGET_S = 0.25 s` for its consumer thread | bounded 250 ms | acceptable |
| 23 | `:1146` `start_session`, `:1164` `surface_viewed` | Startup, tab switch | Enqueue only. A background consumer thread does the disk I/O. | O(1) | fine |
| 24 | `:1403` `set_interval(1.0, _refresh_run_status)` | During a run | A few `query_one` calls and a `Static.update` per second | O(1) | fine |

Not blocking: `run_analysis` itself (`@work(thread=True)`, `:2257`), DirectoryTree's directory read (thread worker), and telemetry writes (consumer thread).

## Profiler hotspots

pyinstrument 5.1.3 ran through `uv run --with pyinstrument` (an ephemeral overlay; the project `.venv` is untouched). Each phase was profiled in a separate, untimed session for 10k and 1M rows × 5000 entities. Profiles are in `…/scratchpad/perf/profiles/` as `*.txt` trees, `*_flat.txt` self-time listings and `*.html`.

**Import (`python -X importtime`, 1.53 s cumulative):**

| Module | Cumulative |
|---|---|
| `core.analysis_run` | 0.81 s |
| `core.privacy_coverage_solver` → `scipy.stats` | 0.45 s |
| `pandas` | 0.45 s |
| `core.dimensional_analyzer` → `core.solvers.lp_solver` → `scipy.optimize` | 0.28 s |
| `textual.app` | 0.17 s |

The TUI needs none of the solver modules until Run is pressed.

**Startup (about 3.1 s under the profiler):**

- Textual CSS takes most of the time: `Stylesheet.apply`/`RenderStyles.get_rule`/`ScalarProperty.__get__` about 0.8 s of self time, `Selector.check` 0.27 s, compositor `add_widget` 0.25 s.
- App code takes only about 0.3 s: `on_mount` → `load_presets` 0.29 s, of which `update_advanced_parameters` is 0.20 s. The deferred `on_select_changed(preset_select)` runs it again.
- `PresetManager._load_presets` appears 4×. YAML `compose_mapping_node` shows 0.21 s self.

**CSV load and entity change (1M × 5000):**

| Call | Time |
|---|---|
| `load_unique_entities` | 1.02 s |
| `pandas read_csv` (C parser `read`) | 0.81 s |
| `Series.unique` | 0.08–0.10 s |
| `dropna` | 0.05–0.08 s |
| `load_csv_headers` | 0.09 s |

The rest is widget repopulation.

**Keys (1M):**

| Call | Time |
|---|---|
| `Stylesheet.apply` (focus restyle) | 1.03 s |
| pandas C parser, from the `#csv_path` blur | 0.57 s |
| compositor `add_widget` | 0.45 s |
| `FooterKey` message loop and render | about 0.23 s |
| `Screen._update_focus_styles` within `set_focus` | 0.42 s over 8 tabs |

**Advanced (Ctrl+A):**

| Call | Time |
|---|---|
| `action_toggle_advanced` | 0.39 s |
| `update_advanced_parameters` | 0.14 s, of which `ConfigManager` → `PresetManager._load_presets` is 0.08 s |
| layout/restyle of the expanded form and the toast | remainder |

**Picker (2000 files):**

| Call | Time |
|---|---|
| `CsvPickerScreen.compose` (`FileListItem.__init__`) | 1.65 s |
| stylesheet self time | 3.7 s |
| `Stylesheet.apply` | 3.1 s |
| `replace_rules` | 2.9 s |
| `FileListItem._get_box_model` | 2.5 s |
| `arrange` | 1.9 s |

All of this comes from mounting 2000 ListItems.

**Log flood (2000 records):**

| Call | Time |
|---|---|
| `LogHandler._flush` | 1.5 s inclusive |
| `rich.Text.render` | 1.7 s self |
| compositor `add_widget` | 1.4 s |
| `Log.rich_style` | 0.6 s |

The cost is per-flush refresh work, repeated about 2000 times.

## Proposed Phase 1 budgets

These are the probe's `--budget` defaults (`DEFAULT_BUDGETS` in `scripts/tui_perf_probe.py`). Each one can be overridden with `--budget-<metric-with-dashes>`, and `0` disables a check. They are checked against the per-dataset median of at least 3 repeats on this class of machine. Use `--budget-stat max` for a stricter gate.

| Metric | Budget | Baseline (worst dataset median) | How Phase 1 gets there |
|---|---|---|---|
| `import_s` | ≤ 1.0 s | 1.40 s | Lazy-import `core.analysis_run` and the solver/scipy chain inside the run worker |
| `startup_idle_s` | ≤ 1.0 s | 1.26–3.12 s | Mount fewer widgets up front (compose collapsed and inactive-tab forms lazily); parse presets once |
| `startup_stall_max_ms` | ≤ 500 ms | 741–2431 ms | Same as above, plus moving preset/config parsing off `on_mount` |
| `csv_headers_ready_s` | ≤ 0.10 s | 0.02–0.03 s | Already fine. Keep the header read off the entity path. |
| `csv_stall_max_ms` | ≤ 100 ms at all sizes up to 1M rows | 942 ms | Entity values loaded in a thread worker; apply `set_options` once |
| `entity_change_s` (options ready) | ≤ 1.5 s at 1M rows | 0.92 s (worst run 1.20 s) | Can stay data-bound. This budget is a no-regression guard, not a goal. |
| `entity_change_stall_max_ms` | ≤ 100 ms | 917 ms | Worker plus cancellation of the previous load (`exclusive=True`) |
| `key_latency_p95_ms` | ≤ 100 ms | 1467 ms | Drop the reload-on-blur of `#csv_path` (or no-op it when the path is unchanged); scope `:focus-within` restyles to small containers |
| `key_latency_max_ms` | ≤ 250 ms | 1099–1593 ms | as above |
| `key_stall_max_ms` | ≤ 100 ms | 1272 ms | as above |
| `advanced_expand_s` | ≤ 0.15 s | 0.48 s | Cache resolved preset config per preset name; do not re-populate on every expand |
| `picker_open_s` (2000 files) | ≤ 0.2 s | 0.94 s | Cap quick picks (for example 50, most recent first) and use a set for de-duplication |
| `picker_stall_max_ms` (2000 files) | ≤ 250 ms | 5574 ms | Cap the quick picks; use `OptionList` instead of one `ListItem` widget per file |
| `log_flood_s` (5000 lines) | ≤ 1.0 s | 6.6 s | Non-blocking batching: append under the lock and schedule the flush with `call_soon_threadsafe` or a 50–100 ms `set_interval` drain, not a blocking `call_from_thread` |
| `log_flood_stall_max_ms` | ≤ 50 ms | 49 ms | Keep it there while fixing throughput |

Typing in an Input already costs 4–6 ms. Phase 1 must not regress it; it is covered by `key_latency_p50_ms`, which the probe reports but does not gate.

## Reproduce

All data and run directories live outside the repo. The probe refuses a `--data-dir` inside the repository. It sets `HOME`, `SESSION_FILE`, `AUTOBENCH_LOG_DIR` and the cwd to a throwaway directory and sets `AUTOBENCH_TELEMETRY=0`, mirroring `tests/test_tui_ux.py` and `tests/conftest.py`. Use `/usr/local/bin/uv`; the first `uv` on `PATH` is the wrong version.

```bash
P=/tmp/claude-0/-home-user-autobench/d13cb994-08e3-5f72-b4d1-86adf775fd7d/scratchpad/perf
cd "$P"

# 1. Full baseline (6 datasets x 3 repeats; about 15 min; synthetic CSVs cached in $P/data)
/usr/local/bin/uv run --project /home/user/autobench python /home/user/autobench/scripts/tui_perf_probe.py \
  --rows 10000 100000 1000000 --cardinality 50 5000 --repeat 3 \
  --data-dir "$P/data" --json-out "$P/baseline.json"

# 2. Picker scaling + log flood (dataset-independent)
for n in 200 2000; do
  /usr/local/bin/uv run --project /home/user/autobench python /home/user/autobench/scripts/tui_perf_probe.py \
    --rows 10000 --cardinality 50 --repeat 3 --data-dir "$P/data" --phases startup picker log \
    --no-import --picker-files $n --json-out "$P/picker_log_$n.json"
done

# 3. Per-phase profiles (extra untimed session; pyinstrument via ephemeral overlay)
/usr/local/bin/uv run --project /home/user/autobench --with pyinstrument python /home/user/autobench/scripts/tui_perf_probe.py \
  --rows 10000 1000000 --cardinality 5000 --repeat 1 --data-dir "$P/data" --no-import \
  --log-lines 2000 --profile-dir "$P/profiles"

# 4. Import breakdown
HOME=$P AUTOBENCH_TELEMETRY=0 /usr/local/bin/uv run --project /home/user/autobench \
  python -X importtime -c "import sys; sys.path.insert(0,'/home/user/autobench'); import tui_app" 2> "$P/importtime.txt"

# 5. Budget gate (exit 1 when exceeded; baseline currently fails 11 of 15 checks at 10k rows)
/usr/local/bin/uv run --project /home/user/autobench python /home/user/autobench/scripts/tui_perf_probe.py \
  --rows 10000 1000000 --cardinality 5000 --repeat 3 --data-dir "$P/data" --budget

# Compare against another worktree (e.g. the load_unique_entities fix):
#   ... scripts/tui_perf_probe.py --repo /path/to/other/worktree --json-out "$P/after.json" ...
```

Run artefacts: `baseline.json`, `baseline.out`, `picker_log_200.json`, `picker_log_2000.json`, `importtime.txt` and `profiles/` under `/tmp/claude-0/-home-user-autobench/d13cb994-08e3-5f72-b4d1-86adf775fd7d/scratchpad/perf/`.

### Probe design notes (for re-runs against a refactored TUI)

- The probe drives the app only through stable selectors (`#csv_path`, `#entity_col`, `#entity_name`, `#output_file`, `#advanced_opt`, `#btn_run`, `#log_output`) and real keys (Enter, Tab, Ctrl+A, Ctrl+O, Escape). If Ctrl+A is swallowed, it falls back to `run_action("toggle_advanced")`.
- Readiness is **polled**: it waits until `#entity_name` offers options with the expected prefix. The same measurement therefore works when loading moves into a worker. With `--csv` (a real file) it waits until the option set changes and is non-empty.
- If the redesign renames these IDs, update the selectors in `run_scenario` and keep the metric names, so the JSON stays comparable.
- The probe uses a few private Textual hooks (`_driver.send_message`, `message_queue_size`/`_next_callbacks`, `Select._options`), all guarded. Re-check them on a Textual upgrade.
