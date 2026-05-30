"""Balanced metrics DataFrame and CSV export for share/rate analysis."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import pandas as pd

from core.dimensional_analyzer import DimensionalAnalyzer


def get_balanced_metrics_df(
    df: pd.DataFrame,
    analyzer: DimensionalAnalyzer,
    dimensions: list,
    metric_col: Optional[str] = None,
    secondary_metrics: Optional[list] = None,
    total_col: Optional[str] = None,
    numerator_cols: Optional[Dict[str, str]] = None
) -> pd.DataFrame:
    """
    Calculate balanced metrics for primary and secondary metrics.
    Returns a DataFrame with columns: Dimension, Category, [Time], Balanced_{Metric}...
    """
    rows = []
    entity_col = analyzer.entity_column
    
    # Get global weights or per-dimension weights
    def get_weight(dimension: str, peer: str) -> float:
        """Get weight multiplier for a peer in a dimension."""
        if dimension in analyzer.per_dimension_weights and peer in analyzer.per_dimension_weights[dimension]:
            return float(analyzer.per_dimension_weights[dimension][peer])
        if hasattr(analyzer, 'global_weights') and peer in analyzer.global_weights:
            return float(analyzer.global_weights[peer].get('multiplier', 1.0))
        return 1.0
    
    # Check if time column is available
    time_col = analyzer.time_column if hasattr(analyzer, 'time_column') else None
    has_time = time_col and time_col in df.columns
    
    # Build list of metrics to calculate
    metrics_to_calculate = []
    
    # Share analysis primary metric
    if metric_col:
        metrics_to_calculate.append(('Primary', metric_col))
        
    # Rate analysis metrics
    if total_col:
        metrics_to_calculate.append(('Total', total_col))
        if numerator_cols:
            for key, col in numerator_cols.items():
                if col in df.columns:
                    metrics_to_calculate.append((f'Approval_{key.capitalize()}' if key == 'approval' else f'Fraud_{key.capitalize()}' if key == 'fraud' else key.capitalize(), col))

    # Secondary metrics
    if secondary_metrics:
        for sec_metric in secondary_metrics:
            if sec_metric in df.columns:
                metrics_to_calculate.append(('Secondary', sec_metric))
    
    # Process each dimension
    for dimension in dimensions:
        # Aggregate data by entity, dimension category, and optionally time
        group_cols = [entity_col, dimension]
        # Only add time_col if it's different from the current dimension
        if has_time and time_col != dimension:
            group_cols.append(time_col)
        
        # Build aggregation dict - exclude columns that are part of groupby
        agg_dict = {}
        for _, metric in metrics_to_calculate:
            if metric in df.columns and metric not in group_cols:
                agg_dict[metric] = 'sum'
        
        if not agg_dict:
            continue
            
        entity_dim_agg = df.groupby(group_cols).agg(agg_dict).reset_index()
        
        # Get unique categories
        categories = entity_dim_agg[dimension].unique()
        
        # Get unique time periods if applicable
        time_periods = sorted(entity_dim_agg[time_col].unique()) if has_time else [None]
        
        for category in categories:
            for time_period in time_periods:
                # Filter to this category (and time period if applicable)
                if has_time:
                    cat_df = entity_dim_agg[
                        (entity_dim_agg[dimension] == category) & 
                        (entity_dim_agg[time_col] == time_period)
                    ]
                else:
                    cat_df = entity_dim_agg[entity_dim_agg[dimension] == category]
                
                if cat_df.empty:
                    continue
                
                # Build row data
                row_data = {
                    'Dimension': dimension,
                    'Category': category,
                }
                
                # Add time period if applicable
                if has_time:
                    row_data[time_col] = time_period
                
                # Calculate balanced metric for each metric column
                for metric_type, metric in metrics_to_calculate:
                    if metric not in cat_df.columns:
                        continue
                        
                    balanced_metric = 0.0
                    for _, row in cat_df.iterrows():
                        peer = row[entity_col]
                        weight = get_weight(dimension, peer)
                        balanced_metric += row[metric] * weight
                    
                    # Column name based on metric type
                    if metric_type == 'Primary':
                        col_name = f'Balanced_{metric}'
                    elif metric_type == 'Total':
                        col_name = 'Balanced_Total'
                    elif metric_type.startswith('Approval'):
                        col_name = 'Balanced_Approval_Total' # Standardize name for rate analysis
                    elif metric_type.startswith('Fraud'):
                        col_name = 'Balanced_Fraud_Total' # Standardize name for rate analysis
                    elif metric_type == 'Secondary':
                        col_name = metric
                    else:
                        col_name = f'Balanced_{metric}'
                        
                    row_data[col_name] = round(balanced_metric, 2)
                
                rows.append(row_data)
    
    if not rows:
        return pd.DataFrame()
    
    # Create DataFrame
    result_df = pd.DataFrame(rows)
    
    # Sort by Dimension, Time (if present), then Category
    sort_cols = ['Dimension']
    if has_time and time_col in result_df.columns:
        sort_cols.append(time_col)
    sort_cols.append('Category')
    
    return result_df.sort_values(sort_cols)


def export_balanced_csv(
    results: Optional[Dict[str, pd.DataFrame]], 
    output_file: str, 
    logger: logging.Logger,
    analysis_type: str = 'share',
    all_results: Optional[Dict[str, Dict[str, pd.DataFrame]]] = None,
    df: Optional[pd.DataFrame] = None,
    analyzer: Optional[Any] = None,
    dimensions: Optional[list] = None,
    total_col: Optional[str] = None,
    numerator_cols: Optional[Dict[str, str]] = None,
    metric_col: Optional[str] = None,
    secondary_metrics: Optional[list] = None,
    include_calculated: bool = False
) -> None:
    """
    Export balanced metrics to CSV in concatenated dimension format.
    
    For rate analysis: exports dimension, category, balanced_total, balanced_approval_total, balanced_fraud_total
    The balanced totals are weighted sums: sum(peer_value * weight) across all peers
    
    For share analysis: exports dimension, category, balanced metric values (for primary and secondary metrics)
    The balanced metrics are weighted sums: sum(peer_metric_value * weight) across all peers
    
    Args:
        results: Results dictionary for share analysis (dimension -> DataFrame)
        output_file: Base output file path (will change extension to .csv)
        logger: Logger instance
        analysis_type: Type of analysis ('share' or 'rate')
        all_results: For rate analysis, dict of rate_type -> results (e.g., {'approval': {...}, 'fraud': {...}})
        df: Source dataframe for recalculating weighted totals
        analyzer: Analyzer instance with weights
        dimensions: List of dimensions analyzed
        total_col: Total column name (for rate analysis)
        numerator_cols: Dict mapping rate_type to numerator column name
        metric_col: Primary metric column name (for share analysis)
        secondary_metrics: List of secondary metric columns (for share analysis)
    """
    # Create CSV filename from Excel filename
    csv_output = output_file.rsplit('.', 1)[0] + '_balanced.csv'
    
    if analysis_type == 'rate' and all_results and df is not None and analyzer is not None:
        # Rate analysis: calculate weighted totals for each dimension-category
        export_rows = []
        
        # Get entity column and weights
        entity_col = analyzer.entity_column
        
        # Get global weights or per-dimension weights
        def get_weight(dimension: str, peer: str) -> float:
            """Get weight multiplier for a peer in a dimension."""
            weight = 1.0
            if hasattr(analyzer, 'global_weights') and peer in analyzer.global_weights:
                weight = float(analyzer.global_weights[peer].get('multiplier', 1.0))
            if dimension in analyzer.per_dimension_weights and peer in analyzer.per_dimension_weights[dimension]:
                weight = float(analyzer.per_dimension_weights[dimension][peer])
            return weight
        
        # Check if time column is available
        time_col = analyzer.time_column if hasattr(analyzer, 'time_column') else None
        has_time = time_col and time_col in df.columns
        
        # Get secondary metrics from caller
        secondary_metrics_list = getattr(analyzer, 'secondary_metrics', None)
        
        # Process each dimension
        for dimension in dimensions:
            # Aggregate data by entity, dimension category, and optionally time
            group_cols = [entity_col, dimension]
            # Only add time_col if it's different from the current dimension
            if has_time and time_col != dimension:
                group_cols.append(time_col)
            
            # Build aggregation dict - exclude columns that are part of groupby
            agg_dict = {}
            if total_col not in group_cols:
                agg_dict[total_col] = 'sum'
            
            # Add numerator columns (exclude those in group_cols)
            if numerator_cols:
                for num_col in numerator_cols.values():
                    if num_col in df.columns and num_col not in group_cols:
                        agg_dict[num_col] = 'sum'
            
            # Add secondary metrics (exclude those in group_cols)
            if secondary_metrics_list:
                for sec_metric in secondary_metrics_list:
                    if sec_metric in df.columns and sec_metric not in group_cols:
                        agg_dict[sec_metric] = 'sum'
            
            if not agg_dict:
                continue
                
            entity_dim_agg = df.groupby(group_cols).agg(agg_dict).reset_index()
            
            # Get unique categories
            categories = entity_dim_agg[dimension].unique()
            
            # Get unique time periods if applicable
            time_periods = sorted(entity_dim_agg[time_col].unique()) if has_time else [None]
            
            for category in categories:
                for time_period in time_periods:
                    # Filter to this category (and time period if applicable)
                    if has_time:
                        cat_df = entity_dim_agg[
                            (entity_dim_agg[dimension] == category) & 
                            (entity_dim_agg[time_col] == time_period)
                        ]
                    else:
                        cat_df = entity_dim_agg[entity_dim_agg[dimension] == category]
                    
                    if cat_df.empty:
                        continue
                    
                    # Calculate weighted totals
                    balanced_total = 0.0
                    balanced_approval = 0.0
                    balanced_fraud = 0.0
                    secondary_balanced = {}
                    
                    # Calculate raw totals if requested
                    raw_total = 0.0
                    raw_approval = 0.0
                    raw_fraud = 0.0
                    secondary_raw = {}

                    # Peer-only totals for weight-effect calculations
                    raw_peer_total = 0.0
                    raw_peer_approval = 0.0
                    raw_peer_fraud = 0.0
                    balanced_peer_total = 0.0
                    balanced_peer_approval = 0.0
                    balanced_peer_fraud = 0.0
                    
                    # Initialize secondary metrics dict
                    if secondary_metrics_list:
                        for sec_metric in secondary_metrics_list:
                            if sec_metric in cat_df.columns:
                                secondary_balanced[sec_metric] = 0.0
                                if include_calculated:
                                    secondary_raw[sec_metric] = 0.0
                    
                    for _, row in cat_df.iterrows():
                        peer = row[entity_col]
                        weight = get_weight(dimension, peer)
                        is_target = analyzer.target_entity is not None and peer == analyzer.target_entity

                        # Balanced totals should always be peer-only
                        if not is_target:
                            # Weighted total (denominator)
                            balanced_total += row[total_col] * weight
                            balanced_peer_total += row[total_col] * weight

                            # Weighted approval numerator
                            if approval_col := numerator_cols.get('approval'):
                                if approval_col in row.index:
                                    balanced_approval += row[approval_col] * weight
                                    balanced_peer_approval += row[approval_col] * weight

                            # Weighted fraud numerator
                            if fraud_col := numerator_cols.get('fraud'):
                                if fraud_col in row.index:
                                    balanced_fraud += row[fraud_col] * weight
                                    balanced_peer_fraud += row[fraud_col] * weight

                            # Weighted secondary metrics
                            for sec_metric in secondary_balanced.keys():
                                if sec_metric in row.index:
                                    secondary_balanced[sec_metric] += row[sec_metric] * weight

                        # Raw totals if requested (peer-only)
                        if include_calculated and not is_target:
                            raw_total += row[total_col]
                            raw_peer_total += row[total_col]

                            if approval_col := numerator_cols.get('approval'):
                                if approval_col in row.index:
                                    raw_approval += row[approval_col]
                                    raw_peer_approval += row[approval_col]

                            if fraud_col := numerator_cols.get('fraud'):
                                if fraud_col in row.index:
                                    raw_fraud += row[fraud_col]
                                    raw_peer_fraud += row[fraud_col]

                            for sec_metric in secondary_raw.keys():
                                if sec_metric in row.index:
                                    secondary_raw[sec_metric] += row[sec_metric]
                    
                    # Add row to export
                    row_data = {
                        'Dimension': dimension,
                        'Category': category,
                    }
                    
                    if include_calculated:
                        # Add raw and balanced rates and impact
                        if total_col:
                            row_data['Raw_Total'] = raw_total
                            row_data['Balanced_Total'] = balanced_total
                        
                        # Approval
                        if numerator_cols.get('approval'):
                            row_data['Balanced_Approval_Total'] = balanced_approval
                            # Calculate rates in %
                            raw_rate = (raw_peer_approval / raw_peer_total * 100) if raw_peer_total > 0 else 0.0
                            bal_rate = (balanced_peer_approval / balanced_peer_total * 100) if balanced_peer_total > 0 else 0.0
                            row_data['Raw_Approval_Rate_%'] = raw_rate
                            row_data['Balanced_Approval_Rate_%'] = bal_rate
                            row_data['Approval_Impact_PP'] = bal_rate - raw_rate
                            
                        # Fraud
                        if numerator_cols.get('fraud'):
                            row_data['Balanced_Fraud_Total'] = balanced_fraud
                            # Calculate rates in pp for consistency with impact
                            raw_fraud_rate = (raw_peer_fraud / raw_peer_total * 100) if raw_peer_total > 0 else 0.0
                            bal_fraud_rate = (balanced_peer_fraud / balanced_peer_total * 100) if balanced_peer_total > 0 else 0.0
                            row_data['Raw_Fraud_Rate_%'] = raw_fraud_rate
                            row_data['Balanced_Fraud_Rate_%'] = bal_fraud_rate
                            row_data['Fraud_Impact_PP'] = bal_fraud_rate - raw_fraud_rate
                    
                    # Add time period if applicable
                    if has_time:
                        row_data[time_col] = time_period
                    
                    # Use dynamic column names based on input columns
                    row_data[total_col] = round(balanced_total, 2)
                    
                    if numerator_cols:
                        if approval_col := numerator_cols.get('approval'):
                            row_data[approval_col] = round(balanced_approval, 2) if balanced_approval > 0 else None
                        if fraud_col := numerator_cols.get('fraud'):
                            row_data[fraud_col] = round(balanced_fraud, 2) if balanced_fraud > 0 else None
                    
                    # Add secondary metrics to row
                    for sec_metric, sec_value in secondary_balanced.items():
                        row_data[sec_metric] = round(sec_value, 2)
                    
                    export_rows.append(row_data)
        
        if not export_rows:
            logger.warning("No data to export for rate analysis CSV")
            return
        
        # Create DataFrame and export
        export_df = pd.DataFrame(export_rows)
        
        # Sort by Dimension, Time (if present), then Category
        sort_cols = ['Dimension']
        if has_time and time_col in export_df.columns:
            sort_cols.append(time_col)
        sort_cols.append('Category')
        
        export_df = export_df.sort_values(sort_cols)
        export_df.to_csv(csv_output, index=False)
        logger.info(f"Balanced rate data CSV exported to: {csv_output}")
        print(f"Balanced CSV: {csv_output}")
        
    elif analysis_type == 'share' and results and df is not None and analyzer is not None:
        # Share analysis: calculate balanced metrics for each dimension-category
        export_rows = []
        
        # Get entity column and weights
        entity_col = analyzer.entity_column
        
        # Get global weights or per-dimension weights
        def get_weight(dimension: str, peer: str) -> float:
            """Get weight multiplier for a peer in a dimension."""
            weight = 1.0
            if hasattr(analyzer, 'global_weights') and peer in analyzer.global_weights:
                weight = float(analyzer.global_weights[peer].get('multiplier', 1.0))
            if dimension in analyzer.per_dimension_weights and peer in analyzer.per_dimension_weights[dimension]:
                weight = float(analyzer.per_dimension_weights[dimension][peer])
            return weight
        
        # Check if time column is available
        time_col = analyzer.time_column if hasattr(analyzer, 'time_column') else None
        has_time = time_col and time_col in df.columns
        
        # Build list of metrics to calculate (primary + secondary)
        metrics_to_calculate = []
        if metric_col:
            metrics_to_calculate.append(('Primary', metric_col))
        if secondary_metrics:
            for sec_metric in secondary_metrics:
                if sec_metric in df.columns:
                    metrics_to_calculate.append(('Secondary', sec_metric))
        
        target_entity = analyzer.target_entity
        if include_calculated and not target_entity:
            logger.info("Peer-only mode: skipping target-vs-peer share calculations in balanced CSV.")

        # Process each dimension
        for dimension in dimensions:
            # Aggregate data by entity, dimension category, and optionally time
            group_cols = [entity_col, dimension]
            # Only add time_col if it's different from the current dimension
            if has_time and time_col != dimension:
                group_cols.append(time_col)

            # Build aggregation dict for all metrics - exclude columns that are part of groupby
            agg_dict = {}
            for _, metric in metrics_to_calculate:
                if metric in df.columns and metric not in group_cols:
                    agg_dict[metric] = 'sum'

            if not agg_dict:
                continue

            entity_dim_agg = df.groupby(group_cols).agg(agg_dict).reset_index()

            # Get unique categories
            categories = entity_dim_agg[dimension].unique()

            # Get unique time periods if applicable
            time_periods = sorted(entity_dim_agg[time_col].unique()) if has_time else [None]

            for category in categories:
                for time_period in time_periods:
                    # Filter to this category (and time period if applicable)
                    if has_time:
                        cat_df = entity_dim_agg[
                            (entity_dim_agg[dimension] == category) &
                            (entity_dim_agg[time_col] == time_period)
                        ]
                    else:
                        cat_df = entity_dim_agg[entity_dim_agg[dimension] == category]

                    if cat_df.empty:
                        continue

                    # Calculate metrics
                    balanced_metric_values = {}
                    raw_metric_values = {}

                    # Initialize values
                    for m_type, m_col in metrics_to_calculate:
                        balanced_metric_values[m_col] = 0.0
                        if include_calculated:
                            raw_metric_values[m_col] = 0.0

                    for _, row in cat_df.iterrows():
                        peer = row[entity_col]
                        if analyzer.target_entity is not None and peer == analyzer.target_entity:
                            continue
                        weight = get_weight(dimension, peer)

                        for m_type, m_col in metrics_to_calculate:
                            if m_col in row:
                                val = row[m_col]
                                balanced_metric_values[m_col] += val * weight
                                if include_calculated:
                                    raw_metric_values[m_col] += val

                    # Add row to export
                    row_data = {
                        'Dimension': dimension,
                        'Category': category,
                    }

                    # Add metric values
                    for m_type, m_col in metrics_to_calculate:
                        # Use original metric name for column header
                        clean_name = m_col
                        row_data[f'Balanced_{clean_name}'] = round(balanced_metric_values[m_col], 2)

                        if include_calculated:
                            row_data[f'Raw_{clean_name}'] = round(raw_metric_values[m_col], 2)

                            # Calculate shares and impact
                            if target_entity:
                                target_rows = cat_df[cat_df[entity_col] == target_entity]
                                peer_rows = cat_df[cat_df[entity_col] != target_entity]
                                target_val = float(target_rows[m_col].sum()) if not target_rows.empty else 0.0
                                raw_peer_total = float(peer_rows[m_col].sum()) if not peer_rows.empty else 0.0
                                balanced_peer_total = 0.0
                                for _, prow in peer_rows.iterrows():
                                    peer = prow[entity_col]
                                    weight = get_weight(dimension, peer)
                                    balanced_peer_total += float(prow[m_col]) * weight
                                raw_denom = target_val + raw_peer_total
                                bal_denom = target_val + balanced_peer_total
                                raw_share = (target_val / raw_denom * 100.0) if raw_denom > 0 else 0.0
                                bal_share = (target_val / bal_denom * 100.0) if bal_denom > 0 else 0.0
                                row_data[f'Raw_{clean_name}_Share_%'] = round(raw_share, 4)
                                row_data[f'Balanced_{clean_name}_Share_%'] = round(bal_share, 4)
                                row_data[f'{clean_name}_Impact_PP'] = round(bal_share - raw_share, 4)
                            else:
                                row_data[f'Raw_{clean_name}_Share_%'] = None
                                row_data[f'Balanced_{clean_name}_Share_%'] = None
                                row_data[f'{clean_name}_Impact_PP'] = None

                    # Add time period if applicable
                    if has_time:
                        row_data[time_col] = time_period

                    export_rows.append(row_data)
        
        if not export_rows:
            logger.warning("No data to export for share analysis CSV")
            return
        
        # Create DataFrame and export
        export_df = pd.DataFrame(export_rows)
        
        # Sort by Dimension, Time (if present), then Category
        sort_cols = ['Dimension']
        if has_time and time_col in export_df.columns:
            sort_cols.append(time_col)
        sort_cols.append('Category')
        
        export_df = export_df.sort_values(sort_cols)
        export_df.to_csv(csv_output, index=False)
        logger.info(f"Balanced share metrics CSV exported to: {csv_output}")
        print(f"Balanced CSV: {csv_output}")
    
    else:
        logger.warning("No valid results provided for CSV export")
        return

