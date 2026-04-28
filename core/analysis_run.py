"""Shared orchestration helpers for analysis run setup."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from core.data_loader import DataLoader, ValidationIssue, ValidationSeverity
from core.report_generator import ReportGenerator
from core.validation_runner import run_input_validation
from utils.config_manager import ConfigManager

COMMON_CLI_OVERRIDES = (
    'entity_col',
    'time_col',
    'debug',
    'log_level',
    'per_dimension_weights',
    'auto',
    'auto_subset_search',
    'subset_search_max_tests',
    'trigger_subset_on_slack',
    'max_cap_slack',
    'validate_input',
    'compare_presets',
    'output_format',
    'include_calculated',
)


def build_run_config(
    args: argparse.Namespace,
    *,
    extra_overrides: Optional[Dict[str, Any]] = None,
) -> ConfigManager:
    """Create ConfigManager from common run-time CLI overrides."""
    cli_overrides: Dict[str, Any] = {
        key: getattr(args, key, None)
        for key in COMMON_CLI_OVERRIDES
    }
    cli_overrides['analyze_distortion'] = (
        getattr(args, 'analyze_impact', None)
        or getattr(args, 'analyze_distortion', None)
    )
    if extra_overrides:
        cli_overrides.update(extra_overrides)
    cli_overrides = {k: v for k, v in cli_overrides.items() if v is not None}

    return ConfigManager(
        config_file=getattr(args, 'config', None),
        preset=getattr(args, 'preset', None),
        cli_overrides=cli_overrides,
    )


def resolve_output_settings(config: ConfigManager) -> Dict[str, Any]:
    """Resolve commonly-used output flags from merged config."""
    include_impact_summary = config.get('output', 'include_impact_summary', default=None)
    if include_impact_summary is None:
        include_impact_summary = config.get('output', 'include_distortion_summary', default=False)

    return {
        'include_preset_comparison': config.get('output', 'include_preset_comparison', default=False),
        'include_impact_summary': include_impact_summary,
        'include_calculated_metrics': config.get('output', 'include_calculated_metrics', default=False),
        'include_privacy_validation': config.get('output', 'include_privacy_validation', default=False),
        'include_audit_log': config.get('output', 'include_audit_log', default=True),
        'output_format': config.get('output', 'output_format', default='analysis'),
        'fraud_in_bps': config.get('output', 'fraud_in_bps', default=True),
    }


def resolve_input_dataframe(args: argparse.Namespace, data_loader: DataLoader) -> pd.DataFrame:
    """Return a preloaded DataFrame when present, otherwise load from the configured source."""
    df = getattr(args, 'df', None)
    if df is not None:
        return df
    return data_loader.load_data(args)


def resolve_entity_column(
    df: pd.DataFrame,
    preferred_entity_col: str,
) -> str:
    """Resolve the entity column using configured preference then standard fallbacks."""
    if preferred_entity_col in df.columns:
        return preferred_entity_col
    if 'issuer_name' in df.columns:
        return 'issuer_name'
    if 'entity_identifier' in df.columns:
        return 'entity_identifier'
    raise ValueError(f"Entity column '{preferred_entity_col}' not found in data")


def prepare_run_data(
    args: argparse.Namespace,
    config: ConfigManager,
    logger: logging.Logger,
    *,
    preferred_entity_col: str,
) -> Tuple[DataLoader, pd.DataFrame, str, Optional[str]]:
    """Create the loader, resolve the input DataFrame, entity column, and time column."""
    data_loader = DataLoader(config)
    df = resolve_input_dataframe(args, data_loader)
    logger.info(f"Loaded {len(df)} records with {len(df.columns)} columns")
    entity_col = resolve_entity_column(df, preferred_entity_col)
    time_col = config.get('input', 'time_col')
    return data_loader, df, entity_col, time_col


def resolve_target_entity(
    df: pd.DataFrame,
    entity_col: str,
    target_entity: Optional[str],
    logger: logging.Logger,
) -> Optional[str]:
    """Resolve the user-supplied target entity to the canonical dataset value."""
    resolved_entity = target_entity
    if target_entity:
        entity_upper = str(target_entity).upper()
        all_matches = [
            entity for entity in df[entity_col].unique()
            if entity is not None and str(entity).upper() == entity_upper
        ]
        if len(all_matches) > 1:
            logger.error(f"Ambiguous entity name: '{target_entity}' matches multiple entities: {all_matches}")
            logger.error("Please specify the exact entity name with correct casing.")
            return None
        if len(all_matches) == 1:
            match = str(all_matches[0])
            if match != target_entity:
                logger.warning(f"Target entity case mismatch. Using '{match}' instead of '{target_entity}'.")
            resolved_entity = match
    return resolved_entity


def validate_analysis_input(
    *,
    df: pd.DataFrame,
    config: ConfigManager,
    data_loader: DataLoader,
    analysis_type: str,
    entity_col: str,
    time_col: Optional[str],
    target_entity: Optional[str],
    dimensions: Optional[List[str]] = None,
    metric_col: Optional[str] = None,
    total_col: Optional[str] = None,
    numerator_cols: Optional[Dict[str, str]] = None,
) -> Tuple[Optional[List[ValidationIssue]], bool]:
    """Run validation using shared dimension-defaulting behavior."""
    validation_dimensions = dimensions if dimensions else data_loader.get_available_dimensions(df)
    return run_input_validation(
        df=df,
        config=config,
        data_loader=data_loader,
        analysis_type=analysis_type,
        metric_col=metric_col,
        total_col=total_col,
        numerator_cols=numerator_cols,
        entity_col=entity_col,
        dimensions=validation_dimensions,
        time_col=time_col,
        target_entity=target_entity,
    )


def resolve_dimensions(
    args: argparse.Namespace,
    config: ConfigManager,
    data_loader: DataLoader,
    df: pd.DataFrame,
    logger: logging.Logger,
) -> Optional[List[str]]:
    """Resolve dimensions from explicit args or auto-detection settings."""
    if args.dimensions:
        dimensions = args.dimensions
        logger.info(f"Using specified dimensions: {dimensions}")
        return dimensions

    auto_flag = getattr(args, 'auto', None)
    auto_config = config.get('analysis', 'auto_detect_dimensions', default=False)
    should_auto = bool(auto_flag) if auto_flag is not None else bool(auto_config)
    if should_auto:
        dimensions = data_loader.get_available_dimensions(df)
        logger.info(f"Auto-detected {len(dimensions)} dimensions: {dimensions}")
        return dimensions

    logger.error("No dimensions provided. Use --dimensions or enable auto-detect (--auto or config.analysis.auto_detect_dimensions).")
    return None


def build_report_paths(
    output_format: str,
    analysis_output_file: str,
    publication_output: Optional[str] = None,
) -> List[str]:
    """Build the ordered list of generated report outputs."""
    report_paths: List[str] = []
    if output_format in ('analysis', 'both'):
        report_paths.append(analysis_output_file)
    if output_format in ('publication', 'both') and publication_output:
        report_paths.append(publication_output)
    return report_paths


def summarize_validation_issues(
    validation_issues: Optional[List[ValidationIssue]],
) -> Dict[str, int]:
    """Count validation issues by severity for audit logging."""
    if not validation_issues:
        return {}

    return {
        'validation_errors': sum(1 for issue in validation_issues if issue.severity == ValidationSeverity.ERROR),
        'validation_warnings': sum(1 for issue in validation_issues if issue.severity == ValidationSeverity.WARNING),
        'validation_infos': sum(1 for issue in validation_issues if issue.severity == ValidationSeverity.INFO),
    }


def write_audit_log(
    config: ConfigManager,
    *,
    analysis_output_file: str,
    metadata: Dict[str, Any],
    report_paths: List[str],
    dimensions_analyzed: int,
    csv_output: Optional[str] = None,
    impact_df: Optional[pd.DataFrame] = None,
    privacy_validation_df: Optional[pd.DataFrame] = None,
    validation_issues: Optional[List[ValidationIssue]] = None,
) -> str:
    """Create the audit log for a completed analysis run."""
    audit_log_file = str(Path(analysis_output_file).with_name(f"{Path(analysis_output_file).stem}_audit.log"))
    impact_summary = metadata.get('impact_summary', {}) if isinstance(metadata, dict) else {}
    results_summary = {
        'dimensions_analyzed': dimensions_analyzed,
        'categories_analyzed': len(impact_df) if impact_df is not None else None,
        'impact_mean_abs_pp': impact_summary.get('mean_abs_impact_pp'),
        'privacy_rule': metadata.get('privacy_rule'),
        'additional_constraint_violations_count': metadata.get('additional_constraint_violations_count'),
        'privacy_validation_rows': len(privacy_validation_df) if privacy_validation_df is not None else 0,
        'outputs': report_paths,
        'balanced_csv': csv_output,
    }
    results_summary.update(summarize_validation_issues(validation_issues))
    audit_metadata = {key: value for key, value in metadata.items() if key != 'analyzer_ref'}
    ReportGenerator(config).create_audit_log(audit_log_file, audit_metadata, results_summary)
    return audit_log_file
