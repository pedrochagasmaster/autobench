# De-Slop Audit

Date: 2026-05-30

Scope: read-only maintenance audit of the Python CLI/TUI benchmarking tool. This
document lists refactoring, deletion, reliability, and tooling opportunities.
It does not propose a rewrite or new framework. Unless marked as a bug, all
cleanup should preserve external behavior: CLI flags, config keys, workbook
formats, CSV formats, privacy rules, and public classes should remain stable.

Evidence labels:

- Confirmed: directly visible in code, tests, docs, committed artifacts, or
  call sites.
- Likely: strongly suggested by the repo shape, but owner or runtime
  confirmation is still useful.
- Needs confirmation: plausible cleanup target that needs production, owner, or
  runtime evidence.

Deletion labels:

- Safe to delete now: no active references found and low public interface risk.
- Probably dead, confirm first: not wired into the main workflow, but may be
  used manually.
- Risky to delete: public or compatibility surface; keep until explicitly
  deprecated or tested.

## A. Repo map

- Project type: pure Python CLI plus Textual TUI for privacy-compliant peer
  benchmarking.
- Main entrypoints:
  - `benchmark.py`: CLI commands `share`, `rate`, and `config`.
  - `tui_app.py`: Textual UI.
  - `utils/csv_validator.py`: CSV-vs-Excel validator utility.
  - `scripts/perform_gate_test.py`: integration gate runner.
  - `scripts/generate_cli_sweep.py` and `scripts/run_cli_sweep.py`: sweep
    generation and execution.
- Core modules:
  - `core/dimensional_analyzer.py`: main analysis facade and remaining large
    state holder.
  - `core/analysis_run.py`: shared CLI/TUI orchestration.
  - `core/global_weight_optimizer.py`, `core/solvers/*`: optimizer and solver
    flow.
  - `core/privacy_validator.py`, `core/privacy_policy.py`: privacy rule
    selection and enforcement.
  - `core/data_loader.py`: CSV and legacy SQL loading plus validation helpers.
  - `core/report_generator.py`, `core/excel_reports.py`,
    `core/output_artifacts.py`: workbook/publication output paths.
  - `core/contracts.py`: orchestration and solver dataclasses.
- Peripheral modules:
  - `utils/config_manager.py`, `utils/preset_manager.py`,
    `utils/validators.py`, `utils/logger.py`.
  - `scripts/` diagnostics, gate, and sweep tooling.
  - `tool_extension_project/`: historical extension scripts and docs.
  - `test_gate/`, `test_sweeps/`, `outputs/`: generated or investigation
    artifacts.
- Tests and commands found:
  - `py -m pytest tests/ -v`
  - `py scripts/perform_gate_test.py`
  - `ruff check --select E,F --ignore E501,F401 benchmark.py core/ utils/ tui_app.py`
  - `py utils/csv_validator.py report.xlsx report_balanced.csv --verbose`
- Tooling gaps:
  - No `pyproject.toml`, `pytest.ini`, `tox.ini`, or GitHub Actions workflow.
  - `mypy.ini` exists but excludes `benchmark.py` and `tui_app.py`.
  - Runtime `requirements.txt` does not declare dev tools such as `pytest`,
    `ruff`, or `mypy`.
- Public interfaces to treat carefully:
  - CLI commands and flags.
  - YAML config schema and shipped presets.
  - Excel workbook sheet names and CSV export schemas.
  - `core.__all__`: `DimensionalAnalyzer`, `PrivacyValidator`, `DataLoader`,
    `ReportGenerator`.
  - Deprecated distortion/weight-effect wrappers until their deprecation window
    is closed.

## B. Executive diagnosis

- `core` still imports `benchmark.py`, so the CLI remains part of the core
  dependency graph.
- `benchmark.py` is mostly a CLI adapter, but still owns large balanced CSV and
  compatibility-wrapper logic.
- `execute_share_run` and `execute_rate_run` are copy-paste pipelines with
  parity risk.
- `DimensionalAnalyzer` remains a god object despite useful partial extraction.
- Config is mapped manually through defaults, CLI overrides, TUI fields,
  analyzer constructor parameters, and solver request objects.
- The TUI advanced override path appears invalid against the strict config
  validator.
- Gate and sweep validation is noisy and partly theatrical: some expectations
  are emitted but not enforced, and fixtures are not clean-clone portable.
- Generated, client-specific, and historical artifacts are mixed into the main
  tree.
- Legacy "distortion" naming is still intertwined with newer "impact" naming.
- Broad `except Exception` blocks hide real failures in CLI help, TUI config,
  data loading, preset comparison, and gate tooling.

## C. Prioritized findings

### F01 - Break `core -> benchmark` imports

- Severity: High
- Confidence: Confirmed
- Category: architecture, public interface
- Location: `core/analysis_run.py`, `core/output_artifacts.py`,
  `benchmark.py`
- Problem: Core orchestration imports helpers from the CLI module.
- Evidence: `core/analysis_run.py` lazy-imports `get_balanced_metrics_df` and
  `export_balanced_csv` from `benchmark.py`. `core/output_artifacts.py` imports
  `generate_excel_report` and `generate_multi_rate_excel_report` from
  `benchmark.py`. `benchmark.py` imports `core.analysis_run`, creating a cycle.
- Why it matters: core cannot be tested or imported cleanly without the CLI
  module, and compatibility wrappers in `benchmark.py` become load-bearing.
- Safer direction: move balanced CSV helpers into `core/balanced_export.py` and
  call `core.excel_reports` directly from `core/output_artifacts.py`. Leave
  `benchmark.py` as parser, command router, and console output adapter.
- Validation:
  - `py -m pytest tests/test_output_artifacts.py tests/test_benchmark_orchestration_helpers.py -v`
  - `py scripts/perform_gate_test.py`
  - `ruff check --select E,F --ignore E501,F401 benchmark.py core/ utils/ tui_app.py`

### F02 - Move balanced CSV/export logic out of `benchmark.py`

- Severity: High
- Confidence: Confirmed
- Category: duplication, complexity
- Location: `benchmark.py:get_balanced_metrics_df`,
  `benchmark.py:export_balanced_csv`
- Problem: Hundreds of lines of weighted aggregation and CSV schema logic live
  in the CLI file.
- Evidence: `get_balanced_metrics_df` and `export_balanced_csv` duplicate
  weight lookup, grouping, time handling, raw/balanced calculations, and CSV
  row building for share and rate paths.
- Why it matters: share/rate export fixes must be patched in multiple places,
  and core behavior is hidden in the entrypoint.
- Safer direction: extract a dedicated core module with one weight resolver, one
  grouping helper, and separate small row builders for share/rate schemas.
- Validation:
  - `py -m pytest tests/test_enhanced_features.py tests/test_output_artifacts.py -v`
  - `py scripts/perform_gate_test.py`
  - `py utils/csv_validator.py <rate_report.xlsx> <rate_balanced.csv> --verbose`

### F03 - Consolidate share/rate run orchestration

- Severity: High
- Confidence: Confirmed
- Category: duplication, reliability
- Location: `core/analysis_run.py:execute_share_run`,
  `core/analysis_run.py:execute_rate_run`
- Problem: Share and rate runs duplicate setup, validation, compliance blocking,
  optimizer execution, diagnostics, preset comparison, artifact construction,
  output writing, CSV export, and audit log handling.
- Evidence: The two functions have the same skeleton with metric-specific
  branches embedded inline.
- Why it matters: adding or fixing a cross-cutting run feature requires editing
  both functions and can create share/rate drift.
- Safer direction: extract a common run pipeline and pass mode-specific
  callbacks for metric validation, result calculation, and impact summary.
- Validation:
  - `py -m pytest tests/test_benchmark_orchestration_helpers.py tests/test_output_artifacts.py -v`
  - `py scripts/perform_gate_test.py`
  - Add/keep one share and one rate CLI subprocess smoke test.

### F04 - Deduplicate privacy weight fitting

- Severity: Medium
- Confidence: Confirmed
- Category: duplication, fake abstraction
- Location: `core/analysis_run.py`, `core/preset_comparison.py`,
  `core/dimensional_analyzer.py`
- Problem: The same `consistent_weights` branch appears in share, rate, and
  preset comparison paths, and callers reach into private analyzer methods.
- Evidence: Each path chooses between `calculate_global_privacy_weights` and
  `_build_categories` + `_get_privacy_rule` + `_solve_per_dimension_weights`.
- Why it matters: privacy fitting changes can drift between normal runs and
  preset comparison.
- Safer direction: add a public `fit_privacy_weights(...)` helper or analyzer
  method and call it from all three paths.
- Validation:
  - `py -m pytest tests/test_enhanced_features.py tests/test_global_weight_optimizer_fallbacks.py -v`
  - `py scripts/perform_gate_test.py`

### F05 - Shrink `DimensionalAnalyzer`

- Severity: High
- Confidence: Confirmed
- Category: complexity, architecture
- Location: `core/dimensional_analyzer.py`
- Problem: The analyzer still owns solver request construction, subset search,
  per-dimension solving, privacy validation dataframe construction, metrics,
  impact summaries, deprecated wrappers, and broad mutable run state.
- Evidence: The constructor has many optimization, privacy, Bayesian, dynamic
  constraint, merchant, and reporting controls. Several methods now only
  delegate to extracted modules, while other large pieces remain in the class.
- Why it matters: compliance and report changes require understanding too much
  state in one file.
- Safer direction: preserve public methods, but move impact math, privacy
  validation dataframe construction, solver-request building, and subset search
  into named core modules.
- Validation:
  - `py -m pytest tests/test_solvers.py tests/test_global_weight_optimizer_fallbacks.py -v`
  - `py -m pytest tests/test_cli_runtime_behavior.py -v`
  - `py scripts/perform_gate_test.py`

### F06 - Replace duplicated solver request builders

- Severity: Medium
- Confidence: Confirmed
- Category: duplication
- Location: `core/dimensional_analyzer.py`, `core/global_weight_optimizer.py`,
  `core/contracts.py`
- Problem: LP and heuristic `SolverRequest` objects are assembled in multiple
  places from analyzer state.
- Evidence: `DimensionalAnalyzer` and `GlobalWeightOptimizer` both map analyzer
  attributes into `SolverRequest`.
- Why it matters: config/solver defaults can drift between global and
  per-dimension paths.
- Safer direction: one `SolverRequestBuilder` or analyzer settings object used
  by both code paths.
- Validation:
  - `py -m pytest tests/test_solvers.py tests/test_global_weight_optimizer_fallbacks.py -v`

### F07 - Collapse config mapping sprawl

- Severity: Medium
- Confidence: Confirmed
- Category: complexity, public interface
- Location: `utils/config_manager.py`, `core/analysis_run.py`,
  `core/contracts.py`, `tui_app.py`
- Problem: Optimization/config fields are hand-mapped across defaults, CLI
  overrides, TUI fields, analyzer constructor kwargs, and solver request
  dataclasses.
- Evidence: `ConfigManager._get_default_config`, `_apply_cli_overrides`,
  `build_dimensional_analyzer`, `SolverRequest`, and TUI advanced fields all
  contain overlapping key maps.
- Why it matters: adding or renaming a setting requires edits in many files and
  can create silent inconsistencies.
- Safer direction: build one typed settings object from merged config and use it
  as the interface between config, TUI, analyzer, and solvers.
- Validation:
  - `py -m pytest tests/test_preset_validation.py tests/test_privacy_rules_config.py -v`
  - `py benchmark.py config validate config/template.yaml`

### F08 - Fix TUI advanced override validation

- Severity: High
- Confidence: Confirmed
- Category: reliability, UI
- Location: `tui_app.py:apply_advanced_overrides`,
  `utils/validators.py`, `core/analysis_run.py`
- Problem: The TUI writes override YAML with `version: "tui-override"` and no
  `compliance_posture`, while the config validator requires version `3.0` and a
  valid compliance posture.
- Evidence: `apply_advanced_overrides` writes the temp config and stores it on
  `request.config`. `utils/validators.py` rejects unsupported versions and
  missing `compliance_posture`.
- Why it matters: the advanced TUI path can fail before analysis or silently
  discourage users from using config overrides.
- Safer direction: either emit a valid partial v3.0 override with inherited
  posture, or introduce an explicit partial-override loading path.
- Validation:
  - Add a unit test for `PresetWorkflow.write_override_file` +
    `ConfigManager(config_file=..., preset=...)`.
  - Manual TUI: load preset, edit advanced values, apply overrides, run with
    demo CSV.

### F09 - Remove TUI advanced field mirror mapping

- Severity: Medium
- Confidence: Confirmed
- Category: duplication, reliability
- Location: `tui_app.py:update_advanced_parameters`,
  `tui_app.py:apply_advanced_overrides`
- Problem: Advanced config load and save paths mirror the same widget/YAML map
  by hand.
- Evidence: Both methods enumerate LP, constraints, bounds, subset, Bayesian,
  analysis, and output fields.
- Why it matters: new fields can be added to one direction but not the other.
- Safer direction: one field map that can populate widgets and collect values.
- Validation:
  - Manual TUI round trip: preset -> edit advanced -> export YAML -> validate.
  - `py -m pytest tests/test_tui_contracts.py tests/test_preset_workflow.py -v`

### F10 - Stop silent TUI widget failures

- Severity: Medium
- Confidence: Confirmed
- Category: reliability, AI smell
- Location: `tui_app.py`
- Problem: TUI helper methods catch `Exception` and return empty strings,
  `False`, or `pass` for missing fields.
- Evidence: `safe_set_input`, `safe_set_checkbox`, `get_input`, and `get_bool`
  swallow all exceptions.
- Why it matters: a renamed widget ID turns into a quiet config change rather
  than a diagnosable error.
- Safer direction: catch the specific widget lookup exception and log/notify
  the missing field ID.
- Validation:
  - Add a small unit or app-level test that a missing field is surfaced.
  - Manual advanced settings smoke test.

### F11 - Avoid double validation in TUI runs

- Severity: Medium
- Confidence: Confirmed
- Category: architecture, reliability
- Location: `tui_app.py:run_analysis`, `core/analysis_run.py`
- Problem: The TUI validation-first flow builds config, loads data, resolves
  dimensions, and validates before calling `execute_run`; the executor repeats
  much of that work.
- Evidence: TUI calls `build_run_config`, `prepare_run_data`,
  `resolve_dimensions`, and `validate_analysis_input`, then passes `saved_df` to
  the run executor, which rebuilds config and validates again.
- Why it matters: more IO, more chances for TUI and CLI behavior to drift.
- Safer direction: pass a prepared dataset/validation result to the executor, or
  mark validation as already complete when a preloaded dataframe is supplied.
- Validation:
  - `py -m pytest tests/test_tui_contracts.py -v`
  - Manual TUI run with validation warnings modal.

### F12 - Make diagnostics flags honest

- Severity: Medium
- Confidence: Confirmed
- Category: reliability, performance
- Location: `core/analysis_run.py:collect_run_diagnostics`
- Problem: `include_privacy_validation` and `export_csv` are accepted as
  parameters, but diagnostics always builds the privacy validation dataframe and
  method breakdown.
- Evidence: The function signature includes both flags, while the body
  unconditionally calls `build_privacy_validation_dataframe` and builds
  `method_breakdown_df`.
- Why it matters: flags do not communicate cost or behavior; users cannot turn
  off expensive diagnostics.
- Safer direction: gate diagnostics on `include_privacy_validation`,
  `debug_mode`, or output needs; delete unused `export_csv` if it truly has no
  purpose.
- Validation:
  - `py -m pytest tests/test_benchmark_orchestration_helpers.py -v`
  - One CLI smoke with debug on and one with debug off to compare sheet output.

### F13 - Unify report/output modules

- Severity: Medium
- Confidence: Confirmed
- Category: architecture, fake abstraction
- Location: `core/report_generator.py`, `core/excel_reports.py`,
  `core/output_artifacts.py`, `benchmark.py`
- Problem: Workbook generation is spread across a class, helper wrappers, an
  artifact writer, and CLI compatibility functions.
- Evidence: `excel_reports.py` mostly packages metadata and delegates to
  `ReportGenerator`; `output_artifacts.py` dispatches analysis vs publication;
  `benchmark.py` keeps wrappers over `excel_reports.py`.
- Why it matters: output feature changes require knowing several shallow layers.
- Safer direction: one output facade in `core/output_artifacts.py` backed by
  direct `ReportGenerator` calls; delete CLI wrappers after moving imports.
- Validation:
  - `py -m pytest tests/test_output_artifacts.py tests/test_report_generator_dependencies.py -v`
  - `py scripts/perform_gate_test.py`

### F14 - Reduce parser duplication

- Severity: Low
- Confidence: Confirmed
- Category: duplication
- Location: `benchmark.py:create_parser`
- Problem: share and rate parsers duplicate common config, logging, output,
  validation, comparison, and subset-search flags.
- Evidence: share and rate `add_argument` blocks repeat most run-level flags,
  with a few mode-specific differences.
- Why it matters: help text and defaults can drift.
- Safer direction: `add_common_run_flags(parser, mode=...)` plus explicit
  mode-only flags.
- Validation:
  - `py benchmark.py share --help`
  - `py benchmark.py rate --help`
  - Gate/sweep generation tests or smoke run.

### F15 - Remove unreachable CLI/TUI branches

- Severity: Low
- Confidence: Confirmed
- Category: dead weight
- Location: `benchmark.py:main`, `tui_app.py:on_button_pressed`
- Problem: `benchmark.py` handles a `presets` command that is not registered,
  and TUI handles `btn_help_presets` although the button ID is
  `btn_preset_help`.
- Evidence: `create_parser` registers only `share`, `rate`, and `config`;
  `main` still branches on `args.command == "presets"`. TUI compose creates
  `btn_preset_help`; handler also checks `btn_help_presets`.
- Deletion class: Safe to delete now.
- Safer direction: delete dead branches, leave `benchmark config list` intact.
- Validation:
  - `py benchmark.py config list`
  - Manual TUI click on `Preset Guide`.

### F16 - Delete unused imports and constants in `benchmark.py`

- Severity: Low
- Confidence: Confirmed
- Category: dead weight
- Location: `benchmark.py`
- Problem: imports/constants remain after the orchestration refactor.
- Evidence: imports such as `tempfile`, `ValidationSeverity`,
  `ReportGenerator`, `PrivacyValidator`, and several `core.analysis_run`
  helpers are unused in `benchmark.py`; `BEST_PRESET_MARKER` is defined there
  but preset comparison now lives in `core`.
- Deletion class: Safe to delete now, after lint confirms.
- Safer direction: run focused `ruff --select F401,F841` and delete only unused
  names.
- Validation:
  - `ruff check --select F401,F841 benchmark.py`
  - `py -m pytest tests/test_benchmark_orchestration_helpers.py -v`

### F17 - Decide SQL support fate

- Severity: Medium
- Confidence: Confirmed
- Category: dead weight, public interface
- Location: `core/data_loader.py`, `utils/config_manager.py`,
  `requirements.txt`
- Problem: SQL loading exists programmatically, but no CLI/TUI path exposes it.
- Evidence: `DataLoader.load_data` branches on `sql_query` and `sql_table`;
  `ConfigManager.get_sql_connection` imports `pypyodbc`; CLI parser is CSV
  centric.
- Deletion class: Risky to delete without owner evidence because it may be a
  programmatic API.
- Safer direction: either document/test SQL support as a public API, or remove
  it and `pypyodbc` from runtime dependencies.
- Validation:
  - Search external usage.
  - If kept: add a mock SQL connection test.
  - If removed: `py -m pytest tests/ -v`.

### F18 - Finish impact vs distortion terminology cleanup

- Severity: Medium
- Confidence: Confirmed
- Category: domain clarity, public interface
- Location: `benchmark.py`, `utils/config_manager.py`,
  `core/dimensional_analyzer.py`, `core/preset_comparison.py`,
  `core/report_generator.py`, `tui_app.py`
- Problem: New "impact" terminology coexists with legacy "distortion" names
  across CLI, config, TUI IDs, sheet helpers, aliases, and tests.
- Evidence: CLI exposes both `--analyze-impact` and deprecated
  `--analyze-distortion`; config maps `analyze_distortion` to
  `include_impact_summary`; TUI widget ID remains `analyze_distortion`; legacy
  wrappers are tested.
- Deletion class: Risky until deprecation completes.
- Safer direction: use impact internally and in docs/UI labels; keep aliases and
  wrapper tests until v4 removal.
- Validation:
  - `py -m pytest tests/test_legacy_wrappers.py tests/test_enhanced_features.py -v`
  - CLI help check for deprecation wording.

### F19 - Clarify peer-only impact behavior

- Severity: Low
- Confidence: Needs confirmation
- Category: reliability, public interface
- Location: `core/analysis_run.py`
- Problem: share impact is gated on a resolved entity; rate impact is not.
- Evidence: share path only builds impact when `include_impact_summary` and
  `resolved_entity`; rate path only checks `include_impact_summary`.
- Why it matters: peer-only share with `--analyze-impact` can silently omit
  sheets, while rate may still produce impact.
- Safer direction: document this behavior or align it intentionally.
- Validation:
  - Peer-only share smoke with `--analyze-impact`.
  - Peer-only rate smoke with `--analyze-impact`.

### F20 - Make broad exception handling actionable

- Severity: Medium
- Confidence: Confirmed
- Category: reliability, AI smell
- Location: `benchmark.py`, `core/data_loader.py`,
  `core/preset_comparison.py`, `tui_app.py`, `scripts/perform_gate_test.py`
- Problem: many broad `except Exception` blocks log vaguely, return empty
  values, or continue.
- Evidence: preset help returns empty, parser preset choices return empty,
  data loader config parsing falls back silently, preset comparison converts any
  failure into a status row or `None`, TUI helper lookups swallow failures.
- Why it matters: real regressions become missing options, skipped settings, or
  incomplete comparisons.
- Safer direction: catch narrow exceptions near expected failure modes; use
  boundary-level `exc_info=True` only where returning to the user.
- Validation:
  - Focused tests for missing preset directory, invalid advanced config, and
    failed preset comparison.

### F21 - Delete non-portable committed `test_sweeps/`

- Severity: Medium
- Confidence: Confirmed
- Category: dead weight, tooling
- Location: `test_sweeps/**`
- Problem: committed sweep artifacts are generated, large, stale, and
  environment-specific.
- Evidence: `test_sweeps/meta.json` references
  `data\e176097_tpv_nubank_filtered.csv`, Windows paths, private dimensions,
  and entity values not available in a clean clone.
- Deletion class: Safe to delete now.
- Safer direction: delete from git, regenerate on demand, and ignore generated
  outputs/results.
- Validation:
  - Generate a portable sweep from a committed or documented fixture.
  - `py scripts/run_cli_sweep.py --sweep-dir test_sweeps --results-json test_sweeps/results.json --workers 4 --limit 20`

### F22 - Delete `tool_extension_project/`

- Severity: Medium
- Confidence: Confirmed
- Category: dead weight
- Location: `tool_extension_project/**`
- Problem: archived client-specific scripts and completed plans are disconnected
  from the active tool.
- Evidence: scripts hardcode Nubank-specific data and outputs; docs say new
  functionality should be integrated into `benchmark.py`, `tui_app.py`, and
  `core`; no active imports from main code.
- Deletion class: Safe to delete now, unless owners still use it manually.
- Safer direction: delete or move outside the main source tree.
- Validation:
  - `py -m pytest tests/ -v`
  - Search for references before deletion.

### F23 - Remove scratch investigation outputs

- Severity: Low
- Confidence: Confirmed for some files, Needs confirmation for FortBrasil JSON
- Category: dead weight
- Location: `outputs/investigation/**`,
  `outputs/investigation_fortbrasil*/**`
- Problem: generated investigation YAML/JSON artifacts are committed under
  `outputs/`.
- Evidence: scratch YAMLs have no active references; FortBrasil JSONs reference
  proprietary data and may be historical baselines.
- Deletion class:
  - `outputs/investigation/*.yaml`: Safe to delete now.
  - `outputs/investigation_fortbrasil*/**`: Probably dead, confirm first.
- Safer direction: delete scratch configs; move any true golden baselines under
  `tests/fixtures/golden/` with a documented regeneration path.
- Validation:
  - Search references.
  - `py -m pytest tests/ -v`.

### F24 - Remove orphan config `config/peer_auto_privacy.yaml`

- Severity: Low
- Confidence: Confirmed
- Category: dead weight
- Location: `config/peer_auto_privacy.yaml`
- Problem: config file is not referenced by code or docs.
- Evidence: searches found no references; active privacy config is
  `config/privacy_rules.yaml`.
- Deletion class: Safe to delete now.
- Safer direction: delete, or move to docs/examples if it has explanatory value.
- Validation:
  - `py -m pytest tests/test_privacy_rules_config.py -v`
  - `py benchmark.py config validate config/template.yaml`

### F25 - Clean generated gate artifacts

- Severity: Low
- Confidence: Confirmed
- Category: dead weight, tooling
- Location: `test_gate/config/generated_template.yaml`
- Problem: generated config template output is committed even though the gate
  runner deletes/regenerates it.
- Evidence: `perform_gate_test.py` removes `test_gate/config/generated_template.yaml`
  before running cases.
- Deletion class: Safe to delete now.
- Safer direction: delete from git and ignore generated templates.
- Validation:
  - `py scripts/perform_gate_test.py`

### F26 - Pin gate fixture and make it clean-clone runnable

- Severity: High
- Confidence: Confirmed
- Category: reliability, tooling
- Location: `scripts/perform_gate_test.py`, `scripts/generate_cli_sweep.py`,
  `test_gate/meta.json`, `README.md`
- Problem: gate generation does not pass `--csv`; it depends on whatever CSV is
  found in gitignored `data/`.
- Evidence: `perform_gate_test.py` calls the generator with only `--mode gate`
  and `--out-dir`. `test_gate/meta.json` expects `data/readme_demo.csv`, while
  clean clones do not include `data/`.
- Why it matters: gate can produce different cases on different machines.
- Safer direction: commit a tiny fixture under `tests/fixtures` and pass it
  explicitly to the gate generator, or have the gate create its own fixture.
- Validation:
  - Fresh clone: `py scripts/perform_gate_test.py`.
  - Check `test_gate/meta.json` uses the intended fixture.

### F27 - Implement or delete unenforced gate expectations

- Severity: Medium
- Confidence: Confirmed
- Category: reliability, test theater
- Location: `scripts/generate_cli_sweep.py`, `scripts/perform_gate_test.py`,
  `test_gate/**/cases.jsonl`
- Problem: the generator emits expectations that verifier ignores or treats as
  pass-by-exit-code.
- Evidence: config expectations such as `list_presets_output`,
  `preset_details_output`, and `validate_template_ok` return success if process
  execution succeeded; output-base/auto-name expectations are not checked.
- Why it matters: gate output overstates coverage.
- Safer direction: add an expectation registry where every emitted token is
  either enforced or explicitly listed as informational.
- Validation:
  - Add a meta-test comparing generator expectations to verifier handlers.
  - `py -m pytest tests/test_gate_runner.py -v`

### F28 - Add missing rate CLI subprocess smoke

- Severity: Medium
- Confidence: Confirmed
- Category: reliability
- Location: `tests/test_cli_runtime_behavior.py`
- Problem: share CLI has subprocess coverage, but rate CLI does not.
- Evidence: current CLI runtime tests run share CLI and direct core/privacy
  behavior. Rate analysis is mostly exercised in-process and by gate.
- Why it matters: documented gate rate failures are not locked down by a
  clean-clone unit/integration test.
- Safer direction: add a `benchmark.py rate` subprocess test using
  `tests/fixtures/mock_benchmark_data.py`.
- Validation:
  - `py -m pytest tests/test_cli_runtime_behavior.py -v`

### F29 - Test `utils/csv_validator.py`

- Severity: Medium
- Confidence: Confirmed
- Category: reliability
- Location: `utils/csv_validator.py`, `tests/`
- Problem: CSV validator is a substantial utility with no unit tests.
- Evidence: no test file imports or exercises `utils/csv_validator.py`; gate
  only invokes it for rate CSVs.
- Why it matters: the validator is a core parity tool for refactoring exports,
  but it can regress unnoticed.
- Safer direction: add a minimal Excel+CSV pass case and a deliberate drift fail
  case.
- Validation:
  - `py -m pytest tests/test_csv_validator.py -v`

### F30 - Exercise `validation_runner` directly

- Severity: Medium
- Confidence: Confirmed
- Category: reliability
- Location: `core/validation_runner.py`, `tests/test_benchmark_orchestration_helpers.py`
- Problem: orchestration tests mock validation, while the validation runner has
  no direct tests.
- Evidence: `validate_analysis_input` delegates to `run_input_validation`;
  tests patch the runner rather than asserting its real abort/warning behavior.
- Why it matters: cleanup around validation-first CLI/TUI paths lacks a direct
  safety net.
- Safer direction: add tests for insufficient peers abort and warnings-only
  proceed behavior.
- Validation:
  - `py -m pytest tests/test_validation_runner.py -v`

### F31 - Retarget private-method tests over time

- Severity: Low
- Confidence: Confirmed
- Category: reliability, testability
- Location: `tests/test_benchmark_orchestration_helpers.py`,
  `tests/test_data_loader_normalization.py`,
  `tests/test_additional_constraints_tiers.py`,
  `tests/test_report_generator_dependencies.py`, `tests/test_solvers.py`
- Problem: several tests bind to private helpers and make semantics-preserving
  refactors noisy.
- Evidence: tests import `_build_dimensional_analyzer`, `_resolve_consistency_mode`,
  `_normalize_columns`, `_evaluate_additional_constraints`,
  `_build_unique_sheet_name`, `_should_convert_rate_column`, and
  `_additional_constraints_penalty`.
- Why it matters: tests protect implementation details instead of public
  outcomes.
- Safer direction: keep them until replacement tests exist, then retarget to
  public APIs and output outcomes.
- Validation:
  - Add public-path tests before deleting any private helper tests.

### F32 - Consolidate test fixtures and args builders

- Severity: Low
- Confidence: Confirmed
- Category: duplication
- Location: `tests/fixtures/mock_benchmark_data.py`,
  `tests/test_output_artifacts.py`, `tests/test_enhanced_features.py`,
  `tests/test_benchmark_orchestration_helpers.py`
- Problem: tests duplicate 7-entity dataframes, `SimpleNamespace` builders, and
  stubs.
- Evidence: canonical mock fixture exists but many tests build parallel frames
  or args objects inline.
- Why it matters: fixture changes and run-request defaults drift across tests.
- Safer direction: promote `mock_benchmark_data.py` and shared request builders
  through `tests/conftest.py`.
- Validation:
  - `py -m pytest tests/ -v`

### F33 - Make share CSV parity explicit

- Severity: Medium
- Confidence: Confirmed
- Category: reliability
- Location: `scripts/perform_gate_test.py`, `utils/csv_validator.py`
- Problem: gate skips share CSV validation because current Excel and CSV metrics
  do not align.
- Evidence: verifier logs and continues for share balanced CSV expectations.
- Why it matters: share export refactors have only weak file/schema coverage.
- Safer direction: add a share-specific parity assertion or document the gap in
  a test with a clear skip reason.
- Validation:
  - One share `--export-balanced-csv --include-calculated` test asserting schema
    and a few deterministic values.

### F34 - Add config subcommand subprocess tests

- Severity: Low
- Confidence: Confirmed
- Category: reliability
- Location: `benchmark.py`, `scripts/perform_gate_test.py`, `tests/`
- Problem: `config list/show/validate/generate` is covered mostly by gate
  exit-code checks.
- Evidence: gate returns success for config expectations after process success.
- Why it matters: public CLI config behavior can regress while gate remains
  green.
- Safer direction: add subprocess tests for `config list` and
  `config validate config/template.yaml`, plus a temp output for
  `config generate`.
- Validation:
  - `py -m pytest tests/test_cli_config_commands.py -v`

### F35 - Stop committing stale historical docs as active guidance

- Severity: Low
- Confidence: Likely
- Category: dead weight, documentation
- Location: `docs/superpowers/plans/**`,
  `docs/CORE_LOGIC_REVIEW*.md`,
  `docs/IMPLEMENTATION_PLAN_FIXES_1_TO_4.md`,
  `docs/post_audit_sweep_results_analysis.md`,
  `docs/OPERATIONAL_GAINS.docx`
- Problem: historical plans and review docs contradict current code, line
  counts, branch state, and test counts.
- Evidence: plans reference old branches and prior failures; reviews recommend
  extractions already present; `.docx` duplicates a Markdown doc.
- Deletion class: Probably dead, confirm which docs are canonical.
- Safer direction: keep `docs/CORE_TECHNICAL_DOC.md` and
  `docs/OPERATIONAL_GAINS.md` as canonical; archive or delete stale plan/review
  files.
- Validation:
  - Search docs for unique instructions before deletion.

### F36 - Refresh `AGENTS.md`

- Severity: Medium
- Confidence: Confirmed
- Category: documentation, tooling
- Location: `AGENTS.md`
- Problem: developer guidance is stale and misleading.
- Evidence: file tree omits newer modules and lists absent `old/`; says
  `outputs/` is gitignored though committed outputs exist; gate status notes
  conflict with post-remediation artifacts; sweep command mentions a
  top-level `test_sweeps/commands.ps1` that is not present.
- Why it matters: agents and maintainers follow this file for mandatory test
  commands and architecture context.
- Safer direction: update file tree, generated artifact policy, current gate
  expectations, and canonical test commands.
- Validation:
  - `py -m pytest tests/ -v`
  - `py scripts/perform_gate_test.py`

### F37 - Normalize generated path handling

- Severity: Low
- Confidence: Confirmed
- Category: tooling
- Location: `scripts/generate_cli_sweep.py`, committed sweep/gate artifacts
- Problem: generated case JSON uses OS-native path strings, so Windows
  generation commits backslashes that are poor inputs on Linux.
- Evidence: committed `test_sweeps/meta.json` contains Windows paths.
- Safer direction: use `.as_posix()` in generated commands/artifacts or stop
  committing generated sweep cases.
- Validation:
  - Regenerate sweep on Linux and Windows-equivalent path inputs.

### F38 - Clarify SciPy optionality

- Severity: Medium
- Confidence: Confirmed
- Category: dependency, reliability
- Location: `requirements.txt`, `core/solvers/lp_solver.py`,
  `tests/test_solvers.py`
- Problem: SciPy is labeled optional, but LP is the primary strict privacy-cap
  solver path.
- Evidence: `requirements.txt` marks SciPy optional; `LPSolver` silently returns
  `None` when SciPy is unavailable; solver tests skip LP assertions without
  SciPy.
- Why it matters: an install without SciPy changes algorithm behavior rather
  than failing clearly.
- Safer direction: either make SciPy explicitly required for normal installs or
  document and test the fallback behavior as a supported mode.
- Validation:
  - `py -m pytest tests/test_solvers.py -v`
  - A no-SciPy environment smoke if fallback is intended.

### F39 - Add dev dependency/tooling manifest

- Severity: Medium
- Confidence: Confirmed
- Category: tooling
- Location: repository root, `requirements.txt`, docs
- Problem: documented test/lint/typecheck commands require undeclared tools.
- Evidence: `pytest`, `ruff`, and `mypy` are referenced in docs/AGENTS but not
  declared in a dev requirements file or `pyproject.toml`.
- Safer direction: add `requirements-dev.txt` or `pyproject.toml` optional dev
  dependencies, without changing runtime deps.
- Validation:
  - Fresh environment: install runtime + dev deps, run documented commands.

### F40 - Bring entrypoints under type/lint coverage

- Severity: Medium
- Confidence: Confirmed
- Category: tooling, reliability
- Location: `mypy.ini`, `benchmark.py`, `tui_app.py`
- Problem: strict mypy excludes the two largest user-facing entrypoint files.
- Evidence: `mypy.ini` excludes `benchmark.py` and `tui_app.py`.
- Safer direction: do not turn on strict typing all at once; add targeted type
  checks for smaller extracted modules as `benchmark.py` and TUI logic shrink.
- Validation:
  - `mypy core/ utils/`
  - Future: `mypy benchmark.py` after extraction.

## D. Deletion candidates by safety

### Safe to delete now

- `test_sweeps/**` after confirming no one expects committed generated cases.
- `tool_extension_project/**` after owner acknowledgement, or immediately if
  repository policy is active-product-only.
- `outputs/investigation/*.yaml`.
- `config/peer_auto_privacy.yaml`.
- `test_gate/config/generated_template.yaml`.
- Dead branches: `benchmark presets` handler and TUI `btn_help_presets`.
- Unused imports/constants confirmed by lint.

### Probably dead, confirm first

- `outputs/investigation_fortbrasil*/**`.
- `scripts/dump_additional_violations.py`.
- `scripts/general_dimension_constraint_check.py` and notebook.
- Historical plan/review docs under `docs/superpowers/plans/` and
  `docs/CORE_LOGIC_REVIEW*.md`.
- `docs/OPERATIONAL_GAINS.docx` if Markdown is canonical.

### Risky to delete without versioned deprecation

- `presets/*.yaml`.
- `config/template.yaml`.
- `config/privacy_rules.yaml`.
- `scripts/perform_gate_test.py`, `scripts/generate_cli_sweep.py`,
  `scripts/run_cli_sweep.py`.
- `tests/**`.
- Deprecated distortion/weight-effect wrapper methods and CLI/config aliases.
- SQL loader support until owner confirms it is not a programmatic API.

## E. Suggested PR sequence

1. Documentation-only cleanup:
   - Add/keep this audit as the canonical cleanup inventory.
   - Refresh `AGENTS.md` current tree, test commands, generated artifact policy,
     and gate status.
2. Low-risk dead code:
   - Remove unreachable `presets`/`btn_help_presets` branches.
   - Remove unused imports/constants.
3. Test honesty:
   - Commit or generate a portable gate fixture.
   - Add rate CLI subprocess smoke, csv_validator unit tests, and
     validation_runner unit tests.
   - Implement or explicitly mark all gate expectations.
4. Generated artifact cleanup:
   - Delete or ignore `test_sweeps/**`, generated templates, scratch outputs,
     and archived extension project files.
5. Break the core/CLI cycle:
   - Move balanced CSV and Excel entrypoints into core modules.
6. Orchestration cleanup:
   - Deduplicate privacy fitting and share/rate finalization.
7. Config/TUI cleanup:
   - Fix TUI override validation and consolidate field maps.
8. Analyzer/report decomposition:
   - Move impact, privacy-validation dataframe, solver-request, and subset
     search responsibilities out of `DimensionalAnalyzer`.
9. Terminology cleanup:
   - Standardize internals/docs on impact while preserving public distortion
     aliases until the announced removal version.
10. Tooling cleanup:
    - Add dev dependency manifest and gradually bring extracted entrypoint logic
      under type checks.

## F. Minimum validation by cleanup type

General code cleanup:

```bash
py -m pytest tests/ -v
py scripts/perform_gate_test.py
ruff check --select E,F --ignore E501,F401 benchmark.py core/ utils/ tui_app.py
```

Output/reporting cleanup:

```bash
py -m pytest tests/test_output_artifacts.py tests/test_report_generator_dependencies.py -v
py scripts/perform_gate_test.py
py utils/csv_validator.py <rate_report.xlsx> <rate_balanced.csv> --verbose
```

CLI/config cleanup:

```bash
py benchmark.py share --help
py benchmark.py rate --help
py benchmark.py config list
py benchmark.py config validate config/template.yaml
```

TUI cleanup:

```bash
py -m pytest tests/test_tui_contracts.py tests/test_preset_workflow.py -v
```

Manual TUI checks still matter for TUI changes:

- Load a demo CSV.
- Select a preset.
- Open Advanced settings.
- Apply overrides.
- Export overrides.
- Run share and rate analysis with validation enabled.

Generated artifact cleanup:

```bash
py scripts/perform_gate_test.py
py scripts/generate_cli_sweep.py --mode core --csv <portable_fixture.csv> --out-dir test_sweeps
py scripts/run_cli_sweep.py --sweep-dir test_sweeps --results-json test_sweeps/results.json --workers 4 --limit 20
```

## G. Do not simplify away

- Mastercard Control 3.2 privacy caps and additional participant thresholds.
- Compliance posture and acknowledgement behavior.
- Preset semantics.
- Public CLI flags and config keys without deprecation.
- Workbook/CSV schemas without parity checks.
- Warnings or comments that explain legal/compliance invariants or surprising
  privacy behavior.
- Legacy wrappers before their announced deprecation/removal version.
