"""Lightweight observability helper for analysis runs."""

from __future__ import annotations

import time
from typing import Any, Dict, List


class RunObservability:
    """Records timing and event metadata for a single analysis run."""

    def __init__(self) -> None:
        self._events: List[Dict[str, Any]] = []
        self._start = time.monotonic()

    def record(self, event: str, **kwargs: Any) -> None:
        self._events.append({
            "event": event,
            "elapsed_s": round(time.monotonic() - self._start, 3),
            **kwargs,
        })

    def as_metadata(self) -> Dict[str, Any]:
        return {
            "events": list(self._events),
            "total_elapsed_s": round(time.monotonic() - self._start, 3),
        }
