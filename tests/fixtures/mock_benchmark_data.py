from pathlib import Path

import pandas as pd


def build_mock_benchmark_df() -> pd.DataFrame:
    entities = ["Target", "P1", "P2", "P3", "P4", "P5", "P6"]
    rows = []
    volumes = {
        ("2024-01", "CREDIT", "Online"): [100, 420, 90, 80, 70, 60, 50],
        ("2024-01", "CREDIT", "Store"): [120, 180, 160, 150, 140, 130, 120],
        ("2024-01", "DEBIT", "Online"): [80, 90, 85, 80, 75, 70, 65],
        ("2024-02", "CREDIT", "Online"): [95, 400, 95, 85, 75, 65, 55],
        ("2024-02", "CREDIT", "Store"): [110, 175, 165, 155, 145, 135, 125],
        ("2024-02", "DEBIT", "Online"): [85, 92, 88, 82, 78, 72, 68],
    }
    for (month, card_type, channel), values in volumes.items():
        for entity, txn in zip(entities, values):
            total = txn * 10
            rows.append({
                "issuer_name": entity,
                "year_month": month,
                "card_type": card_type,
                "channel": channel,
                "txn_cnt": txn,
                "total": total,
                "approved": int(total * (0.88 if entity == "P1" else 0.92)),
                "fraud": max(1, int(total * (0.012 if entity == "P1" else 0.006))),
            })
    return pd.DataFrame(rows)


def write_mock_benchmark_csv(path: Path) -> Path:
    build_mock_benchmark_df().to_csv(path, index=False)
    return path


def write_insufficient_peer_csv(path: Path) -> Path:
    rows = []
    for entity, txn in [("Target", 100), ("P1", 900), ("P2", 50), ("P3", 50)]:
        rows.append({
            "issuer_name": entity,
            "card_type": "A",
            "channel": "Online",
            "txn_cnt": txn,
            "total": txn * 10,
            "approved": txn * 9,
            "fraud": max(1, txn // 100),
        })
    pd.DataFrame(rows).to_csv(path, index=False)
    return path
