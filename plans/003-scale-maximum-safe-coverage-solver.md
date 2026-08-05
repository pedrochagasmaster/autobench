# Plan 003: Scale the Maximum Safe Coverage solver

> **Executor contract**: Read this complete file before you change source files.
> Follow each step in order. Run every required check. Honor every STOP condition.
> Do not weaken a privacy rule. Do not publish, deploy, or commit production data.

## Copy-ready cloud-agent prompt

```text
Work in the Autobench repository.

Read AGENTS.md, CONTRIBUTING.md, plans/002-maximize-safe-coverage.md, and
plans/003-scale-maximum-safe-coverage-solver.md completely.
Treat Plan 003 as the execution contract.

Fix the Maximum Safe Coverage solver for production-scale Getnet inputs.
Keep the public Python, CLI, TUI, YAML, result, and certificate contracts unchanged.
Do not weaken policy limits, comparison tolerances, proof rules, or verification.

Replace repeated dense peer expressions with one normalized mean-weight variable
for each Publication Unit and metric. Remove conservatively dominated rule branches.
Remove structurally fixed or impossible witness variables. Build one CSC constraint
matrix for each solve stage. Replace per-unit release tie-break solves with exact
binary blocks. Derive the canonical authorizing rule after final weight selection.

Keep SciPy as the solver interface. Do not add highspy or use SciPy internals.
Require optimal status, zero MIP gap, a matching dual bound, and verifier success.

Use test-first development. Use only sanitized fixtures in the Autobench repository.
Run the isolated Getnet production-shaped acceptance outside the repository.
Do not replace any accepted Getnet output. Do not push, deploy, or release.
Stop and report when a STOP condition occurs. Do not tune around a failed proof.
```

## Status

- **Execution**: TODO
- **Priority**: P0
- **Effort**: L
- **Risk**: HIGH
- **Depends on**: Plan 002
- **Category**: privacy solver scale
- **Planned at**: Autobench commit `cda290f`, 2026-08-04

## Goal

Make `maximize-safe-coverage` prove the exact optimum for all five Getnet quarters.

The solver must complete inside the stated memory and time limits.

The solver must preserve the current public behavior and privacy proof contract.

## Current failure

The 2025Q1 Getnet model has these values:

- 242 Publication Units
- 33 governed peers
- three governed metrics
- 101,112 variables
- 84,447 integer variables
- 302,720 constraint rows
- 5,396,123 nonzero coefficients

The first solve failed with `MemoryError: std::bad_alloc`.

A later exact solve produced no certificate after 20 minutes.

The source CSV is only 6.3 MB. Input size is not the cause.

The model expands this product:

```text
Publication Unit x metric x rule x tier x peer
```

The model contains 82,995 tier-witness variables and 16,599 distortion variables.

Each peer constraint repeats almost every global weight coefficient.

This repetition makes matrix nonzeros grow approximately with peer count squared.

The solver also creates distortion variables before the coverage-count solve needs them.

SciPy converts each constraint matrix to CSC before each solve.

SciPy also stacks multiple constraints into a new CSC matrix.

The current repeated tie-break solves cause the same large conversion many times.

## Research decision

Fix the mathematical formulation before changing solver parameters.

Keep SciPy `milp` as the solver interface for this plan.

SciPy already uses HiGHS and already exists in the approved Edge Node runtime.

Do not add `highspy` in this plan.

Current `highspy` wheels can require a newer Linux runtime than the Edge Node.

The direct HiGHS interface is useful, but it does not fix the oversized formulation.

Reconsider a direct HiGHS interface only in a separate approved plan.

Primary research sources:

- [Full research note](../docs/research/2026-08-04-maximum-safe-coverage-milp-scaling.md)
- [SciPy 1.18 `milp` contract](https://docs.scipy.org/doc/scipy-1.18.0/reference/generated/scipy.optimize.milp.html)
- [SciPy 1.18 `milp` source](https://github.com/scipy/scipy/blob/v1.18.0/scipy/optimize/_milp.py)
- [HiGHS Python sparse-model examples](https://ergo-code.github.io/HiGHS/stable/interfaces/python/example-py/)
- [HiGHS MIP starts and multiple objectives](https://ergo-code.github.io/HiGHS/stable/guide/further/)
- [HiGHS proof result fields](https://ergo-code.github.io/HiGHS/stable/structures/structs/HighsInfo/)

## Fixed invariants

Keep these invariants unchanged:

- One global weight vector applies to every released Publication Unit.
- Every required metric in a released unit passes one approved rule.
- The Citi overlay remains mandatory when applicable.
- The Candidate Universe stays fixed during optimization.
- The Release Set and Suppression Set form an exact partition.
- The primary objective counts Publication Units only.
- The solver calls a result maximum only after an exact proof.
- The independent verifier remains the final release gate.
- Any timeout, malformed result, or nonzero gap fails closed.
- Suppressed keys and values remain absent from client evidence.

Do not change comparison epsilon or the numeric safety buffer.

Do not expand weight bounds to make a test pass.

## Non-goals

Do not add a privacy rule.

Do not change a rule threshold.

Do not add a Getnet-specific solver path.

Do not add a second privacy release mode.

Do not add a compatibility solver.

Do not keep the old dense formulation after cutover.

Do not use SciPy private modules.

Do not add `highspy`, Pyomo, OR-Tools, or another solver package.

Do not implement Benders decomposition, lazy constraints, or distributed solving.

Do not commit production data, generated reports, or benchmark outputs.

## Mathematical reformulation

### Normalized input shares

For unit `u`, metric `m`, and peer `p`, define:

```text
f[u,m,p] = source_volume[u,m,p] / source_total[u,m]
```

The values for one unit and metric sum to one.

### Mean-weight variable

Add one continuous variable `b[u,m]`:

```text
b[u,m] = sum(f[u,m,p] * w[p] for p in peers)
```

Its bounds are `min_weight` and `max_weight`.

This row is the only dense peer row for that unit and metric.

### Primary concentration row

Replace each repeated denominator expression with:

```text
100 * f[u,m,p] * w[p] <= cap[r] * b[u,m] + M * (1 - y[u,r])
```

This row has at most three variable coefficients.

### Secondary witness row

For threshold `tau`, use:

```text
100 * f[u,m,p] * w[p] >= tau * b[u,m] - M * (1 - z[u,m,r,t,p])
```

This row also has at most three variable coefficients.

### Citi row

Use the same `b[u,m]` variable for the Citi maximum-share row.

Do not create a second total or denominator expression.

### Distortion row

The current weighted mean equals `b[u,m]`.

Use this expression:

```text
d[u,m,p] >= abs(w[p] - b[u,m]) when r[u] = 1
```

Each linear side uses `d`, `w`, `b`, and `r` only.

### Safe big-M values

Derive every big-M value from normalized shares and configured weight bounds.

Do not use an arbitrary common big-M value.

Calculate bounds from the complete expanded peer expression.

Do not treat `b[u,m]` and `w[p]` as independent when this makes M looser.

Test each bound against exhaustive corner values for small fixtures.

## Conservative model presolve

### Rule dominance

Remove rule `B` only when another applicable rule `A` is always easier.

Use this conservative condition:

- `A` has no secondary tiers.
- `A.min_entities <= B.min_entities`.
- `A.max_concentration >= B.max_concentration`.
- At least one comparison is strict, or `B` has secondary tiers.

For merchant spend, `4/35` removes `5/25`, `6/30`, and `7/35`.

Keep `10/40`. Neither `4/35` nor `10/40` dominates the other.

Do not add a general logical implication engine.

### Structural witnesses

Classify primary cap expressions before row creation.

- Omit a cap row when it always passes across all weight bounds.
- Disable that rule when one required cap row can never pass.
- Keep a cap row only when its result can change with the weights.

Apply the same interval test to the Citi overlay.

- Omit the Citi row when it always passes.
- Disable release when the Citi row can never pass.

Then classify secondary witnesses.

Calculate witness expression bounds before variable creation.

- Do not create a variable for an always-true witness.
- Do not create a variable for an impossible witness.
- Reduce the required count by the always-true witness count.
- Disable the rule when possible witnesses cannot meet the remaining count.

Use exact interval formulas from normalized shares and weight bounds.

Do not infer a fixed witness from one tested weight vector.

## Solver stages

### Stage 1: maximum coverage

Build only these variable families:

- global weights `w[p]`
- mean weights `b[u,m]`
- releases `r[u]`
- rule selections `y[u,r]`
- uncertain tier witnesses `z[u,m,r,t,p]`

Do not include distortion or neutral-distance variables.

Set `mip_rel_gap` to zero inside the certifying mode.

Allow time and node limits to stop work. Treat either stop as unproven.

Require all of these facts:

- solver status is optimal
- the primary objective is integral
- `mip_gap == 0`
- the normalized dual bound equals the release count

### Stage 2: minimum distortion

Fix the proven release count.

Add distortion variables and rows only after Stage 1 succeeds.

Preserve the exact primary count.

### Stage 3: minimum neutral distance

Add neutral-distance variables only after Stage 2 succeeds.

Preserve the count and distortion bounds.

Use zero tolerance when the neutral optimum is exactly zero.

### Stage 4: deterministic result

Replace one solve per release variable with exact binary blocks.

Use blocks of at most 16 canonical release variables.

Encode one block with integer coefficients `2^15` through `2^0`.

Maximizing this integer value gives the same canonical bit order.

Fix the proven integer block value before the next block.

Require optimal status for each block.

Keep sequential weight minimization for the 33 continuous weights.

After final weights exist, evaluate all applicable rules again.

Record the first canonical rule that passes every metric.

Do not run one solver call for each authorizing rule.

Run one final feasibility solve with all fixed values.

## Sparse matrix construction

Move model compilation to `core/privacy_coverage_model.py`.

Keep `optimize_safe_coverage` as the small external interface.

The new model module must hide these implementation details:

- canonical variable indexes
- normalized metric data
- conservative rule pruning
- structural witness pruning
- sparse row construction
- stage objective vectors
- stage constraint bounds
- safe model statistics

Build canonical CSC matrices before calling SciPy.

Pass one `LinearConstraint` to each `milp` call.

Do not pass a list that makes SciPy call `vstack` during every solve.

Prepare all release-block rows before Stage 4 starts.

Change their lower and upper bounds as each block becomes fixed.

Release obsolete stage matrices before building a larger stage.

Do not retain Python coefficient lists after CSC construction.

## File changes

Create:

- `core/privacy_coverage_model.py`
- `tests/test_privacy_coverage_model.py`
- `tests/fixtures/production_scale_coverage.py`
- `tools/benchmark_privacy_coverage_solver.py`

Modify:

- `core/privacy_coverage_solver.py`
- `tests/test_privacy_coverage_solver.py`
- `tests/test_privacy_coverage_verifier.py`
- `docs/CORE_TECHNICAL_DOC.md`
- `docs/production-testing.md`

Do not change public request, result, certificate, CLI, TUI, or YAML types.

Do not change dependency files in this plan.

## Test-first sequence

### Step 1: lock the algebra

Add tests that compare every new linear expression with direct weighted shares.

Use all approved rules, metric counts, and weight-bound corners.

Test values immediately below, at, and above each policy threshold.

Watch the tests fail before the new model module exists.

### Step 2: lock conservative presolve

Add rule-dominance tests for merchant and non-merchant scopes.

Prove that every removed rule has a retained dominating rule.

Add always-true, uncertain, and impossible witness tests.

Compare pruned and unpruned decisions on deterministic small fixtures.

### Step 3: lock model size

Generate a sanitized fixture with 242 units, 33 peers, and three metrics.

Do not copy confidential categories, values, or identifiers.

Compile the model without solving it.

Assert all these ceilings for Stage 1:

- total variables are below 60,000
- integer variables are below 42,224
- nonzero coefficients are below 1,350,000
- no cap or witness row has more than four nonzeros
- one mean-weight row exists for each unit and metric

These limits require at least 50% fewer integer variables.

They also require at least 75% fewer nonzero coefficients.

### Step 4: implement the staged solver

Keep each stage green before the next stage starts.

Add stage failure tests for timeout, nonzero gap, malformed output, and infeasibility.

Assert that no later stage runs after an unproven Stage 1 result.

### Step 5: replace deterministic tie-breaking

For small binary masks, compare block results with bit-by-bit results.

Use exhaustive masks for at least two block boundaries.

Test canonical rule selection after final weights.

Delete the obsolete per-unit and per-rule solve loops.

### Step 6: preserve verification

Run the independent verifier on every solver fixture.

Add tamper tests for the release count, dual bound, gap, weights, and rule map.

Do not modify verifier logic to accept a new solver result.

## Benchmark tool contract

The benchmark tool must accept a generated sanitized fixture.

It must print one JSON object to standard output.

Include only safe values:

- unit count
- peer count
- metric count
- variable counts
- integer variable count
- row count
- nonzero count
- stage durations
- peak process memory
- solver states
- release count
- dual bound
- MIP gap
- verifier result

Do not print unit keys, categories, peer identities, source values, or weights.

Do not write a report file by default.

## Local acceptance

Run:

```text
uv sync --extra dev --extra release
uv lock --check
uv run ruff check benchmark.py tui_app.py core utils scripts tools tests
uv run mypy core utils scripts tools
uv run pytest -n 4 --dist loadfile
```

Run the sanitized production-scale benchmark in a fresh process.

Require these results:

- peak resident memory is at most 2 GiB
- Stage 1 completes within 10 minutes
- the complete solve finishes within 20 minutes
- the solver reports an optimal primary result
- the MIP gap is zero
- the dual bound equals the release count
- the independent verifier passes

Time limits apply to the approved Edge Node class.

Local workstation times are diagnostic only.

## Getnet isolated acceptance

Use the immutable downloaded benchmark input outside the Autobench repository.

Run each quarter in a separate process.

Keep every result under an isolated Getnet candidate folder.

Require these results for all five quarters:

- no `MemoryError`
- peak resident memory is at most 2 GiB
- each quarter finishes within 15 minutes
- every solver state is `optimal`
- every MIP gap is zero
- every dual bound equals the release count
- every independent verifier result is `verifier_passed`
- every certificate digest matches its candidate universe

Then run the complete Getnet dashboard-feed pipeline.

Require the current producer, consumer, projection, and provenance checks.

Compare the three isolated EY files with accepted commit `f745a318`.

Explain every material mismatch with row, hash, and certificate evidence.

Do not replace `outputs/dashboard_feed/current`.

Do not publish or promote an isolated candidate.

## Required commits

Use these atomic commit groups:

1. `test: define scalable coverage model contract`
2. `refactor: normalize privacy coverage model`
3. `fix: reduce coverage solver stages and tie breaks`
4. `docs: record coverage solver scale contract`

Do not commit a red test state.

Do not combine unrelated changes.

## STOP conditions

Stop immediately when any condition is true:

- A rewritten row differs from direct policy evaluation.
- A removed rule can uniquely authorize any tested share vector.
- A witness classification is not valid across all weight bounds.
- Stage 1 lacks an optimal status, zero gap, or matching dual bound.
- The independent verifier fails.
- The sanitized model exceeds any model-size ceiling.
- Any Getnet quarter exceeds 2 GiB peak resident memory.
- Any Getnet quarter exceeds 15 minutes.
- A new runtime dependency appears necessary.
- The approved Edge Node cannot run the committed SciPy stack.
- A change requires weaker privacy limits or wider numeric tolerance.
- A test requires confidential Getnet data in Autobench.
- An accepted Getnet output changes before explicit promotion approval.

Report the exact stage, model statistics, solver status, and evidence path.

Do not add a fallback solver or compatibility path.

## Completion contract

Plan 003 is complete only when all conditions are true:

- The old dense formulation is deleted.
- The public interface remains unchanged.
- All local checks pass.
- The sanitized scale benchmark meets every limit.
- All five isolated Getnet quarters return proven certificates.
- The full isolated Getnet candidate completes.
- The candidate comparison report explains every material mismatch.
- No accepted output or remote release is replaced.
- Required source and documentation commits exist.
