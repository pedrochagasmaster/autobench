# De-Slop Audit Remediation — Exhaustive Implementation Plan

> **Source audit:** [`docs/DE_SLOP_AUDIT.md`](../../DE_SLOP_AUDIT.md) (2026-05-30).
> **Scope:** Fix **all** findings in the de-slop audit — `F01`–`F40` (prioritized findings) and `T01`–`T12` (thermo-nuclear structural review).
> **Branch convention:** one branch + PR per phase, e.g. `cursor/de-slop-phase-1-docs-30b0`.

---

## How to use this plan

This plan converts every audit finding into concrete, file-level work. It is organized into **10 phases** that follow the audit's own recommended PR sequence (audit §F) and respect dependency order: documentation and dead code first, test honesty next, then the structural refactors that depend on a green safety net.

Each **task** lists:

- **Fixes** — the audit IDs it closes.
- **Files** — exact paths to touch.
- **Steps** — concrete edits with current line anchors (verified against the current tree on `main`).
- **Validation** — the commands that must pass before the task is considered done.

The [Coverage Matrix](#coverage-matrix) at the end maps every `F`/`T` ID to its task so nothing is dropped.

### Non-negotiable invariants (audit §H — "Do not simplify away")

Every change in this plan MUST preserve:

1. Mastercard **Control 3.2** privacy caps and additional-participant thresholds (`core/privacy_validator.py`, `core/privacy_policy.py`, `config/privacy_rules.yaml`).
2. Compliance posture + acknowledgement behavior (`core/compliance.py`).
3. Preset semantics (`presets/*.yaml` — never edit casually; create new presets if needed).
4. Public CLI flags and config keys (no removal without a deprecation window).
5. Workbook sheet names and CSV export schemas (gate/`csv_validator` parity must stay green).
6. Legal/compliance comments and warnings.
7. Deprecated `distortion`/`weight-effect` wrappers until the announced removal version (`DEPRECATION_REMOVE_VERSION = "4.0"` in `core/dimensional_analyzer.py`).

**Golden rule (audit preamble):** unless a finding is explicitly a bug, all cleanup is behavior-preserving. Use characterization tests to prove parity before moving code.

### Reconciliation notes (audit vs. current tree)

A few audit statements were checked against the current code and adjusted here so steps stay accurate:

- **SQL identifier validation already exists.** `core/data_loader.py` has `_validate_sql_identifier()` (≈L279–283) and `load_from_sql_table()` already calls it. `F17` is therefore a *fate decision* (document+test vs. remove `pypyodbc`), not a security fix.
- **`PresetManager.load_preset` already aliases `get_preset`** (≈L115–117). `core/preset_workflow.py` uses `get_preset`. No `AttributeError` remains; `F04` is purely about the duplicated private-method fitting branch.
- **`OPERATIONAL_GAINS.docx` exists** in `docs/`. `F35` should decide whether the `.docx` duplicate of the `.md` is kept.
- **`old/` directory does not exist** but `AGENTS.md` file tree still lists it (`F36`).
- **`config.subset_search` already accepts both `max_attempts` and `max_tests`** in the validator's `VALID_SUBSET_SEARCH_KEYS`, and `ConfigManager._merge_config` copies `max_tests → max_attempts`. `F07`'s config consolidation must keep this back-compat.

### Baseline before starting (run once, record output)

```bash
py -m pytest tests/ -v
py scripts/perform_gate_test.py
ruff check --select E,F --ignore E501,F401 benchmark.py core/ utils/ tui_app.py
```

Per `AGENTS.md`: unit tests are expected green (≈82 passed) and the gate has three known rate cases that error under the gate runner's invocation pattern (these are addressed by Phase 3 / `F26`). Capture the exact pre-change numbers so each phase can prove no regression.

> **Cloud/Linux note:** `py` is a symlink to `python3`. Input CSVs under `data/` are gitignored; create `data/readme_demo.csv` (7 entities: 6 peers + 1 target) for smoke tests as described in `AGENTS.md`.

---

## Phase roadmap

| Phase | Theme | Findings | Risk |
|-------|-------|----------|------|
| 1 | Documentation truth | `F36`, `F35` | Low |
| 2 | Dead code & dead branches | `F15`, `F16`, `F24`, `F25` | Low |
| 3 | Test honesty & portable gate | `F26`, `F27`, `F28`, `F29`, `F30`, `F33`, `F34`, `F37`, `T07`, `T10` (partial) | Medium |
| 4 | Generated/historical artifact boundary | `F21`, `F22`, `F23`, `T11` | Low–Medium |
| 5 | Break the `core → benchmark` cycle | `F01`, `F02`, `F13`, `T05` (partial), `T12` (partial) | High |
| 6 | Consolidate run orchestration | `F03`, `F04`, `F12`, `F19`, `T01` (partial) | High |
| 7 | Config & TUI consolidation | `F07`, `F08`, `F09`, `F10`, `F11`, `T06`, `T08` | High |
| 8 | Analyzer / optimizer / report decomposition | `F05`, `F06`, `F13`, `T02`, `T03`, `T04`, `T09`, `T12` | High |
| 9 | Terminology, dependencies, deps fate | `F17`, `F18`, `F38`, `F39`, `F40`, `T01` (finish), `T05` (finish) | Medium |
| 10 | Final verification & AGENTS refresh | re-verify `F36`, full suite | Low |

Phases 1–4 are low-risk and unlock a trustworthy test/gate safety net. Phases 5–8 are the structural refactors and MUST run on top of that net. Phase 9 finishes terminology/tooling. Phase 10 re-runs everything.

---

## Phase 1 — Documentation truth

Goal: make the docs honest before changing code, so later phases can update them incrementally. Documentation-only; no code behavior changes.

### Task 1.1 — Refresh `AGENTS.md` (`F36`)

**Files:** `AGENTS.md`

**Steps:**

1. **File tree (≈L120–165):** remove the `old/` entry (directory does not exist). Add the modules introduced since the last refresh that are currently missing from the tree: `core/analysis_run.py`, `core/contracts.py`, `core/compliance.py`, `core/observability.py`, `core/output_artifacts.py`, `core/preset_comparison.py`, `core/preset_workflow.py`, `core/privacy_policy.py`, `core/excel_reports.py`, `core/global_weight_optimizer.py`, `core/category_builder.py`, `core/diagnostics_engine.py`, `core/analysis_calculator.py`, `core/validation_runner.py`, `core/constants.py`, and the `core/solvers/` package (`base_solver.py`, `lp_solver.py`, `heuristic_solver.py`).
2. **Generated-artifact policy:** the tree says `outputs/` is gitignored, but committed investigation artifacts exist. After Phase 4 deletes them, update this note to state the new policy: product code + portable fixtures tracked; generated `test_sweeps/`, gate `outputs/`, and investigation scratch ignored.
3. **Sweep command:** the doc references a top-level `test_sweeps/commands.ps1`. Replace with the actual current workflow: `py scripts/generate_cli_sweep.py --mode core --csv <fixture.csv> --out-dir test_sweeps` then `py scripts/run_cli_sweep.py --sweep-dir test_sweeps --results-json test_sweeps/results.json`.
4. **Gate status note (Cursor Cloud section):** keep accurate after Phase 3/`F26` lands; this is finalized in Phase 10.

**Validation:**

```bash
py -m pytest tests/ -v
py scripts/perform_gate_test.py
```

(Docs change cannot break these; run to confirm no accidental edits leaked into code.)

### Task 1.2 — Resolve stale historical docs (`F35`)

**Files:** `docs/superpowers/plans/**`, `docs/CORE_LOGIC_REVIEW.md`, `docs/CORE_LOGIC_REVIEW_FULL.md`, `docs/IMPLEMENTATION_PLAN_FIXES_1_TO_4.md`, `docs/post_audit_sweep_results_analysis.md`, `docs/OPERATIONAL_GAINS.docx`, `docs/OPERATIONAL_GAINS.md`

**Steps:**

1. Confirm canonical docs are `docs/CORE_TECHNICAL_DOC.md` and `docs/OPERATIONAL_GAINS.md`.
2. Move superseded plans/reviews into an explicit archive folder `docs/archive/` (preserve git history; do not silently delete content that may hold unique instructions). Candidates: `docs/CORE_LOGIC_REVIEW.md`, `docs/CORE_LOGIC_REVIEW_FULL.md`, `docs/IMPLEMENTATION_PLAN_FIXES_1_TO_4.md`, `docs/post_audit_sweep_results_analysis.md`, and the two `docs/superpowers/plans/2026-05-06-*.md` files (this remediation plan stays in `docs/superpowers/plans/`).
3. Delete `docs/OPERATIONAL_GAINS.docx` (binary duplicate of the canonical `.md`) — confirm the `.md` is content-equivalent first.
4. Add a one-line `docs/archive/README.md` stating these are historical and not authoritative.

**Validation:** `grep -rl "OPERATIONAL_GAINS.docx\|CORE_LOGIC_REVIEW" --include=*.py --include=*.md .` returns no active references (other than the archive note and this plan).

---

## Phase 2 — Dead code & dead branches

Goal: remove provably-dead code paths and orphan files. Each step is guarded by lint and a focused test.

### Task 2.1 — Remove unreachable CLI/TUI branches (`F15`)

**Files:** `benchmark.py`, `tui_app.py`

**Steps:**

1. `benchmark.py:main` (≈L1248–1251): delete the `elif args.command == 'presets':` branch. `create_parser` only registers `share`, `rate`, `config`, so this is unreachable. Keep `config list` intact (the real preset listing path). If `list_presets()` (≈L475–480) becomes unused after this, remove it too (confirm with lint in Task 2.2).
2. `tui_app.py:on_button_pressed` (≈L843–859): remove the `btn_help_presets` branch (≈L854–855). `compose` only creates `btn_preset_help` (≈L442); keep that handler.

**Validation:**

```bash
py benchmark.py config list
py -m py_compile tui_app.py
py -m pytest tests/test_tui_contracts.py -v
```

Manual TUI: click "Preset Guide" and confirm the help screen opens.

### Task 2.2 — Delete unused imports/constants in `benchmark.py` (`F16`)

**Files:** `benchmark.py`

**Steps:**

1. Run `ruff check --select F401,F811,F841 benchmark.py` to confirm the unused set. Expected unused: `import tempfile` (L20), `import gc`, `import time`, `ValidationSeverity` (L30), `ReportGenerator` (L31), `PrivacyValidator` (L32), and module constant `BEST_PRESET_MARKER` (L57).
2. Delete only names confirmed by lint. **Do not** remove `DimensionalAnalyzer` (used as a type hint) or the `core.analysis_run` helper imports that are actually referenced.
3. If `_save_workbook_with_retries` (≈L575–583) has no callers (confirmed: none in repo), defer its deletion to Phase 5 (`F13`) where Excel wrappers move wholesale, to keep this task purely lint-driven.

**Validation:**

```bash
ruff check --select F401,F811,F841 benchmark.py
py -m pytest tests/test_benchmark_orchestration_helpers.py -v
```

### Task 2.3 — Remove orphan `config/peer_auto_privacy.yaml` (`F24`)

**Files:** `config/peer_auto_privacy.yaml`

**Steps:**

1. Confirm no references: `grep -rn "peer_auto_privacy" --include=*.py --include=*.yaml --include=*.md .` should match only `docs/DE_SLOP_AUDIT.md` and this plan.
2. Delete the file. Active privacy config remains `config/privacy_rules.yaml`.

**Validation:**

```bash
py -m pytest tests/test_privacy_rules_config.py -v
py benchmark.py config validate config/template.yaml
```

### Task 2.4 — Stop committing generated gate template (`F25`)

**Files:** `test_gate/config/generated_template.yaml`, `.gitignore`

**Steps:**

1. `git rm test_gate/config/generated_template.yaml` (the gate runner deletes+regenerates it each run — `perform_gate_test.py` ≈L577–580).
2. Add `test_gate/config/generated_template.yaml` to `.gitignore` (or a broader `test_gate/**/generated_template.yaml`).

**Validation:**

```bash
py scripts/perform_gate_test.py
git status --short   # generated_template.yaml must not reappear as tracked
```

---

## Phase 3 — Test honesty & portable gate

Goal: make the gate clean-clone runnable, make expectations enforced (no test theater), and add the missing direct test coverage that protects the structural refactors in Phases 5–8. This phase is a prerequisite for the high-risk phases.

### Task 3.1 — Pin a portable gate fixture (`F26`, `F37`)

**Files:** `scripts/perform_gate_test.py`, `scripts/generate_cli_sweep.py`, `tests/fixtures/`, `test_gate/meta.json`, `AGENTS.md`

**Problem:** `perform_gate_test.py:generate_cases` (≈L28–33) calls the generator with only `--mode gate --out-dir`; CSV selection falls to `generate_cli_sweep.find_default_csv()` which scans gitignored `data/`. Clean clones have no `data/`, so the gate is non-deterministic.

**Steps:**

1. Add a tiny tracked fixture `tests/fixtures/gate_demo.csv` (reuse `tests/fixtures/mock_benchmark_data.py:build_mock_benchmark_df()` to write it deterministically, or commit a small CSV with ≥7 entities, columns `issuer_name, year_month, card_type, channel, txn_cnt, total, approved, fraud`).
2. In `perform_gate_test.py:generate_cases`, pass the fixture explicitly: `--csv <repo>/tests/fixtures/gate_demo.csv` plus `--entity-col issuer_name --entity Target --metric txn_cnt --total-col total --approved-col approved --fraud-col fraud --dimensions card_type channel --time-col year_month`.
3. In `generate_cli_sweep.py`, emit generated command paths via `Path(...).as_posix()` everywhere a path is stringified (replaces `str(path)`), so generation is OS-independent (`F37`).
4. Regenerate `test_gate/meta.json` and committed `test_gate/{share,rate,config}/cases.jsonl` from the fixture so they reference `tests/fixtures/gate_demo.csv` with forward slashes.

**Validation:**

```bash
# Simulate a clean clone: ensure data/ is empty or absent
py scripts/perform_gate_test.py
```

The gate must pass without any file in `data/`. Confirm `test_gate/meta.json` references the fixture.

### Task 3.2 — Expectation registry for gate/sweep (`F27`, `T07`)

**Files:** `scripts/generate_cli_sweep.py`, `scripts/perform_gate_test.py`, `tests/test_gate_runner.py`

**Problem:** `expectations_for_case` (generator ≈L254–306) emits tokens (`list_presets_output`, `preset_details_output`, `validate_template_ok`, `output_base=<path>`, `output_filename_auto_generated`) that `verify_case` (≈L309–568) ignores or passes by exit-code only.

**Steps:**

1. Create a single source of truth: a registry mapping each expectation token → `{verifier_fn, required_artifacts, status: "enforced" | "informational"}`. Put it in a small new module `scripts/gate_expectations.py` imported by both generator and verifier.
2. Refactor `verify_case` from its `elif` ladder into a dispatcher over the registry (`T07`: turn the 260-line function into a dispatch loop). Each token must resolve to a registered handler; an unregistered token is a hard error.
3. Implement real handlers for the currently-unenforced tokens:
   - `list_presets_output`: assert stdout contains each shipped preset name.
   - `preset_details_output`: assert stdout contains the preset name + key fields (e.g. `tolerance`).
   - `validate_template_ok`: assert stdout/exit indicates validation success.
   - `output_base=<path>` / `output_filename_auto_generated`: assert the expected output file exists at the derived path.
   Tokens that are genuinely informational must be explicitly listed as `status="informational"` in the registry (not silently skipped).
4. The generator must only emit tokens present in the registry.

**Steps (meta-test):**

5. In `tests/test_gate_runner.py`, add a meta-test asserting **every** token the generator can emit is registered, and every enforced token has a callable handler.

**Validation:**

```bash
py -m pytest tests/test_gate_runner.py -v
py scripts/perform_gate_test.py
```

### Task 3.3 — Make share CSV parity explicit (`F33`)

**Files:** `scripts/perform_gate_test.py`, `utils/csv_validator.py`, `tests/test_csv_validator.py` (new)

**Problem:** the gate skips share balanced-CSV cross-validation (`verify_case` ≈L379–384) because share Excel ("Category Mix") and share CSV ("Market Share / Impact") metrics differ.

**Steps:**

1. Decide the parity contract: either (a) add a share-specific assertion that checks the columns that *do* correspond (schema + a few deterministic values), or (b) keep the skip but convert it from an inline `continue` into an explicit, registered informational expectation (`share_csv_schema_only`) with a documented reason string.
2. Implement the chosen path. Prefer (a): assert the share CSV schema (`Dimension, Category, [time], Balanced_*` columns, and with `--include-calculated`: `Raw_*`, `*_Share_%`, `*_Impact_PP`) and a small set of deterministic values from the fixture.

**Validation:**

```bash
py -m pytest tests/test_csv_validator.py -v
py scripts/perform_gate_test.py
```

### Task 3.4 — Add `csv_validator` unit tests (`F29`)

**Files:** `utils/csv_validator.py`, `tests/test_csv_validator.py` (new)

**Steps:**

1. Add a pass case: generate a tiny Excel + matching balanced CSV from the fixture and assert the validator reports success.
2. Add a deliberate-drift fail case: perturb one CSV value and assert the validator flags a mismatch (non-zero / failed result).
3. Guard against the divide-by-zero when zero dimensions match: `total_checks == 0` must be a **failure**, not a soft skip with a `%` print on zero. Add a test for the no-match case.

**Validation:** `py -m pytest tests/test_csv_validator.py -v`

### Task 3.5 — Add rate CLI subprocess smoke (`F28`)

**Files:** `tests/test_cli_runtime_behavior.py`, `tests/fixtures/mock_benchmark_data.py`

**Steps:**

1. Add `test_mock_rate_cli_produces_expected_outputs` mirroring the existing share subprocess test but invoking `benchmark.py rate --total-col total --approved-col approved --fraud-col fraud ...` against `write_mock_benchmark_csv`.
2. Assert exit code 0, workbook exists, and (with `--debug`) diagnostic sheets are present; assert no `share`-only artifacts leak.

**Validation:** `py -m pytest tests/test_cli_runtime_behavior.py -v`

### Task 3.6 — Exercise `validation_runner` directly (`F30`)

**Files:** `core/validation_runner.py`, `tests/test_validation_runner.py` (new)

**Steps:**

1. Test the insufficient-peers abort path: input with <5 peers → `run_input_validation` produces an ERROR + abort signal.
2. Test warnings-only proceed: input with only warnings → no abort.
3. Stop mocking the runner in `tests/test_benchmark_orchestration_helpers.py` where a real assertion is now possible (retain mocks only where wiring, not behavior, is under test).

**Validation:** `py -m pytest tests/test_validation_runner.py tests/test_benchmark_orchestration_helpers.py -v`

### Task 3.7 — Add config subcommand subprocess tests (`F34`)

**Files:** `benchmark.py`, `tests/test_cli_config_commands.py` (new)

**Steps:**

1. Subprocess test for `config list`: asserts each shipped preset appears.
2. Subprocess test for `config validate config/template.yaml`: asserts success exit + message.
3. Subprocess test for `config generate <tmp>`: asserts a valid v3.0 template is written to a temp path and re-validates.
4. Subprocess test for `config show <preset>`: asserts key fields are printed.

**Validation:** `py -m pytest tests/test_cli_config_commands.py -v`

### Task 3.8 — Public-path tests before retargeting private-seam tests (`F31`, `T10`)

**Files:** `tests/test_benchmark_orchestration_helpers.py`, `tests/test_data_loader_normalization.py`, `tests/test_additional_constraints_tiers.py`, `tests/test_report_generator_dependencies.py`, `tests/test_solvers.py`

**Steps:**

1. **Do not delete** private-seam tests yet. First, add public-path equivalents so coverage never dips while Phases 5–8 move code:
   - For `_build_dimensional_analyzer` / `_resolve_consistency_mode`: add tests via `core.analysis_run.build_dimensional_analyzer` public path (already public) asserting analyzer settings from merged config.
   - For `_normalize_columns`: add a `DataLoader.load_from_csv` round-trip test asserting normalized column outcomes.
   - For `_evaluate_additional_constraints`, `_additional_constraints_penalty`: add behavior tests through the solver/optimizer public surface (`tests/test_solvers.py`, `tests/test_global_weight_optimizer_fallbacks.py`).
   - For `_build_unique_sheet_name`, `_should_convert_rate_column`: add tests asserting workbook sheet names + rate-unit conversion through `ReportGenerator.generate_report` output.
2. Mark the private-seam tests with a comment pointing to their public replacements; they will be retired in Phase 8/9 as each owner module is refactored.

**Validation:** `py -m pytest tests/ -v` (count must be ≥ baseline).

### Task 3.9 — Consolidate test fixtures/builders (`F32`)

**Files:** `tests/conftest.py` (new), `tests/fixtures/mock_benchmark_data.py`, and tests that inline 7-entity frames / `SimpleNamespace` builders.

**Steps:**

1. Promote `build_mock_benchmark_df`, `write_mock_benchmark_csv`, `write_insufficient_peer_csv` as pytest fixtures via `tests/conftest.py`.
2. Add a shared `make_run_args(**overrides)` builder (the canonical `SimpleNamespace`/`AnalysisRunRequest` arg shape) to `conftest.py`.
3. Migrate inline duplicates in `test_output_artifacts.py`, `test_enhanced_features.py`, `test_benchmark_orchestration_helpers.py` to the shared fixtures incrementally (only where it does not change the assertion).

**Validation:** `py -m pytest tests/ -v`

---

## Phase 4 — Generated/historical artifact boundary

Goal: enforce a clean repo policy (`T11`) — product code + portable fixtures tracked; generated/client-specific material ignored or archived.

### Task 4.1 — Delete non-portable `test_sweeps/` (`F21`)

**Files:** `test_sweeps/**`, `.gitignore`

**Steps:**

1. Confirm no test/code imports committed sweep cases (`grep -rn "test_sweeps" --include=*.py .`). The sweep is regenerated on demand.
2. `git rm -r test_sweeps/` (removes Windows-path, Nubank-specific `meta.json` + generated cases + `post_audit_summary.json`).
3. Add `test_sweeps/` to `.gitignore`.
4. Confirm the documented regeneration workflow (Task 1.1 step 3) produces a portable sweep from the Phase 3 fixture.

**Validation:**

```bash
py scripts/generate_cli_sweep.py --mode core --csv tests/fixtures/gate_demo.csv --out-dir test_sweeps
py scripts/run_cli_sweep.py --sweep-dir test_sweeps --results-json test_sweeps/results.json --workers 4 --limit 20
```

### Task 4.2 — Delete `tool_extension_project/` (`F22`)

**Files:** `tool_extension_project/**`, `AGENTS.md`

**Steps:**

1. Confirm no runtime imports (verified: scripts call `benchmark.py` only via subprocess; the string `tool_extension_project` appears only in `AGENTS.md` and the audit).
2. `git rm -r tool_extension_project/` (archived Nubank-specific scripts + completed plans).
3. Remove the `tool_extension_project/` reference from the `AGENTS.md` file tree.

**Validation:**

```bash
grep -rn "tool_extension_project" --include=*.py .   # no results
py -m pytest tests/ -v
```

### Task 4.3 — Remove scratch investigation outputs (`F23`)

**Files:** `outputs/investigation/*.yaml`, `outputs/investigation_fortbrasil/**`, `outputs/investigation_fortbrasil_rerun/**`, `.gitignore`

**Steps:**

1. `outputs/investigation/custom_strict_global.yaml` and `custom_per_dimension.yaml`: no references → `git rm`.
2. `outputs/investigation_fortbrasil/logic_audit_report.json` and `outputs/investigation_fortbrasil_rerun/before_after_eval.json`: these are prior validation snapshots referencing proprietary data. **Confirm-first** policy: if any are genuine golden baselines, move to `tests/fixtures/golden/` with a documented regeneration path; otherwise `git rm`.
3. Add `outputs/` to `.gitignore` (matches stated policy; only fixtures under `tests/fixtures/golden/` stay tracked).

**Validation:**

```bash
grep -rn "investigation_fortbrasil\|custom_strict_global\|custom_per_dimension" --include=*.py .   # no active refs
py -m pytest tests/ -v
```

---

## Phase 5 — Break the `core → benchmark` import cycle

Goal: `core` must import cleanly without `benchmark.py`. This is the foundation for shrinking `benchmark.py` (`T05`) and unifying output (`F13`). Requires the Phase 3 safety net.

> **Current cycle (confirmed):** `benchmark.py` imports `core.analysis_run`; `core/analysis_run.py` lazy-imports `get_balanced_metrics_df`/`export_balanced_csv` from `benchmark` (≈L728, L866, L1020, L1159); `core/output_artifacts.py` lazy-imports `generate_excel_report`/`generate_multi_rate_excel_report` from `benchmark` (≈L25).

### Task 5.1 — Extract balanced CSV/export logic into `core/balanced_export.py` (`F02`)

**Files:** `core/balanced_export.py` (new), `benchmark.py`, `core/analysis_run.py`

**Steps:**

1. Create `core/balanced_export.py` and move `get_balanced_metrics_df` (`benchmark.py` ≈L664–804) and `export_balanced_csv` (≈L807–1226) verbatim, preserving share/rate branches and CSV schemas exactly.
2. Factor the duplicated internals into small helpers within the new module (audit "safer direction"): one `_resolve_weight(dimension, peer)` resolver, one grouping helper, and separate `_build_share_rows` / `_build_rate_rows` row builders. Keep output column names byte-identical.
3. In `core/analysis_run.py`, replace the four lazy `from benchmark import ...` sites with `from core.balanced_export import get_balanced_metrics_df, export_balanced_csv` at module top.
4. In `benchmark.py`, replace the moved function bodies with thin re-export shims **only if** external callers/tests import them from `benchmark`; otherwise delete. Check `grep -rn "from benchmark import\|benchmark\.\(get_balanced_metrics_df\|export_balanced_csv\)" tests/`.

**Validation:**

```bash
py -m pytest tests/test_enhanced_features.py tests/test_output_artifacts.py -v
py scripts/perform_gate_test.py
py utils/csv_validator.py <rate_report.xlsx> <rate_balanced.csv> --verbose
```

### Task 5.2 — Route Excel generation through `core` directly (`F01`, `F13`)

**Files:** `core/output_artifacts.py`, `core/excel_reports.py`, `benchmark.py`

**Steps:**

1. In `core/output_artifacts.py`, replace the lazy `from benchmark import generate_excel_report, generate_multi_rate_excel_report` (≈L25) with `from core.excel_reports import generate_excel_report, generate_multi_rate_excel_report`. `benchmark`'s versions are already thin wrappers over `core.excel_reports`, so this removes the cycle with no behavior change.
2. Delete the now-unused `benchmark.py` wrappers `generate_excel_report` (≈L586–621), `generate_multi_rate_excel_report` (≈L624–661), and `_save_workbook_with_retries` (≈L575–583) **after** confirming no other caller (`grep -rn "generate_excel_report\|generate_multi_rate_excel_report\|_save_workbook_with_retries" benchmark.py tests/`).
3. Confirm `import core.output_artifacts` and `import core.analysis_run` now succeed in a fresh interpreter without importing `benchmark` (add a test in `tests/test_output_artifacts.py`: `import importlib; importlib.import_module("core.analysis_run")` in a subprocess that asserts `benchmark` is not in `sys.modules`).

**Validation:**

```bash
py -c "import sys; import core.analysis_run, core.output_artifacts; assert 'benchmark' not in sys.modules, sorted(sys.modules)"
py -m pytest tests/test_output_artifacts.py tests/test_benchmark_orchestration_helpers.py tests/test_report_generator_dependencies.py -v
py scripts/perform_gate_test.py
ruff check --select E,F --ignore E501,F401 benchmark.py core/ utils/ tui_app.py
```

### Task 5.3 — One output facade (`F13`, `T12` partial)

**Files:** `core/output_artifacts.py`, `core/excel_reports.py`, `core/report_generator.py`

**Steps:**

1. Make `core/output_artifacts.write_outputs` the single output facade. Collapse the shallow `core/excel_reports.py` pass-throughs into `output_artifacts` calling `ReportGenerator` directly, OR keep `excel_reports` only if the deletion test shows it concentrates complexity (it currently just packages metadata — likely inline-able). Apply the deletion test: if removing `excel_reports` re-duplicates metadata packaging across callers, keep it; otherwise inline.
2. Keep `output_format` gating (`analysis`/`publication`/`both`) and the analysis-vs-publication dispatch exactly as-is behaviorally.

**Validation:**

```bash
py -m pytest tests/test_output_artifacts.py tests/test_report_generator_dependencies.py -v
py scripts/perform_gate_test.py
```

---

## Phase 6 — Consolidate run orchestration

Goal: remove share/rate copy-paste in `core/analysis_run.py`, dedupe privacy fitting, make diagnostics flags honest, and align peer-only impact behavior. Depends on Phase 5 (no cycle).

### Task 6.1 — Public `fit_privacy_weights` helper (`F04`)

**Files:** `core/dimensional_analyzer.py` (or a new `core/weight_fitting.py`), `core/analysis_run.py`, `core/preset_comparison.py`

**Problem:** the `consistent_weights` branch is duplicated in `execute_share_run` (≈L685–699), `execute_rate_run` (≈L972–986), and `preset_comparison._run_single_preset_variant` (≈L61–76), each reaching into private `_build_categories` / `_get_privacy_rule` / `_solve_per_dimension_weights`.

**Steps:**

1. Add a public method `DimensionalAnalyzer.fit_privacy_weights(df, metric_col, dimensions)` that internally chooses global vs per-dimension based on `self.consistent_weights` (moving the private-method orchestration inside the analyzer).
2. Replace all three call sites with `analyzer.fit_privacy_weights(...)`.
3. Keep the public attributes (`global_weights`, `per_dimension_weights`, `weight_methods`, …) set exactly as before so downstream readers are unaffected.

**Validation:**

```bash
py -m pytest tests/test_enhanced_features.py tests/test_global_weight_optimizer_fallbacks.py -v
py scripts/perform_gate_test.py
```

### Task 6.2 — Extract a common run pipeline (`F03`, `T01` partial)

**Files:** `core/analysis_run.py`

**Problem:** `execute_share_run` (≈L626–895) and `execute_rate_run` (≈L898–1190) share an identical 18-step skeleton with metric-specific branches inline.

**Steps:**

1. Introduce a small `AnalysisModeSpec` (the seed of `T01`) capturing per-mode behavior: required metric columns, a metric-validation callback, a result-calculation callback (`analyze_dimension_share` vs the rate-type loop over `analyze_dimension_rate`), an impact callback (`calculate_share_impact` vs `calculate_rate_impact`), and the metadata keys unique to each mode.
2. Write one `_execute_run(request, mode_spec, logger)` implementing the shared skeleton (config build, compliance preconditions, output settings, data prep, validation, target/dimension resolution, analyzer build, `fit_privacy_weights`, analysis loop via callback, secondary metrics, metadata assembly, diagnostics, preset comparison, impact via callback, artifacts, `write_outputs`, CSV export, report paths, audit log).
3. Reduce `execute_share_run` / `execute_rate_run` to building their `AnalysisModeSpec` and delegating to `_execute_run`. Keep them as public entry points (`benchmark.py` and tests import them).
4. This is the **partial** `T01`: the spec lives in `analysis_run.py` for now; Phase 9 extends it to parser/TUI/sweep consumers.

**Validation:**

```bash
py -m pytest tests/test_benchmark_orchestration_helpers.py tests/test_output_artifacts.py tests/test_cli_runtime_behavior.py -v
py scripts/perform_gate_test.py
```

Smoke: one share and one rate CLI run with `--export-balanced-csv --debug` and confirm identical sheet/CSV outputs to pre-change (capture before/after workbook sheet lists).

### Task 6.3 — Make diagnostics flags honest (`F12`)

**Files:** `core/analysis_run.py`

**Problem:** `collect_run_diagnostics` (≈L413–511) accepts `include_privacy_validation` and `export_csv` but never reads them; it always builds the privacy-validation DataFrame and method breakdown.

**Steps:**

1. Gate the privacy-validation DataFrame + method breakdown construction on `include_privacy_validation or debug_mode or <output needs the sheet>`. Build only what the requested output requires.
2. Remove the `export_csv` parameter entirely if it has no effect (confirm CSV export is fully handled after `write_outputs` at call sites L784/L1069 — it is), updating both call sites.
3. Add a test: one run with privacy validation off → no privacy-validation DataFrame built (assert via spy/log); one with `--debug` → built.

**Validation:**

```bash
py -m pytest tests/test_benchmark_orchestration_helpers.py -v
```

Smoke: compare workbook sheets for `--debug` vs no-debug runs.

### Task 6.4 — Clarify peer-only impact behavior (`F19`)

**Files:** `core/analysis_run.py`

**Problem:** share impact is gated on `output_settings['include_impact_summary'] and resolved_entity` (≈L819); rate impact only checks `include_impact_summary` (≈L1106). So peer-only `--analyze-impact` silently omits impact for share but produces it for rate.

**Steps:**

1. Decide intended behavior (the `AnalysisModeSpec` impact callback is the natural home). Recommended: align both — peer-only impact is computed when the mode supports a peer-only impact definition; if share peer-only impact is undefined, log an explicit INFO ("impact skipped: peer-only share has no target to compare") rather than silently omitting.
2. Implement the chosen behavior consistently across modes and document it in a code comment + `docs/CORE_TECHNICAL_DOC.md`.

**Validation:** peer-only share and peer-only rate smoke runs with `--analyze-impact`; assert documented behavior (sheet present/absent + log line).

---

## Phase 7 — Config & TUI consolidation

Goal: fix the broken TUI advanced-override path, remove mirrored field maps, stop silent widget failures, and reduce double validation. Establish one typed settings boundary (`T08`) used by config/TUI/analyzer.

### Task 7.1 — One typed `ResolvedConfig`/settings object (`F07`, `T08`)

**Files:** `utils/config_manager.py`, `core/analysis_run.py`, `core/contracts.py`

**Problem:** optimization/config fields are hand-mapped across `_get_default_config`, `_apply_cli_overrides`, `build_dimensional_analyzer`, `SolverRequest`, and TUI advanced fields.

**Steps:**

1. Add a typed `ResolvedConfig` dataclass (nested typed sections: `bounds`, `linear_programming`, `subset_search`, `constraints`, `bayesian`, `analysis`, `output`) produced once from the merged `ConfigManager` dict after CLI/preset/file resolution.
2. Make `build_dimensional_analyzer` consume `ResolvedConfig` instead of repeatedly calling `config.get(section, key, default=...)`. The edges (CLI parsing, preset YAML, TUI widgets) stay flexible; core sees only the typed object.
3. Keep `max_tests → max_attempts` back-compat in `_merge_config` so existing presets remain valid (do not break the reconciliation note).
4. This is incremental: introduce `ResolvedConfig` and migrate `build_dimensional_analyzer` first; later migrate `SolverRequest` building (Phase 8 `F06`) to read from it.

**Validation:**

```bash
py -m pytest tests/test_preset_validation.py tests/test_privacy_rules_config.py -v
py benchmark.py config validate config/template.yaml
```

### Task 7.2 — Fix TUI advanced override validation (`F08`)

**Files:** `tui_app.py`, `core/preset_workflow.py`, `utils/validators.py`

**Problem:** `apply_advanced_overrides` (≈L965–1086) writes `{"version": "tui-override"}` with no `compliance_posture`; `ConfigValidator` requires version `"3.0"` and a valid `compliance_posture`. Any TUI advanced override that is loaded as a config will be rejected.

**Steps:**

1. Decide the contract. Recommended (least surprising): emit a **valid partial v3.0 override** — write `version: "3.0"` and inherit `compliance_posture` from the selected preset (the TUI already loads preset posture in `run_analysis` ≈L1169–1175). Set `compliance_posture` in the override YAML to that inherited value.
2. Alternatively, introduce an explicit partial-override loading path in `ConfigManager`/`validators` that accepts override fragments without the full required-field set, and route TUI overrides through it. (More code; only choose if posture inheritance is undesirable.)
3. Move the YAML assembly into `core/preset_workflow.py` (e.g. `write_override_file(data, *, posture)`) so it can be unit-tested without the TUI.

**Validation:**

```bash
py -m pytest tests/test_preset_workflow.py tests/test_tui_contracts.py -v
```

Add a unit test: `PresetWorkflow.write_override_file(...)` output passes `ConfigManager(config_file=override, preset=...)`. Manual TUI: load preset → edit advanced → apply overrides → run with demo CSV.

### Task 7.3 — Single TUI advanced field map (`F09`)

**Files:** `tui_app.py`

**Problem:** `update_advanced_parameters` (≈L732–823, load) and `apply_advanced_overrides` (≈L965–1086, save) mirror the same widget↔YAML map by hand.

**Steps:**

1. Define one declarative field map (list of `{widget_id, config_path, kind: input|checkbox, parser, formatter}`) as a class attribute.
2. Drive both load (populate widgets) and save (collect values) from that single map. Keep the `max_attempts`/`max_tests` dual-read behavior (≈L798–801) via the parser entry.

**Validation:**

```bash
py -m pytest tests/test_tui_contracts.py tests/test_preset_workflow.py -v
```

Manual TUI round trip: preset → edit advanced → export YAML → `py benchmark.py config validate <exported>`.

### Task 7.4 — Stop silent TUI widget failures (`F10`)

**Files:** `tui_app.py`

**Problem:** `safe_set_input`, `safe_set_checkbox`, `get_input`, `get_bool` swallow all exceptions and return defaults; a renamed widget ID becomes a silent config change.

**Steps:**

1. Narrow the `except Exception` to the specific Textual widget-lookup exception (`textual.css.query.NoMatches`).
2. On a missing widget, log a WARNING and `self.notify(...)` with the offending widget ID instead of silently returning `""`/`False`.
3. Add an app-level/unit test asserting a missing field ID is surfaced (e.g. via captured log/notify), not swallowed.

**Validation:** `py -m pytest tests/test_tui_contracts.py -v` + manual advanced-settings smoke.

### Task 7.5 — Avoid double validation in TUI runs (`F11`)

**Files:** `tui_app.py`, `core/analysis_run.py`

**Problem:** the TUI validation-first flow runs `build_run_config`, `prepare_run_data`, `resolve_dimensions`, `validate_analysis_input` (≈L1229–1250), then passes `saved_df` to `execute_run`, which rebuilds config and revalidates.

**Steps:**

1. Pass the already-prepared dataset + validation result into `execute_run` (e.g. via a `PreparedDataset` on the request, or a `validation_already_done=True` marker when a preloaded `df` is supplied).
2. In `_execute_run` (Phase 6), skip re-validation when a completed validation result is provided. Keep CLI behavior unchanged (CLI still validates once).

**Validation:**

```bash
py -m pytest tests/test_tui_contracts.py -v
```

Manual TUI run with validation-warnings modal; confirm data is loaded/validated once (log shows a single load).

---

## Phase 8 — Analyzer / optimizer / report decomposition

Goal: shrink the god object and the 500-line optimizer method, replace mutable side-effects with a result object, type the metadata bag, and collapse the dual solver API. Highest risk — requires characterization tests first.

### Task 8.1 — `WeightingResult` instead of mutable analyzer side-effects (`T02`)

**Files:** `core/global_weight_optimizer.py`, `core/dimensional_analyzer.py`, `core/analysis_run.py`, `core/output_artifacts.py`, `core/contracts.py`

**Problem:** weight fitting mutates ~15 analyzer attributes (`global_weights`, `per_dimension_weights`, `weight_methods`, `last_lp_stats`, `subset_search_results`, `rank_changes_df`, `structural_summary_df`, `structural_detail_df`, `removed_dimensions`, …); later phases harvest them via `getattr`/`hasattr`.

**Steps:**

1. **Characterization tests first:** capture current `global_weights`, `per_dimension_weights`, `weight_methods`, `rank_changes_df`, and structural DataFrames for the mock fixture (golden values) in `tests/test_global_weight_optimizer_fallbacks.py`.
2. Define a `WeightingResult` dataclass in `core/contracts.py`: `global_weights`, `per_dimension_weights`, `weight_methods`, `last_lp_stats`, `privacy_rule_name`, `removed_dimensions`, `global_dimensions_used`, `rank_changes_df`, `structural_summary_df`, `structural_detail_df`, `subset_search_results`, `compliance_blocked_reason`.
3. Have `GlobalWeightOptimizer.calculate_global_privacy_weights` **return** a `WeightingResult`. For backward compatibility, the analyzer still stores the fields (so existing readers keep working), but `_execute_run` passes the `WeightingResult` explicitly to diagnostics/output.
4. Migrate `collect_run_diagnostics` and output paths to read from the passed `WeightingResult` rather than `getattr(analyzer, ...)`.

**Validation:**

```bash
py -m pytest tests/test_solvers.py tests/test_global_weight_optimizer_fallbacks.py -v
py scripts/perform_gate_test.py
```

Golden values from step 1 must be unchanged.

### Task 8.2 — Split the 500-line optimizer method (`T03`, `F05` partial)

**Files:** `core/global_weight_optimizer.py`

**Problem:** `calculate_global_privacy_weights` (≈L94–605) owns category building, rule selection, insufficient-peer blocking, LP attempts, slack handling, subset search, fallback, final-state assignment, and post-validation re-weighting.

**Steps:**

1. With Task 8.1's golden tests green, split into phase methods returning small objects: `build_weighting_problem(...)`, `solve_full_problem(...)`, `decide_subset_fallback(...)`, `solve_removed_dimensions(...)`, `assemble_weighting_result(...)`, and a `post_validate_and_correct(...)` for the violation re-weight tail (≈L375–605).
2. Keep the public method as a thin orchestrator calling the phases in order. No control-flow/behavior change — the golden tests enforce this.

**Validation:**

```bash
py -m pytest tests/test_global_weight_optimizer_fallbacks.py tests/test_solvers.py -v
py scripts/perform_gate_test.py
```

### Task 8.3 — Shrink `DimensionalAnalyzer` (`F05`)

**Files:** `core/dimensional_analyzer.py`, new `core/impact_calculator.py`, `core/privacy_validation_builder.py`, `core/subset_search.py`

**Problem:** the analyzer (2108 lines) still owns impact math, privacy-validation DataFrame construction, subset search, per-dimension solving, and solver-request building.

**Steps (move, do not rewrite — preserve public method signatures on the analyzer as thin delegates):**

1. Move impact math (`calculate_share_impact` ≈L1683–1821, `calculate_rate_impact` ≈L1837–1963, `calculate_impact_summary` ≈L1982–2097, `_calculate_share_metrics`, `_calculate_rate_metrics`, `_weighted_percentile`) into `core/impact_calculator.py`; analyzer methods delegate.
2. Move `build_privacy_validation_dataframe` (≈L1436–1681) into `core/privacy_validation_builder.py`.
3. Move `_search_largest_feasible_subset` (≈L724–903) into `core/subset_search.py`.
4. Keep deprecated wrappers (`calculate_share_distortion`, `calculate_rate_weight_effect`, `calculate_distortion_summary`, `calculate_global_weights`) in place until v4 (`F18`/`F38` rule).

**Validation:**

```bash
py -m pytest tests/test_solvers.py tests/test_global_weight_optimizer_fallbacks.py tests/test_cli_runtime_behavior.py -v
py scripts/perform_gate_test.py
```

### Task 8.4 — One `SolverRequest` builder (`F06`)

**Files:** `core/contracts.py` (or new `core/solver_request_builder.py`), `core/dimensional_analyzer.py`, `core/global_weight_optimizer.py`

**Problem:** LP/heuristic `SolverRequest` builders are duplicated: `dimensional_analyzer._build_lp_request`/`_build_heuristic_request` (≈L505–568) and `global_weight_optimizer._build_lp_request`/`_build_heuristic_request` (≈L27–92). Also, `SolverRequest` dataclass defaults diverge from analyzer defaults (e.g. `min_peer_count_for_constraints` 6 vs 4).

**Steps:**

1. Create a single `SolverRequestBuilder` (or `build_lp_request(settings)` / `build_heuristic_request(settings)` functions) that reads from the Phase-7 `ResolvedConfig`/analyzer-settings object.
2. Replace all four builder methods with calls to the shared builder.
3. Reconcile the diverging `SolverRequest` dataclass defaults with the analyzer's real defaults (document the canonical values; ensure no behavior change for the configured paths — covered by solver tests).

**Validation:**

```bash
py -m pytest tests/test_solvers.py tests/test_global_weight_optimizer_fallbacks.py -v
```

### Task 8.5 — Type the metadata bag (`T04`)

**Files:** `core/contracts.py`, `core/analysis_run.py`, `core/output_artifacts.py`, `core/report_generator.py`

**Problem:** `AnalysisArtifacts.metadata` is an untyped dict carrying run facts, output options, compliance summary, diagnostics, DataFrame refs, and `analyzer_ref`.

**Steps:**

1. Split metadata into typed dataclasses: `RunSummary`, `ComplianceSummary` (exists in `core/compliance.py` — reuse), `DiagnosticFrames`, `OutputSettings`, `AuditLogPayload`.
2. Build these typed objects in `_execute_run`; convert to the workbook metadata dict only at the final `ReportGenerator` boundary (keep the existing string-keyed dict as the *rendering* format, not the transport format).
3. Report tests assert typed fields before Excel serialization.

**Validation:**

```bash
py -m pytest tests/test_output_artifacts.py tests/test_report_generator_dependencies.py -v
py scripts/perform_gate_test.py
```

### Task 8.6 — Collapse dual solver API (`T09`)

**Files:** `core/solvers/base_solver.py`, `core/solvers/lp_solver.py`, `core/solvers/heuristic_solver.py`

**Problem:** `PrivacySolver.solve` accepts either a `SolverRequest` or legacy kwargs via `coerce_request`.

**Steps:**

1. `grep -rn "\.solve(" core/ tests/` to enumerate every solver call site; confirm whether any pass legacy kwargs instead of a `SolverRequest`.
2. If none rely on the kwargs path: make `solve(request: SolverRequest)` the only signature; drop `coerce_request`/`build_request` from the abstract interface (or keep one adapter outside the solver package if an external caller needs it).
3. Update `tests/test_solvers.py` to construct `SolverRequest` objects (via the Phase-8.4 builder).

**Validation:** `py -m pytest tests/test_solvers.py -v`

### Task 8.7 — Split report formatter vs policy (`T12`)

**Files:** `core/report_generator.py`, `core/output_artifacts.py`, `core/excel_reports.py`

**Problem:** `ReportGenerator` (828 lines) mixes workbook formatting, publication policy, diagnostic allow-lists, rate-unit conversion, metadata unpacking, and sheet construction; `generate_publication_workbook` is ≈173 lines.

**Steps:**

1. Separate a report-content model (what sheets/columns to emit, driven by `OutputSettings` from Task 8.5) from low-level Excel formatting helpers.
2. Split analysis-workbook rendering from publication-workbook rendering; keep publication allow-list policy out of the low-level sheet writer.
3. No sheet name/schema changes (gate + `csv_validator` enforce parity).

**Validation:**

```bash
py -m pytest tests/test_output_artifacts.py tests/test_report_generator_dependencies.py -v
py scripts/perform_gate_test.py
```

---

## Phase 9 — Terminology, dependencies, deps fate, finish structural specs

### Task 9.1 — Finish impact vs. distortion terminology (`F18`, `F38`)

**Files:** `benchmark.py`, `utils/config_manager.py`, `core/dimensional_analyzer.py`, `core/preset_comparison.py`, `core/report_generator.py`, `tui_app.py`

**Steps:**

1. Internals/docs/UI labels standardize on **impact**. Keep public deprecated aliases: CLI `--analyze-distortion` (alias of `--analyze-impact`), config `analyze_distortion` mapping, deprecated wrapper methods, and `Distortion_PP`/`*_Weight_Effect_PP` fallback columns — until v4.
2. Rename the TUI widget label to "Analyze impact" (already labeled so at ≈L449) but the widget **ID** stays `analyze_distortion` for now to avoid breaking the field map; add a TODO referencing the v4 removal. (Renaming the ID is a public-ish contract via tests — defer to v4.)
3. Ensure deprecation wording is consistent in `--help` for both `--analyze-distortion` occurrences (share ≈L232, rate ≈L329).

**Validation:**

```bash
py -m pytest tests/test_legacy_wrappers.py tests/test_enhanced_features.py -v
py benchmark.py share --help    # check deprecation wording
py benchmark.py rate --help
```

### Task 9.2 — Reduce parser duplication (`F14`, `T01` finish)

**Files:** `benchmark.py`

**Steps:**

1. Extract `add_common_run_flags(parser, mode)` covering the flags duplicated between share (≈L168–256) and rate (≈L261–358): `--csv`, `--entity`, `--entity-col`, `--output`, dimension group, `--time-col`, `--config`, `--preset`, `--compliance-posture`, `--acknowledge-accuracy-first`, `--debug`, `--log-level`, `--per-dimension-weights`, `--export-balanced-csv`, `--compare-presets`, `--analyze-impact`/`--analyze-distortion`, validate-input pair, `--output-format`/`--publication-format`, `--include-calculated`, subset-search flags.
2. Keep mode-only flags explicit: share `--metric` (required) + `--secondary-metrics`; rate `--total-col` (required), `--approved-col`, `--fraud-col`, `--secondary-metrics`, `--fraud-in-bps`/`--no-fraud-in-bps`.
3. Drive the parser from the `AnalysisModeSpec` introduced in Phase 6 to complete `T01` (parser, run execution, and — where feasible — sweep generation consume one mode contract). Sweep generator (`scripts/generate_cli_sweep.py`) share/rate construction can read the same spec for required columns.

**Validation:**

```bash
py benchmark.py share --help
py benchmark.py rate --help
py -m pytest tests/test_cli_runtime_behavior.py -v
py scripts/perform_gate_test.py
```

### Task 9.3 — Decide SQL support fate (`F17`)

**Files:** `core/data_loader.py`, `utils/config_manager.py`, `requirements.txt`, docs

**Steps (pick one, document the decision):**

- **Keep as programmatic API:** document SQL loading (`load_from_sql_query`/`load_from_sql_table`) in `docs/CORE_TECHNICAL_DOC.md` as a supported API, and add a mock-connection unit test (`tests/test_data_loader_sql.py`) that patches `ConfigManager.get_sql_connection` and asserts `_validate_sql_identifier` rejects unsafe names and accepts safe ones.
- **Remove:** delete the SQL branches in `load_data` (≈L115–136), `load_from_sql_query` (≈L206–244), `load_from_sql_table` (≈L246–277), `_validate_sql_identifier`, and `ConfigManager.get_sql_connection`; drop `pypyodbc` from `requirements.txt`.

Recommended: **keep + test** (the validator already exists and removal is a bigger compatibility decision needing owner input).

**Validation:** `py -m pytest tests/ -v` (and the new SQL test if kept).

### Task 9.4 — Clarify SciPy optionality (`F38`)

**Files:** `requirements.txt`, `core/solvers/lp_solver.py`, `core/solvers/heuristic_solver.py`, `tests/test_solvers.py`, docs

**Problem:** SciPy is labeled optional, but `LPSolver.solve` returns `None` without it (≈L46–48) — silently changing algorithm behavior — and it is the primary strict privacy-cap solver.

**Steps (pick one, document):**

- **Make required (recommended):** remove the "optional" comment in `requirements.txt`; on missing SciPy, raise a clear error at solver construction rather than returning `None` mid-run.
- **Support fallback explicitly:** document the no-SciPy mode as a supported degraded mode and add a test that asserts the documented fallback behavior (currently solver tests skip LP assertions without SciPy).

**Validation:**

```bash
py -m pytest tests/test_solvers.py -v
```

### Task 9.5 — Add dev dependency/tooling manifest (`F39`)

**Files:** `requirements-dev.txt` (new) or `pyproject.toml` (new), docs/`AGENTS.md`

**Steps:**

1. Add `requirements-dev.txt` declaring `pytest`, `ruff`, `mypy` with version floors (do not touch runtime `requirements.txt`).
2. Document `pip install -r requirements.txt -r requirements-dev.txt` in `AGENTS.md`/`README.md` before the documented test/lint/typecheck commands.

**Validation:** fresh venv → install runtime + dev → run `py -m pytest`, `ruff check`, `mypy core/ utils/`.

### Task 9.6 — Bring extracted modules under type/lint coverage (`F40`)

**Files:** `mypy.ini`

**Steps:**

1. Keep `benchmark.py`/`tui_app.py` excluded from strict mypy for now (still large), but add targeted type checks for the small modules extracted in Phases 5–8 (`core/balanced_export.py`, `core/impact_calculator.py`, `core/privacy_validation_builder.py`, `core/subset_search.py`, `core/solver_request_builder.py`). Ensure they pass `mypy`.
2. After `benchmark.py` shrinks (Phase 5/9), revisit removing its mypy exclusion in a follow-up.

**Validation:**

```bash
mypy core/ utils/
```

---

## Phase 10 — Final verification & docs refresh

### Task 10.1 — Full-suite verification

**Steps:**

1. `py -m pytest tests/ -v` — all pass; count ≥ baseline + new tests from Phase 3.
2. `py scripts/perform_gate_test.py` — clean-clone runnable (no `data/`), all enforced expectations pass.
3. `ruff check --select E,F --ignore E501,F401 benchmark.py core/ utils/ tui_app.py` — no `E`/`F` violations.
4. `mypy core/ utils/` — clean.
5. Smoke: `py benchmark.py share ... --output-format both --export-balanced-csv --debug` and one rate run; diff workbook sheet lists and CSV schemas against the pre-Phase-5 captures (must be identical).

### Task 10.2 — Finalize `AGENTS.md` and `docs/CORE_TECHNICAL_DOC.md` (`F36` finish)

**Steps:**

1. Update the AGENTS.md Cursor Cloud testing note with the new pass/fail counts and gate status.
2. Update the file tree to reflect all modules created/moved by Phases 5–8.
3. Reconcile `docs/CORE_TECHNICAL_DOC.md` output-sheet list and peer-only impact behavior (`F19`) with actual generated sheets.

**Validation:** `py -m pytest tests/ -v && py scripts/perform_gate_test.py`

---

## Coverage Matrix

Every audit finding maps to at least one task.

| Audit ID | Title | Task(s) |
|----------|-------|---------|
| F01 | Break `core -> benchmark` imports | 5.1, 5.2 |
| F02 | Move balanced CSV/export out of `benchmark.py` | 5.1 |
| F03 | Consolidate share/rate orchestration | 6.2 |
| F04 | Deduplicate privacy weight fitting | 6.1 |
| F05 | Shrink `DimensionalAnalyzer` | 8.3 |
| F06 | Replace duplicated solver request builders | 8.4 |
| F07 | Collapse config mapping sprawl | 7.1 |
| F08 | Fix TUI advanced override validation | 7.2 |
| F09 | Remove TUI advanced field mirror mapping | 7.3 |
| F10 | Stop silent TUI widget failures | 7.4 |
| F11 | Avoid double validation in TUI runs | 7.5 |
| F12 | Make diagnostics flags honest | 6.3 |
| F13 | Unify report/output modules | 5.2, 5.3, 8.7 |
| F14 | Reduce parser duplication | 9.2 |
| F15 | Remove unreachable CLI/TUI branches | 2.1 |
| F16 | Delete unused imports/constants in `benchmark.py` | 2.2 |
| F17 | Decide SQL support fate | 9.3 |
| F18 | Finish impact vs distortion terminology | 9.1 |
| F19 | Clarify peer-only impact behavior | 6.4, 10.2 |
| F20 | Make broad exception handling actionable | 6.3, 7.4, 3.2 (gate), 9.3 |
| F21 | Delete non-portable `test_sweeps/` | 4.1 |
| F22 | Delete `tool_extension_project/` | 4.2 |
| F23 | Remove scratch investigation outputs | 4.3 |
| F24 | Remove orphan `config/peer_auto_privacy.yaml` | 2.3 |
| F25 | Clean generated gate artifacts | 2.4 |
| F26 | Pin gate fixture, clean-clone runnable | 3.1 |
| F27 | Implement/delete unenforced gate expectations | 3.2 |
| F28 | Add missing rate CLI subprocess smoke | 3.5 |
| F29 | Test `utils/csv_validator.py` | 3.4 |
| F30 | Exercise `validation_runner` directly | 3.6 |
| F31 | Retarget private-method tests over time | 3.8 |
| F32 | Consolidate test fixtures and args builders | 3.9 |
| F33 | Make share CSV parity explicit | 3.3 |
| F34 | Add config subcommand subprocess tests | 3.7 |
| F35 | Stop committing stale historical docs | 1.2 |
| F36 | Refresh `AGENTS.md` | 1.1, 10.2 |
| F37 | Normalize generated path handling | 3.1 |
| F38 | Clarify SciPy optionality | 9.4 |
| F39 | Add dev dependency/tooling manifest | 9.5 |
| F40 | Bring entrypoints under type/lint coverage | 9.6 |
| T01 | `AnalysisMode` model | 6.2 (seed), 9.2 (finish) |
| T02 | `WeightingResult` instead of mutable side-effects | 8.1 |
| T03 | Split 500-line optimizer method | 8.2 |
| T04 | Type the metadata junk drawer | 8.5 |
| T05 | `benchmark.py` < 1k lines | 5.1, 5.2, 9.2 (cumulative) |
| T06 | TUI form model, not procedural script | 7.3, 7.4 |
| T07 | Gate/sweep expectation model | 3.2 |
| T08 | One config schema boundary | 7.1 |
| T09 | Solvers stop dual interface | 8.6 |
| T10 | Stop blessing private seams before refactors | 3.8 |
| T11 | Repository boundary for generated/client material | 4.1, 4.2, 4.3 |
| T12 | Report formatter vs policy split | 8.7, 5.3 |

### `F20` note (broad exception handling)

`F20` is cross-cutting and addressed wherever broad `except Exception` blocks live, narrowing each to the expected failure mode and adding boundary-level `exc_info=True` only at user-facing returns:

- `benchmark.py` preset help / parser preset choices → 2.x + 9.2.
- `core/data_loader.py` config parsing fallback → 9.3.
- `core/preset_comparison.py` failure-to-status conversion → 6.1.
- `tui_app.py` helper lookups → 7.4.
- `scripts/perform_gate_test.py` (15 broad blocks) → 3.2.

Each touched block gets a focused test per the audit's `F20` validation list (missing preset directory, invalid advanced config, failed preset comparison).

---

## Risk register

| Risk | Mitigation |
|------|------------|
| Refactor silently changes weights/compliance output | Characterization/golden tests **before** moving code (Tasks 8.1–8.2); gate parity (`csv_validator`) on every phase. |
| Removing `benchmark.py` wrappers breaks an external import | Grep tests + repo for imports before deleting; keep thin shims if any caller exists. |
| Deleting `test_sweeps/`/`outputs/` loses a real golden baseline | Confirm-first for FortBrasil JSONs; move genuine baselines to `tests/fixtures/golden/`. |
| TUI override change breaks the advanced path | Unit-test `write_override_file` + `ConfigManager` load; manual TUI smoke. |
| Touching presets violates "never edit presets casually" | This plan does **not** edit `presets/*.yaml`; config consolidation keeps `max_tests`/`max_attempts` back-compat. |
| Privacy semantics regressions | Phase 8 never touches `privacy_validator`/`privacy_policy` rule logic; only moves callers. Control 3.2 caps and thresholds are invariant (§H). |

---

## Suggested branch/PR sequence

1. `cursor/de-slop-phase-1-docs-30b0` — Phase 1.
2. `cursor/de-slop-phase-2-deadcode-30b0` — Phase 2.
3. `cursor/de-slop-phase-3-test-honesty-30b0` — Phase 3.
4. `cursor/de-slop-phase-4-artifacts-30b0` — Phase 4.
5. `cursor/de-slop-phase-5-import-cycle-30b0` — Phase 5.
6. `cursor/de-slop-phase-6-orchestration-30b0` — Phase 6.
7. `cursor/de-slop-phase-7-config-tui-30b0` — Phase 7.
8. `cursor/de-slop-phase-8-decomposition-30b0` — Phase 8.
9. `cursor/de-slop-phase-9-terminology-deps-30b0` — Phase 9.
10. `cursor/de-slop-phase-10-verify-30b0` — Phase 10.

Each PR runs the full validation triad (`pytest`, gate, `ruff`) plus its task-specific checks, and must not regress the recorded baseline.
