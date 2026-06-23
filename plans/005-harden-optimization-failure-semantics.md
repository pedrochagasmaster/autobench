# Plan 005: Make optimization-failure paths report honest compliance state (no false "primary cap passed")

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat e0950c4..HEAD -- core/global_weight_optimizer.py core/solvers/heuristic_solver.py core/analysis_run.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: plans/001-privacy-rule-boundary-tests.md, plans/003-analysis-run-integration-test.md, plans/004-fix-compliance-violation-double-count.md
- **Category**: bug
- **Planned at**: commit `e0950c4`, 2026-06-10

## Why this matters

When every solver fails (global LP, subset search, heuristic), the run does **not** abort. `WeightingSolveState` keeps its defaults, `assemble_weighting_result` computes `primary_passed = not residual_cap_violation` from those defaults (`False` → `primary_passed=True`), and the weighting compliance state can read `strict_compliant` while the analysis proceeds with identity multipliers (every peer weight 1.0) that were never validated against the privacy caps. Two adjacent bugs compound this: the heuristic solver reports `success=True` even when residual cap violations exceed the tolerance band (it only fails on violations when `tolerance <= 0`), and the heuristic fallback path marks `state.converged = True` even when the solver says it did not converge. There is a final safety net — `build_strict_final_validation` re-checks balanced shares — but the weighting-level compliance metadata (`weighting_compliance_state`, the "verdict" written to reports and audit logs) is wrong, and the run should never claim `strict_compliant` weighting when no solver produced weights. Note the repo already hard-fails for insufficient peers (`raise ValueError` at `core/global_weight_optimizer.py:114-122`) — total optimization failure deserves the same honesty.

## Current state

- `core/global_weight_optimizer.py:60-84` — pipeline: `solve_full_problem` → `decide_subset_fallback` → `run_heuristic_fallback` → (if converged) finalize/post-validate → `assemble_weighting_result` **always** runs, converged or not.
- `core/global_weight_optimizer.py:374-375` — total-failure branch just logs:

```python
else:
    logger.warning("Heuristic global optimization failed; proceeding without global weights.")
```

- `core/global_weight_optimizer.py:700-722` — `assemble_weighting_result` (the mislabeling):

```python
residual_cap_violation = bool(
    (state.residual_cap_violation or last_lp_stats.get("residual_cap_violation", False))
    if state is not None
    else last_lp_stats.get("residual_cap_violation", False)
)
...
primary_passed = not residual_cap_violation
secondary_passed = residual_violations == 0 and not residual_additional_violation
if primary_passed and secondary_passed and not relaxation_used:
    verdict = "strict_compliant"
```

  When nothing converged, `state.residual_cap_violation` is the dataclass default (`False`) and `last_lp_stats` is stale/empty → verdict `strict_compliant`.
- `core/global_weight_optimizer.py:358-371` — heuristic fallback sets `state.converged = True` even when `heuristic_result.success` is `False` ("using best-effort weights"). It does record `state.heuristic_converged` and the residual flags — those propagate; the issue is only that `converged=True` + possible `strict_compliant` verdict overstate the result.
- `core/solvers/heuristic_solver.py:238-262` — residual check and success semantics:

```python
max_share = max_concentration + tolerance
...
        if adjusted_share > max_share + 1e-9:
            residual_cap_violation = True
...
success = bool(result.success)
if tolerance <= 0.0 and (residual_cap_violation or residual_additional_violation):
    success = False
```

  `residual_cap_violation` already means "exceeds cap **plus** tolerance" — yet with `tolerance > 0` the success flag is not cleared. A solution violating caps beyond the user's own tolerance band is reported as a success.
- `core/dimensional_analyzer.py` — empty `global_weights` makes `_get_peer_multiplier` fall back to `1.0` (identity weights) around line 803.
- Insufficient-peers precedent (the pattern to follow), `core/global_weight_optimizer.py:107-122`: sets `analyzer.compliance_blocked_reason`, logs, raises `ValueError`. `core/analysis_run.py` catches that and produces a `blocked` compliance summary (see `build_compliance_summary`'s `blocked_reason` parameter, `core/compliance.py:255-271`).
- Tests covering fallbacks: `tests/test_global_weight_optimizer_fallbacks.py` (uses `_FakeAnalyzer`, `_FakeLpSolver`, `_FakeHeuristicSolver`) — extend these.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Fallback tests | `py -m pytest tests/test_global_weight_optimizer_fallbacks.py tests/test_solvers.py -q` | all pass |
| Integration | `py -m pytest tests/test_analysis_run_integration.py -q` | all pass |
| Full suite | `py -m pytest tests/ -q` | all pass |
| Gate | `py scripts/perform_gate_test.py` | exit 0 |
| Typecheck | `py -m mypy core/ utils/` | exit 0 |

## Scope

**In scope**:
- `core/global_weight_optimizer.py`
- `core/solvers/heuristic_solver.py`
- `tests/test_global_weight_optimizer_fallbacks.py`, `tests/test_solvers.py` (extend)
- `core/analysis_run.py` — only if the new failure exception needs explicit handling there (check how the insufficient-peers `ValueError` is caught and mirror it).

**Out of scope**:
- `core/compliance.py` — violation accounting was fixed in plan 004; do not touch.
- `core/solvers/lp_solver.py` — LP success semantics are not part of this finding.
- Behavior of *successful* runs — gate cases must produce identical outputs.
- The `accuracy_first` / `best_effort` posture semantics — those postures may legitimately keep best-effort weights; this plan only fixes the *labeling* and the *total-failure* path.

## Git workflow

- Branch: `advisor/005-optimization-failure-semantics`
- Commit per step; message style: `fix: <imperative>` (e.g. `fix: fail weighting verdict when no solver converged`)
- Do NOT push or open a PR unless instructed.

## Steps

### Step 1: Heuristic solver — decouple success from tolerance

In `core/solvers/heuristic_solver.py:260-262`, change so any residual violation clears success regardless of tolerance (the residual check at line 240-258 already incorporates the tolerance into `max_share`, so a residual violation is by definition *beyond* the allowed band):

```python
success = bool(result.success)
if residual_cap_violation or residual_additional_violation:
    success = False
```

Keep `stats['residual_cap_violation']` / `stats['residual_additional_violation']` exactly as-is.

Add a unit test in `tests/test_solvers.py`: construct a heuristic request with `tolerance=5.0` where the best achievable solution still exceeds `cap + tolerance` for some category → assert `result.success is False` and `result.stats['residual_cap_violation'] is True`. Model on the structurally-infeasible case at `tests/test_solvers.py:173-197` — note that exemplar uses `tolerance=0.0`; your variant changes only the tolerance (a structurally dominant peer, e.g. one peer holding ~90% of every category, stays infeasible at any tolerance ≤ 5.0 against a 25% cap).

**Verify**: `py -m pytest tests/test_solvers.py -q` → all pass.

### Step 2: Total-failure path raises instead of proceeding

In `core/global_weight_optimizer.py`, in `run_heuristic_fallback`'s `else` branch (line 374-375), follow the insufficient-peers precedent:

```python
else:
    analyzer.compliance_blocked_reason = "optimization_failed"
    logger.error(
        "Global LP, subset search, and heuristic optimization all failed; "
        "aborting analysis to avoid emitting unvalidated identity weights."
    )
    raise ValueError(
        "Weight optimization failed: no solver produced a feasible weight set. "
        "See Structural Diagnostics for infeasibility causes."
    )
```

Before writing this, check how `core/analysis_run.py` handles the insufficient-peers `ValueError` (search for `insufficient_peers` and `compliance_blocked_reason` in `core/analysis_run.py` and `core/compliance.py`). Expected outcome of that check: `_handle_optimization_failure` (`core/analysis_run.py:843-861`) propagates **any** `analyzer.compliance_blocked_reason` generically (line ~850) — it does not match on the specific string, so `optimization_failed` should flow into a `blocked` compliance summary with **no** `analysis_run.py` edit. Only if you find string-specific matching does `core/analysis_run.py` need a change.

Extend `tests/test_global_weight_optimizer_fallbacks.py`: configure the fakes so LP fails, subset search returns nothing, and the heuristic returns `None` → assert `ValueError` is raised and `compliance_blocked_reason == "optimization_failed"`.

**Verify**: `py -m pytest tests/test_global_weight_optimizer_fallbacks.py -q` → all pass.

### Step 3: Heuristic best-effort acceptance is labeled, never `strict_compliant`

In `run_heuristic_fallback` (line 358-371) the path where `heuristic_result` exists but `heuristic_result.success` is `False` currently proceeds with best-effort weights. Keep that behavior (postures other than strict legitimately want best-effort weights — blocking is plan 006's job at the artifact layer), but guarantee the verdict can't be `strict_compliant`:

In `assemble_weighting_result`, when `state is not None and state.heuristic_converged is False`, force the verdict to at most `best_effort`:

```python
heuristic_failed = state is not None and state.heuristic_converged is False
if primary_passed and secondary_passed and not relaxation_used and not heuristic_failed:
    verdict = "strict_compliant"
elif primary_passed and secondary_passed:
    verdict = "best_effort"
else:
    verdict = "non_compliant"
```

Note `state.heuristic_converged` is `None` when the heuristic never ran (LP success path) — `is False` correctly distinguishes "ran and failed" from "didn't run".

Add a test: fakes where heuristic returns weights with `success=False` but no residual violations → `WeightingResult.compliance_state.verdict == "best_effort"`, not `strict_compliant`. The existing `_NonConvergedHeuristicSolver` fake (`tests/test_global_weight_optimizer_fallbacks.py:52-60`) sets `residual_additional_violation=True`, so it cannot serve here — write a **new** fake that returns `success=False` with both residual flags absent/false.

**Verify**: `py -m pytest tests/test_global_weight_optimizer_fallbacks.py -q` → all pass.

### Step 4: Full verification

**Verify**, in order:
1. `py -m pytest tests/ -q` → all pass.
2. `py scripts/perform_gate_test.py` → exit 0 (all 18 cases — none of the gate scenarios hit total solver failure, so outputs must be unchanged).
3. `py -m mypy core/ utils/` → exit 0.

## Test plan

- `tests/test_solvers.py`: heuristic `success=False` on residual violation with positive tolerance.
- `tests/test_global_weight_optimizer_fallbacks.py`: total failure raises `ValueError` with `optimization_failed` reason; failed-heuristic acceptance yields `best_effort` verdict; existing fallback tests still pass.
- Pattern: existing `_Fake*` fixtures in `tests/test_global_weight_optimizer_fallbacks.py`.

## Done criteria

- [ ] `rg -n "proceeding without global weights" core/global_weight_optimizer.py` returns no matches (exit code 1)
- [ ] With all solvers failed, `calculate_global_privacy_weights` raises `ValueError` (test proves it)
- [ ] Heuristic residual violation ⇒ `success=False` independent of tolerance (test proves it)
- [ ] `state.heuristic_converged is False` ⇒ verdict ≠ `strict_compliant` (test proves it)
- [ ] `py -m pytest tests/ -q`, `py scripts/perform_gate_test.py`, `py -m mypy core/ utils/` all exit 0
- [ ] `plans/README.md` status row updated

## STOP conditions

- The gate fails after Step 1 or Step 3 — a gate scenario actually depends on tolerant heuristic "success" or on heuristic best-effort being labeled strict. Report which case and stop; that's a posture-policy decision for the maintainer.
- `core/analysis_run.py` has no generic handler for the insufficient-peers `ValueError` (i.e., the exception propagates as a raw crash today) — report; wiring a new error-handling layer is beyond this plan.
- Step 3's `heuristic_converged` is not reliably `None`/`True`/`False` tri-state (e.g. it's set on LP paths too) — re-read `WeightingSolveState` and report the discrepancy.

## Maintenance notes

- Plan 006 builds on this: artifact-level blocking for strict posture assumes verdicts are now honest.
- The single-weight mode path (`core/global_weight_optimizer.py:245-246, 565-569`) still knowingly keeps violating global weights with log warnings under `strategic_consistency` — deliberately out of scope here (posture-policy question, audit finding CORRECTNESS-06); reviewers should be aware it remains.
- Reviewers should scrutinize: that no gate case output changed, and that `optimization_failed` produces `run_status="blocked"` end to end.
