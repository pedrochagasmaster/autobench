# TUI Redesign Phase 1: 03 Performance Architecture

Phase 1 is a design spec. It changes no repo code. For each hotspot in
[Phase 0 04 Performance baseline](../tui-redesign-phase0/04-performance-baseline.md),
this document gives the architectural fix and a Textual 7.5 measurement that
shows the fix works. It ends with the final budgets for the probe's
`DEFAULT_BUDGETS` and a plan for wiring the probe into CI. Structure and flows
are in [01](01-interaction-design.md). Tokens, status and copy are in
[02](02-visual-system.md).

Line numbers refer to `tui_app.py` at `f6f47b6`.

**Machine and method.** Same class of VM as Phase 0: 4 vCPU shared, Python
3.13.16, Textual 7.5.0, pandas 2.3.3. The VM was quieter than during Phase 0.
Unmodified `tui_app.py` reached startup idle in 1.04–1.27 s here, against
1.3–3.1 s in 04. So **compare each fix with the `orig` row measured in the
same session**, not with the 04 table. Unless stated otherwise, cells are
medians over 3–6 fresh app sessions. Stall is the lateness of a 5 ms asyncio
sleeper, as defined by the probe. All prototypes reuse the probe's own
helpers (`settle`, `press`, `StallProbe`, `wait_until`) from
`scripts/tui_perf_probe.py`, so the numbers are comparable with 04.

| Prototype / benchmark | Path (scratchpad) |
|---|---|
| Import chain variants (repo copies) | `…/phase1-vs/repo_lazy/`, `repo_lazy_tui/`, `imp.py`, `who.py` |
| Deferred-import stall | `…/phase1-vs/bench_import_stall.py` |
| Startup variants of the real app (probe `--repo`) | `…/phase1-vs/make_variants.py` → `variants/M*`, results `probe_out/*.out` |
| Focus-change variants of the real app | `…/phase1-vs/bench_focus.py` → `focus.jsonl` |
| CSV tab-out guard | `…/phase1-vs/bench_csv_blur.py` |
| CSV picker | `…/phase1-vs/bench_picker.py` |
| Log handler | `…/phase1-vs/bench_log.py`, `bench_logwrite.py` |
| Entity picker at 10k/100k | `…/phase1-vs/bench_entity.py` (+ Phase 0 `…/perf/select_bench.py`) |
| Expert screen open | `…/phase1-vs/bench_expert.py` |
| Full test suite with the lazy `core/__init__` | `…/phase1-vs/repo_full/`, result `pytest_lazy_core.txt` |

`…` is `/tmp/claude-0/-home-user-autobench/d13cb994-08e3-5f72-b4d1-86adf775fd7d/scratchpad`.

## Decision summary

| Hotspot (04) | Fix | Measured effect (same-session medians) |
|---|---|---|
| Cold import 1.4 s | Load `core.analysis_run` on first use and pre-warm it in a thread after first paint. Optionally, make the `core/__init__` facade lazy. | import 1.32 → 0.96 s (TUI-only) → **0.62 s** (with the facade). Background pre-warm stalls the UI ≤ 87 ms. |
| Startup with 233 widgets, 4 preset parses | Mount only the active step. Expert settings is its own screen. Parse presets once. **Set the theme in `__init__`.** | idle 1.16 → **0.38 s**, stall 530 → **~215 ms**. The theme line alone: stall 530 → 278 ms. |
| Tab 20–350 ms | No `:focus-within` on large containers. An app-owned key bar instead of a recomposing `Footer`. | Tab p50 104 → **11 ms**, p95 313 → **44–55 ms** |
| `#csv_path` tab-out reload | Reload only when (realpath, mtime, size) changes | Tab-out at 1M rows 147 → 57 ms. With the focus fix: **11–18 ms**. Duplicate "CSV loaded" toasts gone. |
| Picker, 2,000 files | Capped quick picks, `OptionList`, directory scan in a thread worker | open-to-ready **9.2 s → 0.18 s**, stall 4.3 s → 0.12 s |
| LogHandler, 1 flush per record | Bounded buffer, one non-blocking `post_message` wake, drain on the UI thread | 5,000 records **3.4–5.4 s → 0.14–0.21 s**. The worker is no longer throttled. |
| `Select` with 10k–100k entities | Above 2,000 values: a filter `Input` + `SuggestFromList` + an `OptionList` capped at 200 | 100k: Select opens in 2.5–2.7 s with a 1.6 s stall. The filter peaks at **≤ 31 ms per key** with a ≤ 16 ms stall. |
| Worker reads widgets (D7) | A frozen `RunInputs` snapshot built on the UI thread. Dialogs run before the worker starts. | Rule + test (§7) |

**`core/` touches.** Only one is useful, and it is optional: a lazy
`core/__init__.py` facade, worth about 0.3 s of import time. It is
behaviour-neutral (§1.4), and the full test suite passes with it. Everything
else stays in the TUI layer. 02 suggests one more *additive* module
(`core/labels.py`, pure data). Engine-stage progress or cancel would need a
hook in `execute_run`. That is outside this plan (01 §7.2 limits cancel to
the stages before the engine).

---

## 1. Startup

### 1.1 Mount only what is visible

**Rule.** At launch the main screen mounts:
- the header and rail
- the **active step's form only**
- the action bar and key bar
- at ≥110 columns, the status column

Other steps mount the first time they are shown and stay mounted after that,
so switching back is free and widget state survives. Expert settings, Help,
the picker and every dialog are separate screens, composed when opened.

**Form state is not widget state.** A plain `FormState` dataclass on the app
is the single source of truth: every field's value, plus which CSV and entity
list it belongs to. Widgets write to it on `Changed` and read from it on
mount. The lazy mount needs this, and three other features need it too:
- **Review & run** (01 step 5) summarises steps that may never have been
  mounted.
- **Run gathering** (§7) reads the snapshot, not the widgets.
- **Session restore** (fixes D4) applies saved values to `FormState` before
  the CSV and widgets exist. A column choice is accepted once the header
  load confirms it.

**Measured** with the real app and the unchanged probe (`--phases startup
--no-import --repeat 3`, two rounds each). Each variant is a copy of
`tui_app.py` with one change applied (`make_variants.py`):

| Variant | Widgets mounted | `startup_idle_s` | `startup_stall_max_ms` |
|---|---|---|---|
| M0 today | 233 | 1.04–1.27 | 528–611 |
| M1 presets parsed once (§1.2) | 233 | 0.94–1.06 | 558–583 |
| M2 no Advanced form (Expert is a screen) | 163 | 0.72–0.75 | 353–441 |
| M3 = M2 + presets once | 163 | 0.70–0.71 | 416–436 |
| M4 = M3 + Rate tab and Compliance form not mounted (≈ "active step only") | 122 | 0.56–0.69 | 397–496 |
| M0b today + **theme set in `__init__`** | 233 | 0.84–0.89 | **277–280** |
| M5 = M4 + theme in `__init__` | 122 | 0.35–0.61 | 188–420 |
| **M6 = M5 + no launch toast** | **117** | **0.38–0.43** | **192–238** |

M4–M6 still mount the Data, Entity and Analysis sections together. The real
"active step only" design mounts fewer, so these numbers are an upper bound.

### 1.2 Parse presets once

Today `PresetManager._load_presets` runs four times at startup and again on
every Advanced expand. Each `ConfigManager(preset=…)` builds a fresh
`PresetManager` (`utils/config_manager.py:562`), and `load_presets`
constructs a new `PresetWorkflow` (`tui_app.py`, `load_presets`).

Fix (TUI only, no change to `utils/` or `core/`):

```python
class PresetCatalog:
    """One PresetWorkflow plus a memo of resolved preset configs, for display only."""

    def __init__(self) -> None:
        self.workflow = PresetWorkflow()            # one parse of presets/*.yaml
        self._resolved: dict[tuple[str, int], dict] = {}

    def resolved_config(self, preset: str) -> dict:
        key = (preset, _presets_dir_mtime_ns())     # an edited preset invalidates it
        if key not in self._resolved:
            self._resolved[key] = ConfigManager(preset=preset).config
        return copy.deepcopy(self._resolved[key])   # callers can't mutate the cache
```

- **Display only.** The run path is untouched. `build_run_config` inside the
  worker still builds a fresh `ConfigManager`, exactly as the CLI does, so
  what runs never comes from the cache.
- `_refresh_privacy_release_mode_from_config` (`ConfigManager(config_file,
  preset).resolve()`) gets the same memo, keyed by `(preset, override path,
  override mtime_ns, size)`. It moves to a worker, so the posture line can
  show `Resolving posture…` (01 §5.1).
- Measured: M1 vs M0 saves about 0.1 s of startup idle. The Expert screen no
  longer re-parses anything when it opens (§8, `expert_open_s`).

### 1.3 Theme assignment moves to `__init__`

`on_mount` sets `self.theme = "tokyo-night"` (`tui_app.py:1203`) after the
first stylesheet pass over all widgets, so the whole tree is restyled a
second time. Setting it in `__init__` (02 §1.3) costs nothing and is the
largest single startup win: **stall 528–611 → 277–280 ms** (M0 → M0b). It is
a one-line change that Phase 2 can ship first.

### 1.4 Defer `scipy`: what is safe without changing `core/` behaviour

**The chain.** `tui_app` imports `core.analysis_run` at module level
(`tui_app.py:62-70`). That pulls in `core.privacy_coverage_solver` →
`scipy.stats` (0.45 s) and the rest of the engine. Separately, **any**
`from core.x import …` first runs `core/__init__.py`. That file eagerly
imports `DimensionalAnalyzer` (→ `core.solvers.lp_solver` → `scipy.optimize`),
`PrivacyValidator`, `DataLoader` and `ReportGenerator` (`core/__init__.py:27-31`).
So a TUI-only lazy import still loads `scipy.optimize` *(verified with an
import tracer, `who.py`)*.

**Option A: TUI only (no `core/` diff).** Replace the
`from core.analysis_run import (…)` block with a locked accessor plus thin
module-level wrappers:

```python
_ANALYSIS_RUN = None
_ANALYSIS_RUN_LOCK = threading.Lock()

def _analysis_run():
    """core.analysis_run, imported on first use (pulls in scipy.stats)."""
    global _ANALYSIS_RUN
    with _ANALYSIS_RUN_LOCK:
        if _ANALYSIS_RUN is None:
            _ANALYSIS_RUN = importlib.import_module("core.analysis_run")
    return _ANALYSIS_RUN

def execute_run(*args, **kwargs):            # same for build_run_config,
    return _analysis_run().execute_run(*args, **kwargs)   # prepare_run_data, …
```

- The wrappers keep the module attributes `tui_app.prepare_run_data` and
  friends, so `monkeypatch.setattr(tui_app, "prepare_run_data", …)`
  (`tests/test_tui_ux.py`) keeps working.
- `except RunBlocked` becomes `except _analysis_run().RunBlocked`. An
  `except` expression is only evaluated when an exception propagates, and by
  then the module is loaded.
- **Test interaction.** `tests/telemetry/test_no_inline_imports.py` forbids
  `import` statements inside functions in `tui_app.py`. The accessor calls
  `importlib.import_module` rather than using an import statement, so it
  passes the AST check. That obeys the letter of the test, but the intent
  should be stated openly: the PR adds a comment and an explicit allow-list
  entry (`tui_app._analysis_run`) to that test, so the exception is reviewed
  rather than slipped past.

**Option B: also make the `core/__init__` facade lazy (a `core/` diff).**
`core/__init__.py` already has a PEP 562 `__getattr__` for
`execute_share_run` and `execute_rate_run`. That precedent exists because of
a circular import. Extend the same mechanism to the five heavy facade names:

```python
_LAZY_FACADE = {
    "evaluate_privacy_rule_sweep": "privacy_policy",
    "DimensionalAnalyzer": "dimensional_analyzer",
    "PrivacyValidator": "privacy_validator",
    "DataLoader": "data_loader",
    "ReportGenerator": "report_generator",
    "execute_rate_run": "analysis_run",
    "execute_share_run": "analysis_run",
}

def __getattr__(name):
    module_name = _LAZY_FACADE.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(f".{module_name}", __name__), name)
    globals()[name] = value
    return value
```

**Why B is behaviour-neutral.**
1. `from core import DataLoader`, `core.DataLoader` and `from core import *`
   (driven by the unchanged `__all__`) all still resolve, through
   `__getattr__`.
2. No code in `core/` or `utils/` is changed apart from *when* five modules
   load. `grep` finds no module-level side effects in those five modules that
   other code relies on (no registries, no global configuration).
3. The engine imports its own dependencies directly. `core.analysis_run`
   imports `core.dimensional_analyzer` and the rest by name, so a run loads
   exactly the same code.
4. **The full test suite passes** with the change applied to a scratch copy
   of the repository at `f29f85f` (`repo_full/`, `pytest_lazy_core.txt`):
   1,410 passed, 2 skipped, 2 failed. The 2 failures
   (`tests/test_production_scripts.py::test_publish_snapshot_script_*`) fail
   the same way with the **original** `core/__init__.py` and in the real
   checkout in this sandbox. They depend on git remote setup, not on this
   change.

It still counts as a `core/` change for review purposes. Ship it as its own
small PR, with a test that `import tui_app` does not load `scipy`.

**Measured** (cold `import tui_app` in a fresh subprocess, 6 runs each):

| Variant | `import_s` median (range) | Heavy modules loaded at import |
|---|---|---|
| today | 1.32 (1.18–1.47) | scipy, scipy.stats, scipy.optimize, pandas, numpy, core.analysis_run |
| A: TUI lazy `analysis_run` | 0.96 (0.87–1.16) | scipy, scipy.optimize, pandas, numpy |
| A + B: lazy facade too | **0.62** (0.56–0.69) | pandas, numpy |

`pandas` stays: the TUI reads CSV headers with it, and `utils.config_manager`
→ `core.compliance` imports it.

**Paying the deferred cost without a stall.** The first Run would otherwise
pay about 0.8 s of import on the worker thread. Pre-warm instead: one thread
worker, started from `call_after_refresh` after the first paint, calls
`_analysis_run()`. Measured with a running app and the stall probe
(`bench_import_stall.py`, 3 runs):

| Where the import runs | Import time | Max UI stall | p95 stall |
|---|---|---|---|
| UI thread | 0.82–0.98 s | **818–977 ms** | the same |
| Thread worker (pre-warm) | 0.80–0.87 s | **67–87 ms** | 5.5–6.2 ms |

The run worker always calls `_analysis_run()` first. If the pre-warm has not
finished, the lock makes the run wait for it, so the module is never imported
twice.

---

## 2. Focus-change cost (Tab 20–350 ms)

**Mechanism** (Textual 7.5 source, confirmed by the measurements below):

1. `Screen._update_focus_styles` (`textual/screen.py:1066`) walks from the
   screen down to the focused widget. At the **outermost** ancestor that has
   a `:focus-within` rule, it restyles that ancestor's **entire subtree**,
   for both the newly focused widget and the blurred one. With
   `.form-section:focus-within` (`tui_app.py:604`), every Tab restyles one or
   two whole sections.
2. `Footer.bindings_changed` (`textual/widgets/_footer.py:330`) runs
   `call_after_refresh(self.recompose)` on every focus change. The bindings
   signal fires whether or not the visible keys changed, and the footer
   rebuilds every `FooterKey`.

**Measured** with the real app, a 10k-row CSV loaded, starting on
`#entity_col`: 10 × Tab then 6 × Shift+Tab, latency = keypress to idle with
the probe's `press()`. Three sessions per cell. "today" is unmodified
`tui_app.py`. "M6" is the startup variant with 117 widgets.

| Variant | today p50 / p95 ms | M6 p50 / p95 ms | max stall (today / M6) |
|---|---|---|---|
| F0 as is | 104 / 313 | 89 / 373 | 231 / 177 |
| F1 no section `:focus-within` | 10 / 471 | 9 / 317 | 198 / 40 |
| F2 `:focus-within` scoped to the 2-widget `.field-pair` | 11 / 251 | 11 / 386 | 165 / 53 |
| F3 Footer removed | 39 / 188 | 40 / 174 | 155 / 140 |
| F4 = F1 + F3 | 12 / 47 | 9 / 47 | 34 / 31 |
| **F5 = F2 + F3** (scoped focus marker, no Footer) | 15 / 50 | 9 / 56 | 37 / 40 |
| **F6 = F2 + app-owned static key bar** | **12 / 44** | **11 / 55** | 33 / 51 |
| F7 = F2 + `StableFooter` (recompose only if the visible key set changed) | 13 / 95 | 11 / 113 | 45 / 47 |

**Findings.**
- Both causes must go. Either fix alone leaves p95 at 170–470 ms. The section
  restyle drives p50, and the Footer recompose drives the tail.
- A scoped `:focus-within` (02 §4.4: `.ab-field:focus-within > .ab-label`)
  costs the same as none at all, because the restyled subtree is two or
  three widgets. **Rule:** `:focus-within` only on containers with ≤ 5
  descendants. Never on a step, a section, a pane or a screen.
- **Recommendation: an app-owned `KeyBar`** (F6). 01 §4.4 already defines the
  footer as a fixed string per context, so a `Static` that is updated only
  when the context changes renders that table directly. Keys stay clickable
  through `[@click=app.<action>]` content actions. Bindings stay real
  `Binding`s with `show=False`.
- `StableFooter` (F7) is the fallback if the stock `Footer` look is wanted.
  It recomposes only when the visible key set changes (text field ↔ Select ↔
  list), and those context changes are its p95 (95–113 ms, at the edge of
  the budget).

```python
class StableFooter(Footer):
    _signature = None
    def bindings_changed(self, screen):
        sig = tuple((key, b.action, b.description, enabled)
                    for key, (_, b, enabled, _tip) in screen.active_bindings.items() if b.show)
        if sig == self._signature:
            self._bindings_ready = True
            return
        self._signature = sig
        super().bindings_changed(screen)
```

---

## 3. CSV path: reload only when the file changed

Today every blur of `#csv_path` re-reads the header, repopulates 6 Selects
and 4 SelectionLists, and toasts "CSV loaded" again (`on_input_blurred` →
`_try_load_csv_from_path_input` → `load_csv_headers`).

**Rule.** After a successful load, store
`signature = (os.path.realpath(path), st_mtime_ns, st_size)`, one `stat()`.
On blur (and on Enter), compute the signature of the stripped input. If it
equals the stored one, do nothing: no read, no repopulation, no toast. Enter
on an unchanged path is also a no-op, apart from moving focus to Target
entity (01 §4.3). The palette's **Reload current CSV** forces a reload. The
same stripped, resolved path feeds both the header load and the entity
worker, which fixes D8 (raw `#csv_path` text vs `_resolve_csv_path`).

**Measured** (`bench_csv_blur.py`: load once, then 4 × focus `#csv_path` → Tab,
waiting for any background entity reload to finish). Two sessions per row:

| Data | Variant | Tab-out median / max ms | Stall median ms | Toasts after 4 Tab-outs |
|---|---|---|---|---|
| 1M rows × 5,000 entities | today | 147 / 258 | 47–54 | 4–6 |
| 1M rows × 5,000 entities | guard | 57 / 171 | 24–29 | 2 |
| 1M rows × 5,000 entities | **guard + focus fix (F4)** | **11–18 / 28** | **9** | 2 |
| 10k rows × 50 entities | today | 118–171 / 242 | 43 | 6 |
| 10k rows × 50 entities | guard + focus fix | 16–21 / 29 | 6–13 | 2 |

Since the Phase 0 entity-worker fix, the blur no longer freezes for 0.8–1.5 s
(the reload of entity values is a no-op when they are already loaded). What
was left was header repopulation plus the focus-change cost. With both
removed, Tab out of the path costs the same as any other Tab.

---

## 4. CSV picker

**Design.**
1. **Quick picks** come from the same globs, de-duplicated with a `set`
   (today's `match not in seen` list check is O(F²)), sorted by mtime newest
   first, **capped at 50**. A count line reads `Recent (50 of 2,003)`. The
   filter box below covers the rest.
2. **One `OptionList`** per list. It renders only the visible lines, so it is
   virtualised. There is no `ListItem` widget per file.
3. **Browse** is a second `OptionList` holding the current directory
   (`▸ subdir/` entries first, then `*.csv`), with `..` to go up. A thread
   worker (`@work(thread=True, exclusive=True, group="browse")`) does one
   `os.scandir()` and uses `DirEntry.is_dir(follow_symlinks=False)`, which
   costs no extra `stat` on Linux because the type comes from `d_type`. It
   hands back a list of `Option`s, and the UI applies one `set_options()`.
   Enter on a directory starts the worker for that directory, and
   `exclusive=True` discards a stale scan.
4. A **filter `Input`** at the top narrows both lists (substring, casefolded).
   The 01 picker footer `↑↓ Move ↵ Open Tab List/browse Esc Cancel` applies.

`DirectoryTree` is dropped. It populates its nodes on the UI thread with a
`stat` per entry (04 #14). A flat list per directory is also easier to drive
with the keyboard.

**Measured** with 2,003 entries in the cwd (`bench_picker.py`, the Phase 0
`picker_2000` fixture, 3 sessions each). "Open to ready" runs from the start
of quick-pick collection until the screen is idle with both lists populated:

| Variant | Quick-pick rows | Widgets on the picker screen | Open to ready (s) | Max stall (ms) |
|---|---|---|---|---|
| P0 today (`ListView` of `FileListItem` + `CsvDirectoryTree`) | 2,000 | 4,011 | 8.96–9.49 | 4,122–4,403 |
| P1 `OptionList` (uncapped) + `CsvDirectoryTree` | 2,000 | 11 | 0.38–0.44 | 144–191 |
| **P2 capped `OptionList` + threaded `OptionList` browse** | 50 | 11 | **0.18–0.22** | **116–154** |

Swapping one `ListItem` per file for an `OptionList` is about 95% of the win.
The cap and the threaded scan bring it under the 0.2 s budget.

---

## 5. Log

### 5.1 The batching fix

Today `LogHandler.emit` appends a record, and if no flush is pending it calls
`app.call_from_thread(self._flush)`. `call_from_thread` **blocks the emitting
worker** until the UI has run the flush, so the buffer never holds more than
about one record. 2,000 records cause about 2,000 round-trips, and the
analysis worker is throttled by the UI.

**Fix.** A `RunLog(Log)` widget owns a bounded, thread-safe pending buffer:

```python
class RunLog(Log):
    class Wake(Message): ...

    def __init__(self, **kw):
        super().__init__(max_lines=MAX_VIEW_LINES, highlight=False, **kw)
        self._pending = collections.deque(maxlen=MAX_VIEW_LINES)  # bounded even if the UI stalls
        self._dropped = 0
        self._lock = threading.Lock()
        self._wake_posted = False

    def enqueue(self, line: str) -> None:            # any thread, never blocks on the UI
        with self._lock:
            if len(self._pending) == self._pending.maxlen:
                self._dropped += 1
            self._pending.append(line)
            if self._wake_posted:
                return
            self._wake_posted = True
        self.post_message(self.Wake())               # thread-safe: call_soon_threadsafe

    def on_run_log_wake(self, _):                    # UI thread
        with self._lock:
            lines, self._pending = list(self._pending), collections.deque(maxlen=MAX_VIEW_LINES)
            dropped, self._dropped, self._wake_posted = self._dropped, 0, False
        if dropped:
            lines.insert(0, f"… {dropped} earlier lines not shown (full log on disk)\n")
        if lines:
            self.write("".join(lines))
```

- `MessagePump.post_message` is thread-safe and non-blocking in Textual 7.5
  (`message_pump.py:873-876` uses `loop.call_soon_threadsafe`).
- The logging handler becomes a one-liner: `log.enqueue(self.format(record) + "\n")`.
- `write_log_message` and the roughly 40 `call_from_thread(log_widget.write, …)`
  calls in the run worker all become `run_log.enqueue(…)`.

**Measured** (`bench_log.py`, 5,000 records from a worker thread, 3 sessions):

| Variant | Drain until visible (s) | Worker blocked (s) | Max stall (ms) |
|---|---|---|---|
| L0 today (`tui_app.LogHandler`) | 3.41–5.39 | 3.40–5.38 | 78–96 |
| **L1 bounded buffer + `post_message` wake** | **0.14–0.21** | **0.11–0.16** | 54–116 |
| L2 bounded buffer + 50 ms `set_interval` drain | 0.21–0.28 | 0.11–0.13 | 77–121 |
| L3 = L1 with 256-line chunks re-posted via `call_later` | 0.18–0.21 | 0.13–0.16 | 165–203 |
| L9 handler only formats (GIL floor, no UI work) | 0.07 | 0.07 | 7 |

The remaining stall is `Log.write` itself, which is linear at about 16 µs
per line (`bench_logwrite.py`):

| Lines per write | 1 | 64 | 256 | 1,000 | 2,000 | 5,000 |
|---|---|---|---|---|---|---|
| `Log.write` (ms) | 0.3 | 1.7 | 4.0 | 14.5 | 31.2 | 81.0 |

The bounded buffer caps a single write at `MAX_VIEW_LINES` (about 31 ms).
Chunking (L3) was slower, because every chunk pays a refresh and compositor
pass. A real run interleaves logging with computation, so the flood is a
worst case. L1 is the design.

### 5.2 Bounds

| Thing | Bound | Why |
|---|---|---|
| Visible log | `max_lines = 2000` per run (unchanged) | Memory and render cost stay flat |
| Pending buffer | `deque(maxlen=2000)`, plus a "… N earlier lines not shown" marker | A stalled UI can't grow memory without limit |
| Earlier runs | The last **5** runs, each a list of ≤ 2,000 lines, in memory only | 01's "Earlier runs" without unbounded growth. About 1 MB at 100 bytes per line. |
| Full record | The existing deferred log file on disk (`setup_deferred_logging`), unchanged | The view is a window. The file is the record, and it follows the privacy quarantine rules. |

### 5.3 The run-log view

- **Where.** It is a view, not a pane. It lives in the status/results area
  (≥110: the lower part of the status column; <110: `Show run log` from
  Results, 01 §3.3). It is never a Tab stop in the setup form (02 friction
  #11).
- **Line format.** `HH:MM:SS ␣ glyph ␣ message`: `Formatter("%(asctime)s %(levelglyph)s %(message)s",
  datefmt="%H:%M:%S")`. The level glyph is `·` for INFO, `▲` for WARNING,
  `✗` for ERROR and above (02 §2). That saves about 20 columns per line over
  `YYYY-MM-DD HH:MM:SS,mmm - INFO - ` (03 F03).
- **Rendering.** `Log` with `highlight=False` (cheap, unwrapped,
  horizontally scrollable). Do not switch to `RichLog` for wrapping. It
  renders every line through Rich and is much slower per line. Outcomes
  never live only in the log: the result card (02 §5.3) carries them, so a
  clipped log line no longer hides a verdict.
- **Per run.** A run starts a new section (`── Run 14:02:11 · share analysis ──`).
  Today's `log_widget.clear()` at run start becomes "start a new section".
  The previous run moves to Earlier runs. Clearing is an explicit palette
  command, never `^L` (03 F10, T2).
- **Tracebacks** go to the file log only (02 §5.3). The view shows one line,
  `✗ Unexpected error (KeyError), details in the log file`.
- **stdout capture.** `_execute_run_for_tui` swaps `sys.stdout` and
  `sys.stderr` process-wide from the worker (`contextlib.redirect_stdout`),
  so anything printed on other threads during a run is captured too. Keep it
  (it works around a Windows console-handle failure), but enqueue the
  captured text with `RunLog.enqueue` after the run instead of
  `call_from_thread`.

---

## 6. Large entity lists

**Threshold.** Up to **2,000** distinct values: the stock `Select`, which has
type-to-search. Its overlay opens in 0.10–0.16 s at 2,000 values and 0.28 s
at 5,000 (`select_bench_2k.py`), so 2,000 is where it stays under the 0.2 s
interaction feel. Above 2,000: `EntityPicker`.

**`EntityPicker`** is one composite widget:
- A filter `Input`, with `SuggestFromList(values, case_sensitive=False)` for
  inline completion (→ accepts it).
- An `OptionList` of at most **200** matches, titled `200 of 5,214 matches`.
- A first option `None: peer group only`, so a blank choice is explicit.

Matching uses prefix search with `bisect` over the sorted, casefolded values,
which the existing entity worker builds alongside the value list. When there
is no prefix match it falls back to a substring scan. ↑↓ moves through the
list. Enter or a click chooses.

**Privacy rule.** Only a chosen option, or an exact match of the typed text,
becomes the target entity. Free text never does. While the text matches no
entity, the action bar shows `! NOT READY  Target entity not found in
<column>`, so a typo can never silently turn into a peer-only run. The
Phase 0 rule that target entities are never restored from the session file
is unchanged.

**Measured** (`bench_entity.py` at 80x24, 2 sessions each; keystrokes typed
are `ent_0099`):

| Values | Variant | Load (s) | Open (s) | Key p50 / max (ms) | Max stall (ms) |
|---|---|---|---|---|---|
| 10,000 | E0 `Select` | 0.015–0.018 | 0.26–0.33 | 2.7–2.9 / 3–7 | 134–179 |
| 10,000 | E1 `Input` + `SuggestFromList` | 0.002 | — | 2.6–3.1 / 5 | 2–3 |
| 10,000 | E2 filter + capped `OptionList` | 0.008 | — | 3.7–4.5 / 6–16 | 8–10 |
| 100,000 | E0 `Select` | 0.175–0.185 | **2.55–2.71** | 27–30 / 34–47 | **1,608–1,691** |
| 100,000 | E1 `Input` + `SuggestFromList` | 0.002 | — | 2.0–2.8 / 4–6 | 1–2 |
| 100,000 | E2 filter + capped `OptionList` | 0.007 | — | 3.7–5.9 / 14–31 | 14–16 |

For reference, Phase 0's `select_bench.py` re-run in this session gives a
Select overlay open time of 0.48 s at 10k and 4.23 s at 100k. Its timing
includes a `pilot.pause()` frame, so it is higher than E0. The composite
picker gives E1's instant completion plus E2's browsable list. It stays at
≤ 31 ms per keystroke at 100k without a worker. Above 500k values, move the
substring fallback into an `exclusive=True` thread worker. The prefix path
stays on the UI thread, because it is O(log n).

---

## 7. Threading rule (follow-up D7)

**Rule:** *Workers never touch widgets.* Everything a run needs is read on
the UI thread into an immutable snapshot **before** the worker starts.
Dialogs happen on the UI thread **before** the worker that needs their
answer. Workers talk back with messages.

Concretely:

1. **Gather on the UI thread.** `action_run` (UI thread) calls
   `snapshot = RunInputs.from_form(self.form_state)`. It is a frozen
   dataclass holding every value that today's worker reads with
   `query_one` (`tui_app.py`, `run_analysis`: csv, entity, entity_col,
   preset, config path, output, time_col, the checkboxes, mode-specific
   columns, dims, privacy values). Preflight validation (01's blockers) runs
   on the snapshot. If anything blocks, the run does not start.
2. **Ask before working.** Consent (accuracy_first, resolved from the
   *effective* config, 01 §8.2) and the clearing-spend attestation are pushed
   as screens with `push_screen(…, callback)` on the UI thread. 01 moves them
   after validation, so the flow is a chain of workers and callbacks:
   `validate worker(snapshot) → UI: validation dialog → UI: consent and
   attestation dialogs → execute worker(snapshot + answers)`. That removes
   today's pattern of a worker blocking on `threading.Event` while it waits
   for a dialog (`_confirm_accuracy_first_consent`,
   `_confirm_clearing_spend_basis`).
3. **Workers receive data, return data.** `@work(thread=True, exclusive=True,
   group="run")` methods take the snapshot as an argument and only call
   `core` (`prepare_run_data`, `validate_analysis_input`, `execute_run`).
   They report with `self.post_message(RunProgress(...))`,
   `RunFinished(artifacts)` and `RunFailed(exc)`, all non-blocking.
   `call_from_thread` is only for the rare call that needs a return value.
   The log uses `RunLog.enqueue` (§5).
4. **The UI owns state transitions.** `on_run_finished` (UI thread) updates
   `FormState`, the badges and Results. The worker never calls
   `_end_run_ui` or `notify`.
5. **Cancellation** before the engine (01 §7.2): the UI sets the worker's
   cancelled flag. The worker checks `get_current_worker().is_cancelled`
   between stages and returns without side effects.
6. **Enforced by a test.** A fixture wraps `DOMNode.query_one`, `query` and
   `Widget.refresh` to assert `threading.get_ident() == app._thread_id`, then
   drives a stubbed full run (success, validation issues, consent, withheld).
   Any widget access from a worker fails the test.

---

## 8. Budgets and CI

### 8.1 Final `DEFAULT_BUDGETS`

Budgets are checked against the median of at least 3 repeats on this class of
machine (the probe's default `--budget-stat median`).

| Metric | Current | **Proposed** | Phase 1 prototype (same session) | Reason |
|---|---|---|---|---|
| `import_s` | 1.0 | **1.0** (0.8 once the `core/__init__` facade lands) | 0.96 (A) / 0.62 (A+B) | Option A alone lands just under 1.0. Tighten when B ships. |
| `startup_idle_s` | 1.0 | **0.75** | 0.38–0.43 (M6) | About 1.8× headroom over the prototype on a noisy VM. The redesign mounts fewer widgets than M6. |
| `startup_stall_max_ms` | 500 | **300** | 192–238 (M6) | The theme fix alone gets 277–280 with all 233 widgets. |
| `csv_headers_ready_s` | 0.10 | **0.10** (keep) | 0.02–0.03 (04) | Already met. Guards against regression. |
| `csv_stall_max_ms` | 100 | **100** (keep) | 46–57 at 1M (Phase 0 fix) | Met since the entity worker landed |
| `entity_change_s` | 1.5 | **1.5** (keep) | 0.6–1.2 at 1M (data-bound) | A no-regression guard, not a goal |
| `entity_change_stall_max_ms` | 100 | **100** (keep) | 29–31 (Phase 0 fix) | Met |
| `key_latency_p95_ms` | 100 | **100** (keep) | 44–56 (F4–F6) | Room for CI noise. Not lower: one context change can cost about 50 ms. |
| `key_latency_max_ms` | 250 | **150** | 47–56 (focus), 11–28 (1M tab-out with guard) | The worst key used to be the CSV tab-out, which is now an ordinary Tab |
| `key_stall_max_ms` | 100 | **100** (keep) | 31–51 | Matches the interaction stall budget |
| `advanced_expand_s` | 0.15 | **removed** → `expert_open_s` **0.30** | 0.23 median, 0.38 worst (`bench_expert.py`, 19 fields, cached presets) | Expert is a screen composed on demand. Pre-mounting it to hit 0.15 would break the startup budget. |
| `picker_open_s` | 0.20 | **0.20** (keep) | 0.18–0.22 open to ready (P2) | The probe measures "screen active", which is earlier than P2's figure, so it has margin |
| *new* `picker_ready_s` (2,000 files) | — | **0.50** | 0.19–0.23 | Browse list populated, replacing `picker_tree_ready_s` |
| `picker_stall_max_ms` | 250 | **200** | 116–154 | |
| `log_flood_s` (5,000 lines) | 1.0 | **0.5** | 0.14–0.21 | |
| `log_flood_stall_max_ms` | 50 | **100** | 54–116 (median about 70) | The old 49 ms was a side effect of the worker being throttled into one-line writes, while the flood took 4–9 s. One bounded write of 2,000 lines costs about 31 ms plus a frame. Aligned with the interaction stall budget. |
| *new* `entity_filter_key_max_ms` (100k values) | — | **50** | 14–31 | Guards the `EntityPicker` |

**Probe changes for Phase 2** (in `scripts/`, not `core/`):
- New selectors where the redesign renames widgets (`#advanced_opt` → F8
  Expert screen; `CsvDirectoryTree` → the browse `OptionList`).
- The `advanced` phase becomes `expert`, the `picker` phase reports
  `picker_ready_s`, and there is a new `entity-large` phase that generates a
  100k-value column.
- A `--compare BASE.json` mode for §8.2.
- Metric names stay stable otherwise, so the 04 JSON stays comparable.

### 8.2 Wiring the probe into CI without flakiness

| Option | Flakiness | Cost | Catches |
|---|---|---|---|
| Absolute budgets on every PR | High. Shared runners vary 2–2.5× (04 saw 2.5× between identical runs). | 5–15 min | Real regressions, plus noise |
| Absolute budgets × a generous multiplier (for example 2.5×) | Low | Same | Only catastrophic regressions. A 2× slowdown passes. |
| Nightly absolute run | n/a (not a gate) | Off the PR path | Trends, slowly |
| **Paired relative check on PRs** | **Low.** Base and head run on the same runner, interleaved, so machine speed cancels out. | ~2× one probe run at 10k rows (≈4–6 min) | Regressions of 30% and up in any gated metric, on the PR that causes them |

**Recommendation: the paired relative check as the PR gate**, path-filtered
to `tui_app.py`, `tui/**`, `scripts/tui_perf_probe.py` and `core/__init__.py`.

- One job on Python 3.13 only. Performance does not vary meaningfully across
  3.10–3.13, and the test matrix already covers correctness on every version.
- It checks out the merge base into a worktree and runs the probe
  **interleaved**: base, head, base, head, base, head, each `--repeat 1`,
  10k rows × 50 and 5,000 entities, phases
  `startup csv entity keys expert picker log`.
- It fails a metric only when **both** are true: `head_median > 1.30 ×
  base_median` **and** `head_median − base_median > floor`. The floor is
  50 ms for `*_ms` metrics and 0.10 s for `*_s` metrics, so a 6 → 9 ms change
  can't fail it.
- Absolute budgets run in the same job as a **ceiling at 2×**
  `DEFAULT_BUDGETS`. That catches a PR whose base was already bad, without
  being sensitive to noise.
- Both JSON files are uploaded as artefacts.
- Add a **nightly** scheduled job alongside the gate. It runs the full 04
  matrix (10k, 100k, 1M rows) against absolute `DEFAULT_BUDGETS` at 1× with
  `--repeat 5`, uploads the JSON, and opens or updates one tracking issue
  when it fails. It informs, it does not block. It is also where the 1M-row
  budgets (`entity_change_s`, `csv_stall_max_ms`) live, because generating
  70 MB fixtures on every PR is not worth it.

Until the redesign lands, run the gate as **non-blocking** (report only) for
two weeks. Its false-positive rate then decides the 1.30 factor before it
becomes a required check. Changing branch protection is a Release Operator
action (AGENTS.md).
