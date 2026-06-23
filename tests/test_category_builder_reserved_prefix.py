import unittest

import pandas as pd

from core.category_builder import CategoryBuilder


class TestCategoryBuilderReservedPrefix(unittest.TestCase):
    def test_reserved_dimension_prefix_is_rejected(self) -> None:
        builder = CategoryBuilder(
            entity_column="issuer_name",
            target_entity=None,
            time_column=None,
            consistent_weights=False,
        )
        df = pd.DataFrame(
            {
                "issuer_name": ["A", "B"],
                "_TIME_CUSTOM": ["x", "y"],
                "txn_cnt": [1, 2],
            }
        )
        with self.assertRaises(ValueError):
            builder.build_categories(df, "txn_cnt", ["_TIME_CUSTOM"])


if __name__ == "__main__":
    unittest.main()
