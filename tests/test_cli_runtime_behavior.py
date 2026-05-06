"""CLI runtime behavior tests from the audit investigation."""

import subprocess
import sys
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from core.dimensional_analyzer import DimensionalAnalyzer
from core.privacy_validator import PrivacyValidator
from tests.fixtures.mock_benchmark_data import write_insufficient_peer_csv, write_mock_benchmark_csv


def test_mock_share_cli_produces_diagnostic_sheets(tmp_path: Path) -> None:
    csv_path = write_mock_benchmark_csv(tmp_path / "mock.csv")
    output = tmp_path / "share_both.xlsx"

    result = subprocess.run(
        [
            sys.executable, "benchmark.py", "share",
            "--metric", "txn_cnt",
            "--csv", str(csv_path),
            "--entity-col", "issuer_name",
            "--entity", "Target",
            "--dimensions", "card_type", "channel",
            "--time-col", "year_month",
            "--output", str(output),
            "--output-format", "both",
            "--debug",
            "--validate-input",
        ],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    assert output.exists()
    assert (tmp_path / "share_both_publication.xlsx").exists()
    workbook = load_workbook(output, read_only=True)
    try:
        assert "Privacy Validation" in workbook.sheetnames
        assert "Peer Weights" in workbook.sheetnames
        assert "Weight Methods" in workbook.sheetnames
    finally:
        workbook.close()


def test_privacy_validator_matches_weighted_mock_behavior(tmp_path: Path) -> None:
    csv_path = write_mock_benchmark_csv(tmp_path / "mock.csv")
    df = pd.read_csv(csv_path)
    peers_df = df[df["issuer_name"] != "Target"]
    raw_online = peers_df[
        (peers_df["year_month"] == "2024-01") & (peers_df["channel"] == "Online")
    ].groupby("issuer_name", as_index=False)["txn_cnt"].sum()
    validator = PrivacyValidator(rule_name="6/30")

    raw_ok, raw_warnings = validator.validate_peer_group(raw_online, ["txn_cnt"], "issuer_name")

    assert raw_ok is False

    analyzer = DimensionalAnalyzer(
        target_entity="Target",
        entity_column="issuer_name",
        time_column="year_month",
        debug_mode=True,
        consistent_weights=True,
    )
    analyzer.calculate_global_privacy_weights(df, "txn_cnt", ["card_type", "channel"])
    weights = {peer: data["multiplier"] for peer, data in analyzer.global_weights.items()}
    weighted_online = raw_online.copy()
    weighted_online["txn_cnt"] = weighted_online.apply(
        lambda row: row["txn_cnt"] * weights.get(row["issuer_name"], 1.0),
        axis=1,
    )

    weighted_ok, weighted_warnings = validator.validate_peer_group(weighted_online, ["txn_cnt"], "issuer_name")
    validation_df = analyzer.build_privacy_validation_dataframe(df, "txn_cnt", ["card_type", "channel"])

    assert weighted_ok is True
    assert weighted_warnings == []
    assert int((validation_df["Compliant"] == "No").sum()) == 0
