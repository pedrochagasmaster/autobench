from types import SimpleNamespace

import pandas as pd

from core.balanced_export import _iter_balanced_groups
from core.contracts import WeightLookup


def test_iter_balanced_groups_handles_target_time_weights_and_suppression() -> None:
    df = pd.DataFrame(
        {
            "issuer_name": ["Target", "P1", "P2", "Target", "P1", "P2"],
            "segment": ["A", "A", "A", "B", "B", "B"],
            "period": [1, 1, 1, 2, 2, 2],
            "metric": [100, 10, 20, 200, 30, 40],
        }
    )
    analyzer = SimpleNamespace(
        entity_column="issuer_name",
        target_entity="Target",
        time_column="period",
    )
    weights = WeightLookup(
        global_weights={"P1": {"multiplier": 2.0}, "P2": {"multiplier": 3.0}},
        per_dimension_weights={"segment": {"P1": 4.0}},
    )
    groups = list(
        _iter_balanced_groups(
            df,
            analyzer=analyzer,
            dimensions=["segment"],
            metric_columns=["metric"],
            weights=weights,
            suppressed_categories=[
                {"dimension": "segment", "category": "B", "time_period": 2}
            ],
            exclude_target=True,
        )
    )
    assert len(groups) == 1
    group = groups[0]
    assert (group.dimension, group.category, group.time_period) == ("segment", "A", 1)
    assert group.category_rows["issuer_name"].tolist() == ["P1", "P2", "Target"]
    assert group.rows["issuer_name"].tolist() == ["P1", "P2"]
    assert group.peer_weights.tolist() == [4.0, 3.0]

    unfiltered = list(
        _iter_balanced_groups(
            df,
            analyzer=analyzer,
            dimensions=["segment"],
            metric_columns=["metric"],
            weights=weights,
            suppressed_categories=[],
            exclude_target=False,
        )
    )
    unfiltered_a = next(group for group in unfiltered if group.category == "A")
    assert unfiltered_a.rows["issuer_name"].tolist() == ["P1", "P2", "Target"]
