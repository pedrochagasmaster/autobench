# Privacy‑Compliant Peer Benchmark Tool (v2)

**Status: Production-ready. All core features implemented and validated.**

Compare a target entity against a peer group across multiple dimensions while enforcing Mastercard privacy rules (Control 3.2). The tool produces detailed Excel reports with Balanced Peer Averages, Best‑in‑Class (BIC) benchmarks, and diagnostics that explain feasibility and weighting decisions.

**New in v2.1:**
- **Peer-only mode**: Analyze peer distributions without specifying a target entity
- **Multi-rate analysis**: Simultaneously analyze approval and fraud rates in a single run
- **Time-aware consistency**: Global weights work across all time periods and categories
- **Time-dimension output**: When `--time-col` is set, dimension sheets show metrics for each time-category combination plus aggregated "General" rows

This is the actively maintained v2 CLI. Legacy notebooks/scripts live in `old/` for reference only.

---

## Highlights
- **Share analysis**: Distribution of a volume metric across categories of each dimension.
- **Rate analysis**: Approval and/or fraud rates by dimension (numerator/total). Both can be analyzed simultaneously.
- **Peer-only mode**: Analyze peer group distributions without specifying a target entity (omit `--entity`).
- **Built‑in privacy**: Per‑category peer concentration caps (4/35, 5/25, 6/30, 7/35, 10/40) applied consistently.
- **Global, consistent weights** across dimensions (optional): One set of peer multipliers applied everywhere:
  - LP solver with rank‑preserving objective; tolerance modeled via cap slacks.
  - Robust fallbacks: auto subset search for the largest feasible global dimension set; greedy dropping; per‑dimension LP/heuristic.
- **Time-aware consistency**: Single weights work across all time periods and month-category combinations.
- **Time-dimension output**: When `--time-col` is specified, dimension sheets include rows for each time-category combination plus "General" rows (aggregated across time).
- **Deep diagnostics and transparency**:
  - Weight Methods tab: which method each dimension used and resulting multipliers.
  - Subset Search tab: attempts, feasibility, and slack usage when searching for a feasible global set.
  - Structural Summary/Detail tabs: quantify structural infeasibility drivers by dimension/category/peer.
  - Rank Changes: full tab plus a Summary snippet showing top movers by absolute rank delta.
- **Rich Excel output** and detailed logs for auditability.

---

## Installation
Prerequisites
- Python 3.10+ (tested on 3.12)
- Windows, macOS, or Linux

Install dependencies
```powershell
pip install -r requirements.txt
````

Recommended

  - SciPy (included in requirements): Enables strict LP solver (HiGHS) for global weights.
  - openpyxl (included): Excel writer.

Windows convenience

```powershell
./setup.ps1
```

This verifies Python/pip, installs packages, and prepares folders.

-----

## Input data

The loader normalizes column names (lowercase, underscores) and maps common aliases via `utils/config_manager.py`.

Minimum for SHARE analysis

  - Entity identifier column (default `issuer_name`; override with `--entity-col`).
  - Metric column for volume: one of
      - `transaction_count` (preferred) or alias `txn_cnt`
      - `transaction_amount` (preferred) or alias `tpv`

Additional for RATE analysis

  - `--total-col` (denominator)
  - One or both of `--approved-col` (approval rate) or `--fraud-col` (fraud rate)
  - When both are specified, generates separate Excel files for each rate type
  - Approval rates use 85th percentile BIC (higher is better)
  - Fraud rates use 15th percentile BIC (lower is better)

**Peer-only mode** (optional)

  - Omit `--entity` to analyze peer distributions without a target entity
  - All entities treated as peers; no target-specific columns in output
  - Works with both share and rate analysis

Tip: Prefer the standardized names; aliases are accepted when recognized.

-----

## Quick start (Windows PowerShell)

We prefer running with the Windows Python launcher `py` and PowerShell style paths.

Share analysis, auto dimensions

```powershell
py benchmark.py share --csv data\sample.csv --entity "BANCO SANTANDER" --metric transaction_count --auto
```

Share analysis, explicit dimensions

```powershell
py benchmark.py share --csv data\sample.csv --entity "BANCO SANTANDER" --metric transaction_amount --dimensions flag_domestic cp_cnp tipo_compra
```

Share analysis, peer-only mode (no target)

```powershell
py benchmark.py share --csv data\sample.csv --metric transaction_count --auto
```

Rate analysis (approval only)

```powershell
py benchmark.py rate --csv data\sample.csv --entity "BANCO SANTANDER" --total-col total_count --approved-col approved_count --auto
```

Rate analysis (fraud only)

```powershell
py benchmark.py rate --csv data\sample.csv --entity "BANCO SANTANDER" --total-col total_count --fraud-col fraud_count --auto
```

Rate analysis (both approval and fraud simultaneously)

```powershell
py benchmark.py rate --csv data\sample.csv --entity "BANCO SANTANDER" --total-col total_count --approved-col approved_count --fraud-col fraud_count --auto
```

Advanced: Time-aware consistency

```powershell
py benchmark.py share --csv data\sample.csv --entity "BANCO SANTANDER" --metric transaction_count --auto --consistent-weights --time-col ano_mes --debug
```

Advanced: Random subset search

```powershell
py benchmark.py share --csv data\sample.csv --entity "BANCO SANTANDER" --metric transaction_count --auto --consistent-weights --auto-subset-search --no-greedy-subset-search --subset-search-max-tests 500 --debug
```

-----

## CLI overview

General

  - `--csv <path>`: Input CSV file
  - `--entity <name>`: Target entity (optional - omit for peer-only mode)
  - `--entity-col <col>`: Entity identifier (default `issuer_name`)
  - `--output/-o <file>`: Excel output (auto‑named if omitted; multi-rate adds suffix)
  - `--bic-percentile <float>`: Default 0.85 for approval rates
  - `--log-level {DEBUG,INFO,WARNING,ERROR}`: Default INFO
  - `--debug`: Adds Peer Weights tab and extra details. In dimension sheets, includes original (unweighted) peer metrics before privacy adjustments:
      - **Share analysis**: Original Peer Average (%), Original Total Volume, Weight Effect (pp)
      - **Rate analysis**: Original Peer Average (%), Original Total Numerator, Original Total Denominator, Weight Effect (pp)
  - `--consistent-weights`: Compute one global set of peer multipliers for all dimensions
  - `--time-col <column>`: Time column for time-aware consistency (e.g., ano\_mes, year\_month)

Share specific

  - `--metric {txn_cnt,tpv,transaction_count,transaction_amount}`
  - Dimensions: `--auto` or `--dimensions <col...>`
  - Weighting params: `--max-iterations`, `--tolerance` (pp), `--max-weight`, `--min-weight`, `--volume-preservation`
  - Advanced search/diagnostics:
      - `--prefer-slacks-first`: Try full‑dimension LP with rank penalty 0 to probe feasibility with slacks
      - `--auto-subset-search`: Search largest feasible global dimension subset
      - `--subset-search-max-tests <int>`: Limit attempts (default 200)
      - `--greedy-subset-search` / `--no-greedy-subset-search`: Use greedy (remove one dim at a time) vs random search (test random n-1, n-2, ... combinations) (default: greedy enabled)
      - `--trigger-subset-on-slack` / `--no-trigger-subset-on-slack`: If LP uses slack above threshold, auto-run subset search (default on)
      - `--max-cap-slack <float>`: Slack sum threshold as percentage of total volume to trigger subset search (default 0.0)

Rate specific

  - One or both of `--approved-col` or `--fraud-col` (at least one required)
  - `--total-col <col>` (denominator, required)
  - Dimensions: `--auto` or `--dimensions <col...>`
  - BIC percentiles automatically set: 85th for approval (higher is better), 15th for fraud (lower is better)
  - When both rate types specified: single Excel file with prefixed dimension sheets (`Approval_*`, `Fraud_*`)

Presets and help

```powershell
py benchmark.py presets
py benchmark.py --help; py benchmark.py share --help; py benchmark.py rate --help
```

-----

## Privacy rules and caps

Applied cap is a function of peer count:

  - **With target entity**: Peer count = unique entities - 1 (excludes target)
  - **Peer-only mode**: Peer count = unique entities (all are peers)

Cap thresholds by peer count:

  - ≥10 peers → 40%
  - 7–9 peers → 35%
  - 6 peers → 30%
  - 5 peers → 25%
  - 4 peers → 35%
  - \<4 peers → 50% (warning: below minimum for compliance)

Caps apply per category within each dimension after weighting. The tool prevents any single peer from exceeding the cap in the adjusted share used to compute Balanced Peer Averages.

-----

## Peer-only mode

Analyze peer distributions without a target entity by omitting the `--entity` parameter.

**Key differences:**

  - All entities in the dataset are treated as peers
  - Peer count = total unique entities (not unique entities - 1)
  - Output excludes target-specific columns: `target_share`, `target_rate`, `target_rank`, `delta`
  - Output files named with `PEER_ONLY` identifier when no custom name provided
  - Works with both share and rate analysis

**Use cases:**

  - Market landscape analysis without a specific benchmark target
  - Exploratory analysis to understand peer distributions
  - Establishing baseline benchmarks before selecting a target entity

**Example:**

```powershell
py benchmark.py share --csv data\peers.csv --metric transaction_count --dimensions flag_domestic card_type --consistent-weights --time-col ano_mes
```

Output: `benchmark_share_PEER_ONLY_20251106_121649.xlsx`

-----

## Multi-rate analysis

Analyze both approval and fraud rates simultaneously by specifying both `--approved-col` and `--fraud-col`.

**Key features:**

  - **Shared weights**: Privacy-constrained weights are calculated ONCE based on the shared denominator (`--total-col`)
  - **Single Excel file**: Both rate types combined in one report with side-by-side columns in each dimension sheet
  - **Combined dimension sheets**: Each dimension shows both approval and fraud metrics together for easy comparison
      - Approval columns: `Approval_Entity_Rate`, `Approval_Peer_Avg`, `Approval_Peer_BIC`, `Approval_Gap`
      - Fraud columns: `Fraud_Entity_Rate`, `Fraud_Peer_Avg`, `Fraud_Peer_BIC`, `Fraud_Gap`
      - Color-coded headers: Green for approval metrics, orange for fraud metrics
  - **Debug mode enhancements**: With `--debug` flag, dimension sheets include:
      - **Original metrics**: Unweighted peer averages and total volumes before privacy adjustments are applied
      - **Weight effect**: Shows the impact of privacy weighting in percentage points (Balanced Average - Original Average)
      - **Share analysis columns**: Original Peer Average (%), Original Total Volume, Weight Effect (pp)
      - **Rate analysis columns**: Original Peer Average (%), Original Total Numerator, Original Total Denominator, Weight Effect (pp)
      - Peer count per category
  - Approval rates: 85th percentile BIC (higher is better)
  - Fraud rates: 15th percentile BIC (lower is better)
  - Privacy compliance: Constraints applied to the common denominator ensure consistent privacy across both analyses

**Rationale:**
Since both approval and fraud rates share the same denominator, the privacy constraints are based on the total volume. This allows calculating weights once and applying them to both numerators, ensuring efficiency and consistency. Combining metrics in the same dimension sheet enables direct side-by-side comparison.

**Example:**

```powershell
py benchmark.py rate --csv data\transactions.csv --total-col amt_total --approved-col amt_approved --fraud-col amt_fraud --dimensions product_group flag_domestic --consistent-weights --time-col year_month --debug --output benchmark_analysis.xlsx
```

Output: `benchmark_analysis.xlsx` (single file with combined dimension sheets showing both approval and fraud metrics)

-----

## Time-aware consistency (advanced)

When `--time-col` is specified with `--consistent-weights`, the tool enforces a time-aware consistency model:

**Conceptual strategy:**

  - The same peer weights must work across **all time periods** and **all time-category combinations**
  - Monthly weighted volumes must follow privacy rules for each month
  - Monthly weighted volumes for each category of each dimension must follow privacy rules for each month-category combination

**Technical implementation:**

  - Expands the LP formulation to include constraints for each time period
  - Adds monthly total volume constraints: `m_p * vol_{p,month} ≤ cap * Σ_j m_j * vol_{j,month}`
  - Adds monthly category constraints: `m_p * vol_{p,month,cat} ≤ cap * Σ_j m_j * vol_{j,month,cat}`
  - Single set of weights `m_p` satisfies privacy rules across all time-dimension-category combinations

**Usage:**

```powershell
py benchmark.py share --csv data\sample.csv --entity "BANCO SANTANDER" --metric transaction_count --auto --consistent-weights --time-col ano_mes
```

This ensures temporal consistency: peer weights remain constant across months while satisfying privacy constraints in every month and category combination.

-----

## Weighting engine (deep dive)

Terminology

  - v\_{p,c}: Raw volume for peer p in category c (across all chosen dimensions when solving globally).
  - m\_p: Peer multiplier (weight) constrained to [min\_weight, max\_weight].
  - cap: The privacy cap (e.g., 0.35 for 7/35) for the dimension’s peer count.
  - tol: Tolerance in percentage points, modeled as slack penalty strength.

Global LP formulation

  - Decision variables: m\_p ≥ 0, absolute‑deviation auxiliaries t^+\_p, t^-*p, cap slack s*{p,c} ≥ 0, and optional rank slacks.
  - Adjusted concentration per (p,c): a\_{p,c}(m) = m\_p v\_{p,c} − cap · Σ\_j m\_j v\_{j,c}.
  - Cap constraints with slacks: a\_{p,c}(m) − s\_{p,c} ≤ 0.
  - Bounds: min\_weight ≤ m\_p ≤ max\_weight.
  - Objective (rank‑preserving, L1 around 1):
      - Minimize Σ\_p (t^+*p + t^-*p) + λ\_rank · Φ\_rank(m) + λ\_cap · Σ*{p,c} s*{p,c},
      - with t^+\_p − t^-\_p = m\_p − 1 to encode |m\_p − 1|.
      - Rank term Φ\_rank promotes preserving the original peer order (strength derived from `--volume-preservation`).
  - Slack penalty λ\_cap ≈ 100 / tolerance\_pp so that lower tolerance increases the cost of relaxing caps.
  - Solver: SciPy `linprog` (HiGHS). Automatic fallback among HiGHS variants; captures diagnostics (max/sum slack, method used).

Behavior and fallbacks

1)  Full‑set LP attempt (rank term applied). If infeasible and `--prefer-slacks-first` is set, a second probe sets rank strength to 0 to see if slacks can make it solvable; heavy slack usage is flagged in logs and validation.
2)  Auto subset search (`--auto-subset-search`): Two modes available:
      - **Greedy mode (default)**: `--greedy-subset-search` removes the most unbalanced dimension one at a time with attempts to re‑add; returns the largest feasible global dimension set and associated weights.
      - **Random mode**: `--no-greedy-subset-search` randomly tests dimension subsets starting with n-1 combinations, then n-2, continuing until a feasible solution is found or max tests reached. Stops as soon as a feasible subset at the current size is found (no need to test smaller subsets).
      - All attempts are recorded in the Subset Search tab.
3)  Greedy dimension dropping: If still infeasible, drop dimensions until feasible.
4)  Per‑dimension solves: For dimensions dropped from the global set, compute per‑dimension LP weights or use the heuristic; ensure each dimension is still privacy‑compliant.

Heuristic (when LP is unavailable or as fallback)

  - Iteratively down‑weights violators (peers near/over cap) and up‑weights under‑represented peers within [min,max], guided by the cap gap and a soft rank preservation pull.
  - Stops after `--max-iterations` or when all categories validate.

Balanced Peer Average (used in reports)

  - For share: Σ\_p metric\_p × adjusted\_share\_p with adjusted\_share capped by the privacy rule.
  - For rate: Weighted by adjusted totals to form a balanced peer rate.

-----

## Structural infeasibility diagnostics

Goal: Determine when constraints cannot be satisfied regardless of m within bounds.

For each (dimension, category, peer):

  - Compute minimal possible adjusted share of peer p if everyone else takes their most favorable bounds:
      - min\_adj\_share\_p = (min\_w · v\_{p}) / (min\_w · v\_{p} + max\_w · Σ\_{j≠p} v\_{j}).
  - If min\_adj\_share\_p \> cap + tolerance, the category is structurally infeasible (no feasible m exists).

Outputs

  - Structural Summary tab: Per dimension counts of infeasible categories/peers and worst margins over cap.
  - Structural Detail tab: Row‑level diagnostics with dimension, category, peer, min\_adj\_share, cap, tolerance, and margin.

Use these to decide whether to merge/re‑bin categories, relax bounds, or exclude specific dimensions from the global set.

-----

## Excel report contents

  - **Summary**: Inputs, data info, applied privacy rule, BIC, methodology notes; LP/Slack diagnostics; Rank Changes (Top Movers); and the list of analyzed dimensions with category counts.
  - **One sheet per dimension**:
      - With target entity: Target share/rate, Balanced Peer Average, Distance (pp), and BIC
      - Peer-only mode: Only peer distribution metrics (no target columns)
      - **Debug mode**: When `--debug` is enabled, dimension sheets include original (unweighted) metrics:
          - Share analysis: Original Peer Average (%), Original Total Volume, Weight Effect (pp)
          - Rate analysis: Original Peer Average (%), Original Total Numerator, Original Total Denominator, Weight Effect (pp)
      - **Multi-rate analysis**: When both approval and fraud rates are analyzed, they are combined into a **single Excel file**. Dimension sheets will show approval and fraud metrics side-by-side with color-coded columns (green for approval, orange for fraud).
  - **Peer Weights** (debug mode): Shows both balanced (privacy-weighted) and unbalanced (original) volumes and shares for each peer, including multipliers and weight effect analysis.
  - **Weight Methods**: For every dimension × peer, the method used (Global LP, Per‑dimension LP, Global weights (dropped), etc.) and the multiplier.
  - **Subset Search**: Ordered attempts describing which dimensions were tried, success/failure, and slack stats.
  - **Structural Summary and Structural Detail**: Diagnostic sheets described above.
  - **Rank Changes**: Peer baseline vs adjusted share ranks and deltas (Peer, Base\_Share\_%, Adjusted\_Share\_%, Base\_Rank, Adjusted\_Rank, Delta).

-----

## Tuning recipes

  - **Include more dimensions globally**: Lower `--rank/--volume-preservation` strength, loosen bounds (higher `--max-weight`, lower `--min-weight`), and enable `--auto-subset-search`.
  - **Avoid masking violations**: Prefer disabling `--prefer-slacks-first` for production. If enabled, verify slack totals in logs and the Subset Search results.
  - **Tight vs loose tolerance**: Lower `--tolerance` raises slack penalty (harder to use slacks). Higher tolerance allows limited slack but validation will still flag cap breaches.
  - **Greedy vs Random subset search**:
      - Use greedy mode (default) for faster, deterministic results when you want to quickly find a feasible subset.
      - Use random mode (`--no-greedy-subset-search`) when greedy gets stuck or you want to explore different dimension combinations. Random mode tests all size n-1 subsets (shuffled) before moving to n-2, potentially finding better global solutions at the cost of more computation.
      - Increase `--subset-search-max-tests` (e.g., 500-1000) for random mode to allow more exploration.
  - **Time-aware consistency**:
      - Use `--time-col` with `--consistent-weights` when you need weights that remain constant across time periods.
      - This creates significantly more constraints (time periods × categories) and may require looser bounds or higher tolerance.
      - Consider using `--max-cap-slack 0.1` to allow minimal slack when time constraints make the problem very constrained.
  - **Peer-only mode**: Omit `--entity` to analyze peer distributions without a target. Useful for market landscape analysis or exploratory work before selecting a benchmark target.
  - **Multi-rate analysis**: Specify both `--approved-col` and `--fraud-col` to analyze approval and fraud rates simultaneously with a single command, generating a combined report.

-----

## Project structure

  - `benchmark.py`: CLI entry point and Excel writer.
  - `core/`
      - `dimensional_analyzer.py`: Share/Rate computation, LP/heuristic weighting, subset search, diagnostics.
      - `data_loader.py`: CSV loading, normalization, auto dimension discovery.
      - `privacy_validator.py`, `report_generator.py`: Helpers.
  - `utils/`
      - `config_manager.py`: Column mappings, presets, optional SQL config.
      - `logger.py`: Logging setup.
  - `data/`: Example datasets (sensitive data should be redacted).
  - `old/`: Legacy notebooks/scripts.

-----

## Troubleshooting

  - **Column not found**: Prefer standardized names or extend `config_manager.py` mappings.
  - **Too few peers (\<4)**: Tool warns; results may not meet minimum privacy requirements.
  - **LP infeasible**: Inspect Structural tabs; consider relaxing bounds or removing problematic dimensions; enable `--auto-subset-search`.
  - **Missing Peer Weights**: Add `--debug`.
  - **Excel write error**: If the file is open, PowerShell locks it. Save to a new filename or close the workbook.
  - **Multi-rate analysis not running both**: Ensure both `--approved-col` and `--fraud-col` are specified.
  - **Peer-only mode not working**: Verify `--entity` parameter is completely omitted (not empty string).

-----

## Additional documentation

  - **PEER\_ONLY\_MODE.md**: Detailed guide on peer-only analysis mode, including use cases and technical implementation
  - **MULTI\_RATE\_ANALYSIS.md**: Complete documentation for simultaneous approval and fraud rate analysis
  - **TIME\_DIMENSION\_OUTPUT.md**: Guide to time-dimension combination output when `--time-col` is specified
  - **DEBUG\_ORIGINAL\_METRICS.md**: Documentation for original (unweighted) metrics shown in debug mode
  - **PEER\_WEIGHTS\_TAB.md**: Complete guide to the Peer Weights tab showing balanced and unbalanced volumes/shares
  - **TIME\_AWARE\_CONSISTENCY.md**: (if exists) Deep dive into time-aware constraint formulation

-----

## Compliance note

This tool enforces per‑category peer concentration caps aligned with Mastercard Control 3.2. It does not anonymize inputs; handle source data securely and validate outputs per your organization’s standards.
