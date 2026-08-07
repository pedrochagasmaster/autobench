# Maximum Safe Coverage MILP scaling research

Date: 2026-08-04

## Decision

Fix the mathematical model before changing solver parameters.

Add one normalized weighted-total variable for each Publication Unit and metric.
Use this variable in all share constraints.

Build stage one without later-stage variables.
Apply safe structural presolve before variable allocation.

Keep SciPy for the first implementation layer.
Use one CSC constraint matrix for each solve.

Evaluate direct `highspy` only after the reduced SciPy model passes parity tests.
The node03 binary compatibility check is a required gate before this dependency change.

## Current evidence

The real Getnet 2025Q1 case has 242 Publication Units, 33 peers, and three metrics.
The current model creates these objects:

- 101,112 variables
- 84,447 integer variables
- 302,720 rows
- 5,396,123 nonzero coefficients

The first solve stopped with `MemoryError: std::bad_alloc`.
An exact 20-minute attempt did not produce a certificate.

The evidence is in
`D:/Projects/Getnet/docs/autobench_maximum_safe_coverage_getnet_test_20260804.md`.

The CSV is not the memory problem.
The input file is 6,254,079 bytes.
The model expansion is much larger than the input.

## Root cause

The current model writes the same weighted total into almost every privacy row.

For each unit, metric, rule, and positive peer, the primary row includes nearly every peer weight.
The secondary witness row repeats the same pattern.
The distortion rows also repeat a weighted mean over all peers.

See the current primary, witness, and distortion construction in
[`core/privacy_coverage_solver.py`](../../core/privacy_coverage_solver.py).

This creates approximately quadratic nonzero growth in the peer count.
The important term is:

```text
unit x metric x rule-or-tier x peer x peer
```

The witness count is also large.
The current model creates one binary witness for each unit, metric, rule, tier, and positive peer.

Memory then peaks before the solver can reduce the model.
Python lists, NumPy arrays, SciPy sparse arrays, and the HiGHS model can overlap.

SciPy converts each constraint matrix to `csc_array`.
It also stacks multiple constraints into another CSC array before the HiGHS call.
This behavior is explicit in the
[SciPy 1.18.0 documentation](https://docs.scipy.org/doc/scipy-1.18.0/reference/generated/scipy.optimize.milp.html)
and the
[SciPy 1.18.0 source](https://github.com/scipy/scipy/blob/v1.18.0/scipy/optimize/_milp.py#L13-L74).

HiGHS presolve reduces the solver model after model submission.
It cannot prevent the Python and SciPy construction peak.
HiGHS documents presolve as a model-dimension reduction step before the main solve.
See the [HiGHS presolve guide](https://ergo-code.github.io/HiGHS/stable/guide/further/#presolve).

## Exact algebraic reformulation

For unit `u`, metric `m`, and peer `p`, define:

```text
A[u,m]       = sum_p a[u,m,p]
f[u,m,p]     = a[u,m,p] / A[u,m]
s[u,m]       = sum_p f[u,m,p] * w[p]
```

`A[u,m]` is positive under the current input contract.
`s[u,m]` is the normalized weighted total.
Its bounds are the global weight bounds.

The weighted share is:

```text
share[u,m,p] = 100 * f[u,m,p] * w[p] / s[u,m]
```

Use one equality for each unit and metric:

```text
s[u,m] - sum_p f[u,m,p] * w[p] = 0
```

Then replace each dense primary row with:

```text
cap[r] * s[u,m] - 100 * f[u,m,p] * w[p] >= conditional lower bound
```

Replace each dense secondary row with:

```text
100 * f[u,m,p] * w[p] - threshold * s[u,m] >= conditional lower bound
```

Replace the Citi row with:

```text
25 * s[u,m] - 100 * f[u,m,citi] * w[citi] >= conditional lower bound
```

The current distortion mean is exactly `s[u,m]`.
Use it directly in the absolute-value rows:

```text
d[u,m,p] >=  w[p] - s[u,m] - M_d * (1 - r[u])
d[u,m,p] >= -w[p] + s[u,m] - M_d * (1 - r[u])
```

This is an exact extended formulation.
It does not change a privacy rule or a feasible weight vector.

Most privacy rows change from `O(peers)` nonzeros to `O(1)` nonzeros.
Only the one total-definition row remains `O(peers)` for each unit and metric.

The main nonzero term changes from approximately:

```text
O(units * metrics * rules * tiers * peers^2)
```

to:

```text
O(units * metrics * peers)
+ O(units * metrics * rules * tiers * peers)
```

The normalized form also avoids raw amount coefficients.
Its coefficients are mainly fractions and percentages.
HiGHS recommends coefficients and bounds near order one when possible.
See [HiGHS numerical considerations](https://ergo-code.github.io/HiGHS/stable/guide/numerics/).

Keep each current interval-derived big-M value.
Calculate it from the original weight coefficients.
Do not calculate a looser value from only the `s[u,m]` bounds.

## Structural presolve before allocation

Apply these rules before index creation:

1. Disable a rule when a metric has too few positive peers.
2. Omit a primary row when its interval minimum already passes.
3. Disable a rule when a primary row's interval maximum cannot pass.
4. Classify each secondary witness as always true, always false, or variable.
5. Create binaries only for variable witnesses.
6. Disable a rule when fixed and variable witnesses cannot meet a tier count.
7. Subtract always-true witnesses from the required tier count.
8. Remove rules that another applicable rule fully dominates.

Rule dominance must use policy meaning, not rule names.
Rule A dominates rule B only when B passing always makes A pass.

With the current merchant policy, `4/35` dominates `5/25`, `6/30`, and `7/35`.
It does not dominate `10/40` because `10/40` permits a 40 percent maximum.

This removal preserves the current canonical authorizer.
Canonical rule order selects `4/35` before the three dominated rules.

Do not remove the current `z <= y` rows in the first change.
Those rows reduce free binary symmetry.
Remove them only after measured parity and performance evidence.

Share witness variables for equal thresholds only when two rules use the same normalized threshold.
This is a secondary reduction.
The current five secondary thresholds are distinct.

## Stage-specific models

Stage one proves the maximum release count.
It needs only these variables:

- global weights `w`
- normalized totals `s`
- release indicators `r`
- rule indicators `y`
- unresolved witness indicators `z`

Stage one does not need distortion variables `d`.
It does not need neutral-distance variables `q`.
It does not need their rows.

After stage one proves `K`, build the later model.
Add `sum(r) = K`, distortion variables, and neutral-distance variables at that time.

For the SciPy implementation, build one complete `csc_array` per stage.
Pass one `LinearConstraint` to `milp`.
Do not pass a base constraint plus an extras sequence.

SciPy converts every input matrix to CSC.
It uses `vstack(..., format="csc")` when it receives multiple constraints.
A single CSC constraint avoids that additional stack step.
See the [SciPy conversion source](https://github.com/scipy/scipy/blob/v1.18.0/scipy/optimize/_milp.py#L62-L74).

Stage four currently solves once for many release, rule, and weight decisions.
First, remove the authorizing-rule solve loop.
After final weights are known, run the independent rule evaluator.
Select the first passing applicable rule in canonical order.

This change is valid because `y` and `z` are feasibility auxiliaries.
They do not change the projected feasible set for the final weights and release mask.

Keep the existing sequential release-mask and weight tie-break in the SciPy layer.
This gives a smaller first implementation with lower semantic risk.

## SciPy and direct HiGHS comparison

### Reduced SciPy model

Benefits:

- It adds no dependency.
- It uses the current public API.
- It gives the current proof fields.
- It has the lowest deployment risk.

Limits:

- `milp` has no initial-solution argument.
- `milp` has no reusable solver session.
- Each call converts and submits a complete model.
- Repeated stage-four calls still have overhead.

The public signature and options are in the
[SciPy `milp` documentation](https://docs.scipy.org/doc/scipy-1.18.0/reference/generated/scipy.optimize.milp.html).

### Direct `highspy`

Benefits:

- `passModel`, `addRows`, and `addCols` accept sparse model data.
- Objective costs and variable or row bounds can change in one model.
- `setSolution` accepts a partial or complete MIP start.
- `getInfo` exposes proof and feasibility fields.

The official examples list these operations.
See the [HiGHS Python examples](https://ergo-code.github.io/HiGHS/stable/interfaces/python/example-py/).

HiGHS states that a feasible integer assignment supplies an initial primal bound.
A weight-only start is not sufficient for this model.
Build a complete neutral start for `r`, `y`, and `z` with the existing evaluator.
See the [HiGHS MIP hot-start guide](https://ergo-code.github.io/HiGHS/stable/guide/further/#mip).

HiGHS also supports lexicographic objectives.
Do not use that feature in the first solver migration.
Explicit stage rows keep proof evidence and failure handling easier to inspect.

## Node03 compatibility gate

The active node03 runtime uses CPython 3.10.10.
The current probe does not record its glibc version.

The official `highspy` 1.15.1 CPython 3.10 x86-64 wheel requires glibc 2.24 or later.
See the [official PyPI file metadata](https://pypi.org/project/highspy/1.15.1/#files).

Therefore, direct `highspy` has an unresolved node03 binary risk.
Do not add it until a read-only probe records:

```text
getconf GNU_LIBC_VERSION
```

Then install the locked wheel in an isolated candidate runtime.
Run an import check and a small optimal MIP before any release build.

STOP if glibc is older than 2.24.
The implementation must then keep the public SciPy solver or use an approved baseline-built wheel.
Do not import SciPy's private bundled HiGHS modules.

## Proof and verification contract

Preserve the current independent verifier.
Do not use solver pass flags as privacy evidence.

Stage one must set an exact proof target:

```text
mip_rel_gap = 0
mip_abs_gap = 0
```

SciPy documents the relative gap option and returns `mip_dual_bound` and `mip_gap`.
See the [SciPy result contract](https://docs.scipy.org/doc/scipy-1.18.0/reference/generated/scipy.optimize.milp.html#returns).

HiGHS defaults are not exact.
The default relative gap is `0.0001`.
The default absolute gap is `1e-06`.
See the [HiGHS option definitions](https://ergo-code.github.io/HiGHS/stable/options/definitions/#mip_rel_gap).

For direct HiGHS, require all of these facts:

- model status is `kOptimal`
- the primal solution status is feasible
- the primary objective is integral
- the normalized dual bound equals the released count
- `mip_gap` is exactly zero
- no reported primal or integrality violation exceeds the accepted tolerance

`HighsInfo` exposes the objective, MIP dual bound, MIP gap, integrality violation, and primal infeasibility fields.
See the [official `HighsInfo` contract](https://ergo-code.github.io/HiGHS/stable/structures/structs/HighsInfo/).

The independent verifier must still recalculate:

- every released metric share
- the selected authorizing rule
- mandatory overlays
- global weight bounds and identity
- the exact release and suppression partition
- sink filtering
- policy, universe, mask, and artifact digests

A time limit, memory limit, unknown status, nonzero gap, or verifier failure remains diagnostic-only.
It must not create a Coverage Certificate.

## Implementation plan

### Phase 1: Characterize the current contract

Add tests before changing the formulation.

Record these values for each test case:

- release set
- suppression set
- global weights
- authorizing rules
- four objective results
- solver state, dual bound, and gap
- variables, integer variables, rows, and nonzeros by row family

Use the existing small fixtures.
Add generated small cases that cover every rule and the Citi overlay.

Add a model-size test for a 33-peer, three-metric shape.
Do not store Getnet protected values in Autobench.

Acceptance:

- All current solver and verifier tests pass.
- The diagnostic counts reproduce the current row families.

### Phase 2: Add normalized totals

Create `s[u,m]` after metric canonicalization.
Use normalized fractions `f[u,m,p]` in the total equality.

Rewrite primary, secondary, Citi, and distortion rows.
Keep the current interval-derived big-M calculations.

Build one CSC matrix and one `LinearConstraint`.

Acceptance:

- New and old solvers match on every small fixture.
- The independent verifier accepts the same final results.
- Permutation and repeated-run hashes stay equal.
- The 33-peer model has linear, not quadratic, nonzero growth.

STOP if any feasible set or authorizing rule changes without an explained policy-equivalent reason.

### Phase 3: Add structural presolve

Add rule dominance and interval classification before variable allocation.

Test each removal with paired cases:

- always passing
- always failing
- boundary feasible
- boundary infeasible
- dominated rule
- non-dominated rule

Acceptance:

- Small-case outputs remain equal.
- Candidate Universe membership remains unchanged.
- Only solver auxiliaries and redundant rows decrease.

### Phase 4: Split the stages

Build a stage-one privacy model without `d` or `q`.
Build the later model only after `K` is proven.

Recalculate the canonical authorizing rule after final weights.
Remove the obsolete rule tie-break solve loop.

Acceptance:

- Stage one contains no distortion or neutral rows.
- Later objective values match the characterization tests.
- The stage-one proof fields remain unchanged.

### Phase 5: Run the real SciPy acceptance test

Run the exact external Getnet 2025Q1 input by its recorded SHA-256.
Capture wall time, peak process memory, and model counts.

Acceptance:

- No `std::bad_alloc` occurs.
- Stage one reaches optimal status.
- The gap is zero.
- The dual bound proves the released count.
- The independent verifier passes.
- Two isolated repeats have identical safe-result and certificate digests.

STOP if 2025Q1 does not complete within the agreed node03 resource budget.
Do not tune threads or heuristics as a substitute for Phases 2 through 4.

### Phase 6: Decide whether direct HiGHS is necessary

Keep SciPy when Phase 5 meets the resource budget.
This is the simplest complete design.

Use direct `highspy` only when repeated model submission remains the measured limit.

Before migration:

1. Prove node03 glibc compatibility.
2. Add `highspy` to `pyproject.toml`, `requirements.txt`, and `uv.lock`.
3. Update the approved runtime import manifest.
4. Verify Windows and node03 wheels in isolated runtimes.

Implement one narrow solver adapter.
Pass typed compressed arrays once.
Change objectives and bounds through the public HiGHS API.

Create a complete neutral MIP start with the policy evaluator.
Treat the start only as a search aid.

Acceptance:

- SciPy and direct HiGHS match on all small characterization cases.
- Direct HiGHS exposes all required proof fields.
- 2025Q1 improves the measured limiting resource.

### Phase 7: Full release acceptance

Run the complete Autobench test suite.
Run lint, type checks, package checks, and the standard release smoke test.

Then run all five Getnet quarters in an isolated candidate folder.

For each quarter, require:

- optimal primary status
- exact zero gap
- proving dual bound
- independent verifier pass
- deterministic digests
- no suppressed key or value in client artifacts

Keep accepted Getnet outputs unchanged until separate promotion approval.

## Rejected fixes

Do not treat these changes as the root fix:

- a larger process memory limit
- a longer time limit
- more threads
- a different heuristic preset
- a positive MIP gap
- one weighted objective for all four priorities
- an unverified feasible incumbent
- a private SciPy HiGHS import

They do not remove the model expansion.
Some also violate the accepted proof contract.

## Primary sources

- [SciPy 1.18.0 `milp` documentation](https://docs.scipy.org/doc/scipy-1.18.0/reference/generated/scipy.optimize.milp.html)
- [SciPy 1.18.0 `milp` source](https://github.com/scipy/scipy/blob/v1.18.0/scipy/optimize/_milp.py)
- [HiGHS further features](https://ergo-code.github.io/HiGHS/stable/guide/further/)
- [HiGHS Python examples](https://ergo-code.github.io/HiGHS/stable/interfaces/python/example-py/)
- [HiGHS option definitions](https://ergo-code.github.io/HiGHS/stable/options/definitions/)
- [HiGHS `HighsInfo`](https://ergo-code.github.io/HiGHS/stable/structures/structs/HighsInfo/)
- [HiGHS numerical considerations](https://ergo-code.github.io/HiGHS/stable/guide/numerics/)
- [`highspy` 1.15.1 package files](https://pypi.org/project/highspy/1.15.1/#files)
