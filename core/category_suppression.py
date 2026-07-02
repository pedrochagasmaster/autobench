"""Suppress under-populated and structurally infeasible categories from published outputs."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd


def extract_structural_infeasible_pairs(
    structural_detail_df: Optional[pd.DataFrame],
    *,
    dimensions: Optional[Iterable[str]] = None,
) -> List[Tuple[str, str]]:
    """Return (dimension, category) pairs flagged as structurally infeasible."""
    if structural_detail_df is None or structural_detail_df.empty:
        return []

    allowed_dimensions = set(dimensions) if dimensions is not None else None
    pairs: set[Tuple[str, str]] = set()
    for row in structural_detail_df.itertuples(index=False):
        margin = float(getattr(row, "margin_over_cap_pp", 0.0) or 0.0)
        if margin <= 0:
            continue
        dimension = str(getattr(row, "dimension", ""))
        category = str(getattr(row, "category", ""))
        if allowed_dimensions is not None and dimension not in allowed_dimensions:
            continue
        if dimension and category:
            pairs.add((dimension, category))
    return sorted(pairs)


def is_category_suppressed(
    suppressed: List[Dict[str, Any]],
    dimension: str,
    category: Any,
    time_period: Any = None,
) -> bool:
    """Return True when a published row for this group should be omitted."""
    if not suppressed:
        return False

    category_key = str(category)
    for record in suppressed:
        if record.get("dimension") != dimension:
            continue
        if str(record.get("category")) != category_key:
            continue
        record_time = record.get("time_period")
        if record_time is None:
            return True
        if time_period is not None and str(record_time) == str(time_period):
            return True
    return False


def compute_suppressed_categories(
    df: pd.DataFrame,
    *,
    entity_col: str,
    target_entity: Optional[str],
    dimensions: List[str],
    metric_col: str,
    min_entities: int,
    time_col: Optional[str] = None,
    structural_infeasible: Optional[Iterable[Tuple[str, str]]] = None,
) -> List[Dict[str, Any]]:
    """Identify category groups that must not appear in published analyst artifacts."""
    suppressed: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str, Optional[str]]] = set()

    peer_df = df
    if target_entity is not None and entity_col in df.columns:
        peer_df = df[df[entity_col] != target_entity]

    effective_time_col = time_col if time_col and time_col in df.columns else None

    def _append_below_min_record(
        dimension: str,
        category: Any,
        time_period: Optional[Any],
        participants: int,
    ) -> None:
        dedupe_key = (str(dimension), str(category), str(time_period) if time_period is not None else None)
        if dedupe_key in seen:
            return
        seen.add(dedupe_key)
        suppressed.append(
            {
                "dimension": str(dimension),
                "category": str(category),
                "time_period": time_period,
                "participants": participants,
                "reason": "below_min_entities",
            }
        )

    for dimension in dimensions:
        if dimension not in peer_df.columns:
            continue

        group_cols = [dimension]
        if effective_time_col and effective_time_col != dimension:
            group_cols.append(effective_time_col)

        grouped = peer_df.groupby(group_cols, dropna=False)
        for group_key, group in grouped:
            if not isinstance(group_key, tuple):
                group_key = (group_key,)

            category = group_key[0]
            time_period: Optional[Any] = group_key[1] if len(group_key) > 1 else None
            if metric_col not in group.columns:
                continue

            participants = int(group.loc[group[metric_col] > 0, entity_col].nunique())
            if participants < min_entities:
                _append_below_min_record(dimension, category, time_period, participants)

        if effective_time_col:
            for category, group in peer_df.groupby(dimension, dropna=False):
                if metric_col not in group.columns:
                    continue
                participants = int(group.loc[group[metric_col] > 0, entity_col].nunique())
                if participants < min_entities:
                    _append_below_min_record(dimension, category, None, participants)

    for dimension, category in structural_infeasible or []:
        dedupe_key = (str(dimension), str(category), None)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        suppressed.append(
            {
                "dimension": str(dimension),
                "category": str(category),
                "time_period": None,
                "participants": 0,
                "reason": "structurally_infeasible",
            }
        )

    return suppressed


def format_suppression_warning(record: Dict[str, Any], *, min_entities: int) -> str:
    """Build a human-readable run warning for one suppression record."""
    dimension = record.get("dimension", "")
    category = record.get("category", "")
    if record.get("reason") == "structurally_infeasible":
        return f"Suppressed {dimension}/{category}: structurally infeasible"
    participants = record.get("participants", 0)
    return (
        f"Suppressed {dimension}/{category}: "
        f"{participants} participant(s) < rule minimum {min_entities}"
    )


def filter_suppressed_rows(
    results_df: pd.DataFrame,
    suppressed: List[Dict[str, Any]],
    dimension: str,
    time_col: Optional[str] = None,
) -> pd.DataFrame:
    """Drop result rows whose category group is suppressed for this dimension."""
    if results_df.empty or not suppressed:
        return results_df

    resolved_time_col = time_col
    if resolved_time_col is None and "Time_Period" in results_df.columns:
        resolved_time_col = "Time_Period"

    def _keep_row(row: pd.Series) -> bool:
        time_period = row[resolved_time_col] if resolved_time_col is not None else None
        return not is_category_suppressed(suppressed, dimension, row["Category"], time_period)

    return results_df.loc[results_df.apply(_keep_row, axis=1)].reset_index(drop=True)


def apply_suppression_to_results(
    results: Dict[str, Any],
    suppressed: List[Dict[str, Any]],
    *,
    is_rate: bool,
    time_col: Optional[str] = None,
) -> Dict[str, Any]:
    """Filter share or nested rate result DataFrames using suppression records."""
    if not suppressed:
        return results

    if is_rate:
        filtered: Dict[str, Any] = {}
        for rate_type, dimension_results in results.items():
            filtered[rate_type] = {
                dimension: filter_suppressed_rows(
                    dimension_df,
                    suppressed,
                    dimension,
                    time_col=time_col,
                )
                for dimension, dimension_df in dimension_results.items()
            }
        return filtered

    return {
        dimension: filter_suppressed_rows(
            dimension_df,
            suppressed,
            dimension,
            time_col=time_col,
        )
        for dimension, dimension_df in results.items()
    }
