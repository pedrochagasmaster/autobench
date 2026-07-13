"""Balanced metrics DataFrame and CSV export for share/rate analysis."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional

import pandas as pd

from core.category_suppression import is_category_suppressed
from core.contracts import WeightLookup
from core.dimensional_analyzer import DimensionalAnalyzer
from core.export_sanitizer import sanitize_cell


@dataclass(frozen=True)
class _BalancedGroup:
    dimension: str
    category: Any
    time_period: Any
    category_rows: pd.DataFrame
    rows: pd.DataFrame
    peer_weights: pd.Series


def _resolve_time_column(df: pd.DataFrame, analyzer: Any) -> Optional[str]:
    time_col = getattr(analyzer, "time_column", None)
    return time_col if time_col in df.columns else None


def _iter_balanced_groups(
    df: pd.DataFrame,
    *,
    analyzer: Any,
    dimensions: List[str],
    metric_columns: List[str],
    weights: WeightLookup,
    suppressed_categories: Optional[List[Dict[str, Any]]],
    exclude_target: bool,
) -> Iterator[_BalancedGroup]:
    entity_col = analyzer.entity_column
    time_col = _resolve_time_column(df, analyzer)
    for dimension in dimensions:
        group_cols = [entity_col, dimension]
        if time_col is not None and time_col != dimension:
            group_cols.append(time_col)
        aggregations = {
            column: "sum"
            for column in metric_columns
            if column in df.columns and column not in group_cols
        }
        if not aggregations:
            continue
        aggregated = df.groupby(group_cols).agg(aggregations).reset_index()
        time_periods = (
            sorted(aggregated[time_col].unique())
            if time_col is not None
            else [None]
        )
        weight_map = weights.map_for_dimension(dimension)
        for category in aggregated[dimension].unique():
            for time_period in time_periods:
                if is_category_suppressed(
                    suppressed_categories or [],
                    dimension,
                    category,
                    time_period,
                ):
                    continue
                mask = aggregated[dimension] == category
                if time_col is not None:
                    mask &= aggregated[time_col] == time_period
                category_rows = aggregated[mask]
                if category_rows.empty:
                    continue
                rows = category_rows
                if exclude_target and analyzer.target_entity is not None:
                    rows = rows[rows[entity_col] != analyzer.target_entity]
                yield _BalancedGroup(
                    dimension=dimension,
                    category=category,
                    time_period=time_period,
                    category_rows=category_rows,
                    rows=rows,
                    peer_weights=rows[entity_col].map(weight_map).fillna(1.0),
                )


def _weighted_sum(group: _BalancedGroup, column: str) -> float:
    return float((group.rows[column] * group.peer_weights).sum())


def _write_csv(
    rows: List[Dict[str, Any]],
    *,
    csv_output: str,
    time_col: Optional[str],
) -> None:
    export_df = pd.DataFrame(rows)
    sort_cols = ["Dimension"]
    if time_col is not None and time_col in export_df.columns:
        sort_cols.append(time_col)
    sort_cols.append("Category")
    export_df = export_df.sort_values(sort_cols)
    for column in export_df.select_dtypes(include="object").columns:
        export_df[column] = export_df[column].map(sanitize_cell)
    export_df.to_csv(csv_output, index=False)


def get_balanced_metrics_df(
    df: pd.DataFrame,
    analyzer: DimensionalAnalyzer,
    dimensions: list,
    metric_col: Optional[str] = None,
    secondary_metrics: Optional[list] = None,
    total_col: Optional[str] = None,
    numerator_cols: Optional[Dict[str, str]] = None,
    weight_lookup: Optional[WeightLookup] = None,
    suppressed_categories: Optional[List[Dict[str, Any]]] = None,
) -> pd.DataFrame:
    """
    Calculate balanced metrics for primary and secondary metrics.
    Returns a DataFrame with columns: Dimension, Category, [Time], Balanced_{Metric}...
    """
    rows = []
    weights = weight_lookup or WeightLookup.from_analyzer(analyzer)
    time_col = _resolve_time_column(df, analyzer)

    metrics_to_calculate = []
    if metric_col:
        metrics_to_calculate.append(("Primary", metric_col))
    if total_col:
        metrics_to_calculate.append(("Total", total_col))
        if numerator_cols:
            for key, col in numerator_cols.items():
                if col in df.columns:
                    metric_type = {
                        "approval": "Approval",
                        "fraud": "Fraud",
                    }.get(key, key.capitalize())
                    metrics_to_calculate.append((metric_type, col))

    if secondary_metrics:
        for sec_metric in secondary_metrics:
            if sec_metric in df.columns:
                metrics_to_calculate.append(("Secondary", sec_metric))

    metric_columns = [metric for _, metric in metrics_to_calculate]
    for group in _iter_balanced_groups(
        df,
        analyzer=analyzer,
        dimensions=dimensions,
        metric_columns=metric_columns,
        weights=weights,
        suppressed_categories=suppressed_categories,
        exclude_target=False,
    ):
        row_data = {
            "Dimension": group.dimension,
            "Category": group.category,
        }
        if time_col is not None:
            row_data[time_col] = group.time_period

        for metric_type, metric in metrics_to_calculate:
            if metric not in group.rows.columns:
                continue

            balanced_metric = _weighted_sum(group, metric)

            if metric_type == "Primary":
                col_name = f"Balanced_{metric}"
            elif metric_type == "Total":
                col_name = "Balanced_Total"
            elif metric_type.startswith("Approval"):
                col_name = "Balanced_Approval_Total"
            elif metric_type.startswith("Fraud"):
                col_name = "Balanced_Fraud_Total"
            elif metric_type == "Secondary":
                col_name = metric
            else:
                col_name = f"Balanced_{metric}"

            row_data[col_name] = round(balanced_metric, 2)

        rows.append(row_data)

    if not rows:
        return pd.DataFrame()

    result_df = pd.DataFrame(rows)
    sort_cols = ["Dimension"]
    if time_col is not None and time_col in result_df.columns:
        sort_cols.append(time_col)
    sort_cols.append("Category")
    return result_df.sort_values(sort_cols)


def export_balanced_csv(
    results: Optional[Dict[str, pd.DataFrame]],
    output_file: str,
    logger: logging.Logger,
    analysis_type: str = "share",
    all_results: Optional[Dict[str, Dict[str, pd.DataFrame]]] = None,
    df: Optional[pd.DataFrame] = None,
    analyzer: Optional[Any] = None,
    dimensions: Optional[list] = None,
    total_col: Optional[str] = None,
    numerator_cols: Optional[Dict[str, str]] = None,
    metric_col: Optional[str] = None,
    secondary_metrics: Optional[list] = None,
    include_calculated: bool = False,
    weight_lookup: Optional[WeightLookup] = None,
    suppressed_categories: Optional[List[Dict[str, Any]]] = None,
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
    csv_output = output_file.rsplit(".", 1)[0] + "_balanced.csv"
    dimensions = dimensions or []
    numerator_cols = numerator_cols or {}

    if (
        analysis_type == "rate"
        and all_results
        and df is not None
        and analyzer is not None
        and total_col is not None
    ):
        export_rows = []
        weights = weight_lookup or WeightLookup.from_analyzer(analyzer)
        time_col = _resolve_time_column(df, analyzer)
        secondary_metrics_list = getattr(analyzer, "secondary_metrics", None)

        metric_columns = [total_col]
        if numerator_cols:
            metric_columns.extend(
                num_col
                for num_col in numerator_cols.values()
                if num_col in df.columns
            )
        if secondary_metrics_list:
            metric_columns.extend(
                sec_metric
                for sec_metric in secondary_metrics_list
                if sec_metric in df.columns
            )

        for group in _iter_balanced_groups(
            df,
            analyzer=analyzer,
            dimensions=dimensions,
            metric_columns=metric_columns,
            weights=weights,
            suppressed_categories=suppressed_categories,
            exclude_target=True,
        ):
            balanced_total = _weighted_sum(group, total_col)

            approval_col = numerator_cols.get("approval") if numerator_cols else None
            fraud_col = numerator_cols.get("fraud") if numerator_cols else None

            balanced_approval = 0.0
            if approval_col and approval_col in group.rows.columns:
                balanced_approval = _weighted_sum(group, approval_col)

            balanced_fraud = 0.0
            if fraud_col and fraud_col in group.rows.columns:
                balanced_fraud = _weighted_sum(group, fraud_col)

            secondary_balanced: Dict[str, float] = {}
            if secondary_metrics_list:
                for sec_metric in secondary_metrics_list:
                    if sec_metric in group.rows.columns:
                        secondary_balanced[sec_metric] = _weighted_sum(group, sec_metric)

            raw_total = 0.0
            raw_peer_approval = 0.0
            raw_peer_fraud = 0.0
            if include_calculated:
                raw_total = float(group.rows[total_col].sum())
                if approval_col and approval_col in group.rows.columns:
                    raw_peer_approval = float(group.rows[approval_col].sum())
                if fraud_col and fraud_col in group.rows.columns:
                    raw_peer_fraud = float(group.rows[fraud_col].sum())

            row_data = {
                "Dimension": group.dimension,
                "Category": group.category,
            }

            if include_calculated:
                if total_col:
                    row_data["Raw_Total"] = raw_total
                    row_data["Balanced_Total"] = balanced_total

                if numerator_cols.get("approval"):
                    row_data["Balanced_Approval_Total"] = balanced_approval
                    raw_rate = (
                        (raw_peer_approval / raw_total * 100)
                        if raw_total > 0
                        else 0.0
                    )
                    bal_rate = (
                        (balanced_approval / balanced_total * 100)
                        if balanced_total > 0
                        else 0.0
                    )
                    row_data["Raw_Approval_Rate_%"] = raw_rate
                    row_data["Balanced_Approval_Rate_%"] = bal_rate
                    row_data["Approval_Impact_PP"] = bal_rate - raw_rate

                if numerator_cols.get("fraud"):
                    row_data["Balanced_Fraud_Total"] = balanced_fraud
                    raw_fraud_rate = (
                        (raw_peer_fraud / raw_total * 100)
                        if raw_total > 0
                        else 0.0
                    )
                    bal_fraud_rate = (
                        (balanced_fraud / balanced_total * 100)
                        if balanced_total > 0
                        else 0.0
                    )
                    row_data["Raw_Fraud_Rate_%"] = raw_fraud_rate
                    row_data["Balanced_Fraud_Rate_%"] = bal_fraud_rate
                    row_data["Fraud_Impact_PP"] = bal_fraud_rate - raw_fraud_rate

            if time_col is not None:
                row_data[time_col] = group.time_period

            if not include_calculated:
                row_data[total_col] = round(balanced_total, 2)

                if numerator_cols:
                    if approval_col := numerator_cols.get("approval"):
                        row_data[approval_col] = (
                            round(balanced_approval, 2) if balanced_approval > 0 else None
                        )
                    if fraud_col := numerator_cols.get("fraud"):
                        row_data[fraud_col] = (
                            round(balanced_fraud, 2) if balanced_fraud > 0 else None
                        )

                for sec_metric, sec_value in secondary_balanced.items():
                    row_data[sec_metric] = round(sec_value, 2)

            export_rows.append(row_data)

        if not export_rows:
            logger.warning("No data to export for rate analysis CSV")
            return

        _write_csv(export_rows, csv_output=csv_output, time_col=time_col)
        logger.info(f"Balanced rate data CSV exported to: {csv_output}")
        print(f"Balanced CSV: {csv_output}")

    elif analysis_type == "share" and results and df is not None and analyzer is not None:
        export_rows = []
        entity_col = analyzer.entity_column
        weights = weight_lookup or WeightLookup.from_analyzer(analyzer)
        time_col = _resolve_time_column(df, analyzer)

        metrics_to_calculate = []
        if metric_col:
            metrics_to_calculate.append(("Primary", metric_col))
        if secondary_metrics:
            for sec_metric in secondary_metrics:
                if sec_metric in df.columns:
                    metrics_to_calculate.append(("Secondary", sec_metric))

        target_entity = analyzer.target_entity
        if include_calculated and not target_entity:
            logger.info(
                "Peer-only mode: skipping target-vs-peer share calculations in balanced CSV."
            )

        metric_columns = [metric for _, metric in metrics_to_calculate]
        for group in _iter_balanced_groups(
            df,
            analyzer=analyzer,
            dimensions=dimensions,
            metric_columns=metric_columns,
            weights=weights,
            suppressed_categories=suppressed_categories,
            exclude_target=True,
        ):
            balanced_metric_values: Dict[str, float] = {}
            raw_metric_values: Dict[str, float] = {}
            for _m_type, m_col in metrics_to_calculate:
                if m_col in group.rows.columns:
                    balanced_metric_values[m_col] = _weighted_sum(group, m_col)
                    if include_calculated:
                        raw_metric_values[m_col] = float(group.rows[m_col].sum())
                else:
                    balanced_metric_values[m_col] = 0.0
                    if include_calculated:
                        raw_metric_values[m_col] = 0.0

            row_data = {
                "Dimension": group.dimension,
                "Category": group.category,
            }

            target_rows = None
            peer_rows = None
            if include_calculated and target_entity:
                target_rows = group.category_rows[
                    group.category_rows[entity_col] == target_entity
                ]
                peer_rows = group.category_rows[
                    group.category_rows[entity_col] != target_entity
                ]

            for _m_type, m_col in metrics_to_calculate:
                row_data[f"Balanced_{m_col}"] = round(
                    balanced_metric_values[m_col], 2
                )

                if include_calculated:
                    row_data[f"Raw_{m_col}"] = round(raw_metric_values[m_col], 2)

                    if target_rows is not None and peer_rows is not None:
                        target_val = (
                            float(target_rows[m_col].sum())
                            if not target_rows.empty
                            else 0.0
                        )
                        raw_peer_total = (
                            float(peer_rows[m_col].sum())
                            if not peer_rows.empty
                            else 0.0
                        )
                        if not peer_rows.empty and m_col in peer_rows.columns:
                            balanced_peer_total = balanced_metric_values[m_col]
                        else:
                            balanced_peer_total = 0.0
                        raw_denom = target_val + raw_peer_total
                        bal_denom = target_val + balanced_peer_total
                        raw_share = (
                            (target_val / raw_denom * 100.0) if raw_denom > 0 else 0.0
                        )
                        bal_share = (
                            (target_val / bal_denom * 100.0) if bal_denom > 0 else 0.0
                        )
                        row_data[f"Raw_{m_col}_Share_%"] = round(raw_share, 4)
                        row_data[f"Balanced_{m_col}_Share_%"] = round(bal_share, 4)
                        row_data[f"{m_col}_Impact_PP"] = round(
                            bal_share - raw_share, 4
                        )
                    else:
                        row_data[f"Raw_{m_col}_Share_%"] = None
                        row_data[f"Balanced_{m_col}_Share_%"] = None
                        row_data[f"{m_col}_Impact_PP"] = None

            if time_col is not None:
                row_data[time_col] = group.time_period

            export_rows.append(row_data)

        if not export_rows:
            logger.warning("No data to export for share analysis CSV")
            return

        _write_csv(export_rows, csv_output=csv_output, time_col=time_col)
        logger.info(f"Balanced share metrics CSV exported to: {csv_output}")
        print(f"Balanced CSV: {csv_output}")

    else:
        logger.warning("No valid results provided for CSV export")
        return
