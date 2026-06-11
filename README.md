# Privacy-Compliant Peer Benchmark Tool

Privacy-safe benchmarking for issuers, banks, and merchants with automatic Mastercard Control 3.2 enforcement.

## TL;DR

- Use `py tui_app.py` for a guided first run.
- Use `py benchmark.py share|rate ...` for automation.
- Privacy caps are always enforced automatically.
- Start with preset `balanced_default` unless you have a specific regulatory/reporting need.

## Table of Contents

- [What This Tool Solves](#what-this-tool-solves)
- [Quick Start](#quick-start)
- [First Successful Run (Copy/Paste)](#first-successful-run-copypaste)
- [Input Data Requirements](#input-data-requirements)
- [Privacy Rules (Auto-Applied)](#privacy-rules-auto-applied)
- [TUI Workflow](#tui-workflow)
- [CLI Cookbook](#cli-cookbook)
- [Programmatic use (Python API)](#programmatic-use-python-api)
- [Large Dataset / Low-Memory Runs](#large-dataset--low-memory-runs)
- [Presets](#presets)
- [Outputs](#outputs)
- [Excel Sheet Guide](#excel-sheet-guide)
- [Troubleshooting](#troubleshooting)
- [Validation and Testing](#validation-and-testing)
- [Additional Documentation](#additional-documentation)

## What This Tool Solves

This project benchmarks an entity against peers while preventing single-peer dominance in category-level comparisons.

You get:

- Peer-weighted benchmarks with privacy constraints.
- Share and rate analysis modes.
- Excel outputs for analysis/audit/publication and optional balanced CSV export.
- Optional audit package zip (`--audit-package`) bundling workbook(s), balanced
  CSV, audit log, config snapshot, and validation/compliance summary.
- CLI and TUI entry points using the same core engine.

## Quick Start

> In this repo, use `py` for Python commands.

Requires Python 3.10+.

Install dependencies:

```powershell
py -m pip install -r requirements.txt
```

Run the TUI:

```powershell
py tui_app.py
```

Or inspect CLI help:

```powershell
py benchmark.py --help
py benchmark.py share --help
py benchmark.py rate --help
```

## First Successful Run (Copy/Paste)

Use the tracked fixture `tests/fixtures/gate_demo.csv` (1 target + 6 peers). On
Linux/macOS:

```bash
py benchmark.py share \
  --csv tests/fixtures/gate_demo.csv \
  --entity Target \
  --metric txn_cnt \
  --dimensions card_type channel \
  --time-col year_month \
  --preset balanced_default \
  --output gate_demo_share.xlsx
```

```bash
py benchmark.py rate \
  --csv tests/fixtures/gate_demo.csv \
  --entity Target \
  --total-col total \
  --approved-col approved \
  --fraud-col fraud \
  --dimensions card_type channel \
  --time-col year_month \
  --preset balanced_default \
  --export-balanced-csv \
  --output gate_demo_rate.xlsx
```

Launch the TUI:

```bash
py tui_app.py
```

TUI workflow:

1. Enter `tests/fixtures/gate_demo.csv` in **CSV File Path** (Browse is optional).
2. Press Enter or tab away to load column headers.
3. Set **Entity ID Column** to `issuer_name`, **Target Entity** to `Target`.
4. On the Share tab, choose metric `txn_cnt`, time column `year_month`, and
   dimensions `card_type` + `channel`.
5. Click **Run Analysis** and confirm the log shows `Analysis completed successfully`.

Success signals:

- CLI commands exit 0 and write `gate_demo_*.xlsx`.
- Rate run also writes `gate_demo_rate_balanced.csv`.
- The workbook `Summary` shows `Input Validation: pass` and `Compliance Verdict: fully_compliant`.
- TUI completes without a thread/logging crash and shows a saved report path.

Generated `.xlsx`, `.csv`, and `benchmark_log_*.txt` files are gitignored local
artifacts; they are safe to delete after inspection.

Windows PowerShell equivalents use backslashes, for example
`--csv tests\fixtures\gate_demo.csv`.

## Input Data Requirements

Expected format is pre-aggregated long format (one row per entity x dimension bucket).

Example:

```csv
issuer_name,flag_domestic,card_type,txn_cnt,tpv
BANCO SANTANDER,Domestic,CREDIT,125000,15000000
BANCO SANTANDER,Domestic,DEBIT,200000,8000000
ITAU UNIBANCO,Domestic,CREDIT,180000,22000000
```

Important rules:

- Entity names are case-sensitive.
- Column names are normalized to lowercase with underscores.
- Keep metric units consistent (currency, count definitions, etc.).
- Non-merchant benchmarking requires enough peers for the selected privacy rule, starting at 5 peers for 5/25; merchant 4/35 is only available when merchant mode is explicitly used.
- Nulls in key entity/metric fields will trigger validation issues.

## Privacy Rules (Auto-Applied)

The engine selects the rule based on peer count.

| Rule | Min Peers | Max Concentration | Additional Condition |
|---|---:|---:|---|
| 5/25 | 5 | 25% | - |
| 6/30 | 6 | 30% | >=3 participants at >=7% |
| 7/35 | 7 | 35% | >=2 at >=15%, plus >=1 at >=8% |
| 10/40 | 10 | 40% | >=2 at >=20%, plus >=1 at >=10% |
| 4/35 | 4 | 35% | Merchant benchmarking only |

You do not manually configure these caps during normal runs.

## TUI Workflow

The TUI (`tui_app.py`) is best for first-time users:

1. Enter a CSV path or use Browse (searches current directory and `data/`).
2. Press Enter or tab away from the path field to load headers.
3. Choose entity column and target entity (or run peer-only).
4. Pick a preset.
5. Configure Share or Rate tab.
6. Click Run Analysis and watch logs.

Keyboard shortcuts:

- `Ctrl+O` open/select file
- `Ctrl+R` run analysis
- `F1` preset help
- `Ctrl+A` toggle advanced panel
- `Ctrl+E` export advanced overrides

## CLI Cookbook

Share analysis:

```powershell
py benchmark.py share --csv FILE --entity NAME --metric COLUMN --dimensions DIM1 DIM2
```

Rate analysis:

```powershell
py benchmark.py rate --csv FILE --entity NAME --total-col TOTAL --approved-col APPROVED --fraud-col FRAUD --dimensions DIM1 DIM2
```

Peer-only mode (omit `--entity`):

```powershell
py benchmark.py share --csv FILE --metric COLUMN --auto
```

Run with diagnostics and CSV export:

```powershell
py benchmark.py share --csv FILE --entity NAME --metric COLUMN --auto --analyze-impact --export-balanced-csv --include-calculated --debug
```

Publication output format:

```powershell
py benchmark.py rate --csv FILE --total-col TOTAL --approved-col APPROVED --output-format publication
```

Low-memory server run:

```powershell
py benchmark.py share --csv FILE --entity NAME --metric COLUMN --dimensions DIM1 DIM2 --lean
```

Config/preset management:

```powershell
py benchmark.py config list
py benchmark.py config show balanced_default
py benchmark.py config validate my_config.yaml
py benchmark.py config generate my_config.yaml
```

## Programmatic use (Python API)

For scheduled pipelines or notebook integration, call the same in-process backend
the CLI and TUI use instead of shelling out to `benchmark.py`.

**Stable public surface** (kept compatible across releases; everything else in
`core/` is internal and may change without notice):

| Symbol | Role |
|--------|------|
| `core.contracts.AnalysisRunRequest` | Input contract for share or rate runs |
| `core.analysis_run.execute_share_run` | Run share analysis |
| `core.analysis_run.execute_rate_run` | Run rate analysis |
| `core.contracts.AnalysisArtifacts` | Return type (paths and DataFrames) |

A complete runnable example lives at `examples/run_from_python.py`. Minimal
share run:

```python
import logging
from core.analysis_run import execute_share_run
from core.contracts import AnalysisRunRequest

request = AnalysisRunRequest(
    csv="tests/fixtures/gate_demo.csv",
    entity="Target",
    metric="txn_cnt",
    dimensions=["card_type", "channel"],
    time_col="year_month",
    preset="balanced_default",
    compliance_posture="strict",
    output="report.xlsx",
)
artifacts = execute_share_run(request, logging.getLogger("pipeline"))
print(artifacts.analysis_output_file)
```

When a preset is set, pass `compliance_posture` explicitly (matches TUI/CLI
behavior). For rate runs, set `mode="rate"` plus `total_col` and numerator
columns. Advanced: pass a pre-loaded DataFrame via `request.df` to skip CSV
reload after validation.

Contract tests in `tests/test_public_api.py` pin imports, signatures, and field
names; breaking changes require updating the README, example, and consumers.

## Large Dataset / Low-Memory Runs

Use `--lean` for memory-limited remote servers or very large CSV files:

```bash
py benchmark.py share \
  --csv large_input.csv \
  --entity Target \
  --metric txn_cnt \
  --dimensions card_type channel \
  --time-col year_month \
  --lean \
  --output lean_share.xlsx
```

Lean mode keeps privacy-cap enforcement intact while reducing memory and CPU
pressure:

- loads only the columns needed for explicit-dimension runs;
- estimates CSV workload before full load;
- streams heavy CSVs in chunks when safe;
- pre-aggregates duplicate entity/dimension/time rows by summing metric columns;
- disables optional heavy artifacts such as debug sheets, impact summaries,
  preset comparisons, audit logs, and dual workbooks;
- disables subset search to avoid repeated LP attempts.

Adaptive batching only pre-aggregates when input validation is disabled, because
row-level validation details can be lost after aggregation. Validate a smaller
sample first, then use `--lean` for the full trusted input.

See `docs/RESOURCE_MANAGEMENT.md` for trigger thresholds, config tuning, and
operational caveats.

## Presets

List available presets:

```powershell
py benchmark.py config list
```

Recommended starting point:

- `balanced_default`: day-to-day analysis.

Use when needed:

- `compliance_strict`: regulatory/audit-first, zero tolerance.
- `strategic_consistency`: emphasize one consistent global weighting behavior.
- `research_exploratory`: harder datasets with more flexibility.
- `low_distortion` / `minimal_distortion`: prioritize lower distortion patterns.

Quick selection guide:

- Regulatory submission -> `compliance_strict`
- Executive/dashboard consistency -> `strategic_consistency`
- General business analysis -> `balanced_default`

## Outputs

Main output is Excel (`.xlsx`), optionally with balanced CSV. Set `--report-format json` (or `output.format: json` in config) to also write a machine-readable `.json` sidecar beside the analysis workbook; the JSON is analysis-grade and not publication-redacted.

Common sheets:

- `Summary`
- One sheet per analyzed dimension
- `Weight Methods`
- `Rank Changes`
- Additional diagnostics based on flags (`--debug`, `--analyze-impact`, subset search paths)

Balanced CSV is useful for BI ingestion (Power BI, Tableau, pipelines).

Secondary metrics requested with `--secondary-metrics` are exported as
supplemental weighted context using the final peer weights. They are not
independent privacy-compliance surfaces; the compliance verdict is based on the
primary share metric or rate denominator/numerator contract for the run.

## Excel Sheet Guide

The report includes a consistent core set of sheets, plus optional diagnostics.

Core sheets:

- `Summary`
  - Inputs, configuration, preset used, and high-level metadata.
  - Primary place to confirm the run parameters and interpretation context.
- `[Dimension]` sheets (one per dimension)
  - Category-level comparisons for the target entity vs peer averages.
  - Includes gaps (percentage point deltas) and best-in-class benchmarks.
- `Weight Methods`
  - Shows which weighting strategy was applied per dimension:
    `Global-LP`, `Per-Dimension-LP`, or `Per-Dimension-Bayesian`.
- `Rank Changes`
  - Tracks rank shifts before/after weighting to show distortion impact.

Optional diagnostic sheets (appear when enabled or triggered):

- `Peer Weights` (debug)
  - Raw peer volumes, multipliers, and final weights.
  - Use for audit trails and deep validation.
- `Privacy Validation` (debug)
  - Per-category compliance checks and concentration caps.
- `Structural Summary` / `Structural Detail`
  - Buckets that are infeasible under strict caps.
  - Useful for explaining unavoidable residual violations.
- `Subset Search`
  - Logs subset search attempts when global LP is infeasible.
- `Impact Summary` / `Impact Detail` (analyze impact)
  - Distortion metrics by dimension/category (aka “impact”).
  - Triggered by `--analyze-impact` (alias: `--analyze-distortion`).

## Troubleshooting

- `Entity not found`
  - Use exact case-sensitive entity values from the CSV.
- `Column not found`
  - Use normalized names (`lowercase_with_underscores`).
- `No valid dimensions`
  - Pass explicit `--dimensions` instead of relying on `--auto`.
- LP infeasibility warnings
  - Expected for some sparse/structural datasets; fallback methods are built in.
- Unexpectedly high distortion
  - Try `--compare-presets` and inspect impact sheets.

## Validation and Testing

For contributors, run after changes:

```bash
py -m ruff check .
py -m mypy core/ utils/
py scripts/perform_gate_test.py
py -m pytest tests/ -v
```

For a fast inner-loop smoke (not a substitute for the full gate before PR):

```bash
py scripts/perform_gate_test.py --only share_gate_baseline
```

GitHub Actions runs ruff, unit tests, and the full gate on pull requests
(see `.github/workflows/ci.yml`). Mypy is a local-only check.

Balanced CSV exports are now cross-validated automatically when
`output.validate_export` is enabled (the default). Rate exports run the full
workbook-vs-CSV check; share exports receive a schema check mirroring the gate
test. Results appear in run metadata and audit packages. The manual command
below remains available for ad-hoc verification.

Optional CSV-vs-Excel cross-check (use a rate export with
`--export-balanced-csv`; share exports are schema-checked by the gate unless a
workbook exposes explicit `Balanced_*_Share_%` columns):

```bash
py utils/csv_validator.py gate_demo_rate.xlsx gate_demo_rate_balanced.csv --verbose
```

For release evidence, add `--audit-package` to bundle the generated workbook(s),
balanced CSV (when exported), audit log, config snapshot, and validation summary
into `<output>_audit_package.zip`.

## Additional Documentation

- `AGENTS.md` - full business rules and contributor constraints
- `docs/RESOURCE_MANAGEMENT.md` - lean mode, adaptive batching, and low-memory run guidance
- `SETUP.md` - deployment/setup notes
- `docs/CORE_TECHNICAL_DOC.md` - core engine technical reference
- `utils/CSV_VALIDATOR_README.md` - CSV validator details

## Version

Configuration model: v3.0.
