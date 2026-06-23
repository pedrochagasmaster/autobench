# Plan 011: Add DimensionalAnalyzer.from_resolved() and collapse the 30-kwarg construction site

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat e0950c4..HEAD -- core/dimensional_analyzer.py core/analysis_run.py utils/config_manager.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED
- **Depends on**: plans/002-config-precedence-tests.md, plans/003-analysis-run-integration-test.md
- **Category**: tech-debt
- **Planned at**: commit `e0950c4`, 2026-06-10

## Why this matters

Every configuration knob must today be threaded through three places by hand: `ResolvedConfig.from_merged_config` (typed view), `build_dimensional_analyzer` in `core/analysis_run.py:105-144` (~30 manual keyword mappings), and the `DimensionalAnalyzer.__init__` signature. Renames drift silently (the config layer already handles a `max_attempts` vs legacy `max_tests` alias that the analyzer boundary doesn't know about). Centralizing the mapping in a `DimensionalAnalyzer.from_resolved()` classmethod makes adding a knob a two-place change and makes the analyzer constructible from config in tests without 30 kwargs.

## Current state

- `core/analysis_run.py:105-144` — the mapping wall (excerpt):

```python
analyzer = DimensionalAnalyzer(
    target_entity=target_entity,
    entity_column=entity_col,
    bic_percentile=bic_percentile,
    debug_mode=debug_mode,
    consistent_weights=consistent_weights,
    merchant_mode=resolved.analysis.merchant_mode,
    rank_constraint_mode=resolved.linear_programming.rank_constraints.get('mode', 'all'),
    ...
    max_iterations=resolved.linear_programming.max_iterations,
    tolerance=resolved.linear_programming.tolerance,
    max_weight=resolved.bounds.max_weight,
    min_weight=resolved.bounds.min_weight,
    ...
    enforce_single_weight_set=enforce_single_weight_set,
)
```

  plus pre-computed locals above it (`rank_preservation_strength`, `lambda_penalty`, `dyn_constraints`, `bayesian_*` — read `core/analysis_run.py:60-104` for how they are derived from `resolved` and from `_resolve_consistency_mode`).
- `utils/config_manager.py:92-104` — `ResolvedConfig` typed view (`config.resolve()`).
- `core/dimensional_analyzer.py:55-98` — the 30+-parameter `__init__`. Do not change its signature in this plan (tests construct it directly).
- `build_dimensional_analyzer` returns `(analyzer, dict)` — the dict at `core/analysis_run.py:145-156` carries **ten** keys: `consistent_weights`, `consistency_mode`, `rank_penalty_weight`, `rank_preservation_strength`, `lambda_penalty`, `bayesian_max_iterations`, `bayesian_learning_rate`, `violation_penalty_weight`, `enforce_single_weight_set`, `dynamic_constraints_config`. This contract must be preserved exactly.
- The consistency-mode helper in `core/analysis_run.py` is named `resolve_consistency_mode` (no leading underscore — `benchmark.py`'s `_resolve_consistency_mode` is a wrapper).
- Callers of `build_dimensional_analyzer`: `core/analysis_run.py` itself, `benchmark.py` passthrough (removed by plan 009 if landed), `core/preset_comparison.py:43-48` (direct import), and `core/analysis_run.py:1469` (passes it as `analyzer_factory`). Find all with `rg -n "build_dimensional_analyzer" -t py`

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Full suite | `py -m pytest tests/ -q` | all pass |
| Integration | `py -m pytest tests/test_analysis_run_integration.py -q` (created by plan 003, a declared dependency — verify it exists before relying on it) | all pass |
| Gate | `py scripts/perform_gate_test.py` | exit 0 |
| Typecheck | `py -m mypy core/ utils/` | exit 0 |

## Scope

**In scope**:
- `core/dimensional_analyzer.py` (add classmethod only — no `__init__` change)
- `core/analysis_run.py` (`build_dimensional_analyzer` body shrinks to call the classmethod)
- New test file `tests/test_analyzer_from_resolved.py`

**Out of scope**:
- `DimensionalAnalyzer.__init__` signature — existing tests and preset comparison construct it directly.
- `utils/config_manager.py` / `ResolvedConfig` — no schema changes.
- The TUI request-assembly parity problem — that is plan 012.

## Git workflow

- Branch: `advisor/011-analyzer-from-resolved`
- Commit message style: `refactor: construct analyzer from ResolvedConfig`
- Do NOT push or open a PR unless instructed.

## Steps

### Step 1: Write the equivalence test first

Create `tests/test_analyzer_from_resolved.py`. Build a `ConfigManager(preset='balanced_default')`, `resolved = config.resolve()`, then construct an analyzer via the existing `build_dimensional_analyzer(...)` (import from `core.analysis_run`; read its exact signature first — it takes `target_entity`, `entity_col`, `resolved`, `time_col`, `debug_mode`, `bic_percentile`, `logger`, `consistent_weights`). Suggested fixture values: `target_entity="Target"`, `entity_col="issuer_name"`, `time_col=None`, `debug_mode=False`, `bic_percentile=0.85`, `logger=logging.getLogger("test")`, `consistent_weights=True`. Capture all of its constructor-relevant attributes into a dict:

```python
ATTRS = [
    "tolerance", "max_weight", "min_weight", "max_iterations",
    "prefer_slacks_first", "auto_subset_search", "subset_search_max_tests",
    "greedy_subset_search", "trigger_subset_on_slack", "max_cap_slack",
    "volume_weighted_penalties", "volume_weighting_exponent",
    "enforce_additional_constraints", "enforce_single_weight_set",
]
```

(Confirm each attribute name exists on the analyzer; extend the list after reading `__init__` to learn the stored names — expect to add at least `merchant_mode`, `rank_constraint_mode`, `rank_constraint_k`, `time_column`, the `bayesian_*` attributes, and the dynamic-constraint attributes. Watch one rename: the constructor kwarg `volume_preservation_strength` is stored under a different attribute name — read `__init__` to find it.) Assert this snapshot for two presets (`balanced_default`, `compliance_strict`) — this is the frozen contract the refactor must preserve.

**Verify**: `py -m pytest tests/test_analyzer_from_resolved.py -q` → passes against the *current* implementation.

### Step 2: Add `DimensionalAnalyzer.from_resolved`

In `core/dimensional_analyzer.py`:

```python
@classmethod
def from_resolved(
    cls,
    resolved: "ResolvedConfig",
    *,
    target_entity: Optional[str],
    entity_column: str,
    time_column: Optional[str],
    debug_mode: bool,
    bic_percentile: float,
    consistent_weights: bool,
    rank_preservation_strength: float,
    lambda_penalty: float,
) -> "DimensionalAnalyzer":
    """Build an analyzer from the typed resolved configuration."""
    ...
```

Move the entire kwarg mapping from `core/analysis_run.py:105-144` into this classmethod verbatim. Parameters that `build_dimensional_analyzer` derives *outside* `resolved` (consistency mode, rank-preservation strength, lambda penalty — check lines 60-104) stay as explicit keyword parameters as shown. Import `ResolvedConfig` under `TYPE_CHECKING` to avoid a runtime `core → utils` import if one doesn't already exist (check current imports — `core/analysis_run.py` already imports from `utils.config_manager`, but keep `dimensional_analyzer.py`'s runtime imports minimal).

**Verify**: `py -m mypy core/ utils/` → exit 0.

### Step 3: Shrink `build_dimensional_analyzer`

Replace its construction block with a call to `DimensionalAnalyzer.from_resolved(...)`, keeping the derivation of `consistent_weights`/`consistency_mode`/`rank_*`/`lambda_penalty` and the returned metadata dict exactly as before.

**Verify**: `py -m pytest tests/test_analyzer_from_resolved.py -q` → the Step 1 snapshot still passes (proving equivalence); `py -m pytest tests/ -q` → all pass.

### Step 4: Full verification

**Verify**: `py scripts/perform_gate_test.py` → exit 0; `py -m mypy core/ utils/` → exit 0.

## Test plan

- Step 1's attribute-snapshot equivalence test (two presets) is the core regression guard.
- Add one negative-drift test: constructing via `from_resolved` with `compliance_strict` yields `tolerance == 0.0` and `auto_subset_search` matching the preset's `subset_search.enabled`.

## Done criteria

- [ ] `build_dimensional_analyzer` in `core/analysis_run.py` no longer contains a 30-kwarg `DimensionalAnalyzer(...)` literal (the mapping lives in `from_resolved`)
- [ ] Attribute snapshot test passes before AND after the refactor (same values)
- [ ] `py -m pytest tests/ -q`, `py scripts/perform_gate_test.py`, `py -m mypy core/ utils/` all exit 0
- [ ] `git status` shows only in-scope files
- [ ] `plans/README.md` status row updated

## STOP conditions

- The analyzer stores constructor params under different attribute names than the kwargs (making the Step 1 snapshot impossible to build reliably) — list the mismatches and report before guessing.
- Moving the mapping reveals a hidden dependency on `core/analysis_run`-module state (e.g. a helper only available there) — report rather than duplicating logic.
- Any gate case output changes — equivalence was violated; bisect by diffing the snapshot attributes.

## Maintenance notes

- New config knobs should now be added in exactly two places: `ResolvedConfig.from_merged_config` and `from_resolved`. Reviewers should reject PRs that re-introduce direct kwarg threading in `analysis_run`.
- Follow-up (not this plan): deprecate direct 30-kwarg construction in tests in favor of `from_resolved`, then consider slimming `__init__` at the v4.0 boundary.
