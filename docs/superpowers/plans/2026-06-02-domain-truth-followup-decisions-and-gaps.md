# Domain Truth Refactor Follow-up Decisions And Gaps

This note records the follow-up audit after implementing the roadmap in
`2026-06-01-domain-truth-refactor-roadmap.md`.

## Decisions Taken

- Kept public CLI/TUI/report interfaces stable while moving business facts into
  typed seams. Workbook sheet names and CSV schemas remain compatibility
  renderings.
- Kept `DataQualityResult` in `core/contracts.py` with the other run lifecycle
  contracts instead of creating a separate `core/data_quality.py`.
- Kept `ConfigManager` at adapter edges. The live analyzer construction and
  output settings use typed `ResolvedConfig`, while some orchestration metadata
  still reads from the merged config during the compatibility window.
- Kept `DimensionalAnalyzer` as the public facade. New typed privacy validation
  is exposed through `build_privacy_validation_result()`, and the legacy
  `build_privacy_validation_dataframe()` now renders from that typed result.
- Treated relaxed secondary-rule handling as non-strict. A row can render legacy
  columns for compatibility, but `strict_compliant` is false when relaxation was
  used.

## Follow-ups Closed In This Pass

- Strict final validation now calls the canonical `evaluate_rule()` engine and
  records per-category rule-evaluation details.
- Live orchestration keeps the returned `DataQualityResult`, passes it into
  compliance finalization, and prevents unchecked input from producing a
  `fully_compliant` verdict.
- `AnalysisPlan`, `AnalysisResult`, and `ReportModel` are constructed on the live
  run path and attached to `AnalysisArtifacts` for output adapters.
- Privacy validation is now typed-row-first. The old DataFrame builder is a
  rendering adapter over `PrivacyValidationResult.to_dataframe()`.
- Audit log compaction and summary construction now go through
  `core/audit_log.py::build_audit_log_model()`.
- `OutputArtifactWriter` now owns the report model and output-mode decisions
  instead of being a discarded marker object.

## Remaining Compatibility Gaps

- `core/analysis_run.py` still builds a broad metadata dictionary for legacy
  report and audit consumers. This is now adapter payload, but not fully deleted.
- `core/report_generator.py` still renders optional sheets from metadata keys.
  It consumes `ReportModel` for summary facts, but sheets are not yet driven by a
  single typed model end-to-end.
- `core/output_artifacts.py` still delegates workbook generation to existing
  Excel helpers. `OutputArtifactWriter` owns decisions, but not every write
  operation yet.
- Analyzer mutable state remains a compatibility surface for balanced CSV,
  impact calculation, and legacy tests.
- TUI advanced configuration still keeps small compatibility wrappers
  (`_nested_get`, `_nested_set`, `_collect_advanced_override_data`) around
  `ConfigOverrideBuilder` so existing tests and call sites remain stable.

## Suggested Next Cleanup

1. Replace remaining metadata-key sheet rendering with `ReportModel` fields.
2. Move balanced CSV and impact readers from analyzer mutable state to
   `WeightingResult`.
3. Collapse TUI advanced wrappers once all tests use `utils/config_overrides.py`.
4. Run the Phase 11 deletion searches and remove compatibility shims one at a
   time with targeted tests.
