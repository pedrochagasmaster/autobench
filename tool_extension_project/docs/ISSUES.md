# Issues

This file captures the current review findings for the enhanced analysis implementation. It assumes the clarified requirements:
- Validation must hard-fail on errors (no "continue anyway").
- Preset comparison must be exhaustive (all presets + per-dimension variants).
- Distortion/weight-effect must be calculated as target vs peers (not portfolio totals).

## Critical (must fix before release)
- TUI validation modal crashes because it references `issue.context`, which does not exist on `ValidationIssue`. `tui_app.py:163`.
- TUI validation calls the wrong function signatures and then proceeds on exceptions, effectively disabling validation and violating the hard-fail requirement. `tui_app.py:1232`, `tui_app.py:1234`, `tui_app.py:1250-1251`.
- Publication output is never generated. `output_format` is parsed and stored but no publication workbook is produced and `generate_publication_workbook` is dead code. `benchmark.py:592`, `benchmark.py:1022`, `core/report_generator.py:487`.
- Enhanced CSV calculations are incorrect for share and rate: they use totals across all entities (including the target) and compute portfolio category shares instead of target-vs-peers shares. Rate weight-effect also includes the target. `benchmark.py:3000-3015`, `benchmark.py:3100-3190`.

## High
- Preset comparison is not exhaustive: it hard-codes four presets and ignores custom presets and per-dimension variants. `benchmark.py:453-460`.
- Rate preset comparison only evaluates the first weight-effect column; multi-rate comparisons are wrong and can pick the wrong "best" preset. `benchmark.py:523-545`.
- Distortion/weight-effect helpers require `global_weights`; in per-dimension mode they return empty even though per-dimension weights exist. `core/dimensional_analyzer.py:1869-1874`, `core/dimensional_analyzer.py:1989-1994`.
- Per-dimension weight fallback defaults to `1.0` for missing peers instead of merging with global weights, skewing distortion/weight-effect. `core/dimensional_analyzer.py:1788`.
- Config-driven thresholds and feature flags are not used consistently; runtime paths still read CLI args directly for compare/analyze/include-calculated, violating the "merged config only" rule. `benchmark.py:591-594`, `benchmark.py:897`, `benchmark.py:919`.
- Data Quality sheet is never emitted even though the helper exists; validation issues are logged and discarded. `benchmark.py:635-680`, `benchmark.py:1088-1136`, `core/report_generator.py:300`.

## Medium
- Validation peer count uses total entities, not peers; with a target specified you can pass with <5 peers. `core/data_loader.py:523`.
- Case-insensitive entity match only logs INFO; analysis still uses the mismatched case and can produce empty/zero target results. `core/data_loader.py:541`.
- TUI `run_analysis` recursively calls itself inside a worker thread, risking overlapping workers and inconsistent UI state. `tui_app.py:1241`, `tui_app.py:1255`.

## Low
- `generate_publication_workbook` mutates DataFrames in place and converts any column containing "fraud", including BIC/weight-effect columns. If wired later, it will corrupt analysis results. `core/report_generator.py:560-569`.
- Enhanced CSV renames primary metric to `Metric`, which is ambiguous and breaks backward compatibility. `benchmark.py:3171`.

## Requirements Mismatches (explicitly confirmed)
- Validation must hard-fail: TUI currently proceeds on validation exceptions. `tui_app.py:1250-1251`.
- Preset comparison must be exhaustive: hard-coded list is insufficient. `benchmark.py:453-460`.
- Distortion/weight-effect must be target vs peers: current CSV math uses portfolio totals. `benchmark.py:3000-3015`, `benchmark.py:3100-3190`.

## Suggested Fixes (high-level)
- Rewire TUI validation to call the correct signatures and abort on any ERROR, matching CLI.
- Use `ConfigManager` merged config for all enhanced feature flags (no direct CLI reads).
- Replace enhanced CSV share/rate calculations with target-vs-peers logic:
  - Share: raw share = target / (target + raw peers); balanced share = target / (target + balanced peers).
  - Rate: raw peer rate = raw peers numerator/denominator; balanced peer rate = weighted peers numerator/denominator.
- Make preset comparison exhaustive:
  - Use `PresetManager.list_presets()` and add per-dimension variants for each preset.
  - For rate, compute per-rate summaries (approval/fraud) and decide a combined "best" policy.
- Enable publication workbook generation when `output_format` is `publication` or `both`, and keep analysis workbook intact.
- Emit Data Quality sheet using existing helper with validation issues.

## Testing Gaps
- No tests for publication output generation or output_format behavior.
- No tests for exhaustive preset comparison and multi-rate selection logic.
- No tests validating target-vs-peer distortion math in enhanced CSV.
