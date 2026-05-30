# Implementation Plan: Fixes 1-4 (Code + Docs)

## Purpose

This plan covers the four requested changes:

1. Fix `low_distortion` crash in time-aware runs (`_TIME_TOTAL` reserved-prefix error).
2. Enforce strategic intent for `strategic_consistency` (single global weight-set behavior).
3. Improve user-facing infeasibility signaling (logs + summary visibility).
4. Update documentation (`README.md` and `docs/CORE_TECHNICAL_DOC.md`) to reflect real behavior, constraints, and CSV semantics.

The plan is designed to be executable step-by-step with strict validation after each major change, aligned with `AGENTS.md`.

---

## Guiding Constraints

- Preserve Mastercard Control 3.2 logic; do not weaken privacy rule enforcement.
- Do not silently change analytical semantics without explicit config/metadata traceability.
- Keep CLI/TUI consistency (shared `core/` behavior).
- Maintain backward compatibility where possible; if behavior changes, document clearly.
- Run required verification after each major step:
  - `py scripts/perform_gate_test.py`
  - `py -m pytest`

---

## Scope and File Impact

### Primary code files

- `core/global_weight_optimizer.py`
- `core/category_builder.py`
- `core/dimensional_analyzer.py`
- `benchmark.py`
- `utils/config_manager.py` (if adding/normalizing config key[s])
- `utils/validators.py` (if schema extension is required)

### Test files (to add/update)

- `tests/` (new targeted regression tests for steps 1 and 2)
- Possibly extend existing integration/unit test modules that already cover optimizer/preset behavior.

### Documentation files

- `README.md`
- `docs/CORE_TECHNICAL_DOC.md`
- Optional release-note style entry in `docs/` if the repo uses change logs/plans there.

---

## Workstream 1: Fix `low_distortion` time-aware crash

## Problem statement

In time-aware runs, per-dimension fallback may incorrectly try to treat internal synthetic dimensions (e.g., `_TIME_TOTAL`) as user dimensions, causing:

- reserved-prefix validation failure in `CategoryBuilder.validate_dimension_names`
- run abortion for preset(s) that should complete.

## Root-cause hypothesis

During violation-dimension collection/retry flow in `global_weight_optimizer`, internal constraint dimensions are being passed into user-dimension category builders without filtering.

## Implementation steps

1. **Trace dimension-flow path**
   - Confirm where violation dimensions are computed and iterated.
   - Identify where `_TIME_TOTAL`/internal prefixes can enter per-dimension solve path.

2. **Add internal-dimension filter guard**
   - Introduce a helper (single source of truth) to classify internal/system dimensions.
   - Filter these before calling `_build_categories`/per-dimension solving.
   - Ensure this applies to both LP and Bayesian fallback branches.

3. **Defensive handling**
   - If an internal dimension is detected in a context that expects user dimensions:
     - skip safely,
     - log at `DEBUG`/`INFO` with clear reason,
     - never raise user-facing fatal error for this path.

4. **Regression test(s)**
   - Add a targeted test covering time-aware + `low_distortion` flow with internal constraints present.
   - Assert: no exception, output artifacts generated, and no reserved-prefix error.

## Acceptance criteria

- `low_distortion` time-aware run completes successfully.
- No `_TIME_TOTAL` reserved-prefix crash.
- Existing non-time-aware behavior unchanged.

## Verification gate

- `py scripts/perform_gate_test.py`
- `py -m pytest`

---

## Workstream 2: Enforce strategic consistency intent

## Decision to finalize before coding

Choose one explicit product behavior (recommended: **strict single-global mode**):

- If preset/config says strategic consistency, no per-dimension fallback is allowed.
- If global constraints cannot satisfy all categories, keep global result and report violations/slack/diagnostics, but do not switch methods.

Alternative (if product prefers flexibility): allow fallback but rename/document preset intent accordingly. This plan assumes strict single-global for alignment with current docs intent.

## Implementation steps

1. **Add explicit config contract**
   - Add config flag (example): `optimization.enforce_single_weight_set: true/false`.
   - Map `strategic_consistency` preset to `true`.
   - Keep default `false` for other presets (unless explicitly set).

2. **Wire config through orchestration**
   - Ensure value is sourced from merged `opt_config` (not raw CLI args).
   - Pass into `DimensionalAnalyzer` and optimizer flow.

3. **Gate fallback behavior**
   - In global optimization flow:
     - if `enforce_single_weight_set=true`, skip per-dimension LP/Bayesian fallback paths.
     - keep global weights and method labeling as global.
     - preserve diagnostics/violation reporting.

4. **Weight-method reporting consistency**
   - Ensure `Weight Methods` tab reflects global method only under strict mode.
   - Ensure metadata/summary indicates strict single-weight-set mode used.

5. **Regression tests**
   - Test strategic mode with structurally hard data:
     - assert no per-dimension method labels,
     - assert run completes with diagnostics,
     - assert behavior remains deterministic with greedy controls where applicable.

## Acceptance criteria

- Strategic run does not silently switch dimensions to per-dimension methods when strict mode is on.
- Method and summary outputs are consistent with configured intent.
- Other presets retain existing fallback behavior.

## Verification gate

- `py scripts/perform_gate_test.py`
- `py -m pytest`

---

## Workstream 3: Improve infeasibility signaling

## Goal

Users should not need to discover structural infeasibility only by manually opening debug tabs.

## Implementation steps

1. **Structured infeasibility summary object**
   - Build a compact run-level summary from structural diagnostics:
     - count of infeasible categories,
     - worst margin over cap,
     - top impacted dimensions/categories,
     - whether infeasibility is structural vs solver/fallback.

2. **Logging improvements**
   - Add clear `WARNING` log block when infeasibility exists.
   - Include action hint (e.g., adjust dimensions/preset/tolerance expectations).

3. **Summary-sheet visibility**
   - Add a concise section in workbook summary:
     - `Structural Infeasibility Detected: Yes/No`
     - key counts and worst margin.

4. **CLI run summary visibility**
   - Print a compact terminal summary after run completion (without noisy detail).

5. **Tests**
   - Unit/integration checks for presence of warning and summary fields when infeasible.
   - Ensure no false positives on feasible datasets.

## Acceptance criteria

- Infeasible runs clearly flag the condition in logs and summary output.
- Feasible runs remain clean (no noisy false alarms).

## Verification gate

- `py scripts/perform_gate_test.py`
- `py -m pytest`

---

## Workstream 4: Documentation updates (`README.md`, `CORE_TECHNICAL_DOC.md`)

## Update goals

- Align documented behavior with implemented behavior and edge cases.
- Remove ambiguity on strategic mode, structural infeasibility, and CSV semantics.

## Documentation changes

1. **Strategic mode semantics**
   - Explain strict single-global mode (if enabled) and its tradeoff.
   - Clarify what happens when constraints are not fully satisfiable.

2. **Structural infeasibility section**
   - Explain what it means, where it appears (`Structural Summary`, `Structural Detail`), and expected user interpretation.

3. **CSV semantics**
   - Explicitly state:
     - share/rate exported balanced totals are peer-weighted totals,
     - target contributions are handled separately in share/rate formula fields.

4. **Known edge cases**
   - Time-aware sparse categories and unavoidable high-concentration buckets.
   - How tolerance and preset choice affect observed compliance in those buckets.

5. **Troubleshooting additions**
   - Include practical guidance when users see residual violations in structurally infeasible slices.

## Acceptance criteria

- README guidance matches actual runtime behavior and output sheets.
- Technical doc formula/flow text matches implemented fallback and strict-mode logic.
- No conflicting statements across docs.

## Verification gate

- Manual docs consistency review after code finalization.
- Spot-check command examples against current CLI options.

---

## End-to-End Validation Strategy

After completing all four workstreams:

1. **Mandatory regression**
   - `py scripts/perform_gate_test.py`
   - `py -m pytest`

2. **Focused FortBrasil logical validation**
   - Re-run representative share/rate commands for:
     - `balanced_default`
     - `compliance_strict`
     - `strategic_consistency`
     - `low_distortion` (must no longer crash)
   - Verify workbook tabs and CSV reproduction checks against weights.

3. **Behavioral assertions**
   - `low_distortion` time-aware completes.
   - strategic strict mode keeps global methods only (if configured).
   - infeasibility warnings/summaries appear when expected.
   - docs reflect final behavior exactly.

---

## Risk Register and Mitigations

- **Risk:** Behavior change for existing strategic users.
  - **Mitigation:** config flag + explicit docs + summary metadata.

- **Risk:** Over-filtering dimensions and skipping legitimate user dimensions.
  - **Mitigation:** centralized internal-dimension classifier + targeted tests.

- **Risk:** Increased log noise.
  - **Mitigation:** concise warning blocks, detailed info only in debug.

- **Risk:** Docs drift after final tweaks.
  - **Mitigation:** docs update as final step, tied to final code state.

---

## Delivery Checklist

- [x] Workstream 1 implemented and verified
- [x] Workstream 2 implemented and verified
- [x] Workstream 3 implemented and verified
- [x] Workstream 4 implemented and reviewed
- [x] Gate test and pytest pass after major implementation steps
- [x] Final focused FortBrasil logical validation completed
- [x] Final change summary prepared with file-level references

## Current Status

- Last updated: 2026-02-02
- Implemented:
  - Internal-dimension filtering for per-dimension fallback/re-weighting.
  - Strict single-weight-set mode (`optimization.constraints.enforce_single_weight_set`), enabled in `strategic_consistency`.
  - Structural infeasibility warnings and summary surfacing in logs and report summaries.
  - README and core technical documentation updates for strategic behavior, structural infeasibility, and CSV semantics.
- Verification completed:
  - `py scripts/perform_gate_test.py` (pass)
  - `py -m pytest` (pass)
  - Re-validated on 2026-02-02:
    - `py scripts/perform_gate_test.py` -> Passed 17, Failed 0, Errors 0
    - `py -m pytest` -> 35 passed
