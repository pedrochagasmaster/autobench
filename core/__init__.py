"""Supported public facade for the benchmarking tool."""

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
from .privacy_policy import evaluate_privacy_rule_sweep
from .dimensional_analyzer import DimensionalAnalyzer
from .privacy_validator import PrivacyValidator
from .data_loader import DataLoader
from .report_generator import ReportGenerator

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

# ``analysis_run`` imports ``utils.config_manager`` at module load, and
# ``utils.config_manager`` in turn imports from this package. Importing it
# eagerly here creates a circular import when ``utils.config_manager`` is the
# first module loaded. Resolve it lazily so attribute access still works
# (e.g. ``core.execute_share_run``) without forcing the import at package init.
def __getattr__(name: str):
    if name in ("execute_rate_run", "execute_share_run"):
        from . import analysis_run
        return getattr(analysis_run, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
