# Post-Audit Full Sweep Results Analysis

## Run Summary

- Date: 2026-05-06
- Branch: `cursor/audit-remediation-26fb`
- Sweep mode: `exhaustive`
- Input CSV: `data/readme_demo.csv` (gitignored local fixture)
- Case count: 1,017
- Result: 1,017 passed, 0 failed, 0 errors
- Runtime: 270.748 seconds

## Commands

```bash
py scripts/generate_cli_sweep.py --mode exhaustive --allow-large --csv data/readme_demo.csv --out-dir /tmp/post_audit_full_sweep
```

The generated commands were executed with a Python runner that:

1. Ran every generated CLI command.
2. Captured stdout and stderr per case under `/tmp/post_audit_full_sweep/run_logs/`.
3. Verified each generated artifact with `GateTestRunner.verify_case()`.
4. Wrote machine-readable summaries to:
   - `/tmp/post_audit_full_sweep/full_sweep_summary.json`
   - `/tmp/post_audit_full_sweep/full_sweep_summary.csv`

Compact copies were saved for review at:

- `/opt/cursor/artifacts/post_audit_full_sweep/full_sweep_runner_output.txt`
- `/opt/cursor/artifacts/post_audit_full_sweep/full_sweep_summary.json`
- `/opt/cursor/artifacts/post_audit_full_sweep/full_sweep_summary.csv`

## Coverage

| Area | Cases | Passed | Notes |
|---|---:|---:|---|
| Share CLI | 504 | 504 | Target and peer-only, manual and auto dimensions, all presets, config + preset combinations, all output formats, validation modes. |
| Rate CLI | 504 | 504 | Same matrix as share, including approval/fraud-capable paths where generated. |
| Config CLI | 9 | 9 | List, show each shipped preset, validate template, generate template. |
| Total | 1,017 | 1,017 | Full generated exhaustive sweep passed. |

## Findings

The final sweep validates the remediation branch across the audit-critical surfaces:

- `analysis`, `publication`, and `both` output modes all generated verifiable workbooks.
- Diagnostic sheets restored by the remediation were present where expected.
- Preset and config combinations loaded successfully, including shipped presets fixed during remediation.
- Accuracy-first preset cases ran after the generator added the required acknowledgement flag.
- Generated output paths were tracked in case metadata, so the verifier checked actual workbooks instead of reporting false "cannot verify" failures.
- Fraud publication cases now include `--fraud-col` when a fraud column is available, so BPS publication verification exercises real fraud output.

## Non-Blocking Observations

- The verifier emitted repeated warnings that no Data Quality header row was present when the Data Quality sheet contained only a pass message. These warnings did not produce failures. A later polish pass could either add a standard header row to no-issue Data Quality sheets or quiet this verifier warning.
- The sweep used the local `data/readme_demo.csv` fixture. It gives broad CLI/config/output coverage but is intentionally small; it is not a substitute for high-cardinality or production-like performance testing.

## Conclusion

The post-audit exhaustive sweep is a valid implementation signal for this branch: all 1,017 generated cases completed and passed artifact verification after generator metadata and acknowledgement handling were corrected.
