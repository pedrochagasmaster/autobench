"""The lazy ``core/__init__`` facade is behaviour-neutral (owner decision 8).

``PUBLIC_NAMES`` and ``EAGER_SUBMODULES`` are a snapshot of ``dir(core)`` taken
from the eager facade at ``9cd167c`` (``import core`` in a fresh interpreter,
non-dunder names). Every one of them must still resolve, to the same object,
both as ``core.<name>`` and through ``from core import <name>``. Each check
runs in a fresh interpreter so an earlier import cannot mask a missing name.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Snapshot of the eager facade's public names (``__all__`` at 9cd167c).
ALL_SNAPSHOT = (
    "AnalysisRunRequest",
    "AnalysisArtifacts",
    "COVERAGE_CERTIFICATE_ARTIFACT_TYPE",
    "CoverageCertificate",
    "PrivacySweepRequest",
    "PrivacyMetricContext",
    "PrivacyOutputDecision",
    "PrivacyReleaseMode",
    "PrivacyRuleStrategy",
    "PrivacyRuleStrategyEvaluation",
    "PrivacyRuleStrategyResult",
    "PrivacyConcentrationBasis",
    "PrivacyEvaluationStatus",
    "PrivacySweepStatus",
    "PrivacyFailureReason",
    "PrivacyThresholdEvaluation",
    "PrivacyRuleSweepEvaluation",
    "PrivacyMandatoryOverlayEvaluation",
    "PrivacySweepAuditMetadata",
    "PrivacySweepResult",
    "PublicationUnit",
    "SafeCoverageResult",
    "evaluate_privacy_rule_sweep",
    "execute_share_run",
    "execute_rate_run",
    "DimensionalAnalyzer",
    "PrivacyValidator",
    "DataLoader",
    "ReportGenerator",
)

# Name -> module that defines it, for the identity check.
DEFINING_MODULE = {
    "evaluate_privacy_rule_sweep": "core.privacy_policy",
    "DimensionalAnalyzer": "core.dimensional_analyzer",
    "PrivacyValidator": "core.privacy_validator",
    "DataLoader": "core.data_loader",
    "ReportGenerator": "core.report_generator",
    "execute_share_run": "core.analysis_run",
    "execute_rate_run": "core.analysis_run",
}

# Submodules the eager facade bound on ``core`` as a side effect of ``import core``.
EAGER_SUBMODULES = (
    "analysis_calculator",
    "canonical_order",
    "category_builder",
    "constants",
    "contracts",
    "data_loader",
    "diagnostics_engine",
    "dimensional_analyzer",
    "export_sanitizer",
    "global_weight_optimizer",
    "impact_calculator",
    "privacy_policy",
    "privacy_rules",
    "privacy_validation",
    "privacy_validator",
    "report_content",
    "report_generator",
    "report_models",
    "solver_request_builder",
    "solvers",
    "subset_search",
)

PUBLIC_NAMES = tuple(sorted(set(ALL_SNAPSHOT) | set(EAGER_SUBMODULES)))


def _run(code: str) -> dict:
    out = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_all_is_unchanged() -> None:
    import core

    assert tuple(core.__all__) == ALL_SNAPSHOT


def test_import_core_does_not_load_the_engine() -> None:
    result = _run(
        """
        import json, sys
        import core
        heavy = ["scipy", "core.analysis_run", "core.dimensional_analyzer",
                 "core.solvers.lp_solver", "core.data_loader", "core.report_generator"]
        print(json.dumps({name: name in sys.modules for name in heavy}))
        """
    )
    assert not any(result.values()), result


@pytest.mark.parametrize("name", PUBLIC_NAMES)
def test_every_public_name_resolves_in_a_fresh_interpreter(name: str) -> None:
    result = _run(
        f"""
        import importlib, json, types
        import core
        via_attr = getattr(core, {name!r})
        namespace = {{}}
        exec("from core import {name}", namespace)
        via_from = namespace[{name!r}]
        if isinstance(via_attr, types.ModuleType):
            expected = importlib.import_module("core." + {name!r})
        else:
            source = {DEFINING_MODULE.get(name, "core.contracts")!r}
            expected = getattr(importlib.import_module(source), {name!r})
        print(json.dumps({{
            "attr_is_expected": via_attr is expected,
            "from_is_expected": via_from is expected,
            "in_dir": {name!r} in dir(core),
        }}))
        """
    )
    assert result == {"attr_is_expected": True, "from_is_expected": True, "in_dir": True}


def test_star_import_exports_exactly_all() -> None:
    result = _run(
        """
        import json
        namespace = {}
        exec("from core import *", namespace)
        print(json.dumps(sorted(k for k in namespace if k != "__builtins__")))
        """
    )
    assert result == sorted(ALL_SNAPSHOT)


def test_unknown_attribute_still_raises_attribute_error() -> None:
    import core

    with pytest.raises(AttributeError):
        core.definitely_not_a_core_name  # noqa: B018
    assert not hasattr(core, "definitely_not_a_core_name")

