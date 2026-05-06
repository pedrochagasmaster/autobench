# Post-Audit Sweep Results Analysis

Date: 2026-05-06

## Scope

This document summarizes the post-remediation exhaustive CLI sweep run requested after implementation of the audit remediation plan.

Artifacts used for this analysis:

- Summary JSON: `/opt/cursor/artifacts/post_audit_exhaustive_v2/sweep_summary.json`
- Detailed results: `/opt/cursor/artifacts/post_audit_exhaustive_v2/sweep_results_detailed.jsonl`
- Execution log: `/opt/cursor/artifacts/post_audit_exhaustive_v2/sweep_runner.log`
- Generated case metadata: `/opt/cursor/artifacts/post_audit_exhaustive_v2/meta.json`

## Result Summary

The corrected exhaustive sweep completed successfully.

- Total cases executed: 1017
- Passed: 1017
- Failed verifier checks: 0
- Execution errors: 0

Breakdown by section:

- Share cases: 504 / 504 passed
- Rate cases: 504 / 504 passed
- Config cases: 9 / 9 passed

The final saved summary in `/opt/cursor/artifacts/post_audit_exhaustive_v2/sweep_summary.json` reports a completely green matrix with no residual failures.

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

The first exhaustive attempts exposed problems in the sweep tooling itself, not in the remediated benchmark engine:

1. `scripts/generate_cli_sweep.py` had a `sys.path`/import-path issue when run as a script.
   - Effect: `accuracy_first` presets such as `low_distortion` and `minimal_distortion` were generated without `--acknowledge-accuracy-first`.
   - Result: those cases were invalid test inputs and failed before analysis.
   - Fix: add repository-root bootstrap to the script so preset loading works consistently in script mode.

2. The exhaustive runner initially needed output-path inference from the generated command text.
   - Effect: some publication-only and both-mode cases were marked as unverifiable even though the benchmark command had succeeded.
   - Fix: infer `--output` from command arguments during execution and feed it back into verification.

3. The gate verifier had stale assumptions about workbook structure.
   - Effect: false failures for `Metadata`, `Impact Summary`, and `Impact Detail` sheets, and brittle fraud-publication checks.
   - Fixes:
     - exclude non-dimension sheets from per-dimension content validation
     - support current `Metric_*` sheet naming
     - align impact-sheet checks to `Impact Detail` / `Impact Summary`
     - make fraud-publication verification robust to the current workbook layout

4. Fraud publication formatting needed a real product fix.
   - Effect: fraud publication sheets existed, but the BPS labeling and detection path were not strong enough for the exhaustive verifier.
   - Fix: update publication workbook generation so fraud rate columns are converted and labeled in basis points on fraud sheets.

These fixes matter because they ensure the exhaustive sweep now measures actual product behavior rather than failing on stale or invalid test scaffolding.

## Product-level conclusions

The exhaustive results support the conclusion that the audit-remediation branch is now stable across the combinatorial CLI matrix represented by the sweep generator.

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

The post-audit exhaustive sweep is fully green.

From a repository-verification perspective, this is strong evidence that the remediation work is valid:

- unit and regression tests pass
- targeted gate verification passes
- exhaustive CLI sweep passes across 1017 generated cases
- saved artifacts are available for audit review and replay

The implementation can now be described as sweep-validated against the repository’s own combinatorial CLI matrix.
