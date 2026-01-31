# Code Review Findings

**Date:** 2026-01-29
**Scope:** Core Logic (`core/`)
**Reviewer:** Principal Software Engineer / Code Review Architect

## Change Summary
Implemented dynamic privacy constraints, refined weight optimization logic with a new "nudge" pass, and improved validation reporting.

## Findings

### 1. File: `core/dimensional_analyzer.py`

#### L604: [HIGH] O(N^2) performance bottleneck in `_nudge_borderline_cap_excess`
The loop iterates over `all_categories`, and for each iteration, it performs a list comprehension over `all_categories` again to find matching categories. With a large dataset, this quadratic complexity will cause significant slowdowns. Pre-group categories by their key outside the loop.

**Suggested change:**
```python
        if not worst_peer:
            return weights

        # Pre-group categories to avoid O(N^2) lookup
        grouped_cats: Dict[Tuple, List[Dict[str, Any]]] = {}
        for cat in all_categories:
            key = (cat['dimension'], cat['category'], cat.get('time_period'))
            if key not in grouped_cats:
                grouped_cats[key] = []
            grouped_cats[key].append(cat)

        for cat in all_categories:
            if dimension_filter:
                # ... existing filter checks ...
                if cat['dimension'] in dimension_filter:
                    pass
                elif self.time_column and any(
                    cat['dimension'].startswith(f"{dim}_{self.time_column}")
                    for dim in dimension_filter
                ):
                    pass
                else:
                    continue

            if cat['peer'] not in weights:
                continue

            # O(1) lookup instead of O(N) scan
            key = (cat['dimension'], cat['category'], cat.get('time_period'))
            matching_cats = grouped_cats.get(key, [])

            total_weighted = sum(c['category_volume'] * weights[c['peer']] for c in matching_cats)
            # ... rest of the loop ...
```

#### L1551: [HIGH] Redundant static calculations inside optimization loop
In `_solve_dimension_weights_heuristic`, the `objective` function rebuilds `peer_cat_vols` and calls `_assess_additional_constraints_applicability` in every iteration. Since `dim_categories` and `stats` are constant during optimization, these should be pre-calculated outside the `objective` function to drastically improve convergence speed.

**Suggested change:**
```python
        # Pre-calculate static data for objective function
        constraint_data = {}
        for key, cat_indices in constraint_map.items():
            dim, _, _ = key
            matching_cats = [dim_categories[i] for i in cat_indices]
            peer_cat_vols = {p: 0.0 for p in peers}
            for cat in matching_cats:
                peer_cat_vols[cat['peer']] = float(cat.get('category_volume', 0.0))
            
            stats = constraint_stats.get(key)
            rep_weight = self._representativeness_weight(stats)
            
            # Check applicability once
            enforce = False
            thresholds = None
            if self.enforce_additional_constraints and rule_name:
                if not min_entities_check:
                    # Handle structural failure case (if needed)
                    pass 
                else:
                    enforce, _, thresholds, _ = self._assess_additional_constraints_applicability(
                        rule_name, dim, peer_cat_vols, stats
                    )
            
            constraint_data[key] = {
                'peer_cat_vols': peer_cat_vols,
                'rep_weight': rep_weight,
                'enforce': enforce,
                'thresholds': thresholds
            }

        # Objective function: minimize violations + deviation from target
        def objective(weight_array):
            # ...
            for key, _ in constraint_map.items():
                data = constraint_data[key]
                peer_cat_vols = data['peer_cat_vols']
                rep_weight = data['rep_weight']
                
                total_weighted = sum(peer_cat_vols[p] * weight_array[peer_index[p]] for p in peers)
                # ...
                        if self._is_share_violation(adjusted_share, max_concentration):
                            excess = adjusted_share - max_share
                            violation_penalty += rep_weight * (excess ** 2)

                if data['enforce']:
                     additional_penalty += rep_weight * self._additional_constraints_penalty(
                        shares, rule_name, data['thresholds']
                     )
            # ...
```

### 2. File: `core/report_generator.py`

#### L75: [MEDIUM] Overly aggressive column exclusion in `_should_convert_rate_column`
The check `if 'total' in col_lower: return False` prevents any column containing "total" from being treated as a rate, even valid rates like `total_approval_rate` or `total_fraud_rate`. This will cause these columns to be formatted incorrectly (as decimals instead of percentages) in the report.

**Suggested change:**
```python
    @staticmethod
    def _should_convert_rate_column(column_name: str, convert_all_rates: bool) -> bool:
        col_lower = str(column_name).lower()
        if 'weight_effect' in col_lower or 'effect' in col_lower:
            return False
        # Only exclude 'total' if it likely refers to a count/volume, not a rate
        if 'total' in col_lower and not ('rate' in col_lower or '%' in col_lower):
            return False
        
        is_rate_like = (
            '%' in col_lower
            or 'rate' in col_lower
# ...
```
