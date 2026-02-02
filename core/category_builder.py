import logging
from typing import Dict, List, Any, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


class CategoryBuilder:
    """Builds dimension categories for privacy constraints."""

    RESERVED_INTERNAL_PREFIX = "_TIME_"
    TIME_TOTAL_DIMENSION_PREFIX = "_TIME_TOTAL_"

    def __init__(
        self,
        entity_column: str,
        target_entity: Optional[str],
        time_column: Optional[str],
        consistent_weights: bool
    ) -> None:
        self.entity_column = entity_column
        self.target_entity = target_entity
        self.time_column = time_column
        self.consistent_weights = consistent_weights

    @classmethod
    def is_internal_dimension_name(cls, dimension: Any) -> bool:
        """Return True when the dimension name is reserved for internal constraints."""
        return str(dimension).startswith(cls.RESERVED_INTERNAL_PREFIX)

    @classmethod
    def validate_dimension_names(cls, dimensions: List[str]) -> None:
        """Reject user dimensions that collide with reserved internal prefixes."""
        for dim in dimensions:
            if cls.is_internal_dimension_name(dim):
                raise ValueError(
                    f"Dimension '{dim}' uses reserved prefix '{cls.RESERVED_INTERNAL_PREFIX}'. "
                    "Please rename the source column."
                )

    def build_categories(
        self,
        df: pd.DataFrame,
        metric_col: str,
        dimensions: List[str]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, float], List[str]]:
        """Aggregate by entity and dimension categories for the given dimensions."""
        self.validate_dimension_names(dimensions)
        if self.time_column and self.consistent_weights:
            return self.build_time_aware_categories(df, metric_col, dimensions)

        all_categories: List[Dict[str, Any]] = []
        for dim in dimensions:
            entity_dim_agg = df.groupby([self.entity_column, dim]).agg({metric_col: 'sum'}).reset_index()
            entity_totals = entity_dim_agg.groupby(self.entity_column)[metric_col].sum()
            categories = entity_dim_agg[dim].unique()
            for category in categories:
                category_df = entity_dim_agg[entity_dim_agg[dim] == category].copy()
                if self.target_entity is not None:
                    peer_df = category_df[category_df[self.entity_column] != self.target_entity]
                else:
                    peer_df = category_df
                for peer_entity in peer_df[self.entity_column].unique():
                    peer_category_vol = peer_df[peer_df[self.entity_column] == peer_entity][metric_col].sum()
                    peer_total_vol = entity_totals[peer_entity]
                    peer_share_pct = (peer_category_vol / peer_total_vol * 100) if peer_total_vol > 0 else 0
                    all_categories.append({
                        'peer': peer_entity,
                        'dimension': dim,
                        'category': category,
                        'volume': peer_total_vol,
                        'category_volume': peer_category_vol,
                        'share_pct': peer_share_pct
                    })
        peers = list(set([c['peer'] for c in all_categories]))
        peer_volumes: Dict[str, float] = {}
        for cat in all_categories:
            if cat['peer'] not in peer_volumes:
                peer_volumes[cat['peer']] = cat['volume']
        return all_categories, peer_volumes, peers

    def build_time_aware_categories(
        self,
        df: pd.DataFrame,
        metric_col: str,
        dimensions: List[str]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, float], List[str]]:
        """Build categories that include time-aware constraints for consistent weights."""
        self.validate_dimension_names(dimensions)
        if not self.time_column:
            return self.build_categories(df, metric_col, dimensions)

        if self.time_column not in df.columns:
            logger.warning(
                "Time column '%s' not found in data. Falling back to standard aggregation.",
                self.time_column
            )
            return self.build_categories(df, metric_col, dimensions)

        logger.info("Building time-aware categories using time column: %s", self.time_column)

        all_categories: List[Dict[str, Any]] = []
        time_periods = sorted(df[self.time_column].dropna().unique())
        logger.info("Found %s time periods: %s", len(time_periods), time_periods)

        for time_period in time_periods:
            time_df = df[df[self.time_column] == time_period]
            entity_totals = time_df.groupby(self.entity_column)[metric_col].sum()
            if self.target_entity is not None:
                peer_totals = entity_totals[entity_totals.index != self.target_entity]
            else:
                peer_totals = entity_totals

            for peer_entity in peer_totals.index:
                peer_monthly_vol = peer_totals[peer_entity]
                all_categories.append({
                    'peer': peer_entity,
                    'dimension': f'{self.TIME_TOTAL_DIMENSION_PREFIX}{self.time_column}',
                    'category': time_period,
                    'volume': float(peer_totals.sum()),
                    'category_volume': peer_monthly_vol,
                    'share_pct': (peer_monthly_vol / peer_totals.sum() * 100) if peer_totals.sum() > 0 else 0,
                    'time_period': time_period,
                    'original_dimension': '_TIME_TOTAL',
                    'original_category': time_period
                })

        for time_period in time_periods:
            time_df = df[df[self.time_column] == time_period]
            for dim in dimensions:
                if dim == self.time_column:
                    continue

                entity_dim_agg = time_df.groupby([self.entity_column, dim]).agg({metric_col: 'sum'}).reset_index()
                categories = entity_dim_agg[dim].unique()

                for category in categories:
                    category_df = entity_dim_agg[entity_dim_agg[dim] == category].copy()
                    if self.target_entity is not None:
                        peer_df = category_df[category_df[self.entity_column] != self.target_entity]
                    else:
                        peer_df = category_df

                    total_time_cat_vol = peer_df[metric_col].sum()
                    for peer_entity in peer_df[self.entity_column].unique():
                        peer_category_vol = peer_df[peer_df[self.entity_column] == peer_entity][metric_col].sum()
                        all_categories.append({
                            'peer': peer_entity,
                            'dimension': f'{dim}_{self.time_column}',
                            'category': f'{category}_{time_period}',
                            'volume': total_time_cat_vol,
                            'category_volume': peer_category_vol,
                            'share_pct': (peer_category_vol / total_time_cat_vol * 100) if total_time_cat_vol > 0 else 0,
                            'time_period': time_period,
                            'original_dimension': dim,
                            'original_category': category
                        })

        peer_volumes: Dict[str, float] = {}
        entity_totals = df.groupby(self.entity_column)[metric_col].sum()
        if self.target_entity is not None:
            peer_totals = entity_totals[entity_totals.index != self.target_entity]
        else:
            peer_totals = entity_totals
        for peer_entity in peer_totals.index:
            peer_volumes[peer_entity] = float(peer_totals[peer_entity])

        peers = list(peer_volumes.keys())
        logger.info(
            "Built %s time-aware category constraints for %s peers across %s time periods",
            len(all_categories),
            len(peers),
            len(time_periods)
        )

        return all_categories, peer_volumes, peers
