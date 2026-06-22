"""Regression tests for defects found during the feature-audit (Phase 3 fixes).

Each test pins a specific logistical bug uncovered while testing the documented
user stories in ``docs/FEATURE_USER_STORIES.csv``.
"""

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_category_builder_missing_time_column_does_not_recurse():
    """C-042: a set-but-absent time column must fall back, not infinite-loop."""
    from core.category_builder import CategoryBuilder

    df = pd.DataFrame(
        {
            "issuer_name": ["Target", "P1", "P2", "P3", "P4", "P5"],
            "card_type": ["CREDIT"] * 6,
            "txn_cnt": [100, 420, 380, 250, 190, 160],
        }
    )
    builder = CategoryBuilder(
        entity_column="issuer_name",
        target_entity="Target",
        time_column="year_month",  # deliberately absent from df
        consistent_weights=True,
    )

    categories, peer_volumes, peers = builder.build_categories(df, "txn_cnt", ["card_type"])

    assert peers, "expected standard-aggregation fallback to yield peers"
    assert all("time_period" not in cat for cat in categories)


def test_config_manager_importable_first_without_circular_import():
    """Importing utils.config_manager first must not trigger a circular import."""
    result = subprocess.run(
        [sys.executable, "-c", "import utils.config_manager as m; print(m.ConfigManager.__name__)"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "ConfigManager" in result.stdout


def test_default_column_mapping_includes_documented_aliases():
    """F-012: documented txn_cnt / amt aliases must be present."""
    from utils.config_manager import ConfigManager

    mapping = ConfigManager.DEFAULT_COLUMN_MAPPING
    assert mapping.get("txn_cnt") == "transaction_count"
    assert mapping.get("amt") == "transaction_amount"


def test_legacy_distortion_keys_from_config_file_map_to_impact(tmp_path):
    """F-010: legacy distortion keys in a config file must override impact keys."""
    from utils.config_manager import ConfigManager

    cfg = tmp_path / "legacy.yaml"
    cfg.write_text(
        "version: '3.0'\n"
        "compliance_posture: strict\n"
        "output:\n"
        "  include_distortion_summary: false\n"
        "  distortion_thresholds:\n"
        "    high_distortion_pp: 2.5\n"
        "    low_distortion_pp: 0.5\n"
    )
    manager = ConfigManager(config_file=str(cfg))
    output_cfg = manager.config.get("output", {})

    assert output_cfg.get("include_impact_summary") is False
    assert output_cfg.get("impact_thresholds", {}).get("high_pp") == 2.5
    assert output_cfg.get("impact_thresholds", {}).get("low_pp") == 0.5


def test_config_show_unknown_preset_returns_nonzero():
    """F-026: ``config show`` on an unknown preset must exit non-zero."""
    result = subprocess.run(
        [sys.executable, "benchmark.py", "config", "show", "no_such_preset_xyz"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "not found" in result.stdout.lower()


@pytest.mark.parametrize(
    "reason, fragment",
    [
        ("fraud_chargeback_requires_clearing_spend_basis", "clearing_spend"),
        ("top_merchant_lists_not_allowed", "top-merchant"),
    ],
)
def test_control3_remediation_hint(reason, fragment):
    """A-010/A-044: block reason codes resolve to actionable remediation hints."""
    from core.control3_policy import remediation_hint

    hint = remediation_hint(reason)
    assert hint and fragment in hint
    assert remediation_hint(None) is None
