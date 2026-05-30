# Codebase & CLI Audit Findings — Complement to GPT's Remediation Plan

> **Date:** 2026-05-06
> **Scope:** Verifies, expands and (where appropriate) corrects the audit remediation plan at `docs/superpowers/plans/2026-05-06-audit-remediation.md`.
> **Method:** Static reading of every module under `core/`, `utils/`, `scripts/`, plus runtime experimentation via the CLI against a deterministic mock dataset.
> **Branch:** `cursor/audit-complement-9ff6`

This document is companion material. It does **not** replace GPT's plan; it confirms which findings reproduce on `main`, lists additional bugs the plan misses, calls out one or two places where the plan's prescription is incomplete or wrong, and grades the plan task-by-task.

---

## 1. Summary of Validation

GPT's plan was reproduced against `main` (commit `2b48443`) using deterministic mock data at `/tmp/audit/mock.csv` (7 entities, 2 months, 3 dim combinations, P1 with 41% raw concentration). Every runtime symptom reported in the plan's **Runtime Investigation Evidence** section reproduces verbatim:

- `share --output-format both`: only `share_both.xlsx` and `share_both_balanced.csv` are produced; **no** `share_both_publication.xlsx`. Confirmed.
- `rate --output-format both`: same; **no** publication workbook. Confirmed.
- Workbook sheet list reduces to `Summary`, `Metric_*`, `Metadata` — `Peer Weights`, `Weight Methods`, `Privacy Validation` are **missing** even with `--debug`. Confirmed.
- Preloaded DataFrame is silently dropped in TUI confirmed flow (`AnalysisRunRequest.to_namespace()` does not preserve `df`). Confirmed.
- `presets/low_distortion.yaml` and `presets/strategic_consistency.yaml` fail `utils.validators.load_config()`. Confirmed.
- Insufficient-peers run (3 peers, `--no-validate-input`) silently writes a workbook with identity weights. Confirmed.
- Five unit tests fail on `main` (4 in `test_enhanced_features`, 1 in `test_solvers`). Confirmed.

Therefore the plan's diagnoses are accurate. The fixes in Tasks 1–12 are necessary and sufficient for the issues the plan enumerates.

The rest of this document focuses on findings that the plan **does not capture** or where its prescription needs an adjustment.

---

## 2. Additional Bugs Not Covered by the Plan

These are concrete defects observed during the audit. They should be merged into the plan (or implemented as a follow-up) before the remediation branch is considered "done".

### 2.1 `compliance_summary` reports `structural_infeasibility` for healthy runs (false-positive verdict)

**Severity:** High — every successful run currently emits `Compliance Verdict: structural_infeasibility` even when nothing is infeasible.

**Location:** `core/compliance.py` lines 24–41.

**Root cause:** The verdict logic is

```python
has_structural = bool(self.structural_infeasibility)
...
elif has_structural:
    compliance_verdict = "structural_infeasibility"
```

`self.structural_infeasibility` is set to the dictionary returned by `DimensionalAnalyzer.get_structural_infeasibility_summary()`, which always contains keys (`has_structural_infeasibility`, `infeasible_dimensions`, ...). A non-empty dict is truthy regardless of whether the run was actually infeasible.

**Reproduction:**

```python
from core.compliance import build_compliance_summary
struct = {'has_structural_infeasibility': False, 'infeasible_dimensions': 0,
          'infeasible_categories': 0, 'infeasible_peers': 0,
          'worst_margin_pp': 0.0, 'top_infeasible_dimension': None,
          'top_infeasible_category': None}
print(build_compliance_summary(posture='strict', structural_infeasibility=struct).to_dict())
# -> 'compliance_verdict': 'structural_infeasibility'  (WRONG)
```

The standard CLI run in §1 above prints `Compliance Verdict: structural_infeasibility` while simultaneously printing `Run Status: compliant` — the two contradict each other in the output.

**Fix:** change `has_structural` to `bool(self.structural_infeasibility) and bool(self.structural_infeasibility.get('has_structural_infeasibility'))`. Add a regression test to `tests/test_compliance_summary.py` exercising both shapes (empty dict and `has_structural_infeasibility=False`).

This bug invalidates Task 5 Step 1 of the plan as written: even after fixing the `Compliant`/`compliant` casing issue, every run will still emit a misleading verdict because the structural-infeasibility branch fires.

### 2.2 `core/preset_workflow.py` calls non-existent `PresetManager.load_preset(...)`

**Severity:** High — TUI `preset_workflow` and `core/preset_comparison.run_preset_comparison()` raise `AttributeError` whenever they execute.

**Location:**
- `core/preset_workflow.py:24` — `return self._pm.load_preset(preset_name)`
- `core/preset_comparison.py:41` — `preset_config = pm.load_preset(preset_name)`
- `utils/preset_manager.py:86` — only `get_preset()` exists; there is no `load_preset()`.

**Reproduction:**

```bash
$ py -c "from core.preset_workflow import PresetWorkflow; PresetWorkflow().load_preset_data('balanced_default')"
AttributeError: 'PresetManager' object has no attribute 'load_preset'
```

A CLI run with `--compare-presets` quietly catches the exception via the `try/except Exception as exc:` in `run_preset_comparison()` and emits `Mean_Distortion_PP=None` for every preset, so the failure surfaces only as silently empty data. See `/tmp/audit/share_compare.xlsx` Metadata sheet for the dump.

**Fix:** Either rename `PresetManager.get_preset` to `load_preset` (preferred — consistency with `list_presets`), or update the two callers to call `get_preset`. Plan Task 4 must be paired with this rename, otherwise the new "real metrics" code will still throw the same `AttributeError`.

### 2.3 `utils/csv_validator.py` crashes with `ZeroDivisionError` when no dimensions match

**Severity:** Medium — the CSV validator (used by `scripts/perform_gate_test.py` and recommended in AGENTS.md) crashes after issuing the "no matching sheet" warnings.

**Location:** `utils/csv_validator.py:570`

```python
print(f"Passed: {total_passed} ({total_passed/total_checks*100:.1f}%)")
```

When zero dimensions match, `total_checks=0`. Division by zero, traceback, exit 1.

**Reproduction:** Run the standard share CLI (which produces dimension sheets named `Metric_1_card_type`, `Metric_2_channel`) and validate against the balanced CSV (which uses `Dimension="card_type"`):

```bash
$ py utils/csv_validator.py /tmp/audit/share_both.xlsx /tmp/audit/share_both_balanced.csv --verbose
WARNING Skipping card_type: No matching Excel sheet found
WARNING Skipping channel:   No matching Excel sheet found
ZeroDivisionError: division by zero
```

**Fix:** guard the percentage prints with `if total_checks > 0`, and treat zero matched dimensions as a failure rather than a soft skip. Plan Task 9 Step 6 partially addresses the sheet-matching issue but does **not** fix the divide-by-zero; both fixes need to land together.

### 2.4 Preset metric-name drift: `subset_search.max_tests` vs `max_attempts`

**Severity:** Medium — five of six shipped presets use the legacy key `max_tests`; the validator calls it `max_attempts`. The runtime back-compat shim hides the divergence.

**Files:**
- Schema accepts only `max_attempts` (`utils/validators.py:310-312`).
- `presets/balanced_default.yaml`, `compliance_strict.yaml`, `low_distortion.yaml`, `minimal_distortion.yaml`, `research_exploratory.yaml` all set `max_tests`.
- Only `presets/strategic_consistency.yaml` sets `max_attempts` — and uses `0`, which fails the validator.
- `utils/config_manager.py:540-547` rewrites `max_tests` to `max_attempts` after merge.

**Why this matters:** `py benchmark.py config validate presets/balanced_default.yaml` returns OK only because the validator never sees `max_tests` (presets are loaded by `PresetManager` outside `load_config`). If anyone ever points `--config presets/balanced_default.yaml` at the CLI, they get `Configuration validation failed: optimization.subset_search.max_tests is unknown` (well, today it doesn't fail because the validator simply does not enforce unknown keys inside `optimization.subset_search` — see §2.5).

**Fix:** Plan Task 7 Step 1 says "remove duplicate mapping keys" in `utils/config_manager.py`, but it does not address this preset-key drift. The plan's Step 5 ("decide unknown nested-key policy") flags it but defers the decision. Recommended decision: treat `max_tests` as an officially documented legacy alias — keep the back-compat shim, add it to the validator's known-keys list, and fix the one preset that still uses `max_attempts: 0` (invalid against the validator).

### 2.5 Validator does not reject unknown nested keys (silent typo trap)

**Severity:** Medium — the schema only flags unknown keys at the **root** level (`utils/validators.py:82-85`). Inside `optimization.linear_programming`, `optimization.subset_search`, `optimization.constraints` etc., any unknown key is silently accepted. Examples that pass today:

- `lambda_penalty` in `linear_programming` (used by 3 presets but never validated).
- `volume_weighted_penalties`/`volume_weighting_exponent` in `linear_programming` (used by 3 presets).
- A typo such as `linear_programmin: {tolerance: 0.0}` in a custom config would silently get ignored at the right level and merged at the wrong one.

This compounds with §2.4. Plan Task 7 mentions it as Step 5 but does not prescribe code, so include it in the same change as §2.4.

### 2.6 `output_format='publication'` still writes the analysis workbook

**Severity:** Medium — even though the plan's Task 3 Step 5 fixes the `both` mode, the present code writes an analysis workbook regardless of `output_format`:

```bash
$ py benchmark.py share ... --output-format publication --output /tmp/audit/share_pub.xlsx
$ ls /tmp/audit/share_pub*
share_pub.xlsx           # this is the analysis workbook, NOT the publication one
share_pub_audit.log
```

`core/output_artifacts.write_outputs()` ignores `output_format` and always writes `analysis_output_file`. The plan's Step 5 prescription handles this correctly via the `_write_report(path, publication=True/False)` helper, but Step 5 currently calls `_write_report(output_file, publication=False)` for analysis and `_write_report(publication_file, publication=True)` for publication — this is fine as long as the helper actually invokes `ReportGenerator.generate_publication_workbook()` for `publication=True`. The plan's pseudocode does not show that branch; make it explicit. Today, `ReportGenerator.generate_publication_workbook()` exists (lines 593-723 of `core/report_generator.py`) but is never called from anywhere — pure dead code on `main`. The fix must wire it up.

### 2.7 Dead code: `REQUIRED_MINIMAL_SCHEMA`, `REQUIRED_FULL_SCHEMA`, `OPTIONAL_FULL_SCHEMA`

**Severity:** Low — `core/data_loader.py:62-81` defines three list-of-string class constants whose intent is "required schemas". `validate_minimal_schema()` and `validate_full_schema()` ignore them entirely and use heuristic `_is_*_like_column()` helpers. Either delete the constants or wire them in. Not in the plan.

### 2.8 Audit log includes serialised DataFrames as strings

**Severity:** Low — `audit_metadata = {key: value for key, value in metadata.items() if key != 'analyzer_ref'}` filters only the analyzer reference. Other DataFrames that get stuffed into `metadata` (e.g. `preset_comparison_df`, `impact_df`, `privacy_validation_df`) end up as `str(df)` in the audit log file. Sample from `/tmp/audit/share_compare_audit.log`:

```
preset_comparison: [{'Preset': 'balanced_default', 'Mean_Distortion_PP': None}, ...]
```

Plan Task 3 Step 7 hints at this for the Metadata sheet but not for the audit log. Apply the same compaction (`f"DataFrame rows={...} cols={...}"`) to the audit log writer in `core/analysis_run.write_audit_log()`.

### 2.9 `core/output_artifacts.py` ignores `--secondary-metrics` for `secondary_results_df` in publication output

When implementing Task 3, ensure that `secondary_results_df`, `preset_comparison_df`, `impact_df`, and `impact_summary_df` are reflected in the **publication** workbook only when they are appropriate for stakeholders (publication is supposed to be "clean, stakeholder-friendly"). The current `generate_publication_workbook()` writes only the per-metric DataFrames and an Executive Summary — it deliberately drops debug data. Decide explicitly whether each diagnostic flows to the analysis workbook only, or both. The plan does not specify.

### 2.10 `tui_app.py` calls `prepare_run_data` with stale `args` after preset-driven posture override

In the TUI confirmed branch (`tui_app.py:1269-1275`), the posture is set on the request *after* validation has already loaded the data (`tui_app.py:1166-1167`). When the user re-runs in the same session and switches between presets with different postures, the cached `df` may correspond to a previous preset's `compliance_posture`. The plan's Task 2 Step 5 handles the simpler "preserve preloaded df" issue; consider adding a note to invalidate `saved_df` when `request.preset` or `request.compliance_posture` changes. Not strictly required — but worth a paragraph in Task 10 Step 5.

### 2.11 `core/compliance.build_blocked_compliance_summary` produces inconsistent fields

When the run is blocked (`accuracy_first` posture, no acknowledgement), `build_blocked_compliance_summary()` returns a `ComplianceSummary` with default `posture/acknowledgement_given`. `to_dict()` then computes `run_status="completed_accuracy_first"` and `compliance_verdict="fully_compliant"`, even though the run was blocked before any work happened. Sample observed during low_distortion preset run:

```text
Run Status: completed_accuracy_first
Compliance Verdict: fully_compliant
Acknowledgement State: not_required
blocked: True
reason: acknowledgement required
```

That output simultaneously says the run completed AND is fully compliant AND is blocked. Add a `blocked` short-circuit in `to_dict()` (e.g. `if self.details.get('blocked'): return {...verdict='blocked'...}`). Not in the plan.

### 2.12 `_normalize_columns` is invoked twice on preloaded DataFrames

After Task 2 Step 4 lands, `prepare_run_data()` will call `data_loader._normalize_columns(df.copy())` on the already-loaded dataframe. The TUI also normalises during validation. The result is harmless (idempotent on already-normalised columns), but the plan should acknowledge that the second pass is a no-op so future maintainers don't try to "deduplicate" it. Add a comment near the call site.

### 2.13 `run_share_analysis` / `run_rate_analysis` print `Report:` empty when `output_format='publication'`

Observed earlier: when only the publication workbook is written, the CLI's success message prints `Report:` with no path because the analysis path is never set on the artifacts. Fix is implicit in Task 3 Step 3 (always assign both paths), but the plan should explicitly state that the CLI summary should print every path in `artifacts.report_paths`, not just `analysis_output_file`. See `benchmark.py` around the share/rate completion summaries (search for `Report:`).

### 2.14 `core.solvers.heuristic_solver` does not signal failure when feasibility cannot be reached

The unit test `test_heuristic_reduces_additional_constraint_penalty` fails because `result.success` is `False` even though the shares are reduced. Plan Task 6 Step 6 requires "make solver success mean post-validated success where used" — but the failing test asserts the **opposite**: that success is `True` when the additional-constraint penalty drops. These two requirements collide. Reconcile by either:

1. Updating the test to assert `optimized_penalty < baseline_penalty` and **not** assert `result.success`; or
2. Treating `success` as "L-BFGS-B converged" rather than "all caps satisfied" — preserve the current SciPy semantics and let downstream code re-check feasibility.

Pick a definition first, then implement. The plan picks definition #1 implicitly (Step 6 says "Return `success=False` when residual violations remain with `tolerance=0.0`"), which **breaks** the test as written. Either drop the test or change its assertion before merging.

---

## 3. Task-by-Task Verification of GPT's Plan

| Task | Plan summary | Verified on `main`? | Notes / corrections |
|---|---|---|---|
| 1 | Lock failures as regression tests | ✅ Each described failure reproduces. | Add tests for §2.1 (compliance verdict), §2.2 (PresetWorkflow AttributeError), §2.3 (CSV validator divide-by-zero), §2.6 (publication-only writes wrong workbook), §2.11 (blocked summary inconsistency). |
| 2 | Preserve preloaded DataFrame through CLI/TUI | ✅ `to_namespace()` drops `df`. Verified via `from core.contracts import AnalysisRunRequest; req=...; req.df='x'; req.to_namespace().df is None`. | Step 4 ("call `data_loader._normalize_columns(df.copy())`") is fine but should be guarded so it does not run on dataframes already containing canonical column names if any caller normalises in advance — currently no such caller exists, so the guard is purely defensive. |
| 3 | Implement analysis and publication output modes | ✅ `output_artifacts.write_outputs()` ignores `output_format`, `publication_output` is never set, `generate_publication_workbook()` is dead code. | Make Step 5 explicitly pass `publication=True` to `_write_report` and have `_write_report` route to `ReportGenerator.generate_publication_workbook()` for that case. Today's `generate_excel_report()` produces Metric sheets named `Metric_{i}_{name}`; CSV validator and gate runner expect `{dimension_name}` (see Task 9). Decide which side renames. |
| 4 | Replace stubbed preset comparison | ✅ Returns rows of `Mean_Distortion_PP=None`. | **Blocking dependency:** §2.2 (rename `load_preset` → `get_preset`). Without that fix, Task 4's new code will keep raising `AttributeError`. Also: Task 4 Step 6 sets `comparison_df["Mean_Distortion_PP"] = comparison_df["Mean_Impact_PP"]`, which preserves the legacy column. The `Preset Comparison` sheet writer in `report_generator.add_preset_comparison_sheet()` writes columns `Preset, Mean Distortion (PP), Max Distortion (PP), Time (s), Best`. Reconcile names in one place. |
| 5 | Fix compliance summary and `_TIME_TOTAL_` | ✅ Casing bug reproduces, `_TIME_TOTAL_` rows are absent (`int((validation_df['Dimension']=='_TIME_TOTAL_').sum()) == 0`). | **Augment with §2.1** (truthy-dict structural-infeasibility false positive) and §2.11 (blocked summary contradicts itself). |
| 6 | Harden optimizer privacy policy | ✅ Identity fallback for `rule_name=='insufficient'` is the documented current behaviour (`core/global_weight_optimizer.py:114-126`). | Reconcile with §2.14 — the chosen `success` semantics must be settled before changing `core/solvers/heuristic_solver.py`. The plan's Task 6 Step 6 and the `test_solvers.py` test currently disagree. |
| 7 | Validate configs and presets consistently | ✅ Two presets fail validation (`low_distortion`, `strategic_consistency`). Duplicate aliases confirmed by `ruff check --select F601 utils/config_manager.py` (2 errors). | **Augment with §2.4 / §2.5** (preset key drift, unknown nested-key acceptance). The plan's Step 1 only removes the duplicate aliases, but the post-merge state still allows undocumented keys. |
| 8 | Data loader safety and rate validation | ✅ `_validate_sql_identifier` does not exist; `validate_rate_input` only warns above 100% (`max_rate_deviation` defaults to 50pp). | Note that the rate-validator already errors on `numerator > denominator` (line 916). Step 3's new `impossible_mask = rates > 100.0` can rarely fire because the prior check already errors out. Recommend the impossible-rate check apply when `numerator_cols` does not include the denominator (e.g., custom rate definitions). |
| 9 | Repair gate runner and CSV validator | ✅ `cmd[3:].split()` and `command.split()` reproduce the entity-quoting bug; `verify_workbook_content`'s `error_patterns` loop short-circuits to truthy on every `df[col]` containing `#`. The fraud `pass` statements are present. | **Augment with §2.3** (divide-by-zero) and §2.6/§3 sheet-naming reconciliation. Without fixing the sheet name mismatch, the gate runner's CSV validation step will keep skipping every dimension and exiting non-zero from the validator subprocess. |
| 10 | Harden TUI non-GUI behavior | ✅ Mode comparison via `tabbed_content.active == 'share_tab'` is brittle but works. The dynamic `request.df = saved_df` only "works" because Python dataclasses accept ad-hoc attributes; `to_namespace()` then drops them. | Acceptable as-is. Add §2.10 note about preset/posture invalidation. |
| 11 | Correct documentation | ✅ `README.md:113` reads "At least 4 participants are required". `SETUP.md:32` is corrupt copy-paste. `run_tool.sh:26` uses `python` (this works in the cloud env but breaks the offline server doc). | Step 4 ("Update AGENTS testing notes") is necessary. The current AGENTS.md says "49/54 pass" — the actual count is `49 passed, 5 failed` matching exactly that figure. |
| 12 | Final verification | ✅ Lint surfaces 8 `E,F` errors (2 × F601 in config_manager, 6 × E701 in solvers). The plan's Step 2 will succeed only after the duplicate keys are removed and the colon-statements in `core/solvers/lp_solver.py` (lines 217-220) and `core/solvers/heuristic_solver.py` (lines 352-355) are split. Suggest extending Step 2 to fix those E701s explicitly, otherwise lint will keep failing post-merge. |

---

## 4. Reproducible Evidence (CLI runs against mock data)

All commands below were executed on `cursor/audit-complement-9ff6` and reproduce on `main`.

```bash
# Setup mock data (7 entities, P1 deliberately at 41% concentration)
py -c "..."  # see plan §Mock Data Generation; persisted to /tmp/audit/mock.csv

# 1. Share with --output-format both --debug --validate-input
py benchmark.py share --csv /tmp/audit/mock.csv --entity-col issuer_name --entity Target \
  --metric txn_cnt --dimensions card_type channel --time-col year_month \
  --output /tmp/audit/share_both.xlsx --output-format both --debug \
  --export-balanced-csv --include-calculated --validate-input
# Observed sheets: ['Summary', 'Metric_1_card_type', 'Metric_2_channel', 'Metadata']
# Observed files: share_both.xlsx, share_both_balanced.csv, share_both_audit.log
# MISSING:        share_both_publication.xlsx, Peer Weights, Weight Methods, Privacy Validation

# 2. Rate with --output-format both --debug --fraud-in-bps
py benchmark.py rate --csv /tmp/audit/mock.csv --entity-col issuer_name --entity Target \
  --total-col total --approved-col approved --fraud-col fraud \
  --dimensions card_type channel --time-col year_month \
  --output /tmp/audit/rate_both.xlsx --output-format both --debug --fraud-in-bps
# Observed: only rate_both.xlsx + rate_both_audit.log
# MISSING:  rate_both_publication.xlsx, diagnostic sheets

# 3. Insufficient peers, no validation -> silent identity fallback (DANGEROUS)
py benchmark.py share --csv /tmp/audit/insufficient.csv --entity Target ... --no-validate-input
# Returns 0, writes a workbook claiming Run Status: compliant.

# 4. CSV validator crash
py utils/csv_validator.py /tmp/audit/share_both.xlsx /tmp/audit/share_both_balanced.csv --verbose
# WARNING Skipping card_type / channel: No matching Excel sheet found
# ZeroDivisionError: division by zero

# 5. Compliance verdict false positive
py -c "from core.compliance import build_compliance_summary; ..."
# {'compliance_verdict': 'structural_infeasibility', 'run_status': 'compliant'}  <- contradiction

# 6. PresetWorkflow break
py -c "from core.preset_workflow import PresetWorkflow; PresetWorkflow().load_preset_data('balanced_default')"
# AttributeError: 'PresetManager' object has no attribute 'load_preset'

# 7. Compare presets via CLI -> all None
py benchmark.py share ... --compare-presets
# Metadata sheet contains the JSON dump with every Mean_Distortion_PP=null

# 8. Lint (E,F minus E501,F401,F541)
ruff check --select E,F --ignore E501,F401,F541 benchmark.py core/ utils/ tui_app.py
# 8 errors: 2 × F601 (config_manager duplicate aliases), 6 × E701 (lp_solver/heuristic_solver one-liner for-loops)

# 9. pytest baseline
py -m pytest tests/ -v
# 49 passed, 5 failed (test_publication_output_generated, test_publication_output_generated_multi_rate,
#                      test_preset_comparison_exhaustive, test_empty_dimensions_list,
#                      test_heuristic_reduces_additional_constraint_penalty)
```

---

## 5. Recommended Execution Order Adjustment

GPT's plan is mostly well-ordered, but two dependencies were missed:

1. **§2.2 (rename `load_preset` → `get_preset` in callers)** must land in or before **Task 4**, otherwise the new preset comparison code throws.
2. **§2.1 (compliance verdict structural false positive)** must land in or before **Task 5**, otherwise every passing test that asserts `compliance_verdict='fully_compliant'` will fail.
3. **§2.14 (heuristic solver success semantics)** must be settled in **Task 1 Step 6** (test rewrite) **before** Task 6 implementation — otherwise the regression tests asserted by Task 1 will be wrong from day one.

Suggested insert points:

- **New Task 4.0 (before Step 1):** "Rename `core/preset_workflow.PresetWorkflow.load_preset_data` and `core/preset_comparison.run_preset_comparison` to call `PresetManager.get_preset(...)`. Add a unit test `tests/test_preset_workflow.py::test_load_preset_data_returns_dict`."
- **New Task 5.0 (before Step 1):** "In `core/compliance.ComplianceSummary.to_dict()`, replace `bool(self.structural_infeasibility)` with `bool(self.structural_infeasibility) and bool(self.structural_infeasibility.get('has_structural_infeasibility'))`. Add a regression test for the empty-but-truthy dict case."
- **New Task 9 follow-up:** Add the divide-by-zero guard in `utils/csv_validator.main()` and treat zero matched dimensions as a hard failure (`exit 1`) rather than a soft skip.

---

## 6. Confidence Statement

After exhaustive review of every Python module under `core/`, `utils/`, and `scripts/`, plus runtime experimentation on share, rate, peer-only, target-with-time, validate-on/off, and `--compare-presets` paths, I am confident that:

- **All 12 tasks in GPT's plan are necessary.** Every plan finding reproduces.
- **GPT's plan is missing at least the 14 items in §2** (graded by severity High/Medium/Low). Most are small fixes (1–10 lines each), but §2.1, §2.2, and §2.6 are blocking — without them the post-Task-12 test suite will still fail or emit misleading verdicts.
- **One of the plan's Steps (Task 6 Step 6) directly contradicts an existing test assertion (§2.14).** This must be resolved before implementation.
- **`scripts/perform_gate_test.py` has additional latent bugs** beyond what Task 9 covers (Excel error detection and the fraud `pass` statements in particular — both are mentioned but the pre-existing destructive cleanup happens at line 531-532 *before* `generate_cases()` runs, which the plan correctly identifies).

There are no "phantom" findings in GPT's plan — every claim it makes was verified against current code.

---

## 7. Files Touched by the Audit

This complement document is read-only; it does not modify any production code or tests. The following files were exhaustively reviewed:

- Entry points: `benchmark.py`, `tui_app.py`, `run_tool.sh`, `setup_remote_env.sh`, `deploy_and_install.ps1`.
- Core: every file under `core/` including `core/solvers/`.
- Utilities: every file under `utils/`.
- Scripts: every file under `scripts/`.
- Configuration: `config/template.yaml`, `config/privacy_rules.yaml`, every preset under `presets/`.
- Tests: every file under `tests/` (49 passing, 5 failing as documented).
- Documentation: `README.md`, `SETUP.md`, `AGENTS.md`, `docs/CORE_LOGIC_REVIEW*.md`, `docs/CORE_TECHNICAL_DOC.md`, `docs/IMPLEMENTATION_PLAN_FIXES_1_TO_4.md`, the GPT plan itself.

---

## 8. Action Items (TL;DR for plan editors)

If you want to merge these findings back into GPT's plan, the minimum delta is:

1. Add §2.1 fix to **Task 5**.
2. Add §2.2 fix as **new Task 4 Step 0**.
3. Add §2.3 fix to **Task 9 Step 6**.
4. Add §2.4 + §2.5 to **Task 7 Step 5** (decide and implement).
5. Make **Task 3 Step 5** explicitly route to `ReportGenerator.generate_publication_workbook()` and reconcile sheet naming with the CSV validator's expectations (Task 9 Step 7).
6. Reconcile **Task 6 Step 6** against the existing `test_heuristic_reduces_additional_constraint_penalty` assertion (§2.14).
7. Add E701 fixes from §3 Task 12 row to **Task 12 Step 2** (or split solver one-liners during Task 6).
8. Mention §2.7 (dead schema constants), §2.8 (audit log DF strings), §2.10 (TUI cache invalidation), §2.11 (blocked summary), §2.13 (CLI Report: empty) — most are 1–3 line edits and can be batched into a dedicated cleanup task or each merged into the relevant existing task.

---

## 9. Cross-Reference With Pre-Existing `docs/` Material

GPT's plan references runtime evidence and stub-history reasoning, but does not cross-check claims against the in-tree documentation set. That documentation contains evidence which both **strengthens** and **constrains** the plan. Read these together with §2 above.

### 9.1 `docs/CORE_LOGIC_REVIEW.md` (Feb 2026 reviewer)

Documents long-standing structural concerns that the plan does not address:

- **God-class `DimensionalAnalyzer`** — 40+ ctor params, 30+ methods, ~2,062 lines today. Plan Task 6 only patches the one fallback branch; it leaves the architecture untouched. If the goal of the remediation branch includes "make tests easy to write" (Task 1), the plan should add an explicit non-goal statement: it does **not** restructure `DimensionalAnalyzer`. Otherwise reviewers will expect it.
- **Epsilon inconsistency** between `PrivacyValidator.COMPARISON_EPSILON = 1e-3` and `DimensionalAnalyzer.COMPARISON_EPSILON = 1e-6`. **Status today:** `core/constants.py` exports `COMPARISON_EPSILON = 1e-9`, and both classes import that shared constant (`PrivacyValidator` line 33, `DimensionalAnalyzer` line 22). The historical doc is now stale on this point — but the plan's Task 11 should still **delete or annotate** that Feb-2026 paragraph in `docs/CORE_LOGIC_REVIEW.md` so future reviewers don't chase a fixed bug.
- **SQL injection in `DataLoader.load_from_sql_table`** — both this doc (§3.2.1, "Critical") and GPT's plan Task 8 Step 1 flag the same defect. Cross-confirmed.
- **Sheet name truncation without collision check** (`Metric_{i+1}_{metric_name[:20]}`) — fixed in current code via `_build_unique_sheet_name()` (lines 100-114). Doc is stale on this point too. Worth flagging in Task 11.
- **Deprecated method wrappers** (`calculate_global_weights`, `calculate_share_distortion`) still present in current code (`tests/test_legacy_wrappers.py` confirms) — not in the plan. Recommend deleting in the same release.

### 9.2 `docs/CORE_LOGIC_REVIEW_FULL.md` (Jan 2026 reviewer)

Reinforces the god-class concern and adds two scalability flags the plan does not cover:

- **LP rank constraints are O(P²)** in "all" mode (`core/solvers/lp_solver.py`). For `P=100`, this generates ~5000 rank constraints. The reviewer recommends a "neighbor-only" mode. **Status today:** the constraint mode is configurable (`rank_constraints.mode = 'all' | 'neighbor'`, default `all`), but `presets/*.yaml` never set it to `neighbor`. The plan does not surface this preset gap.
- **Privacy logic duplication** between `PrivacyValidator` and `HeuristicSolver._additional_constraints_penalty`. Today `core/privacy_policy.py` exists as a facade but the heuristic solver still implements its own penalty logic and its own `_assess_additional_constraints_applicability` (lines 298-342) duplicating what `PrivacyPolicy.assess_additional_constraints` does. The plan does not consolidate these. Recommend either (a) routing the heuristic solver through `PrivacyPolicy`, or (b) explicitly documenting `PrivacyPolicy` as advisory-only.

### 9.3 `docs/CORE_TECHNICAL_DOC.md` (current ground-truth doc)

Contains assertions that contradict observed behavior on `main`:

- **Line 41-56** describes a pipeline that includes `Privacy Validation`, `Peer Weights`, `Weight Methods`, `Structural Summary/Detail`, `Rank Changes`, `Impact Summary` sheets. **None of those are emitted today** (see §1, §2.6 of this complement and §9.4 below). Plan Task 11 Step 5 already says "ensure the output sheet list matches actual generated sheets" — reinforce it: the current doc lies about output. After Task 3 lands, every sheet promised here must actually be produced.
- **Lines 760-801** ("Preset and Config Improvement Opportunities") claim items 1–9 are "addressed". Concretely:
  - Item 1: `max_tests` → `max_attempts` mapping is implemented in `ConfigManager._merge_config()`. Confirmed.
  - Item 2: "lambda_penalty is wired to LPSolver as cap slack penalty override" — verify against current `core/solvers/lp_solver.py`. The plan's Task 6 Step 5 only adds a comment about additional-constraint scope; it does not check that `lambda_penalty` actually flows into the LP objective. **Recommendation:** add a regression test asserting that `lambda_penalty=100000000` (used by `strategic_consistency`) materially changes the LP objective vs `lambda_penalty=None`.
  - Item 3: "rank_penalty_weight as multiplier on volume_preservation" — confirmed in `analysis_run.build_dimensional_analyzer` line 78-80 (`rank_preservation_strength = volume_preservation * rank_penalty_weight`).
  - Item 6: `consistency_mode` is wired through `resolve_consistency_mode()` (`core/analysis_run.py:43-56`). Confirmed.
  - Item 7: Bayesian iter / learning_rate flow into HeuristicSolver. Confirmed via `core/solvers/heuristic_solver.py:86-87, 220-228`.
  - Item 8: Internal-dimension filtering via `CategoryBuilder.is_internal_dimension_name`. Confirmed (`core/global_weight_optimizer.py:463`).
  - Item 9: `enforce_single_weight_set` gating. Confirmed (`core/global_weight_optimizer.py:103, 214-215, 477-481`).
  - **Status takeaway:** items 1, 3, 6, 7, 8, 9 are honoured by current code. Item 4 ("output toggles") is the regression — see §9.4.

### 9.4 `docs/IMPLEMENTATION_PLAN_FIXES_1_TO_4.md` (Feb 2026)

This plan claims `[x]` for all four workstreams and was verified on 2026-02-02 with `pytest -> 35 passed` and gate `Passed 17, Failed 0`. Today the test count is **49 passed, 5 failed** and gate cannot run cleanly because of the quoting bug GPT identified. Therefore the implementation regressed between Feb 2026 and May 2026. That regression window correlates exactly with the refactor commits documented in GPT's plan §"Git History Root Cause for Stub Modules":

| Commit | Date | Effect |
|---|---|---|
| `ae95269` | Feb 2026 | extracted run-setup helpers into `core/analysis_run.py`. |
| `9b61a50` | Feb 2026 | shrank `benchmark.py` by ~2,485 lines, introduced uncommitted stub imports. |
| `81cf493` | May 2026 | added stub implementations in this branch to unblock imports. |
| `cfc267a` | May 2026 | merged stubs into `main`. |

The pre-refactor `benchmark.py` (3,508 lines on commit `9b61a50^`) **had a comprehensive `generate_excel_report()` (lines 1595-2400+) that explicitly created Peer Weights, Weight Methods, Structural Summary, Structural Detail, Rank Changes, Subset Search, Privacy Validation, Preset Comparison, Impact Analysis, Secondary Metrics sheets**. The current `core/excel_reports.generate_excel_report()` is a 50-line wrapper around `ReportGenerator.generate_report()`, and `ReportGenerator._generate_excel_report()` only writes Summary + Metric_* + Metadata. **The diagnostic-sheet generation code was deleted, not extracted.** This is the single largest concrete regression on `main` and is the root cause of GPT's plan Task 3.

This evidence makes Task 3 even more urgent than the plan implies. Recommendation: rewire `ReportGenerator._write_optional_dataframe_sheet()` (Task 3 Step 6) **plus** restore the pre-refactor formatting (column widths, fills, headers) — Task 3 Step 6 as written produces functional but unformatted sheets. Reviewers will compare against the old workbooks and notice the styling regression.

### 9.5 `outputs/investigation_fortbrasil/logic_audit_report.json` (validation snapshot pre-refactor)

This is the strongest piece of in-tree evidence supporting GPT's plan. The JSON snapshot was generated by an earlier, working `benchmark.py` against the FortBrasil dataset and explicitly enumerates which sheets the workbooks contained:

```json
"sheets": [
  "Summary", "flag_domestic", "poi", "poi_3ds_category", "poi_ticket_range",
  "Peer Weights", "Weight Methods", "Structural Summary", "Structural Detail",
  "Rank Changes", "Privacy Validation", "Preset Comparison", "Impact Analysis",
  "Data Quality"
]
```

Run the same command on today's `main` (with the same dataset) and you get only `Summary, Metric_1_*, ..., Metadata`. This is a **regression test you do not need to write** — the JSON snapshot itself is one. Plan Task 1 should reference this file and the next-door `outputs/investigation_fortbrasil_rerun/before_after_eval.json` as canonical "previously known good" output.

The `before_after_eval.json` file is even more direct — it explicitly compares old and new workbook sheets and CSV diffs for `share_strategic`, `rate_strategic`, and `share_balanced_default`. The `csv_compare.max_abs_diffs` block shows numerical drift on the order of `Balanced_qtde_txns_ttl_Share_%: 4.4709` percentage points between old and new on the `share_strategic` case — that is a material change in business-visible output, not a formatting tweak. **Plan Task 1 should add a new regression test** that re-runs `share strategic_consistency` against a small fixture and asserts that the share/impact distributions remain within a documented tolerance band of the pre-refactor numbers, otherwise the remediation branch may quietly ship a different model.

The same snapshot also confirms the `low_distortion` `_TIME_TOTAL_` reserved-prefix red flag (line 113-115) that `IMPLEMENTATION_PLAN_FIXES_1_TO_4.md` claimed to have fixed. The fix is in the code (`CategoryBuilder.is_internal_dimension_name`) but Task 6 Step 1 of GPT's plan does not reference the existing in-tree fix; reviewers may inadvertently revert it. Add a comment.

### 9.6 `docs/OPERATIONAL_GAINS.md`

The user-facing value proposition (75% balancing-time reduction, single L7/L8 analyst can run it end-to-end, audit-ready outputs) **depends entirely on the diagnostic sheets that no longer exist**. Quoting the doc directly:

> Analysts can understand and debug every decision behind peer weights:
> - Peer weight multipliers per dimension
> - How privacy caps shaped the weights
> - Distortion analysis (raw vs balanced results)
> - Which solver was used per dimension (global LP, per-dimension LP, Bayesian fallback)
> - Rank changes before and after balancing
> - Privacy validation results with pass/fail details

Today's main produces a workbook with `['Summary', 'Metric_1_*', 'Metric_2_*', 'Metadata']`. None of the bullets above can be executed. **The product is, as of `main`, materially broken against its documented value proposition.** Plan Task 3 is therefore not "polish" — it is restoring the tool's reason to exist. Reflect that severity in PR descriptions.

---

## 10. Updated Severity Ranking After Doc Review

After cross-checking against `docs/`:

| Severity | Items |
|---|---|
| **P0 — product-broken regression** | §2.6 (publication mode never triggers), §9.4/§9.5 (diagnostic sheets deleted, ALL of `Peer Weights`, `Weight Methods`, `Privacy Validation`, `Structural Summary/Detail`, `Rank Changes`, `Subset Search`, `Preset Comparison`, `Impact Analysis`, `Data Quality`, `Secondary Metrics` are missing on main) |
| **P1 — silently wrong output** | §2.1 (compliance verdict false positive), §2.2 (preset comparison silently empty), §9.5 (numerical drift in `Balanced_*_Share_%` between pre/post refactor) |
| **P2 — cannot validate** | §2.3 (CSV validator crashes), GPT plan Task 9 (gate runner shlex+sheet matching) |
| **P3 — preset/config drift** | §2.4 (preset key drift), §2.5 (validator silent on unknown nested keys), §9.1 stale epsilon docs |
| **P4 — code quality / dead code** | §2.7 (dead schema constants), §2.8 (audit log DF strings), §2.11 (blocked summary), §2.13 (empty Report: line) |

**Do not merge GPT's remediation plan without addressing every P0 and P1 item.** The plan as written addresses the P0/P1 items adequately when augmented with §2.1 and §2.2 patches. P3 items are also already in scope (Task 7). P4 is icing.

---

## 11. Files Touched by This Audit Pass

This complement document remains read-only — no code or test changes. Documents reviewed in this pass that were **not** covered in the original §7 list:

- `docs/CORE_LOGIC_REVIEW.md` (509 lines)
- `docs/CORE_LOGIC_REVIEW_FULL.md` (80 lines)
- `docs/CORE_TECHNICAL_DOC.md` (1158 lines)
- `docs/IMPLEMENTATION_PLAN_FIXES_1_TO_4.md` (297 lines)
- `docs/OPERATIONAL_GAINS.md` (95 lines)
- `outputs/investigation_fortbrasil/logic_audit_report.json` (741 lines, prior pristine validation snapshot)
- `outputs/investigation_fortbrasil_rerun/before_after_eval.json` (206 lines, before/after diff snapshot)
- `outputs/investigation/custom_per_dimension.yaml`, `custom_strict_global.yaml` (custom config samples)
- Pre-refactor `benchmark.py` (commit `9b61a50^`, 3,508 lines) inspected via `git show` to confirm regression scope.
