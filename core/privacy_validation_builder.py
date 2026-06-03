"""Legacy Privacy Validation DataFrame rendering adapter."""

from __future__ import annotations

import pandas as pd
from typing import List

from core.privacy_validation import build_privacy_validation_result


def build_privacy_validation_dataframe(analyzer, df: pd.DataFrame, metric_col: str, dimensions: List[str]) -> pd.DataFrame:
    """Render typed privacy validation rows using the legacy column schema."""
    return build_privacy_validation_result(analyzer, df, metric_col, dimensions).to_dataframe()
