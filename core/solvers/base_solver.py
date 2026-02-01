from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional, List

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
    def solve(
        self, 
        peers: List[str], 
        categories: List[Dict[str, Any]], 
        max_concentration: float, 
        peer_volumes: Dict[str, float],
        **kwargs
    ) -> Optional[SolverResult]:
        """
        Solve for privacy weights.
        
        Parameters:
        -----------
        peers : List[str]
            List of peer entity names
        categories : List[Dict]
            List of category definitions (constraints)
        max_concentration : float
            Maximum allowed share percentage (e.g. 25.0)
        peer_volumes : Dict[str, float]
            Total volumes for each peer
            
        Returns:
        --------
        SolverResult or None if solver fails/is inapplicable
        """
        pass
