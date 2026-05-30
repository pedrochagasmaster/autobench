"""Privacy validation DataFrame construction."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


def build_privacy_validation_dataframe(analyzer, df: pd.DataFrame, metric_col: str, dimensions: List[str]) -> pd.DataFrame:
        """Build detailed privacy validation dataframe showing original and balanced shares for each dimension-category-(time) combination."""
        validation_rows: List[Dict[str, Any]] = []
        all_categories, peer_volumes, _ = analyzer._build_categories(df, metric_col, dimensions)
        peers = list(analyzer.global_weights.keys())
        if not peers:
            per_dim_peers = set()
            for weights in analyzer.per_dimension_weights.values():
                per_dim_peers.update(weights.keys())
            peers = sorted(per_dim_peers) if per_dim_peers else sorted(peer_volumes.keys())
        peer_count = len(peers)
        if peer_count == 0:
            return pd.DataFrame()
        constraint_stats = analyzer._build_constraint_stats(all_categories, peers, peer_volumes) if all_categories else {}
        rule_name, max_concentration = analyzer._get_privacy_rule(peer_count)
        weights = {p: float(analyzer.global_weights.get(p, {}).get('multiplier', 1.0)) for p in peers}

        def append_time_total_rows(time_period: Any) -> None:
            time_df = df[df[analyzer.time_column] == time_period]
            entity_agg = time_df.groupby(analyzer.entity_column).agg({metric_col: 'sum'}).reset_index()
            peer_data = []
            for peer_entity in peers:
                peer_vol = float(entity_agg[entity_agg[analyzer.entity_column] == peer_entity][metric_col].sum())
                peer_data.append({'peer': peer_entity, 'volume': peer_vol})

            total_original_vol = sum(p['volume'] for p in peer_data)
            total_balanced_vol = sum(p['volume'] * weights.get(p['peer'], 1.0) for p in peer_data)
            for peer_info in peer_data:
                peer = peer_info['peer']
                peer_weight = weights.get(peer, 1.0)
                original_share = (peer_info['volume'] / total_original_vol * 100.0) if total_original_vol > 0 else 0.0
                balanced_vol = peer_info['volume'] * peer_weight
                balanced_share = (balanced_vol / total_balanced_vol * 100.0) if total_balanced_vol > 0 else 0.0
                is_violation = analyzer._is_share_violation(balanced_share, max_concentration)
                validation_rows.append({
                    'Dimension': '_TIME_TOTAL_',
                    'Time_Period': time_period,
                    'Category': str(time_period),
                    'Peer': peer,
                    'Rule_Name': rule_name,
                    'Weight_Source': 'Global',
                    'Weight_Method': analyzer.weight_methods.get('_TIME_TOTAL_', 'Global-LP'),
                    'Multiplier': peer_weight,
                    'Original_Volume': peer_info['volume'],
                    'Original_Share_%': round(original_share, 4),
                    'Balanced_Volume': balanced_vol,
                    'Balanced_Share_%': round(balanced_share, 4),
                    'Privacy_Cap_%': max_concentration,
                    'Tolerance_%': analyzer.tolerance,
                    'Additional_Constraints_Enforced': 'No',
                    'Additional_Constraints_Relaxed': 'No',
                    'Additional_Constraints_Passed': 'Yes',
                    'Additional_Constraint_Detail': 'Time total cap validation',
                    'Structural_Infeasible_Peer': 'No',
                    'Structural_Infeasible_Category': 'No',
                    'Structural_Margin_Peer_pp': 0.0,
                    'Structural_Margin_Category_pp': 0.0,
                    'Compliant': 'No' if is_violation else 'Yes',
                    'Violation_Margin_%': round(balanced_share - max_concentration, 4) if is_violation else 0.0,
                })

        # Structural diagnostics are peer-level, keyed by (dimension, category, peer).
        # Expose both peer-level and category-level infeasibility markers in validation output.
        structural_peer_margin: Dict[Tuple[str, str, str], float] = {}
        structural_category_margin: Dict[Tuple[str, str], float] = {}
        if analyzer.structural_detail_df is not None and not analyzer.structural_detail_df.empty:
            for row in analyzer.structural_detail_df.itertuples(index=False):
                dimension_key = str(getattr(row, 'dimension', ''))
                category_key = str(getattr(row, 'category', ''))
                peer_key = str(getattr(row, 'peer', ''))
                margin = float(getattr(row, 'margin_over_cap_pp', 0.0) or 0.0)
                if margin <= 0:
                    continue
                peer_lookup = (dimension_key, category_key, peer_key)
                cat_lookup = (dimension_key, category_key)
                structural_peer_margin[peer_lookup] = max(structural_peer_margin.get(peer_lookup, 0.0), margin)
                structural_category_margin[cat_lookup] = max(structural_category_margin.get(cat_lookup, 0.0), margin)

        for dimension in dimensions:
            dim_weights = dict(weights)
            if dimension in analyzer.per_dimension_weights:
                dim_weights.update(analyzer.per_dimension_weights[dimension])
            weight_source = "Per-Dimension" if dimension in analyzer.per_dimension_weights else "Global"
            weight_method = analyzer.weight_methods.get(dimension, "Global-LP")
            if analyzer.time_column and analyzer.time_column in df.columns:
                time_periods = analyzer._get_time_periods(df)
                for time_period in time_periods:
                    time_df = df[df[analyzer.time_column] == time_period]
                    entity_dim_agg = time_df.groupby([analyzer.entity_column, dimension]).agg({metric_col: 'sum'}).reset_index()
                    for category in entity_dim_agg[dimension].unique():
                        cat_df = entity_dim_agg[entity_dim_agg[dimension] == category]
                        structural_dim = f"{dimension}_{analyzer.time_column}"
                        structural_cat = f"{category}_{time_period}"
                        peer_data = []
                        for peer_entity in peers:
                            peer_cat_vol = float(cat_df[cat_df[analyzer.entity_column] == peer_entity][metric_col].sum())
                            peer_data.append({'peer': peer_entity, 'volume': peer_cat_vol})
                        total_original_vol = sum(p['volume'] for p in peer_data)
                        total_balanced_vol = sum(p['volume'] * dim_weights.get(p['peer'], 1.0) for p in peer_data)
                        balanced_shares: List[float] = []
                        for peer_info in peer_data:
                            peer_weight = dim_weights.get(peer_info['peer'], 1.0)
                            balanced_vol = peer_info['volume'] * peer_weight
                            balanced_share = (balanced_vol / total_balanced_vol * 100.0) if total_balanced_vol > 0 else 0.0
                            balanced_shares.append(balanced_share)

                        peer_category_volumes = {p['peer']: p['volume'] for p in peer_data}
                        stats = constraint_stats.get((f"{dimension}_{analyzer.time_column}", f"{category}_{time_period}", time_period))
                        enforce, reason, thresholds, relaxed = analyzer._assess_additional_constraints_applicability(
                            rule_name, dimension, peer_category_volumes, stats
                        )
                        if enforce:
                            additional_passed, additional_details = analyzer._evaluate_additional_constraints(
                                balanced_shares, rule_name, thresholds
                            )
                            threshold_detail = f" Thresholds={thresholds}" if thresholds else ""
                            additional_detail = "; ".join(additional_details) if additional_details else ""
                            additional_detail = f"{additional_detail}{threshold_detail}".strip()
                            additional_enforced = "Yes"
                        else:
                            additional_passed = True
                            additional_enforced = "No"
                            if reason == 'no_additional':
                                additional_detail = "Not applicable"
                            else:
                                additional_detail = f"Skipped ({reason})"
                        additional_relaxed = "Yes" if relaxed else "No"

                        for idx, peer_info in enumerate(peer_data):
                            peer, peer_vol = peer_info['peer'], peer_info['volume']
                            peer_weight = dim_weights.get(peer, 1.0)
                            original_share = (peer_vol / total_original_vol * 100.0) if total_original_vol > 0 else 0.0
                            balanced_vol = peer_vol * peer_weight
                            balanced_share = balanced_shares[idx]
                            is_violation = analyzer._is_share_violation(balanced_share, max_concentration)
                            compliant = (not is_violation) and additional_passed
                            violation_margin = balanced_share - max_concentration if is_violation else 0.0
                            structural_peer_pp = structural_peer_margin.get((structural_dim, structural_cat, str(peer)), 0.0)
                            structural_category_pp = structural_category_margin.get((structural_dim, structural_cat), 0.0)
                            validation_rows.append({
                                'Dimension': dimension,
                                'Time_Period': time_period,
                                'Category': category,
                                'Peer': peer,
                                'Rule_Name': rule_name,
                                'Weight_Source': weight_source,
                                'Weight_Method': weight_method,
                                'Multiplier': peer_weight,
                                'Original_Volume': peer_vol,
                                'Original_Share_%': round(original_share, 4),
                                'Balanced_Volume': balanced_vol,
                                'Balanced_Share_%': round(balanced_share, 4),
                                'Privacy_Cap_%': max_concentration,
                                'Tolerance_%': analyzer.tolerance,
                                'Additional_Constraints_Enforced': additional_enforced,
                                'Additional_Constraints_Relaxed': additional_relaxed,
                                'Additional_Constraints_Passed': 'Yes' if additional_passed else 'No',
                                'Additional_Constraint_Detail': additional_detail,
                                'Structural_Infeasible_Peer': 'Yes' if structural_peer_pp > 0 else 'No',
                                'Structural_Infeasible_Category': 'Yes' if structural_category_pp > 0 else 'No',
                                'Structural_Margin_Peer_pp': round(structural_peer_pp, 4) if structural_peer_pp > 0 else 0.0,
                                'Structural_Margin_Category_pp': round(structural_category_pp, 4) if structural_category_pp > 0 else 0.0,
                                'Compliant': 'Yes' if compliant else 'No',
                                'Violation_Margin_%': round(violation_margin, 4) if violation_margin > 0 else 0.0
                            })
                for time_period in time_periods:
                    append_time_total_rows(time_period)
            else:
                entity_dim_agg = df.groupby([analyzer.entity_column, dimension]).agg({metric_col: 'sum'}).reset_index()
                for category in entity_dim_agg[dimension].unique():
                    cat_df = entity_dim_agg[entity_dim_agg[dimension] == category]
                    structural_dim = str(dimension)
                    structural_cat = str(category)
                    peer_data = []
                    for peer_entity in peers:
                        peer_cat_vol = float(cat_df[cat_df[analyzer.entity_column] == peer_entity][metric_col].sum())
                        peer_data.append({'peer': peer_entity, 'volume': peer_cat_vol})
                    total_original_vol = sum(p['volume'] for p in peer_data)
                    total_balanced_vol = sum(p['volume'] * dim_weights.get(p['peer'], 1.0) for p in peer_data)
                    balanced_shares: List[float] = []
                    for peer_info in peer_data:
                        peer_weight = dim_weights.get(peer_info['peer'], 1.0)
                        balanced_vol = peer_info['volume'] * peer_weight
                        balanced_share = (balanced_vol / total_balanced_vol * 100.0) if total_balanced_vol > 0 else 0.0
                        balanced_shares.append(balanced_share)

                    peer_category_volumes = {p['peer']: p['volume'] for p in peer_data}
                    stats = constraint_stats.get((dimension, category, None))
                    enforce, reason, thresholds, relaxed = analyzer._assess_additional_constraints_applicability(
                        rule_name, dimension, peer_category_volumes, stats
                    )
                    if enforce:
                        additional_passed, additional_details = analyzer._evaluate_additional_constraints(
                            balanced_shares, rule_name, thresholds
                        )
                        threshold_detail = f" Thresholds={thresholds}" if thresholds else ""
                        additional_detail = "; ".join(additional_details) if additional_details else ""
                        additional_detail = f"{additional_detail}{threshold_detail}".strip()
                        additional_enforced = "Yes"
                    else:
                        additional_passed = True
                        additional_enforced = "No"
                        if reason == 'no_additional':
                            additional_detail = "Not applicable"
                        else:
                            additional_detail = f"Skipped ({reason})"
                    additional_relaxed = "Yes" if relaxed else "No"

                    for idx, peer_info in enumerate(peer_data):
                        peer, peer_vol = peer_info['peer'], peer_info['volume']
                        peer_weight = dim_weights.get(peer, 1.0)
                        original_share = (peer_vol / total_original_vol * 100.0) if total_original_vol > 0 else 0.0
                        balanced_vol = peer_vol * peer_weight
                        balanced_share = balanced_shares[idx]
                        is_violation = analyzer._is_share_violation(balanced_share, max_concentration)
                        compliant = (not is_violation) and additional_passed
                        violation_margin = balanced_share - max_concentration if is_violation else 0.0
                        structural_peer_pp = structural_peer_margin.get((structural_dim, structural_cat, str(peer)), 0.0)
                        structural_category_pp = structural_category_margin.get((structural_dim, structural_cat), 0.0)
                        validation_rows.append({
                            'Dimension': dimension,
                            'Time_Period': None,
                            'Category': category,
                            'Peer': peer,
                            'Rule_Name': rule_name,
                            'Weight_Source': weight_source,
                            'Weight_Method': weight_method,
                            'Multiplier': peer_weight,
                            'Original_Volume': peer_vol,
                            'Original_Share_%': round(original_share,  4),
                            'Balanced_Volume': balanced_vol,
                            'Balanced_Share_%': round(balanced_share, 4),
                            'Privacy_Cap_%': max_concentration,
                            'Tolerance_%': analyzer.tolerance,
                            'Additional_Constraints_Enforced': additional_enforced,
                            'Additional_Constraints_Relaxed': additional_relaxed,
                            'Additional_Constraints_Passed': 'Yes' if additional_passed else 'No',
                            'Additional_Constraint_Detail': additional_detail,
                            'Structural_Infeasible_Peer': 'Yes' if structural_peer_pp > 0 else 'No',
                            'Structural_Infeasible_Category': 'Yes' if structural_category_pp > 0 else 'No',
                            'Structural_Margin_Peer_pp': round(structural_peer_pp, 4) if structural_peer_pp > 0 else 0.0,
                            'Structural_Margin_Category_pp': round(structural_category_pp, 4) if structural_category_pp > 0 else 0.0,
                            'Compliant': 'Yes' if compliant else 'No',
                            'Violation_Margin_%': round(violation_margin, 4) if violation_margin > 0 else 0.0
                        })
        return pd.DataFrame(validation_rows)
