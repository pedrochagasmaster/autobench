# Plan 012: Unify TUI request assembly with the CLI's AnalysisRunRequest contract

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat e0950c4..HEAD -- tui_app.py core/contracts.py utils/config_overrides.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED
- **Depends on**: none (plan 003's integration test is a helpful but not required net)
- **Category**: tech-debt
- **Planned at**: commit `e0950c4`, 2026-06-10

## Why this matters

The CLI builds its `AnalysisRunRequest` via `AnalysisRunRequest.from_namespace(mode, args)` (`core/contracts.py:~151-162`), but the TUI hand-assembles the same dataclass field-by-field across ~70 lines (`tui_app.py:1122-1192`). The two assembly paths have already drifted: the TUI hardcodes `per_dimension_weights = False`, and has no wiring for `lean` or `audit_package` even though both are CLI features. Every new CLI flag silently ships without TUI parity. A single `from_widget_values` constructor next to `from_namespace` makes drift structurally visible (one file to update) and testable.

## Current state

- `core/contracts.py` (~lines 84-162) — `AnalysisRunRequest` dataclass + `from_namespace(mode, args)` classmethod. Read both fully; `from_namespace` is the canonical mapping.
- `tui_app.py:1122-1192` — the hand-built request. Precise structure (read it before editing): the `AnalysisRunRequest(...)` is **constructed** at 1122-1137 with initial kwargs; lines **1138-1153** are a preset/compliance block (conditional `compliance_posture`, `acknowledge_accuracy_first`, with early `return`s) that is NOT request assembly and must stay inline; lines 1155-1192 then mutate request fields in mode-specific branches, including the hardcoded `per_dimension_weights = False` (~line 1169).
- `utils/config_overrides.py:34-59` — `ADVANCED_FIELD_SPECS` (a `List[ConfigFieldSpec]`) maps TUI advanced-panel inputs to config override keys; these flow separately from the request object. Don't change this mechanism; just don't break it.
- TUI tests: `tests/test_tui_smoke.py` (happy-path Share run with `validate_input=False`) and `tests/test_tui_contracts.py` (widget/config contract checks) — the second is the natural home for new parity tests.
- TUI conventions (AGENTS.md): validation-first flow via `ValidationModal`; analysis runs on a worker thread. Two distinct DataFrame fields exist on the request: the validation flow sets `request.prepared_dataset` (`tui_app.py:1220-1226`), and the confirmed-run path sets `request.df` later (~line 1264). They are different fields — do not conflate them; both stay as post-assembly assignments.
- `from_namespace` has special handling for `control3_overrides` (`core/contracts.py:157-161`); the TUI sets none of those today.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| TUI tests | `py -m pytest tests/test_tui_smoke.py tests/test_tui_contracts.py -q` | all pass |
| Full suite | `py -m pytest tests/ -q` | all pass |
| Gate | `py scripts/perform_gate_test.py` | exit 0 (CLI unaffected) |

## Scope

**In scope**:
- `core/contracts.py` (add one classmethod)
- `tui_app.py` (replace the hand-assembly block)
- `tests/test_tui_contracts.py` (extend)

**Out of scope**:
- The validation-first modal flow and worker-thread structure in `tui_app.py` (~lines 1195-1245) — known-fragile (audit CORRECTNESS-12); do not restructure it here.
- Adding *new* TUI widgets for `lean`/`audit_package` — parity of the assembly mechanism first; new widgets are follow-up. Where no widget exists, the constructor takes the dataclass default.
- `benchmark.py` / `from_namespace` behavior.

## Git workflow

- Branch: `advisor/012-tui-request-parity`
- Commit message style: `refactor: build TUI request via shared constructor`
- Do NOT push or open a PR unless instructed.

## Steps

### Step 1: Inventory the current TUI assignments

Read `tui_app.py:1122-1192` and produce a table (in the commit message or PR description): request field → widget id / hardcoded value / unset. Cross-check against the `AnalysisRunRequest` field list. Flag fields the TUI never sets (expected: `lean`, `audit_package`, possibly others).

**Verify**: `rg -n "request\.\w+ ?=" tui_app.py` — every distinct field name in that output within lines 1122-1192 appears in your table (fields assigned outside that range, e.g. `prepared_dataset`/`df`, are post-assembly and excluded).

### Step 2: Add `AnalysisRunRequest.from_widget_values`

In `core/contracts.py`, next to `from_namespace`:

```python
@classmethod
def from_widget_values(cls, mode: str, values: Dict[str, Any]) -> "AnalysisRunRequest":
    """Build a request from a flat dict of TUI widget values.

    Keys mirror the dataclass field names. Missing keys take dataclass
    defaults, keeping TUI behavior aligned with CLI defaults.
    """
    field_names = {f.name for f in dataclasses.fields(cls)}
    unknown = set(values) - field_names
    if unknown:
        raise ValueError(f"Unknown request fields from TUI: {sorted(unknown)}")
    return cls(mode=mode, **{k: v for k, v in values.items() if k in field_names})
```

(Adapt to the actual dataclass: if `mode` is not a field or is named differently, follow `from_namespace`'s handling. The `unknown`-key guard is the drift alarm — keep it.)

**Verify**: `py -m pytest tests/ -q` → all pass (nothing uses it yet).

### Step 3: Replace the TUI assembly block

In `tui_app.py`, replace the request **construction** (1122-1137) and the mode-branch **field mutations** (1155-1192) with: build a flat `values: dict` from widgets (same reads as today, including `per_dimension_weights=False` — preserve current behavior exactly, just centralize it; the mode-specific branches contribute their keys to the dict instead of mutating the request), then call `AnalysisRunRequest.from_widget_values(mode, values)` once. The preset/compliance block at 1138-1153 (with its early `return`s) stays inline between dict-building and construction — it is control flow, not assembly. Keep the `prepared_dataset`/`df` injections and validation flow untouched as post-assembly assignments.

**Verify**: `py -m pytest tests/test_tui_smoke.py -q` → passes (the smoke test runs a full Share analysis through the TUI).

### Step 4: Add the parity test

In `tests/test_tui_contracts.py`:
1. `from_widget_values("share", {...minimal valid keys...})` equals an `AnalysisRunRequest` built with the same kwargs directly.
2. Unknown key raises `ValueError` (the drift alarm works).
3. **Parity audit test**: for every field of `AnalysisRunRequest`, assert it is either (a) present in the TUI's widget-values builder (import or replicate the key list — if the TUI builds the dict inline, extract the key list into a module-level constant in `tui_app.py`, e.g. `TUI_REQUEST_FIELDS`, so the test can import it), or (b) listed in an explicit `TUI_UNSUPPORTED_FIELDS` constant with a comment (e.g. `lean`, `audit_package`). New CLI fields then fail this test until someone consciously classifies them.

**Verify**: `py -m pytest tests/test_tui_contracts.py -q` → all pass.

### Step 5: Full verification

**Verify**: `py -m pytest tests/ -q` → all pass; `py scripts/perform_gate_test.py` → exit 0.

## Test plan

See Step 4 — equivalence, drift alarm, and the field-classification parity test. Pattern: existing contract tests in `tests/test_tui_contracts.py`.

## Done criteria

- [ ] `tui_app.py` no longer assigns `AnalysisRunRequest` fields one-by-one post-construction; it builds a dict and calls `from_widget_values`
- [ ] Every `AnalysisRunRequest` field is classified (supported widget or `TUI_UNSUPPORTED_FIELDS`) and the test enforces it
- [ ] `py -m pytest tests/ -q` exits 0 (incl. TUI smoke)
- [ ] `py scripts/perform_gate_test.py` exits 0
- [ ] `plans/README.md` status row updated

## STOP conditions

- The TUI smoke test fails after Step 3 in the worker/modal flow (not in request construction) — you've disturbed the threading path; revert and retry with a strictly mechanical replacement. If it still fails, report (audit CORRECTNESS-12 suspects this area is fragile).
- `AnalysisRunRequest` has mutable post-construction mutation requirements (fields set *after* validation modal, e.g. `df`) that `from_widget_values` can't express — keep those specific post-assignments and note them; if more than 2-3 fields need post-assignment, report.

## Maintenance notes

- The parity test is the long-term value: every new CLI flag now forces an explicit TUI decision. Reviewers should refuse additions to `TUI_UNSUPPORTED_FIELDS` without a comment justifying why.
- Follow-up candidates (not this plan): TUI widgets for `lean` and `audit_package`; renaming the `analyze_distortion` widget id to match the `--analyze-impact` CLI naming (audit DEBT-11).
