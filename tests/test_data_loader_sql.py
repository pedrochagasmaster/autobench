"""Tests for SQL loading helpers in core/data_loader.py."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.data_loader import DataLoader
from utils.config_manager import ConfigManager


class SqliteConfig(ConfigManager):
    def __init__(self, connection: sqlite3.Connection) -> None:
        super().__init__()
        self._connection = connection

    def get_sql_connection(self) -> sqlite3.Connection:
        return self._connection


def _sqlite_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute(
        'CREATE TABLE benchmarks ("Issuer_Name" TEXT, "Txn Cnt" INTEGER)'
    )
    connection.execute(
        'INSERT INTO benchmarks ("Issuer_Name", "Txn Cnt") VALUES (?, ?)',
        ("Target", 100),
    )
    connection.commit()
    return connection


def test_validate_sql_identifier_rejects_unsafe_names() -> None:
    loader = DataLoader(ConfigManager())
    with pytest.raises(ValueError):
        loader._validate_sql_identifier("users;drop table")
    with pytest.raises(ValueError):
        loader._validate_sql_identifier("123bad")


def test_validate_sql_identifier_accepts_safe_names() -> None:
    loader = DataLoader(ConfigManager())
    loader._validate_sql_identifier("issuer_name")
    loader._validate_sql_identifier("schema_table")


def test_load_from_sql_query_uses_configured_connection_and_normalizes_columns(tmp_path: Path) -> None:
    connection = _sqlite_connection()
    query_file = tmp_path / "query.sql"
    query_file.write_text('SELECT "Issuer_Name", "Txn Cnt" FROM benchmarks', encoding="utf-8")
    loader = DataLoader(SqliteConfig(connection))

    df = loader.load_from_sql_query(str(query_file))

    assert list(df.columns) == ["issuer_name", "txn_cnt"]
    assert df.iloc[0].to_dict() == {"issuer_name": "Target", "txn_cnt": 100}


def test_load_from_sql_table_uses_safe_identifier_and_normalizes_columns() -> None:
    connection = _sqlite_connection()
    loader = DataLoader(SqliteConfig(connection))

    df = loader.load_from_sql_table("benchmarks")

    assert list(df.columns) == ["issuer_name", "txn_cnt"]
    assert df.iloc[0].to_dict() == {"issuer_name": "Target", "txn_cnt": 100}
