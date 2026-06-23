# Plan 018: Document and pin a stable programmatic Python API (execute_share_run / execute_rate_run)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat e0950c4..HEAD -- core/analysis_run.py core/contracts.py README.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S–M
- **Risk**: LOW
- **Depends on**: plans/003-analysis-run-integration-test.md (the integration test proves the API works in-process; its learnings feed the example)
- **Category**: direction
- **Planned at**: commit `e0950c4`, 2026-06-10

## Why this matters

CLI and TUI already share one in-process backend: `AnalysisRunRequest` → `execute_share_run` / `execute_rate_run` → `AnalysisArtifacts`. Teams that want scheduled pipelines or notebook integration currently shell out to `benchmark.py` as a subprocess or reverse-engineer internals — fragile, slow, and an untested contract. The architecture makes a documented library surface nearly free: name the entry points public, show one working example, and pin the contract with a test so accidental breakage is caught. Deliberately small: three symbols, not the whole `DimensionalAnalyzer` surface.

## Current state

- `core/analysis_run.py:1546-1556` — the entry points (verbatim):

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

- `core/contracts.py` (~lines 84-162) — `AnalysisRunRequest` dataclass (fields include `csv`, `entity`, `metric`, `dimensions`, `time_col`, `preset`, `output`, `export_balanced_csv`, optional pre-loaded `df`) and `AnalysisArtifacts` (carries `analysis_output_file`-derived `report_paths`, `csv_output`, `audit_log_output`, `audit_package_output`, diagnostic DataFrames). Read both fully — the docs you write must match the real field names.
- The TUI is the existing exemplar consumer: it calls `execute_run(request, logger)` (`tui_app.py:45, 1267`) — a mode-dispatching convenience wrapper over the pair. The documented public surface stays the mode-specific pair (`execute_share_run`/`execute_rate_run`); treat `execute_run` as internal and do not document it (one wrapper fewer to freeze).
- `core/__init__.py` exports `DimensionalAnalyzer`, `PrivacyValidator`, `DataLoader` (per AGENTS.md) — check whether `analysis_run` symbols are exported and decide in Step 2.
- README has no programmatic-usage section; `docs/CORE_TECHNICAL_DOC.md` is the technical reference.
- There is no `examples/` directory yet.
- If plan 003 landed, `tests/test_analysis_run_integration.py` already drives this exact surface — the example script is essentially that test minus pytest.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Run the example | `py examples/run_from_python.py` | exit 0, prints output path |
| Contract test | `py -m pytest tests/test_public_api.py -q` | all pass |
| Full suite | `py -m pytest tests/ -q` | all pass |
| Gate | `py scripts/perform_gate_test.py` | exit 0 |
| Typecheck | `py -m mypy core/ utils/` | exit 0 |

## Scope

**In scope**:
- `examples/run_from_python.py` (create)
- `tests/test_public_api.py` (create)
- `README.md` (new "Programmatic use (Python API)" section)
- `docs/CORE_TECHNICAL_DOC.md` (short API contract section)
- `core/__init__.py` or `core/analysis_run.py` — only if adding explicit re-exports/`__all__` (no behavior change)

**Out of scope**:
- Exposing `DimensionalAnalyzer`, `ConfigManager`, or any other internals as "public API" — the contract is exactly `AnalysisRunRequest`, `execute_share_run`, `execute_rate_run` (and `AnalysisArtifacts` as the return type).
- Semver/packaging work (`pyproject` packaging metadata, PyPI) — this is a documented in-repo contract, not a published package.
- Any change to `_execute_run` behavior.

## Git workflow

- Branch: `advisor/018-python-api`
- Commit message style: `docs: document programmatic API` / `test: pin public API contract`
- Do NOT push or open a PR unless instructed.

## Steps

### Step 1: Write the example script

`examples/run_from_python.py` — a complete, runnable share analysis against the tracked fixture:

```python
"""Minimal programmatic usage of the benchmark engine.

The public API surface is:
    core.contracts.AnalysisRunRequest   (input contract)
    core.analysis_run.execute_share_run (share analysis)
    core.analysis_run.execute_rate_run  (rate analysis)
    -> both return core.contracts.AnalysisArtifacts
"""
import logging
from core.analysis_run import execute_share_run
from core.contracts import AnalysisRunRequest

logging.basicConfig(level=logging.INFO)

request = AnalysisRunRequest(
    # fill with the real field names from core/contracts.py
    csv="tests/fixtures/gate_demo.csv",
    entity="Target",
    metric="txn_cnt",
    dimensions=["card_type", "channel"],
    time_col="year_month",
    preset="balanced_default",
    output="example_share.xlsx",
)
artifacts = execute_share_run(request, logging.getLogger("example"))
print("Report:", artifacts.analysis_output_file)
```

Adapt field names to the actual dataclass. The script must run from the repo root and exit 0. Note in a comment that generated `.xlsx` files are gitignored.

**Verify**: `py examples/run_from_python.py` → exit 0, workbook created; delete the workbook afterward.

### Step 2: Decide and wire the import surface

Check `core/__init__.py`. Recommendation: add the three symbols to `core`'s exports with an `__all__`, so the documented import is stable even if `analysis_run` is later split (audit DEBT-01 expects that). If re-exporting creates an import-cycle or heavy import-time cost (e.g. `core/__init__` becomes slow because `analysis_run` pulls 15 modules), document direct module imports instead (`from core.analysis_run import ...`) and skip the re-export — record which choice you made and why in the PR description.

**Verify**: `py -c "from core.analysis_run import execute_share_run, execute_rate_run; from core.contracts import AnalysisRunRequest, AnalysisArtifacts; print('ok')"` → prints `ok`.

### Step 3: Pin the contract with a test

`tests/test_public_api.py`:
1. Import test (the line from Step 2's verify, as a test).
2. Signature pin: `inspect.signature(execute_share_run)` has exactly parameters `(request, logger)`; same for `execute_rate_run`.
3. Field-presence pin: `AnalysisRunRequest` has (at least) the fields used in the example — assert each name in `{f.name for f in dataclasses.fields(AnalysisRunRequest)}`. Use "at least" semantics (new fields allowed; removals/renames fail).
4. Return-contract pin: `AnalysisArtifacts` has fields `analysis_output_file`, `csv_output`, `report_paths` (extend per actual dataclass; "at least" semantics again).
5. A comment block at the top: "These tests pin the documented public API (README → Programmatic use). Breaking them requires updating the README, the example, and consumers."

**Verify**: `py -m pytest tests/test_public_api.py -q` → all pass.

### Step 4: Documentation

- `README.md`: add a "Programmatic use (Python API)" section after the CLI Cookbook: the three-symbol contract, the example file path, a trimmed inline snippet, and the stability promise ("these symbols are kept stable; everything else in `core/` is internal and may change without notice"). Mention `request.df` for pre-loaded DataFrames (the TUI's validation-first pattern) as an advanced option.
- `docs/CORE_TECHNICAL_DOC.md`: short subsection stating the same contract and pointing at `tests/test_public_api.py` as the enforcement.

**Verify**: `rg -n "Programmatic use" README.md` → match; example path referenced in README exists.

### Step 5: Full verification

**Verify**: `py -m pytest tests/ -q` → all pass; `py scripts/perform_gate_test.py` → exit 0; `py -m mypy core/ utils/` → exit 0; `git status` shows only in-scope files (no stray `example_share.xlsx` — it's gitignored, but don't commit it regardless).

## Test plan

See Step 3 — import, signatures, request fields, artifact fields. Pattern: plain pytest, no fixtures needed.

## Done criteria

- [ ] `py examples/run_from_python.py` exits 0 from a clean checkout (with deps installed)
- [ ] `tests/test_public_api.py` pins imports, signatures, and field presence
- [ ] README and CORE_TECHNICAL_DOC document the three-symbol contract and the stability promise
- [ ] `py -m pytest tests/ -q`, `py scripts/perform_gate_test.py`, `py -m mypy core/ utils/` all exit 0
- [ ] `plans/README.md` status row updated

## STOP conditions

- `AnalysisRunRequest` cannot be constructed for a valid share run without private helpers (required fields with no public way to derive them) — the API isn't actually usable as documented; report what's missing instead of documenting a workaround.
- Re-exporting from `core/__init__.py` creates a circular import — fall back to direct module imports (Step 2 already allows this); if even direct import fails outside the repo root due to path assumptions, report.

## Maintenance notes

- When `analysis_run.py` is split (deferred DEBT-01), the re-export layer (or documented import path) is the compatibility boundary — the contract test will catch a break.
- New request fields should be added with defaults so existing programmatic consumers don't break; reviewers should check `test_public_api.py` passes untouched on additive changes.
- Future candidates for the public surface (only with demand): `ValidationIssue`/input validation, preset listing. Resist exposing `DimensionalAnalyzer`.
