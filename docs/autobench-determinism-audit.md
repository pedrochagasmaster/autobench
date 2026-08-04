# Autobench determinism audit

Date: 2026-08-03

## Decision

Autobench does not guarantee identical analytical results for identical data and settings.

The main defect is process hash order. Standard analysis builds the peer list from a Python set.
The LP then uses this list as its variable order and its rank tie order.

A focused test produced different weights from identical input and configuration.
Only `PYTHONHASHSEED` changed.

Do not publish the proposed FAQ answer as “Yes.”

A safe current answer is:

> No. Autobench usually repeats results in one fixed environment. However, it does not yet guarantee this for every method and configuration.

## Scope

This audit covers these paths:

- Global LP optimization.
- Greedy and seeded subset search.
- Per-dimension fallback.
- The L-BFGS-B heuristic fallback.
- All committed presets.
- Share and rate analysis.
- CLI, TUI, and Python calls.
- Supported Python and dependency versions.
- Output-only time and identifier changes.

The audit used repository source, tests, locks, plans, and ADRs only.

## Findings

### 1. Process hash order can change analytical weights

The standard category builder groups rows first. It then creates `peers` with `list(set(...))`.
Python set order is not a stable product contract.

Source: `core/category_builder.py:55-90`.

The LP assigns each peer an index from that list. It also sorts equal base shares without a business tie key.
The resulting rank constraints can therefore change when peer order changes.

Source: `core/solvers/lp_solver.py:78-129`.

This is not only a report-order issue. A focused process test used five peers with equal total volume.
One peer had a different category mix. The cap was 35 percent.

Selected results were:

- Seed 1: all weights were `1.0`; absolute slack was `0.45`.
- Seed 4: weight A was `0.1627906977`; other weights were `1.2093023256`; slack was zero.
- Seed 5: one peer was `1.5088339223`; other weights were `0.8727915194`.

Thus, identical data and configuration can produce different analytical results across fresh processes.

This defect affects all standard, non-time category builds. It can reach global and per-dimension modes.
Time-aware building uses ordered group indexes for peers instead.

Source: `core/category_builder.py:92-178`.

### 2. LP repeatability is conditional

The LP tries `highs`, `highs-ds`, then `highs-ipm`. It accepts the first successful method.

Source: `core/solvers/lp_solver.py:232-251`.

The call fixes only `maxiter`. It does not fix solver threads or a solver random seed.

Source: `core/solvers/lp_solver.py:68-76` and `core/solvers/lp_solver.py:232-243`.

The LP is repeatable only when these inputs remain fixed:

- Peer and category order.
- SciPy and HiGHS behavior.
- Numeric libraries and platform.
- Solver success status.

The project documentation already states this condition. It does not claim universal LP repeatability.

Source: `docs/CORE_TECHNICAL_DOC.md:1272-1284`.

### 3. The heuristic has no random search, but it has numeric sensitivity

The path called “Bayesian” is an L-BFGS-B minimization. It uses a fixed all-one or target-weight start.
It contains no random-number call.

Source: `core/solvers/heuristic_solver.py:225-256`.

For fixed array order and one fixed binary environment, the source gives a repeatable start and method.
This is not a cross-platform guarantee. The repository warns about small numeric differences.

Source: `docs/CORE_TECHNICAL_DOC.md:195-198` and `docs/CORE_TECHNICAL_DOC.md:1278-1284`.

The heuristic also uses the incoming peer order for arrays and output weights.
The standard set-order defect therefore reaches this method too.

Source: `core/solvers/heuristic_solver.py:38-50`, `core/solvers/heuristic_solver.py:89-113`, and `core/solvers/heuristic_solver.py:258-293`.

### 4. Random subset search now uses a fixed seed

The current random subset path creates `random.Random(0)`. It shuffles each combination list with that object.

Source: `core/subset_search.py:149-164`.

Thus, this search order repeats for the same ordered dimension list.
It does not correct nondeterministic peer order inside each LP trial.

Two technical-document sections are stale. They say random search has no fixed seed.

Source: `docs/CORE_TECHNICAL_DOC.md:195-198` and `docs/CORE_TECHNICAL_DOC.md:1278-1284`.

### 5. Greedy subset search uses input order as its tie rule

Greedy search drops the dimension with the maximum unbalance score.
Python `max` returns the first matching item when scores tie.

Source: `core/subset_search.py:116-148`.

This is repeatable for the same ordered dimension list. It is not order-independent.
Explicit dimensions keep caller order. Auto-detected dimensions keep CSV column order.

Source: `core/analysis_run.py:980-1002` and `core/data_loader.py:878-890`.

### 6. Presets do not remove the defect

Every committed preset enters the same optimizer pipeline. The pipeline tries LP first.
It can then use subset search, per-dimension fallback, or the heuristic.

Source: `core/global_weight_optimizer.py:60-84` and `core/global_weight_optimizer.py:185-380`.

The preset files change bounds, slack, search, and iteration values.
They do not sort peers or add a stable rank tie key.

Sources:

- `presets/balanced_default.yaml:1-42`.
- `presets/compliance_strict.yaml:1-40`.
- `presets/low_distortion.yaml:1-44`.
- `presets/minimal_distortion.yaml:1-43`.
- `presets/research_exploratory.yaml:1-40`.
- `presets/strategic_consistency.yaml:1-43`.

The defect therefore applies to every preset when the standard category path runs.

### 7. Per-dimension fallback does not give a stronger guarantee

The fallback solves each dimension with the original peer list.
It tries LP first and then the L-BFGS-B heuristic.

Source: `core/dimensional_analyzer.py:783-854`.

The same process-order and numeric conditions apply. A dimension loop follows the given dimension order.

### 8. CLI and TUI use the same engine

The CLI builds a shared request. It then calls the shared share or rate executor.

Source: `benchmark.py:671-676` and `benchmark.py:745-750`.

The TUI also calls the shared executor with `AnalysisRunRequest`.

Source: `tui_app.py:1387-1403` and `core/contracts.py:449-480`.

Therefore, equal resolved requests reach the same engine. This removes one interface-specific algorithm difference.
It does not remove process hash order or runtime differences.

TUI and CLI settings must still resolve to the same request. A similar screen selection is not sufficient evidence.

### 9. Supported runtimes do not use one numeric stack

The package supports Python 3.10 and later. Its dependency ranges permit many NumPy and SciPy versions.

Source: `pyproject.toml:5-17`.

The current lock selects different NumPy and SciPy versions by Python version.
For example, SciPy is 1.15.3 below Python 3.11 and 1.18.0 on Python 3.12 or later.

Source: `uv.lock:3-24`.

The production Edge Node design is narrower. It uses an approved Python 3.10 runtime.
It identifies the immutable environment by dependency-bundle digest.

Source: `install.sh:10-23`, `docs/adr/0001-shared-global-runtime.md:30-52`, and `plans/001-mirror-shared-global-runtime.md:183-186`.

One production bundle reduces version drift. It does not fix the peer-order defect.
The broad package support prevents a cross-runtime identity claim.

### 10. Full output files change even when analytical values do not

Run metadata records the current time. Default output names also include the current time.

Source: `core/analysis_run.py:714-777` and `core/analysis_run.py:1655-1666`.

Telemetry creates a new session UUID. Some denied-output paths also use a UUID.

Source: `core/telemetry/__init__.py:52-61`, `utils/logger.py:88-95`, and `core/privacy_output_policy.py:416-424`.

Thus, workbooks, JSON files, logs, paths, and telemetry are not byte-identical across runs.
These changes are output metadata. They are separate from the analytical-weight defect.

### 11. Current tests do not prove end-to-end determinism

Solver tests check feasibility, limits, and summary statistics.
They do not repeat a run across process hash seeds.

Source: `tests/test_solvers.py:74-105` and `tests/test_solvers.py:187-317`.

Subset tests check trial records and failures. They do not test seeded combination order end to end.

Source: `tests/test_subset_search.py:47-162`.

The interface contract tests compare request construction. They do not compare analytical outputs across interfaces.

Source: `tests/test_tui_contracts.py:23-33` and `tests/test_tui_contracts.py:52-68`.

No current test covers these conditions:

- Different `PYTHONHASHSEED` values.
- Different Python or SciPy versions.
- Different supported platforms.
- Solver thread settings.
- Row-order permutations.
- Equal-volume rank ties.
- Full repeat runs for every preset and fallback.
- Exact CLI, TUI, and Python result parity.

## Row-order assessment

Pandas group operations build category totals before optimization.
The normal path does not explicitly sort the input rows first.

Source: `core/category_builder.py:63-85`.

The lean path sums each chunk and then sums the partial tables.

Source: `core/data_loader.py:440-503`.

Positive floating-point addition can depend on grouping order and aggregation stages.
The repository has no row-permutation determinism test.

This audit did not find a row-order failure with a small focused sum test.
Therefore, row-order sensitivity remains unproved, but it is also not guaranteed absent.

## Focused commands

Environment check:

```powershell
uv run python --version
uv run python -c "import scipy,numpy,pandas; print('scipy',scipy.__version__,'numpy',numpy.__version__,'pandas',pandas.__version__)"
```

Observed environment:

```text
Python 3.13.14
scipy 1.18.0 numpy 2.5.1 pandas 2.3.3
```

Focused tests:

```powershell
uv run python -m pytest tests/test_solvers.py tests/test_subset_search.py tests/test_tui_contracts.py tests/test_config_precedence.py -q
```

Result:

```text
41 passed in 2.87s
```

Direct `uv run pytest ...` failed during test discovery on this Windows host.
It could not import `tests.fixtures`. `uv run python -m pytest ...` passed.

The process-order experiment ran the same inline Python program eight times.
It set `PYTHONHASHSEED` to `1,2,3,4,5,10,42,99` before each process.
The program called `CategoryBuilder.build_categories` and `LPSolver.solve` directly.

## Required work before a strong “Yes” answer

The following changes are necessary for a universal guarantee:

1. Sort peers by one documented canonical key before all solver calls.
2. Add a stable business tie key for equal base shares.
3. Define exact numeric tolerances for result equality.
4. Define the supported runtime bundle for the guarantee.
5. Pin or control solver thread behavior where the solver permits it.
6. Add process, row-order, preset, fallback, interface, and runtime tests.
7. Separate analytical equality from byte-identical artifact equality.
8. Correct the stale random-search documentation.

Until this work passes, Autobench has conditional repeatability, not guaranteed determinism.
