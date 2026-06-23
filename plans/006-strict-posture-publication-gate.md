# Plan 006: Block publication-format outputs when strict posture detects violations (keep analysis workbook)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat e0950c4..HEAD -- core/analysis_run.py core/output_artifacts.py core/compliance.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: plans/004-fix-compliance-violation-double-count.md, plans/005-harden-optimization-failure-semantics.md
- **Category**: bug
- **Planned at**: commit `e0950c4`, 2026-06-10

## Why this matters

Under `compliance_posture: strict` (the `compliance_strict` preset), a run with detected privacy violations is labeled `run_status: non_compliant` — but every artifact is still written, including the **publication-format workbook** intended for external distribution. A user can unknowingly distribute a publication workbook from a non-compliant run; the only protection is a metadata label. The maintainer has decided (2026-06-10): **when posture is strict and violations are detected, publication-format outputs must not be written; the analysis workbook is still written for debugging**, with a clear log/Summary indication. Best-effort and accuracy-first postures keep current behavior.

## Current state

- `core/compliance.py:221-222` — strict posture only labels:

```python
if self.posture == "strict":
    run_status = "non_compliant" if has_violations else "compliant"
```

- `core/analysis_run.py:1428-1440` — compliance summary is computed and stored in metadata **before** outputs are written.
- `core/analysis_run.py:1502` — `artifacts = write_outputs(request, artifacts, config=config, logger=logger)`. `write_outputs` lives in `core/output_artifacts.py` (~line 60-151) and decides between analysis workbook, publication workbook, or both, based on `output.output_format` (`analysis` | `publication` | `both`). It produces `artifacts.publication_output` when a publication workbook is written.
- `core/analysis_run.py:1517-1521` — `artifacts.report_paths = build_report_paths(output_settings.output_format, analysis_output_file, artifacts.publication_output)`.
- Posture values: `strict`, `best_effort`, `accuracy_first` (see `core/compliance.py:221-228`). Posture for the run is in `compliance_context['compliance_posture']` (`core/analysis_run.py:1429`).
- The violation count in `compliance_summary['violations']` is accurate after plan 004; verdict honesty after plan 005.
- Gate: `scripts/perform_gate_test.py` runs 18 cases including publication-format cases — confirm whether any gate case is strict-posture **with** violations (search `test_gate/*/cases.jsonl` for `compliance_strict` and check those cases' expectations). At commit `e0950c4` the gate passes with `fully_compliant` verdicts, so no gate case should trip the new gate — verify rather than assume.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Integration tests | `py -m pytest tests/test_output_artifacts.py -q` (add `tests/test_analysis_run_integration.py` to the invocation only if it exists — it is created by plan 003) | all pass |
| Full suite | `py -m pytest tests/ -q` | all pass |
| Gate | `py scripts/perform_gate_test.py` | exit 0 |
| Typecheck | `py -m mypy core/ utils/` | exit 0 |

## Scope

**In scope**:
- `core/output_artifacts.py` (the blocking logic)
- `core/analysis_run.py` (pass posture/violations into the writer if not already available there)
- `tests/test_output_artifacts.py` (extend)

**Out of scope**:
- `core/compliance.py` — verdict/status strings unchanged.
- Balanced CSV export and audit log/package — they remain written in all cases (they are analysis/debug evidence, not publication artifacts). If the maintainer later wants CSV blocked too, that's a follow-up.
- TUI/CLI flag surface — no new flags; the behavior keys off posture.

## Git workflow

- Branch: `advisor/006-strict-publication-gate`
- Commit message style: `feat: withhold publication outputs on strict non-compliance`
- Do NOT push or open a PR unless instructed.

## Steps

### Step 1: Locate the publication branch in `write_outputs`

Read `core/output_artifacts.py` fully. The publication workbook is generated inside `write_outputs` via the `_write_report(publication_file, publication=True)` call at `core/output_artifacts.py:147-150`, which routes to `ReportGenerator.generate_publication_workbook` (line ~110). Confirm this matches the live file.

**Verify**: `rg -n "write_publication|publication=True" core/output_artifacts.py` → shows the property (line ~48-50) and the call site (~147-148); record the line numbers in your commit message.

### Step 2: Add the gate

In `write_outputs` (or a small helper beside it), before generating the publication workbook:

```python
posture = (artifacts.compliance_summary or {}).get("posture")
violations = int((artifacts.compliance_summary or {}).get("violations", 0) or 0)
block_publication = posture == "strict" and violations > 0
```

(`AnalysisArtifacts` carries `compliance_summary` — it is passed into `build_analysis_artifacts` at `core/analysis_run.py:1488-1500`. Confirm the attribute name on the dataclass; if the summary is only in `metadata`, read it from there instead.)

When `block_publication`:
- Skip publication workbook generation entirely; set `artifacts.publication_output = None` — note `build_report_paths`/`build_analysis_artifacts` (`core/report_artifact_builder.py:42`) **pre-populates** `publication_output` with the expected path before `write_outputs` runs, so you are overwriting a non-None value, not "leaving" it.
- Log at ERROR: `"Strict posture: publication output withheld (violations=%d). Analysis workbook written for debugging only."`
- Set `artifacts.metadata["publication_withheld_reason"] = "strict_posture_violations"` at the **start** of `write_outputs`, before any workbook write. Timing facts: `artifacts.metadata` is the **same dict object** as the local `metadata` in `_execute_run` (passed by reference into `build_analysis_artifacts`), and the audit log is written **after** `write_outputs` (`core/analysis_run.py:1523-1527`, using that same local dict) — so mutating `artifacts.metadata` inside `write_outputs` is sufficient for the audit log to capture it. Verify the same-object claim with a quick check (`assert artifacts.metadata is metadata` mentally or in a scratch test); if they are *copies*, also sync the key in `core/analysis_run.py` after the `write_outputs` call (in scope).
- Do NOT attempt to surface the reason on the Excel Summary sheet — `_write_summary_sheet` (`core/report_generator.py:293-301`) renders a hardcoded key list and `core/report_generator.py` is out of scope. The ERROR log + metadata/audit-log are the deliverable; Summary-sheet display is an explicitly deferred follow-up (note it in the commit message).
- If `output_format == "publication"` (publication-only run): write no workbook, log the error, and ensure `report_paths` ends up empty but the run completes with `run_status="non_compliant"`. (Rationale: silently substituting an analysis workbook where a publication one was requested risks the wrong file being distributed.)

**Verify**: `py -m pytest tests/test_output_artifacts.py -q` → existing tests pass (none currently exercise strict+violations).

### Step 3: Tests

In `tests/test_output_artifacts.py`, following its existing style of invoking runs/writers with temp outputs:

1. Strict posture + `compliance_summary` with `violations >= 1` + `output_format="both"` → analysis workbook exists, publication file does **not** exist, `publication_output is None`, metadata contains `publication_withheld_reason`.
2. Same but posture `best_effort` → publication workbook **is** written (current behavior preserved).
3. Strict posture + zero violations → publication workbook written (no false blocking).
4. Strict + violations + `output_format="publication"` → no workbook written, run does not raise.

If constructing a genuinely violating run from fixture data is heavy, unit-test the gate by invoking `write_outputs` directly with a crafted `artifacts.compliance_summary` — that is acceptable; the integration-level behavior is covered by test 1 if feasible. For the direct-invocation fixture: build the smallest real artifacts via one `benchmark.run_share_analysis`-style run (the pattern most tests in `tests/test_output_artifacts.py` use), then overwrite `artifacts.compliance_summary = {"posture": "strict", "violations": 1, ...}` and call `write_outputs` again with a fresh tmp output path — do not hand-construct `ReportModel` from scratch.

**Verify**: `py -m pytest tests/test_output_artifacts.py -q` → all pass.

### Step 4: Full verification

**Verify**: `py -m pytest tests/ -q` → all pass; `py scripts/perform_gate_test.py` → exit 0; `py -m mypy core/ utils/` → exit 0.

## Test plan

See Step 3 — four cases: blocked, posture-exempt, violation-free, publication-only. Pattern file: `tests/test_output_artifacts.py`.

## Done criteria

- [ ] Strict + violations ⇒ no publication file on disk (test proves it)
- [ ] Best-effort + violations ⇒ publication file written (test proves it)
- [ ] Strict + no violations ⇒ publication file written (test proves it)
- [ ] `py -m pytest tests/ -q`, `py scripts/perform_gate_test.py`, `py -m mypy core/ utils/` all exit 0
- [ ] `git status` shows only in-scope files modified
- [ ] `plans/README.md` status row updated

## STOP conditions

- A gate case is strict-posture and *expects* a publication workbook while having violations — that means the gate itself relies on the behavior this plan removes; report the case ID and stop.
- `AnalysisArtifacts` does not carry the compliance summary and `write_outputs` has no access to metadata either — plumbing it through requires touching the artifact contract (`core/contracts.py` / `core/report_artifact_builder.py`); report before expanding scope.
- Audit-package code (`core/audit_package.py`) breaks because `report_paths` no longer contains a publication path — `_add_existing_file` tolerates missing paths (`core/audit_package.py:18-24` warns and returns), so it shouldn't; if it does, report.

## Maintenance notes

- This is deliberately publication-only blocking. The maintainer explicitly chose to keep the analysis workbook for debugging. If a future "block everything" mode is requested, gate it behind config, not a behavior change.
- Reviewers should scrutinize the publication-only (`output_format="publication"`) path — it now can complete with zero workbooks; downstream scripts that assume a file exists must handle that.
- Single-weight mode (`strategic_consistency`) can still emit cap-violating weights under non-strict postures — known, out of scope (audit CORRECTNESS-06).
