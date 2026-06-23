# Plan 003: Add a fast in-process integration test for the analysis_run orchestration pipeline

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat e0950c4..HEAD -- core/analysis_run.py core/contracts.py tests/fixtures/gate_demo.csv`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW
- **Depends on**: none
- **Category**: tests
- **Planned at**: commit `e0950c4`, 2026-06-10

## Why this matters

`core/analysis_run.py` (~1,550 lines) is the single orchestration path shared by CLI and TUI and the highest-churn file in the repo. Today the only end-to-end coverage is the gate suite — 18 subprocess invocations of `benchmark.py`, each cold-starting Python — and helper-level tests with heavy mocking. There is no fast, in-process test that exercises the full pipeline (`AnalysisRunRequest` → `execute_share_run`/`execute_rate_run` → written artifacts). That gap makes every refactor of the orchestrator (and the compliance-semantics fixes in plans 004–006) regress only at gate granularity. This plan adds the missing mid-layer test, which later plans use as their safety net.

## Current state

- `core/analysis_run.py:1546-1556` — the public entry points:

```python
def execute_share_run(request: AnalysisRunRequest, logger: logging.Logger) -> AnalysisArtifacts:
    return _execute_run(request, SHARE_MODE_SPEC, logger)

def execute_rate_run(request: AnalysisRunRequest, logger: logging.Logger) -> AnalysisArtifacts:
    return _execute_run(
        request,
        RATE_MODE_SPEC,
        logger,
        extra_config_overrides={'fraud_in_bps': request.fraud_in_bps},
    )
```

- `core/contracts.py` (~line 84-162) — `AnalysisRunRequest` dataclass with fields including `csv`, `entity`, `metric`, `dimensions`, `time_col`, `preset`, `output`, `export_balanced_csv`, and an optional pre-loaded `df`. It has a `from_namespace(mode, args)` classmethod used by the CLI. Read the dataclass definition before constructing instances.
- `_execute_run` ends by returning `AnalysisArtifacts` (see `core/analysis_run.py:1488-1543`) carrying `analysis_output_file`-derived `report_paths`, `csv_output`, `audit_log_output`, `audit_package_output`.
- Run metadata lands in the artifacts/compliance summary: `metadata['compliance_verdict']`, `metadata['run_status']` are set at `core/analysis_run.py:1437-1438` from `build_compliance_summary(...).to_dict()`.
- Test fixture: `tests/fixtures/gate_demo.csv` — 7 entities (6 peers + 1 target named `Target`), entity column `issuer_name`, share metric `txn_cnt`, rate columns `total`/`approved`/`fraud`, dimensions `card_type` and `channel`, time column `year_month`. The README "First Successful Run" section (README.md:66-115) documents exactly these parameters and expects `Compliance Verdict: fully_compliant`.
- Existing tests that call `benchmark.run_share_analysis` directly: `tests/test_output_artifacts.py`, `tests/test_enhanced_features.py` — use these for style (tmp output paths, cleanup), but the new test must go through `core.analysis_run.execute_share_run` / `execute_rate_run`, not through `benchmark.py`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| New test | `py -m pytest tests/test_analysis_run_integration.py -q` | all pass, < ~60s |
| Full suite | `py -m pytest tests/ -q` | all pass |
| Gate | `py scripts/perform_gate_test.py` | exit 0 |

## Scope

**In scope**:
- `tests/test_analysis_run_integration.py` (create)

**Out of scope**:
- `core/analysis_run.py`, `core/contracts.py` — no product changes. If the pipeline cannot be driven in-process without modification, STOP and report.
- `scripts/perform_gate_test.py` — the gate remains untouched.

## Git workflow

- Branch: `advisor/003-analysis-run-integration-test`
- Commit message style: `test: add in-process analysis_run integration coverage`
- Do NOT push or open a PR unless instructed.

## Steps

### Step 1: Read the request contract

Read `core/contracts.py` fully, especially `AnalysisRunRequest` and `AnalysisArtifacts`. List which fields are required vs defaulted. The TUI (`tui_app.py:1122-1192`) constructs the request field-by-field and is a useful reference for a minimal valid share request.

**Verify**: you can state (in a comment at the top of the new test file) the minimal required fields for a share run and a rate run.

### Step 2: Write the share-run integration test

In `tests/test_analysis_run_integration.py`:

```python
import logging
from pathlib import Path
from core.analysis_run import execute_share_run
from core.contracts import AnalysisRunRequest

FIXTURE = Path(__file__).parent / "fixtures" / "gate_demo.csv"

def test_share_run_end_to_end(tmp_path):
    out = tmp_path / "share_it.xlsx"
    request = AnalysisRunRequest(
        # mode/analysis fields per the actual dataclass — fill from Step 1
        csv=str(FIXTURE),
        entity="Target",
        metric="txn_cnt",
        dimensions=["card_type", "channel"],
        time_col="year_month",
        preset="balanced_default",
        output=str(out),
    )
    artifacts = execute_share_run(request, logging.getLogger("test"))
    assert out.exists()
```

(Adjust constructor args to the real dataclass — field names above are from the audit and must be confirmed in Step 1.)

Then strengthen assertions:
1. The workbook exists and opens with `openpyxl.load_workbook`; sheet names include `Summary`, `Weight Methods`, `Rank Changes`, and one sheet per dimension.
2. Compliance: assert `artifacts.compliance_summary['compliance_verdict'] == 'fully_compliant'` — the field exists on `AnalysisArtifacts` and is populated in `core/report_artifact_builder.py:44`. Expected for this fixture+preset: `fully_compliant` (per README success signals).
3. No stray files: only expected outputs under `tmp_path`.

**Verify**: `py -m pytest tests/test_analysis_run_integration.py -q` → passes.

### Step 3: Write the rate-run integration test

Same shape via `execute_rate_run`, with these required differences (per `_validate_rate_request`, `core/analysis_run.py:1202-1209`): set `mode="rate"`, `total_col="total"`, `approved_col="approved"`, `fraud_col="fraud"` (at least one of approved/fraud is mandatory and must exist in the loaded DataFrame; omit `metric`), plus `export_balanced_csv=True`. (The share request needs no `mode` — it defaults to `"share"`.) Assert:
1. Workbook written.
2. `<stem>_balanced.csv` exists (per `core/analysis_run.py:1515` the path is `analysis_output_file.rsplit('.', 1)[0] + '_balanced.csv'`).
3. The CSV has `Dimension` and `Category` columns and ≥1 row.

**Verify**: `py -m pytest tests/test_analysis_run_integration.py -q` → both tests pass.

### Step 4: Guard against cwd pollution

`benchmark.py` writes `benchmark_log_*.txt` to cwd, but in-process `execute_*_run` should not. Run the tests and check `git status` — if new log files appear in the repo root, ensure your test does not call `setup_logging` and uses a plain `logging.getLogger`. If `_execute_run` itself writes files outside `tmp_path` (e.g. audit logs beside the output file), assert they land beside the output file in `tmp_path`, not in cwd.

**Verify**: `git status` shows only the new test file.

## Test plan

This plan is the test plan. Two tests minimum (share + rate). Keep total runtime under ~60 seconds so it stays in the default pytest loop.

## Done criteria

- [ ] `py -m pytest tests/test_analysis_run_integration.py -q` exits 0 with ≥2 tests
- [ ] Tests import from `core.analysis_run` and `core.contracts`, not from `benchmark`
- [ ] `py -m pytest tests/ -q` exits 0
- [ ] `py scripts/perform_gate_test.py` exits 0
- [ ] `git status` clean except the new test file
- [ ] `plans/README.md` status row updated

## STOP conditions

- `AnalysisRunRequest` cannot express a valid share run without going through `from_namespace` (i.e., required fields are undocumented or interdependent in ways the dataclass doesn't show) — report what's missing.
- The share run on `gate_demo.csv` with `balanced_default` does **not** produce `fully_compliant` — that contradicts the README's documented success signal; report rather than weakening the assertion.
- Test runtime exceeds ~120s — report; do not silently mark it `slow`.

## Maintenance notes

- Plans 004, 005, 006, 010, and 011 all rely on this test as their fast regression net — land this before any of them.
- When `analysis_run.py` is eventually split into phases (audit finding DEBT-01, not planned this round), this test is the characterization baseline.
