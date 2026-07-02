"""Tests for under-populated and structurally infeasible category suppression (F1)."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from core.analysis_run import execute_share_run
from core.category_suppression import (
    apply_suppression_to_results,
    compute_suppressed_categories,
    filter_suppressed_rows,
    is_category_suppressed,
)
from core.contracts import AnalysisRunRequest

FIXTURE = Path(__file__).parent / "fixtures" / "gate_demo.csv"
SHARE_DIMENSIONS = ["card_type", "channel"]


def _build_peer_df(
    *,
    include_prepaid_exclusive: bool = False,
    include_duo_category: bool = False,
    time_aware: bool = False,
) -> pd.DataFrame:
    entities = ["Target", "P1", "P2", "P3", "P4", "P5", "P6"]
    rows: list[dict[str, object]] = []
    months = ["2024-01", "2024-02"] if time_aware else ["2024-01"]

    for month in months:
        for entity in entities:
            rows.append(
                {
                    "issuer_name": entity,
                    "year_month": month,
                    "card_type": "CREDIT",
                    "channel": "Online",
                    "txn_cnt": 100,
                    "total": 1000,
                    "approved": 900,
                    "fraud": 10,
                }
            )

    if include_prepaid_exclusive:
        rows.append(
            {
                "issuer_name": "P1",
                "year_month": "2024-01",
                "card_type": "PREPAID",
                "channel": "Online",
                "txn_cnt": 250,
                "total": 2500,
                "approved": 2200,
                "fraud": 25,
            }
        )

    if include_duo_category:
        for entity in ("P1", "P2"):
            rows.append(
                {
                    "issuer_name": entity,
                    "year_month": "2024-01",
                    "card_type": "DUO",
                    "channel": "Online",
                    "txn_cnt": 150,
                    "total": 1500,
                    "approved": 1350,
                    "fraud": 15,
                }
            )

    if time_aware:
        rows.append(
            {
                "issuer_name": "P1",
                "year_month": "2024-02",
                "card_type": "SPARSE",
                "channel": "Online",
                "txn_cnt": 80,
                "total": 800,
                "approved": 720,
                "fraud": 8,
            }
        )

    return pd.DataFrame(rows)


class TestComputeSuppressedCategories:
    def test_exclusive_category_suppressed(self) -> None:
        df = _build_peer_df(include_prepaid_exclusive=True)
        suppressed = compute_suppressed_categories(
            df,
            entity_col="issuer_name",
            target_entity="Target",
            dimensions=["card_type"],
            metric_col="txn_cnt",
            min_entities=6,
        )
        prepaid = [record for record in suppressed if record["category"] == "PREPAID"]
        assert len(prepaid) == 1
        assert prepaid[0]["reason"] == "below_min_entities"
        assert prepaid[0]["participants"] == 1

    def test_duo_category_suppressed(self) -> None:
        df = _build_peer_df(include_duo_category=True)
        suppressed = compute_suppressed_categories(
            df,
            entity_col="issuer_name",
            target_entity="Target",
            dimensions=["card_type"],
            metric_col="txn_cnt",
            min_entities=6,
        )
        duo = [record for record in suppressed if record["category"] == "DUO"]
        assert len(duo) == 1
        assert duo[0]["participants"] == 2

    def test_well_populated_category_untouched(self) -> None:
        df = _build_peer_df()
        suppressed = compute_suppressed_categories(
            df,
            entity_col="issuer_name",
            target_entity="Target",
            dimensions=["card_type"],
            metric_col="txn_cnt",
            min_entities=6,
        )
        assert not any(record["category"] == "CREDIT" for record in suppressed)

    def test_target_excluded_from_participant_count(self) -> None:
        df = _build_peer_df(include_prepaid_exclusive=True)
        rows = df.to_dict("records")
        rows.append(
            {
                "issuer_name": "Target",
                "year_month": "2024-01",
                "card_type": "PREPAID",
                "channel": "Online",
                "txn_cnt": 500,
                "total": 5000,
                "approved": 4500,
                "fraud": 50,
            }
        )
        df = pd.DataFrame(rows)
        suppressed = compute_suppressed_categories(
            df,
            entity_col="issuer_name",
            target_entity="Target",
            dimensions=["card_type"],
            metric_col="txn_cnt",
            min_entities=6,
        )
        prepaid = [record for record in suppressed if record["category"] == "PREPAID"]
        assert len(prepaid) == 1
        assert prepaid[0]["participants"] == 1

    def test_time_aware_grouping(self) -> None:
        df = _build_peer_df(time_aware=True)
        suppressed = compute_suppressed_categories(
            df,
            entity_col="issuer_name",
            target_entity="Target",
            dimensions=["card_type"],
            metric_col="txn_cnt",
            min_entities=6,
            time_col="year_month",
        )
        sparse = [record for record in suppressed if record["category"] == "SPARSE"]
        assert len(sparse) == 2
        assert any(record["time_period"] == "2024-02" for record in sparse)
        assert any(record["time_period"] is None for record in sparse)

    def test_structural_infeasible_deduped_when_below_min(self) -> None:
        df = _build_peer_df(include_prepaid_exclusive=True)
        suppressed = compute_suppressed_categories(
            df,
            entity_col="issuer_name",
            target_entity="Target",
            dimensions=["card_type"],
            metric_col="txn_cnt",
            min_entities=6,
            structural_infeasible=[("card_type", "PREPAID")],
        )
        prepaid = [record for record in suppressed if record["category"] == "PREPAID"]
        assert len(prepaid) == 1
        assert prepaid[0]["reason"] == "below_min_entities"

    def test_structural_infeasible_without_under_population(self) -> None:
        df = _build_peer_df()
        suppressed = compute_suppressed_categories(
            df,
            entity_col="issuer_name",
            target_entity="Target",
            dimensions=["card_type"],
            metric_col="txn_cnt",
            min_entities=6,
            structural_infeasible=[("card_type", "CREDIT")],
        )
        credit = [record for record in suppressed if record["category"] == "CREDIT"]
        assert len(credit) == 1
        assert credit[0]["reason"] == "structurally_infeasible"


class TestFilterSuppressedRows:
    def test_filter_share_results(self) -> None:
        results_df = pd.DataFrame(
            {
                "Category": ["CREDIT", "PREPAID"],
                "Balanced_txn_cnt": [100.0, 250.0],
            }
        )
        suppressed = [
            {
                "dimension": "card_type",
                "category": "PREPAID",
                "time_period": None,
                "participants": 1,
                "reason": "below_min_entities",
            }
        ]
        filtered = filter_suppressed_rows(results_df, suppressed, "card_type")
        assert list(filtered["Category"]) == ["CREDIT"]

    def test_apply_suppression_rate_shape(self) -> None:
        results = {
            "approval": {
                "card_type": pd.DataFrame({"Category": ["CREDIT", "PREPAID"], "Rate": [90.0, 100.0]}),
            },
            "fraud": {
                "card_type": pd.DataFrame({"Category": ["CREDIT", "PREPAID"], "Rate": [1.0, 2.0]}),
            },
        }
        suppressed = [
            {
                "dimension": "card_type",
                "category": "PREPAID",
                "time_period": None,
                "participants": 1,
                "reason": "below_min_entities",
            }
        ]
        filtered = apply_suppression_to_results(results, suppressed, is_rate=True)
        assert "approval" in filtered
        assert list(filtered["approval"]["card_type"]["Category"]) == ["CREDIT"]
        assert list(filtered["fraud"]["card_type"]["Category"]) == ["CREDIT"]


class TestIsCategorySuppressed:
    def test_category_level_suppression_applies_to_all_times(self) -> None:
        suppressed = [
            {
                "dimension": "card_type",
                "category": "PREPAID",
                "time_period": None,
                "participants": 1,
                "reason": "structurally_infeasible",
            }
        ]
        assert is_category_suppressed(suppressed, "card_type", "PREPAID", "2024-01")
        assert is_category_suppressed(suppressed, "card_type", "PREPAID", "2024-02")
        assert not is_category_suppressed(suppressed, "card_type", "CREDIT", "2024-01")


def test_share_run_suppresses_exclusive_category(tmp_path: Path) -> None:
    csv_path = tmp_path / "exclusive.csv"
    _build_peer_df(include_prepaid_exclusive=True).to_csv(csv_path, index=False)
    out = tmp_path / "share_exclusive.xlsx"

    request = AnalysisRunRequest(
        csv=str(csv_path),
        entity="Target",
        metric="txn_cnt",
        dimensions=["card_type"],
        time_col="year_month",
        preset="balanced_default",
        compliance_posture="strict",
        output=str(out),
        export_balanced_csv=True,
    )
    artifacts = execute_share_run(request, logging.getLogger("test"))

    card_type_df = artifacts.results["card_type"]
    assert "PREPAID" not in card_type_df["Category"].values

    csv_output = pd.read_csv(artifacts.csv_output)
    assert "PREPAID" not in csv_output["Category"].values

    suppressed = artifacts.metadata.get("suppressed_categories", [])
    assert any(record["category"] == "PREPAID" for record in suppressed)
    assert any("PREPAID" in warning for warning in artifacts.metadata.get("run_warnings", []))

    privacy_df = artifacts.privacy_validation_df
    assert privacy_df is not None
    assert "PREPAID" in privacy_df["Category"].values


def test_gate_demo_produces_no_suppressions(tmp_path: Path) -> None:
    out = tmp_path / "gate_share.xlsx"
    request = AnalysisRunRequest(
        csv=str(FIXTURE),
        entity="Target",
        metric="txn_cnt",
        dimensions=SHARE_DIMENSIONS,
        time_col="year_month",
        preset="balanced_default",
        compliance_posture="strict",
        output=str(out),
    )
    artifacts = execute_share_run(request, logging.getLogger("test"))
    assert artifacts.metadata.get("suppressed_categories", []) == []
