"""Fresh-process determinism matrix.

Set iteration order only changes between interpreter processes, so an in-process
test cannot prove the analytical pipeline is stable. Every case/preset pair is
therefore run in subprocesses seeded with different ``PYTHONHASHSEED`` values,
and the normalized analytical fingerprints must match exactly.

Included in the comparison: global weights, per-dimension weights, selected and
removed dimensions, weight methods, calculated benchmark values, privacy
verdicts, and suppression decisions. Excluded: timestamps, session identifiers,
generated file names, log creation times, and workbook binary data, none of
which the determinism guarantee covers.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pytest

from tests.determinism_support import CASES, PRESETS

REPO_ROOT = Path(__file__).resolve().parent.parent
HASH_SEEDS = ("1", "2", "4", "5", "17", "42")
PAIRS: List[Tuple[str, str]] = [
    (case, preset) for case in sorted(CASES) for preset in PRESETS
]


def _fingerprint(case: str, preset: str, seed: str, log_dir: Path) -> str:
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = seed
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["AUTOBENCH_TELEMETRY"] = "0"
    env["AUTOBENCH_LOG_DIR"] = str(log_dir)
    completed = subprocess.run(
        [sys.executable, "-m", "tests.determinism_support", case, preset],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"{case}/{preset} failed with PYTHONHASHSEED={seed}:\n{completed.stderr}"
        )
    return completed.stdout


@pytest.fixture(scope="module")
def fingerprint_matrix(tmp_path_factory: pytest.TempPathFactory) -> Dict[Tuple[str, str], Dict[str, str]]:
    """Collect one fingerprint per case, preset, and hash seed."""
    log_dir = tmp_path_factory.mktemp("determinism_logs")
    jobs: List[Tuple[str, str, str]] = [
        (case, preset, seed) for case, preset in PAIRS for seed in HASH_SEEDS
    ]
    with ThreadPoolExecutor(max_workers=max(os.cpu_count() or 2, 2)) as pool:
        results: Iterable[str] = pool.map(
            lambda job: _fingerprint(job[0], job[1], job[2], log_dir), jobs
        )
        collected = list(results)

    matrix: Dict[Tuple[str, str], Dict[str, str]] = {}
    for (case, preset, seed), fingerprint in zip(jobs, collected):
        matrix.setdefault((case, preset), {})[seed] = fingerprint
    return matrix


@pytest.mark.parametrize("case,preset", PAIRS, ids=lambda value: str(value))
def test_hash_seeds_produce_identical_analytical_results(
    case: str,
    preset: str,
    fingerprint_matrix: Dict[Tuple[str, str], Dict[str, str]],
) -> None:
    by_seed = fingerprint_matrix[(case, preset)]
    reference_seed = HASH_SEEDS[0]
    reference = by_seed[reference_seed]

    assert reference, f"{case}/{preset} produced an empty fingerprint"

    for seed in HASH_SEEDS[1:]:
        if by_seed[seed] == reference:
            continue
        expected = json.loads(reference)
        actual = json.loads(by_seed[seed])
        differing = sorted(
            key for key in set(expected) | set(actual)
            if expected.get(key) != actual.get(key)
        )
        raise AssertionError(
            f"{case}/{preset} differs between PYTHONHASHSEED={reference_seed} "
            f"and PYTHONHASHSEED={seed} in: {differing}"
        )


@pytest.mark.parametrize("preset", PRESETS)
def test_reversed_dimension_order_produces_same_weight_mapping(
    preset: str,
    fingerprint_matrix: Dict[Tuple[str, str], Dict[str, str]],
) -> None:
    """Supplying the dimensions in reverse must not move any peer's weight."""
    forward = json.loads(fingerprint_matrix[("solve_fallbacks", preset)][HASH_SEEDS[0]])
    reversed_run = json.loads(
        fingerprint_matrix[("solve_fallbacks_reversed", preset)][HASH_SEEDS[0]]
    )

    forward_weights = forward["analyzer"]["global_weights"]
    reversed_weights = reversed_run["analyzer"]["global_weights"]

    assert forward_weights
    assert list(forward_weights) == list(reversed_weights)
    assert {peer: record["multiplier"] for peer, record in forward_weights.items()} == {
        peer: record["multiplier"] for peer, record in reversed_weights.items()
    }


@pytest.mark.parametrize("preset", PRESETS)
def test_every_preset_reports_solver_output(
    preset: str,
    fingerprint_matrix: Dict[Tuple[str, str], Dict[str, str]],
) -> None:
    """Guard against a preset silently dropping out of the matrix."""
    fingerprint = json.loads(fingerprint_matrix[("solve_fallbacks", preset)][HASH_SEEDS[0]])
    analyzer = fingerprint["analyzer"]

    assert analyzer is not None
    assert analyzer["global_weights"], f"{preset} produced no global weights"
    assert analyzer["weight_methods"], f"{preset} produced no weight methods"
