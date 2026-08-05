# Plan 004: Prove Maximum Safe Coverage with direct HiGHS

> **Executor contract**: Read this complete file before you change source files.
> Follow each step in order. Run every required check. Honor every STOP condition.
> Do not weaken a privacy rule. Do not publish, deploy, or commit production data.

## Copy-ready cloud-agent prompt

```text
Work in the Autobench repository.

Start from commit 1c252ba on branch plan-003-coverage-solver-scale.
Read AGENTS.md, CONTRIBUTING.md, plans/002-maximize-safe-coverage.md,
plans/003-scale-maximum-safe-coverage-solver.md, and
plans/004-prove-maximum-safe-coverage-with-highs.md completely.
Treat Plan 004 as the execution contract.

Replace the Maximum Safe Coverage SciPy MILP call with direct highspy.
Keep the normalized Plan 003 model and all public contracts unchanged.
Delete the obsolete SciPy MILP path after the HiGHS proof gate passes.
Do not create a second solver setting or a compatibility path.

Build a complete neutral MIP start with the existing policy evaluator.
Use the start only as a search aid.
Require an optimal status, zero MIP gaps, a matching dual bound, and verifier success.
Record separate times for the first incumbent and the final proof.

First test the direct maximization strategy on real Getnet 2025Q1.
If it fails, test the stated K-plus-one infeasibility strategy once.
Do not tune hidden solver options or run an open-ended parameter search.
Stop if neither exact strategy proves Stage 1 within 15 minutes.

Use test-first development. Use only sanitized fixtures in the Autobench repository.
Run protected Getnet acceptance outside the Autobench repository.
Keep all Getnet output isolated. Never replace accepted output.
Do not push, deploy, merge, or release.
Stop and report when a STOP condition occurs.
```

## Status

- **Execution**: TODO
- **Priority**: P0
- **Effort**: L
- **Risk**: HIGH
- **Depends on**: Plan 003 at commit `1c252ba`
- **Category**: exact privacy solver proof
- **Planned at**: Autobench commit `1c252ba`, 2026-08-05

## Decision

Use direct `highspy` for Maximum Safe Coverage.

Do not add a user solver option.

Do not keep the SciPy MILP path after the proof gate passes.

Keep SciPy for other Autobench functions that already use it.

## Goal

Prove the exact Maximum Safe Coverage result for all five Getnet quarters.

Complete each Stage 1 proof within 15 minutes on node03.

Keep the current privacy result, certificate, CLI, TUI, and Python contracts.

Keep the independent verifier as the final release authority.

## Non-goals

- Do not change the Control 3.2 policy.
- Do not change the 4/35 or 10/40 rule semantics.
- Do not change the Citi overlay semantics.
- Do not add a new privacy release mode.
- Do not add a solver choice to any user interface.
- Do not add HiPO or `highspy[extras]`.
- Do not add Pyomo, OR-Tools, or another model layer.
- Do not change public result or certificate fields.
- Do not accept a nonzero proof gap.
- Do not use a time limit as proof.
- Do not store protected Getnet values in Autobench.
- Do not replace accepted Getnet output.

## Verified starting evidence

### Repository state

Plan 003 ends at commit `1c252ba47d4ba249fe74217ba450e9364b82d2c7`.

The branch is `plan-003-coverage-solver-scale`.

The Plan 003 commits are:

1. `10ee07d`: test the scalable model contract.
2. `9f9006e`: normalize the coverage model.
3. `5e415d6`: reduce stages and tie breaks.
4. `2eebc86`: document the scale contract.
5. `1c252ba`: record the Getnet STOP result.

### Real Getnet Stage 1

The protected 2025Q1 input has SHA-256:

```text
1313103cb45767ba03ca57117e400770868b3fd6d9d500ff300be8a6f9cec820
```

Plan 003 reduced the model to these values:

- 242 publication units
- 33 peers
- three metrics
- 28,930 variables
- 28,171 integer variables
- 81,842 rows
- 257,769 nonzero coefficients
- 0.55 seconds to compile

The SciPy Stage 1 call did not return within the proof limit.

The run produced no solver status, dual bound, gap, or certificate.

The accepted Getnet baseline stayed unchanged.

### Node03 runtime gate

A read-only probe ran on node03 through maintained Paramiko transport.

The probe used strict host-key checks with the operator `known_hosts` file.

The result is:

```text
GNU_LIBC=glibc 2.28
MACHINE=x86_64
AUTOBENCH_PYTHON=3.10.10
AUTOBENCH_SCIPY=1.15.3
```

The evidence file is outside both repositories:

```text
C:\Users\e176097\AppData\Local\Temp\getnet_node03_glibc_probe_20260805.json
```

The `highspy` 1.15.1 CPython 3.10 x86-64 wheel needs glibc 2.24 or later.

Thus, the recorded node03 runtime passes the published wheel platform gate.

This fact does not prove solver performance.

## Root cause

Plan 003 removed the memory fault.

The remaining fault is exact MIP proof time.

Real data leaves 28,171 integer variables after structural presolve.

The sanitized fixture leaves 3,502 integer variables.

Real data has no always-true witness variables.

It also has fewer impossible witness variables than the fixture.

SciPy does not accept a MIP start through `scipy.optimize.milp`.

SciPy also returns only after the complete solver call ends.

Direct HiGHS can accept a complete solution and report MIP progress.

A MIP start can improve the first feasible bound.

A MIP start cannot prove the matching dual bound by itself.

Plan 004 therefore measures the incumbent and proof times separately.

## Required exact strategies

Plan 004 permits two fixed Stage 1 strategies.

Do not add an automatic portfolio or user setting.

### Strategy A: direct exact maximization

Maximize the integer release count in one HiGHS model.

Load the complete neutral MIP start before the solve.

Set both MIP gaps to zero.

Accept only a proven optimal model status.

This strategy is the preferred production design.

### Strategy B: incumbent plus one infeasibility proof

Use Strategy B only if Strategy A reaches the 15-minute STOP condition.

Let `K` be the best independently verified release count.

Add the exact row `sum(r) >= K + 1`.

Set the objective to zero.

Solve one feasibility model with exact tolerances.

An infeasible status proves that `K` is maximum.

A feasible status means `K` was not maximum.

Use the new feasible result as the next incumbent.

Then run Strategy B one more time with its new `K`.

STOP after that second proof attempt.

Do not build an unbounded iterative search.

Use Strategy B in production only after it passes every parity test.

## Proof contract

Stage 1 passes only when all facts below are true:

- HiGHS returns `kOptimal` for Strategy A.
- HiGHS returns `kInfeasible` for the final Strategy B proof.
- The returned primal solution is feasible when a solution is required.
- The release objective is integral within the existing readback tolerance.
- The normalized MIP dual bound equals the release count for Strategy A.
- `mip_gap` equals zero for Strategy A.
- `mip_rel_gap` is zero.
- `mip_abs_gap` is zero.
- No primal violation exceeds the existing accepted tolerance.
- No integrality violation exceeds the existing accepted tolerance.
- The independent verifier passes the candidate result.

Do not create a certificate from a time-limit result.

Do not create a certificate from an interrupted result.

Do not create a certificate from an unknown result.

Do not create a certificate from a feasible but unproven result.

Do not convert a rounded gap into zero.

## Complete neutral MIP start

Build the start from neutral global weights.

Use weight `1.0` for each governed peer.

Use the same canonical peer and metric order as the compiled model.

Calculate all continuous mean-weight values from the compiled equations.

Evaluate each rule with the existing public policy evaluation functions.

Set each release variable from the evaluated rule results.

Set each rule-selection variable from one canonical authorizing rule.

Set every witness variable from the same evaluated weighted shares.

Use the compiled witness index to avoid missing fixed variables.

Set all Stage 1 variable values.

Check every bound and row before calling `setSolution`.

Reject the start if any row exceeds the existing feasibility tolerance.

Do not ask HiGHS to repair a partial start.

Do not use solver output to decide privacy semantics.

## Internal design

Add one internal module:

```text
core/privacy_coverage_highs.py
```

Keep it private to `core`.

Do not export it from `core/__init__.py`.

Create one small `HighsCoverageSession` class.

The class owns one `highspy.Highs` object for one solve stage.

It accepts one `StageConstraintSet` from Plan 003.

It loads the existing CSC arrays without dense conversion.

It controls only these operations:

- model load
- option setup
- complete start load
- objective change
- row-bound change
- solve
- status and proof extraction
- progress event capture

Return a typed internal result.

Use these fields:

- model status
- primal solution status
- column values
- objective value
- MIP primal bound
- MIP dual bound
- MIP gap
- maximum primal infeasibility
- maximum integrality violation
- node count
- run time
- first verified incumbent time

Do not expose raw `highspy` objects outside this module.

Keep `core/privacy_coverage_model.py` solver-neutral.

Keep `core/privacy_coverage_verifier.py` solver-neutral.

## Progress evidence

Use the official MIP logging callback.

Capture safe numeric fields only.

Record these fields for each progress event:

- elapsed seconds
- node count
- primal bound
- dual bound
- MIP gap

Do not record unit keys, peer names, weights, or protected values.

Record the first incumbent only after local row validation succeeds.

Keep the callback read-only.

Do not supply external solutions through callbacks.

Use a fixed random seed of zero.

Record the HiGHS version and all non-default solver options.

## Dependency and runtime changes

Add the direct dependency to:

- `pyproject.toml`
- `requirements.txt`
- `constraints.txt`
- `uv.lock`

Pin the production constraint to `highspy==1.15.1`.

Use `highspy>=1.15.1,<1.16` in project and requirements metadata.

Add `highspy` to `shared_runtime.REQUIRED_IMPORTS`.

Update the shared-runtime tests for the new required import.

Keep the Edge Node dependency target at CPython 3.10 and `cp310`.

Do not change the node platform to work around a wheel problem.

Build the wheel bundle through the existing edge-deploy workflow.

Do not run `pip` on node03.

## Test-first implementation steps

### Step 0: confirm drift and create the branch

Run:

```powershell
git status --short --branch
git rev-parse HEAD
git log --oneline -6
uv lock --check
```

Require HEAD `1c252ba47d4ba249fe74217ba450e9364b82d2c7`.

Require no uncommitted source change.

Create branch `plan-004-direct-highs-proof`.

STOP if Plan 003 source changed after the stated commit.

STOP if the worktree contains an unexplained change.

### Step 1: define adapter and proof tests

Add `tests/test_privacy_coverage_highs.py`.

Test CSC model loading without dense conversion.

Test binary and continuous integrality mapping.

Test finite and infinite bounds.

Test minimization and maximization objective signs.

Test these model statuses:

- optimal
- infeasible
- time limit
- iteration limit
- interrupted
- unknown
- solver error

Test missing and nonfinite proof fields.

Test a nonzero relative gap.

Test a nonzero absolute objective difference.

Test primal and integrality violations.

Test that all unproven states fail closed.

Use small generated models only.

### Step 2: define complete-start tests

Add start tests to `tests/test_privacy_coverage_highs.py`.

Cover both approved privacy rules.

Cover each secondary witness tier.

Cover the Citi overlay.

Cover an always-true witness.

Cover an impossible witness.

Cover an uncertain witness at each threshold boundary.

Cover a unit with no authorizing rule.

Cover a unit with two passing rules.

Require the canonical rule for the two-rule case.

Require values for every Stage 1 variable.

Require zero row violations before `setSolution`.

Tamper with each variable family and require rejection.

### Step 3: add the dependency surfaces

Update all dependency files in one commit.

Update `shared_runtime.REQUIRED_IMPORTS`.

Update these tests:

- `tests/test_shared_runtime.py`
- `tests/test_production_scripts.py`
- `tests/bundle_helpers.py`, if its bundle contract needs the package

Run:

```powershell
uv lock
uv lock --check
uv sync --extra dev --extra release
uv run python -c "import highspy; print(highspy.Highs().version())"
uv run pytest tests/test_shared_runtime.py tests/test_production_scripts.py -q
```

Require HiGHS version 1.15.1.

STOP if the lock selects another production version.

STOP if Windows cannot import the locked wheel.

### Step 4: implement the internal HiGHS adapter

Create `core/privacy_coverage_highs.py`.

Use the low-level public HiGHS matrix interface.

Load the existing CSC arrays once per stage.

Set exact proof options explicitly.

Use:

```text
mip_rel_gap = 0
mip_abs_gap = 0
random_seed = 0
```

Set the caller time limit explicitly.

Do not change heuristic effort, cuts, presolve, or symmetry settings.

Do not add undocumented options.

Validate every HiGHS call status.

Map HiGHS statuses to the existing solver states.

Return safe diagnostic data for failures.

Run:

```powershell
uv run pytest tests/test_privacy_coverage_highs.py -q
uv run ruff check core/privacy_coverage_highs.py tests/test_privacy_coverage_highs.py
uv run mypy core/privacy_coverage_highs.py
```

### Step 5: implement and validate the neutral start

Add the start builder to `core/privacy_coverage_highs.py`.

Reuse existing canonical and policy functions.

Do not duplicate rule evaluation.

Validate all rows before submitting the start.

Add a test that HiGHS accepts the complete start.

Add a test that the start supplies the expected primal bound.

Add repeated-run tests for the first incumbent value.

Do not require the first incumbent time to match exactly.

### Step 6: add direct HiGHS behind the internal test seam

Keep the public function name `optimize_safe_coverage`.

Make it call the internal HiGHS adapter.

Keep `SafeCoverageResult` unchanged.

Keep solver state strings unchanged.

Set `solver_name` to `highspy.Highs`.

Set `solver_version` from the loaded HiGHS library.

Preserve the four objective stages.

Preserve the current release-block tie break.

Preserve direct policy evaluation for authorizing rules.

Preserve the independent verifier call.

Do not delete the SciPy call yet.

Keep it only as a test oracle during this step.

### Step 7: prove sanitized parity

Run both implementations in tests only.

Compare these outputs:

- release set
- suppression set
- global weights within existing tolerance
- authorizing rules
- primary objective
- later objective values
- release-mask digest
- verifier result
- certificate fields

Test all current small fixtures.

Test the sanitized 242 by 33 by 3 fixture.

Require two direct HiGHS runs with identical safe digests.

Require exact Stage 1 proof in each run.

Require the current benchmark ceilings.

Run:

```powershell
uv run pytest tests/test_privacy_coverage_solver.py tests/test_privacy_coverage_highs.py -q
uv run python -m tools.benchmark_privacy_coverage_solver
```

STOP if a release set changes.

STOP if an authorizing rule changes without a policy-equivalent explanation.

STOP if the independent verifier fails.

### Step 8: add safe proof telemetry

Update `tools/benchmark_privacy_coverage_solver.py`.

Report compile, incumbent, and proof times separately.

Report the final primal bound, dual bound, gap, and node count.

Report the start validation result.

Do not report protected values or identifiers.

Add deterministic JSON schema tests.

### Step 9: run the node03 candidate-runtime gate

Build an isolated dependency bundle through edge-deploy-core.

Use the current Autobench release profile.

Do not activate the candidate runtime.

Transfer with maintained Paramiko transport.

Use strict host-key checks.

Install under a new immutable candidate digest.

Run only these checks in the candidate runtime:

```text
import highspy
print the HiGHS version
solve a small exact binary MIP
report model status, dual bound, and gap
```

Do not run production SQL.

Do not use Dispatch for this non-SQL runtime check.

Do not activate `.venv/current`.

STOP if the wheel import fails.

STOP if the small MIP lacks exact proof fields.

### Step 10: run real Getnet Strategy A

Use the exact recorded 2025Q1 input hash.

Run outside the Autobench repository.

Write to a new isolated Getnet candidate directory.

Keep the accepted baseline unchanged.

Use the approved current policy values:

- release mode: Maximum Safe Coverage
- strict compliance: true
- merchant spend: true
- Citi recipient: false
- Citi identifiers: empty

Set the Stage 1 limit to 15 minutes.

Use Strategy A only.

Capture:

- input hash
- Autobench commit
- dependency-bundle digest
- Python, HiGHS, NumPy, and SciPy versions
- model statistics
- start validation
- first incumbent time and count
- final proof time
- final primal bound
- final dual bound
- final gap
- node count
- model status
- verifier result
- safe artifact hashes

Do not continue to later stages without exact Stage 1 proof.

If Strategy A passes, skip Strategy B.

If Strategy A reaches the limit, continue to Step 11.

### Step 11: run real Getnet Strategy B once

Use the best independently verified Strategy A incumbent.

Require a valid candidate result for its release set.

Run the `K + 1` feasibility proof.

Set a new 15-minute limit.

If HiGHS finds a feasible result, verify it independently.

Then run one final `K + 1` proof for the new count.

Use the unused part of the same 15-minute Strategy B budget.

STOP if Strategy B does not prove maximum within that budget.

STOP if any found solution fails the independent verifier.

If Strategy B passes, make it the single production Stage 1 design.

Document why Strategy A failed and Strategy B passed.

### Step 12: remove the obsolete SciPy MILP path

Run this step only after Step 10 or Step 11 passes.

Remove the `scipy.optimize.milp` import from the coverage solver.

Remove `_solve_stage` and SciPy result shims that only support coverage MILP.

Remove tests that patch the SciPy `milp` binding.

Replace them with direct adapter fault tests.

Do not remove SciPy from Autobench dependencies.

Other Autobench modules still use SciPy.

Do not keep an environment switch for the old path.

Do not keep a fallback on import or solver failure.

Fail closed when `highspy` is unavailable.

### Step 13: update technical and production documents

Update:

- `docs/CORE_TECHNICAL_DOC.md`
- `docs/production-testing.md`
- `docs/research/2026-08-04-maximum-safe-coverage-milp-scaling.md`
- `plans/README.md`
- this plan status

Explain the single direct HiGHS design.

Explain the complete MIP start.

Explain separate incumbent and proof times.

Explain fail-closed status handling.

Record the node03 glibc evidence.

Record the selected exact strategy.

Do not state that a warm start proves optimality.

### Step 14: run local acceptance

Run:

```powershell
uv lock --check
uv run ruff check .
uv run mypy core
uv run pytest -n 4 --dist loadfile
uv run python -m tools.benchmark_privacy_coverage_solver
uv run python scripts/perform_gate_test.py
```

Run the configured Python 3.10 and Python 3.12 checks.

If a baseline type fault remains, prove it on `main`.

Do not hide a new type fault as baseline behavior.

### Step 15: run all five Getnet quarters

Use one new isolated candidate directory.

Run quarters 2025Q1 through 2026Q1.

Require each Stage 1 proof within 15 minutes.

Require all later stages to complete.

Require independent verifier success for each quarter.

Run each quarter twice.

Require identical release-mask and certificate digests.

Compare the candidate with accepted baseline `f745a318`.

Explain every material mismatch with source evidence.

Do not replace `outputs/dashboard_feed/current`.

Do not replace any accepted remote release.

### Step 16: commit the complete branch

Use atomic commits in this order:

1. tests for the HiGHS adapter and complete start
2. dependency and runtime import changes
3. direct HiGHS adapter and solver integration
4. proof telemetry and benchmark changes
5. SciPy coverage-path removal
6. technical and production documents
7. Getnet acceptance STOP or PASS record

Do not commit protected inputs or generated Getnet artifacts.

Do not push without explicit user approval.

## Required Getnet evidence layout

Create a new directory under:

```text
D:\Projects\Getnet\outputs\dashboard_feed\candidates\
```

Use a name that includes `plan004` and the UTC run date.

Include only approved safe artifacts and redacted diagnostics.

Required files are:

```text
acceptance_report.md
comparison_to_f745a318.md
run_manifest.json
quarter_results.json
_diagnostic/model_stats_<quarter>.json
_diagnostic/proof_progress_<quarter>.jsonl
_diagnostic/stage_evidence_<quarter>.md
_diagnostic/baseline_hashes_before.json
_diagnostic/baseline_hashes_after.json
```

The before and after baseline hashes must match.

## Acceptance criteria

Plan 004 is complete only when all criteria pass:

- The locked direct `highspy` dependency imports on Windows.
- The locked wheel imports in an isolated node03 runtime.
- The small node03 MIP returns exact proof fields.
- The complete neutral MIP start passes local row validation.
- All sanitized parity tests pass.
- No protected value enters the Autobench repository.
- One fixed Stage 1 strategy passes real 2025Q1.
- Each real Stage 1 proof completes within 15 minutes.
- All five quarters complete all stages.
- Every quarter has optimal or infeasible exact proof evidence.
- Every MIP gap equals zero where an optimal solution is required.
- Every proving dual bound matches the released count.
- Every independent verifier result passes.
- Repeated safe digests match.
- The accepted Getnet baseline hashes remain unchanged.
- Every material difference from `f745a318` has evidence.
- The coverage solver has no SciPy MILP fallback.
- CLI, TUI, and Python API behavior stays unchanged.
- The full local acceptance suite passes.

## STOP conditions

Stop immediately when any condition occurs:

- HEAD differs from the required Plan 003 commit before implementation.
- The worktree has an unexplained source change.
- The locked highspy wheel does not support CPython 3.10 x86-64.
- Windows cannot import the locked highspy wheel.
- An isolated node03 runtime cannot import the wheel.
- The small node03 MIP lacks exact proof fields.
- A MIP start fails local row validation.
- A parity test changes the safe release set.
- A parity test weakens a privacy decision.
- The independent verifier rejects a candidate solution.
- Strategy A does not prove Stage 1 within 15 minutes, unless Step 11 starts.
- Strategy B does not prove Stage 1 within its 15-minute budget.
- Real 2025Q1 lacks exact status, gap, or dual-bound proof.
- Any later quarter exceeds its 15-minute Stage 1 limit.
- A required deterministic digest changes across repeated runs.
- A protected value enters a repository file or log.
- An accepted Getnet output hash changes.
- Work requires a solver option outside this plan.
- Work requires a privacy policy change.

At a STOP condition, preserve safe evidence.

Write a clear STOP report.

Do not tune around the failed proof.

Do not continue later stages or quarters after the first proof failure.

## STOP report format

Record:

- exact stage and strategy
- Autobench commit
- input hash
- runtime and bundle identity
- model statistics
- start validation result
- first incumbent time and count
- final primal and dual bounds
- final gap
- node count
- solver status
- elapsed time
- verifier status
- unchanged baseline hash proof
- exact evidence paths
- next operator decision, if one exists

## Source references

- [HiGHS Python examples](https://ergo-code.github.io/HiGHS/dev/interfaces/python/example-py/)
- [HiGHS callback fields](https://ergo-code.github.io/HiGHS/dev/callbacks/)
- [HiGHS option definitions](https://ergo-code.github.io/HiGHS/dev/options/definitions/)
- [highspy 1.15.1 files](https://pypi.org/project/highspy/1.15.1/#files)
- `docs/research/2026-08-04-maximum-safe-coverage-milp-scaling.md`
- `core/privacy_coverage_model.py`
- `core/privacy_coverage_solver.py`
- `core/privacy_coverage_verifier.py`
- `tools/benchmark_privacy_coverage_solver.py`

