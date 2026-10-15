"""Supported public facade for the benchmarking tool.

The light, pure-data contracts are imported eagerly. The engine-facing names
(``DimensionalAnalyzer``, ``DataLoader``, ...) and the submodules the facade
used to import eagerly are resolved on first attribute access through a PEP 562
``__getattr__``. That keeps ``import core`` (and therefore every
``from core.x import ...``) from pulling in scipy before it is needed, while
``from core import X``, ``core.X`` and ``from core import *`` resolve exactly
the same objects as before. ``tests/test_core_facade.py`` enumerates the
public surface to prove it.
"""

import importlib

from .contracts import (
    AnalysisArtifacts,
    AnalysisRunRequest,
    COVERAGE_CERTIFICATE_ARTIFACT_TYPE,
    CoverageCertificate,
    PrivacyConcentrationBasis,
    PrivacyEvaluationStatus,
    PrivacyFailureReason,
    PrivacyMandatoryOverlayEvaluation,
    PrivacyMetricContext,
    PrivacyOutputDecision,
    PrivacyReleaseMode,
    PrivacyRuleStrategy,
    PrivacyRuleStrategyEvaluation,
    PrivacyRuleStrategyResult,
    PrivacyRuleSweepEvaluation,
    PrivacySweepAuditMetadata,
    PrivacySweepRequest,
    PrivacySweepResult,
    PrivacySweepStatus,
    PrivacyThresholdEvaluation,
    PublicationUnit,
    SafeCoverageResult,
)

# Public name -> submodule that defines it. Imported on first access.
_LAZY_FACADE = {
    "evaluate_privacy_rule_sweep": "privacy_policy",
    "DimensionalAnalyzer": "dimensional_analyzer",
    "PrivacyValidator": "privacy_validator",
    "DataLoader": "data_loader",
    "ReportGenerator": "report_generator",
    # ``analysis_run`` imports ``utils.config_manager`` at module load, and
    # ``utils.config_manager`` in turn imports from this package. Importing it
    # eagerly here would create a circular import when ``utils.config_manager``
    # is the first module loaded.
    "execute_rate_run": "analysis_run",
    "execute_share_run": "analysis_run",
}

# Submodules that the eager facade used to load as a side effect of
# ``import core``, so ``core.<submodule>`` worked without importing it first.
# Attribute access keeps working: it imports the submodule on demand.
_LAZY_SUBMODULES = frozenset({
    "analysis_calculator",
    "canonical_order",
    "category_builder",
    "constants",
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
})

__all__ = [
    'AnalysisRunRequest',
    'AnalysisArtifacts',
    'COVERAGE_CERTIFICATE_ARTIFACT_TYPE',
    'CoverageCertificate',
    'PrivacySweepRequest',
    'PrivacyMetricContext',
    'PrivacyOutputDecision',
    'PrivacyReleaseMode',
    'PrivacyRuleStrategy',
    'PrivacyRuleStrategyEvaluation',
    'PrivacyRuleStrategyResult',
    'PrivacyConcentrationBasis',
    'PrivacyEvaluationStatus',
    'PrivacySweepStatus',
    'PrivacyFailureReason',
    'PrivacyThresholdEvaluation',
    'PrivacyRuleSweepEvaluation',
    'PrivacyMandatoryOverlayEvaluation',
    'PrivacySweepAuditMetadata',
    'PrivacySweepResult',
    'PublicationUnit',
    'SafeCoverageResult',
    'evaluate_privacy_rule_sweep',
    'execute_share_run',
    'execute_rate_run',
    'DimensionalAnalyzer',
    'PrivacyValidator',
    'DataLoader',
    'ReportGenerator',
]

def __getattr__(name: str):
    module_name = _LAZY_FACADE.get(name)
    if module_name is not None:
        value = getattr(importlib.import_module(f".{module_name}", __name__), name)
        globals()[name] = value
        return value
    if name in _LAZY_SUBMODULES:
        # Importing a submodule binds it on the package, so this runs once.
        return importlib.import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(_LAZY_FACADE) | _LAZY_SUBMODULES)
