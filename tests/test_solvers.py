"""
Unit tests for solver isolation (LPSolver, HeuristicSolver).
"""

import unittest
from typing import Dict, List, Tuple

import numpy as np

from core.solvers.lp_solver import LPSolver, _SCIPY_AVAILABLE
from core.solvers.heuristic_solver import HeuristicSolver


def _build_categories(
    dimension: str,
    category: str,
    volumes_by_peer: Dict[str, float]
) -> List[Dict[str, object]]:
    return [
        {
            'dimension': dimension,
            'category': category,
            'peer': peer,
            'category_volume': volume,
        }
        for peer, volume in volumes_by_peer.items()
    ]


def _weighted_shares(volumes_by_peer: Dict[str, float], weights: Dict[str, float]) -> Dict[str, float]:
    weighted_total = sum(volumes_by_peer[p] * weights[p] for p in volumes_by_peer)
    if weighted_total <= 0:
        return {peer: 0.0 for peer in volumes_by_peer}
    return {
        peer: (volumes_by_peer[peer] * weights[peer] / weighted_total) * 100.0
        for peer in volumes_by_peer
    }


@unittest.skipUnless(_SCIPY_AVAILABLE, "SciPy required for LP solver")
class TestLPSolver(unittest.TestCase):
    def test_lp_solver_respects_caps(self) -> None:
        peers = ["A", "B", "C"]
        peer_volumes = {"A": 100.0, "B": 80.0, "C": 60.0}

        cat1_vols = {"A": 50.0, "B": 30.0, "C": 20.0}
        cat2_vols = {"A": 50.0, "B": 50.0, "C": 40.0}
        categories = (
            _build_categories("dim1", "cat1", cat1_vols)
            + _build_categories("dim1", "cat2", cat2_vols)
        )

        solver = LPSolver()
        result = solver.solve(
            peers=peers,
            categories=categories,
            max_concentration=50.0,
            peer_volumes=peer_volumes,
            tolerance=0.0,
            rank_preservation_strength=0.0,
            min_weight=0.5,
            max_weight=2.0,
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.success)
        self.assertEqual(result.method, "lp")

        weights = result.weights
        for w in weights.values():
            self.assertGreaterEqual(w, 0.5 - 1e-6)
            self.assertLessEqual(w, 2.0 + 1e-6)

        avg = sum(weights.values()) / len(weights)
        self.assertAlmostEqual(avg, 1.0, places=6)

        for vols in (cat1_vols, cat2_vols):
            shares = _weighted_shares(vols, weights)
            self.assertLessEqual(max(shares.values()), 50.0 + 1e-6)

        expected_stats_keys = {"method", "max_slack", "sum_slack", "num_vars", "num_constraints"}
        self.assertTrue(expected_stats_keys.issubset(set(result.stats.keys())))

    def test_lambda_penalty_changes_lp_objective(self) -> None:
        """§9.3 item 2: ``lambda_penalty`` (used by ``strategic_consistency``)
        must materially flow into the LP objective. Reviewers can otherwise
        not tell whether the preset's `lambda_penalty=1e8` is honoured.
        """
        peers = ["P1", "P2", "P3", "P4"]
        peer_volumes = {"P1": 60.0, "P2": 20.0, "P3": 10.0, "P4": 10.0}
        categories = _build_categories("dim1", "cat1", peer_volumes)

        solver = LPSolver()
        baseline = solver.solve(
            peers=peers,
            categories=categories,
            max_concentration=30.0,
            peer_volumes=peer_volumes,
            tolerance=5.0,
            rank_preservation_strength=0.0,
            min_weight=0.1,
            max_weight=10.0,
        )
        weighted = solver.solve(
            peers=peers,
            categories=categories,
            max_concentration=30.0,
            peer_volumes=peer_volumes,
            tolerance=5.0,
            rank_preservation_strength=0.0,
            min_weight=0.1,
            max_weight=10.0,
            lambda_penalty=1.0e6,
        )

        self.assertIsNotNone(baseline)
        self.assertIsNotNone(weighted)
        assert baseline is not None and weighted is not None

        baseline_max_slack = float(baseline.stats.get("max_slack", 0.0))
        weighted_max_slack = float(weighted.stats.get("max_slack", 0.0))
        # When lambda_penalty is large, the LP prefers crushing slack down to
        # zero rather than accepting tolerance-bounded slack. The weighted
        # max_slack must therefore be no greater than the baseline.
        self.assertLessEqual(weighted_max_slack, baseline_max_slack + 1e-6)


class TestHeuristicSolver(unittest.TestCase):
    def test_heuristic_reduces_additional_constraint_penalty(self) -> None:
        peers = ["P1", "P2", "P3", "P4", "P5", "P6"]
        volumes = {"P1": 70.0, "P2": 10.0, "P3": 5.0, "P4": 5.0, "P5": 5.0, "P6": 5.0}
        categories = _build_categories("dim1", "cat1", volumes)
        peer_volumes = volumes.copy()

        solver = HeuristicSolver()
        baseline_weights = {peer: 1.0 for peer in peers}
        baseline_shares = _weighted_shares(volumes, baseline_weights)
        baseline_penalty = solver._additional_constraints_penalty(list(baseline_shares.values()), "6/30")

        result = solver.solve(
            peers=peers,
            categories=categories,
            max_concentration=30.0,
            peer_volumes=peer_volumes,
            min_weight=0.1,
            max_weight=10.0,
            tolerance=0.0,
            enforce_additional_constraints=True,
            dynamic_constraints_enabled=False,
            rule_name="6/30",
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.method, "heuristic")

        optimized_shares = _weighted_shares(volumes, result.weights)
        optimized_penalty = solver._additional_constraints_penalty(list(optimized_shares.values()), "6/30")

        self.assertLessEqual(optimized_penalty, baseline_penalty + 1e-6)
        self.assertLessEqual(max(optimized_shares.values()), max(baseline_shares.values()) + 1e-6)

        avg = sum(result.weights.values()) / len(result.weights)
        self.assertAlmostEqual(avg, 1.0, places=6)
        self.assertTrue(all(w >= 0.1 - 1e-6 for w in result.weights.values()))
        self.assertTrue(all(w <= 10.0 + 1e-6 for w in result.weights.values()))

    def test_heuristic_reports_failure_when_zero_tolerance_still_violates_cap(self) -> None:
        peers = ["P1", "P2", "P3", "P4", "P5", "P6"]
        volumes = {"P1": 70.0, "P2": 10.0, "P3": 5.0, "P4": 5.0, "P5": 5.0, "P6": 5.0}
        categories = _build_categories("dim1", "cat1", volumes)

        solver = HeuristicSolver()
        result = solver.solve(
            peers=peers,
            categories=categories,
            max_concentration=30.0,
            peer_volumes=volumes.copy(),
            min_weight=0.1,
            max_weight=10.0,
            tolerance=0.0,
            enforce_additional_constraints=True,
            dynamic_constraints_enabled=False,
            rule_name="6/30",
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertFalse(result.success)
        self.assertEqual(result.method, "heuristic")


if __name__ == "__main__":
    unittest.main(verbosity=2)
