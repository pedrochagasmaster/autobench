"""
Unit tests for ReportGenerator dependency handling.
"""

import unittest
from unittest.mock import MagicMock, patch

from core.report_generator import ReportGenerator


class TestReportGeneratorDependencies(unittest.TestCase):
    def test_generate_report_requires_openpyxl(self) -> None:
        generator = ReportGenerator(MagicMock())

        real_import = __import__

        def guarded_import(name, *args, **kwargs):
            if name == "openpyxl":
                raise ImportError("No module named 'openpyxl'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=guarded_import):
            with self.assertRaises(ImportError) as ctx:
                generator.generate_report(
                    results={},
                    output_file="dummy.xlsx",
                    format="excel",
                    analysis_type="share",
                    metadata=None,
                )

        self.assertIn("openpyxl", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
