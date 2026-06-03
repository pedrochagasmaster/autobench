# Resource Management for Large Runs

This guide explains how the benchmark tool keeps memory and CPU use lower on
memory-limited remote servers, especially for massive CSV inputs and many
dimensions.

## Quick recipe

Use lean mode when running on a constrained server:

```bash
py benchmark.py share \
  --csv large_input.csv \
  --entity "Target Entity" \
  --metric txn_cnt \
  --dimensions card_type channel product_type \
  --time-col year_month \
  --lean \
  --output lean_share.xlsx
```

For rate analysis:

```bash
py benchmark.py rate \
  --csv large_input.csv \
  --entity "Target Entity" \
  --total-col total \
  --approved-col approved \
  --fraud-col fraud \
  --dimensions card_type channel product_type \
  --time-col year_month \
  --lean \
  --output lean_rate.xlsx
```

Lean mode is intended for explicit-dimension runs. Avoid `--auto` on very wide
or high-cardinality datasets because auto-detection must inspect more columns
and can select dimensions that dramatically increase category counts.

## What lean mode changes

`--lean` maps to `runtime.lean_mode: true` and applies a resource-saving profile
through the merged config:

| Area | Lean setting | Why |
| --- | --- | --- |
| Input validation | `input.validate_input: false` | Avoids full row-level validation scans before analysis. |
| CSV projection | `input.project_csv_columns: true` | Loads only entity, metric, numerator, dimension, and time columns needed for the run. |
| Adaptive batching | `input.adaptive_batching: true` | Allows heavy CSVs to be streamed and pre-aggregated before the core pipeline. |
| CSV chunk size | `input.csv_chunk_size: 100000` | Caps per-chunk memory while streaming. |
| Debug sheets | `output.include_debug_sheets: false` | Avoids extra diagnostic DataFrames and workbook sheets. |
| Privacy validation sheet | `output.include_privacy_validation: false` | Keeps compliance validation typed, but avoids rendering the large sheet. |
| Impact/preset comparison | disabled | Avoids additional full analysis passes. |
| Audit log | disabled | Avoids rendering extra diagnostic summaries. |
| Output format | `analysis` | Writes one workbook, not analysis + publication. |
| Subset search | disabled | Avoids repeated LP attempts over alternate dimension subsets. |
| Auto dimensions | disabled | Forces intentional dimension selection. |

## Adaptive batching behavior

Adaptive batching happens at CSV load time, before the full pandas DataFrame is
materialized.

The loader:

1. Reads the CSV header.
2. Resolves the requested run columns after normalizing names.
3. Estimates row count and file size.
4. If the run is above configured thresholds and safe to aggregate, reads CSV
   chunks.
5. Normalizes each chunk.
6. Groups by:
   - entity column
   - explicit dimensions
   - optional time column
7. Sums metric/numerator columns.
8. Periodically compacts partial aggregates so memory does not grow with every
   chunk.
9. Passes the compact aggregated DataFrame into the existing optimizer and
   report pipeline.

This is safe for the expected long-format benchmark input because the tool's
privacy categories and reports use additive totals by entity/dimension/time.

## When batching triggers

Batching can trigger when all of these are true:

- `input.adaptive_batching: true`
- explicit `--dimensions` are provided
- row-level input validation is disabled
- enough aggregation columns are known
- estimated rows or file size cross the configured thresholds

Defaults:

```yaml
input:
  adaptive_batching: true
  batch_row_threshold: 250000
  batch_file_size_mb: 256.0
  batch_compaction_chunks: 20
```

The loader records the decision in `DataLoader.last_workload_estimate` for tests
and debugging. The estimate includes file size, estimated rows, projected column
count, total column count, whether batching was selected, and the reason.

## Why validation disables batching

Row-level validation checks nulls, invalid values, row indices, and other data
quality signals that can be lost after aggregation. For that reason, adaptive
batching only pre-aggregates when input validation is disabled.

Recommended pattern:

1. Validate a representative extract or smaller sample with validation enabled.
2. Run the full massive file with `--lean` once the input contract is trusted.

## What does not change

Lean mode and adaptive batching do **not** bypass privacy compliance:

- Privacy rule selection is unchanged.
- Control 3.2 caps are still enforced on the final peer/category totals.
- Additional rule checks still run through the existing analyzer.
- Typed privacy validation is still available for the final compliance summary.

The main tradeoff is operational visibility: lean runs intentionally omit heavy
debug/audit/report artifacts unless you opt them back in through config.

## Tuning examples

### More aggressive batching

Use lower thresholds when the server has very little memory:

```yaml
runtime:
  lean_mode: true

input:
  batch_row_threshold: 50000
  batch_file_size_mb: 64.0
  csv_chunk_size: 50000
  batch_compaction_chunks: 5
```

### Keep audit output but still batch

Lean mode disables audit logs. If audit output is required, use a config file
instead of `--lean` and selectively enable the audit log:

```yaml
runtime:
  lean_mode: true

output:
  include_audit_log: true
```

Note that audit output can require additional DataFrame rendering, so memory use
will be higher than a fully lean run.

### Disable batching

If a run relies on row-level custom behavior or you need to inspect raw rows:

```yaml
input:
  adaptive_batching: false
```

## Practical guidance for massive datasets

- Prefer explicit `--dimensions`; avoid `--auto` for large files.
- Start with a small dimension list, then add dimensions intentionally.
- Avoid `--time-col` unless time-consistent weights are required; time-aware
  constraints multiply category counts by time periods.
- Avoid `--compare-presets`, `--analyze-impact`, `--debug`, and
  `--output-format both` on constrained servers.
- If privacy feasibility is difficult, run a smaller diagnostic slice outside
  lean mode, then use lean mode for production-scale execution.
