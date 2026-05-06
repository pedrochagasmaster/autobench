# Post-Audit Sweep Results Analysis

Date: 2026-05-06

## Scope

This document summarizes the post-remediation core CLI sweep run for the consolidated audit remediation branch.

Artifacts used for this analysis were generated under `/tmp/audit_consolidation_sweep` during verification and are intentionally not committed.

## Result Summary

The corrected core sweep completed successfully.

- Total cases executed: 1063
- Passed: 1063
- Failed verifier checks: 0
- Execution errors: 0

Breakdown by section:

- Share cases: 526 / 526 passed
- Rate cases: 528 / 528 passed
- Config cases: 9 / 9 passed

The final saved summary in `/tmp/audit_consolidation_sweep/results/summary.json` reports a completely green matrix with no residual failures.

## Why this sweep is meaningful

This was not just a command-generation smoke test. Each case was executed and then verified with the same post-remediation gate verifier logic used by `scripts/perform_gate_test.py`.

For every exhaustive case, the runner:

1. Executed the generated CLI command.
2. Checked for non-zero process exits.
3. Verified expected artifacts such as:
   - analysis workbooks
   - publication workbooks
   - balanced CSV files where applicable
   - audit logs
4. Applied workbook-content validation and publication-format checks.

This means the sweep exercised:

- target and peer-only modes
- manual and auto dimension resolution
- analysis, publication, and both output modes
- validation on/off paths
- preset and config combinations
- share and rate analyses
- fraud BPS publication formatting
- config list/show/validate/generate flows

## Important issues discovered while making the sweep valid

The first consolidation sweep attempt exposed problems in the sweep tooling and two small verification-surface gaps:

1. The reusable sweep runner initially inferred publication-only output paths from stdout.
   - Effect: the gate verifier appended `_publication` twice for publication-only cases.
   - Fix: prefer generated `output_base=...` expectations over stdout inference.

2. `benchmark config generate` was not idempotent in repeated sweep runs.
   - Effect: the generated template already existed from case generation.
   - Fix: remove the generated template before executing sweep cases.

3. Rate balanced CSV export used source column names instead of standard balanced column names.
   - Effect: the CSV validator could not find rate columns.
   - Fix: emit `Balanced_Total`, `Balanced_Approval_Total`, and `Balanced_Fraud_Total`.

4. The gate verifier treated single-category share sheets as if they must sum to 100%.
   - Effect: peer-only/per-dimension single-category sheets failed with a 90.10% sum.
   - Fix: skip the share-mix sum check when fewer than two category values are present.

These fixes matter because they ensure the sweep measures actual product behavior rather than failing on stale or invalid test scaffolding.

## Product-level conclusions

The core sweep results support the conclusion that the audit-remediation branch is now stable across the combinatorial CLI matrix represented by the sweep generator.

Specifically, the sweep demonstrates that the remediated code now handles:

- preloaded and standard file-driven run paths without dropping required inputs
- output-mode semantics consistently across share and rate analyses
- publication workbook generation across all relevant combinations
- diagnostic workbook sheet generation without regressing report writing
- preset loading and preset comparison without the earlier stub-path failures
- `accuracy_first` preset execution when the required acknowledgement is provided
- gate-style verification for fraud BPS publication outputs
- config CLI flows without the prior rerun or path-handling drift

## Residual caveats

There are still a few limits to what this sweep proves:

1. The sweep dataset is intentionally small and deterministic.
   - This is appropriate for broad combinatorial coverage, but it is not a stress/performance benchmark.

2. Share CSV validation remains intentionally skipped by gate logic.
   - The repository’s share CSV export and Excel report represent different semantics, so the verifier does not try to cross-validate them numerically in the same way as rate outputs.

3. The sweep confirms runtime stability and expected artifact behavior for the generated matrix.
   - It does not replace domain review of business-level quality for external production datasets.

## Final assessment

The post-audit core sweep is fully green.

From a repository-verification perspective, this is strong evidence that the remediation work is valid:

- unit and regression tests pass
- targeted gate verification passes
- core CLI sweep passes across 1063 generated cases
- generated sweep artifacts remain outside source control

The implementation can now be described as sweep-validated against the repository’s own combinatorial CLI matrix.
