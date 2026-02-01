"""Dimension-level share/rate calculation workflows."""

from typing import Any, Dict, List, Optional

import pandas as pd


class AnalysisCalculator:
    """Coordinates per-dimension share/rate execution for DimensionalAnalyzer."""

    def __init__(self, analyzer: Any) -> None:
        self.analyzer = analyzer

    def analyze_dimension_share(
        self,
        df: pd.DataFrame,
        dimension_column: str,
        metric_col: str = "transaction_count",
    ) -> pd.DataFrame:
        return self._analyze_dimension(
            df=df,
            dimension_column=dimension_column,
            aggregation_columns={metric_col: "sum"},
            metric_callback=self.analyzer._calculate_share_metrics,
            callback_kwargs={"metric_col": metric_col},
        )

    def analyze_dimension_rate(
        self,
        df: pd.DataFrame,
        dimension_column: str,
        total_col: str,
        numerator_col: str,
    ) -> pd.DataFrame:
        return self._analyze_dimension(
            df=df,
            dimension_column=dimension_column,
            aggregation_columns={total_col: "sum", numerator_col: "sum"},
            metric_callback=self.analyzer._calculate_rate_metrics,
            callback_kwargs={"total_col": total_col, "numerator_col": numerator_col},
        )

    def _analyze_dimension(
        self,
        df: pd.DataFrame,
        dimension_column: str,
        aggregation_columns: Dict[str, str],
        metric_callback: Any,
        callback_kwargs: Dict[str, Any],
    ) -> pd.DataFrame:
        results: List[Dict[str, Any]] = []
        entity_col = self.analyzer.entity_column
        time_col = self.analyzer.time_column

        if time_col and time_col in df.columns:
            entity_category_time_agg = (
                df.groupby([entity_col, dimension_column, time_col])
                .agg(aggregation_columns)
                .reset_index()
            )
            primary_metric = next(iter(aggregation_columns.keys()))
            entity_totals_by_time = entity_category_time_agg.groupby([entity_col, time_col])[primary_metric].sum()

            entity_category_agg = (
                df.groupby([entity_col, dimension_column])
                .agg(aggregation_columns)
                .reset_index()
            )
            entity_totals = entity_category_agg.groupby(entity_col)[primary_metric].sum()
            categories = entity_category_agg[dimension_column].unique()
            time_periods = self.analyzer._get_time_periods(df)

            for category in categories:
                for time_period in time_periods:
                    time_category_df = entity_category_time_agg[
                        (entity_category_time_agg[dimension_column] == category)
                        & (entity_category_time_agg[time_col] == time_period)
                    ].copy()
                    result = metric_callback(
                        time_category_df,
                        entity_totals_by_time,
                        dimension_column,
                        category,
                        time_period=time_period,
                        **callback_kwargs,
                    )
                    if result:
                        results.append(result)

                category_df = entity_category_agg[entity_category_agg[dimension_column] == category].copy()
                result = metric_callback(
                    category_df,
                    entity_totals,
                    dimension_column,
                    category,
                    time_period="General",
                    **callback_kwargs,
                )
                if result:
                    results.append(result)
        else:
            entity_category_agg = (
                df.groupby([entity_col, dimension_column])
                .agg(aggregation_columns)
                .reset_index()
            )
            primary_metric = next(iter(aggregation_columns.keys()))
            entity_totals = entity_category_agg.groupby(entity_col)[primary_metric].sum()
            categories = entity_category_agg[dimension_column].unique()

            for category in categories:
                category_df = entity_category_agg[entity_category_agg[dimension_column] == category].copy()
                result = metric_callback(
                    category_df,
                    entity_totals,
                    dimension_column,
                    category,
                    time_period=None,
                    **callback_kwargs,
                )
                if result:
                    results.append(result)

        return pd.DataFrame(results)
