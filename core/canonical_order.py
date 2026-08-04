"""Canonical ordering rule for analytical inputs.

Analytical results must not depend on how a label happened to reach the
optimizer. Python set iteration order changes between processes, and pandas
first-appearance order changes when rows are reordered, so solver-facing
sequences (peers, dimensions, constraint keys, time periods) pass through the
single ordering rule defined here before they reach a solver.

The canonical key is ``(str(value), type(value).__name__)``. The string form is
primary so labels sort the way an analyst reads them, and the type name is the
secondary key so mixed-type labels such as ``1`` and ``"1"`` keep a fixed order
instead of raising a comparison error.
"""

from __future__ import annotations

from typing import Any, Iterable, List, Tuple


def canonical_key(value: Any) -> Tuple[str, str]:
    """Return the documented stable sort key for an analytical label."""
    return (str(value), type(value).__name__)


def canonical_order(values: Iterable[Any]) -> List[Any]:
    """Return the distinct ``values`` in canonical order."""
    return sorted(dict.fromkeys(values), key=canonical_key)
