"""Report content model helpers (sheet policy and rate conversion)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from core.contracts import OutputSettings


@dataclass
class PublicationDiagnosticAllowList:
    """Diagnostic sheets permitted in publication workbooks."""

    sheet_names: Sequence[str] = field(
        default_factory=lambda: (
            "Impact Summary",
            "Peer Weights",
            "Privacy Validation",
            "Rank Changes",
            "Preset Comparison",
        )
    )

    def is_allowed(self, sheet_name: str) -> bool:
        return sheet_name in self.sheet_names


def resolve_convert_all_rates(metadata: Optional[Dict[str, Any]]) -> bool:
    if not metadata:
        return False
    analysis_label = str(metadata.get("analysis_type", "")).lower()
    rate_types = [str(rt).lower() for rt in metadata.get("rate_types", [])]
    if rate_types and all(rt == "fraud" for rt in rate_types):
        return True
    return "fraud_rate" in analysis_label and not rate_types


def should_convert_rate_column(column_name: str, convert_all_rates: bool) -> bool:
    col_lower = str(column_name).lower().strip()
    non_rate_markers = (
        "impact",
        "effect",
        "distortion",
        "weight",
        "multiplier",
        "total",
        "volume",
        "count",
        "numerator",
        "denominator",
    )
    if any(marker in col_lower for marker in non_rate_markers):
        return False

    rate_patterns = (
        col_lower.endswith("_raw_%"),
        col_lower.endswith("_balanced_%"),
        col_lower in {"target rate (%)", "balanced peer average (%)", "bic (%)"},
        "rate" in col_lower,
    )
    if not any(rate_patterns):
        return False
    if convert_all_rates:
        return True
    return "fraud" in col_lower


def apply_rate_display_conversion(
    df: pd.DataFrame,
    *,
    analysis_type: str,
    metadata: Optional[Dict[str, Any]],
    fraud_in_bps: bool,
    metric_name: Optional[str] = None,
) -> pd.DataFrame:
    """Apply publication/analysis rate unit conversion without mutating the input."""
    if analysis_type != "rate":
        return df

    converted = df.copy(deep=True)
    convert_all_rates = resolve_convert_all_rates(metadata)
    if fraud_in_bps:
        for col in converted.columns:
            if not pd.api.types.is_numeric_dtype(converted[col]):
                continue
            if should_convert_rate_column(col, convert_all_rates):
                converted[col] = converted[col] * 100
        converted.columns = [
            (
                str(col).replace("(%)", "(bps)").replace("Rate %", "Rate (bps)")
                if "fraud" in str(col).lower() and "bps" not in str(col).lower()
                else col
            )
            for col in converted.columns
        ]

    rate_prefix = None
    if metric_name and analysis_type == "rate" and "_" in str(metric_name):
        rate_prefix = str(metric_name).split("_", 1)[0]
    if fraud_in_bps and rate_prefix == "fraud":
        renamed_columns: List[Any] = []
        for col in converted.columns:
            col_str = str(col)
            if col_str == "Balanced Peer Average (%)":
                renamed_columns.append("Fraud Rate (bps)" if fraud_in_bps else "Fraud Rate (%)")
            elif col_str == "Original Peer Average (%)":
                renamed_columns.append("Original Fraud Rate (bps)" if fraud_in_bps else "Original Fraud Rate (%)")
            elif col_str == "Target Rate (%)":
                renamed_columns.append("Target Fraud Rate (bps)" if fraud_in_bps else "Target Fraud Rate (%)")
            else:
                renamed_columns.append(col)
        converted.columns = renamed_columns
    return converted


def publication_diagnostics_enabled(output_settings: OutputSettings) -> bool:
    """Whether optional diagnostic sheets should appear in publication output."""
    return output_settings.output_format in ("publication", "both")
