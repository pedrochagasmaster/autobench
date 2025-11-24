# Preset Refactoring Plan: Intent-Based Configuration

## Objective
Transition from parameter-centric presets (e.g., "flexible_dimensions") to intent-centric presets (e.g., "strategic_consistency") to make the tool more intuitive and aligned with real-world business scenarios.

## Core Philosophy
Users should choose a preset based on **what they value most**:
1.  **Compliance**: "I cannot have any privacy violations."
2.  **Consistency**: "I need one set of weights for all dimensions."
3.  **Balance**: "I want a good report with minimal fuss."
4.  **Exploration**: "This dataset is difficult, just give me numbers."

## Proposed Presets

### 1. `compliance_strict.yaml` (formerly `strict_privacy`)
**Intent:** Regulatory reporting and external audits.
**Priority:** Zero privacy violations.
**Trade-off:** May drop dimensions (calculate them separately), leading to different weights for different parts of the report.
**Key Settings:**
*   `tolerance`: 0.0 (Strict)
*   `subset_search.enabled`: true (Drop dimensions if needed)
*   `subset_search.strategy`: "greedy" (Deterministic dropping of worst offenders)
*   `volume_preservation`: 0.95 (High, but allow slight reordering)

### 2. `strategic_consistency.yaml` (formerly `global_with_violations`)
**Intent:** Internal strategic analysis and executive dashboards.
**Priority:** Global consistency (one set of weights).
**Trade-off:** Will allow privacy violations in specific categories, but minimizes their business impact.
**Key Settings:**
*   `tolerance`: 25.0 (High, allows violations)
*   `subset_search.enabled`: false (Never drop dimensions)
*   `volume_weighted_penalties`: true (Critical: prioritize high-volume categories)
*   `volume_weighting_exponent`: 1.5 (Strong emphasis on protecting large categories)

### 3. `balanced_default.yaml` (formerly `standard`)
**Intent:** Day-to-day analysis.
**Priority:** Good balance of compliance and consistency.
**Trade-off:** Allows very small violations (1-2%) before dropping dimensions.
**Key Settings:**
*   `tolerance`: 2.0 (Small buffer)
*   `subset_search.enabled`: true
*   `subset_search.trigger_on_slack`: true (If slack > buffer, drop dimension)

### 4. `research_exploratory.yaml` (formerly `maximum_flexibility`)
**Intent:** Data exploration and difficult datasets.
**Priority:** Finding *any* feasible solution.
**Trade-off:** Lower rank preservation, higher weight bounds.
**Key Settings:**
*   `bounds.max_weight`: 20.0
*   `constraints.volume_preservation`: 0.5

## Implementation Steps

1.  **Create new preset files** based on the specifications above.
2.  **Update `benchmark.py`** to recognize new presets (if hardcoded) or just rely on the file existence.
3.  **Update `README.md`** to explain the new "Intent-Based" selection guide.
4.  **Deprecate** old presets (move to `presets/legacy/` or keep for compatibility but hide from list).

## Specific Adjustments to `global_with_violations` (-> `strategic_consistency`)
*   **Issue:** Current tolerance (65.0) is too loose.
*   **Fix:** Reduce to 25.0. This forces the optimizer to try harder, while still allowing necessary violations.
*   **Enhancement:** Increase `volume_weighting_exponent` to 1.5 to ensure that if we *do* violate, it's almost exclusively in negligible categories.

## Specific Adjustments to `strict_privacy` (-> `compliance_strict`)
*   **Issue:** Can be too rigid and fail to find solutions even when close.
*   **Fix:** Switch `subset_search.strategy` to `greedy`. This is more robust than `random` for strict compliance because it systematically removes the single worst dimension until the rest solve perfectly.
