"""Sanitized Getnet-shaped fixture for Maximum Safe Coverage tests.

Synthetic peers and categories only. No real merchant, issuer, or category
names. No confidential Getnet values.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import pandas as pd

FIXTURE_CSV_NAME = "safe_coverage_getnet_shaped.csv"

# Peer names are synthetic. PeerA is intentionally dominant in SectorX so that
# SectorX fails primary-cap / secondary checks under global weights that keep
# SectorY safe. PeerF is thin on merchant_count in SectorZ to create a
# secondary-metric-only failure shape when merchant_count is required.
_PEERS = ("PeerA", "PeerB", "PeerC", "PeerD", "PeerE", "PeerF")


def build_safe_coverage_getnet_shaped_df() -> pd.DataFrame:
    """Return a small multi-period, multi-dimension share fixture."""
    rows: List[dict] = []

    # Quarter Q1 / Region North / SectorY — intended safe under 5/25-like shares.
    safe_amounts = {
        "PeerA": 18.0,
        "PeerB": 17.0,
        "PeerC": 16.0,
        "PeerD": 16.0,
        "PeerE": 16.0,
        "PeerF": 17.0,
    }
    # Quarter Q1 / Region North / SectorX — PeerA-dominant unsafe amount shares.
    unsafe_amounts = {
        "PeerA": 70.0,
        "PeerB": 6.0,
        "PeerC": 6.0,
        "PeerD": 6.0,
        "PeerE": 6.0,
        "PeerF": 6.0,
    }
    # SectorZ amounts are balanced, but merchant_count is PeerA-dominant so a
    # secondary-metric-only failure exists when merchant_count is required.
    secondary_fail_amounts = {
        "PeerA": 20.0,
        "PeerB": 16.0,
        "PeerC": 16.0,
        "PeerD": 16.0,
        "PeerE": 16.0,
        "PeerF": 16.0,
    }
    secondary_fail_merchants = {
        "PeerA": 80.0,
        "PeerB": 4.0,
        "PeerC": 4.0,
        "PeerD": 4.0,
        "PeerE": 4.0,
        "PeerF": 4.0,
    }

    specs = (
        ("2025Q1", "North", "SectorY", safe_amounts, safe_amounts, safe_amounts),
        ("2025Q1", "North", "SectorX", unsafe_amounts, unsafe_amounts, unsafe_amounts),
        (
            "2025Q1",
            "South",
            "SectorZ",
            secondary_fail_amounts,
            secondary_fail_amounts,
            secondary_fail_merchants,
        ),
        ("2025Q2", "North", "SectorY", safe_amounts, safe_amounts, safe_amounts),
        ("2025Q2", "South", "SectorX", unsafe_amounts, unsafe_amounts, unsafe_amounts),
    )

    for quarter, region, sector, amounts, txns, merchants in specs:
        for peer in _PEERS:
            amount = float(amounts[peer])
            txn = float(txns[peer])
            merchant = float(merchants[peer])
            rows.append(
                {
                    "issuer_name": peer,
                    "quarter": quarter,
                    "region": region,
                    "sector": sector,
                    "transaction_amount": amount * 1000.0,
                    "transaction_count": txn * 10.0,
                    "merchant_count": merchant,
                }
            )
    return pd.DataFrame(rows)


def write_safe_coverage_getnet_shaped_csv(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    build_safe_coverage_getnet_shaped_df().to_csv(path, index=False)
    return path


def default_fixture_csv_path() -> Path:
    return Path(__file__).with_name(FIXTURE_CSV_NAME)
