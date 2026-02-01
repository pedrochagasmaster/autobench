"""
Validation orchestration for both share and rate analysis.
Extracted to eliminate code duplication between run_share_analysis() and run_rate_analysis().
"""
import logging
from typing import List, Optional, Dict, Any, Tuple, TYPE_CHECKING

import pandas as pd

from core.data_loader import DataLoader, ValidationIssue, ValidationSeverity
if TYPE_CHECKING:
    from utils.config_manager import ConfigManager

logger = logging.getLogger(__name__)


def _summarize_issues(issues: List[ValidationIssue]) -> Tuple[int, int, int]:
    errors = [i for i in issues if i.severity == ValidationSeverity.ERROR]
    warnings = [i for i in issues if i.severity == ValidationSeverity.WARNING]
    infos = [i for i in issues if i.severity == ValidationSeverity.INFO]
    return len(errors), len(warnings), len(infos)


def _log_validation_issue(issue: ValidationIssue) -> None:
    severity_loggers = {
        ValidationSeverity.ERROR: logger.error,
        ValidationSeverity.WARNING: logger.warning,
        ValidationSeverity.INFO: logger.info,
    }
    log_fn = severity_loggers.get(issue.severity, logger.info)
    severity_label = getattr(issue.severity, 'value', str(issue.severity))
    log_fn(f"VALIDATION {severity_label} [{issue.category}]: {issue.message}")


def run_input_validation(
    df: pd.DataFrame,
    config: "ConfigManager",
    data_loader: DataLoader,
    analysis_type: str,
    metric_col: Optional[str] = None,
    total_col: Optional[str] = None,
    numerator_cols: Optional[Dict[str, str]] = None,
    entity_col: str = 'issuer_name',
    dimensions: Optional[List[str]] = None,
    time_col: Optional[str] = None,
    target_entity: Optional[str] = None,
) -> Tuple[Optional[List[ValidationIssue]], bool]:
    """
    Run validation and return issues + should_abort flag.

    Parameters
    ----------
    df : pd.DataFrame
        Input data
    config : ConfigManager
        Configuration manager instance
    data_loader : DataLoader
        Data loader with validation methods
    analysis_type : str
        'share' or 'rate'
    metric_col : str, optional
        For share analysis: the metric column
    total_col : str, optional
        For rate analysis: the denominator column
    numerator_cols : dict, optional
        For rate analysis: mapping of rate name to numerator column
    entity_col : str
        Entity identifier column
    dimensions : list, optional
        Dimensions to validate
    time_col : str, optional
        Time column if present
    target_entity : str, optional
        Target entity for analysis

    Returns
    -------
    Tuple[Optional[List[ValidationIssue]], bool]
        (issues, should_abort): List of issues and whether to abort analysis.
        issues is None if validation is disabled.
    """
    validate_input = config.get('input', 'validate_input', default=True)
    if not validate_input:
        logger.info("Input validation is disabled.")
        return None, False

    logger.info("Running input data validation...")

    val_dimensions = dimensions or data_loader.get_available_dimensions(df)
    thresholds = config.get('input', 'validation_thresholds', default={})
    merchant_mode = config.get('analysis', 'merchant_mode', default=False)
    if merchant_mode:
        thresholds = dict(thresholds)
        thresholds['min_peer_count'] = min(int(thresholds.get('min_peer_count', 5)), 4)

    if analysis_type == 'share':
        issues = data_loader.validate_share_input(
            df=df,
            metric_col=metric_col,
            entity_col=entity_col,
            dimensions=val_dimensions,
            time_col=time_col,
            target_entity=target_entity,
            thresholds=thresholds
        )
    elif analysis_type == 'rate':
        issues = data_loader.validate_rate_input(
            df=df,
            total_col=total_col,
            numerator_cols=numerator_cols or {},
            entity_col=entity_col,
            dimensions=val_dimensions,
            time_col=time_col,
            target_entity=target_entity,
            thresholds=thresholds
        )
    else:
        logger.error(f"Unknown analysis type: {analysis_type}")
        return [], True

    for issue in issues:
        _log_validation_issue(issue)

    error_count, warning_count, info_count = _summarize_issues(issues)

    if error_count:
        logger.error(f"Found {error_count} ERROR(s), {warning_count} WARNING(s), {info_count} INFO(s)")
        logger.error("Analysis ABORTED due to validation errors. Fix the data and retry.")
        return issues, True
    elif warning_count:
        logger.warning(f"Found {warning_count} WARNING(s), {info_count} INFO(s). Proceeding with analysis.")
    elif info_count:
        logger.info(f"Found {info_count} INFO(s). Data quality is good.")
    else:
        logger.info("Input validation passed with no issues.")

    return issues, False
