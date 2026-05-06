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
- CLI and TUI entry points using the same core engine.

## Quick Start

> In this repo, use `py` for Python commands.

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

If you want a deterministic smoke test with your own tiny CSV, create one:

```powershell
@'
issuer_name,card_type,channel,txn_cnt,amt_total,amt_approved,amt_fraud
BANCO SANTANDER,CREDIT,POS,125000,15000000,14100000,42000
BANCO SANTANDER,DEBIT,POS,200000,8000000,7600000,16000
ITAU UNIBANCO,CREDIT,POS,180000,22000000,20500000,51000
ITAU UNIBANCO,DEBIT,POS,160000,9000000,8500000,18000
BRADESCO,CREDIT,POS,140000,17000000,15900000,47000
BRADESCO,DEBIT,POS,150000,8200000,7700000,17000
CAIXA,CREDIT,POS,130000,14000000,13100000,39000
CAIXA,DEBIT,POS,170000,7800000,7300000,15000
NUBANK,CREDIT,POS,110000,13000000,12200000,36000
NUBANK,DEBIT,POS,120000,7000000,6600000,14000
'@ | Set-Content data\readme_demo.csv
```

Run share analysis:

```powershell
py benchmark.py share --csv data\readme_demo.csv --entity "BANCO SANTANDER" --metric txn_cnt --dimensions card_type channel --preset balanced_default
```

Run rate analysis:

```powershell
py benchmark.py rate --csv data\readme_demo.csv --entity "BANCO SANTANDER" --total-col amt_total --approved-col amt_approved --fraud-col amt_fraud --dimensions card_type channel --preset balanced_default
```

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

1. Select CSV (searches current directory and `data/`).
2. Choose entity column and target entity (or run peer-only).
3. Pick a preset.
4. Configure Share or Rate tab.
5. Click Run Analysis and watch logs.

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

Config/preset management:

```powershell
py benchmark.py config list
py benchmark.py config show balanced_default
py benchmark.py config validate my_config.yaml
py benchmark.py config generate my_config.yaml
```

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

Main output is Excel (`.xlsx`), optionally with balanced CSV.

Common sheets:

- `Summary`
- One sheet per analyzed dimension
- `Weight Methods`
- `Rank Changes`
- Additional diagnostics based on flags (`--debug`, `--analyze-impact`, subset search paths)

Balanced CSV is useful for BI ingestion (Power BI, Tableau, pipelines).

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

For contributors, run both after changes:

```powershell
py scripts/perform_gate_test.py
py -m pytest
```

Optional CSV-vs-Excel cross-check:

```powershell
py utils\csv_validator.py report.xlsx report_balanced.csv --verbose
```

## Additional Documentation

- `AGENTS.md` - full business rules and contributor constraints
- `SETUP.md` - deployment/setup notes
- `docs/CORE_TECHNICAL_DOC.md` - core engine technical reference
- `utils/CSV_VALIDATOR_README.md` - CSV validator details

## Version

Configuration model: v3.0.
