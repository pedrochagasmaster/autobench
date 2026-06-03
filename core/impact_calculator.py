"""Impact calculation between raw and privacy-balanced metrics."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from core.contracts import WeightLookup

logger = logging.getLogger(__name__)


def build_weight_map_for_dimension(analyzer, dimension: str) -> Dict[str, float]:
    return WeightLookup.from_analyzer(analyzer).map_for_dimension(dimension)


def calculate_share_impact(
    analyzer,
    df: pd.DataFrame,
    metric_col: str,
    dimensions: List[str],
    target_entity: Optional[str] = None,
    weight_lookup: Optional[WeightLookup] = None,
) -> pd.DataFrame:
    """Calculate impact between raw and balanced market share."""
    entity = target_entity or analyzer.target_entity
    if not entity:
        logger.warning("No target entity specified for impact calculation")
        return pd.DataFrame()

    if metric_col not in df.columns:
        logger.error(f"Metric column '{metric_col}' not found in DataFrame")
        return pd.DataFrame()

    if df[metric_col].isna().any():
        nan_count = df[metric_col].isna().sum()
        logger.warning(
            f"Metric column '{metric_col}' contains {nan_count} NaN values - these rows will be excluded"
        )
        df = df[df[metric_col].notna()].copy()

    if (df[metric_col] < 0).any():
        neg_count = (df[metric_col] < 0).sum()
        logger.warning(
            f"Metric column '{metric_col}' contains {neg_count} negative values - these rows will be excluded"
        )
        df = df[df[metric_col] >= 0].copy()

    if df.empty:
        logger.warning("No valid data remaining after filtering NaN/negative values")
        return pd.DataFrame()

    impact_rows: List[Dict[str, Any]] = []
    weights = weight_lookup or WeightLookup.from_analyzer(analyzer)

    for dimension in dimensions:
        dim_weights = weights.map_for_dimension(dimension)

        if analyzer.time_column and analyzer.time_column in df.columns:
            time_periods = analyzer._get_time_periods(df)
            null_count = df[analyzer.time_column].isna().sum()
            if null_count > 0:
                logger.warning(
                    f"Time column '{analyzer.time_column}' contains {null_count} null values - excluded from time-based analysis"
                )
            for time_period in time_periods:
                time_df = df[df[analyzer.time_column] == time_period]
                entity_dim_agg = time_df.groupby([analyzer.entity_column, dimension]).agg({metric_col: 'sum'}).reset_index()

                for category in entity_dim_agg[dimension].unique():
                    cat_df = entity_dim_agg[entity_dim_agg[dimension] == category]
                    entity_vol = float(cat_df[cat_df[analyzer.entity_column] == entity][metric_col].sum())
                    total_raw_vol = float(cat_df[metric_col].sum())
                    raw_share = (entity_vol / total_raw_vol * 100.0) if total_raw_vol > 0 else 0.0

                    peer_cat_df = cat_df[cat_df[analyzer.entity_column] != entity]
                    total_balanced_vol = entity_vol
                    for _, row in peer_cat_df.iterrows():
                        peer = row[analyzer.entity_column]
                        peer_vol = float(row[metric_col])
                        peer_weight = dim_weights.get(peer, 1.0)
                        total_balanced_vol += peer_vol * peer_weight

                    balanced_share = (entity_vol / total_balanced_vol * 100.0) if total_balanced_vol > 0 else 0.0
                    impact_pp = balanced_share - raw_share

                    impact_rows.append({
                        'Dimension': dimension,
                        'Category': category,
                        'Time_Period': time_period,
                        'Entity': entity,
                        'Entity_Volume': entity_vol,
                        'Raw_Total_Volume': total_raw_vol,
                        'Balanced_Total_Volume': total_balanced_vol,
                        'Raw_Share_%': round(raw_share, 4),
                        'Balanced_Share_%': round(balanced_share, 4),
                        'Impact_PP': round(impact_pp, 4),
                    })
        else:
            entity_dim_agg = df.groupby([analyzer.entity_column, dimension]).agg({metric_col: 'sum'}).reset_index()

            for category in entity_dim_agg[dimension].unique():
                cat_df = entity_dim_agg[entity_dim_agg[dimension] == category]
                entity_vol = float(cat_df[cat_df[analyzer.entity_column] == entity][metric_col].sum())
                total_raw_vol = float(cat_df[metric_col].sum())
                raw_share = (entity_vol / total_raw_vol * 100.0) if total_raw_vol > 0 else 0.0

                peer_cat_df = cat_df[cat_df[analyzer.entity_column] != entity]
                total_balanced_vol = entity_vol
                for _, row in peer_cat_df.iterrows():
                    peer = row[analyzer.entity_column]
                    peer_vol = float(row[metric_col])
                    peer_weight = dim_weights.get(peer, 1.0)
                    total_balanced_vol += peer_vol * peer_weight

                balanced_share = (entity_vol / total_balanced_vol * 100.0) if total_balanced_vol > 0 else 0.0
                impact_pp = balanced_share - raw_share

                impact_rows.append({
                    'Dimension': dimension,
                    'Category': category,
                    'Time_Period': None,
                    'Entity': entity,
                    'Entity_Volume': entity_vol,
                    'Raw_Total_Volume': total_raw_vol,
                    'Balanced_Total_Volume': total_balanced_vol,
                    'Raw_Share_%': round(raw_share, 4),
                    'Balanced_Share_%': round(balanced_share, 4),
                    'Impact_PP': round(impact_pp, 4),
                })

    return pd.DataFrame(impact_rows)


def calculate_rate_impact(
    analyzer,
    df: pd.DataFrame,
    total_col: str,
    numerator_cols: Dict[str, str],
    dimensions: List[str],
    weight_lookup: Optional[WeightLookup] = None,
) -> pd.DataFrame:
    """Calculate impact on rate metrics (raw vs balanced rates)."""
    impact_rows: List[Dict[str, Any]] = []
    weights = weight_lookup or WeightLookup.from_analyzer(analyzer)

    for dimension in dimensions:
        dim_weights = weights.map_for_dimension(dimension)

        if analyzer.time_column and analyzer.time_column in df.columns:
            time_periods = analyzer._get_time_periods(df)
            null_count = df[analyzer.time_column].isna().sum()
            if null_count > 0:
                logger.warning(
                    f"Time column '{analyzer.time_column}' contains {null_count} null values - excluded from time-based analysis"
                )
            for time_period in time_periods:
                time_df = df[df[analyzer.time_column] == time_period]
                all_num_cols = [total_col] + list(numerator_cols.values())
                entity_dim_agg = time_df.groupby([analyzer.entity_column, dimension]).agg(
                    {col: 'sum' for col in all_num_cols}
                ).reset_index()

                for category in entity_dim_agg[dimension].unique():
                    cat_df = entity_dim_agg[entity_dim_agg[dimension] == category]
                    if analyzer.target_entity:
                        peer_cat_df = cat_df[cat_df[analyzer.entity_column] != analyzer.target_entity]
                    else:
                        peer_cat_df = cat_df

                    row_data = {
                        'Dimension': dimension,
                        'Category': category,
                        'Time_Period': time_period,
                    }

                    for rate_name, num_col in numerator_cols.items():
                        total_num = float(peer_cat_df[num_col].sum())
                        total_denom = float(peer_cat_df[total_col].sum())
                        raw_rate = (total_num / total_denom * 100.0) if total_denom > 0 else 0.0

                        balanced_num = 0.0
                        balanced_denom = 0.0
                        for _, prow in peer_cat_df.iterrows():
                            peer = prow[analyzer.entity_column]
                            w = dim_weights.get(peer, 1.0)
                            balanced_num += float(prow[num_col]) * w
                            balanced_denom += float(prow[total_col]) * w

                        balanced_rate = (balanced_num / balanced_denom * 100.0) if balanced_denom > 0 else 0.0
                        impact_pp = balanced_rate - raw_rate

                        row_data[f'{rate_name}_Raw_%'] = round(raw_rate, 4)
                        row_data[f'{rate_name}_Balanced_%'] = round(balanced_rate, 4)
                        row_data[f'{rate_name}_Impact_PP'] = round(impact_pp, 4)

                    impact_rows.append(row_data)
        else:
            all_num_cols = [total_col] + list(numerator_cols.values())
            entity_dim_agg = df.groupby([analyzer.entity_column, dimension]).agg(
                {col: 'sum' for col in all_num_cols}
            ).reset_index()

            for category in entity_dim_agg[dimension].unique():
                cat_df = entity_dim_agg[entity_dim_agg[dimension] == category]
                if analyzer.target_entity:
                    peer_cat_df = cat_df[cat_df[analyzer.entity_column] != analyzer.target_entity]
                else:
                    peer_cat_df = cat_df

                row_data = {
                    'Dimension': dimension,
                    'Category': category,
                    'Time_Period': None,
                }

                for rate_name, num_col in numerator_cols.items():
                    total_num = float(peer_cat_df[num_col].sum())
                    total_denom = float(peer_cat_df[total_col].sum())
                    raw_rate = (total_num / total_denom * 100.0) if total_denom > 0 else 0.0

                    balanced_num = 0.0
                    balanced_denom = 0.0
                    for _, prow in peer_cat_df.iterrows():
                        peer = prow[analyzer.entity_column]
                        w = dim_weights.get(peer, 1.0)
                        balanced_num += float(prow[num_col]) * w
                        balanced_denom += float(prow[total_col]) * w

                    balanced_rate = (balanced_num / balanced_denom * 100.0) if balanced_denom > 0 else 0.0
                    impact_pp = balanced_rate - raw_rate

                    row_data[f'{rate_name}_Raw_%'] = round(raw_rate, 4)
                    row_data[f'{rate_name}_Balanced_%'] = round(balanced_rate, 4)
                    row_data[f'{rate_name}_Impact_PP'] = round(impact_pp, 4)

                impact_rows.append(row_data)

    return pd.DataFrame(impact_rows)


def calculate_impact_summary(
    impact_df: pd.DataFrame,
    analysis_type: str = 'share',
) -> pd.DataFrame:
    """Calculate summary statistics for impact."""
    if impact_df.empty:
        return pd.DataFrame()

    summary_rows: List[Dict[str, Any]] = []

    if analysis_type == 'share':
        metric_col = 'Impact_PP'
        if metric_col not in impact_df.columns and 'Distortion_PP' in impact_df.columns:
            metric_col = 'Distortion_PP'
        if metric_col not in impact_df.columns:
            logger.warning(f"Column {metric_col} not found in impact dataframe")
            return pd.DataFrame()

        summary_rows.append({
            'Aggregation': 'Overall',
            'Level': 'All Data',
            'Mean_Impact_PP': round(impact_df[metric_col].mean(), 4),
            'Min_Impact_PP': round(impact_df[metric_col].min(), 4),
            'Max_Impact_PP': round(impact_df[metric_col].max(), 4),
            'Std_Impact_PP': round(impact_df[metric_col].std(), 4) if len(impact_df) > 1 else 0.0,
            'Count': len(impact_df),
        })

        for dim in impact_df['Dimension'].unique():
            dim_df = impact_df[impact_df['Dimension'] == dim]
            summary_rows.append({
                'Aggregation': 'By Dimension',
                'Level': dim,
                'Mean_Impact_PP': round(dim_df[metric_col].mean(), 4),
                'Min_Impact_PP': round(dim_df[metric_col].min(), 4),
                'Max_Impact_PP': round(dim_df[metric_col].max(), 4),
                'Std_Impact_PP': round(dim_df[metric_col].std(), 4) if len(dim_df) > 1 else 0.0,
                'Count': len(dim_df),
            })

        if 'Time_Period' in impact_df.columns and impact_df['Time_Period'].notna().any():
            for time_period in impact_df['Time_Period'].dropna().unique():
                time_df = impact_df[impact_df['Time_Period'] == time_period]
                summary_rows.append({
                    'Aggregation': 'By Time Period',
                    'Level': str(time_period),
                    'Mean_Impact_PP': round(time_df[metric_col].mean(), 4),
                    'Min_Impact_PP': round(time_df[metric_col].min(), 4),
                    'Max_Impact_PP': round(time_df[metric_col].max(), 4),
                    'Std_Impact_PP': round(time_df[metric_col].std(), 4) if len(time_df) > 1 else 0.0,
                    'Count': len(time_df),
                })
    else:
        effect_cols = [col for col in impact_df.columns if col.endswith('_Impact_PP')]
        if not effect_cols:
            effect_cols = [col for col in impact_df.columns if col.endswith('_Weight_Effect_PP')]
        if not effect_cols:
            logger.warning("No impact columns found in impact dataframe")
            return pd.DataFrame()

        for rate_col in effect_cols:
            rate_name = rate_col.replace('_Impact_PP', '').replace('_Weight_Effect_PP', '')

            summary_rows.append({
                'Aggregation': 'Overall',
                'Level': 'All Data',
                'Rate': rate_name,
                'Mean_Impact_PP': round(impact_df[rate_col].mean(), 4),
                'Min_Impact_PP': round(impact_df[rate_col].min(), 4),
                'Max_Impact_PP': round(impact_df[rate_col].max(), 4),
                'Std_Impact_PP': round(impact_df[rate_col].std(), 4) if len(impact_df) > 1 else 0.0,
                'Count': len(impact_df),
            })

            for dim in impact_df['Dimension'].unique():
                dim_df = impact_df[impact_df['Dimension'] == dim]
                summary_rows.append({
                    'Aggregation': 'By Dimension',
                    'Level': dim,
                    'Rate': rate_name,
                    'Mean_Impact_PP': round(dim_df[rate_col].mean(), 4),
                    'Min_Impact_PP': round(dim_df[rate_col].min(), 4),
                    'Max_Impact_PP': round(dim_df[rate_col].max(), 4),
                    'Std_Impact_PP': round(dim_df[rate_col].std(), 4) if len(dim_df) > 1 else 0.0,
                    'Count': len(dim_df),
                })

    return pd.DataFrame(summary_rows)
