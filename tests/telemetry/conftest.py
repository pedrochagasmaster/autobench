from __future__ import annotations

import sys
from pathlib import Path


_NON_LINUX_TESTS = {
    "test_events.py",
    "test_platform_portability.py",
    "test_render.py",
}


def pytest_ignore_collect(collection_path: Path) -> bool | None:
    """Run Linux telemetry integration coverage only where its primitives exist."""
    if sys.platform == "linux":
        return None
    if collection_path.parent != Path(__file__).parent:
        return None
    if not collection_path.name.startswith("test_"):
        return None
    return collection_path.name not in _NON_LINUX_TESTS
