"""Tests for SQL loading helpers in core/data_loader.py."""

from __future__ import annotations

import pytest

from core.data_loader import DataLoader
from utils.config_manager import ConfigManager


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
