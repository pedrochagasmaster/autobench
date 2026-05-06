# Core Technical Documentation

This document provides a comprehensive, file-by-file description of the core logic in the Peer Benchmark Tool. It focuses on the `core/` folder and explains how data flows through loading, validation, privacy enforcement, optimization, diagnostics, and reporting. It also lists potential improvements and risks discovered during review.

-------------------------------------------------------------------------------
Documentation Layers (Read by audience)
-------------------------------------------------------------------------------
Level 0 - Executive summary and intent
Level 1 - System overview and operational flows
Level 2 - Deep technical details, algorithms, and edge cases
Appendices - Data schemas, configuration mapping, and glossary

-------------------------------------------------------------------------------
Level 0 - Executive Summary (What this tool does)
-------------------------------------------------------------------------------
The Peer Benchmark Tool computes privacy-compliant benchmarks by comparing a
target entity against a peer group across multiple dimensions (e.g., card type,
domestic vs. international) while enforcing Mastercard Control 3.2 privacy caps.

In short:
- It ingests aggregated transaction data in "long" format.
- It normalizes and validates inputs (optional but default).
- It builds per-dimension privacy constraints.
- It solves for peer weight multipliers that keep any peer below the privacy cap.
- It applies those weights to compute balanced peer averages and best-in-class
  benchmarks, producing Excel/CSV/JSON reports.

Business intent alignment:
- Presets encode analysis goals (strict compliance, strategic consistency, low
  distortion), which are converted to solver parameters through ConfigManager.
- The core engine (DimensionalAnalyzer + solvers) uses only merged config,
  ensuring presets and overrides determine actual behavior.

-------------------------------------------------------------------------------
Level 1 - System Overview (How modules interact)
-------------------------------------------------------------------------------
High-level pipeline:

  Input CSV/SQL
      |
      v
  DataLoader -> normalize -> optional validation (ValidationRunner)
      |
      v
  CategoryBuilder -> privacy categories (optionally time-aware)
      |
      v
  DimensionalAnalyzer
      |   \__ LPSolver (global LP)
      |   \__ HeuristicSolver (additional constraints, fallbacks)
      |   \__ DiagnosticsEngine (structural infeasibility)
      v
  Per-dimension analysis (share/rate, BIC)
      |
      v
  ReportGenerator (Excel/CSV/JSON; publication and audit outputs)

Key integration invariants:
- All solver behavior is controlled by the merged config, not raw CLI args.
- Privacy rules (5/25, 6/30, 7/35, 10/40, 4/35 merchant-only) are automatically
  selected based on peer count.
- Time-aware consistency (if time column provided) adds cross-time constraints,
  requiring a single weight set to satisfy all periods simultaneously.

-------------------------------------------------------------------------------
Level 1 - Practical Usage Patterns (Executive to Ops)
-------------------------------------------------------------------------------
Common modes:
1) Global consistency (default)
   - One set of weights across all dimensions.
   - Best for dashboards and cross-dimension comparability.
2) Per-dimension weights
   - Each dimension solved independently.
   - Higher feasibility, lower consistency.
3) Time-aware consistency
   - Adds constraints per time period; more strict.
4) Peer-only mode
   - No target entity. Produces peer averages and BIC only.

Operational branches:
- Validation enabled? If disabled, analysis proceeds even with data warnings.
- LP success? If not, subset search or heuristic fallback is used.
- Additional constraints? Enforced if rule is 6/30, 7/35, 10/40 and bucket is
  representative (dynamic constraints may relax enforcement).

-------------------------------------------------------------------------------
Level 1 - What "Balanced" Means (Conceptual)
-------------------------------------------------------------------------------
Balanced values are calculated using weighted peer totals. The weights are
privacy-constrained multipliers that ensure no peer dominates beyond the rule.

For a category c:
  Balanced total = sum(peer_volume[p,c] * weight[p])   # peers only
  Balanced share (target) = target_volume / (target_volume + Balanced total)

For rate metrics:
  Balanced rate = sum(weighted peer numerators) / sum(weighted peer denominators)

-------------------------------------------------------------------------------
Level 2 - Detailed Technical Model (Algorithms & Constraints)
-------------------------------------------------------------------------------
The core solves an optimization problem to find per-peer multipliers m_i that
minimize distortion while satisfying privacy caps and (optionally) rank
preservation. It uses a linear program (LP) with slack variables and a fallback
heuristic solver for additional constraints or infeasible cases.

LP variables:
  m_i      = peer multipliers (bounded)
  t_plus   = positive deviation from 1.0
  t_minus  = negative deviation from 1.0
  s_cap    = slack for cap constraints
  s_rank   = slack for rank preservation constraints

Objective (simplified):
  minimize sum(t_plus + t_minus)
           + lambda_cap * sum(s_cap)
           + rank_preservation_strength * sum(s_rank)

Cap constraints for each category and peer:
  (1 - cap) * v_i <= cap * sum_j v_j
  where v_i is weighted category volume for peer i

Rank preservation:
  If peer A has higher baseline volume than B, constrain the weighted volumes
  to preserve that ordering, optionally using only neighbor pairs.

Slack interpretation:
  Slack percent is reported in two ways:
  - Relative to total category volume (sum over all categories)
  - Relative to total peer volume (more intuitive for thresholds)

Heuristic solver:
  Uses L-BFGS-B to minimize penalty of cap violations and additional constraints
  (tier thresholds for 6/30, 7/35, 10/40). It optionally relaxes enforcement in
  low-representativeness buckets using dynamic thresholds.

-------------------------------------------------------------------------------
Level 2 - Time-Aware Constraints (Cross-period consistency)
-------------------------------------------------------------------------------
When time_column is provided and consistent weights are enabled:
- The CategoryBuilder creates two constraint types:
  1) Monthly totals: a privacy constraint per peer per time period.
  2) Monthly category constraints: privacy constraints per category per period.
- All constraints must be satisfied by a single weight vector.

This produces more stable longitudinal comparisons at the cost of feasibility.

-------------------------------------------------------------------------------
Level 2 - Failure Modes and Recovery Paths
-------------------------------------------------------------------------------
1) LP succeeds with slack
   - If slack exceeds threshold and trigger_subset_on_slack is true, subset
     search tries to drop dimensions to eliminate slack.

2) LP fails (infeasible)
   - If prefer_slacks_first is enabled, retries with rank penalty removed.
   - Otherwise, subset search attempts to find a feasible dimension subset.
   - Dropped dimensions are solved per-dimension (LP first, heuristic if needed).

3) Additional constraints violated
   - Heuristic solver runs with the LP solution as target weights, attempting
     to meet tier thresholds.

4) Insufficient peers
   - If privacy rule selection returns "insufficient", the run aborts rather
     than silently emitting identity-weight output.

-------------------------------------------------------------------------------
Level 2 - Observability and Diagnostics
-------------------------------------------------------------------------------
Diagnostics are generated at multiple points:
- Structural diagnostics: detect infeasible categories given min/max weights.
- Rank changes: measure how balancing changes peer ordering.
- Privacy validation: per-category compliance, including dynamic threshold notes.
- Impact analysis: raw vs balanced effects (share and rate).

These diagnostics feed both debug sheets and validation outputs.

-------------------------------------------------------------------------------
Level 2 - Performance and Determinism
-------------------------------------------------------------------------------
Performance considerations:
- LP constraint count grows with (categories * peers).
- Rank constraints can be O(P^2); neighbor mode reduces cost.
- Time-aware consistency multiplies constraints across time periods.

Determinism:
- Greedy subset search is deterministic.
- Random subset search is non-deterministic by design.
- L-BFGS-B results can vary slightly due to numeric precision.

## Scope

Included files:
- core/__init__.py
- core/validation_runner.py
- core/data_loader.py
- core/category_builder.py
- core/diagnostics_engine.py
- core/privacy_validator.py
- core/report_generator.py
- core/dimensional_analyzer.py
- core/solvers/__init__.py
- core/solvers/base_solver.py
- core/solvers/lp_solver.py
- core/solvers/heuristic_solver.py

## End-to-End Core Flow

1) Load and normalize data
- DataLoader reads CSV or SQL sources and normalizes column names.

2) Validate input (optional)
- ValidationRunner calls DataLoader validators for share or rate analysis, logs issues, and decides whether to abort on errors.

3) Build privacy categories
- CategoryBuilder aggregates by entity and dimension, optionally adding time-aware constraints.

4) Compute diagnostics and solve privacy weights
- DimensionalAnalyzer orchestrates weight optimization and diagnostics.
- DiagnosticsEngine provides infeasibility and imbalance diagnostics.
- LPSolver attempts a global LP with cap and rank constraints.
- HeuristicSolver (L-BFGS-B) handles additional constraints and fallback cases.

5) Analyze dimensions
- DimensionalAnalyzer computes per-dimension share or rate results, including balanced peer averages and Best-in-Class (BIC) percentiles.

6) Produce reports
- ReportGenerator writes Excel/CSV/JSON outputs and optional audit and publication workbooks.

## Interaction Model and Core Integration

This section explains how the core modules interact with each other and with configuration/presets to deliver results. While this document focuses on `core/`, the orchestration points (CLI/TUI and config management) are critical to understanding real-world usage.

### High-level interaction graph

1) CLI/TUI provides inputs
- Data source: CSV path or SQL source.
- Analysis type: share or rate.
- Target entity: optional.
- Dimensions: explicit or auto-detected.
- Preset/config: expresses intent.
- Output flags: debug sheets, publication format, validation, distortion, etc.

2) ConfigManager resolves intent into parameters
- Configuration hierarchy (lowest to highest):
  - Defaults
  - Preset (YAML in presets/)
  - Custom config file (YAML/JSON)
  - CLI overrides
- Resulting merged config drives core behavior.

3) Core pipeline executes
- DataLoader normalizes and validates data.
- DimensionalAnalyzer computes privacy weights and per-dimension results.
- ReportGenerator assembles outputs.

### Core-to-core dependencies

- DimensionalAnalyzer depends on:
  - CategoryBuilder to build constraint categories.
  - DiagnosticsEngine for infeasibility and imbalance diagnostics.
  - LPSolver and HeuristicSolver for weight optimization.
  - PrivacyValidator for rule selection and additional constraint evaluation.

- ValidationRunner depends on:
  - DataLoader validators to evaluate input data quality.

- ReportGenerator consumes:
  - DimensionalAnalyzer outputs (results, weights, diagnostics, validation).

### Configuration-to-core mapping (intent -> behavior)

Below are the primary config paths (typically set via presets) and how they translate into core behavior:

- optimization.linear_programming.tolerance
  - Mapped to DimensionalAnalyzer.tolerance.
  - Controls allowed cap slack and share violation threshold (cap + tolerance).
  - Influences LP slack penalty in LPSolver (via 100 / tolerance).

- optimization.linear_programming.rank_constraints.mode / neighbor_k
  - Mapped to DimensionalAnalyzer.rank_constraint_mode / rank_constraint_k.
  - Controls whether rank preservation uses all pairs or neighbor pairs.

- optimization.linear_programming.max_iterations
  - Mapped to DimensionalAnalyzer.max_iterations.
  - Passed into LPSolver (linprog maxiter).

- optimization.bounds.max_weight / min_weight
  - Mapped to DimensionalAnalyzer max/min weight bounds.
  - Used in LPSolver bounds and in HeuristicSolver bounds.
  - Used in DiagnosticsEngine to estimate structural infeasibility.

- optimization.constraints.volume_preservation
  - Mapped to DimensionalAnalyzer.rank_preservation_strength.
  - Controls the penalty for rank inversions in LPSolver.

- optimization.subset_search.enabled / strategy / max_attempts / trigger_on_slack / max_slack_threshold / prefer_slacks_first
  - Mapped to DimensionalAnalyzer subset search and slack behavior.
  - Determines whether to drop dimensions or accept slack.

- optimization.linear_programming.volume_weighted_penalties / volume_weighting_exponent
  - Mapped to DimensionalAnalyzer volume-weighted slack penalties, used by LPSolver.
  - Emphasizes protecting large categories.

- optimization.constraints.enforce_additional_constraints
  - Enables Control 3.2 additional constraints (6/30, 7/35, 10/40) in heuristic optimization.

- optimization.constraints.dynamic_constraints.*
  - Mapped to DimensionalAnalyzer dynamic constraints parameters.
  - Governs whether additional constraints are enforced in sparse buckets.

- optimization.constraints.consistency_mode
  - Mapped to DimensionalAnalyzer.consistent_weights to select global vs per-dimension weighting.

- optimization.constraints.enforce_single_weight_set
  - Mapped to DimensionalAnalyzer.enforce_single_weight_set.
  - When true, disables subset search/dimension dropping/per-dimension re-weighting and keeps one global weight-set.

- optimization.bayesian.max_iterations / optimization.bayesian.learning_rate
  - Mapped to HeuristicSolver max iterations and finite-difference step size.

- analysis.best_in_class_percentile
  - Mapped to DimensionalAnalyzer.bic_percentile.
  - Defines BIC percentile for share and rate metrics.

- analysis.merchant_mode
  - Mapped to DimensionalAnalyzer.merchant_mode.
  - Allows the 4/35 rule if peer count is 4.

- input.validate_input / input.validation_thresholds
  - Used by ValidationRunner + DataLoader validators.

- input.schema_detection_mode
  - Controls DataLoader schema detection: heuristic, mapped (column_mappings only), or hybrid (mappings then heuristic).

- output.include_debug_sheets, include_privacy_validation, include_impact_summary
  - Controls which outputs are produced; enforced in Excel report generation via metadata.

- output.output_format / output.fraud_in_bps
  - Determines whether analysis output, publication output, or both are written.
  - Controls fraud rate conversion for publication workbooks.

## Canonical Dataflows and Usage Patterns

This section describes concrete, real-world dataflows as they execute through the core modules.

### Execution branches and decision points

These are the main branch points that change the core execution path:

1) Validation enabled?
- If input.validate_input is false, ValidationRunner is skipped and analysis proceeds regardless of data issues.

2) Target entity provided?
- If target_entity is None, peer-only mode is used:
  - No target share/rate columns are produced.
  - Peer averages and BIC are still computed.

3) consistent_weights enabled?
- If true, DimensionalAnalyzer computes a global solution using categories across all dimensions.
- If false, each dimension is analyzed independently without global weighting.

4) time_column provided and present in data?
- If yes and consistent_weights is true:
  - Time-aware categories are built.
  - Global LP must satisfy all time-period constraints.
- If no, categories are built without time constraints.

5) LP solver success?
- If LP succeeds:
  - If slack exceeds threshold and trigger_subset_on_slack is true, subset search may still be triggered (unless enforce_single_weight_set is true).
- If LP fails:
  - prefer_slacks_first may retry with relaxed rank penalty.
  - subset search or dimension dropping is used to salvage a feasible set (unless enforce_single_weight_set is true).

6) Additional constraints enforcement?
- If rule is 6/30, 7/35, or 10/40 and enforce_additional_constraints is true:
  - HeuristicSolver may re-optimize to satisfy additional tiers.
  - Dynamic constraints may skip low-representativeness buckets.

7) Per-dimension violations after global solve?
- If violations remain in specific dimensions:
  - Per-dimension LP is attempted (with zero tolerance), unless enforce_single_weight_set is true.
  - HeuristicSolver is used if per-dimension LP fails (and enforce_single_weight_set is false).

8) Output toggles and diagnostics
- If include_privacy_validation is enabled, build_privacy_validation_dataframe is produced.
- If include_impact_summary or analyze_distortion is enabled, impact calculations are performed.
- Debug mode (include_debug_sheets) adds weights and diagnostic tables.

### A) Share analysis with target entity (most common)

1) DataLoader
- CSV is read and normalized.
- Entity, metric, and dimension column names are expected to match normalized names.

2) ValidationRunner (if enabled)
- DataLoader.validate_share_input checks:
  - Required columns exist.
  - Nulls and negative values.
  - Minimum peer count.
  - Target entity presence.

3) DimensionalAnalyzer (consistent_weights on or off)
- If consistent_weights is True:
  - CategoryBuilder builds categories across all dimensions.
  - LPSolver attempts global weights.
  - If infeasible, subset search or dimension dropping is attempted.
  - HeuristicSolver may be used to enforce additional constraints.
  - Weights are stored in global_weights and per_dimension_weights.

- If consistent_weights is False:
  - No global weights are computed.
  - Each dimension is analyzed with its own peer aggregation (unweighted).

4) analyze_dimension_share
- For each dimension (and for each time period if time-aware):
  - Computes balanced peer average (privacy-weighted).
  - Computes BIC percentile across peers.
  - Computes target share and distance to peers.

5) Optional impact/validation outputs
- build_privacy_validation_dataframe produces per-category compliance details.
- calculate_share_impact produces raw vs balanced share impacts.
- calculate_impact_summary aggregates impacts by dimension.

6) ReportGenerator
- Writes summary and per-dimension sheets.
- Optionally includes debug, validation, and distortion/impact sheets.

### B) Share analysis in peer-only mode (no target entity)

1) DataLoader and ValidationRunner behave the same, but target entity checks are skipped.
2) DimensionalAnalyzer computes balanced peer averages, but no target columns are emitted.
3) analyze_dimension_share outputs peer averages and BIC only.
4) Reports omit target-specific fields.

### C) Rate analysis with target entity

1) DataLoader normalizes columns and validators check:
- Denominator presence, numerators, nulls, numerator > denominator, low denominators.

2) DimensionalAnalyzer global weight computation (if consistent_weights is True)
- Weights are computed using total_col as the metric basis for balancing.
- The same global weights are applied across all rate metrics.

3) analyze_dimension_rate
- For each dimension and time period:
  - Balanced peer rate is computed using weighted numerators/denominators.
  - BIC percentile is computed (fraud rates invert percentile).
  - Target rate and distance to peers are computed.

4) Optional impact summaries
- calculate_rate_impact and calculate_impact_summary for rate impacts.

5) ReportGenerator writes rate-specific outputs.

### D) Time-aware consistency (time_column provided, consistent_weights=True)

1) CategoryBuilder.build_time_aware_categories builds two constraint types:
- Monthly totals (TIME_TOTAL constraints).
- Monthly per-category constraints.

2) DimensionalAnalyzer global LP must satisfy all time-aware constraints simultaneously.

3) analyze_dimension_share/analyze_dimension_rate outputs:
- Per time period rows plus a General (all time periods) row.

4) build_privacy_validation_dataframe includes time_period in compliance rows.

### E) Preset comparison or distortion analysis (optional outputs)

- The core contributes these outputs via:
  - calculate_share_impact / calculate_rate_impact
  - calculate_impact_summary
  - build_privacy_validation_dataframe
- Reporting decides whether to include these artifacts based on output config.

## Presets and Intent Translation

Presets live in presets/ and encode user intent as a set of configuration overrides. The intent is captured in comments inside the YAML files and is operationalized by ConfigManager's merge logic.

### Preset selection guide (quick intent map)

Preset | Primary intent | Compliance strictness | Consistency goal | Distortion tolerance | Typical use case
--- | --- | --- | --- | --- | ---
balanced_default | Balanced compliance vs consistency | Medium | Medium | Medium | Day-to-day benchmarking
compliance_strict | Regulatory compliance | High (0.0 tolerance) | Medium | Low | Audit/regulatory reporting
strategic_consistency | Single global weights | Low to Medium | High (no dimension dropping) | Medium to High | Executive dashboards
research_exploratory | Feasibility on hard data | Medium | Low | High | Sparse/difficult datasets
low_distortion | Minimize distortion (identity weights) | Low | High | Very Low | Accuracy-first comparisons
minimal_distortion | Max accuracy, privacy relaxed | Lowest | Low | Highest | Exploratory or internal-only use

### Preset resolution and hierarchy

- Defaults are loaded first.
- Preset YAML is merged on top.
- Custom config file is merged on top of preset.
- CLI overrides apply last.

This order allows:
- Presets to define a base intent.
- Project-specific config files to refine behavior.
- CLI flags to make a specific run deviate without editing files.

### Intent-to-parameter mapping (core-relevant)

The following mappings are the main way presets translate intent into core behavior:

- Global consistency vs flexibility
  - optimization.subset_search.enabled
    - false: never drop dimensions (forces a single global solution).
    - true: allows dropping dimensions to preserve compliance.

- Strictness vs tolerance
  - optimization.linear_programming.tolerance
    - Low (0.0): strict compliance, likely to drop dimensions.
    - High (10-100): accept violations to preserve accuracy.

- Rank preservation
  - optimization.constraints.volume_preservation
    - High (near 1.0): preserve peer ranking.
    - Low (near 0.0): allow reordering for feasibility.

- Distortion vs compliance
  - optimization.bounds.min_weight/max_weight
    - Tight bounds (1.0/1.0): minimal distortion, fewer compliance options.
    - Wide bounds (0.001/50): high flexibility, more compliance options.

- Slack prioritization
  - optimization.subset_search.prefer_slacks_first
    - true: relax rank preservation first, accept slack if needed.
    - false: drop dimensions rather than accept slack.

- Additional constraints enforcement
  - optimization.constraints.enforce_additional_constraints
  - optimization.constraints.dynamic_constraints.*
    - If enabled, additional constraints are enforced only when category buckets are sufficiently representative.

### Preset-by-preset intent translation

This section explains how each preset config changes core behavior and which intended usage it targets.

#### balanced_default
Intent: balanced compliance and consistency.
Key effects:
- tolerance 2.0: allows small violations.
- subset_search enabled and random: will drop dimensions if needed after some slack tolerance.
- volume_preservation 1.0: strong rank preservation.
- Outcome: usually global weights, but will drop dimensions if slack grows.

#### compliance_strict
Intent: regulatory compliance.
Key effects:
- tolerance 0.0: no cap violations allowed.
- subset_search enabled and greedy: drops most unbalanced dimension first.
- volume_preservation 0.95: preserve rank but allow slight flexibility.
- Outcome: strong compliance, possible per-dimension weights for dropped dimensions.

#### strategic_consistency
Intent: single global weights for strategic dashboards.
Key effects:
- subset_search disabled: dimensions are never dropped.
- constraints.enforce_single_weight_set: true (disables per-dimension re-weighting fallback).
- tolerance 25.0: large slack tolerance to preserve global weights.
- volume_weighted_penalties enabled: prioritize large categories.
- Outcome: single global weights even if some violations remain.

#### research_exploratory
Intent: any feasible solution for hard datasets.
Key effects:
- max_weight 20.0 and min_weight 0.005: high flexibility.
- tolerance 5.0: relaxed compliance.
- subset_search random with prefer_slacks_first: more willingness to accept slack.
- Outcome: increased feasibility and coverage, potential rank changes.

#### low_distortion
Intent: minimal distortion in output metrics.
Key effects:
- min_weight = max_weight = 1.0: identity weights (no reweighting).
- tolerance 10.0: allow violations to preserve accuracy.
- subset_search disabled: no dimension dropping.
- Outcome: outputs stay close to raw, compliance may be violated.

#### minimal_distortion
Intent: maximum accuracy with minimal concern for privacy.
Key effects:
- very wide bounds and high tolerance.
- low volume_preservation: allow large reordering.
- subset_search disabled: no dimension dropping.
- Outcome: maximum freedom for raw-like outputs; privacy caps likely violated.

## Interaction Notes: Practical Usage Patterns

### Consistent weights vs per-dimension weights

- Consistent weights (global):
  - One set of multipliers across all dimensions.
  - Highest consistency across output tables.
  - Risk: infeasibility; requires fallback logic.

- Per-dimension weights:
  - Separate multipliers per dimension.
  - Higher feasibility and compliance per dimension.
  - Lower cross-dimension consistency.

### Subset search vs slack acceptance

- Subset search enabled:
  - Attempts to remove dimensions that cause infeasibility.
  - Produces a mix of global and per-dimension weights.

- Slack acceptance (prefer_slacks_first or high tolerance):
  - Keeps global solution even if it violates some caps.
  - Intended for strategic or exploratory use.

### Additional constraints enforcement (Control 3.2)

- Additional constraints are enforced via HeuristicSolver.
- Dynamic enforcement skips constraints in low-representativeness buckets.
- This is a key bridge between strict regulatory compliance and practical feasibility.

-------------------------------------------------------------------------------
Level 2 - Detailed Pipeline Walkthrough (Step-by-step)
-------------------------------------------------------------------------------
This section expands the core flow into concrete steps and data structures.

Step 1: Input normalization
- DataLoader reads CSV/SQL into a DataFrame.
- Column names are normalized to lowercase with underscores and collision-safe
  suffixes (e.g., "Rate (%)" and "Rate (#)" -> "rate" and "rate_5").

Step 2: Optional validation
- ValidationRunner reads input.validate_input and input.validation_thresholds.
- It runs DataLoader.validate_share_input or validate_rate_input.
- Errors stop the run; warnings are logged and analysis continues.
- For merchant_mode, min_peer_count is lowered to 4 to permit 4/35.

Step 3: Category construction
- CategoryBuilder aggregates per peer per dimension category.
- For each category:
  - category_volume = peer's volume inside the category
  - volume = peer's total volume across all categories in the dimension
  - share_pct = category_volume / volume (for diagnostic context)
- If consistent_weights and time_column, time-aware constraints are added:
  - TIME_TOTAL constraints (per time period)
  - TIME_CATEGORY constraints (per category per period)

Step 4: Privacy rule selection
- PrivacyValidator.select_rule chooses one of 4/35, 5/25, 6/30, 7/35, 10/40
  based on peer count (with merchant_mode allowing 4 peers).

Step 5: Global LP attempt
- LPSolver builds one cap constraint per (category, peer).
- Rank constraints preserve baseline ordering based on overall peer volumes.
- LP solves for multipliers that minimize deviation from 1.0.
- Slack statistics are recorded for downstream decisions.

Step 6: Slack handling and subset search
- If slack exceeds threshold and trigger_subset_on_slack is true:
  - subset search finds the largest feasible dimension subset.
  - Removed dimensions are solved per-dimension.
- If LP fails:
  - prefer_slacks_first may retry with rank penalty removed.
  - Otherwise subset search or per-dimension fallback is triggered.

Step 7: Additional constraints enforcement
- If rule has tiers (6/30, 7/35, 10/40) and enforce_additional_constraints:
  - HeuristicSolver runs using LP weights as targets.
  - Dynamic constraints may relax enforcement in low-representativeness buckets.

Step 8: Per-dimension analysis
- analyze_dimension_share:
  - Balanced peer average (weighted), BIC percentile, target share, and delta.
- analyze_dimension_rate:
  - Balanced rate, BIC percentile, target rate, and delta.

Step 9: Diagnostics and reporting
- privacy_validation_df: compliance per category (including dynamic thresholds).
- rank_changes_df: baseline vs adjusted ranking shifts.
- impact summaries: raw vs balanced effects.
- ReportGenerator writes analysis and optional publication/audit outputs.

-------------------------------------------------------------------------------
Level 2 - Mathematical Definitions (Core Computations)
-------------------------------------------------------------------------------
Notation:
  p = peer
  c = category (dimension category or time-aware category)
  v_{p,c} = peer volume in category c
  m_p = peer multiplier (weight)
  cap = max concentration (e.g., 0.25 for 25%)

Weighted totals:
  V_c = sum_p (m_p * v_{p,c})
  share_{p,c} = (m_p * v_{p,c}) / V_c

Privacy constraint (cap):
  share_{p,c} <= cap   for all peers p and categories c

Balanced peer average (share analysis):
  balanced_peer_total_c = sum_{peer != target} m_p * v_{p,c}
  balanced_target_share_c = target_volume_c / (target_volume_c + balanced_peer_total_c)

Balanced peer rate (rate analysis):
  balanced_rate_c = sum_{peer} (m_p * numerator_{p,c}) / sum_{peer} (m_p * denom_{p,c})

Best-in-class (BIC):
  - Uses configured percentile (analysis.best_in_class_percentile).
  - For fraud, the configured analysis.fraud_percentile is used when building
    the analyzer (lower percentile represents "better").

-------------------------------------------------------------------------------
Level 2 - Subset Search Mechanics
-------------------------------------------------------------------------------
Greedy strategy:
1) Start with all dimensions.
2) If LP fails, drop the most unbalanced dimension.
3) Rebuild categories and retry until feasible or max attempts hit.

Random strategy:
1) Randomly select dimension subsets, starting with size N-1.
2) Attempt LP on each subset until feasible or max attempts hit.
3) Best feasible subset maximizes dimension count, then minimizes slack.

-------------------------------------------------------------------------------
Level 2 - Dynamic Additional Constraints
-------------------------------------------------------------------------------
Additional tier requirements (6/30, 7/35, 10/40) are enforced when:
- peer count meets minimum
- effective peer count is high enough
- volume share and representativeness pass thresholds

Dynamic threshold scaling:
- Thresholds and required counts are scaled down when buckets are sparse.
- Enforcement and relaxation counts are tracked in dynamic_constraint_stats.

-------------------------------------------------------------------------------
Level 2 - Output Semantics (What each sheet means)
-------------------------------------------------------------------------------
Analysis workbook:
- Summary: input settings and run metadata
- Per-dimension sheets: balanced averages, target metrics, BIC, deltas
- Metadata: serialized run metadata and compact summaries for non-scalar objects
- Weight Methods: which solver was used per dimension
- Peer Weights: multipliers and volumes (debug)
- Privacy Validation: per-category compliance
- Preset Comparison: per-preset impact metrics and status (if enabled)
- Impact Detail: category-level impact rows (if enabled)
- Impact Summary: aggregated distortion/impact (if enabled)

Publication workbook:
- Executive Summary plus simplified dimension sheets with clean formatting,
  optional fraud conversion to bps, and no debug-only diagnostics.

CSV/JSON:
- CSV: either a single DataFrame or per-metric outputs; balanced totals are peer-weighted totals
- JSON: metadata + results as structured records

## Preset and Config Improvement Opportunities (Core-Relevant)

1) Inconsistent subset_search key names in presets
- Some presets use max_tests but the config expects max_attempts. This can silently ignore preset settings.
- Status: addressed by mapping max_tests -> max_attempts during config merge.

2) linear_programming.lambda_penalty is unused
- Presets set lambda_penalty but LPSolver does not read it.
- This leads to intent not being enforced.
- Status: addressed by passing lambda_penalty into LPSolver as an override for cap slack penalties.

3) linear_programming.rank_penalty_weight is unused
- The rank penalty is controlled by constraints.volume_preservation in DimensionalAnalyzer, not rank_penalty_weight.
- Status: addressed by treating rank_penalty_weight as a multiplier on volume_preservation.

4) Output intent not always enforced at core level
- Many output toggles are implemented in orchestration code, not in core.
- Consider documenting or consolidating to reduce ambiguity.
- Status: addressed by enforcing output flags in the Excel report generator (metadata-driven sheet inclusion).

5) Merchant mode vs validation thresholds
- Validation default min_peer_count is 5, but merchant 4/35 is allowed with merchant_mode.
- Validation thresholds could be rule-aware to avoid false errors.
- Status: addressed by lowering validation min_peer_count to 4 when merchant_mode is enabled.

6) optimization.constraints.consistency_mode is not wired
- Config and schema support it, but core uses an explicit consistent_weights flag.
- This can misalign preset intent with actual behavior.
- Status: addressed by deriving consistent_weights from consistency_mode and mapping CLI overrides into config.

7) optimization.bayesian.* is not used by HeuristicSolver
- Presets set bayesian iterations/learning_rate, but HeuristicSolver uses fixed values.
- Status: addressed. bayesian.max_iterations is wired to heuristic maxiter and learning_rate is used as the finite-difference step size for L-BFGS-B.

8) Time-aware low_distortion could hit internal-dimension fallback errors
- Internal dimensions such as _TIME_TOTAL could be routed into user-dimension fallback paths.
- Status: addressed by filtering reserved/internal dimensions from per-dimension re-weighting paths.

9) strategic_consistency could silently use per-dimension fallback
- This weakened the intended single-global-weight behavior for dashboard consistency.
- Status: addressed via optimization.constraints.enforce_single_weight_set and strict fallback gating.


## Shared Data Structures and Conventions

### Category records
Category records are dictionaries that represent peer volumes for a specific dimension category (and optionally time period). They are produced by CategoryBuilder and consumed by solvers, diagnostics, and validation.

Common keys:
- peer: peer entity name
- dimension: dimension column name or time-aware dimension identifier
- category: category value for that dimension
- volume: peer total volume (standard) or peer totals for the time constraint
- category_volume: peer volume inside the category
- share_pct: share percentage computed during category building
- time_period: optional; present in time-aware categories
- original_dimension: optional; for time-aware categories
- original_category: optional; for time-aware categories

### Weights
- Global weights: stored in DimensionalAnalyzer.global_weights as per-peer multipliers and derived volume/share fields.
- Per-dimension weights: stored in DimensionalAnalyzer.per_dimension_weights; override global weights for specific dimensions.

### SolverResult
Standardized solver output:
- weights: dict peer -> multiplier
- method: solver label
- stats: solver statistics and diagnostics
- success: boolean

### Output DataFrames
- structural_detail_df and structural_summary_df: structural infeasibility diagnostics
- rank_changes_df: rank changes due to balancing
- privacy_validation_df: compliance validation across dimension categories
- impact dataframes: raw vs balanced share/rate impact summaries

## File-by-File Documentation

### core/__init__.py
- Exposes core classes for external imports.
- __all__ includes DimensionalAnalyzer, PrivacyValidator, DataLoader, ReportGenerator.

### core/validation_runner.py

Purpose: Shared input validation logic for share and rate analyses.

Key functions:
- _summarize_issues(issues): counts ERROR/WARNING/INFO ValidationIssue items.
- _log_validation_issue(issue): logs each issue at the appropriate severity level.
- run_input_validation(...):
  - Reads config input.validate_input and input.validation_thresholds.
  - For share: DataLoader.validate_share_input.
  - For rate: DataLoader.validate_rate_input.
  - Logs issues and decides whether analysis should abort.

### core/data_loader.py

Purpose: Load data from CSV/SQL sources, normalize columns, and validate input quality.

Key classes:
- ValidationSeverity: ERROR, WARNING, INFO.
- ValidationIssue dataclass: structured validation feedback.

Key methods:
- load_data(args): routes to CSV, SQL query, or SQL table loaders.
- load_from_csv(file_path): reads CSV, normalizes columns.
- load_from_sql_query(query_file): reads SQL file, executes query via config connection, normalizes columns.
- load_from_sql_table(table_name): queries full table, normalizes columns.
- _normalize_columns(df):
  - Lowercase and strip whitespace.
  - Replace separators with underscores.
  - Remove special characters.
  - Collapse repeated underscores.
  - Resolve naming collisions by suffixing.
- validate_minimal_schema(df): detects count/amount/entity columns using schema_detection_mode
  (mapped, heuristic, or hybrid).
- validate_full_schema(df): detects approved/total/declined/entity columns using schema_detection_mode.
- detect_schema_type(df): returns full, minimal, or unknown.
- get_available_dimensions(df): returns non-numeric, non-identifier columns.
- preprocess_data(df, fill_na=0, remove_zeros=True): fills NaNs and drops rows with all-zero numeric values.
- _match_target_entity(df, entity_col, target_entity): case-insensitive matching to canonical entity name.
- _collect_entity_validation_issues(...): checks peer count and target entity presence.
- validate_share_input(...):
  - Required columns, nulls, negative metrics.
  - Peer count and target entity checks.
  - Small category warning.
  - High concentration warning.
- validate_rate_input(...):
  - Required columns and numerators.
  - Nulls, negatives, numerator > denominator.
  - Low denominator warning.
  - Peer count and target entity checks.
  - Outlier rate warning.

### core/category_builder.py

Purpose: Create privacy constraint categories for the solvers.

Key methods:
- build_categories(df, metric_col, dimensions):
  - Aggregates by entity and dimension category.
  - For each category, excludes target entity and builds peer-specific volumes.
  - Computes per-peer share_pct (peer category volume / peer total volume).
  - Returns all_categories, peer_volumes, peers.

- build_time_aware_categories(df, metric_col, dimensions):
  - Adds time-aware constraints when consistent_weights and time_column are set.
  - Builds monthly total constraints and monthly category constraints.
  - Returns all_categories, peer_volumes, peers.

### core/diagnostics_engine.py

Purpose: Provide structural diagnostics and imbalance metrics.

Key methods:
- dimension_unbalance_scores(all_categories):
  - For each dimension, computes the maximum peer share within any category.
- compute_structural_caps_diagnostics(peers, all_categories, max_concentration):
  - Uses min/max weights to compute the minimum achievable share for each peer/category.
  - If minimum share exceeds cap + tolerance, the category is structurally infeasible.
  - Returns detail and summary dataframes.

### core/privacy_validator.py

Purpose: Enforce Control 3.2 privacy rules and concentration caps.

Rules:
- 5/25, 6/30, 7/35, 10/40, and merchant-only 4/35.

Key methods:
- select_rule(peer_count, merchant_mode=False): chooses appropriate rule.
- get_rule_config(rule_name): returns rule configuration.
- evaluate_additional_constraints(shares, rule_name): checks tier requirements.
- evaluate_additional_constraints_with_thresholds(shares, rule_name, thresholds): supports dynamic thresholds.
- validate_peer_group(peer_group, metrics, entity_column): validates min participants and concentration per metric.
- calculate_concentration(peer_group, metric, entity_column): adds concentration column.
- apply_weighting(peer_group, metric, threshold_percentage, entity_column): caps entity values to meet concentration limits.
- validate_fallback_rules(peer_group, metrics, entity_column): tries rules from strict to permissive.

### core/solvers/base_solver.py

- Defines SolverResult and the abstract PrivacySolver interface.

### core/solvers/lp_solver.py

Purpose: Solve privacy weights using linear programming (SciPy linprog Highs).

Core LP design:
- Variables: m (peer multipliers), t_plus, t_minus, s_cap (cap slack), s_rank (rank slack).
- Objective: minimize deviation from 1.0 plus cap slack penalties and optional rank penalties.
- Constraints:
  - Cap constraints per category and peer.
  - Deviation constraints: m - t_plus <= 1, -m - t_minus <= -1.
  - Rank preservation constraints, either all pairs or neighbor pairs.
- Bounds: multipliers constrained to [min_weight, max_weight], slacks >= 0.
- Tries multiple Highs methods: highs, highs-ds, highs-ipm.
- Stats include slack magnitudes, method, and constraint counts.
- Rescales weights to mean 1.0 within bounds.

### core/solvers/heuristic_solver.py

Purpose: Solve privacy weights using L-BFGS-B with penalties for violations.

Core behavior:
- Objective combines:
  - Cap violations over max_concentration + tolerance.
  - Additional constraints penalties (tier shortfalls).
  - Deviation from target weights (if provided).
- Uses dynamic enforcement based on representativeness and peer statistics.
- Normalizes weights to mean 1.0 within bounds.

Key helpers:
- _build_constraint_stats: computes participants, effective peers, volume shares, representativeness.
- _assess_additional_constraints_applicability: decides if tier constraints are enforced.
- _get_dynamic_additional_thresholds: scales thresholds based on representativeness and peer count.
- _additional_constraints_penalty: computes tier shortfall penalty.

### core/report_generator.py

Purpose: Generate reports in Excel, CSV, and JSON, plus publication and audit outputs.

Key methods:
- generate_report(results, output_file, format, analysis_type, metadata): dispatches based on format.
- _generate_excel_report: creates Summary, Metric sheets, and optional Metadata sheet.
- add_preset_comparison_sheet: adds preset comparison table to an existing workbook.
- add_distortion_summary_sheet: adds distortion summary table.
- add_data_quality_sheet: adds validation issues to a workbook.
- _generate_csv_report: writes dict summary and separate CSVs for DataFrames.
- _generate_json_report: writes JSON with metadata and results.
- create_audit_log: writes a text audit file.
- generate_publication_workbook: creates stakeholder-friendly Excel with simplified formatting.

### core/dimensional_analyzer.py

Purpose: Main engine for privacy-weighted benchmarking and dimension analysis.

Constructor parameters:
- target_entity, entity_column, bic_percentile, debug_mode
- consistent_weights, max_iterations, tolerance, max_weight, min_weight
- rank_preservation_strength, slack policies, subset search controls
- time_column for time-aware constraints
- volume-weighted penalties
- additional constraint enforcement and dynamic constraint configuration

Key attributes:
- global_weights: dict of peer multipliers and derived volumes/shares
- per_dimension_weights: dict of per-dimension overrides
- weight_methods: mapping dimension -> method label
- diagnostics: structural_detail_df, structural_summary_df, rank_changes_df, privacy_validation_df

Key methods:
- calculate_global_privacy_weights(df, metric_col, dimensions):
  - Builds all categories and selects privacy rule.
  - Computes structural diagnostics.
  - Tries global LP; falls back to subset search or dimension dropping.
  - Optionally re-optimizes with heuristic solver if additional constraints violated.
  - Applies tiny nudges for borderline cap violations.
  - Stores weights and builds validation info.

- _search_largest_feasible_subset(...):
  - Greedy or random search to find feasible dimension subsets.

- _solve_per_dimension_weights(...):
  - Solves per-dimension weights when global solution drops dimensions or violations remain.

- analyze_dimension_share(...):
  - Aggregates per dimension and time period to compute balanced peer averages and BIC.

- analyze_dimension_rate(...):
  - Similar to share analysis but for rate metrics.

- build_privacy_validation_dataframe(...):
  - Produces a per-category compliance record (original vs balanced shares).

- calculate_share_impact / calculate_rate_impact:
  - Computes raw vs balanced impact per category/time.

- calculate_impact_summary:
  - Summarizes impact distributions (mean/min/max/std).

-------------------------------------------------------------------------------
Appendix A - Glossary (Core Terms)
-------------------------------------------------------------------------------
Target entity:
- The entity being benchmarked. If omitted, analysis runs in peer-only mode.

Peer:
- Any entity in the dataset excluding the target entity.

Dimension:
- A categorical column used to segment the analysis (e.g., card_type).

Category:
- A specific value within a dimension (e.g., card_type = "DEBIT").

Category volume:
- The metric volume for a single peer inside a category.

Peer volume:
- The metric total for a peer across the full dimension (or time slice).

Multiplier (weight):
- A per-peer scaling factor applied to volumes to satisfy privacy rules.

Balanced peer average:
- A peer-only aggregate that uses privacy-weighted totals.

Best-in-class (BIC):
- A percentile-based benchmark from the peer distribution.

Slack:
- A non-negative variable in the LP that allows controlled constraint violation.

Effective peers:
- A concentration-based measure (1 / sum(share^2)), used to detect dominance.

Representativeness:
- A combined score of peer coverage and volume share, used to decide whether to
  enforce additional constraints in a bucket.

-------------------------------------------------------------------------------
Appendix B - Data Requirements (Share vs Rate)
-------------------------------------------------------------------------------
Share analysis requires:
- entity column (entity_col)
- metric column (metric_col)
- dimensions list (explicit or auto-detected)

Rate analysis requires:
- entity column (entity_col)
- total column (denominator)
- one or more numerator columns (approval, fraud)
- dimensions list (explicit or auto-detected)

All data must be aggregated in long format:
- one row per entity x dimension-category combination
- dimension columns hold category values (e.g., card_type, flag_domestic)

-------------------------------------------------------------------------------
Appendix C - Determinism and Reproducibility
-------------------------------------------------------------------------------
Deterministic modes:
- Greedy subset search is deterministic for the same input.
- LP results are deterministic given solver behavior and identical inputs.

Non-deterministic modes:
- Random subset search uses random.shuffle with no fixed seed by default.
- L-BFGS-B can have small numerical variance across platforms.

Reproducibility tips:
- Prefer greedy subset search for repeatable results.
- Fix input data ordering and use a consistent environment.

-------------------------------------------------------------------------------
Appendix D - Configuration Reference (Core-Relevant)
-------------------------------------------------------------------------------
Input:
- input.entity_col
- input.time_col
- input.schema_detection_mode
- input.validate_input / input.validation_thresholds

Optimization:
- optimization.bounds.min_weight / max_weight
- optimization.linear_programming.tolerance / max_iterations / rank_constraints
- optimization.linear_programming.volume_weighted_penalties / exponent
- optimization.linear_programming.lambda_penalty (optional)
- optimization.constraints.consistency_mode
- optimization.constraints.volume_preservation
- optimization.constraints.enforce_additional_constraints
- optimization.constraints.dynamic_constraints.*
- optimization.subset_search.*
- optimization.bayesian.max_iterations / learning_rate

Analysis:
- analysis.best_in_class_percentile
- analysis.fraud_percentile
- analysis.merchant_mode

Output:
- output.output_format
- output.include_debug_sheets
- output.include_privacy_validation
- output.include_impact_summary
- output.include_preset_comparison
- output.include_calculated_metrics
- output.fraud_in_bps

## Completeness Check
No open improvement items are tracked in this document at this time.

## Completeness Check

This documentation was cross-checked against:
- core file list
- DimensionalAnalyzer method inventory
- solver interfaces and helper functions

All classes, methods, and helpers in core were covered.
