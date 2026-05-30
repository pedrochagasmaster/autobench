# Roadmap

Date: 2026-05-30

This roadmap continues the production-readiness work after the de-slop
remediation merged in PR #18. It is grounded in the latest docs review, CLI
smoke tests, gate/unit checks, and manual TUI testing.

## Product direction

Build the Privacy-Compliant Peer Benchmark Tool into a production-ready
benchmarking product with:

- dependable CLI automation,
- a guided first-run TUI,
- auditable privacy/compliance outputs,
- reproducible offline deployment,
- regression protection for business-visible reports.

## Short term - stabilize the user path

1. Fix the TUI `call_from_thread` crash found during manual testing.
2. Add automated and manual TUI smoke coverage for the documented first-run
   workflow.
3. Make manual CSV path entry trigger header loading so Browse is not a single
   point of failure.
4. Clarify `utils/csv_validator.py` as rate-only or add share-output validation.
5. Update README examples so copy/paste first-run commands use enough peers for
   the privacy rules.
6. Add GitHub Actions for lint, unit tests, and the gate suite.

Success signal:
- A user can launch `py tui_app.py`, select `tests/fixtures/gate_demo.csv`, run
  share analysis, and see a saved report without using the CLI.

## Medium term - harden release quality

1. Add golden output tests for share, rate, peer-only, publication, CSV schema,
   and compliance verdicts.
2. Add performance/regression benchmarks for larger peer/category/time-aware
   datasets.
3. Version the report/config contract with explicit deprecation notes.
4. Create a repeatable offline release process with dependency bundles,
   checksums, smoke commands, and rollback guidance.
5. Improve TUI validation UX:
   - data quality preview,
   - schema mapping,
   - preset explanations,
   - clear warnings for compliance posture.
6. Package run outputs as an audit bundle:
   - workbook,
   - balanced CSV,
   - audit log,
   - config snapshot,
   - validation summary.

Success signal:
- Every release candidate can be reproduced, tested, deployed offline, and
  audited from saved artifacts.

## Long term - productize the platform

1. Add a web/API layer for queued runs, team access, and downloadable report
   bundles.
2. Add run history with input hashes, config snapshots, solver stats, compliance
   verdicts, and artifact lineage.
3. Add enterprise integrations:
   - SQL sources,
   - scheduled benchmark jobs,
   - BI-ready exports,
   - monitoring and alerts.
4. Add compliance governance workflows:
   - reviewer sign-off,
   - exception handling,
   - immutable audit evidence,
   - explainability summaries.
5. Add recommendation features:
   - preset comparison guidance,
   - sensitivity analysis,
   - high-impact category detection,
   - merchant-specific workflows.

Success signal:
- The app supports governed, repeatable benchmarking for production users
  without requiring a developer to run or interpret each analysis.

## Immediate backlog

| Priority | Item | Primary files |
|---|---|---|
| P0 | Fix TUI log handler thread crash | `tui_app.py`, `tests/test_tui_contracts.py` |
| P0 | Add manual TUI walkthrough after fix | `/opt/cursor/artifacts`, `README.md` |
| P1 | Clarify or extend CSV validator scope | `utils/csv_validator.py`, `utils/CSV_VALIDATOR_README.md`, `README.md` |
| P1 | Make README first-run examples fixture-backed | `README.md`, `tests/fixtures/gate_demo.csv` |
| P1 | Add CI gate workflow | `.github/workflows/ci.yml`, `requirements-dev.txt` |
| P2 | Add golden output tests | `tests/fixtures/`, `tests/test_golden_outputs.py` |
| P2 | Document offline release process | `SETUP.md`, `docs/RELEASE_PROCESS.md` |

For implementation detail, see
`docs/PRODUCTION_READINESS_IMPLEMENTATION_PLAN.md`.
