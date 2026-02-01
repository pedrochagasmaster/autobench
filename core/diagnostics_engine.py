from typing import Dict, List, Any, Optional, Tuple

import pandas as pd


class DiagnosticsEngine:
    """Computes structural diagnostics and unbalance scores."""

    def __init__(
        self,
        min_weight: float,
        max_weight: float,
        tolerance: float,
        time_column: Optional[str]
    ) -> None:
        self.min_weight = float(min_weight)
        self.max_weight = float(max_weight)
        self.tolerance = float(tolerance)
        self.time_column = time_column

    def dimension_unbalance_scores(
        self,
        all_categories: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """Return max category concentration (in percent) observed per dimension."""
        scores: Dict[str, float] = {}
        dim_cat_totals: Dict[Tuple[str, Any], float] = {}
        for c in all_categories:
            key = (c['dimension'], c['category'])
            dim_cat_totals[key] = dim_cat_totals.get(key, 0.0) + float(c['category_volume'])
        dim_max: Dict[str, float] = {}
        for c in all_categories:
            key = (c['dimension'], c['category'])
            denom = dim_cat_totals.get(key, 0.0)
            frac = (float(c['category_volume']) / denom) if denom > 0 else 0.0
            dim_max[c['dimension']] = max(dim_max.get(c['dimension'], 0.0), frac)
        for d, v in dim_max.items():
            scores[d] = v * 100.0
        return scores

    @staticmethod
    def build_constraint_stats(
        categories: List[Dict[str, Any]],
        peers: List[str],
        peer_volumes: Dict[str, float]
    ) -> Dict[Tuple[str, Any, Optional[Any]], Dict[str, float]]:
        """Build per-constraint representativeness and concentration diagnostics."""
        overall_total = float(sum(peer_volumes.values()))
        dim_time_totals: Dict[Tuple[str, Optional[Any]], float] = {}
        category_totals: Dict[Tuple[str, Any, Optional[Any]], float] = {}
        peer_sets: Dict[Tuple[str, Any, Optional[Any]], set] = {}
        volumes_by_key: Dict[Tuple[str, Any, Optional[Any]], List[float]] = {}

        for cat in categories:
            key = (cat['dimension'], cat['category'], cat.get('time_period'))
            dim_time_key = (cat['dimension'], cat.get('time_period'))
            vol = float(cat.get('category_volume', 0.0))
            category_totals[key] = category_totals.get(key, 0.0) + vol
            dim_time_totals[dim_time_key] = dim_time_totals.get(dim_time_key, 0.0) + vol
            if key not in peer_sets:
                peer_sets[key] = set()
                volumes_by_key[key] = []
            if vol > 0:
                peer_sets[key].add(cat['peer'])
            volumes_by_key[key].append(vol)

        stats: Dict[Tuple[str, Any, Optional[Any]], Dict[str, float]] = {}
        peer_total = max(len(peers), 1)
        for key, total in category_totals.items():
            dim_time_key = (key[0], key[2])
            dim_total = float(dim_time_totals.get(dim_time_key, 0.0))
            participants = float(len(peer_sets.get(key, set())))
            eff_peers = 0.0
            if total > 0:
                shares_sq = 0.0
                for volume in volumes_by_key.get(key, []):
                    share = volume / total
                    shares_sq += share * share
                eff_peers = (1.0 / shares_sq) if shares_sq > 0 else 0.0

            volume_share = (total / dim_total) if dim_total > 0 else 0.0
            overall_share = (total / overall_total) if overall_total > 0 else 0.0
            peer_fraction = participants / float(peer_total)
            coverage = max(volume_share, overall_share)
            representativeness = (peer_fraction * coverage) ** 0.5 if peer_fraction > 0 and coverage > 0 else 0.0

            stats[key] = {
                'participants': participants,
                'effective_peers': eff_peers,
                'category_total': total,
                'dimension_total': dim_total,
                'volume_share': volume_share,
                'overall_share': overall_share,
                'representativeness': max(0.0, min(1.0, representativeness)),
            }

        return stats

    def compute_structural_caps_diagnostics(
        self,
        peers: List[str],
        all_categories: List[Dict[str, Any]],
        max_concentration: float,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        cap = float(max_concentration)
        tol = float(self.tolerance)
        dim_cat_totals: Dict[Tuple[str, Any], float] = {}
        for c in all_categories:
            key = (c['dimension'], c['category'])
            dim_cat_totals[key] = dim_cat_totals.get(key, 0.0) + float(c['category_volume'])
        rows: List[Dict[str, Any]] = []
        for c in all_categories:
            key = (c['dimension'], c['category'])
            v_p = float(c['category_volume'])
            total_cat = float(dim_cat_totals.get(key, 0.0))
            others = max(total_cat - v_p, 0.0)
            denom = self.min_weight * v_p + self.max_weight * others
            min_adj_share = (self.min_weight * v_p / denom * 100.0) if denom > 0 else 0.0
            margin = min_adj_share - cap - tol
            if margin > 0:
                rows.append({
                    'dimension': c['dimension'],
                    'category': c['category'],
                    'peer': c['peer'],
                    'min_adj_share_%': round(min_adj_share, 6),
                    'cap_%': cap,
                    'tolerance_pp': tol,
                    'margin_over_cap_pp': round(margin, 6),
                })
        detail_df = pd.DataFrame(rows)
        if detail_df.empty:
            summary_df = pd.DataFrame(columns=['dimension', 'infeasible_categories', 'infeasible_peers', 'worst_margin_pp'])
        else:
            grp = detail_df.groupby(['dimension', 'category']).size().reset_index(name='violating_peers')
            cat_counts = grp.groupby('dimension').size().rename('infeasible_categories')
            peer_counts = detail_df.groupby('dimension').size().rename('infeasible_peers')
            worst = detail_df.groupby('dimension')['margin_over_cap_pp'].max().rename('worst_margin_pp')
            summary_df = pd.concat([cat_counts, peer_counts, worst], axis=1).reset_index()
        return detail_df, summary_df
