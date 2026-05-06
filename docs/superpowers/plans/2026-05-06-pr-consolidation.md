# PR Consolidation Plan for Audit Remediation

## Goal

Consolidate the eight open audit-remediation PRs into one reviewable implementation branch that restores audited runtime behavior without inheriting stale generated artifacts or branch-specific regressions.

## Decisions from Grill-with-Docs Session

- Use PR #6 as the **Consolidation Base** for production behavior.
- Do not merge any PR wholesale.
- Port selected durable pieces:
  - PR #11 sweep runner source code.
  - PR #7 durable regression-test ideas.
  - Any missing P0/P1/P2/P3 fixes identified by the audit complement.
- Exclude generated sweep outputs and committed result logs from PR #8 and PR #11.
- Keep **Diagnostic Sheets** analysis-only; **Publication Workbooks** stay stakeholder-clean.
- Treat insufficient peers as a **Privacy Block**, even when input validation is disabled.
- Apply the **Merchant Four-Peer Exception** only when merchant peer count is exactly four.
- Support legacy `max_tests` as an input alias, but canonicalize to `max_attempts` and reject unknown nested keys.
- Treat **Solver Success** as post-validation privacy feasibility, not raw optimizer convergence.
- Keep **Audit Remediation Scope** focused on blocker/drift fixes, not broad optimizer architecture refactoring.

## PR Evaluation Summary

| PR | Use in consolidation | Reason |
|---|---|---|
| #4 | Reference only | Clean broad implementation; passes unit/lint/gate, but less verification tooling than #6/#11. |
| #5 | Do not use as base | Passes gate, but appears to miss SQL identifier and impossible-rate remediation. |
| #6 | Base reference | Best balance of clean implementation, passing unit/lint/gate, and low artifact churn. |
| #7 | Selective test/tooling source | Broadest unit coverage and sweep ambition, but gate regresses `config_generate`. |
| #8 | Reject as source branch | Gate workbook verification fails and large generated sweep JSON is committed. |
| #9 | Backup reference | Solid passing branch, similar to #6, but less useful than #6 plus #11. |
| #10 | Reject as source branch | Gate fails and time-total coverage appears incomplete. |
| #11 | Selective tooling source | Gate passes and sweep runner is useful; trim committed generated results. |

## Implementation Shape

1. Create a fresh branch from `main`.
2. Re-apply PR #6 behavior in logical commits:
   - request/DataFrame contract preservation,
   - analysis/publication output routing,
   - diagnostic sheet restoration,
   - preset comparison metrics,
   - compliance verdict and `_TIME_TOTAL_` validation,
   - insufficient-peer blocking,
   - preset/config validation,
   - data-loader safety,
   - gate/CSV validator repairs,
   - TUI hardening,
   - docs drift fixes.
3. Add PR #11's reusable sweep runner as source code only.
4. Port durable regression tests from PR #7/#11 without committing generated sweep result files.
5. Update `CONTEXT.md` and relevant docs to match the final behavior.

## Verification Gates

Run, in order:

```bash
py -m pytest tests/ -v
ruff check --select E,F --ignore E501,F401 benchmark.py core/ utils/ tui_app.py
py scripts/perform_gate_test.py
py scripts/generate_cli_sweep.py --mode core --csv data/readme_demo.csv --out-dir /tmp/audit_consolidation_sweep
py scripts/run_cli_sweep_cases.py --case-dir /tmp/audit_consolidation_sweep --results-dir /tmp/audit_consolidation_sweep/results
```

Generated files under `/tmp` or `data/readme_demo.csv` must not be committed.
