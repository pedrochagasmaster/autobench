# Codebase Simplification and End-to-End Validation Design

## Goal

Reduce unnecessary production complexity while preserving Autobench's documented
Python API, CLI and TUI behavior, report schemas, and privacy guarantees. Verify
the resulting application through automated tests and deterministic local
end-to-end workflows.

## Scope

The cleanup may remove unused or deprecated internal APIs. It must preserve the
stable public surface documented in `README.md`:

- `core.contracts.AnalysisRunRequest`
- `core.analysis_run.execute_share_run`
- `core.analysis_run.execute_rate_run`
- `core.contracts.AnalysisArtifacts`

CLI flags, TUI workflows, configuration behavior, output formats, exit codes,
privacy enforcement, and publishable-output validation remain compatible.
Generated workbooks, CSVs, reports, logs, telemetry, and harness artifacts stay
outside the repository.

## Simplification Strategy

### Dead internal surface

Remove symbols with no production consumers that are outside the documented
public API. Remove redundant aliases, unused tracking state, and compatibility
wrappers whose only consumers can call the underlying internal implementation
directly.

### Balanced export

Consolidate duplicated share and rate aggregation, weighting, and row-building
logic in `core/balanced_export.py`. The refactor must preserve column names,
column order, row ordering, calculations, sanitization, and export validation.

### Subset search

Extract the duplicated subset-trial evaluation path in `core/subset_search.py`.
Greedy and random candidate selection remain distinct, while category building,
solver invocation, slack checks, result recording, scoring, and best-candidate
updates share one implementation. Trial order and privacy behavior must not
change.

### Mechanical cleanup

Collapse repetitive best-effort telemetry wrappers behind one private helper.
Remove redundant comments and thin adapters only when doing so reduces total
complexity without obscuring domain logic or weakening error handling.

Large rewrites of `DimensionalAnalyzer`, analysis orchestration, report
generation, and privacy-policy code are excluded. Their complexity represents
domain behavior and changing them would create disproportionate regression risk.

## Validation

Establish a clean automated baseline before implementation. Structural changes
use focused characterization tests and test-first development for any new
helper. After each unit, run its targeted tests. Before completion, run:

- Ruff
- mypy for `core/` and `utils/`
- the full pytest suite
- the full CLI gate

Use a deterministic terminal harness to exercise local user-visible flows:

- top-level and command help, version, configuration, and preset operations
- share and rate analyses, peer-only mode, presets, advanced analysis options,
  balanced CSV, publication and dual outputs, JSON, audit package, lean mode,
  compliance postures, validation failures, and telemetry reports
- TUI Share and Rate runs, file/header loading, preset help, advanced overrides,
  keyboard navigation, validation handling, session persistence, and clean exit
- report, CSV, JSON, audit package, and telemetry artifact inspection

Use tracked fixtures and temporary directories. External SSH, deployment,
Kerberos, live edge-node launchers, and shared `/ads_storage` acceptance cannot
be verified safely in the local environment and will be listed explicitly as
coverage gaps.

## Safety Rules

- Never weaken privacy caps, compliance gates, or publishable-output checks.
- Treat output or exit-code differences as regressions unless a removed
  undocumented internal symbol is the sole difference.
- Do not add abstractions unless they remove more duplication than they create.
- Stop and investigate any privacy, report-schema, or deterministic-output
  regression instead of updating tests to accept it.
