from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional

from core.contracts import SolverRequest


@dataclass
class SolverResult:
    """Standardized result from a privacy solver."""
    weights: Dict[str, float]
    method: str
    stats: Dict[str, Any]
    success: bool


class PrivacySolver(ABC):
    """Abstract base class for privacy weight optimization solvers."""

    @abstractmethod
    def solve(self, request: SolverRequest) -> Optional[SolverResult]:
        """Solve for privacy weights using an explicit request interface."""
        raise NotImplementedError
