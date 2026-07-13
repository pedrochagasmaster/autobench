# Codebase Simplification and End-to-End Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove unnecessary internal complexity while preserving Autobench's documented API, privacy behavior, user-visible outputs, and CLI/TUI contracts.

**Architecture:** Delete unconsumed internal surfaces first, then replace repeated export and subset-search paths with small private helpers. Keep orchestration, report schemas, and privacy policy unchanged. Lock behavior with focused tests, the full automated suite, and local terminal-driven CLI/TUI workflows.

**Tech Stack:** Python 3.10+, pandas, Textual, pytest, Ruff, mypy, tmux.

---

## File Map

- `core/contracts.py`: remove the unused inverse weighting-result adapter.
- `core/dimensional_analyzer.py`: remove the unconsumed deprecated global-weight method.
- `utils/preset_manager.py`: remove unused aliases and invalid-preset state while retaining error logging.
- `core/preset_comparison.py`: use its existing analyzer-factory seam explicitly and keep imports at module scope.
- `benchmark.py`: remove the preset-comparison compatibility wrapper and its now-unused imports.
- `core/balanced_export.py`: centralize grouping, weighting, sorting, sanitization, and CSV writing.
- `core/subset_search.py`: centralize one subset trial's solve and diagnostic result.
- `core/telemetry/__init__.py`: centralize the never-raise wrapper behavior.
- `core/output_artifacts.py`: remove the writer property adapter and centralize rate-result flattening.
- `core/report_generator.py`: call report-content helpers directly.
- `tests/test_internal_surface.py`: assert intentionally removed internal compatibility surfaces stay absent.
- `tests/test_balanced_export.py`: characterize the new grouping helper and exported schemas.
- `tests/test_subset_search.py`: characterize trial success, slack rejection, and no-category outcomes.
- `tests/telemetry/test_public_helpers.py`: characterize the shared telemetry safety helper.
- `tests/test_enhanced_features.py`: consume preset comparison from its owning core module.
- `tests/test_preset_workflow.py`: remove the obsolete alias regression test and historical commentary.
- `tests/test_output_artifacts.py`: test direct output behavior rather than the removed writer adapter.
- `tests/test_report_generator_dependencies.py`: test rate-conversion helpers at their owning module.

### Task 1: Establish a clean baseline

**Files:** None.

- [ ] **Step 1: Confirm the branch and clean worktree**

Run:

```bash
git status --short --branch
```

Expected: branch `cursor/deslop-e2e-c5b9`; only this plan commit may be pending before it is committed.

- [ ] **Step 2: Run the focused baseline**

Run:

```bash
python -m pytest \
  tests/test_export_validation.py \
  tests/test_analysis_run_integration.py \
  tests/test_global_weight_optimizer_fallbacks.py \
  tests/telemetry/test_public_helpers.py \
  tests/test_enhanced_features.py \
  tests/test_preset_workflow.py \
  tests/test_output_artifacts.py \
  tests/test_report_generator_dependencies.py -q
```

Expected: PASS. Any baseline failure must be diagnosed before production edits.

- [ ] **Step 3: Capture baseline source size outside the repository**

Run:

```bash
python - <<'PY' >/tmp/autobench-simplification-baseline.txt
from pathlib import Path

paths = [
    "benchmark.py",
    "core/balanced_export.py",
    "core/contracts.py",
    "core/dimensional_analyzer.py",
    "core/output_artifacts.py",
    "core/preset_comparison.py",
    "core/report_generator.py",
    "core/subset_search.py",
    "core/telemetry/__init__.py",
    "utils/preset_manager.py",
]
for name in paths:
    print(f"{name}: {len(Path(name).read_text(encoding='utf-8').splitlines())}")
PY
```

Expected: `/tmp/autobench-simplification-baseline.txt` contains one line count per production file.

### Task 2: Remove dead internal surfaces and the benchmark compatibility seam

**Files:**
- Create: `tests/test_internal_surface.py`
- Modify: `core/contracts.py`
- Modify: `core/dimensional_analyzer.py`
- Modify: `utils/preset_manager.py`
- Modify: `core/preset_comparison.py`
- Modify: `benchmark.py`
- Modify: `tests/test_enhanced_features.py`
- Modify: `tests/test_preset_workflow.py`

- [ ] **Step 1: Write the failing internal-surface test**

Create `tests/test_internal_surface.py`:

```python
"""Keep removed internal compatibility surfaces from growing back."""

import benchmark
import core.contracts as contracts
from core.dimensional_analyzer import DimensionalAnalyzer
from utils.preset_manager import PresetManager


def test_obsolete_internal_compatibility_surfaces_are_absent() -> None:
    assert not hasattr(contracts, "apply_weighting_result_to_analyzer")
    assert not hasattr(DimensionalAnalyzer, "calculate_global_weights")
    assert not hasattr(PresetManager, "load_preset")
    assert not hasattr(PresetManager, "invalid_presets")
    assert not hasattr(PresetManager, "get_invalid_presets")
    assert not hasattr(PresetManager, "get_preset_choices")
    assert not hasattr(benchmark, "run_preset_comparison")
```

- [ ] **Step 2: Verify RED**

Run:

```bash
python -m pytest tests/test_internal_surface.py -q
```

Expected: FAIL because the listed compatibility surfaces still exist.

- [ ] **Step 3: Remove dead definitions and state**

Delete `apply_weighting_result_to_analyzer` from `core/contracts.py` and
`calculate_global_weights` from `core/dimensional_analyzer.py`.

In `utils/preset_manager.py`, delete `_invalid_presets`, its assignment on
validation failure, `load_preset`, both invalid-preset accessors, and
`get_preset_choices`. Keep the validation error visible:

```python
errors = ConfigValidator.validate(preset_data)
if errors:
    logger.error(
        "Skipping invalid preset %s: %s",
        preset_file.name,
        "; ".join(errors),
    )
    continue
```

In `benchmark.py`, delete the local `run_preset_comparison`, remove the pandas,
shared-preset-comparison, and `build_dimensional_analyzer` imports, and simplify
preset choices to:

```python
try:
    preset_choices = PresetManager().list_presets()
except Exception:
    preset_choices = []
```

- [ ] **Step 4: Make preset comparison own its dependencies**

Move `ConfigManager` and `PresetManager` imports to the top of
`core/preset_comparison.py`. Add an `analyzer_factory` keyword parameter to
`run_preset_comparison` and `_run_single_preset_variant`, and call that factory
instead of importing `core.analysis_run` inside the function:

```python
from typing import Any, Callable, Dict, List, Optional

AnalyzerFactory = Callable[..., tuple[Any, Any]]


def _run_single_preset_variant(
    *,
    analyzer_factory: AnalyzerFactory,
    preset_name: str,
    variant_name: str,
    consistent_weights: bool,
    df: pd.DataFrame,
    metric_col: str,
    dimensions: List[str],
    entity_col: str,
    target_entity: Optional[str],
    time_col: Optional[str],
    analysis_type: str,
    total_col: Optional[str],
    numerator_cols: Optional[Dict[str, str]],
    logger: logging.Logger,
) -> Dict[str, Any]:
    preset_config = ConfigManager(preset=preset_name)
    resolved = preset_config.resolve()
    analyzer, _ = analyzer_factory(
        target_entity=target_entity,
        entity_col=entity_col,
        resolved=resolved,
        time_col=time_col,
        debug_mode=False,
        bic_percentile=resolved.analysis.best_in_class_percentile,
        logger=logger,
        consistent_weights=consistent_weights,
    )
```

Pass the caller's `logger` and `analyzer_factory` through every variant call.
`core.analysis_run` already supplies `build_dimensional_analyzer`.

Update `tests/test_enhanced_features.py` to import
`run_preset_comparison` from `core.preset_comparison` and
`build_dimensional_analyzer` from `core.analysis_run`, then pass
`analyzer_factory=build_dimensional_analyzer` in both direct calls.

Delete the alias test and historical alias commentary from
`tests/test_preset_workflow.py`.

- [ ] **Step 5: Commit and push before post-change tests**

Run:

```bash
git add benchmark.py core/contracts.py core/dimensional_analyzer.py \
  core/preset_comparison.py utils/preset_manager.py \
  tests/test_internal_surface.py tests/test_enhanced_features.py \
  tests/test_preset_workflow.py
git commit -m "refactor: remove obsolete internal compatibility surfaces"
git push -u origin cursor/deslop-e2e-c5b9
```

- [ ] **Step 6: Verify GREEN**

Run:

```bash
python -m pytest \
  tests/test_internal_surface.py \
  tests/test_enhanced_features.py \
  tests/test_preset_workflow.py \
  tests/test_preset_validation.py -q
```

Expected: PASS.

### Task 3: Consolidate balanced export grouping and writing

**Files:**
- Create: `tests/test_balanced_export.py`
- Modify: `core/balanced_export.py`

- [ ] **Step 1: Write a failing helper characterization**

Create `tests/test_balanced_export.py` with a small DataFrame containing a target,
two peers, two time periods, and one suppressed category. Import the new
private helper and assert that it excludes the target only when requested,
applies per-dimension multipliers, and skips suppression:

```python
from types import SimpleNamespace

import pandas as pd

from core.balanced_export import _iter_balanced_groups
from core.contracts import WeightLookup


def test_iter_balanced_groups_handles_target_time_weights_and_suppression() -> None:
    df = pd.DataFrame(
        {
            "issuer_name": ["Target", "P1", "P2", "Target", "P1", "P2"],
            "segment": ["A", "A", "A", "B", "B", "B"],
            "period": [1, 1, 1, 2, 2, 2],
            "metric": [100, 10, 20, 200, 30, 40],
        }
    )
    analyzer = SimpleNamespace(
        entity_column="issuer_name",
        target_entity="Target",
        time_column="period",
    )
    weights = WeightLookup(
        global_weights={"P1": {"multiplier": 2.0}, "P2": {"multiplier": 3.0}}
    )
    groups = list(
        _iter_balanced_groups(
            df,
            analyzer=analyzer,
            dimensions=["segment"],
            metric_columns=["metric"],
            weights=weights,
            suppressed_categories=[
                {"dimension": "segment", "category": "B", "time_period": 2}
            ],
            exclude_target=True,
        )
    )
    assert len(groups) == 1
    group = groups[0]
    assert (group.dimension, group.category, group.time_period) == ("segment", "A", 1)
    assert group.rows["issuer_name"].tolist() == ["P1", "P2"]
    assert group.peer_weights.tolist() == [2.0, 3.0]
```

- [ ] **Step 2: Verify RED**

Run:

```bash
python -m pytest tests/test_balanced_export.py -q
```

Expected: collection FAIL because `_iter_balanced_groups` does not exist.

- [ ] **Step 3: Implement the shared grouping seam**

In `core/balanced_export.py`, add a private frozen dataclass containing
`dimension`, `category`, `time_period`, `category_rows`, `rows`, and
`peer_weights`. Implement `_resolve_time_column` and `_iter_balanced_groups`.
Use this implementation:

```python
@dataclass(frozen=True)
class _BalancedGroup:
    dimension: str
    category: Any
    time_period: Any
    category_rows: pd.DataFrame
    rows: pd.DataFrame
    peer_weights: pd.Series


def _resolve_time_column(df: pd.DataFrame, analyzer: Any) -> Optional[str]:
    time_col = getattr(analyzer, "time_column", None)
    return time_col if time_col in df.columns else None


def _iter_balanced_groups(
    df: pd.DataFrame,
    *,
    analyzer: Any,
    dimensions: List[str],
    metric_columns: List[str],
    weights: WeightLookup,
    suppressed_categories: Optional[List[Dict[str, Any]]],
    exclude_target: bool,
) -> Iterator[_BalancedGroup]:
    entity_col = analyzer.entity_column
    time_col = _resolve_time_column(df, analyzer)
    for dimension in dimensions:
        group_cols = [entity_col, dimension]
        if time_col is not None and time_col != dimension:
            group_cols.append(time_col)
        aggregations = {
            column: "sum"
            for column in metric_columns
            if column in df.columns and column not in group_cols
        }
        if not aggregations:
            continue
        aggregated = df.groupby(group_cols).agg(aggregations).reset_index()
        time_periods = (
            sorted(aggregated[time_col].unique())
            if time_col is not None
            else [None]
        )
        weight_map = weights.map_for_dimension(dimension)
        for category in aggregated[dimension].unique():
            for time_period in time_periods:
                if is_category_suppressed(
                    suppressed_categories or [],
                    dimension,
                    category,
                    time_period,
                ):
                    continue
                mask = aggregated[dimension] == category
                if time_col is not None:
                    mask &= aggregated[time_col] == time_period
                category_rows = aggregated[mask]
                if category_rows.empty:
                    continue
                rows = category_rows
                if exclude_target and analyzer.target_entity is not None:
                    rows = rows[rows[entity_col] != analyzer.target_entity]
                yield _BalancedGroup(
                    dimension=dimension,
                    category=category,
                    time_period=time_period,
                    category_rows=category_rows,
                    rows=rows,
                    peer_weights=rows[entity_col].map(weight_map).fillna(1.0),
                )
```

Use it from `get_balanced_metrics_df` with `exclude_target=False`, and from both
CSV export modes with `exclude_target=True`.

Add these two small helpers and use them from both export branches:

```python
def _weighted_sum(group: _BalancedGroup, column: str) -> float:
    return float((group.rows[column] * group.peer_weights).sum())


def _write_csv(
    rows: List[Dict[str, Any]],
    *,
    csv_output: str,
    time_col: Optional[str],
) -> None:
    export_df = pd.DataFrame(rows)
    sort_cols = ["Dimension"]
    if time_col is not None and time_col in export_df.columns:
        sort_cols.append(time_col)
    sort_cols.append("Category")
    export_df = export_df.sort_values(sort_cols)
    for column in export_df.select_dtypes(include="object").columns:
        export_df[column] = export_df[column].map(sanitize_cell)
    export_df.to_csv(csv_output, index=False)
```

Keep every existing rate/share column name, rounding rule, raw calculation,
target-vs-peer share calculation, logger message, and stdout line unchanged.

- [ ] **Step 4: Commit and push before post-change tests**

Run:

```bash
git add core/balanced_export.py tests/test_balanced_export.py
git commit -m "refactor: consolidate balanced export grouping"
git push -u origin cursor/deslop-e2e-c5b9
```

- [ ] **Step 5: Verify GREEN and schema parity**

Run:

```bash
python -m pytest \
  tests/test_balanced_export.py \
  tests/test_export_validation.py \
  tests/test_analysis_run_integration.py \
  tests/test_export_sanitization.py \
  tests/test_category_suppression.py -q
```

Expected: PASS with no output-schema or suppression differences.

### Task 4: Consolidate subset-search trial evaluation

**Files:**
- Create: `tests/test_subset_search.py`
- Modify: `core/subset_search.py`

- [ ] **Step 1: Write failing trial tests**

Create `tests/test_subset_search.py` with this setup and three tests:

```python
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Dict

import pandas as pd

import core.subset_search as subset_search
from core.subset_search import _solve_trial


@dataclass
class _SolverResult:
    success: bool
    weights: Dict[str, float]
    stats: Dict[str, Any]


class _Solver:
    def __init__(self, result: _SolverResult) -> None:
        self.result = result
        self.calls = 0

    def solve(self, _request: object) -> _SolverResult:
        self.calls += 1
        return self.result


def _analyzer(categories: list[dict[str, Any]], solver: _Solver) -> SimpleNamespace:
    analyzer = SimpleNamespace(
        lp_solver=solver,
        last_lp_stats={},
        trigger_subset_on_slack=False,
        max_cap_slack=0.1,
    )
    analyzer._build_categories = lambda _df, _metric, _dims: (
        categories,
        {"P1": 1.0},
        ["P1"],
    )
    analyzer._is_slack_excess = lambda slack: bool(slack and slack > 0.1)
    return analyzer


def test_solve_trial_returns_successful_weights_and_stats(monkeypatch) -> None:
    monkeypatch.setattr(subset_search, "build_lp_request", lambda *_a, **_kw: object())
    solver = _Solver(
        _SolverResult(
            success=True,
            weights={"P1": 1.0},
            stats={"sum_slack": 0.0, "max_slack": 0.0, "method": "LP"},
        )
    )
    analyzer = _analyzer([{"dimension": "d1"}], solver)

    outcome = _solve_trial(
        analyzer,
        df=pd.DataFrame({"metric": [1]}),
        metric_col="metric",
        trial_dims=["d1"],
        max_concentration=25.0,
        peers=["P1"],
    )

    assert outcome.success is True
    assert outcome.weights == {"P1": 1.0}
    assert outcome.sum_slack == 0.0
    assert analyzer.last_lp_stats == {
        "sum_slack": 0.0,
        "max_slack": 0.0,
        "method": "LP",
    }


def test_solve_trial_rejects_excess_slack(monkeypatch) -> None:
    monkeypatch.setattr(subset_search, "build_lp_request", lambda *_a, **_kw: object())
    solver = _Solver(
        _SolverResult(
            success=True,
            weights={"P1": 1.0},
            stats={"sum_slack": 0.2, "max_slack": 0.2, "method": "LP"},
        )
    )
    analyzer = _analyzer([{"dimension": "d1"}], solver)
    analyzer.trigger_subset_on_slack = True

    outcome = _solve_trial(
        analyzer,
        df=pd.DataFrame({"metric": [1]}),
        metric_col="metric",
        trial_dims=["d1"],
        max_concentration=25.0,
        peers=["P1"],
    )

    assert outcome.success is False
    assert outcome.note == "Rejected due to slack 0.200000 > 0.100000"


def test_solve_trial_skips_solver_without_categories(monkeypatch) -> None:
    monkeypatch.setattr(subset_search, "build_lp_request", lambda *_a, **_kw: object())
    solver = _Solver(_SolverResult(True, {"P1": 1.0}, {}))
    analyzer = _analyzer([], solver)

    outcome = _solve_trial(
        analyzer,
        df=pd.DataFrame({"metric": [1]}),
        metric_col="metric",
        trial_dims=["d1"],
        max_concentration=25.0,
        peers=["P1"],
    )

    assert outcome.categories == []
    assert outcome.success is False
    assert solver.calls == 0
```

- [ ] **Step 2: Verify RED**

Run:

```bash
python -m pytest tests/test_subset_search.py -q
```

Expected: collection FAIL because `_solve_trial` does not exist.

- [ ] **Step 3: Implement one trial path**

Move `itertools` to the module imports. Add a frozen `_TrialOutcome` dataclass
with categories, success, weights, sum/max slack, method, and note. Implement
`_solve_trial` once and `_record_trial` once. Both greedy and randomized loops
must call them. Use:

```python
@dataclass(frozen=True)
class _TrialOutcome:
    categories: List[Dict[str, Any]]
    success: bool
    weights: Optional[Dict[str, float]]
    sum_slack: Optional[float]
    max_slack: Optional[float]
    method: Optional[str]
    note: str = ""


def _solve_trial(
    analyzer: Any,
    *,
    df: pd.DataFrame,
    metric_col: str,
    trial_dims: List[str],
    max_concentration: float,
    peers: List[str],
) -> _TrialOutcome:
    categories, peer_volumes, _ = analyzer._build_categories(
        df, metric_col, trial_dims
    )
    if not categories:
        return _TrialOutcome([], False, None, None, None, None)
    result = analyzer.lp_solver.solve(
        build_lp_request(
            analyzer,
            peers=peers,
            categories=categories,
            max_concentration=max_concentration,
            peer_volumes=peer_volumes,
        )
    )
    if not result or not result.success:
        return _TrialOutcome(categories, False, None, None, None, None)
    analyzer.last_lp_stats = result.stats
    stats = dict(result.stats)
    sum_slack = float(stats.get("sum_slack", 0.0) or 0.0)
    max_slack = float(stats.get("max_slack", 0.0) or 0.0)
    note = ""
    success = True
    if analyzer.trigger_subset_on_slack and analyzer._is_slack_excess(sum_slack):
        success = False
        note = (
            f"Rejected due to slack {sum_slack:.6f} > "
            f"{analyzer.max_cap_slack:.6f}"
        )
    return _TrialOutcome(
        categories,
        success,
        result.weights,
        sum_slack,
        max_slack,
        stats.get("method"),
        note,
    )


def _record_trial(
    analyzer: Any,
    *,
    attempt: int,
    trial_dims: List[str],
    outcome: _TrialOutcome,
    note: Optional[str] = None,
) -> None:
    resolved_note = outcome.note if note is None else note
    analyzer.subset_search_results.append(
        {
            "Attempt": attempt,
            "Dimensions": list(trial_dims),
            "Count": len(trial_dims),
            "Success": bool(outcome.success),
            "Max_Slack": None if resolved_note else outcome.max_slack,
            "Sum_Slack": None if resolved_note else outcome.sum_slack,
            "Method": outcome.method,
            "Note": resolved_note,
        }
    )
```

Preserve:

- seeded randomized order (`random.Random(0)`);
- greedy dimension-drop scoring;
- exact result keys and notes;
- `last_lp_stats`;
- slack rejection semantics;
- best-score tie breaking;
- both early-exit conditions.

- [ ] **Step 4: Commit and push before post-change tests**

Run:

```bash
git add core/subset_search.py tests/test_subset_search.py
git commit -m "refactor: unify subset search trial evaluation"
git push -u origin cursor/deslop-e2e-c5b9
```

- [ ] **Step 5: Verify GREEN**

Run:

```bash
python -m pytest \
  tests/test_subset_search.py \
  tests/test_global_weight_optimizer_fallbacks.py \
  tests/test_solvers.py \
  tests/test_golden_outputs.py -q
```

Expected: PASS.

### Task 5: Collapse repetitive telemetry safety wrappers

**Files:**
- Modify: `core/telemetry/__init__.py`
- Modify: `tests/telemetry/test_public_helpers.py`

- [ ] **Step 1: Write the failing safety-helper test**

Add:

```python
def test_run_safely_swallows_callback_exceptions() -> None:
    _inject_service(lambda _record: None)

    def fail(_service: TelemetryService) -> None:
        raise RuntimeError("boom")

    telemetry._run_safely("test", fail)
```

- [ ] **Step 2: Verify RED**

Run:

```bash
python -m pytest tests/telemetry/test_public_helpers.py::test_run_safely_swallows_callback_exceptions -q
```

Expected: FAIL because `_run_safely` does not exist.

- [ ] **Step 3: Add one typed safety helper**

Import `Callable` at module scope and implement:

```python
def _run_safely(
    operation: str,
    callback: Callable[[TelemetryService], None],
) -> None:
    try:
        callback(_get_service())
    except Exception:
        logger.debug("telemetry %s failed", operation, exc_info=True)
```

Reduce each public helper to one `_run_safely` call. Keep all public names,
Literal argument types, never-raise behavior, and lazy singleton behavior.

- [ ] **Step 4: Commit and push before post-change tests**

Run:

```bash
git add core/telemetry/__init__.py tests/telemetry/test_public_helpers.py
git commit -m "refactor: share telemetry safety handling"
git push -u origin cursor/deslop-e2e-c5b9
```

- [ ] **Step 5: Verify GREEN**

Run:

```bash
python -m pytest tests/telemetry -q
```

Expected: PASS.

### Task 6: Remove output/report adapters and trim stale commentary

**Files:**
- Modify: `core/output_artifacts.py`
- Modify: `core/report_generator.py`
- Modify: `tests/test_internal_surface.py`
- Modify: `tests/test_output_artifacts.py`
- Modify: `tests/test_report_generator_dependencies.py`
- Modify: `utils/preset_manager.py`

- [ ] **Step 1: Extend the failing absence/helper tests**

Add `OutputArtifactWriter` and the two `ReportGenerator` pass-through methods to
`tests/test_internal_surface.py`. Add a direct `_flatten_rate_results` test to
`tests/test_output_artifacts.py`:

```python
from core.output_artifacts import _flatten_rate_results, write_outputs


def test_flatten_rate_results_names_rate_and_dimension() -> None:
    frame = pd.DataFrame({"Rate": [1.0]})
    flattened = _flatten_rate_results({"approval": {"channel": frame}})
    assert list(flattened) == ["approval_channel"]
    assert flattened["approval_channel"] is frame
```

Change the rate-conversion test to call
`core.report_content.should_convert_rate_column` directly.

- [ ] **Step 2: Verify RED**

Run:

```bash
python -m pytest \
  tests/test_internal_surface.py \
  tests/test_output_artifacts.py::test_flatten_rate_results_names_rate_and_dimension -q
```

Expected: FAIL for existing adapter surfaces and the missing flatten helper.

- [ ] **Step 3: Simplify artifact writing**

Move `ReportGenerator`, `ReportModel`, and Excel writer imports to module scope
in `core/output_artifacts.py`. Remove `OutputArtifactWriter` and replace it with
local values:

```python
report_model = artifacts.report_model or ReportModel.from_artifacts(artifacts)
output_file = artifacts.analysis_output_file or "benchmark_output.xlsx"
publication_file = artifacts.publication_output or output_file
output_format = (
    request.output_format
    if config is None
    else config.get("output", "output_format", default=request.output_format)
)
```

Implement `_flatten_rate_results` once and use it for publication and JSON.
Delete the adapter-focused mock test.

In `core/report_generator.py`, call `resolve_convert_all_rates` and
`should_convert_rate_column` directly and delete the two static delegates.

Trim only stale or redundant historical comments/docstrings in touched files.
Do not remove comments that explain privacy, output allow-lists, deterministic
ordering, or non-obvious compatibility behavior.

- [ ] **Step 4: Commit and push before post-change tests**

Run:

```bash
git add core/output_artifacts.py core/report_generator.py \
  utils/preset_manager.py tests/test_internal_surface.py \
  tests/test_output_artifacts.py tests/test_report_generator_dependencies.py
git commit -m "refactor: remove thin output and report adapters"
git push -u origin cursor/deslop-e2e-c5b9
```

- [ ] **Step 5: Verify GREEN**

Run:

```bash
python -m pytest \
  tests/test_internal_surface.py \
  tests/test_output_artifacts.py \
  tests/test_report_generator_dependencies.py \
  tests/test_json_output.py \
  tests/test_golden_outputs.py -q
```

Expected: PASS.

### Task 7: Run full automated verification

**Files:** No production changes unless a regression is found.

- [ ] **Step 1: Run static checks**

Run:

```bash
python -m ruff check .
python -m mypy --no-site-packages core/ utils/
```

Expected: both exit 0.

- [ ] **Step 2: Run the complete test suite**

Run:

```bash
python -m pytest -n 4 --dist loadfile
```

Expected: all tests pass with no warnings caused by this branch.

- [ ] **Step 3: Run the complete CLI gate**

Run:

```bash
python scripts/perform_gate_test.py
```

Expected: every share, rate, and config gate case passes.

- [ ] **Step 4: Compare source size**

Repeat Task 1's line-count script to
`/tmp/autobench-simplification-final.txt`, then run:

```bash
diff -u /tmp/autobench-simplification-baseline.txt /tmp/autobench-simplification-final.txt
```

Expected: net production-line reduction. Review any file that grew and confirm
the growth is test-locked shared logic rather than a new abstraction layer.

### Task 8: Exercise the complete local CLI feature surface

**Files:** Generate artifacts only under `/tmp/autobench-e2e`.

- [ ] **Step 1: Exercise discovery and configuration**

Run top-level, `share`, `rate`, `config`, and `telemetry` help; version; config
list; all six `config show` presets; config validation; and config generation
into `/tmp/autobench-e2e/generated.yaml`. Every command must exit 0 except a
second generate to the same path, which must exit 1 without overwriting.

- [ ] **Step 2: Run the core CLI sweep**

Run:

```bash
rm -rf /tmp/autobench-e2e/sweep
python scripts/generate_cli_sweep.py \
  --mode core \
  --out-dir /tmp/autobench-e2e/sweep \
  --csv tests/fixtures/gate_demo.csv \
  --entity-col issuer_name \
  --entity Target \
  --metric-col txn_cnt \
  --total-col total \
  --approved-col approved \
  --fraud-col fraud \
  --dimensions card_type channel \
  --time-col year_month
python scripts/run_cli_sweep.py \
  --sweep-dir /tmp/autobench-e2e/sweep \
  --results-json /tmp/autobench-e2e/sweep/results.json \
  --workers 4
```

Expected: all generated cases pass.

- [ ] **Step 3: Exercise artifact combinations not fully covered by the sweep**

Run tracked-fixture commands for:

- share `both` output with impact, preset comparison, debug,
  per-dimension weights, secondary metric, balanced CSV including calculations,
  JSON, and audit package;
- peer-only auto-dimension publication;
- rate approval and fraud with Control 3 privacy basis and fraud-in-bps;
- accuracy-first with explicit acknowledgement;
- lean share mode;
- strict non-publishable and invalid-input failure paths.

Inspect outputs with pandas, `zipfile`, and openpyxl. Assert expected files,
sheet names, JSON keys, audit-package members, balanced CSV columns, and exit
codes. Save command transcripts under `/tmp/autobench-e2e/transcripts`.

- [ ] **Step 4: Exercise telemetry end to end**

Run one share and one rate command with:

```bash
AUTOBENCH_TELEMETRY=1
AUTOBENCH_TELEMETRY_DIR=/tmp/autobench-e2e/telemetry
```

Then run `telemetry who` and `telemetry summary` against that directory. Confirm
session and completion counts appear, while raw records contain no CSV path,
entity name, metric name, or error detail.

### Task 9: Exercise the complete local TUI surface with terminal control

**Files:** Temporary harnesses and captures only under `/tmp/autobench-e2e`.

- [ ] **Step 1: Run the checked-in TUI suite**

Run:

```bash
python -m pytest \
  tests/test_tui_smoke.py \
  tests/test_tui_ux.py \
  tests/test_tui_contracts.py \
  tests/telemetry/test_tui_integration.py -q
```

Expected: PASS.

- [ ] **Step 2: Drive real terminal key flows**

Launch `python tui_app.py` in a dedicated tmux session using the required tmux
configuration. Capture the initial screen; send F1 and capture the preset guide;
Escape; Ctrl+A and capture the expanded advanced panel; Ctrl+O and capture the
CSV picker; Escape; Ctrl+L; then Ctrl+C. Confirm the process exits and clean up
the session.

- [ ] **Step 3: Drive Share and Rate through a temporary Textual pilot**

Create `/tmp/autobench-e2e/tui_e2e.py` based on
`tests/test_tui_smoke.py`. In separate app sessions:

- configure and run Share with `txn_cnt`, `card_type`, `channel`, impact,
  comparison, balanced CSV, and an advanced override;
- configure and run Rate on the `rate_tab` with `total`, `approved`,
  `card_type`, and `channel`;
- open/close file picker and preset help;
- apply and export advanced overrides in the temporary working directory;
- trigger and inspect a preflight validation refusal;
- save, restart, and verify session restoration.

Wait on concrete log messages rather than fixed sleeps. Assert both output
workbooks exist, both runs reach `success`, and no generated file is under the
repository.

### Task 10: Final review and handoff

**Files:** All changed files.

- [ ] **Step 1: Inspect the final diff**

Run:

```bash
git diff main...HEAD --stat
git diff main...HEAD
git diff --check
git status --short
```

Confirm no generated artifacts, reports, credentials, passcodes, telemetry, or
temporary harnesses are tracked.

- [ ] **Step 2: Request code review**

Review against the approved design, focusing on privacy behavior, output-schema
parity, unintended API removal, test quality, and whether each helper removes
more complexity than it adds. Fix only evidence-backed findings.

- [ ] **Step 3: Re-run verification after any review fix**

Run Ruff, mypy, full pytest, and the full CLI gate again after the final code
change. Commit each focused fix separately and push with:

```bash
git push -u origin cursor/deslop-e2e-c5b9
```

- [ ] **Step 4: Update the pull request**

Record exact test results, net production-line reduction, local CLI/TUI coverage,
and the explicit untested edge-only gaps: SSH/Kerberos, deployment, live
launchers, and shared `/ads_storage` acceptance.
