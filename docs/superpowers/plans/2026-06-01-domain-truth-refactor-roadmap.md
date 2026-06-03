# Domain Truth Refactor Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move business truth out of incidental structures such as report dataframes, metadata dictionaries, CLI arguments, and mutable analyzer attributes into explicit typed domain modules.

**Architecture:** The codebase already has useful seams in `core/contracts.py`, `core/analysis_run.py`, solver modules, and report/output modules. This roadmap deepens those seams so privacy compliance, weighting, data quality, configuration, and reporting each have one canonical domain representation and one rendering path.

**Tech Stack:** Python 3.8+, dataclasses, pandas, scipy, openpyxl, pytest, existing CLI/TUI adapters, existing gate runner.

---

## Scope And Non-Negotiables

This plan covers all nine architecture opportunities discussed after the strict Control 3.2 incident:

1. Compliance and privacy rule engine.
2. Weighted solution result.
3. Run orchestration contract.
4. Configuration resolution.
5. Privacy validation output.
6. Report generation model.
7. Input validation and data quality.
8. Analyzer facade size.
9. TUI advanced configuration.

Every phase must preserve:

- Mastercard Control 3.2 primary caps and secondary/additional participant rules.
- Strict default behavior: no dynamic relaxation unless config explicitly opts in.
- CLI and TUI user-facing flags.
- Preset names and existing YAML compatibility.
- Existing workbook sheet names and CSV export schemas unless a phase explicitly adds fields.
- Gate test behavior: `py scripts/perform_gate_test.py` must pass after each phase.
- Unit tests: `py -m pytest` must pass after each phase.

This is a roadmap, not one giant PR. Each phase should be implemented as a separate branch/PR.

---

## Mapping From The "Hack Fix" Critique

This roadmap explicitly includes the five opportunities identified when the strict final validator was called a defensive hack:

| Original opportunity | Where this roadmap implements it |
|----------------------|-----------------------------------|
| `PrivacyRuleEvaluator`: one canonical owner for Control 3.2 logic | Phase 1: `core/privacy_rules.py`, `PrivacyRule`, `PrivacyRuleEvaluation`, `evaluate_rule()` |
| `PrivacyValidationResult`: typed validation result instead of dataframe-as-truth | Phase 5: `core/privacy_validation.py`, `PrivacyValidationRow`, `PrivacyValidationResult` |
| Single source of truth in the optimizer | Phase 2: `WeightingComplianceState` on `WeightingResult`; `core/global_weight_optimizer.py` records final compliance state |
| Explicit compliance modes | Phase 1 adds `RuleMode`; Phase 3/7 use it during result finalization so relaxed/adaptive outputs cannot become `fully_compliant` |
| Finalization gate before output | Phase 3: `finalize_analysis_result()` runs before report generation; Phase 6 makes reports render typed compliance results only |

The current `core/compliance.py` strict dataframe recheck should be treated as a temporary safety net. Its final home is behind the Phase 1 and Phase 5 typed domain seams.

---

## Baseline Before Starting

- [ ] Run the current full verification suite.

```powershell
py scripts/perform_gate_test.py
py -m pytest
```

Expected current result after the strict-default work:

```text
Gate: 18 passed, 0 failed, 0 errors
Pytest: 119 passed, 2 warnings
```

- [ ] Record `git status --short`.

Expected:

```text
Only the active branch changes should be present.
```

---

## Phase 1: Compliance And Privacy Rule Engine

**Opportunity:** Create one authoritative module for Control 3.2 rule evaluation.

**Current Problem:**

Compliance truth is distributed across:

- `core/privacy_validator.py`: rule config, concentration checks, secondary/additional rule checks.
- `core/privacy_policy.py`: dynamic constraint applicability and relaxation.
- `core/solvers/heuristic_solver.py`: secondary-rule penalties and dynamic thresholds.
- `core/compliance.py`: final compliance summary and the current strict final dataframe validator.
- `core/privacy_validation_builder.py`: dataframe row labels such as `Additional_Constraints_Passed`.

This is why the original case could show `Compliant = Yes` while using relaxed secondary rules. Multiple modules had partial rule knowledge.

**Target Module:**

Create `core/privacy_rules.py`.

**Target Types:**

```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class PrivacyRule:
    name: str
    min_entities: int
    max_concentration: float
    secondary_requirements: Dict[str, tuple[int, float]] = field(default_factory=dict)


@dataclass(frozen=True)
class PrivacyRuleEvaluation:
    rule_name: str
    primary_cap_passed: bool
    secondary_rule_passed: bool
    relaxation_used: bool
    primary_cap_failures: int
    secondary_failures: List[str]
    max_share: float
    participant_count: int

    @property
    def strict_passed(self) -> bool:
        return (
            self.primary_cap_passed
            and self.secondary_rule_passed
            and not self.relaxation_used
        )


class RuleMode(str, Enum):
    STRICT = "strict"
    ADAPTIVE = "adaptive"
    BEST_EFFORT = "best_effort"
    ACCURACY_FIRST = "accuracy_first"
```

**Implementation Steps:**

- [ ] Write tests in `tests/test_privacy_rules_engine.py` for canonical `5/25`, `6/30`, `7/35`, `10/40`, and `4/35`.

```python
from core.privacy_rules import evaluate_rule


def test_10_40_requires_primary_cap_and_secondary_counts() -> None:
    result = evaluate_rule("10/40", [40.0, 20.0, 10.0, 5.0])

    assert result.primary_cap_passed is True
    assert result.secondary_rule_passed is True
    assert result.strict_passed is True


def test_10_40_fails_when_second_twenty_percent_participant_is_missing() -> None:
    result = evaluate_rule("10/40", [40.0, 19.0, 11.0, 10.0])

    assert result.primary_cap_passed is True
    assert result.secondary_rule_passed is False
    assert result.strict_passed is False
```

- [ ] Run the new tests and verify they fail because `core/privacy_rules.py` does not exist.

```powershell
py -m pytest tests/test_privacy_rules_engine.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'core.privacy_rules'
```

- [ ] Create `core/privacy_rules.py` with canonical rule definitions loaded from `PrivacyValidator.get_rule_config()` initially. Do not duplicate YAML parsing in this phase.

- [ ] Move only rule evaluation logic first. Keep `PrivacyValidator` as a backward-compatible adapter that calls `core.privacy_rules`.

- [ ] Add `RuleMode` handling to `core/privacy_rules.py`. In `RuleMode.STRICT`, dynamic thresholds and relaxed secondary constraints must be impossible. In `RuleMode.ADAPTIVE`, relaxation may be used but the resulting evaluation must set `relaxation_used=True` and must not qualify for `strict_passed`.

- [ ] Update `core/compliance.py` to call `evaluate_rule()` instead of carrying private `_evaluate_strict_secondary_rule()` helpers.

- [ ] Update `tests/test_compliance_summary.py` assertions to check the new `PrivacyRuleEvaluation` details are threaded into `strict_final_validation`.

- [ ] Run:

```powershell
py -m pytest tests/test_privacy_rules_engine.py tests/test_compliance_summary.py tests/test_privacy_rules_config.py -q
py scripts/perform_gate_test.py
```

**Acceptance Criteria:**

- Canonical rule behavior lives in `core/privacy_rules.py`.
- `core/compliance.py`, `core/privacy_validator.py`, and later modules call the same evaluator.
- No module other than `core/privacy_rules.py` manually encodes `10/40` as `2 >= 20%` and `3 >= 10%`.

---

## Phase 2: Typed Weighted Solution Result

**Opportunity:** Make optimization output a first-class domain object.

**Current Problem:**

Solver output is split across:

- `SolverResult` in `core/solvers/base_solver.py`.
- `WeightingResult` in `core/contracts.py`.
- Mutable fields on `DimensionalAnalyzer`: `global_weights`, `per_dimension_weights`, `weight_methods`, `last_lp_stats`, `additional_constraint_violations`, `rank_changes_df`.
- Metadata in `core/analysis_run.py`.

Callers need to know too much about implementation details to answer simple questions:

- Did LP solve with slack?
- Did heuristic converge?
- Were secondary rules fixed after fallback?
- Which dimensions were dropped?
- Is the solution strict-compliant or only best-effort?

**Target Type:**

Deepen the existing `WeightingResult` in `core/contracts.py` instead of creating a parallel type.

Add:

```python
@dataclass
class WeightingComplianceState:
    rule_name: Optional[str] = None
    primary_cap_passed: bool = False
    secondary_rule_passed: bool = False
    relaxation_used: bool = False
    heuristic_converged: Optional[bool] = None
    residual_violations: int = 0
    verdict: str = "unknown"


@dataclass
class WeightingResult:
    ...
    compliance_state: WeightingComplianceState = field(default_factory=WeightingComplianceState)
```

**Implementation Steps:**

- [ ] Write failing tests in `tests/test_global_weight_optimizer_fallbacks.py` proving a heuristic non-convergence flag is retained in `WeightingResult`.

```python
def test_weighting_result_records_heuristic_convergence_state() -> None:
    # Use the existing fallback fixture style in this file.
    # Assert result.compliance_state.heuristic_converged is False when solver stats say not converged.
```

- [ ] Update `core/solvers/base_solver.py` so `SolverResult.stats` can expose `converged`, `residual_cap_violation`, and `residual_additional_violation` with documented keys.

- [ ] Update `core/solvers/lp_solver.py` and `core/solvers/heuristic_solver.py` to set those keys consistently.

- [ ] Update `core/global_weight_optimizer.py` so it builds `WeightingComplianceState` after every optimizer path:

```python
result.compliance_state = WeightingComplianceState(
    rule_name=problem.rule_name,
    primary_cap_passed=...,
    secondary_rule_passed=...,
    relaxation_used=analyzer.dynamic_constraints_enabled,
    heuristic_converged=...,
    residual_violations=len(analyzer.additional_constraint_violations),
    verdict="strict_compliant" or "non_compliant" or "best_effort",
)
```

- [ ] Update `core/contracts.py::apply_weighting_result_to_analyzer()` only for backwards compatibility. New callers should consume the typed result.

**Acceptance Criteria:**

- `analysis_run.py` can derive compliance metadata from `weighting_result.compliance_state`, not by probing analyzer fields.
- Heuristic non-convergence is never lost in logs only.
- Existing analyzer attributes still work until later phases remove them.

---

## Phase 3: Run Orchestration Contract

**Opportunity:** Make the analysis lifecycle typed from request to output.

**Current Problem:**

`core/analysis_run.py` is a large procedural module that builds config, loads data, validates input, resolves dimensions, fits weights, calculates results, collects diagnostics, builds metadata, writes reports, writes audit logs, and returns artifacts.

Existing contracts are useful but incomplete:

- `AnalysisRunRequest`
- `PreparedDataset`
- `OutputSettings`
- `RunSummary`
- `AnalysisArtifacts`

The problematic seam is the metadata dictionary. Many modules depend on implicit keys.

**Target Types:**

Add or deepen these in `core/contracts.py`:

```python
@dataclass
class AnalysisPlan:
    request: AnalysisRunRequest
    resolved_config: Any
    entity: Optional[str]
    entity_column: str
    dimensions: List[str]
    metric_columns: Dict[str, str]
    output_settings: OutputSettings


@dataclass
class AnalysisResult:
    plan: AnalysisPlan
    weighting: WeightingResult
    privacy_validation: Any
    data_quality: Any
    results: Any
    compliance_summary: Dict[str, Any]
```

**Implementation Steps:**

- [ ] Write tests in `tests/test_benchmark_orchestration_helpers.py` for a pure `build_analysis_plan()` helper.

```python
def test_build_analysis_plan_contains_resolved_dimensions_and_output_settings() -> None:
    request = AnalysisRunRequest(
        mode="share",
        csv="tests/fixtures/gate_demo.csv",
        entity="Target",
        metric="txn_cnt",
        dimensions=["card_type"],
    )

    plan = build_analysis_plan(request, ConfigManager())

    assert plan.dimensions == ["card_type"]
    assert plan.output_settings.output_format == "analysis"
```

- [ ] Extract plan construction from `_execute_run()` in `core/analysis_run.py` into `build_analysis_plan()`.

- [ ] Extract result finalization from `_execute_run()` into `finalize_analysis_result()`.

- [ ] Keep `execute_share_run()` and `execute_rate_run()` return type as `AnalysisArtifacts` for compatibility until reports are refactored.

- [ ] Make CLI (`benchmark.py`) and TUI (`tui_app.py`) continue constructing `AnalysisRunRequest`.

**Acceptance Criteria:**

- `_execute_run()` becomes a readable orchestration pipeline with explicit typed objects.
- Metadata dictionary population is isolated to one adapter function: `analysis_result_to_metadata()`.
- No CLI/TUI-specific logic is inside compliance or optimizer modules.

---

## Phase 4: Configuration Resolution

**Opportunity:** Stop passing raw config dictionaries into core logic.

**Current Problem:**

`ConfigManager` has a typed `ResolvedConfig`, but raw `config.get(...)` calls still exist in orchestration, validation, report settings, and TUI override paths. Defaults and aliases can diverge.

**Target Rule:**

Core modules accept `ResolvedConfig`, not `ConfigManager`, raw YAML, or nested dictionaries.

**Implementation Steps:**

- [ ] Add a test that forbids raw `config.get("optimization"...` in `core/` except inside config adapter modules.

```python
from pathlib import Path


def test_core_analysis_does_not_read_raw_config_values() -> None:
    offenders = []
    for path in Path("core").glob("*.py"):
        if path.name in {"analysis_run.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        if ".get('optimization'" in text or '.get("optimization"' in text:
            offenders.append(str(path))
    assert offenders == []
```

- [ ] Move config-derived output settings into a function that accepts `ResolvedConfig`:

```python
def resolve_output_settings_from_config(resolved: ResolvedConfig, args: AnalysisRunRequest) -> OutputSettings:
    ...
```

- [ ] Update `core/validation_runner.py` to accept a typed validation settings object rather than `ConfigManager`.

- [ ] Preserve raw `ConfigManager` only at adapter edges:

  - CLI config command handling.
  - TUI advanced-override loading.
  - YAML preset management.

**Acceptance Criteria:**

- All analysis logic uses `ResolvedConfig`.
- Alias handling such as `max_tests -> max_attempts` remains only in `ConfigManager`.
- Defaults are discoverable in dataclass definitions and template YAML.

---

## Phase 5: Privacy Validation Output

**Opportunity:** Make privacy validation a domain result first, dataframe second.

**Current Problem:**

`core/privacy_validation_builder.py` creates a dataframe that both machines and humans consume. This makes strings like `"Yes"`, `"No"`, and `"Thresholds={...}"` part of the business seam.

**Target Types:**

Create `core/privacy_validation.py`.

```python
@dataclass(frozen=True)
class PrivacyValidationRow:
    dimension: str
    category: str
    time_period: Optional[str]
    peer: str
    rule_name: str
    original_volume: float
    original_share_pct: float
    balanced_volume: float
    balanced_share_pct: float
    primary_cap_pct: float
    primary_cap_passed: bool
    secondary_rule_passed: bool
    relaxation_used: bool
    strict_compliant: bool


@dataclass(frozen=True)
class PrivacyValidationResult:
    rows: List[PrivacyValidationRow]

    def strict_failures(self) -> List[PrivacyValidationRow]:
        return [row for row in self.rows if not row.strict_compliant]

    def to_dataframe(self) -> pd.DataFrame:
        ...
```

**Implementation Steps:**

- [ ] Write tests in `tests/test_privacy_validation_result.py`.

```python
def test_privacy_validation_result_renders_legacy_dataframe_columns() -> None:
    result = PrivacyValidationResult([...])

    df = result.to_dataframe()

    assert "Compliant" in df.columns
    assert "Additional_Constraints_Relaxed" in df.columns
```

- [ ] Make `build_privacy_validation_dataframe()` call a new `build_privacy_validation_result()` internally.

- [ ] Update `core/compliance.py` to accept either `PrivacyValidationResult` or the legacy dataframe during migration.

- [ ] Update report generation to render from `PrivacyValidationResult.to_dataframe()`.

**Acceptance Criteria:**

- Compliance logic consumes structured booleans.
- Excel/report code consumes rendered dataframe columns.
- No new code branches inspect `Compliant == "Yes"` directly.

---

## Phase 6: Report Generation Model

**Opportunity:** Make reports pure rendering adapters.

**Current Problem:**

`core/report_generator.py` reads arbitrary metadata keys and optional dataframes. The report layer can silently omit important facts or render stale semantics.

**Target Types:**

Create `core/report_models.py`.

```python
@dataclass(frozen=True)
class ReportModel:
    summary: RunSummary
    compliance_summary: Dict[str, Any]
    results: Any
    privacy_validation_df: Optional[pd.DataFrame]
    weights_df: Optional[pd.DataFrame]
    method_breakdown_df: Optional[pd.DataFrame]
    impact_df: Optional[pd.DataFrame]
    data_quality_df: Optional[pd.DataFrame]
```

**Implementation Steps:**

- [ ] Write tests for `ReportModel.from_analysis_result()`.

```python
def test_report_model_requires_compliance_summary() -> None:
    with pytest.raises(ValueError, match="compliance_summary"):
        ReportModel.from_analysis_result(result_without_compliance)
```

- [ ] Add `ReportModel.from_artifacts()` for compatibility with current `AnalysisArtifacts`.

- [ ] Update `core/report_generator.py` internal methods to use `ReportModel` instead of raw metadata dicts.

- [ ] Keep public `generate_report(results, output_file, analysis_type, metadata)` signature until CLI/TUI migration is complete.

- [ ] Add Summary fields:

```text
Primary cap: pass/fail
Secondary/additional rule: pass/fail
Relaxation used: yes/no
Strict final validation: pass/fail
Input validation: pass/warn/error/disabled
```

**Acceptance Criteria:**

- Missing compliance data is a construction error for analysis/publication reports.
- Reports do not compute compliance.
- Reports only render compliance facts from the domain result.

---

## Phase 7: Input Validation And Data Quality

**Opportunity:** Treat data quality as a first-class part of compliance posture.

**Current Problem:**

The case input had approval rates above 100%. `--no-validate-input` can bypass validation, but final compliance wording can still look clean unless the operator reads audit details.

**Target Types:**

Add to `core/contracts.py` or new `core/data_quality.py`:

```python
@dataclass(frozen=True)
class DataQualityResult:
    checked: bool
    errors: int
    warnings: int
    infos: int
    issues: List[Any]

    @property
    def publishable(self) -> bool:
        return self.checked and self.errors == 0
```

**Implementation Steps:**

- [ ] Write tests in `tests/test_validation_runner.py`.

```python
def test_disabled_input_validation_marks_data_quality_unchecked() -> None:
    result = run_input_validation(..., validate_input=False)

    assert result.checked is False
    assert result.publishable is False
```

- [ ] Update `core/validation_runner.py` to return `DataQualityResult`, not only a list of issues.

- [ ] Update compliance finalization:

```python
if posture == "strict" and not data_quality.publishable:
    verdict = "not_publishable_input"
```

- [ ] Add explicit audit fields:

```text
data_quality_checked: true/false
data_quality_publishable: true/false
validation_errors: N
validation_warnings: N
```

**Acceptance Criteria:**

- Strict compliance requires checked and publishable data.
- `--no-validate-input` can still run analysis, but output verdict cannot be `fully_compliant`.
- Publication outputs warn or block when data quality is unchecked.

### Case-02 Follow-Up: Minimum Publishable Cell Volume

**Opportunity:** Distinguish Control 3.2 concentration compliance from minimum
publishable cell-volume rules.

**Trigger Case:**

`cases/02/autobench.csv` and `cases/02/peer_benchmark.csv` contain five
published rows where the balanced secondary metric `cnt_total` is below 10,000:

```text
fl_domestic_poi_pan / Cross-border - CP - CREDENTIAL ON FILE: 74.40
fl_domestic_poi_pan / Cross-border - CP - ELECTRONIC COMMERCE: 1.04
fl_domestic_poi_pan / Cross-border - CP - MAGNETIC STRIPE: 493.08
fl_domestic_poi_pan / Domestic - CP - CREDENTIAL ON FILE: 249.35
fl_domestic_poi_pan / Domestic - CP - MAGNETIC STRIPE: 1,867.53
```

The current validator only has `input.validation_thresholds.min_denominator=100`
for rate stability on the primary denominator column, and current Control 3.2
validation checks peer-count, concentration caps, and additional participant
share requirements. It does not define or enforce a 10,000-count minimum for
published output cells.

**Why It Matters:**

If the business privacy policy says no published benchmark cell may expose a
peer aggregate with fewer than 10,000 transactions, then a workbook can be
Control 3.2-compliant and still fail publication safety. This is a separate
publication-suppression rule, not a secondary-metric compliance surface.

**Implementation Steps:**

- [ ] Confirm whether the 10,000 minimum is an official publication/privacy
      threshold, which metric(s) it applies to (`cnt_total` only, all count
      metrics, denominator metrics, or all cells), and whether it should be
      evaluated before or after privacy weighting.
- [ ] Add a typed `PublicationSafetyResult` or extend `DataQualityResult` with
      output-cell checks that can be rendered in Summary, Data Quality, audit
      logs, and gate assertions.
- [ ] Add configuration for the policy, for example
      `output.publication_min_count_threshold: 10000` and
      `output.publication_min_count_metrics: ["cnt_total"]`, while keeping
      Control 3.2 rule semantics unchanged.
- [ ] Add a case-02-class fixture where strict Control 3.2 can pass but one
      published count cell is below the publication threshold; assert the final
      verdict is not `fully_compliant` for publication mode.
- [ ] Decide rendering behavior: either suppress unsafe cells, roll them into an
      `Other/Insufficient volume` bucket, or keep values visible but mark the
      output `not_publishable_low_volume`.

**Acceptance Criteria:**

- Logs and workbook identify the exact dimension/category cells below the
  configured minimum, not just a row count.
- Control 3.2 verdicts remain based on the existing privacy rules.
- Publication safety is reported as a separate, explicit condition in Summary,
  Data Quality, and audit artifacts.
- `cases/02` is covered by a smoke/regression check so this class of issue is
  not silently labeled publishable.

---

## Phase 8: Analyzer Facade Size

**Opportunity:** Turn `DimensionalAnalyzer` into a thin facade over deep modules.

**Current Problem:**

`core/dimensional_analyzer.py` owns too many responsibilities:

- Analysis calculations.
- Weighting orchestration.
- Dynamic constraint policy.
- Diagnostics.
- Legacy wrappers.
- Privacy validation construction.
- Mutable state used by downstream modules.

**Target Shape:**

Keep `DimensionalAnalyzer` as a compatibility facade for public callers, but move behavior into existing or new modules:

- `core/category_builder.py`: category construction.
- `core/global_weight_optimizer.py`: weighting.
- `core/analysis_calculator.py`: share/rate calculations.
- `core/privacy_validation.py`: privacy validation result construction.
- `core/diagnostics_engine.py`: diagnostics.
- `core/compliance.py`: final verdict.

**Implementation Steps:**

- [ ] Add characterization tests around `DimensionalAnalyzer` public methods before extraction:

```powershell
py -m pytest tests/test_cli_runtime_behavior.py tests/test_legacy_wrappers.py -q
```

- [ ] Move dynamic additional-constraint helpers from `DimensionalAnalyzer` into the Phase 1 privacy rule/policy modules.

- [ ] Move `build_privacy_validation_dataframe()` implementation behind `core/privacy_validation.py`, leaving a facade method:

```python
def build_privacy_validation_dataframe(...):
    return build_privacy_validation_result(...).to_dataframe()
```

- [ ] Move legacy wrapper warnings to a small `core/legacy_api.py` only if `dimensional_analyzer.py` remains too large after behavior extraction.

**Acceptance Criteria:**

- `DimensionalAnalyzer` delegates, but does not own compliance truth.
- New behavior is added to focused modules, not to the facade.
- Legacy tests remain green.

---

## Phase 9: TUI Advanced Configuration

**Opportunity:** Make TUI config editing an adapter over typed config fields.

**Current Problem:**

`tui_app.py` contains `ADVANCED_FIELD_MAP`, nested get/set helpers, temp YAML generation, preset loading, and validation assumptions. Config semantics leak into UI code.

**Target Module:**

Create `core/config_overrides.py` or `utils/config_overrides.py`.

**Target Types:**

```python
@dataclass(frozen=True)
class ConfigFieldSpec:
    widget_id: str
    path: tuple[str, ...]
    kind: str
    default: Any
    always_write: bool = False


class ConfigOverrideBuilder:
    def read_from_mapping(self, values: Dict[str, Any]) -> Dict[str, Any]:
        ...

    def write_yaml(self, values: Dict[str, Any], path: Path) -> None:
        ...
```

**Implementation Steps:**

- [ ] Move `ADVANCED_FIELD_MAP` out of `tui_app.py` into `utils/config_overrides.py`.

- [ ] Write tests in `tests/test_tui_contracts.py` proving the moved specs still contain required widget IDs.

- [ ] Replace `_nested_get`, `_nested_set`, `_collect_advanced_override_data`, and temp YAML generation in `tui_app.py` with `ConfigOverrideBuilder`.

- [ ] Preserve all existing widget IDs.

**Acceptance Criteria:**

- TUI code does not know nested YAML paths directly.
- Config override behavior is testable without launching Textual.
- Advanced UI changes cannot silently miss config semantics.

---

## Phase 10: Report And Output Artifact Boundary

**Opportunity:** Make output artifacts consume typed models and keep generated files out of business logic.

**Current Problem:**

`core/output_artifacts.py`, `core/report_generator.py`, and `core/excel_reports.py` share responsibilities for workbook generation, publication output, audit log creation, optional sheets, and metadata propagation.

**Target Shape:**

- `OutputArtifactWriter`: decides which artifacts to write.
- `ReportGenerator`: renders one `ReportModel`.
- `AuditLogWriter`: renders audit summary from typed result.
- `BalancedCsvExporter`: remains focused on CSV export.

**Implementation Steps:**

- [ ] Add `core/audit_log.py` with:

```python
def build_audit_log_model(result: AnalysisResult) -> Dict[str, Any]:
    ...
```

- [ ] Move audit metadata compaction out of `core/analysis_run.py::write_audit_log()`.

- [ ] Update tests in `tests/test_output_artifacts.py` to assert the writer receives a `ReportModel`.

- [ ] Keep generated file names and paths stable.

**Acceptance Criteria:**

- `analysis_run.py` no longer contains report/audit formatting logic.
- Artifact writers are adapters, not domain owners.

---

## Phase 11: End-To-End Migration And Deletion

**Opportunity:** Remove compatibility paths after all deep seams exist.

**Current Problem:**

During phases 1-10, backward-compatible adapters will coexist with new typed modules. If not cleaned up, the codebase will have both old and new complexity.

**Implementation Steps:**

- [ ] Search for string-based compliance checks.

```powershell
rg -n "Compliant|Additional_Constraints_Relaxed|Rule_Name|Balanced_Share_%" core tests
```

Allowed after migration:

- Renderers.
- Legacy dataframe compatibility tests.
- CSV/Excel validator tests.

- [ ] Search for analyzer mutable-state reads outside compatibility adapters.

```powershell
rg -n "global_weights|per_dimension_weights|last_lp_stats|additional_constraint_violations" core tests
```

Allowed after migration:

- `core/contracts.py`
- `core/dimensional_analyzer.py` facade
- tests that explicitly cover legacy compatibility

- [ ] Search for raw metadata key dependencies.

```powershell
rg -n "metadata\\.get|metadata\\[" core benchmark.py tui_app.py
```

Allowed after migration:

- report rendering adapters.
- audit rendering adapters.
- CLI/TUI display adapters.

- [ ] Remove dead compatibility paths one at a time with tests.

**Acceptance Criteria:**

- Business truth lives in typed domain modules.
- Dataframes are renderings.
- Metadata dicts are adapter payloads.
- CLI and TUI are adapters.
- `DimensionalAnalyzer` is a compatibility facade, not the owner of all behavior.

---

## Suggested Execution Order

| Order | Phase | Reason |
|-------|-------|--------|
| 1 | Compliance and privacy rule engine | Highest compliance risk and root cause of the original issue. |
| 2 | Privacy validation output | Makes compliance results structured before bigger orchestration changes. |
| 3 | Typed weighted solution result | Captures solver truth before metadata refactors. |
| 4 | Input validation and data quality | Prevents invalid input from being labeled publishable. |
| 5 | Run orchestration contract | Creates typed lifecycle after core domain truth exists. |
| 6 | Configuration resolution | Removes raw config leakage once lifecycle is typed. |
| 7 | Report generation model | Makes reports pure rendering adapters. |
| 8 | Output artifact boundary | Separates audit/report writing from orchestration. |
| 9 | Analyzer facade size | Safest after behavior has moved behind typed seams. |
| 10 | TUI advanced configuration | UI adapter cleanup after config semantics stabilize. |
| 11 | End-to-end migration and deletion | Removes compatibility debt. |

---

## Verification Required After Every Phase

Run:

```powershell
py scripts/perform_gate_test.py
py -m pytest
```

When touching compliance, privacy rules, solver behavior, or output artifacts, also run:

```powershell
py benchmark.py rate --csv tests/fixtures/gate_demo.csv --entity Target --entity-col issuer_name --total-col total --approved-col approved --fraud-col fraud --dimensions card_type channel --debug --output outputs/refactor_smoke_rate.xlsx
py benchmark.py share --csv tests/fixtures/gate_demo.csv --entity Target --entity-col issuer_name --metric txn_cnt --dimensions card_type channel --debug --output outputs/refactor_smoke_share.xlsx
```

Expected:

- CLI exits `0`.
- Audit log contains `compliance_verdict: fully_compliant` for valid fixture runs.
- Privacy Validation sheet has no `Compliant = No` rows.

---

## Stop Conditions

Stop and ask for direction if any phase would require:

- Changing Control 3.2 rule semantics.
- Renaming public workbook sheets.
- Removing a public CLI flag.
- Editing shipped presets in a way that changes their advertised intent.
- Accepting non-compliant output as strict-compliant.
- Skipping gate tests because they are slow.
