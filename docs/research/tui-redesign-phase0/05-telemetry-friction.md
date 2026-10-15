# 05 — Telemetry: where TUI users get stuck, and how to pull it

Phase 0 evidence for the TUI redesign. Read-only research: no repo code was
changed. Every command below was run against a **synthetic** telemetry store in
a scratch directory, written through the real `TelemetryService` and writer
(see [Reproduction](#7-reproduction-synthetic-store)). Sample numbers are
invented. They show that the commands work and say nothing about real users.

> **Update (telemetry pass 1):** most gaps below are now closed. Sections 1–7
> describe the schema-v1 state that the Phase 0 baseline was measured on and are
> kept as written. [§8 Implemented in this pass](#8-implemented-in-this-pass)
> gives the schema-v2 catalog, the gap-by-gap disposition, the compatibility
> rules and the new `benchmark.py telemetry` reports that replace the §5.2
> script.

## Summary

- **The schema is small and closed.** It has 8 event types. Every prop value
  comes from a fixed list, except `session_end.duration_s` (a number). The
  envelope carries the username, session UUID, app version and UTC timestamp.
  Nothing else can be recorded: unknown keys or values are rejected when a
  record is built and again when it is read.
- **The TUI emits very little itself:** `session_start("tui")`, `session_end`,
  `surface_viewed` (share/rate tab changes) and `action_cancelled` (two
  places). Attempts, refusals, failures and completions come from the shared
  `core.analysis_run._execute_run`, and only once a run reaches execution.
- **Pre-run friction is almost entirely invisible.** None of these emit
  anything: the 7 `_fail_launch` guards (missing CSV/metric/total/rate
  column/dimensions, accuracy_first consent declined), CSV load errors, the
  pre-run "Validation error"/"Initialization Error" paths, advanced-override
  problems and session restore. You can only see them indirectly, as TUI
  sessions with no run intent.
- **Three semantic traps for anyone reading the numbers:**
  1. TUI `action_cancelled` is emitted *before* any `action_attempted`, so the
     funnel denominator has to be attempted + cancelled.
  2. A ValidationModal with errors has Proceed disabled, so "Cancel" there is a
     forced exit, yet it is logged as a user cancel.
  3. `action_completed` also covers strict runs whose publication was withheld
     (only the analysis workbook was written).
- **The built-in CLI is coarse.** `benchmark.py telemetry who|summary` gives
  per-user sessions and completions plus total counts by surface, action and
  outcome. It cannot break refusals down by reason, failures by category,
  funnels by action, or durations. Its "Actions" counter also counts every
  `action_*` event, so attempts are counted twice. All the breakdowns asked
  for are possible today with no schema change, using a short read-only script
  on `TelemetryReader.iter_events` (§5.2) or `jq` over the raw files (§5.3).
- **Most proposed gap fixes fit within or next to the current enums.** The
  privacy-safe pattern is always the same: a new closed-enum value, never free
  text.
- **Phase 2 headline metric:** TUI run-intent success
  (completed ÷ (attempted + cancelled)), with time-to-first-completion and the
  share of sessions with no intent as secondary metrics. The baseline needs
  about 150–350 TUI run intents per period. With a small edge-node fleet,
  results should also be confirmed with a per-user paired sign test.

---

## 1. Telemetry system reference

### 1.1 Envelope (`core/telemetry/events.py`)

Each record is one line of compact JSON (at most `MAX_RECORD_BYTES = 8192`).
The record must have exactly these keys (`_ENVELOPE_KEYS`):

| key | content |
|---|---|
| `schema_version` | int, must equal `SCHEMA_VERSION = 1` (otherwise the reader warns and skips the record) |
| `ts` | strict ISO UTC ending in `Z` (`_TS_RE`) |
| `event` | one of the 8 names below |
| `user` | effective-UID username from NSS (`identity.resolve_identity`); no control characters or `/`, at most 128 bytes |
| `session_id` | canonical lowercase UUID4, one per process (`__init__._build_default_service`) |
| `app_version` | contents of the repo `VERSION` file (currently `3.0`), at most 64 bytes, fallback `"0"` |
| `props` | exactly the keys the event's schema lists |

### 1.2 Event catalog (`_EVENT_SCHEMAS`, events.py:125)

| event | props (exact key set) |
|---|---|
| `session_start` | `launch_context` ∈ `LAUNCH_CONTEXTS` = `cli_share`, `cli_rate`, `tui` |
| `session_end` | `duration_s`: finite, 0 ≤ x ≤ `MAX_DURATION_S` (31,536,000), rounded to ms; measured on the monotonic clock from the session_start enqueue |
| `surface_viewed` | `surface` ∈ `SURFACES` = `share`, `rate` |
| `action_attempted` | `action` ∈ `ACTIONS` = `share_analysis`, `rate_analysis` |
| `action_completed` | `action` |
| `action_cancelled` | `action` |
| `action_refused` | `action`, `reason` ∈ `REFUSAL_REASONS` = `configuration`, `input_validation`, `compliance_policy` |
| `action_failed` | `action`, `category` ∈ `FAILURE_CATEGORIES` = `input`, `analysis`, `output`, `unexpected` |

`OUTCOMES = completed, cancelled, refused, failed` is used only for report
ordering. The `Literal` aliases in `core/telemetry/__init__.py` mirror the
constants tuples, and a test enforces that they match.

### 1.3 How outcomes are classified (`core/analysis_run.py:2287-2335`)

`_execute_run` emits `action_attempted` (line 2298) and then maps the result.
A `_PhaseTracker` moves through `configuration` (2395), `input` (2427),
`analysis` (2480) and `output` (3269).

| result | event |
|---|---|
| `RunBlocked` | `refused / compliance_policy` (2309) |
| `RunAborted` (any phase) | `refused / input_validation` (2312) |
| `ValueError` in the configuration phase | `refused / configuration` (2316) |
| `ValueError` in a later phase | `failed / <phase>` (2318) |
| other `Exception` | `failed / <phase>`, or `unexpected` if the phase is unknown (2321) |
| `BaseException` (e.g. KeyboardInterrupt) | `failed / unexpected` (2324) |
| returns with `privacy_sink_authorized is True` | `completed` (2329) |
| returns with the privacy sink not authorized | `refused / compliance_policy` (2331) |

Caveats that matter for reading the data:

- `RunAborted` is always reported as `input_validation`, even when it is raised
  in the analysis phase ("No analysis results generated") or in configuration
  (invalid `privacy_rule_strategy`).
- A strict-posture run with violations writes the analysis workbook and
  withholds the publication workbook, but it still reports **`completed`**.
  The synthetic real-path run confirmed this: the violating dataset produced
  `action_completed`.
- In the TUI, `RunAborted` is shown with the title **"Failed"**
  (tui_app.py:2632), while telemetry records it as **refused**. The user-facing
  wording and the telemetry label don't match.

### 1.4 Gating: opt-out, capability, identity

- **Opt-out, not opt-in.** Telemetry is on by default. Setting
  `AUTOBENCH_TELEMETRY` to `0`, `false`, `off` or `no` (case-insensitive)
  disables all writes and never starts the consumer thread
  (`service._env_enabled`). Opting out does not delete existing records.
- **Private sink, always attempted:**
  `/ads_storage/<user>/.autobench/telemetry/events.jsonl`. Directories are
  `0700` and the file is `0600`. The `<user>` home must already exist and be
  owned by the effective UID; the writer creates only `.autobench/telemetry`
  (`writer._ensure_private_parents`).
- **Shared sink:** `<shared>/users/<base64url(username)>.jsonl` with mode
  `0644`. `<shared>` defaults to `/ads_storage/autobench/telemetry`, or the
  value of `AUTOBENCH_TELEMETRY_DIR` if set. If that variable is set but blank,
  shared writes are disabled and private writes continue. Shared writes only
  happen if `capability.shared_writer_supported` passes: Linux, the required
  `O_*` flags and `flock` present, `/proc/sys/fs/protected_hardlinks == 1`,
  real (non-symlink) ancestors, and `users/` with mode 1777 (sticky,
  world-writable, world-searchable). Deployment creates these directories; the
  application never does.
- **Writes:** `O_APPEND|O_CREAT|O_WRONLY|O_CLOEXEC|O_NONBLOCK|O_NOFOLLOW`.
  After opening, `fstat` must show a regular file, owned by the effective UID,
  with exactly one link. The writer then calls `fchmod`, takes a non-blocking
  `flock`, and runs a write-all loop. The private and shared appends are
  independent (`append_record`).
- **Service** (`service.py`): a bounded queue (`DATA_CAPACITY = 256`, plus 2
  reserved slots for session_end and flush) drained by one daemon consumer.
  Shutdown waits at most 250 ms. Events emitted after shutdown are dropped.
  Every public helper is wrapped in `_run_safely`, so telemetry cannot raise
  into product code.

### 1.5 Privacy guarantees, and what is deliberately not recorded

From the design spec (`docs/superpowers/specs/2026-07-12-offline-telemetry-design.md`)
and `tests/telemetry/test_privacy_regression.py`:

- **Never recorded:** paths or basenames, entity or peer names, dataset values,
  column or dimension names, presets, output names, CLI arguments, environment
  values, exception text, domain objects, or analysis results.
  `test_captured_records_use_exact_envelope_and_approved_props_only` runs a
  real share analysis and checks that the raw records contain none of: the
  fixture path, output paths, `Target`, `issuer_name`, `txn_cnt`, `card_type`,
  `channel`, `year_month`, `balanced_default`, `gate_demo`, exception
  class/text, peer names (`P1`, `P2`), category values (`PREPAID`),
  `/ads_storage`, `observability`, or `total_elapsed_s`.
- **No influence on analysis.** Results with telemetry on and off are
  equivalent: same compliance summary, same publication decision, identical
  frames. Strict withholding behaves the same either way. Failing helpers
  (`_get_service` raising) do not change outputs.
- **No telemetry fields in run metadata or the audit log model.**
- **Opt-out starts no consumer thread and writes no `.jsonl`.**
- **The repo tracks no `.jsonl` files except an allowlist, and contains no
  generated `events.jsonl`.**
- **By design, usernames are visible to every local user** in the portable
  shared profile (`0644` files). This is a known disclosure, not a leak, but
  any new event must not add anything that becomes sensitive when tied to a
  named user.

---

## 2. TUI emission map

The TUI imports only `action_cancelled`, `end_session`, `start_session` and
`surface_viewed` (tui_app.py:78-83). `test_tui_does_not_import_or_call_orchestration_action_helpers`
ensures the TUI never imports or calls attempted/completed/refused/failed.

| user action | code path | event (props) |
|---|---|---|
| TUI mounted and usable | `on_mount` tui_app.py:1146 | `session_start(launch_context=tui)` |
| Initial tab shown, including a tab restored from the session | `on_mount` → `_emit_surface_if_changed` :1148 → :1170 | `surface_viewed(share\|rate)` |
| Switch tab Share ↔ Rate (deduplicated: only on a real change) | `on_tabbed_content_tab_activated` :2206 → :1170 | `surface_viewed(share\|rate)` |
| ValidationModal → Cancel button or Esc (`dismiss(False)`) | `_handle_validation_modal_result` :1187-1189 | `action_cancelled(share_analysis\|rate_analysis)`. **No preceding attempt.** |
| ValidationModal shown with errors (Proceed disabled) → Cancel | same, :1189 | `action_cancelled`. **A forced exit recorded as a user cancel.** |
| Rate run with a fraud column → ClearingSpendConfirmScreen → Cancel or Esc | `run_analysis` :2379 | `action_cancelled(rate_analysis)`. **No preceding attempt.** |
| Run confirmed (no issues, or Proceed on warnings) → execution | :2462 → :2479 → `_execute_run_for_tui` :1513 → `execute_run` | `action_attempted(...)` from analysis_run.py:2298 |
| Run completes (publication may still be withheld) → "Analysis Complete" toast :2619 | analysis_run.py:2329 | `action_completed` |
| Privacy sink denied → "Publication Withheld" toast :2606 | analysis_run.py:2331 | `action_refused(reason=compliance_policy)` |
| `RunBlocked` → "Blocked" toast :2627 | analysis_run.py:2309 | `action_refused(compliance_policy)` |
| `RunAborted` → "Failed" toast :2632 | analysis_run.py:2312 | `action_refused(input_validation)` (label mismatch) |
| Other exception → "Execution Error" :2635 | analysis_run.py:2318/2321/2324 | `action_failed(input\|analysis\|output\|unexpected)` |
| Quit (with or without the "still running" confirm) | `on_unmount` :1157 | `session_end(duration_s)`. An in-flight run's outcome is then **dropped** (service closed), which leaves an "open" attempt. |
| Terminal killed, SIGHUP, crash | none | **no `session_end`** (visible as a session without an end) |

Pinned non-events: CSV picker cancel and the quit-confirm callbacks emit no
`action_cancelled` (`test_csv_picker_cancel_and_quit_confirm_emit_no_cancel`).

---

## 3. Gaps: friction moments that emit nothing today

"Within the schema" means the existing events and enums could carry it, though
possibly with ambiguity. "Additive enum" means a new value for an existing
prop, which needs a `SCHEMA_VERSION` decision: today's reader treats unknown
enum values as invalid lines and silently drops them, so old readers would
under-count. "New event" means a new `_EVENT_SCHEMAS` entry. The privacy rule
for every proposal: **closed enum values only. No free text, counts of data
rows or categories, column, entity, file or preset names, or exception
messages.**

| # | friction moment (code) | today | proposal | fits schema? | privacy risk |
|---|---|---|---|---|---|
| G1 | `_fail_launch` "CSV path is required." :2273 | nothing | `action_refused(action, reason=configuration)` with no prior attempt (TUI-side, like cancel) | **Within**, but it conflates with orchestration-level configuration refusals and breaks the test that forbids `action_refused` in the TUI. Cleaner: a new event `launch_blocked{action, field}` with `field ∈ {csv, metric, total, rate_column, dimensions}` | None if `field` is a fixed enum of *form slots*. It must never carry the selected column's name. |
| G2 | `_fail_launch` primary metric :2325 / total :2351 / rate column :2358 / dimensions (share :2332, rate :2365) | nothing | same as G1, `field=metric\|total\|rate_column\|dimensions` | as G1 | as G1 |
| G3 | accuracy_first consent declined :2315 (goes through `_fail_launch`) | nothing. This is **inconsistent** with clearing-spend decline, which does emit `cancelled`. | `action_cancelled(action)` | **Within**, no change needed | None. It reveals only that the user's preset has the accuracy_first posture, which the same user's later refusal pattern already implies. |
| G4 | ValidationModal cancel when the modal has errors (forced) vs warnings (chosen) :1187 | both are `action_cancelled` | split it: forced exits become `action_refused(reason=input_validation)` (UI-side), voluntary ones stay `cancelled`. Or add a new event `validation_reviewed{action, outcome∈{proceed,cancel,blocked}}` | Refused-variant is **within**, but it changes the TUI-only rule. New event is cleaner. | Low. Must not include issue counts, severities per column, or row indices (the modal shows row indices). |
| G5 | Pre-run validation exception "Validation error" :2457-2459 (`prepare_run_data`/`resolve_dimensions` raising) | nothing | `action_failed(action, category=input)` without an attempt, or a new `launch_blocked{field=dataset_read}` | **Within** (category `input` exists), with the attempt asymmetry | None if the exception text stays out (the toast currently shows `exc`; telemetry must not). |
| G6 | Outer "Initialization Error" :2470 | nothing | `action_failed(action, unexpected)` | **Within** | None |
| G7 | CSV not found :1609-1614, header read failure :1680, entity list load failure :2170 | nothing (toast and log only) | new event `dataset_load_failed{stage∈{path_missing,header_read,entity_list}}` | **New event** (no `action` applies; the user hasn't chosen to run) | Low **only** if no path, basename, size or column count is recorded. Even "file size bucket" should be rejected. |
| G8 | CSV loaded successfully (`load_csv_headers`) | nothing | new event `dataset_loaded{}` (no props) or `surface_viewed`-style `step_reached{step∈{dataset,configured,validated}}` | **New event** | None with zero props. Column count must **not** be added. |
| G9 | Advanced overrides applied :1907 / failed :1913 / empty :1885; export :2249/:2251 | nothing | new event `advanced_override{outcome∈{applied,empty,failed,exported,export_failed}}` | **New event** | Low. Must not record which fields or values changed. A field-name enum would be about our own config keys, not data, but it still needs privacy-owner review because it reveals tuning behaviour per named user. |
| G10 | Session restored (`_restore_session` :1236 → `_apply_session` :1248) | nothing | add `restored: bool` to `session_start`, or a new event `session_restored{}` | **Schema change** to an existing event's exact key set, or a new event | None (boolean) |
| G11 | Time from mount to first run intent | **derivable today** from `session_start.ts` → first `action_attempted`/`action_cancelled` `ts` (§5.2 prints it) | none needed. Time to the *validation modal* would need G4/G8. | **Within** | None |
| G12 | Time spent in ValidationModal before deciding | not derivable (the cancel ts exists, but there's no "modal shown" event) | the G4 event covers it via its timestamp | New event | None |
| G13 | Strict run with publication withheld but workbook written: reported as `completed` | indistinguishable from a clean completion | add `publication∈{published,withheld,not_applicable}` to `action_completed` | **Schema change** to an existing event | **Low but non-zero.** It encodes a dataset-derived property (violations exist) tied to a named user. Needs privacy-owner sign-off. Keep it out unless the redesign specifically targets the withheld-publication UX. |
| G14 | Help / preset guide opened (F1, :1946/:2127), advanced panel toggled | nothing | `surface_viewed(surface=preset_help\|advanced)`, an additive `SURFACES` value | **Additive enum** (SCHEMA_VERSION or reader-tolerance decision) | None |
| G15 | Quit while a run is in flight (:1980 confirm → exit) | attempt with no outcome (outcome dropped) | derivable as "open" = attempted − (completed + refused + failed). An explicit `action_cancelled` before `exit()` would make it clear. | **Within** | None |
| G16 | `RunAborted` shown as "Failed" but recorded as refused | label mismatch | no telemetry change; reconcile the UI wording in the redesign | n/a | n/a |

Cross-cutting recommendation: put any pre-attempt TUI events (G1-G6) behind
one new event, e.g. `launch_blocked{action, field}`, instead of overloading
`action_refused`/`action_failed` from the TUI. That keeps the
"`_execute_run` owns attempt/refuse/fail/complete" invariant (and its test)
intact, and keeps CLI and TUI funnels comparable.

---

## 4. Where the data lives (what the owner reads)

- **Per edge node**, at `/ads_storage/autobench/telemetry/users/*.jsonl`
  (shared, one file per user), plus each user's private copy. There is **no
  upload or fleet collection**. Retention, rotation and collection are
  operator-owned procedures.
- The reader's shared-file gate requires the **file owner UID to equal the NSS
  UID of the username in the first valid record**, and the filename to match
  the base64url token. **Copying files to another host breaks this gate.** The
  copies are owned by whoever copied them, so `benchmark.py telemetry` silently
  falls back to your own private file. (Since §8.5 the fallback is no longer
  silent: a stderr warning names the rejection reasons.) To aggregate across hosts, either run
  the reader on each node or use the `jq` route (§5.3) on copied files, which
  bypasses the gate and the schema validation, so trust the inputs.
- Check what you're reading with `telemetry who`. If it lists only yourself,
  you're on the private fallback.

---

## 5. Pull commands, with sample output

Run from the repo root. In this environment use `/usr/local/bin/uv run python`.
On an edge node, use the installed interpreter. `--dir` names the directory
**whose child is `users/`**. Omit it to use `AUTOBENCH_TELEMETRY_DIR` or the
default `/ads_storage/autobench/telemetry`. The default window is 30 days
(`--days N`; `--days 0` means today only).

In this document, `$S` is the scratch store:
`/tmp/claude-0/-home-user-autobench/d13cb994-08e3-5f72-b4d1-86adf775fd7d/scratchpad/telemetry`.

### 5.1 Built-in CLI (`benchmark.py telemetry`, benchmark.py:343-447)

```console
$ python benchmark.py telemetry who --dir $S/fleet/shared
USER	SESSIONS	LAST_SEEN	COMPLETED
daemon	12	2026-10-12T14:36:21Z	6
nixbld1	9	2026-10-13T14:13:52Z	2
nixbld2	14	2026-10-14T02:41:47Z	7
nixbld3	13	2026-10-14T08:57:33Z	8
root	17	2026-10-12T20:25:16Z	11
ubuntu	8	2026-10-05T16:03:44Z	3

$ python benchmark.py telemetry summary --dir $S/fleet/shared [--days 30] [--user NAME]
Surfaces
share  40
rate  25

Actions
share_analysis  88
rate_analysis  52

Outcomes
completed  37
cancelled  14
refused  16
failed  10
```

Limits: "Actions" counts **every** `action_*` event (attempted plus outcomes),
so it is not a run count. The 88 here is 41 attempts + 47 outcome/cancel
events. Outcomes are not split by action, reason or category. There's no
launch_context, duration, or app_version slicing. The reader commands never
start a telemetry session themselves.

### 5.2 Friction breakdowns (no schema or code change; read-only script on the validated reader)

This uses `TelemetryReader.iter_events`, so it gets the same owner/token gate,
strict decoding and date window as the CLI. Save it outside the repo (for
example `~/friction_report.py`), not under the repo.

```python
"""Friction breakdowns over the validated TelemetryReader stream (read-only).
Usage: python friction_report.py [--dir PARENT_OF_USERS] [--days N] [--user NAME]
                                 [--context tui|cli_share|cli_rate] [--app-version V]"""
import argparse, statistics, sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, "/home/user/autobench")   # repo root on the edge node
from core.telemetry.constants import ACTIONS, REFUSAL_REASONS, FAILURE_CATEGORIES, SURFACES, LAUNCH_CONTEXTS
from core.telemetry.reader import TelemetryReader

ap = argparse.ArgumentParser()
ap.add_argument("--dir", type=Path); ap.add_argument("--days", type=int, default=30)
ap.add_argument("--user"); ap.add_argument("--context", choices=LAUNCH_CONTEXTS)
ap.add_argument("--app-version", help="only sessions whose events carry this app_version (pre/post redesign split)")
a = ap.parse_args()
events = list(TelemetryReader(shared_dir=a.dir).iter_events(days=a.days, user=a.user))

sess = defaultdict(list)
for e in events: sess[(e.user, e.session_id)].append(e)
ctx = {k: next((e.props["launch_context"] for e in v if e.event == "session_start"), None) for k, v in sess.items()}
keep = {k for k in sess if (a.context is None or ctx[k] == a.context)
        and (a.app_version is None or sess[k][0].app_version == a.app_version)}
ev = [e for k in keep for e in sess[k]]
print(f"window={a.days}d  users={len({k[0] for k in keep})}  sessions={len(keep)}  events={len(ev)}"
      + (f"  context={a.context}" if a.context else "") + (f"  app_version={a.app_version}" if a.app_version else ""))

print("\n## Funnel per action  (cancelled is emitted BEFORE attempted in the TUI -> 'intents' = attempted + cancelled)")
c = Counter((e.event, e.props.get("action")) for e in ev)
print(f"{'action':<16}{'intents':>8}{'cancel':>8}{'attempt':>8}{'complete':>9}{'refused':>8}{'failed':>7}{'complete/attempt':>17}{'open':>6}")
for act in ACTIONS:
    at, cp, rf, fl, cn = (c[(x, act)] for x in ("action_attempted", "action_completed", "action_refused", "action_failed", "action_cancelled"))
    rate = f"{cp/at:.0%}" if at else "-"
    print(f"{act:<16}{at+cn:>8}{cn:>8}{at:>8}{cp:>9}{rf:>8}{fl:>7}{rate:>17}{at-cp-rf-fl:>6}")

print("\n## Refusals by reason")
r = Counter((e.props["action"], e.props["reason"]) for e in ev if e.event == "action_refused")
for reason in REFUSAL_REASONS:
    print(f"{reason:<20}" + "  ".join(f"{act}={r[(act, reason)]}" for act in ACTIONS) + f"  total={sum(r[(x, reason)] for x in ACTIONS)}")

print("\n## Failures by category")
f = Counter((e.props["action"], e.props["category"]) for e in ev if e.event == "action_failed")
for cat in FAILURE_CATEGORIES:
    print(f"{cat:<20}" + "  ".join(f"{act}={f[(act, cat)]}" for act in ACTIONS) + f"  total={sum(f[(x, cat)] for x in ACTIONS)}")

print("\n## Surface usage (TUI)")
sv = Counter(e.props["surface"] for e in ev if e.event == "surface_viewed")
tui = [k for k in keep if ctx[k] == "tui"]
seen = {s: sum(1 for k in tui if any(e.event == "surface_viewed" and e.props["surface"] == s for e in sess[k])) for s in SURFACES}
both = sum(1 for k in tui if len({e.props["surface"] for e in sess[k] if e.event == "surface_viewed"}) == 2)
for s in SURFACES: print(f"{s:<6} views={sv[s]:<4} tui_sessions_viewing={seen[s]}/{len(tui)}")
print(f"tui sessions viewing both surfaces: {both}/{len(tui)}")
print("launch contexts: " + "  ".join(f"{x}={sum(1 for k in keep if ctx[k] == x)}" for x in LAUNCH_CONTEXTS))

print("\n## Session duration (session_end.duration_s)")
def pct(xs, p): xs = sorted(xs); return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]
for x in (None,) + LAUNCH_CONTEXTS:
    d = [e.props["duration_s"] for k in keep if x is None or ctx[k] == x for e in sess[k] if e.event == "session_end"]
    if d: print(f"{x or 'all':<10} n={len(d):<4} p10={pct(d,10):>7.1f}s p50={pct(d,50):>7.1f}s p90={pct(d,90):>7.1f}s max={max(d):>7.1f}s")
bins = [(0, 10), (10, 60), (60, 300), (300, 900), (900, 3600), (3600, 1e12)]
d = [e.props["duration_s"] for k in tui for e in sess[k] if e.event == "session_end"]
print("tui histogram: " + "  ".join(f"[{lo:g}-{'inf' if hi > 1e9 else f'{hi:g}'})s={sum(lo <= v < hi for v in d)}" for lo, hi in bins))
missing_end = sum(1 for k in keep if not any(e.event == "session_end" for e in sess[k]))
print(f"sessions without session_end (crash/kill/drop): {missing_end}")

print("\n## TUI friction derived from timestamps (no schema change)")
zero = sum(1 for k in tui if not any(e.event in ("action_attempted", "action_cancelled") for e in sess[k]))
print(f"tui sessions with no run intent at all (left before any attempt/cancel): {zero}/{len(tui)}")
noc = sum(1 for k in tui if any(e.event == "action_attempted" for e in sess[k]) and not any(e.event == "action_completed" for e in sess[k]))
print(f"tui sessions with >=1 attempt but no completion: {noc}/{len(tui)}")
ttfa = []
for k in tui:
    st = next((e.ts for e in sess[k] if e.event == "session_start"), None)
    fa = min((e.ts for e in sess[k] if e.event == "action_attempted"), default=None)
    if st and fa: ttfa.append((fa - st).total_seconds())
if ttfa: print(f"time to first attempt: n={len(ttfa)} p50={statistics.median(ttfa):.0f}s p90={pct(ttfa,90):.0f}s")
ttfc = []
for k in tui:
    st = next((e.ts for e in sess[k] if e.event == "session_start"), None)
    fc = min((e.ts for e in sess[k] if e.event == "action_completed"), default=None)
    if st and fc: ttfc.append((fc - st).total_seconds())
if ttfc: print(f"time to first completion: n={len(ttfc)} p50={statistics.median(ttfc):.0f}s p90={pct(ttfc,90):.0f}s")
retry = Counter()
for k in tui:
    seq = [e.event for e in sorted(sess[k], key=lambda e: e.ts) if e.event.startswith("action_") and e.event != "action_attempted"]
    for prev, nxt in zip(seq, seq[1:]):
        if prev in ("action_refused", "action_failed", "action_cancelled"): retry[(prev, nxt)] += 1
print("outcome after a bad outcome (same session): " + ", ".join(f"{p.split('_')[1]}->{n.split('_')[1]}={v}" for (p, n), v in sorted(retry.items())))
```

Sample output (synthetic fleet, all contexts):

```console
$ python friction_report.py --dir $S/fleet/shared
window=30d  users=6  sessions=73  events=351

## Funnel per action  (cancelled is emitted BEFORE attempted in the TUI -> 'intents' = attempted + cancelled)
action           intents  cancel attempt complete refused failed complete/attempt  open
share_analysis        47       6      41       27       9      5              66%     0
rate_analysis         30       8      22       10       7      5              45%     0

## Refusals by reason
configuration       share_analysis=3  rate_analysis=0  total=3
input_validation    share_analysis=3  rate_analysis=3  total=6
compliance_policy   share_analysis=3  rate_analysis=4  total=7

## Failures by category
input               share_analysis=1  rate_analysis=3  total=4
analysis            share_analysis=1  rate_analysis=1  total=2
output              share_analysis=0  rate_analysis=0  total=0
unexpected          share_analysis=3  rate_analysis=1  total=4

## Surface usage (TUI)
share  views=40   tui_sessions_viewing=39/50
rate   views=25   tui_sessions_viewing=25/50
tui sessions viewing both surfaces: 14/50
launch contexts: cli_share=17  cli_rate=6  tui=50

## Session duration (session_end.duration_s)
all        n=73   p10=   51.7s p50=  201.0s p90=  448.2s max= 1250.4s
cli_share  n=17   p10=   75.4s p50=  129.2s p90=  247.4s max=  301.2s
cli_rate   n=6    p10=   92.7s p50=  149.8s p90=  234.2s max=  294.9s
tui        n=50   p10=   44.3s p50=  233.3s p90=  507.6s max= 1250.4s
tui histogram: [0-10)s=1  [10-60)s=6  [60-300)s=28  [300-900)s=14  [900-3600)s=1  [3600-inf)s=0
sessions without session_end (crash/kill/drop): 0

## TUI friction derived from timestamps (no schema change)
tui sessions with no run intent at all (left before any attempt/cancel): 15/50
tui sessions with >=1 attempt but no completion: 9/50
time to first attempt: n=28 p50=149s p90=212s
time to first completion: n=19 p50=183s p90=268s
outcome after a bad outcome (same session): cancelled->cancelled=1, cancelled->refused=1, failed->cancelled=2, failed->completed=1, refused->completed=1, refused->refused=2
```

TUI only, split by release (this is how Phase 2 compares before and after; it
needs a `VERSION` bump for the redesign):

```console
$ python friction_report.py --dir $S/fleet/shared --context tui --app-version 2.9   # abridged
window=30d  users=6  sessions=24  events=130  context=tui  app_version=2.9
action           intents  cancel attempt complete refused failed complete/attempt  open
share_analysis        12       2      10        8       2      0              80%     0
rate_analysis         15       3      12        6       3      3              50%     0
$ python friction_report.py --dir $S/fleet/shared --context tui --app-version 3.0   # abridged
window=30d  users=6  sessions=26  events=132  context=tui  app_version=3.0
share_analysis        18       2      16       13       1      2              81%     0
rate_analysis          9       4       5        1       4      0              20%     0
```

The same script against the **real-path** store (an actual headless TUI Pilot
session plus four real `execute_share_run` calls) shows the funnel and refusal
mapping are correct end-to-end:

```console
$ python friction_report.py --dir $S/real/shared   # abridged
window=30d  users=1  sessions=2  events=15
share_analysis         4       0       4        2       2      0              50%     0
```

The 4 real runs were: clean (completed), strict with violations (**completed**,
publication withheld; see §1.3), missing metric column (`refused/input_validation`),
and accuracy_first without acknowledgement (`refused/compliance_policy`).

### 5.3 Quick `jq` equivalents (raw files; no owner/token gate, no schema validation, no date window)

```console
$ D=$S/fleet/shared/users          # on a node: /ads_storage/autobench/telemetry/users
# funnel + reason/category in one table
$ jq -r 'select(.event|startswith("action_")) | [.props.action,(.event|sub("action_";"")),(.props.reason // .props.category // "")] | @tsv' $D/*.jsonl | sort | uniq -c | sort -k2,2 -k1,1nr
     22 rate_analysis	attempted
     10 rate_analysis	completed
      8 rate_analysis	cancelled
      4 rate_analysis	refused	compliance_policy
      3 rate_analysis	failed	input
      3 rate_analysis	refused	input_validation
      1 rate_analysis	failed	analysis
      1 rate_analysis	failed	unexpected
     41 share_analysis	attempted
     27 share_analysis	completed
      6 share_analysis	cancelled
      3 share_analysis	failed	unexpected
      3 share_analysis	refused	compliance_policy
      3 share_analysis	refused	configuration
      3 share_analysis	refused	input_validation
      1 share_analysis	failed	analysis
      1 share_analysis	failed	input
$ jq -r 'select(.event=="action_refused") | .props.reason' $D/*.jsonl | sort | uniq -c | sort -nr
      7 compliance_policy
      6 input_validation
      3 configuration
$ jq -r 'select(.event=="action_failed") | .props.category' $D/*.jsonl | sort | uniq -c | sort -nr
      4 unexpected
      4 input
      2 analysis
$ jq -r 'select(.event=="surface_viewed") | .props.surface' $D/*.jsonl | sort | uniq -c
     25 rate
     40 share
$ jq -s -r '[.[]|select(.event=="session_end")|.props.duration_s]|sort as $d|($d|length) as $n|"n=\($n) p50=\($d[($n/2|floor)]) p90=\($d[($n*0.9|floor)]) max=\($d[-1])"' $D/*.jsonl
n=73 p50=200.986 p90=448.227 max=1250.436
```

The `jq` totals match §5.2 exactly. Add `select(.ts >= "2026-09-14")` to
apply a date window.

---

## 6. Phase 0 / Phase 2 success metrics

**Phase 0 (now):** record a baseline of at least 4 weeks per node, using
`--context tui`, on the current `VERSION`. **Phase 2:** the same measurement on
the redesign's `VERSION`, in a window of equal length, split with
`--app-version`. Compare TUI against CLI too: the CLI didn't change, so it
acts as a control for changes in the data or the user population.

| metric (TUI context, per action and pooled) | formula from existing events | desired direction | notes |
|---|---|---|---|
| **M1 Run-intent success (headline)** | completed ÷ (attempted + cancelled) | ↑ | Robust to friction moving between "cancelled before attempt" and "refused after attempt" |
| M2 Completion per attempt | completed ÷ attempted | ↑ (≥ baseline) | Should rise if the redesign catches input/config problems before execution |
| M3 Avoidable refusals | refused{input_validation + configuration} ÷ attempted | ↓ | These are the problems a better form and inline validation should prevent |
| M4 Pre-attempt cancel rate | cancelled ÷ (attempted + cancelled) | ↓, interpreted together with M3 | Can legitimately *rise* if validation moves earlier; never read it alone. G4 is needed to separate forced from voluntary. |
| M5 No-intent sessions | TUI sessions with no attempt or cancel ÷ TUI sessions | ↓ | The best existing proxy for the invisible `_fail_launch`/CSV friction (G1-G7) |
| M6 Time to first completion | p50/p90 of (first `action_completed.ts` − `session_start.ts`) | ↓ | Time to first attempt is a secondary metric |
| M7 Recovery rate | share of TUI sessions with a refused/failed/cancelled outcome that later reach `completed` | ↑ | Measures whether error messages lead users to a fix |
| M8 Rate-surface gap | M1(share) − M1(rate) | → 0 | Rate has the extra clearing-spend modal and more required fields |
| **Guardrail G-a** | refused{compliance_policy} ÷ attempted | **No change expected** | A drop must come from better preset guidance, never from weakened enforcement. Investigate any significant drop. |
| Guardrail G-b | failed{unexpected} ÷ attempted | flat or ↓ | A redesign regression shows up here first |
| Guardrail G-c | sessions without `session_end` ÷ sessions | flat | Crashes or hangs in the new UI |
| Context (not a goal) | session duration distribution | none | Shorter isn't automatically better. Read together with M6. |

**Minimum sample sizes.** Two-proportion test, α = 0.05 two-sided, 80% power,
n = 7.85 · (p₁q₁ + p₂q₂)/(p₁ − p₂)², events **per period**:

| change to detect | n per period |
|---|---|
| M1 0.55 → 0.70 (15 pp) | ≈ 160 run intents |
| M1 0.60 → 0.70 (10 pp) | ≈ 350 run intents |
| M3 0.20 → 0.10 | ≈ 200 attempts |
| M3 0.30 → 0.20 | ≈ 290 attempts |
| M5 0.30 → 0.20 | ≈ 290 TUI sessions |

Rules of thumb:

1. **Don't report any ratio whose denominator is under 30.** Show the raw
   counts instead.
2. Events cluster heavily by user: a few power users dominate. Require **at
   least 10–15 distinct TUI users in each period**, and also report per-user
   M1. With a small fleet, use a **paired sign test across users** who are
   active in both periods. At α = 0.05 two-sided you need 8/8, 9/10, 10/12 or
   12/15 users to improve.
3. If fleet volume can't reach about 150 TUI intents per 4 weeks, treat Phase 2
   telemetry as **directional only** and rely on the qualitative research for
   decisions.
4. Freeze the measurement window and the `VERSION` boundary before looking at
   Phase 2 data. Exclude the deployment day and the following 48 hours
   (learning effects).
5. If any gap events (G1-G10) are added in Phase 2, they have **no baseline**.
   Use them for diagnosis, not before/after claims. To get a baseline for them,
   ship them before the redesign (in a Phase 1 release) as their own change.

---

## 7. Reproduction (synthetic store)

All writes went to `$S` (above). Nothing was written to `/ads_storage` (which
doesn't exist here), `$HOME`, or the repo. `tui_app.SESSION_FILE` and
`AUTOBENCH_LOG_DIR` were redirected to scratch.

- `$S/scripts/real_emit.py <store>`: injects a real `TelemetryService`
  (`storage_root=<store>/ads`, `shared_dir=<store>/shared`, `users/` mode 1777)
  via `core.telemetry._reset_for_tests`. It runs a headless
  `BenchmarkApp().run_test()` Pilot session (mount → rate tab → share tab →
  exit), then four real `execute_share_run` calls on
  `tests/fixtures/gate_demo.csv`. Result: identical private (`0600`) and shared
  (`0644`) files with 15 records.
- `$S/scripts/synth_fleet.py <store>`: 73 sessions for 6 real NSS accounts
  (root, ubuntu, daemon, nixbld1-3), written through the real service and
  writer with injected UTC/monotonic clocks spanning 27 days, using a fixed
  random seed. Files are pre-created and chowned to each UID so the writer's
  owner check and the reader's owner/token gate both pass.
- `$S/scripts/friction_report.py`: the §5.2 script.

```console
cd /home/user/autobench
/usr/local/bin/uv run python $S/scripts/real_emit.py   $S/real
/usr/local/bin/uv run python $S/scripts/synth_fleet.py $S/fleet
/usr/local/bin/uv run python benchmark.py telemetry who     --dir $S/fleet/shared
/usr/local/bin/uv run python benchmark.py telemetry summary --dir $S/fleet/shared
/usr/local/bin/uv run python $S/scripts/friction_report.py --dir $S/fleet/shared --context tui
```

---

## 8. Implemented in this pass

This pass closes the friction gaps from §3, fixes the three semantic traps
from the Summary, replaces the §5.2 script with built-in CLI reports, and makes
the reader's private fallback explicit. The privacy rule from §3 still holds:
**every new value is a closed enum, a strict boolean, or the existing bounded
duration.** No new field can carry a path, file name, column name, entity,
data value, row count, exception text, or anything the user typed. Privacy
enforcement, publishable-output validation and analysis results did not
change.

### 8.1 Schema v2 catalog

Records are now written with `schema_version: 2`, except `session_start` and
`session_end` (see §8.4). Changes from v1 are in **bold**.

| event | props (exact key set) | emitted by |
|---|---|---|
| `session_start` | `launch_context` ∈ `cli_share`, `cli_rate`, `tui` | CLI, TUI mount |
| `session_end` | `duration_s` (bounded number, as before) | shutdown |
| **`session_restored`** | *(none)* | TUI mount, after a saved form was applied (G10) |
| `surface_viewed` | `surface` ∈ `share`, `rate`, **`validation_review`**, **`preset_help`**, **`advanced`** | TUI tabs; the validation modal being pushed (G12); F1 or Preset Guide button; the advanced panel expanding by any route (G14) |
| `action_attempted` | `action` ∈ `share_analysis`, `rate_analysis` | `core.analysis_run._execute_run` only |
| `action_completed` | `action`, **`publication_withheld`: bool** | `_execute_run` only (G13) |
| `action_cancelled` | `action`, **`prompt`** ∈ `validation_review`, `accuracy_first_consent`, `clearing_spend`, `quit_before_run`, `quit_during_run` | TUI only |
| `action_refused` | `action`, `reason` ∈ `configuration`, `input_validation`, `compliance_policy` | `_execute_run` only |
| `action_failed` | `action`, `category` ∈ `input`, `analysis`, `output`, `unexpected` | `_execute_run` only |
| **`launch_blocked`** | `action`, `reason` ∈ `csv_missing`, `entity_loading`, `metric_missing`, `total_missing`, `rate_column_missing`, `dimensions_missing`, `validation_errors`, `data_preparation_error`, `initialization_error` | TUI only, before any attempt (G1, G2, G4, G5, G6) |
| **`dataset_load`** | `outcome` ∈ `loaded`, `not_found`, `header_read_failed`, `entity_list_failed` | TUI CSV loading (G7, G8) |
| **`advanced_override`** | `outcome` ∈ `applied`, `empty`, `failed`, `exported`, `export_failed` | TUI advanced panel (G9) |

The vocabularies live in `core/telemetry/constants.py`, the catalogs in
`core/telemetry/events.py` (`_EVENT_SCHEMAS_V1` is frozen, `_EVENT_SCHEMAS_V2`
is current), and the typed helpers in `core/telemetry/__init__.py`
(`launch_blocked`, `dataset_load`, `advanced_override`, `session_restored`,
plus the new required arguments on `action_completed` and `action_cancelled`).
`publication_withheld` accepts only a JSON `true`/`false`: `0`, `1`, `"true"`,
`null` and reason strings are rejected.

`publication_withheld` is true exactly when `write_outputs` set the closed
`publication_withheld_reason` marker to `strict_posture_violations` or
`strict_posture_noncompliant_verdict` on a run whose privacy sink was
authorized (`core.analysis_run._publication_withheld`). Telemetry records the
boolean only, never the reason or the violation count. The repo owner approved
this flag (it resolves the sign-off question in the G13 row of §3).

`dataset_load` events are deduplicated per (outcome, file) in TUI memory,
because blur and Enter both reload the same path. Only the outcome is sent.

### 8.2 Run intents: the funnel without guesswork

Every TUI run press now ends in exactly one recorded terminal, and each
terminal says whether it happened before or after the attempt:

```text
run intent ─┬─ launch_blocked{reason}                      (before attempt)
            ├─ action_cancelled{prompt ≠ quit_during_run}  (before attempt)
            └─ action_attempted ─┬─ action_completed{publication_withheld}
                                 ├─ action_refused{reason}
                                 ├─ action_failed{category}
                                 ├─ action_cancelled{prompt = quit_during_run}
                                 └─ (nothing: "open", the process died)
```

So **intents = launch_blocked + pre-attempt cancels + attempted**, and every
term is an explicit record. `core.telemetry.report.is_run_intent` encodes the
rule. v1 data still fits it: v1 cancels have no `prompt`, and in v1 every
cancel was pre-attempt (validation modal or clearing-spend confirm), so they
count as pre-attempt. The CLI emits only `action_attempted` and its outcomes,
so CLI intents equal CLI attempts and CLI and TUI funnels stay comparable.

Validation-modal outcomes (G4) are now distinguished:

| modal state when dismissed | v1 | v2 |
|---|---|---|
| warnings only, Proceed pressed | `action_attempted` follows | unchanged |
| warnings only, Cancel or Esc | `action_cancelled` | `action_cancelled{prompt=validation_review}` (the user's choice) |
| errors (Proceed disabled), Cancel or Esc | `action_cancelled` | `launch_blocked{reason=validation_errors}` (a forced exit) |
| `should_abort` set (with or without errors) | `action_cancelled` or nothing | `launch_blocked{reason=validation_errors}` |
| dismissed with no result (`None`) | nothing | nothing |

`surface_viewed{validation_review}` is emitted when the modal is pushed, so the
time to the next attempt, cancel or block is the time spent in review (G12).

Quitting while busy (G15) is no longer an unexplained open attempt.
`quit_during_run` is recorded when the run state is `running` (the attempt was
already emitted). `quit_before_run` is recorded while `validating`. One race
remains: a run that finishes during the 250 ms shutdown budget after a
`quit_during_run` could in principle record a second terminal. The service
stops accepting events as soon as shutdown begins, so in practice the outcome is
dropped.

### 8.3 Outcome semantics, made explicit

- **refused** means the product deliberately declined to produce benchmark
  output for a known reason: a compliance policy block, an aborted input
  (`RunAborted`, in any phase) or a configuration error. **failed** means an
  error the product did not anticipate, categorised by the phase it happened
  in. **launch_blocked** means the TUI stopped before the run was attempted.
  This is documented next to the mapping in `core/analysis_run.py`.
- **`RunAborted` stays `refused/input_validation`** (G16). The TUI toast title
  "Failed" is not plainly wrong from the user's side (the run did not produce a
  report), so the copy was not changed. Readers should treat "Failed" toasts
  as refused-or-failed telemetry.
- **Strict-withheld runs** still count as `completed`. In v2 they carry
  `publication_withheld=true`, and the funnel shows them in the `WITHHELD`
  column. v1 completions are reported as "predate schema v2" rather than being
  guessed either way.

### 8.4 Compatibility: how records are versioned, and what each reader does

**Mechanism.** Every record carries `schema_version`. The reader decodes each
record against the catalog of its own version (`SUPPORTED_SCHEMA_VERSIONS =
(1, 2)`), so a file can mix versions freely: an upgraded node appends v2 records
after its v1 history. The rule for future changes is in `constants.py`: any
change to an existing event's key set or enum values needs a new version,
because a reader on the same version silently drops records it cannot
validate, but rejects a record with a different version **with a warning**.

`session_start` and `session_end` did not change, so they are still written as
`schema_version: 1` (`events.LEGACY_WRITE_EVENTS`; a test pins that their v1
and v2 validators are the same objects). This keeps an installed v1 reader's
shared-file gate working: the gate needs one v1-valid record in the first
64 KiB. Without it, a node that only has v2 records would look **empty and
silent** to a v1 reader. Only the session lifecycle qualifies. Writing
`action_attempted` as v1 while `action_completed` is v2 would give old readers
an inconsistent funnel.

| reader | data | behaviour |
|---|---|---|
| new (v2) | v1 files | Reads everything. v1 cancels count as pre-attempt; v1 completions are reported as unflagged. |
| new (v2) | mixed v1 + v2 | Reads everything (test `test_new_reader_reads_mixed_v1_and_v2_file`). |
| new (v2) | a future v3 record | Skips it. At the end of the report it prints one counted warning: `skipped N record(s) with an unsupported schema_version (this reader supports 1, 2); upgrade Autobench to read them.` Invalid lines inside accepted files are also counted (`skipped N record(s) that failed schema validation.`). Before, they were dropped silently. |
| installed v1 (main @ `ddea32c`) | mixed v1 + v2 | **No crash.** v1 records are aggregated correctly. Each v2 record prints `WARNING: unsupported schema_version: 2` and is skipped. `who` still shows every session (the session lifecycle is v1), while completions and summary counts cover only the v1 era. |
| installed v1 | v2-only node | **No crash.** Files still pass the gate (via `session_start`). `who` lists users, sessions and last seen. `COMPLETED` and `summary` counts are 0, and one warning per skipped record says why. |

The v1 rows were verified by running the real `core/telemetry` package from
`main` (`git archive ddea32c core/telemetry`) against the synthetic stores in
§8.7. On a mixed store (6 users, 504 records, 275 of them v2), the v1 `who`
showed all 81 sessions and printed 275 `unsupported schema_version: 2`
warnings. On a v2-only store, it listed all 6 users with their sessions and
printed 325 warnings. In both cases the old output is partial but never wrong
without warning. **Upgrade the reader before trusting reports over v2 data.**

### 8.5 Reader: no more silent private fallback

`TelemetryReader.select_sources` now records why each shared file was rejected
(`SHARED_REJECTION_REASONS`: `unreadable`, `no_valid_record`, `name_mismatch`,
`unknown_user`, `owner_mismatch`) and why it fell back to the caller's private
file (`no_shared_dir`, `no_shared_files`, `all_shared_rejected`).
`iter_events` passes that through the `warn` callback, which the CLI prints to
stderr. The warning names only the directory the operator chose, closed reason
names and counts. It never names a rejected file, its token, its user or
anything inside it. The owner/token gate itself is unchanged, and copied files
are still **not** read.

```console
$ python benchmark.py telemetry who --dir $S2/copied     # files cp'd by root: owner is root, not the writer
WARNING: no shared telemetry file in $S2/copied/users passed the owner/name check (5 rejected: owner_mismatch=5); reporting only your own private telemetry file. Files copied from another host fail the owner check: run the report on the node that wrote them.
USER	SESSIONS	LAST_SEEN	COMPLETED
No telemetry events.
```

When some files qualify and others do not, the report uses the good ones and
warns `skipped N shared telemetry file(s) in … (name_mismatch=1) …`. The
breakdown reports also print `source=shared|private` in their header line.
Cross-host aggregation still means running the report on each node (or the
§5.3 `jq` route, which has no gate or validation).

### 8.6 CLI reports (replacing the §5.2 script)

`benchmark.py telemetry summary` "Actions" now counts **run intents**
(`is_run_intent`), so outcomes are no longer counted twice. The section is
relabelled `Actions (run intents)`. The new subcommands all use
`TelemetryReader.iter_events`, so they keep the owner/token gate, the strict
per-version decoding and the `--days` window. They never start a telemetry
session or write anything.

| command | shows |
|---|---|
| `telemetry funnel` | per action and pooled: intents, blocked, cancelled (pre-attempt), attempted, completed, withheld, refused, failed, quit in run, open, SUCCESS = completed/intents (M1), PER_ATTEMPT = completed/attempted (M2) |
| `telemetry refusals` | refusals by reason × action |
| `telemetry failures` | failures by category × action |
| `telemetry blocks` | launch blocks by reason × action, and cancels by prompt × action (v1 cancels as `unrecorded_v1`) |
| `telemetry surfaces` | views per surface, TUI sessions viewing each, sessions viewing both tabs, launch contexts |
| `telemetry durations` | n/p10/p50/p90/max per launch context, histograms, sessions without `session_end` |
| `telemetry friction` | all of the above, plus TUI no-intent sessions (M5), attempt-without-completion, restored sessions, recovery (M7), time to first intent/attempt/completion (M6), time in validation review, validation-review outcomes, dataset loads, advanced overrides |

Options: `--days N`, `--dir PARENT_OF_USERS`, `--user NAME`,
`--context {cli_share,cli_rate,tui}`, `--app-version V` (validated like the
envelope field). Ratios whose denominator is under 30 are marked `*` (§6 rule
1). The output contains only counts, durations and closed vocabulary values.
It never contains usernames (except an explicit `--user` filter echoed in the
header), paths or record content.

### 8.7 Sample output (synthetic store)

`$S2` = `/tmp/claude-0/-home-user-autobench/d13cb994-08e3-5f72-b4d1-86adf775fd7d/scratchpad/telemetry2`.
`$S2/scripts/synth_store.py $S2/fleet` writes 6 real NSS accounts × 10–16
sessions over 27 days, using a fixed seed. Each account has 4 sessions of
hand-built v1 history, followed by records from the real v2 encoder. Files are
chowned to each account so the owner/token gate passes. Numbers are invented.

```console
$ python benchmark.py telemetry summary --dir $S2/fleet/shared
Surfaces
share  57
rate  18
validation_review  15
preset_help  7
advanced  11

Actions (run intents)
share_analysis  60
rate_analysis  25

Outcomes
completed  48
cancelled  9
refused  12
failed  2

$ python benchmark.py telemetry funnel --dir $S2/fleet/shared
window=30d  source=shared  users=6  sessions=81  events=504

Funnel per action (intents = blocked + cancelled + attempted)
ACTION          INTENTS  BLOCKED  CANCELLED  ATTEMPTED  COMPLETED  WITHHELD  REFUSED  FAILED  QUIT_IN_RUN  OPEN  SUCCESS  PER_ATTEMPT
share_analysis       60        8          3         49         36         4       11       2            0     0      60%          73%
rate_analysis        25        6          3         16         12         0        1       0            3     0     48%*         75%*
all                  85       14          6         65         48         4       12       2            3     0      56%          74%

BLOCKED and CANCELLED happen before any attempt; WITHHELD is the part of COMPLETED whose publication a strict posture withheld.
SUCCESS = COMPLETED / INTENTS; PER_ATTEMPT = COMPLETED / ATTEMPTED; * marks a denominator under 30.
19 completion(s) predate schema v2 and carry no publication_withheld flag (counted in COMPLETED, not in WITHHELD).

$ python benchmark.py telemetry funnel --context tui --app-version 3.1 --dir $S2/fleet/shared
window=30d  source=shared  users=6  sessions=41  events=325  context=tui  app_version=3.1
ACTION          INTENTS  BLOCKED  CANCELLED  ATTEMPTED  COMPLETED  WITHHELD  REFUSED  FAILED  QUIT_IN_RUN  OPEN  SUCCESS  PER_ATTEMPT
share_analysis       24        8          0         16          8         2        6       2            0     0     33%*         50%*
rate_analysis        18        6          3          9          5         0        1       0            3     0     28%*         56%*
all                  42       14          3         25         13         2        7       2            3     0      31%         52%*
```

`telemetry friction` prints the funnel and every breakdown in one report:

```console
$ python benchmark.py telemetry friction --dir $S2/fleet/shared   # abridged: funnel, refusals, failures omitted
Launch blocks by reason (before any attempt)
REASON                  SHARE_ANALYSIS  RATE_ANALYSIS  TOTAL
csv_missing                          1              0      1
entity_loading                       0              0      0
metric_missing                       6              0      6
total_missing                        0              1      1
rate_column_missing                  0              0      0
dimensions_missing                   0              0      0
validation_errors                    1              4      5
data_preparation_error               0              1      1
initialization_error                 0              0      0
total                                8              6     14

Cancels by prompt
PROMPT                  SHARE_ANALYSIS  RATE_ANALYSIS  TOTAL
validation_review                    0              2      2
accuracy_first_consent               0              0      0
clearing_spend                       0              1      1
quit_before_run                      0              0      0
quit_during_run                      0              3      3
unrecorded_v1                        3              0      3
total                                3              6      9

Surface usage
SURFACE            VIEWS  TUI_SESSIONS_VIEWING
share                 57                 57/57
rate                  18                 18/57
validation_review     15                 13/57
preset_help            7                  7/57
advanced              11                 11/57

TUI sessions viewing both tabs: 18/57
Launch contexts: cli_share=17  cli_rate=7  tui=57  unknown=0

Session duration (session_end.duration_s, seconds)
CONTEXT     N    P10    P50    P90    MAX
all        81   46.5  141.4  235.0  308.4
cli_share  17  103.9  183.8  215.2  236.3
cli_rate    7  130.8  141.4  185.6  192.3
tui        57   39.8  131.1  238.4  308.4

tui histogram: [0-10)s=2  [10-60)s=8  [60-300)s=46  [300-900)s=1  [900-3600)s=0  [3600-inf)s=0
Sessions without session_end (crash, kill or drop): 0

TUI friction
TUI sessions: 57
Sessions with no run intent: 14/57 (25%)
Sessions with an attempt but no completion: 12/57
Sessions restored from a saved form: 25/57
Sessions recovering after a bad outcome: 4/27
Time to first run intent: n=43 p50=87s p90=162s
Time to first attempt: n=35 p50=102s p90=171s
Time to first completion: n=23 p50=184s p90=252s
Time in validation review: n=15 p50=16s p90=33s
Validation review outcomes: proceeded=8  cancelled=2  blocked=5  no_decision=0
Dataset loads: loaded=37  not_found=7  header_read_failed=4  entity_list_failed=0
Advanced overrides: applied=2  empty=8  failed=1  exported=0  export_failed=0
```

To reproduce:

```console
cd /home/user/autobench
PYTHONPATH=$PWD /usr/local/bin/uv run python $S2/scripts/synth_store.py $S2/fleet
/usr/local/bin/uv run python benchmark.py telemetry friction --dir $S2/fleet/shared
git archive ddea32c core/telemetry | tar -x -C $S2/oldreader && touch $S2/oldreader/core/__init__.py
/usr/local/bin/uv run python $S2/scripts/old_reader_check.py $S2/oldreader $S2/fleet/shared who
```

### 8.8 Gap-by-gap disposition

| # | disposition |
|---|---|
| G1 | **Done.** `launch_blocked{csv_missing}`. The guard's message is not recorded. |
| G2 | **Done.** `metric_missing`, `total_missing`, `rate_column_missing`, `dimensions_missing` (share and rate). The 8th guard, added after the audit ("entity values still loading"), is `entity_loading`. |
| G3 | **Done**, as `action_cancelled{prompt=accuracy_first_consent}`, the same treatment as the clearing-spend decline (`prompt=clearing_spend`). The consent decline is the operator's choice, so it is a cancel, not a block. |
| G4 | **Done.** A forced exit (Proceed disabled or `should_abort`) is `launch_blocked{validation_errors}`; a voluntary Cancel is `action_cancelled{validation_review}`; see §8.2. Edits are in `_handle_validation_modal_result` and at the `push_screen` call. The `ValidationModal` class was not touched. |
| G5 | **Done.** `launch_blocked{data_preparation_error}`. The exception text stays in the toast and log only. |
| G6 | **Done.** `launch_blocked{initialization_error}`. |
| G7 | **Done.** `dataset_load{not_found \| header_read_failed \| entity_list_failed}`. No path, basename, size or column count. |
| G8 | **Done.** `dataset_load{loaded}`, with no props beyond the outcome. Column count deliberately not recorded. |
| G9 | **Done, outcome only.** `advanced_override{applied \| empty \| failed \| exported \| export_failed}`. **Not done:** recording *which* fields changed. Field names describe a named user's tuning behaviour, and the audit asked for privacy-owner review first. |
| G10 | **Done.** `session_restored{}`, emitted right after `session_start` when a saved form was applied. A new zero-prop event rather than a new key on `session_start`, so `session_start` stays v1-compatible (§8.4). |
| G11 | **Already derivable**. Now printed by `telemetry friction` (time to first intent, attempt and completion). |
| G12 | **Done** via `surface_viewed{validation_review}` + the next terminal; `telemetry friction` prints "Time in validation review". |
| G13 | **Done** (owner-approved). `action_completed.publication_withheld: bool`. |
| G14 | **Done.** `surface_viewed{preset_help \| advanced}`. Collapsing the panel emits nothing. |
| G15 | **Done.** `action_cancelled{quit_during_run \| quit_before_run}`; see §8.2 for the remaining race. |
| G16 | **Semantics documented, copy unchanged** (§8.3). |
| CLI pre-run failures | **Not done.** `benchmark.py` argument and preset errors happen before `start_session` (argparse exits, `_validate_preset_arg`), so there is no session to attach them to, and they are not TUI friction. |

### 8.9 Baseline caveat

As §6 rule 5 says, the v2-only events (`launch_blocked`, `dataset_load`,
`advanced_override`, `session_restored`, the new surfaces, cancel prompts,
`publication_withheld`) have **no Phase 0 baseline**. Ship this pass in a
release *before* the redesign, record at least 4 weeks on that `VERSION`,
and only then compare. M1 computed on v1 data (attempted + cancelled) and on v2
data (blocked + pre-attempt cancels + attempted) is **not** the same quantity.
The v2 denominator also includes `_fail_launch` presses that v1 never saw. For
a v1-comparable figure, subtract `BLOCKED` from `INTENTS`.

### 8.10 Schema v3 (Phase 2 PR 4, TUI layout shell)

v3 adds three closed enum values and nothing else: no new event, no new key.

| event | prop | new value | when |
|---|---|---|---|
| `action_cancelled` | `prompt` | `cancel_before_run` | the visible Cancel (`^G`, action bar) stopped the attempt before `action_attempted` (file read, consent or clearing-spend dialog, validation review) |
| `action_cancelled` | `prompt` | `cancel_during_run` | the visible Cancel took effect after `action_attempted`: core stopped at a phase boundary with `RunCancelled`, before any output was written. In `IN_RUN_CANCEL_PROMPTS`, like `quit_during_run` |
| `launch_blocked` | `reason` | `entity_not_found` | the large-entity filter (above 2,000 values) holds text that is not an exact entity; until v3 this block recorded nothing |

Two cancel values instead of one keep the §8.2 funnel exact: a single value
could not say whether an attempt had been recorded. Cancel telemetry is
recorded where the cancel *took effect*, not when the key was pressed, so a
Cancel that arrives after output writing started (the run then finishes
normally) records nothing extra and every attempt still ends exactly once.
The typed entity text is never recorded.

Versioning follows §8.4 exactly. `SCHEMA_VERSION = 3`,
`SUPPORTED_SCHEMA_VERSIONS = (1, 2, 3)`. `_EVENT_SCHEMAS_V2` is now frozen
(its enums are literal tuples in `events.py`), and `_EVENT_SCHEMAS_V3` is
current. `session_start`/`session_end` are still written as v1; every other
event is written as v3.

| reader | data | behaviour |
|---|---|---|
| new (v3) | v1, v2 or mixed v1+v2+v3 files | Reads everything, each record against its own catalog (`test_new_reader_reads_mixed_v1_v2_and_v3_file`). v3-only values inside a v1 or v2 record are rejected (`test_v3_values_decode_only_in_a_v3_record`). |
| installed v2 | mixed v2 + v3 | No crash. v1/v2 records and every `session_start`/`session_end` are read; each v3 record is skipped with the counted warning `skipped N record(s) with an unsupported schema_version (this reader supports 1, 2); upgrade Autobench to read them.` (checked by running the v2 package from `74e9025` against a v3 store) |
| installed v1 | v3 records | As for v2 records in §8.4: skipped with `unsupported schema_version: 3`, sessions still counted. |

The funnel column `QUIT_IN_RUN` is renamed `CANCEL_IN_RUN`, because it now
counts both in-run prompts.

### 8.11 Schema v4 (Phase 2 PR 6, verification)

v4 adds one closed enum value and nothing else: no new event, no new key.

| event | prop | new value | when |
|---|---|---|---|
| `launch_blocked` | `reason` | `citi_entity_missing` | "A Citi competitor will receive this output" is ticked and no exact Citibank entity is chosen (blank, or large-list filter text that matches no value) |

Until v4 this case reached core. The TUI recorded `action_attempted`, then
core raised `RunBlocked("citibank_entity_name is required when a Citi
competitor receives the output")`, recorded as `action_refused` /
`compliance_policy`. Core still refuses it exactly as before. The TUI now
stops the run at the readiness check, using the same condition, so the
attempt never starts. Neither the Citibank entity, the typed filter text nor
the core message is recorded (`test_tui_v4_citi_block_records_only_closed_values`).

**Effect on §6.** Guardrail G-a (`refused{compliance_policy}` ÷ attempted) can
drop slightly after this release, because these runs move from REFUSED to
BLOCKED. That drop is the reclassification, not weaker enforcement. When
comparing with a pre-v4 window, move `launch_blocked{citi_entity_missing}`
back into the compliance-policy refusals.

Versioning follows §8.4 exactly. `SCHEMA_VERSION = 4`,
`SUPPORTED_SCHEMA_VERSIONS = (1, 2, 3, 4)`. `_EVENT_SCHEMAS_V3` is now frozen
(its enums are literal tuples in `events.py`) and `_EVENT_SCHEMAS_V4` is
current. `session_start`/`session_end` are still written as v1.

| reader | data | behaviour |
|---|---|---|
| new (v4) | mixed v1 + v2 + v3 + v4 | Reads everything, each record against its own catalog (`test_new_reader_reads_mixed_v1_to_v4_file`). `citi_entity_missing` inside a v1, v2 or v3 record is rejected (`test_v4_values_decode_only_in_a_v4_record`). |
| installed v3 | mixed v1–v4 | No crash. v1–v3 records and every `session_start`/`session_end` are read. Each v4 record is skipped with `skipped 4 record(s) with an unsupported schema_version (this reader supports 1, 2, 3); upgrade Autobench to read them.` Checked by running the real v3 package (`git archive 5da85ae core/telemetry`) against a v4 store. |
| installed v2 | mixed v1–v4 | The same, with `supports 1, 2` (package from `74e9025`). |
| installed v1 | v2–v4 records | Each skipped with `unsupported schema_version: N`; sessions are still counted (package from `ddea32c`). |
