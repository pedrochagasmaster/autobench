from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

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

    @staticmethod
    def build_request(
        peers: Optional[List[str]] = None,
        categories: Optional[List[Dict[str, Any]]] = None,
        max_concentration: Optional[float] = None,
        peer_volumes: Optional[Dict[str, float]] = None,
        **kwargs: Any,
    ) -> SolverRequest:
        return SolverRequest(
            peers=list(peers or []),
            categories=list(categories or []),
            max_concentration=float(max_concentration or 0.0),
            peer_volumes=dict(peer_volumes or {}),
            **kwargs,
        )

    @classmethod
    def coerce_request(
        cls,
        request: Optional[SolverRequest] = None,
        *,
        peers: Optional[List[str]] = None,
        categories: Optional[List[Dict[str, Any]]] = None,
        max_concentration: Optional[float] = None,
        peer_volumes: Optional[Dict[str, float]] = None,
        **kwargs: Any,
    ) -> SolverRequest:
        if request is not None:
            return request
        return cls.build_request(
            peers=peers,
            categories=categories,
            max_concentration=max_concentration,
            peer_volumes=peer_volumes,
            **kwargs,
        )

    @abstractmethod
    def solve(
        self,
        request: Optional[SolverRequest] = None,
        *,
        peers: Optional[List[str]] = None,
        categories: Optional[List[Dict[str, Any]]] = None,
        max_concentration: Optional[float] = None,
        peer_volumes: Optional[Dict[str, float]] = None,
        **kwargs: Any,
    ) -> Optional[SolverResult]:
        """Solve for privacy weights using an explicit request interface."""
        raise NotImplementedError
