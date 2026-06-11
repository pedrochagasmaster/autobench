"""Neutralize Excel/CSV formula injection for untrusted export cells."""

from __future__ import annotations

from typing import Any

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_cell(value: Any) -> Any:
    """Neutralize Excel formula injection for untrusted string cells."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value
