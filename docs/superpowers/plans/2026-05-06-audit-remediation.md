# Audit Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the highest-risk audit findings in the privacy-compliant peer benchmark tool so CLI, TUI, reports, presets, gates, and compliance diagnostics behave consistently and are covered by fresh tests.

**Architecture:** Keep the current CLI/TUI/core split, but make `core.analysis_run` and `core.contracts` the single orchestration contract for preloaded data, merged config, output paths, and compliance summaries. Strengthen output generation and verification without rewriting the optimizer wholesale; hard privacy-policy changes get explicit tests first because they affect legal compliance semantics.

**Tech Stack:** Python 3.12 via `py`, pandas, scipy linprog, openpyxl, PyYAML, pytest, ruff, Textual TUI.

---

## Scope and Priorities

This plan is organized by risk and dependency order:

1. Stabilize orchestration contracts and test fixtures.
2. Fix output/report generation and preset comparison false confidence.
3. Tighten compliance summaries and optimizer policy behavior.
4. Repair config, preset, validation, gate, and CSV-validator drift.
5. Refresh docs and run repository verification.

Do not modify `presets/*.yaml` casually. Preset changes in this plan are explicitly called out because two shipped presets are invalid against the repository validator and the audit found runtime ambiguity.

---

## File Structure

**Create**
- `tests/test_output_artifacts.py` - focused tests for analysis/publication report paths and workbook sheets.
- `tests/test_preset_validation.py` - validates every preset and asserts intended legacy-key handling.
- `tests/test_compliance_summary.py` - compliance summary casing and violation-count tests.
- `tests/test_gate_runner.py` - tests command parsing and expectation enforcement in gate tooling.
- `tests/test_tui_contracts.py` - non-GUI tests for TUI request/preloaded-DataFrame contract.

**Modify**
- `core/contracts.py` - add `df` to `AnalysisRunRequest` and preserve it through namespace conversion.
- `core/analysis_run.py` - use merged config consistently, build both output paths, pass merged config to report helpers, and normalize preloaded data safely.
- `core/output_artifacts.py` - write analysis and publication workbooks according to `output_format`.
- `core/excel_reports.py` - pass structured diagnostic frames to `ReportGenerator` as real sheets.
- `core/report_generator.py` - emit diagnostic sheets and publication workbook formatting deterministically.
- `core/preset_comparison.py` - compute real impact/distortion metrics for each preset and per-dimension variant.
- `core/compliance.py` - count violations from both `Compliant` and `compliant` forms.
- `core/global_weight_optimizer.py` - hard-block insufficient peers or mark identity fallback as non-compliant according to posture.
- `core/privacy_validator.py` - clarify and test merchant rule selection.
- `core/data_loader.py` - validate SQL table names and rate values above 100%.
- `utils/config_manager.py` - remove duplicate aliases and validate JSON configs.
- `utils/preset_manager.py` - validate presets at load time or expose invalid-preset status.
- `utils/csv_validator.py` - align sheet matching with generated workbook names and fail loudly on skipped dimensions.
- `scripts/perform_gate_test.py` - parse commands with `shlex.split`, avoid destructive cleanup before successful case generation, enforce fraud expectations.
- `scripts/generate_cli_sweep.py` - generate portable paths and stronger rate-column choices.
- `tui_app.py` - keep preloaded validation data in the confirmed run and harden mode/entity handling.
- `README.md`, `SETUP.md`, `run_tool.sh`, `AGENTS.md` - correct user-facing drift found by the audit.

---

## Task 1: Lock the Current Failures as Regression Tests

**Files:**
- Create: `tests/test_tui_contracts.py`
- Create: `tests/test_output_artifacts.py`
- Create: `tests/test_compliance_summary.py`
- Create: `tests/test_gate_runner.py`
- Modify: `tests/test_enhanced_features.py`
- Modify: `tests/test_solvers.py`

- [ ] **Step 1: Add a failing request contract test for preloaded DataFrame preservation**

Add this test to `tests/test_tui_contracts.py`:

```python
import pandas as pd

from core.contracts import AnalysisRunRequest


def test_analysis_run_request_preserves_preloaded_dataframe() -> None:
    df = pd.DataFrame({"issuer_name": ["Target", "P1"], "metric": [1, 2]})
    request = AnalysisRunRequest(mode="share", csv="", metric="metric")
    request.df = df

    namespace = request.to_namespace()

    assert namespace.df is df
```

- [ ] **Step 2: Run the focused test and confirm the current failure**

Run: `py -m pytest tests/test_tui_contracts.py::test_analysis_run_request_preserves_preloaded_dataframe -v`

Expected before implementation: `FAILED` because `namespace.df` is `None`.

- [ ] **Step 3: Add output-format regression tests**

Add to `tests/test_output_artifacts.py`:

```python
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from openpyxl import load_workbook

from benchmark import run_share_analysis


def _share_args(output: Path, df: pd.DataFrame, output_format: str = "both") -> SimpleNamespace:
    return SimpleNamespace(
        csv="",
        df=df,
        metric="txn_cnt",
        secondary_metrics=None,
        entity="Target",
        entity_col="issuer_name",
        output=str(output),
        dimensions=["card_type"],
        auto=False,
        time_col=None,
        config=None,
        preset=None,
        debug=True,
        log_level="INFO",
        per_dimension_weights=False,
        export_balanced_csv=False,
        validate_input=False,
        compare_presets=False,
        analyze_distortion=False,
        output_format=output_format,
        include_calculated=False,
        auto_subset_search=None,
        subset_search_max_tests=None,
        trigger_subset_on_slack=None,
        max_cap_slack=None,
        compliance_posture=None,
        acknowledge_accuracy_first=False,
    )


def test_output_format_both_writes_analysis_and_publication(tmp_path: Path) -> None:
    df = pd.DataFrame(
        {
            "issuer_name": ["Target", "P1", "P2", "P3", "P4", "P5", "P6"],
            "card_type": ["A", "A", "A", "A", "A", "A", "A"],
            "txn_cnt": [100, 200, 180, 160, 140, 120, 110],
        }
    )
    output = tmp_path / "share.xlsx"

    result = run_share_analysis(_share_args(output, df), __import__("logging").getLogger("test_output"))

    assert result == 0
    assert output.exists()
    assert (tmp_path / "share_publication.xlsx").exists()


def test_debug_workbook_contains_diagnostic_sheets(tmp_path: Path) -> None:
    df = pd.DataFrame(
        {
            "issuer_name": ["Target", "P1", "P2", "P3", "P4", "P5", "P6"],
            "card_type": ["A", "A", "A", "A", "A", "A", "A"],
            "txn_cnt": [100, 200, 180, 160, 140, 120, 110],
        }
    )
    output = tmp_path / "share.xlsx"

    result = run_share_analysis(_share_args(output, df, output_format="analysis"), __import__("logging").getLogger("test_sheets"))

    assert result == 0
    workbook = load_workbook(output, read_only=True)
    try:
        assert "Peer Weights" in workbook.sheetnames
        assert "Weight Methods" in workbook.sheetnames
        assert "Privacy Validation" in workbook.sheetnames
    finally:
        workbook.close()
```

- [ ] **Step 4: Run the output tests and confirm current failures**

Run: `py -m pytest tests/test_output_artifacts.py -v`

Expected before implementation: failures for missing publication workbook and diagnostic sheets.

- [ ] **Step 5: Add compliance-summary casing test**

Add to `tests/test_compliance_summary.py`:

```python
import pandas as pd

from core.compliance import build_compliance_summary


def test_compliance_summary_counts_title_case_validation_column() -> None:
    privacy_validation_df = pd.DataFrame({"Compliant": ["Yes", "No", "No"]})

    summary = build_compliance_summary(posture="strict", privacy_validation_df=privacy_validation_df)

    assert summary.violations == 2
    assert summary.verdict in {"non_compliant", "structural_infeasibility"}
```

- [ ] **Step 6: Add gate command parsing and fraud expectation tests**

Add to `tests/test_gate_runner.py`:

```python
import shlex


def test_gate_command_parser_preserves_quoted_entity_names() -> None:
    command = 'py benchmark.py share --entity "BANCO SANTANDER" --csv data/readme_demo.csv'

    parsed = ["/usr/bin/python3"] + shlex.split(command[3:])

    assert parsed[3] == "--entity"
    assert parsed[4] == "BANCO SANTANDER"
```

- [ ] **Step 7: Run the complete current failing bundle**

Run: `py -m pytest tests/test_tui_contracts.py tests/test_output_artifacts.py tests/test_compliance_summary.py tests/test_gate_runner.py tests/test_enhanced_features.py tests/test_solvers.py -v`

Expected before implementation: failures demonstrate every high-risk regression target.

- [ ] **Step 8: Commit regression tests**

Run:

```bash
git add tests/test_tui_contracts.py tests/test_output_artifacts.py tests/test_compliance_summary.py tests/test_gate_runner.py tests/test_enhanced_features.py tests/test_solvers.py
git commit -m "test: capture audit remediation regressions"
```

---

## Task 2: Preserve Preloaded DataFrames Through CLI/TUI Orchestration

**Files:**
- Modify: `core/contracts.py:47-119`
- Modify: `core/analysis_run.py:287-322`
- Modify: `tui_app.py:1235-1275`
- Test: `tests/test_tui_contracts.py`
- Test: `tests/test_benchmark_orchestration_helpers.py`

- [ ] **Step 1: Add `df` as an explicit request field**

In `core/contracts.py`, add the import and field:

```python
from typing import Any, Dict, List, Optional
```

Inside `AnalysisRunRequest`:

```python
    df: Any = None
```

Keep it near `csv` because both describe input source:

```python
    mode: str = "share"
    csv: Optional[str] = None
    df: Any = None
    entity: Optional[str] = None
```

- [ ] **Step 2: Simplify namespace conversion**

Replace `to_namespace()` in `core/contracts.py` with:

```python
    def to_namespace(self) -> argparse.Namespace:
        data: Dict[str, Any] = {f.name: getattr(self, f.name) for f in fields(self)}
        return argparse.Namespace(**data)
```

- [ ] **Step 3: Add a namespace round-trip test**

Add this test to `tests/test_tui_contracts.py`:

```python
from types import SimpleNamespace

import pandas as pd

from core.contracts import AnalysisRunRequest


def test_analysis_run_request_from_namespace_copies_dataframe() -> None:
    df = pd.DataFrame({"issuer_name": ["Target"], "metric": [1]})
    namespace = SimpleNamespace(mode="share", csv="", df=df, metric="metric", ignored_flag=True)

    request = AnalysisRunRequest.from_namespace("share", namespace)

    assert request.df is df
    assert not hasattr(request, "ignored_flag")
```

- [ ] **Step 4: Normalize preloaded DataFrames in `prepare_run_data()`**

In `core/analysis_run.py`, after `df = resolve_input_dataframe(args, data_loader)`, add:

```python
    if getattr(args, "df", None) is not None:
        df = data_loader._normalize_columns(df.copy())
```

This preserves CLI normalization parity for TUI preloaded data. Use `_normalize_columns` because this repository already treats it as the shared normalization primitive.

- [ ] **Step 5: Remove dynamic attribute assignment in TUI confirmed path**

In `tui_app.py`, replace:

```python
                if saved_df is not None:
                    request.df = saved_df
                artifacts = execute_run(request, logger)
```

with:

```python
                request.df = saved_df
                artifacts = execute_run(request, logger)
```

- [ ] **Step 6: Run request/TUI contract tests**

Run: `py -m pytest tests/test_tui_contracts.py tests/test_benchmark_orchestration_helpers.py::TestBenchmarkOrchestrationHelpers::test_resolve_input_dataframe_prefers_preloaded_dataframe -v`

Expected: all selected tests pass.

- [ ] **Step 7: Run previously failing publication tests**

Run: `py -m pytest tests/test_enhanced_features.py::TestValidationAndOutputs::test_publication_output_generated tests/test_enhanced_features.py::TestValidationAndOutputs::test_publication_output_generated_multi_rate -v`

Expected after Task 2: failures move past “No valid data source specified”; publication assertions may still fail until Task 3.

- [ ] **Step 8: Commit orchestration fix**

Run:

```bash
git add core/contracts.py core/analysis_run.py tui_app.py tests/test_tui_contracts.py
git commit -m "fix: preserve preloaded analysis dataframes"
```

---

## Task 3: Implement Analysis and Publication Output Modes

**Files:**
- Modify: `core/contracts.py:122-141`
- Modify: `core/analysis_run.py:168-182,496-507,829-835,1108-1114`
- Modify: `core/output_artifacts.py:13-68`
- Modify: `core/excel_reports.py:40-136`
- Modify: `core/report_generator.py:194-217`
- Test: `tests/test_output_artifacts.py`
- Test: `tests/test_enhanced_features.py`

- [ ] **Step 1: Make `report_paths` type match actual usage**

In `core/contracts.py`, change:

```python
    report_paths: Optional[Dict[str, str]] = None
```

to:

```python
    report_paths: Optional[List[str]] = None
```

- [ ] **Step 2: Build analysis and publication paths in one place**

In `core/analysis_run.py`, update `build_report_paths()` so:

```python
def build_report_paths(artifacts: AnalysisArtifacts, output_settings: Dict[str, Any]) -> List[str]:
    output_format = output_settings["output_format"]
    paths: List[str] = []
    if output_format in {"analysis", "both"}:
        paths.append(str(artifacts.analysis_output_file))
    if output_format in {"publication", "both"}:
        paths.append(str(artifacts.publication_output))
    return paths
```

- [ ] **Step 3: Assign publication path before writing outputs**

Where share and rate artifacts are assembled, set:

```python
    output_path = Path(request.output or "benchmark_output.xlsx")
    artifacts.analysis_output_file = str(output_path)
    artifacts.publication_output = str(output_path.with_name(f"{output_path.stem}_publication{output_path.suffix}"))
```

If the current code already assigns `analysis_output_file`, keep that value and add only `publication_output` next to it.

- [ ] **Step 4: Pass the merged config to report helpers**

In `core/output_artifacts.py`, add `config=config` to both `generate_excel_report()` and `generate_multi_rate_excel_report()` calls.

- [ ] **Step 5: Write output according to `output_format`**

Replace the single-write logic in `core/output_artifacts.py` with:

```python
    output_format = (config.get("output", "output_format", default=request.output_format) if config else request.output_format)
    write_analysis = output_format in {"analysis", "both"}
    write_publication = output_format in {"publication", "both"}

    if write_analysis:
        _write_report(output_file, publication=False)
        logger.info("Analysis report written to %s", output_file)

    if write_publication:
        publication_file = artifacts.publication_output or output_file
        _write_report(publication_file, publication=True)
        logger.info("Publication report written to %s", publication_file)
```

Use a small private helper `_write_report(path: str, publication: bool) -> None` inside `write_outputs()` to avoid duplicating the share/rate branches.

- [ ] **Step 6: Add diagnostic sheets in `ReportGenerator`**

In `core/report_generator.py`, after metric sheets and before `Metadata`, add:

```python
        self._write_optional_dataframe_sheet(wb, "Peer Weights", metadata, "weights_df")
        self._write_optional_dataframe_sheet(wb, "Weight Methods", metadata, "method_breakdown_df")
        self._write_optional_dataframe_sheet(wb, "Privacy Validation", metadata, "privacy_validation_df")
        self._write_optional_dataframe_sheet(wb, "Preset Comparison", metadata, "preset_comparison_df")
        self._write_optional_dataframe_sheet(wb, "Impact Detail", metadata, "impact_df")
        self._write_optional_dataframe_sheet(wb, "Impact Summary", metadata, "impact_summary_df")
```

Add this method:

```python
    def _write_optional_dataframe_sheet(
        self,
        workbook: Any,
        sheet_name: str,
        metadata: Optional[Dict[str, Any]],
        metadata_key: str,
    ) -> None:
        if not metadata:
            return
        df = metadata.get(metadata_key)
        if df is None or not hasattr(df, "empty") or df.empty:
            return
        ws = workbook.create_sheet(self._build_unique_sheet_name(sheet_name, workbook.sheetnames))
        for col_idx, column in enumerate(df.columns, start=1):
            ws.cell(row=1, column=col_idx, value=str(column))
        for row_idx, row in enumerate(df.itertuples(index=False), start=2):
            for col_idx, value in enumerate(row, start=1):
                ws.cell(row=row_idx, column=col_idx, value=value)
```

- [ ] **Step 7: Keep metadata sheet serializable**

In `_write_metadata_sheet`, when a metadata value is a DataFrame or list of validation objects, write a compact string such as:

```python
if hasattr(value, "shape"):
    display_value = f"DataFrame rows={value.shape[0]} cols={value.shape[1]}"
else:
    display_value = value
```

- [ ] **Step 8: Run output tests**

Run: `py -m pytest tests/test_output_artifacts.py tests/test_enhanced_features.py::TestValidationAndOutputs::test_publication_output_generated tests/test_enhanced_features.py::TestValidationAndOutputs::test_publication_output_generated_multi_rate -v`

Expected: all selected tests pass.

- [ ] **Step 9: Smoke-test CLI output**

Create a temporary CSV and run:

```bash
py benchmark.py share --csv /tmp/audit_share.csv --entity Target --entity-col issuer_name --metric txn_cnt --dimensions card_type --output /tmp/audit_share.xlsx --output-format both --no-validate-input
```

Expected: both `/tmp/audit_share.xlsx` and `/tmp/audit_share_publication.xlsx` exist.

- [ ] **Step 10: Commit output fix**

Run:

```bash
git add core/contracts.py core/analysis_run.py core/output_artifacts.py core/excel_reports.py core/report_generator.py tests/test_output_artifacts.py tests/test_enhanced_features.py
git commit -m "fix: honor analysis and publication report modes"
```

---

## Task 4: Replace Stubbed Preset Comparison With Real Metrics

**Files:**
- Modify: `core/preset_comparison.py:13-65`
- Modify: `benchmark.py:482-507`
- Test: `tests/test_enhanced_features.py`

- [ ] **Step 1: Make empty dimensions return an empty DataFrame**

At the start of `run_preset_comparison()`:

```python
    if not dimensions:
        return pd.DataFrame(columns=["Preset", "Mode", "Mean_Impact_PP", "Max_Impact_PP", "Status"])
```

- [ ] **Step 2: Use merged `ConfigManager` per preset**

Replace raw YAML slicing with:

```python
from utils.config_manager import ConfigManager

preset_config = ConfigManager(preset=preset_name)
opt_config = preset_config.config["optimization"]
analysis_config = preset_config.config["analysis"]
```

- [ ] **Step 3: Evaluate global and per-dimension variants**

Use this row loop:

```python
for preset_name in presets:
    for variant_name, consistent_weights in [(preset_name, True), (f"{preset_name}+perdim", False)]:
        rows.append(
            _run_single_preset_variant(
                preset_name=preset_name,
                variant_name=variant_name,
                consistent_weights=consistent_weights,
                df=df,
                metric_col=metric_col,
                dimensions=dimensions,
                entity_col=entity_col,
                target_entity=target_entity,
                time_col=time_col,
            )
        )
```

- [ ] **Step 4: Compute impact from actual analysis output**

Add helper:

```python
def _mean_abs_impact(results: Dict[str, pd.DataFrame]) -> tuple[float, float]:
    values: List[float] = []
    for result_df in results.values():
        for column in result_df.columns:
            if column in {"Impact_PP", "Distortion_PP"} or "Impact" in column or "Distortion" in column:
                numeric = pd.to_numeric(result_df[column], errors="coerce").dropna().abs()
                values.extend(numeric.tolist())
    if not values:
        return 0.0, 0.0
    return float(pd.Series(values).mean()), float(pd.Series(values).max())
```

- [ ] **Step 5: Produce explicit status per preset**

Rows should contain:

```python
{
    "Preset": variant_name,
    "Mode": "global" if consistent_weights else "per_dimension",
    "Mean_Impact_PP": round(mean_impact, 4),
    "Max_Impact_PP": round(max_impact, 4),
    "Status": "ok",
}
```

On exception:

```python
{
    "Preset": variant_name,
    "Mode": "global" if consistent_weights else "per_dimension",
    "Mean_Impact_PP": None,
    "Max_Impact_PP": None,
    "Status": f"failed: {exc}",
}
```

- [ ] **Step 6: Preserve legacy column name**

If existing reports expect `Mean_Distortion_PP`, add:

```python
comparison_df["Mean_Distortion_PP"] = comparison_df["Mean_Impact_PP"]
```

- [ ] **Step 7: Run preset tests**

Run: `py -m pytest tests/test_enhanced_features.py::TestValidationAndOutputs::test_preset_comparison_exhaustive tests/test_enhanced_features.py::TestPresetComparison::test_empty_dimensions_list -v`

Expected: both tests pass, and preset rows include `preset+perdim` variants.

- [ ] **Step 8: Commit preset comparison fix**

Run:

```bash
git add core/preset_comparison.py benchmark.py tests/test_enhanced_features.py
git commit -m "fix: compute real preset comparison metrics"
```

---

## Task 5: Fix Compliance Summary and Privacy Validation Coverage

**Files:**
- Modify: `core/compliance.py:59-75`
- Modify: `core/dimensional_analyzer.py:1470-1555`
- Test: `tests/test_compliance_summary.py`
- Test: `tests/test_additional_constraints_tiers.py`

- [ ] **Step 1: Count both validation column conventions**

Replace the violation-count block in `build_compliance_summary()` with:

```python
    if privacy_validation_df is not None and not privacy_validation_df.empty:
        if "compliant" in privacy_validation_df.columns:
            violations = int((~privacy_validation_df["compliant"].astype(bool)).sum())
        elif "Compliant" in privacy_validation_df.columns:
            normalized = privacy_validation_df["Compliant"].astype(str).str.strip().str.lower()
            violations = int((normalized != "yes").sum())
```

- [ ] **Step 2: Add `_TIME_TOTAL_` rows to privacy validation**

In `build_privacy_validation_dataframe()`, after the per-dimension time-aware rows are built, add a separate loop for time-total categories when `self.time_column` exists:

```python
        if self.time_column and self.time_column in df.columns:
            for time_period in self._get_time_periods(df):
                time_df = df[df[self.time_column] == time_period]
                entity_agg = time_df.groupby(self.entity_column).agg({metric_col: "sum"}).reset_index()
                peer_data = []
                for peer_entity in peers:
                    peer_vol = float(entity_agg[entity_agg[self.entity_column] == peer_entity][metric_col].sum())
                    peer_data.append({"peer": peer_entity, "volume": peer_vol})
                total_original_vol = sum(p["volume"] for p in peer_data)
                total_balanced_vol = sum(p["volume"] * weights.get(p["peer"], 1.0) for p in peer_data)
                for peer_info in peer_data:
                    peer = peer_info["peer"]
                    peer_weight = weights.get(peer, 1.0)
                    original_share = (peer_info["volume"] / total_original_vol * 100.0) if total_original_vol > 0 else 0.0
                    balanced_vol = peer_info["volume"] * peer_weight
                    balanced_share = (balanced_vol / total_balanced_vol * 100.0) if total_balanced_vol > 0 else 0.0
                    is_violation = self._is_share_violation(balanced_share, max_concentration)
                    validation_rows.append({
                        "Dimension": "_TIME_TOTAL_",
                        "Time_Period": time_period,
                        "Category": str(time_period),
                        "Peer": peer,
                        "Rule_Name": rule_name,
                        "Weight_Source": "Global",
                        "Weight_Method": self.weight_methods.get("_TIME_TOTAL_", "Global-LP"),
                        "Multiplier": peer_weight,
                        "Original_Volume": peer_info["volume"],
                        "Original_Share_%": round(original_share, 4),
                        "Balanced_Volume": balanced_vol,
                        "Balanced_Share_%": round(balanced_share, 4),
                        "Privacy_Cap_%": max_concentration,
                        "Tolerance_%": self.tolerance,
                        "Additional_Constraints_Enforced": "No",
                        "Additional_Constraints_Relaxed": "No",
                        "Additional_Constraints_Passed": "Yes",
                        "Additional_Constraint_Detail": "Time total cap validation",
                        "Compliant": "No" if is_violation else "Yes",
                        "Violation_Margin_%": round(balanced_share - max_concentration, 4) if is_violation else 0.0,
                    })
```

- [ ] **Step 3: Add a test for time-total validation rows**

Add to `tests/test_compliance_summary.py`:

```python
import pandas as pd

from core.dimensional_analyzer import DimensionalAnalyzer


def test_time_aware_privacy_validation_includes_time_total_rows() -> None:
    df = pd.DataFrame(
        {
            "issuer_name": ["Target", "P1", "P2", "P3", "P4", "P5", "P6"] * 2,
            "month": ["2024-01"] * 7 + ["2024-02"] * 7,
            "card_type": ["A", "A", "A", "A", "A", "A", "A"] * 2,
            "txn_cnt": [100, 200, 180, 160, 140, 120, 110, 90, 190, 170, 150, 130, 115, 105],
        }
    )
    analyzer = DimensionalAnalyzer(
        target_entity="Target",
        entity_column="issuer_name",
        time_column="month",
        debug_mode=True,
    )
    analyzer.calculate_global_privacy_weights(df, "txn_cnt", ["card_type"])

    validation_df = analyzer.build_privacy_validation_dataframe(df, "txn_cnt", ["card_type"])

    assert "_TIME_TOTAL_" in set(validation_df["Dimension"])
```

- [ ] **Step 4: Run compliance tests**

Run: `py -m pytest tests/test_compliance_summary.py tests/test_additional_constraints_tiers.py -v`

Expected: all selected tests pass.

- [ ] **Step 5: Commit compliance summary fix**

Run:

```bash
git add core/compliance.py core/dimensional_analyzer.py tests/test_compliance_summary.py
git commit -m "fix: report compliance violations consistently"
```

---

## Task 6: Clarify and Harden Optimizer Privacy Policy

**Files:**
- Modify: `core/global_weight_optimizer.py:100-126`
- Modify: `core/privacy_validator.py:286-310`
- Modify: `core/solvers/lp_solver.py:176-187`
- Test: `tests/test_solvers.py`
- Test: `tests/test_privacy_rules_config.py`
- Test: `tests/test_global_weight_optimizer_fallbacks.py`

- [ ] **Step 1: Decide merchant rule policy in code comments and tests**

If merchant `4/35` must only apply at exactly 4 peers, change:

```python
if merchant_mode and '4/35' in rules and peer_count >= int(rules['4/35'].get('min_entities', 4)):
```

to:

```python
if merchant_mode and peer_count == int(rules["4/35"].get("min_entities", 4)):
```

If merchants should always use `4/35`, add a test and doc note stating that merchant benchmarking intentionally uses `4/35` for all peer counts >= 4.

- [ ] **Step 2: Add explicit tests for merchant rule selection**

In `tests/test_privacy_rules_config.py`:

```python
def test_merchant_rule_selection_is_explicit_for_large_peer_groups() -> None:
    assert PrivacyValidator.select_rule(4, merchant_mode=True) == "4/35"
    assert PrivacyValidator.select_rule(10, merchant_mode=False) == "10/40"
```

Add the merchant-mode expectation chosen in Step 1.

- [ ] **Step 3: Replace silent identity fallback for insufficient peers**

In `core/global_weight_optimizer.py`, replace identity fallback with:

```python
        if rule_name == "insufficient":
            raise ValueError(f"Insufficient peers for privacy rule selection: peers={peer_count}")
```

If backwards compatibility requires no exception, set:

```python
            analyzer.compliance_blocked_reason = "insufficient_peers"
            analyzer.global_dimensions_used = []
```

and ensure `execute_share_run()` / `execute_rate_run()` turns that marker into `RunAborted`.

- [ ] **Step 4: Add insufficient-peer test**

In `tests/test_global_weight_optimizer_fallbacks.py`:

```python
def test_global_optimizer_aborts_on_insufficient_peers() -> None:
    # Build a fake analyzer with three peers and assert ValueError contains "Insufficient peers".
```

- [ ] **Step 5: Document LP additional-constraint scope**

In `core/solvers/lp_solver.py`, above the cap constraint loop, add:

```python
# This LP encodes max-concentration caps. Tier participant requirements
# are evaluated after solving because they are count-based, non-linear
# constraints in the current solver architecture.
```

- [ ] **Step 6: Make solver success mean post-validated success where used**

In `core/solvers/heuristic_solver.py`, after optimization, compute residual cap and additional violations. Return `success=False` when residual violations remain with `tolerance=0.0`.

- [ ] **Step 7: Run optimizer tests**

Run: `py -m pytest tests/test_solvers.py tests/test_privacy_rules_config.py tests/test_global_weight_optimizer_fallbacks.py -v`

Expected: all selected tests pass.

- [ ] **Step 8: Commit privacy policy hardening**

Run:

```bash
git add core/global_weight_optimizer.py core/privacy_validator.py core/solvers/lp_solver.py core/solvers/heuristic_solver.py tests/test_solvers.py tests/test_privacy_rules_config.py tests/test_global_weight_optimizer_fallbacks.py
git commit -m "fix: harden optimizer privacy policy handling"
```

---

## Task 7: Validate Configs and Presets Consistently

**Files:**
- Modify: `utils/config_manager.py:33-84,156-188`
- Modify: `utils/preset_manager.py:58-69`
- Modify: `utils/validators.py`
- Modify: `presets/low_distortion.yaml`
- Modify: `presets/strategic_consistency.yaml`
- Create: `tests/test_preset_validation.py`

- [ ] **Step 1: Remove duplicate mapping keys**

In `utils/config_manager.py`, choose canonical aliases:

```python
"total_txns": "total_count"
"total_amount": "total_amount"
```

Remove the earlier duplicate entries that map them to share metrics. Keep unambiguous share aliases such as `txn_count`, `txn_amt`, `tpv`, and `amount`.

- [ ] **Step 2: Validate JSON configs**

In `load_config()`, after JSON load:

```python
from .validators import ConfigValidator, ConfigValidationError
errors = ConfigValidator.validate(loaded_config)
if errors:
    raise ConfigValidationError(errors)
```

Use the same validation path for YAML and JSON.

- [ ] **Step 3: Make all shipped presets valid**

For `presets/low_distortion.yaml`, choose valid bounds:

```yaml
optimization:
  bounds:
    max_weight: 1.0001
    min_weight: 1.0
```

For `presets/strategic_consistency.yaml`, choose a positive disabled-search value:

```yaml
  subset_search:
    enabled: false
    max_attempts: 1
```

- [ ] **Step 4: Add preset validation test**

Create `tests/test_preset_validation.py`:

```python
from pathlib import Path

from utils.validators import load_config


def test_all_shipped_presets_validate() -> None:
    for preset_path in sorted(Path("presets").glob("*.yaml")):
        config = load_config(preset_path)
        assert config["version"] == "3.0"
```

- [ ] **Step 5: Decide unknown nested-key policy**

If legacy keys like `lambda_penalty` and `max_tests` are supported, add them to `ConfigValidator`. If they are not supported, rename or remove them from presets and add validator errors for unknown `optimization.linear_programming` and `optimization.subset_search` keys.

- [ ] **Step 6: Run config tests and lint duplicate-key check**

Run:

```bash
py -m pytest tests/test_preset_validation.py tests/test_privacy_rules_config.py -v
ruff check --select F601 utils/config_manager.py
```

Expected: tests pass and ruff reports no repeated dict keys.

- [ ] **Step 7: Commit config and preset fixes**

Run:

```bash
git add utils/config_manager.py utils/preset_manager.py utils/validators.py presets/low_distortion.yaml presets/strategic_consistency.yaml tests/test_preset_validation.py
git commit -m "fix: validate presets and config aliases"
```

---

## Task 8: Fix Data Loader Safety and Rate Validation

**Files:**
- Modify: `core/data_loader.py:273-278,948-960`
- Test: `tests/test_enhanced_features.py`

- [ ] **Step 1: Validate SQL table names**

Add helper in `core/data_loader.py`:

```python
def _validate_sql_identifier(identifier: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?", identifier):
        raise ValueError(f"Unsafe SQL table name: {identifier!r}")
    return identifier
```

Import `re` at the top of the file.

- [ ] **Step 2: Use validated table name**

Replace:

```python
query = f"SELECT * FROM {table_name}"
```

with:

```python
safe_table_name = _validate_sql_identifier(table_name)
query = f"SELECT * FROM {safe_table_name}"
```

- [ ] **Step 3: Treat impossible rates as errors**

In `validate_rate_input()`, split rate checks:

```python
impossible_mask = rates > 100.0
if impossible_mask.any():
    issues.append(ValidationIssue(
        severity=ValidationSeverity.ERROR,
        category="invalid_rates",
        message=f"Rate '{rate_name}' has {int(impossible_mask.sum())} values above 100%",
    ))
```

Keep the deviation warning for values below zero or other configured outliers only if product requirements still need it.

- [ ] **Step 4: Add validation tests**

In `tests/test_enhanced_features.py`, add a rate validation test with `approved > total` and assert an `ERROR` issue category `invalid_rates`.

- [ ] **Step 5: Run data validation tests**

Run: `py -m pytest tests/test_enhanced_features.py::TestValidationEdgeCases -v`

Expected: all selected tests pass.

- [ ] **Step 6: Commit data safety fix**

Run:

```bash
git add core/data_loader.py tests/test_enhanced_features.py
git commit -m "fix: harden data loader validation"
```

---

## Task 9: Repair Gate Runner and CSV Validator

**Files:**
- Modify: `scripts/perform_gate_test.py:110-123,371-377,482-503,552-562`
- Modify: `scripts/generate_cli_sweep.py:151-157,272-276`
- Modify: `utils/csv_validator.py:46-80,515-526`
- Test: `tests/test_gate_runner.py`

- [ ] **Step 1: Parse gate commands with `shlex.split`**

In `scripts/perform_gate_test.py`, import `shlex` and replace:

```python
cmd_list = [sys.executable] + command[3:].split()
```

with:

```python
cmd_list = [sys.executable] + shlex.split(command[3:])
```

Replace `command.split()` with `shlex.split(command)`.

- [ ] **Step 2: Avoid destructive cleanup before case generation succeeds**

In `GateTestRunner.run()`, move cleanup after `self.generate_cases()` succeeds, or preserve checked-in case files by cleaning only `self.output_dir / "outputs"`.

Use:

```python
generated_outputs = self.output_dir / "outputs"
if generated_outputs.exists():
    shutil.rmtree(generated_outputs)
```

- [ ] **Step 3: Fix Excel error detection**

Replace the error-cell block with:

```python
error_patterns = ("#DIV/0!", "#N/A", "#VALUE!", "#REF!", "#NAME?")
for col in df.columns:
    values = df[col].astype(str)
    if values.apply(lambda cell: any(pattern in cell for pattern in error_patterns)).any():
        failures.append(f"Sheet '{sheet_name}' Column '{col}': Contains Excel errors")
```

- [ ] **Step 4: Enforce fraud BPS expectation**

Replace the `pass` statements in the `fraud_in_bps_in_publication` block with failures:

```python
if not any("bps" in h.lower() for h in headers):
    failures.append("Fraud publication output is missing bps header")
break
if not found_fraud:
    failures.append("Fraud publication output is missing fraud rate column")
```

- [ ] **Step 5: Add handler for `fraud_in_percent_in_publication`**

Add:

```python
elif exp == "fraud_in_percent_in_publication":
    if wb_pub:
        headers = []
        for sheet in wb_pub.sheetnames:
            if sheet == "Summary":
                continue
            headers.extend(str(c.value) for c in wb_pub[sheet][3] if c.value)
        if any("Fraud" in h and "bps" in h.lower() for h in headers):
            failures.append("Fraud publication output used bps when percent was expected")
```

- [ ] **Step 6: Make CSV validator fail on unmatched dimensions**

In `utils/csv_validator.py`, add `"Metadata"` to `skip_sheets` and replace skipped dimensions with a failed result:

```python
if excel_df is None:
    all_results.append(ValidationResult(False, dimension, "sheet_match", "No matching Excel sheet found"))
    continue
```

- [ ] **Step 7: Match generated metric sheet names**

Add helper:

```python
def _sheet_matches_dimension(sheet_name: str, dimension: str) -> bool:
    normalized_sheet = sheet_name.lower().replace("_", "")
    normalized_dim = dimension.lower().replace("_", "").replace("/", "")
    return normalized_sheet == normalized_dim or normalized_sheet.endswith(normalized_dim[:20])
```

Use it in the dimension loop.

- [ ] **Step 8: Run gate/tooling tests**

Run: `py -m pytest tests/test_gate_runner.py -v`

Expected: all gate parser tests pass.

- [ ] **Step 9: Commit gate and validator fixes**

Run:

```bash
git add scripts/perform_gate_test.py scripts/generate_cli_sweep.py utils/csv_validator.py tests/test_gate_runner.py
git commit -m "fix: make gate verification meaningful"
```

---

## Task 10: Harden TUI Non-GUI Behavior

**Files:**
- Modify: `tui_app.py:642-647,823-836,1099-1275`
- Test: `tests/test_tui_contracts.py`

- [ ] **Step 1: Add mode resolution helper**

In `tui_app.py`, add method on `BenchmarkApp`:

```python
    def _current_mode(self) -> str:
        active = str(self.query_one(TabbedContent).active)
        return "share" if active == "share_tab" else "rate"
```

Replace direct comparison at lines 1142-1143 with `mode = self._current_mode()`.

- [ ] **Step 2: Add entity-column validation**

Before constructing `AnalysisRunRequest`, if `entity_col` resolves to `"issuer_name"` and the CSV header does not contain it, notify and re-enable Run:

```python
if entity_col == "issuer_name" and self.current_file:
    headers = list(pd.read_csv(self.current_file, nrows=0).columns)
    if "issuer_name" not in [h.lower().replace(" ", "_") for h in headers]:
        self.call_from_thread(self.notify, "Select the entity column before running.", severity="error")
        self.call_from_thread(lambda: setattr(self.query_one("#btn_run"), "disabled", False))
        return
```

- [ ] **Step 3: Clear file list before repopulating**

In `populate_file_list()`, clear the `ListView` before extending:

```python
file_list.clear()
file_list.extend(items)
```

- [ ] **Step 4: Prevent duplicate root log handlers**

Before adding a `LogHandler`, remove existing handlers of the same type for the same widget:

```python
for handler in list(root_logger.handlers):
    if isinstance(handler, LogHandler):
        root_logger.removeHandler(handler)
```

- [ ] **Step 5: Add pure tests for helper behavior**

In `tests/test_tui_contracts.py`, add this import-safe test:

```python
from types import SimpleNamespace

from core.analysis_run import build_run_config
from core.contracts import AnalysisRunRequest


def test_analysis_run_request_copies_dataframe_from_namespace() -> None:
    df = object()
    namespace = SimpleNamespace(mode="share", csv="", df=df, metric="metric")

    request = AnalysisRunRequest.from_namespace("share", namespace)

    assert request.df is df


def test_build_run_config_accepts_request_namespace_after_dataframe_fix() -> None:
    request = AnalysisRunRequest(mode="share", csv="", df=object(), metric="metric", validate_input=False)

    config = build_run_config(request.to_namespace())

    assert config.get("input", "validate_input") is False
```

- [ ] **Step 6: Run import and contract tests**

Run:

```bash
py -m py_compile tui_app.py
py -m pytest tests/test_tui_contracts.py -v
```

Expected: compile and tests pass.

- [ ] **Step 7: Commit TUI hardening**

Run:

```bash
git add tui_app.py tests/test_tui_contracts.py
git commit -m "fix: harden tui analysis workflow"
```

---

## Task 11: Correct Documentation and Developer Scripts

**Files:**
- Modify: `README.md:108-114`
- Modify: `SETUP.md:31-33`
- Modify: `run_tool.sh:24-26`
- Modify: `AGENTS.md`
- Modify: `docs/CORE_TECHNICAL_DOC.md`

- [ ] **Step 1: Correct participant guidance**

In `README.md`, replace:

```markdown
- At least 4 participants are required for privacy-compliant analysis.
```

with:

```markdown
- Non-merchant benchmarking requires enough peers for the selected privacy rule, starting at 5 peers for 5/25; merchant 4/35 is only available when merchant mode is explicitly used.
```

- [ ] **Step 2: Correct setup git command**

In `SETUP.md`, replace the corrupted line with:

```bash
cd /ads_storage/autobench && git init && git remote add origin https://e176097@scm.mastercard.int/stash/scm/~e176097/autobench.git && git fetch origin && git checkout -f -b main origin/main
```

- [ ] **Step 3: Use `py` launcher in TUI wrapper**

In `run_tool.sh`, replace:

```bash
python "$TUI_APP" "$@"
```

with:

```bash
py "$TUI_APP" "$@"
```

- [ ] **Step 4: Update AGENTS testing notes after fixes**

In `AGENTS.md`, update the Cursor Cloud testing note that currently says unit tests are 49/54 and gate share/rate fail due to quoting. After implementation, the note should state the fresh pass/fail counts from Task 12.

- [ ] **Step 5: Reconcile docs with implemented report sheets**

In `docs/CORE_TECHNICAL_DOC.md`, ensure the output sheet list matches actual generated sheets after Task 3.

- [ ] **Step 6: Commit docs fix**

Run:

```bash
git add README.md SETUP.md run_tool.sh AGENTS.md docs/CORE_TECHNICAL_DOC.md
git commit -m "docs: align audit remediation guidance"
```

---

## Task 12: Final Verification and Release Checklist

**Files:**
- No planned code edits.
- Verify the full repository state.

- [ ] **Step 1: Run unit tests**

Run: `py -m pytest tests/ -v`

Expected: all collected tests pass. If any test fails, fix the relevant task before continuing.

- [ ] **Step 2: Run lint**

Run: `ruff check --select E,F --ignore E501,F401 benchmark.py core/ utils/ tui_app.py`

Expected: no `E` or `F` violations.

- [ ] **Step 3: Create gate CSV fixture when no local data exists**

If `data/` has no CSVs, create `data/readme_demo.csv` with:

```csv
issuer_name,card_type,channel,txn_cnt,total,approved,fraud
Target,CREDIT,Online,100,1000,900,10
P1,CREDIT,Online,200,2000,1800,20
P2,CREDIT,Online,180,1800,1600,18
P3,CREDIT,Online,160,1600,1450,16
P4,CREDIT,Online,140,1400,1280,14
P5,CREDIT,Online,120,1200,1100,12
P6,CREDIT,Online,110,1100,1000,11
```

Do not commit this file because `data/*.csv` is gitignored.

- [ ] **Step 4: Run gate test**

Run: `py scripts/perform_gate_test.py`

Expected: gate completes without command parsing failures. If business-case failures remain, each failure message must identify a real output issue rather than a runner bug.

- [ ] **Step 5: Run targeted CLI smoke**

Run:

```bash
py benchmark.py share --csv data/readme_demo.csv --entity Target --entity-col issuer_name --metric txn_cnt --dimensions card_type channel --output /tmp/remediation_share.xlsx --output-format both --debug --no-validate-input
```

Expected:
- `/tmp/remediation_share.xlsx` exists.
- `/tmp/remediation_share_publication.xlsx` exists.
- Analysis workbook contains `Peer Weights`, `Weight Methods`, and `Privacy Validation`.

- [ ] **Step 6: Confirm clean git state**

Run: `git status --short --branch`

Expected: only intended source changes are present before final commit; no generated `.xlsx`, `.csv`, `.log`, or `data/readme_demo.csv` files are staged.

- [ ] **Step 7: Final commit if verification edits were needed**

Run:

```bash
git add benchmark.py core/ tests/ utils/ scripts/ tui_app.py README.md SETUP.md run_tool.sh AGENTS.md docs/CORE_TECHNICAL_DOC.md
git commit -m "chore: finalize audit remediation verification"
```

Only run this commit when Step 1-6 required additional tracked edits.

---

## Self-Review

**Spec coverage:** The plan covers all audit categories requested in the prior review: preloaded data contract, output modes, preset comparison, core privacy policy, compliance summaries, config/presets, data validation, gate tooling, CSV validation, TUI workflow, and docs drift.

**Placeholder scan:** The plan contains exact files, commands, expected outcomes, and code snippets. It avoids vague implementation instructions and does not rely on undefined functions except helpers explicitly defined in the relevant task.

**Type consistency:** `AnalysisRunRequest.df` is introduced before later tasks depend on it. `report_paths` is changed to `List[str]` before CLI printing continues to call `", ".join(...)`. Preset comparison columns preserve `Mean_Distortion_PP` while adding `Mean_Impact_PP`.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-06-audit-remediation.md`.

Two execution options:

1. **Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.
