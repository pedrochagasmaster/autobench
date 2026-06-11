"""Shared orchestration helpers for analysis run setup."""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

from core.compliance import build_blocked_compliance_summary, build_compliance_summary
from core.control3_policy import CONTROL3_POLICY_KEYS, Control3PolicyInput, evaluate_control3_policy
from core.audit_log import build_audit_log_model
from core.audit_package import write_audit_package
from core.balanced_export import export_balanced_csv, get_balanced_metrics_df
from core.contracts import (
    AnalysisArtifacts,
    AnalysisPlan,
    AnalysisResult,
    AnalysisRunRequest,
    DataQualityResult,
    OutputSettings,
    PreparedDataset,
    RunSummary,
    WeightLookup,
    WeightingResult,
)
from core.data_loader import DataLoader, ValidationIssue, ValidationSeverity
from core.dimensional_analyzer import DimensionalAnalyzer
from core.observability import RunObservability
from core.output_artifacts import write_outputs
from core.preset_comparison import run_preset_comparison as execute_preset_comparison
from core.report_artifact_builder import build_analysis_artifacts
from core.report_generator import ReportGenerator
from core.validation_runner import run_input_validation
from utils.config_manager import ConfigManager, ResolvedConfig

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
    'report_format',
    'include_calculated',
    'audit_package',
    'validate_export',
    'lean',
    'compliance_posture',
)


def resolve_consistency_mode(
    resolved: ResolvedConfig,
    logger: logging.Logger,
) -> Tuple[bool, str]:
    """Translate config consistency mode into a bool for the analyzer."""
    consistency_mode = resolved.constraints.consistency_mode
    mode_normalized = str(consistency_mode).strip().lower().replace('_', '-')
    if mode_normalized in ('per-dimension', 'perdimension', 'per dimension'):
        return False, consistency_mode
    if mode_normalized in ('global', 'consistent', 'global-weights'):
        return True, consistency_mode

    logger.warning("Unknown consistency_mode '%s', defaulting to global weights", consistency_mode)
    return True, consistency_mode


def build_dimensional_analyzer(
    *,
    target_entity: Optional[str],
    entity_col: str,
    resolved: ResolvedConfig,
    time_col: Optional[str],
    debug_mode: bool,
    bic_percentile: float,
    logger: logging.Logger,
    consistent_weights: Optional[bool] = None,
) -> Tuple[DimensionalAnalyzer, Dict[str, Any]]:
    """Build a DimensionalAnalyzer from merged resolved configuration."""
    dyn_constraints = resolved.constraints.dynamic_constraints
    if consistent_weights is None:
        consistent_weights, consistency_mode = resolve_consistency_mode(resolved, logger)
    else:
        consistency_mode = resolved.constraints.consistency_mode

    rank_penalty_weight = resolved.linear_programming.rank_penalty_weight
    volume_preservation = resolved.constraints.volume_preservation
    rank_preservation_strength = volume_preservation * float(rank_penalty_weight)
    lambda_penalty = resolved.linear_programming.lambda_penalty
    bayesian_max_iterations = resolved.bayesian.max_iterations
    bayesian_learning_rate = resolved.bayesian.learning_rate
    violation_penalty_weight = resolved.bayesian.violation_penalty_weight
    enforce_single_weight_set = resolved.constraints.enforce_single_weight_set

    analyzer = DimensionalAnalyzer.from_resolved(
        resolved,
        target_entity=target_entity,
        entity_column=entity_col,
        time_column=time_col,
        debug_mode=debug_mode,
        bic_percentile=bic_percentile,
        consistent_weights=consistent_weights,
        rank_preservation_strength=rank_preservation_strength,
        lambda_penalty=lambda_penalty,
    )
    return analyzer, {
        'consistent_weights': consistent_weights,
        'consistency_mode': consistency_mode,
        'rank_penalty_weight': rank_penalty_weight,
        'rank_preservation_strength': rank_preservation_strength,
        'lambda_penalty': lambda_penalty,
        'bayesian_max_iterations': bayesian_max_iterations,
        'bayesian_learning_rate': bayesian_learning_rate,
        'violation_penalty_weight': violation_penalty_weight,
        'enforce_single_weight_set': enforce_single_weight_set,
        'dynamic_constraints_config': dyn_constraints,
    }


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
    control3_overrides = getattr(args, 'control3_overrides', None)
    if isinstance(control3_overrides, dict):
        cli_overrides.update(control3_overrides)
    else:
        cli_overrides.update(
            {
                key: getattr(args, key)
                for key in CONTROL3_POLICY_KEYS
                if getattr(args, key, None) is not None
            }
        )
    cli_overrides = {k: v for k, v in cli_overrides.items() if v is not None}

    return ConfigManager(
        config_file=getattr(args, 'config', None),
        preset=getattr(args, 'preset', None),
        cli_overrides=cli_overrides,
    )


def resolve_output_settings(config: ConfigManager) -> OutputSettings:
    """Resolve commonly-used output flags from merged config."""
    return resolve_output_settings_from_config(config.resolve(), AnalysisRunRequest())


def resolve_output_settings_from_config(
    resolved: ResolvedConfig,
    request: AnalysisRunRequest,
) -> OutputSettings:
    """Resolve output flags from typed config plus request defaults."""
    return OutputSettings(
        include_preset_comparison=bool(resolved.output.include_preset_comparison),
        include_impact_summary=bool(resolved.output.include_impact_summary),
        include_calculated_metrics=bool(resolved.output.include_calculated_metrics),
        include_privacy_validation=bool(resolved.output.include_privacy_validation),
        include_audit_log=bool(resolved.output.include_audit_log),
        include_audit_package=bool(resolved.output.include_audit_package),
        output_format=str(resolved.output.output_format or request.output_format),
        fraud_in_bps=bool(resolved.output.fraud_in_bps),
    )


def build_analysis_plan(
    request: AnalysisRunRequest,
    resolved: ResolvedConfig,
    *,
    entity: Optional[str] = None,
    entity_column: Optional[str] = None,
    dimensions: Optional[List[str]] = None,
    output_settings: Optional[OutputSettings] = None,
) -> AnalysisPlan:
    metric_columns: Dict[str, str] = {}
    if request.is_share and request.metric:
        metric_columns["metric"] = request.metric
    if request.is_rate:
        if request.total_col:
            metric_columns["total"] = request.total_col
        metric_columns.update(request.numerator_cols)
    return AnalysisPlan(
        request=request,
        resolved_config=resolved,
        entity=entity if entity is not None else request.entity,
        entity_column=entity_column or request.entity_col,
        dimensions=list(dimensions if dimensions is not None else (request.dimensions or [])),
        metric_columns=metric_columns,
        output_settings=output_settings or resolve_output_settings_from_config(resolved, request),
    )


def finalize_analysis_result(
    *,
    plan: AnalysisPlan,
    weighting_result: WeightingResult,
    privacy_validation: Any,
    data_quality: DataQualityResult,
    results: Any,
    compliance_summary: Dict[str, Any],
) -> AnalysisResult:
    return AnalysisResult(
        plan=plan,
        weighting=weighting_result,
        privacy_validation=privacy_validation,
        data_quality=data_quality,
        results=results,
        compliance_summary=compliance_summary,
    )


def analysis_result_to_metadata(result: AnalysisResult) -> Dict[str, Any]:
    return {
        "weighting_compliance_state": result.weighting.compliance_state,
        "data_quality_checked": result.data_quality.checked,
        "data_quality_publishable": result.data_quality.publishable,
        "validation_errors": result.data_quality.errors,
        "validation_warnings": result.data_quality.warnings,
    }


def build_common_run_metadata(
    args: argparse.Namespace,
    resolved: ResolvedConfig,
    analyzer: Any,
    *,
    resolved_entity: Optional[str],
    entity_col: str,
    total_records: int,
    unique_entities: int,
    dimensions_analyzed: int,
    dimension_names: List[str],
    secondary_metrics: Optional[List[str]],
    debug_mode: bool,
    consistent_weights: bool,
    include_privacy_validation: bool,
    include_impact_summary: bool,
    include_preset_comparison: bool,
    include_calculated_metrics: bool,
    output_format: str,
    consistency_mode: str,
    enforce_single_weight_set: bool,
) -> Dict[str, Any]:
    """Build the shared metadata envelope for completed analysis runs."""
    peer_count = unique_entities if resolved_entity is None else max(unique_entities - 1, 0)
    compliance_posture = resolved.compliance_posture
    high_impact_pp = resolved.output.impact_thresholds.get(
        'high_pp',
        resolved.output.distortion_thresholds.get('high_distortion_pp', 1.0),
    )
    low_impact_pp = resolved.output.impact_thresholds.get(
        'low_pp',
        resolved.output.distortion_thresholds.get('low_distortion_pp', 0.25),
    )

    return {
        'entity': resolved_entity or 'PEER-ONLY',
        'secondary_metrics': secondary_metrics,
        'entity_column': entity_col,
        'total_records': total_records,
        'unique_entities': unique_entities,
        'peer_count': peer_count,
        'dimensions_analyzed': dimensions_analyzed,
        'dimension_names': list(dimension_names),
        'preset': getattr(args, 'preset', None),
        'compliance_posture': compliance_posture,
        'acknowledgement_state': (
            'required_and_given'
            if compliance_posture == 'accuracy_first' and getattr(args, 'acknowledge_accuracy_first', False)
            else ('required_missing' if compliance_posture == 'accuracy_first' else 'not_required')
        ),
        'debug_mode': debug_mode,
        'consistent_weights': consistent_weights,
        'merchant_mode': resolved.analysis.merchant_mode,
        'include_debug_sheets': debug_mode,
        'include_privacy_validation': include_privacy_validation,
        'include_impact_summary': include_impact_summary,
        'include_preset_comparison': include_preset_comparison,
        'include_calculated_metrics': include_calculated_metrics,
        'output_format': output_format,
        'timestamp': datetime.now(),
        'input_csv': getattr(args, 'csv', None),
        'log_level': getattr(args, 'log_level', None),
        'dimensions_mode': 'manual' if bool(getattr(args, 'dimensions', None)) else ('auto' if getattr(args, 'auto', False) else 'manual'),
        'dimensions_requested': getattr(args, 'dimensions', None),
        'entity_col_arg': getattr(args, 'entity_col', None),
        'consistency_mode': consistency_mode,
        'enforce_single_weight_set': enforce_single_weight_set,
        'max_iterations': resolved.linear_programming.max_iterations,
        'tolerance_pp': resolved.linear_programming.tolerance,
        'max_weight': resolved.bounds.max_weight,
        'min_weight': resolved.bounds.min_weight,
        'volume_preservation_strength': resolved.constraints.volume_preservation,
        'rank_penalty_weight': resolved.linear_programming.rank_penalty_weight,
        'rank_preservation_strength': getattr(analyzer, 'rank_preservation_strength', None),
        'prefer_slacks_first': resolved.subset_search.prefer_slacks_first,
        'lambda_penalty': resolved.linear_programming.lambda_penalty,
        'volume_weighted_penalties': resolved.linear_programming.volume_weighted_penalties,
        'volume_weighting_exponent': resolved.linear_programming.volume_weighting_exponent,
        'subset_search_enabled': resolved.subset_search.enabled,
        'subset_search_strategy': resolved.subset_search.strategy,
        'subset_search_max_tests': resolved.subset_search.max_attempts,
        'subset_search_trigger_on_slack': resolved.subset_search.trigger_on_slack,
        'subset_search_max_slack_threshold': resolved.subset_search.max_slack_threshold,
        'bayesian_max_iterations': resolved.bayesian.max_iterations,
        'bayesian_learning_rate': resolved.bayesian.learning_rate,
        'violation_penalty_weight': resolved.bayesian.violation_penalty_weight,
        'structural_infeasibility_summary': analyzer.get_structural_infeasibility_summary(),
        'privacy_rule': getattr(analyzer, 'privacy_rule_name', None),
        'additional_constraints_enforced': getattr(analyzer, 'enforce_additional_constraints', False),
        'additional_constraint_violations_count': len(getattr(analyzer, 'additional_constraint_violations', []) or []),
        'dynamic_constraints_enabled': getattr(analyzer, 'dynamic_constraints_enabled', False),
        'dynamic_constraints_stats': getattr(analyzer, 'dynamic_constraint_stats', {}),
        'dynamic_constraints_config': resolved.constraints.dynamic_constraints,
        'impact_thresholds': {
            'high_pp': high_impact_pp,
            'low_pp': low_impact_pp,
        },
        'control3_policy_declarations': resolved.control3.to_metadata_dict(),
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
    if getattr(args, 'df', None) is not None:
        # TUI validation already normalizes in some paths; repeating is harmless and keeps CLI parity.
        df = data_loader._normalize_columns(df.copy())
    logger.info(f"Loaded {len(df)} records with {len(df.columns)} columns")
    entity_col = resolve_entity_column(df, preferred_entity_col)
    time_col = config.get('input', 'time_col')
    return data_loader, df, entity_col, time_col


def apply_prepared_dataset(
    request: AnalysisRunRequest,
    config: ConfigManager,
    logger: logging.Logger,
    *,
    preferred_entity_col: str,
) -> Tuple[Optional[DataLoader], Optional[pd.DataFrame], Optional[str], Optional[str], bool]:
    """Use a pre-validated dataset from the request when available.

    Returns ``(data_loader, df, entity_col, time_col, used_prepared)``.
    """
    prepared = request.prepared_dataset
    if prepared is None or prepared.df is None:
        return None, None, None, None, False

    data_loader = prepared.data_loader or DataLoader(config)
    df = prepared.df
    entity_col = prepared.entity_col or resolve_entity_column(df, preferred_entity_col)
    time_col = prepared.time_col if prepared.time_col is not None else config.get('input', 'time_col')
    logger.info(
        "Using pre-validated dataset (%s records, %s columns)",
        len(df),
        len(df.columns),
    )
    return data_loader, df, entity_col, time_col, True


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
) -> DataQualityResult:
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


def build_data_quality_from_validation_issues(
    issues: Optional[List[ValidationIssue]],
) -> DataQualityResult:
    """Build a data-quality result from already-collected validation issues."""
    issues_list = issues if issues is not None else []

    def severity_value(issue: ValidationIssue) -> str:
        severity = getattr(issue, "severity", "")
        return str(getattr(severity, "value", severity)).upper()

    errors = sum(1 for issue in issues_list if severity_value(issue) == "ERROR")
    warnings = sum(1 for issue in issues_list if severity_value(issue) == "WARNING")
    infos = sum(1 for issue in issues_list if severity_value(issue) == "INFO")
    return DataQualityResult(
        checked=True,
        errors=errors,
        warnings=warnings,
        infos=infos,
        issues=issues,
        should_abort=errors > 0,
    )


def should_reuse_prepared_validation(request: AnalysisRunRequest, *, used_prepared: bool) -> bool:
    """Return true when a prepared dataset already carries validation results."""
    prepared = request.prepared_dataset
    return bool(used_prepared and prepared is not None and prepared.validation_issues is not None)


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
        time_col = config.get('input', 'time_col')
        if time_col:
            dimensions = [dim for dim in dimensions if dim != time_col]
        logger.info(f"Auto-detected {len(dimensions)} dimensions: {dimensions}")
        return dimensions

    logger.error("No dimensions provided. Use --dimensions or enable auto-detect (--auto or config.analysis.auto_detect_dimensions).")
    return None


def collect_run_diagnostics(
    *,
    analyzer: Any,
    df: pd.DataFrame,
    validation_metric_col: str,
    dimensions: List[str],
    debug_mode: bool,
    include_privacy_validation: bool,
    consistent_weights: bool,
    logger: logging.Logger,
    weighting_result: Optional[WeightingResult] = None,
    include_audit_log: bool = True,
) -> Dict[str, Any]:
    """Collect debug-oriented run artifacts shared by share and rate flows."""
    weights_df = None
    privacy_validation_df = None
    compliance_privacy_validation = None
    output_privacy_validation_df = None
    method_breakdown_df = None
    metadata_updates: Dict[str, Any] = {}

    def _from_result(field: str, default: Any = None) -> Any:
        if weighting_result is not None and hasattr(weighting_result, field):
            value = getattr(weighting_result, field)
            return default if value is None else value
        return getattr(analyzer, field, default)

    structural_summary_df = _from_result('structural_summary_df')
    structural_detail_df = _from_result('structural_detail_df')
    rank_changes_df = _from_result('rank_changes_df')
    subset_search_results = _from_result('subset_search_results', [])

    if debug_mode:
        weights_df = analyzer.get_weights_dataframe()
        if not weights_df.empty:
            logger.info(f"Captured weights data: {len(weights_df)} weight entries")

    should_render_privacy_validation_df = include_privacy_validation or debug_mode or include_audit_log
    if hasattr(analyzer, "build_privacy_validation_result"):
        privacy_validation_result = analyzer.build_privacy_validation_result(df, validation_metric_col, dimensions)
        compliance_privacy_validation = privacy_validation_result
        metadata_updates["privacy_validation_result"] = privacy_validation_result
        if should_render_privacy_validation_df:
            privacy_validation_df = privacy_validation_result.to_dataframe()
    else:
        privacy_validation_df = analyzer.build_privacy_validation_dataframe(df, validation_metric_col, dimensions)
        compliance_privacy_validation = privacy_validation_df
    if include_privacy_validation or debug_mode:
        output_privacy_validation_df = privacy_validation_df
    privacy_validation_count = (
        len(getattr(compliance_privacy_validation, "rows", []))
        if privacy_validation_df is None
        else len(privacy_validation_df)
    )
    if privacy_validation_count:
        logger.info(f"Built privacy validation data: {privacy_validation_count} validation entries")
    if privacy_validation_df is not None and not privacy_validation_df.empty:
        if 'Structural_Infeasible_Category' in privacy_validation_df.columns:
            structural_rows = int((privacy_validation_df['Structural_Infeasible_Category'] == 'Yes').sum())
            structural_categories = int(
                privacy_validation_df.loc[
                    privacy_validation_df['Structural_Infeasible_Category'] == 'Yes',
                    ['Dimension', 'Category', 'Time_Period']
                ].drop_duplicates().shape[0]
            )
            metadata_updates['structural_infeasible_validation_rows'] = structural_rows
            metadata_updates['structural_infeasible_validation_categories'] = structural_categories

    rows = []
    dims_all = list(dimensions)
    used_dims = set(_from_result('global_dimensions_used', []))
    removed_dims = set(_from_result('removed_dimensions', []))
    per_dim_dict: Dict[str, Dict[str, float]] = _from_result('per_dimension_weights', {})
    weight_methods: Dict[str, str] = _from_result('weight_methods', {})
    global_w = _from_result('global_weights', {})
    peers = set(global_w.keys())
    for dim_name, weight_map in per_dim_dict.items():
        peers.update(weight_map.keys())
    if (
        not peers
        and privacy_validation_df is not None
        and not privacy_validation_df.empty
        and 'Peer' in privacy_validation_df.columns
    ):
        peers.update(str(peer) for peer in privacy_validation_df['Peer'].dropna().unique())
    if not peers and compliance_privacy_validation is not None and hasattr(compliance_privacy_validation, "rows"):
        peers.update(str(row.peer) for row in compliance_privacy_validation.rows if row.peer)
    for dim_name in dims_all:
        if dim_name in weight_methods:
            method = weight_methods[dim_name]
        elif dim_name in per_dim_dict:
            method = 'Per-Dimension-LP'
        elif dim_name in used_dims:
            method = 'Global-LP'
        elif dim_name in removed_dims:
            method = 'Global weights (dropped in LP)'
        else:
            method = 'Global weights'

        for peer in sorted(peers):
            if dim_name in per_dim_dict and peer in per_dim_dict[dim_name]:
                multiplier = float(per_dim_dict[dim_name][peer])
            else:
                multiplier = float(global_w.get(peer, {}).get('multiplier', 1.0))
            global_weight_pct = global_w.get(peer, {}).get('weight', None)
            rows.append({
                'Dimension': dim_name,
                'Method': method,
                'Peer': peer,
                'Multiplier': round(multiplier, 6),
                'Global_Weight_%': round(global_weight_pct, 4) if isinstance(global_weight_pct, (int, float)) else None,
            })
    if rows:
        method_breakdown_df = pd.DataFrame(rows)
        logger.info(f"Built method breakdown data: {len(method_breakdown_df)} entries")

    if structural_summary_df is not None and hasattr(structural_summary_df, "empty") and not structural_summary_df.empty:
        metadata_updates['structural_summary_df'] = structural_summary_df
    if structural_detail_df is not None and hasattr(structural_detail_df, "empty") and not structural_detail_df.empty:
        metadata_updates['structural_detail_df'] = structural_detail_df
    if rank_changes_df is not None and hasattr(rank_changes_df, "empty") and not rank_changes_df.empty:
        metadata_updates['rank_changes_df'] = rank_changes_df
    if subset_search_results:
        subset_search_df = pd.DataFrame(subset_search_results)
        if not subset_search_df.empty:
            metadata_updates['subset_search_df'] = subset_search_df

    return {
        'weights_df': weights_df,
        'privacy_validation_df': output_privacy_validation_df,
        'compliance_privacy_validation_df': compliance_privacy_validation,
        'method_breakdown_df': method_breakdown_df,
        'metadata_updates': metadata_updates,
    }


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
    Path(audit_log_file).parent.mkdir(parents=True, exist_ok=True)
    audit_model = build_audit_log_model(
        metadata=metadata,
        report_paths=report_paths,
        dimensions_analyzed=dimensions_analyzed,
        csv_output=csv_output,
        impact_df=impact_df,
        privacy_validation_df=privacy_validation_df,
        validation_summary=summarize_validation_issues(validation_issues),
    )
    ReportGenerator(config).create_audit_log(
        audit_log_file,
        audit_model["metadata"],
        audit_model["results_summary"],
    )
    return audit_log_file


class RunAborted(Exception):
    """Raised when analysis input or configuration prevents execution."""


class RunBlocked(RunAborted):
    """Raised when a posture precondition blocks execution before analysis."""

    def __init__(self, message: str, compliance_summary: Dict[str, Any]):
        super().__init__(message)
        self.compliance_summary = compliance_summary


def enforce_compliance_preconditions(config: ConfigManager, request: AnalysisRunRequest) -> Dict[str, Any]:
    posture = config.get('compliance_posture')
    acknowledgement_given = bool(request.acknowledge_accuracy_first)
    if posture == 'accuracy_first' and not acknowledgement_given:
        summary = build_blocked_compliance_summary(posture, acknowledgement_given).to_dict()
        raise RunBlocked(
            "accuracy_first compliance_posture requires explicit acknowledgement before execution",
            summary,
        )
    resolved = config.resolve() if hasattr(config, "resolve") else None
    policy_input = Control3PolicyInput.from_evidence(
        resolved.control3,
        analysis_mode=request.mode,
        rate_types=request.rate_types,
    )
    control3_policy = evaluate_control3_policy(policy_input)
    if not control3_policy.allowed:
        summary = build_blocked_compliance_summary(
            posture,
            acknowledgement_given,
            reason=control3_policy.blocked_reason or "control3_policy_blocked",
            extra_details={
                "control3_policy": {
                    "requirements": control3_policy.requirements,
                    "details": control3_policy.details,
                }
            },
        ).to_dict()
        raise RunBlocked(control3_policy.blocked_reason or "Control 3 policy blocked this run", summary)
    return {
        'compliance_posture': posture,
        'acknowledgement_given': acknowledgement_given,
        'control3_policy': {
            'allowed': control3_policy.allowed,
            'blocked_reason': control3_policy.blocked_reason,
            'requirements': control3_policy.requirements,
            'details': control3_policy.details,
        },
    }


def build_run_request(mode: str, args: argparse.Namespace) -> AnalysisRunRequest:
    return AnalysisRunRequest.from_namespace(mode, args)


def execute_run(request: AnalysisRunRequest, logger: logging.Logger) -> AnalysisArtifacts:
    if request.is_share:
        return execute_share_run(request, logger)
    if request.is_rate:
        return execute_rate_run(request, logger)
    raise RunAborted(f"Unsupported analysis mode: {request.mode}")


@dataclass
class AnalysisModeSpec:
    """Per-mode hooks for the shared analysis run pipeline."""

    start_event: str
    extra_config_overrides: Dict[str, Any]
    resolve_preferred_entity_col: Callable[[AnalysisRunRequest, ConfigManager], str]
    validate_request: Callable[[AnalysisRunRequest, pd.DataFrame], None]
    build_validation_kwargs: Callable[
        [AnalysisRunRequest, str, Optional[str], List[str]],
        Dict[str, Any],
    ]
    weight_metric_col: Callable[[AnalysisRunRequest], str]
    initial_bic_percentile: Callable[[AnalysisRunRequest, ConfigManager], float]
    run_analysis: Callable[
        [AnalysisRunRequest, DimensionalAnalyzer, pd.DataFrame, List[str], ConfigManager],
        Dict[str, Any],
    ]
    secondary_metrics_kwargs: Callable[[AnalysisRunRequest, List[str]], Dict[str, Any]]
    build_mode_metadata: Callable[..., Dict[str, Any]]
    preset_comparison_extra: Callable[[AnalysisRunRequest], Dict[str, Any]]
    compute_impact: Callable[..., Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Dict[str, Any]]]
    resolve_output_filename: Callable[[AnalysisRunRequest, Optional[str], Dict[str, Any]], str]
    export_balanced_csv_fn: Callable[..., None]


def _handle_optimization_failure(
    exc: ValueError,
    *,
    analyzer: DimensionalAnalyzer,
    compliance_context: Dict[str, Any],
    logger: logging.Logger,
) -> None:
    block_reason = getattr(analyzer, 'compliance_blocked_reason', None) or 'optimization_aborted'
    block_extra: Dict[str, Any] = {'error': str(exc)}
    if hasattr(analyzer, 'compliance_blocked_peer_count'):
        block_extra['peer_count'] = int(analyzer.compliance_blocked_peer_count)
    logger.error("Optimization aborted: %s", exc)
    blocked_summary = build_compliance_summary(
        posture=compliance_context.get('compliance_posture'),
        acknowledgement_given=compliance_context.get('acknowledgement_given', False),
        blocked_reason=block_reason,
        blocked_details=block_extra,
    ).to_dict()
    raise RunBlocked(str(exc), blocked_summary) from exc


def _validate_balanced_export(
    *,
    analysis_output_file: str,
    csv_output: str,
    is_rate: bool,
    compliance_posture: str,
    logger: logging.Logger,
) -> Dict[str, Any]:
    """Validate balanced CSV export against the analysis workbook."""
    try:
        workbook_path = Path(analysis_output_file)
        csv_path = Path(csv_output)
        if not workbook_path.exists() or not csv_path.exists():
            logger.warning("Export validation skipped: missing workbook or CSV")
            return {'checked': False}

        if is_rate:
            validator_script = Path(__file__).resolve().parents[1] / 'utils' / 'csv_validator.py'
            cmd = [sys.executable, str(validator_script), str(workbook_path), str(csv_path)]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            result: Dict[str, Any] = {'checked': True, 'passed': proc.returncode == 0, 'mode': 'full'}
            if proc.returncode == 0:
                logger.info(
                    "Export validation passed (mode=%s): balanced CSV is consistent with the workbook",
                    'full',
                )
            else:
                stdout_tail = (proc.stdout or '')[-2000:]
                stderr_tail = (proc.stderr or '')[-2000:]
                logger.error(
                    "Export validation FAILED (mode=full):\nstdout: %s\nstderr: %s",
                    stdout_tail,
                    stderr_tail,
                )
                if compliance_posture == 'strict':
                    raise RuntimeError("Balanced CSV failed cross-validation against the workbook")
            return result

        df_csv = pd.read_csv(csv_path)
        required = {'Dimension', 'Category'}
        missing = required - set(df_csv.columns)
        balanced_cols = [column for column in df_csv.columns if column.startswith('Balanced_')]
        passed = not missing and bool(balanced_cols)
        result = {'checked': True, 'passed': passed, 'mode': 'schema'}
        if passed:
            logger.info(
                "Export validation passed (mode=%s): balanced CSV is consistent with the workbook",
                'schema',
            )
        else:
            details: List[str] = []
            if missing:
                details.append(f"missing columns: {sorted(missing)}")
            if not balanced_cols:
                details.append('missing Balanced_* columns')
            logger.error("Export validation FAILED (mode=schema): %s", '; '.join(details))
            if compliance_posture == 'strict':
                raise RuntimeError("Balanced CSV failed cross-validation against the workbook")
        return result
    except RuntimeError:
        raise
    except Exception as exc:
        logger.warning("Export validation could not run: %s", exc)
        return {'checked': False}


def _compute_share_impact(
    *,
    request: AnalysisRunRequest,
    analyzer: DimensionalAnalyzer,
    df: pd.DataFrame,
    dimensions: List[str],
    resolved_entity: Optional[str],
    include_impact_summary: bool,
    logger: logging.Logger,
    weighting_result: WeightingResult,
) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Dict[str, Any]]:
    """Share impact compares target entity share vs balanced peers.

    Peer-only mode has no target entity, so share impact is undefined. Rate
    impact compares raw vs balanced peer-group rates and remains defined without
    a target entity.
    """
    metadata_updates: Dict[str, Any] = {}
    if not include_impact_summary:
        return None, None, metadata_updates
    if not resolved_entity:
        logger.info("Impact skipped: peer-only share has no target entity to compare")
        return None, None, metadata_updates

    impact_df = analyzer.calculate_share_impact(
        df,
        request.metric,
        dimensions,
        resolved_entity,
        WeightLookup.from_weighting_result(weighting_result),
    )
    impact_summary_df = None
    if impact_df is not None and not impact_df.empty:
        impact_summary = {
            'mean_impact_pp': round(impact_df['Impact_PP'].mean(), 4),
            'mean_abs_impact_pp': round(impact_df['Impact_PP'].abs().mean(), 4),
            'std_impact_pp': round(impact_df['Impact_PP'].std(), 4) if len(impact_df) > 1 else 0.0,
            'min_impact_pp': round(impact_df['Impact_PP'].min(), 4),
            'max_impact_pp': round(impact_df['Impact_PP'].max(), 4),
            'categories_analyzed': len(impact_df),
        }
        metadata_updates['impact_summary'] = impact_summary
        if 'Dimension' in impact_df.columns:
            impact_summary_df = pd.DataFrame([
                {
                    'Dimension': dim,
                    'Mean_Abs_Impact_PP': round(dim_data['Impact_PP'].abs().mean(), 4),
                    'Max_Abs_Impact_PP': round(dim_data['Impact_PP'].abs().max(), 4),
                    'Categories': len(dim_data),
                }
                for dim in impact_df['Dimension'].unique()
                for dim_data in [impact_df[impact_df['Dimension'] == dim]]
            ])
        metadata_updates['impact_details'] = impact_df.to_dict('records')
    return impact_df, impact_summary_df, metadata_updates


def _compute_rate_impact(
    *,
    analyzer: DimensionalAnalyzer,
    df: pd.DataFrame,
    dimensions: List[str],
    total_col: str,
    numerator_cols: Dict[str, str],
    include_impact_summary: bool,
    weighting_result: WeightingResult,
) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Dict[str, Any]]:
    metadata_updates: Dict[str, Any] = {}
    if not include_impact_summary:
        return None, None, metadata_updates

    impact_df = analyzer.calculate_rate_impact(
        df,
        total_col,
        numerator_cols,
        dimensions,
        WeightLookup.from_weighting_result(weighting_result),
    )
    impact_summary_df = None
    if impact_df is not None and not impact_df.empty:
        impact_summary: Dict[str, Any] = {}
        rate_cols = [col for col in impact_df.columns if col.endswith('_Impact_PP')]
        for col in rate_cols:
            rate_name = col.replace('_Impact_PP', '')
            impact_summary[f'{rate_name}_mean_abs_impact_pp'] = round(impact_df[col].abs().mean(), 4)
            impact_summary[f'{rate_name}_max_abs_impact_pp'] = round(impact_df[col].abs().max(), 4)
        if rate_cols:
            impact_summary['mean_abs_impact_pp'] = round(impact_df[rate_cols].abs().stack().mean(), 4)
        metadata_updates['impact_summary'] = impact_summary
        if 'Dimension' in impact_df.columns:
            impact_summary_df = pd.DataFrame([
                {
                    'Dimension': dim,
                    'Mean_Abs_Impact_PP': round(sum(dim_data[col].abs().mean() for col in rate_cols) / len(rate_cols), 4) if rate_cols else 0.0,
                    'Max_Abs_Impact_PP': round(max(dim_data[col].abs().max() for col in rate_cols), 4) if rate_cols else 0.0,
                    'Categories': len(dim_data),
                }
                for dim in impact_df['Dimension'].unique()
                for dim_data in [impact_df[impact_df['Dimension'] == dim]]
            ])
        metadata_updates['impact_details'] = impact_df.to_dict('records')
    return impact_df, impact_summary_df, metadata_updates


def _run_share_analysis(
    request: AnalysisRunRequest,
    analyzer: DimensionalAnalyzer,
    df: pd.DataFrame,
    dimensions: List[str],
    _config: ConfigManager,
) -> Dict[str, Any]:
    results: Dict[str, Any] = {}
    for dim in dimensions:
        results[dim] = analyzer.analyze_dimension_share(df=df, dimension_column=dim, metric_col=request.metric)
    if not results:
        raise RunAborted('No analysis results generated')
    return results


def _run_rate_analysis(
    request: AnalysisRunRequest,
    analyzer: DimensionalAnalyzer,
    df: pd.DataFrame,
    dimensions: List[str],
    config: ConfigManager,
) -> Dict[str, Any]:
    default_bic = config.get('analysis', 'best_in_class_percentile', default=0.85)
    fraud_bic = config.get('analysis', 'fraud_percentile', default=0.15)
    bic_percentiles: Dict[str, float] = {}
    if request.approved_col:
        bic_percentiles['approval'] = default_bic
    if request.fraud_col:
        bic_percentiles['fraud'] = fraud_bic

    all_results: Dict[str, Any] = {}
    for rate_type in request.rate_types:
        analyzer.bic_percentile = bic_percentiles[rate_type]
        numerator_col = request.numerator_cols[rate_type]
        results: Dict[str, Any] = {}
        for dim in dimensions:
            results[dim] = analyzer.analyze_dimension_rate(
                df=df,
                dimension_column=dim,
                total_col=request.total_col,
                numerator_col=numerator_col,
            )
        if results:
            all_results[rate_type] = results
    if not all_results:
        raise RunAborted('No analysis results generated for any rate type')
    return all_results


def _build_share_mode_metadata(
    *,
    request: AnalysisRunRequest,
    config: ConfigManager,
    analyzer: DimensionalAnalyzer,
    resolved: ResolvedConfig,
    consistent_weights: bool,
    observability: RunObservability,
    weighting_result: Optional[WeightingResult] = None,
    **_: Any,
) -> Dict[str, Any]:
    metadata = {
        'analysis_type': 'share',
        'metric': request.metric,
        'bic_percentile': config.get('analysis', 'best_in_class_percentile'),
        'auto_subset_search': resolved.subset_search.enabled,
        'trigger_subset_on_slack': resolved.subset_search.trigger_on_slack,
        'max_cap_slack': resolved.subset_search.max_slack_threshold,
        'last_lp_stats': (
            weighting_result.last_lp_stats
            if weighting_result is not None
            else getattr(analyzer, 'last_lp_stats', {})
        ),
        'slack_subset_triggered': (
            weighting_result.slack_subset_triggered
            if weighting_result is not None
            else getattr(analyzer, 'slack_subset_triggered', False)
        ),
        'observability': observability.as_metadata(),
    }
    if consistent_weights:
        if weighting_result is not None:
            metadata['global_dimensions_used'] = list(weighting_result.global_dimensions_used)
            metadata['removed_dimensions'] = list(weighting_result.removed_dimensions)
            metadata['per_dimension_weighted'] = list(weighting_result.per_dimension_weights.keys())
            metadata['subset_search_results'] = list(weighting_result.subset_search_results)
        else:
            metadata['global_dimensions_used'] = getattr(analyzer, 'global_dimensions_used', [])
            metadata['removed_dimensions'] = getattr(analyzer, 'removed_dimensions', [])
            metadata['per_dimension_weighted'] = list(getattr(analyzer, 'per_dimension_weights', {}).keys())
            metadata['subset_search_results'] = getattr(analyzer, 'subset_search_results', [])
    return metadata


def _build_rate_mode_metadata(
    *,
    request: AnalysisRunRequest,
    config: ConfigManager,
    results: Dict[str, Any],
    output_settings: OutputSettings,
    observability: RunObservability,
    **_: Any,
) -> Dict[str, Any]:
    default_bic = config.get('analysis', 'best_in_class_percentile', default=0.85)
    fraud_bic = config.get('analysis', 'fraud_percentile', default=0.15)
    bic_percentiles: Dict[str, float] = {}
    if request.approved_col:
        bic_percentiles['approval'] = default_bic
    if request.fraud_col:
        bic_percentiles['fraud'] = fraud_bic
    return {
        'analysis_type': 'multi_rate' if len(results) > 1 else f"{request.rate_types[0]}_rate",
        'rate_types': request.rate_types,
        'approved_col': request.approved_col,
        'fraud_col': request.fraud_col,
        'total_col': request.total_col,
        'bic_percentiles': bic_percentiles,
        'fraud_in_bps': output_settings.fraud_in_bps,
        'observability': observability.as_metadata(),
    }


def _share_output_filename(request: AnalysisRunRequest, resolved_entity: Optional[str], _results: Dict[str, Any]) -> str:
    entity_name = resolved_entity.replace(' ', '_') if resolved_entity else 'PEER_ONLY'
    return request.output or f"benchmark_share_{entity_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"


def _rate_output_filename(request: AnalysisRunRequest, resolved_entity: Optional[str], results: Dict[str, Any]) -> str:
    entity_name = resolved_entity.replace(' ', '_') if resolved_entity else 'PEER_ONLY'
    if request.output:
        return request.output
    if len(results) > 1:
        return f"benchmark_multi_rate_{entity_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return f"benchmark_{request.rate_types[0]}_rate_{entity_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"


def _export_share_balanced_csv(
    *,
    request: AnalysisRunRequest,
    results: Dict[str, Any],
    analysis_output_file: str,
    df: pd.DataFrame,
    analyzer: DimensionalAnalyzer,
    dimensions: List[str],
    output_settings: OutputSettings,
    logger: logging.Logger,
    weighting_result: WeightingResult,
) -> None:
    export_balanced_csv(
        results,
        analysis_output_file,
        logger,
        analysis_type='share',
        df=df,
        analyzer=analyzer,
        dimensions=dimensions,
        metric_col=request.metric,
        secondary_metrics=request.secondary_metrics,
        include_calculated=output_settings.include_calculated_metrics,
        weight_lookup=WeightLookup.from_weighting_result(weighting_result),
    )


def _export_rate_balanced_csv(
    *,
    request: AnalysisRunRequest,
    results: Dict[str, Any],
    analysis_output_file: str,
    df: pd.DataFrame,
    analyzer: DimensionalAnalyzer,
    dimensions: List[str],
    output_settings: OutputSettings,
    logger: logging.Logger,
    weighting_result: WeightingResult,
) -> None:
    analyzer.secondary_metrics = request.secondary_metrics
    export_balanced_csv(
        None,
        analysis_output_file,
        logger,
        analysis_type='rate',
        all_results=results,
        df=df,
        analyzer=analyzer,
        dimensions=dimensions,
        total_col=request.total_col,
        numerator_cols=request.numerator_cols,
        include_calculated=output_settings.include_calculated_metrics,
        weight_lookup=WeightLookup.from_weighting_result(weighting_result),
    )


def _validate_share_request(request: AnalysisRunRequest, df: pd.DataFrame) -> None:
    if not request.metric or request.metric not in df.columns:
        raise RunAborted(f"Metric column '{request.metric}' not found in data")


SHARE_MODE_SPEC = AnalysisModeSpec(
    start_event='share-run-started',
    extra_config_overrides={},
    resolve_preferred_entity_col=lambda _request, config: config.get('input', 'entity_col'),
    validate_request=_validate_share_request,
    build_validation_kwargs=lambda request, entity_col, time_col, dimensions: {
        'analysis_type': 'share',
        'metric_col': request.metric,
        'entity_col': entity_col,
        'time_col': time_col,
        'target_entity': request.entity,
        'dimensions': dimensions,
    },
    weight_metric_col=lambda request: request.metric,
    initial_bic_percentile=lambda _request, config: config.get('analysis', 'best_in_class_percentile', default=0.85),
    run_analysis=_run_share_analysis,
    secondary_metrics_kwargs=lambda request, dimensions: {
        'metric_col': request.metric,
        'dimensions': dimensions,
    },
    build_mode_metadata=_build_share_mode_metadata,
    preset_comparison_extra=lambda _request: {'analysis_type': 'share'},
    compute_impact=lambda **kwargs: _compute_share_impact(
        request=kwargs['request'],
        analyzer=kwargs['analyzer'],
        df=kwargs['df'],
        dimensions=kwargs['dimensions'],
        resolved_entity=kwargs['resolved_entity'],
        include_impact_summary=kwargs['output_settings'].include_impact_summary,
        logger=kwargs['logger'],
        weighting_result=kwargs['weighting_result'],
    ),
    resolve_output_filename=_share_output_filename,
    export_balanced_csv_fn=_export_share_balanced_csv,
)


def _validate_rate_request(request: AnalysisRunRequest, df: pd.DataFrame) -> None:
    if not request.approved_col and not request.fraud_col:
        raise RunAborted('At least one of --approved-col or --fraud-col must be specified')
    if not request.total_col or request.total_col not in df.columns:
        raise RunAborted(f"Total column '{request.total_col}' not found in data")
    for column in [request.approved_col, request.fraud_col]:
        if column and column not in df.columns:
            raise RunAborted(f"Rate column '{column}' not found in data")


RATE_MODE_SPEC = AnalysisModeSpec(
    start_event='rate-run-started',
    extra_config_overrides={},  # filled per-request in _execute_run
    resolve_preferred_entity_col=lambda request, _config: request.entity_col,
    validate_request=_validate_rate_request,
    build_validation_kwargs=lambda request, entity_col, time_col, dimensions: {
        'analysis_type': 'rate',
        'total_col': request.total_col,
        'numerator_cols': request.numerator_cols,
        'entity_col': entity_col,
        'time_col': time_col,
        'target_entity': request.entity,
        'dimensions': dimensions,
    },
    weight_metric_col=lambda request: request.total_col,
    initial_bic_percentile=lambda request, config: (
        config.get('analysis', 'best_in_class_percentile', default=0.85)
        if request.approved_col
        else config.get('analysis', 'fraud_percentile', default=0.15)
    ),
    run_analysis=_run_rate_analysis,
    secondary_metrics_kwargs=lambda request, dimensions: {
        'total_col': request.total_col,
        'dimensions': dimensions,
    },
    build_mode_metadata=_build_rate_mode_metadata,
    preset_comparison_extra=lambda request: {
        'analysis_type': 'rate',
        'total_col': request.total_col,
        'numerator_cols': request.numerator_cols,
    },
    compute_impact=lambda **kwargs: _compute_rate_impact(
        analyzer=kwargs['analyzer'],
        df=kwargs['df'],
        dimensions=kwargs['dimensions'],
        total_col=kwargs['request'].total_col,
        numerator_cols=kwargs['request'].numerator_cols,
        include_impact_summary=kwargs['output_settings'].include_impact_summary,
        weighting_result=kwargs['weighting_result'],
    ),
    resolve_output_filename=_rate_output_filename,
    export_balanced_csv_fn=_export_rate_balanced_csv,
)


def _execute_run(
    request: AnalysisRunRequest,
    mode_spec: AnalysisModeSpec,
    logger: logging.Logger,
    *,
    extra_config_overrides: Optional[Dict[str, Any]] = None,
) -> AnalysisArtifacts:
    args = request.to_namespace()
    config_overrides = dict(mode_spec.extra_config_overrides)
    if extra_config_overrides:
        config_overrides.update(extra_config_overrides)
    config = build_run_config(args, extra_overrides=config_overrides or None)
    compliance_context = enforce_compliance_preconditions(config, request)
    output_settings = resolve_output_settings(config)
    observability = RunObservability()
    observability.record(mode_spec.start_event, entity=request.entity, csv=request.csv)

    preferred_entity_col = mode_spec.resolve_preferred_entity_col(request, config)
    try:
        prepared_loader, prepared_df, prepared_entity_col, prepared_time_col, used_prepared = apply_prepared_dataset(
            request,
            config,
            logger,
            preferred_entity_col=preferred_entity_col,
        )
        if used_prepared:
            data_loader = prepared_loader
            df = prepared_df
            entity_col = prepared_entity_col
            time_col = prepared_time_col
        else:
            data_loader, df, entity_col, time_col = prepare_run_data(
                args,
                config,
                logger,
                preferred_entity_col=preferred_entity_col,
            )
    except ValueError as exc:
        raise RunAborted(str(exc)) from exc

    mode_spec.validate_request(request, df)

    if should_reuse_prepared_validation(request, used_prepared=used_prepared):
        logger.info("Reusing prepared input validation results")
        data_quality = build_data_quality_from_validation_issues(
            request.prepared_dataset.validation_issues if request.prepared_dataset else None
        )
    else:
        data_quality = validate_analysis_input(
            df=df,
            config=config,
            data_loader=data_loader,
            **mode_spec.build_validation_kwargs(request, entity_col, time_col, request.dimensions),
        )
    validation_issues, should_abort = data_quality
    if should_abort:
        raise RunAborted('Analysis aborted due to validation errors')

    resolved_entity = resolve_target_entity(df, entity_col, request.entity, logger)
    if request.entity and resolved_entity is None:
        raise RunAborted('Target entity could not be resolved')

    dimensions = resolve_dimensions(args, config, data_loader, df, logger)
    if dimensions is None:
        raise RunAborted('No dimensions available for analysis')

    resolved = config.resolve()
    debug_mode = config.get('output', 'include_debug_sheets', default=False)
    analyzer, analyzer_settings = build_dimensional_analyzer(
        target_entity=resolved_entity,
        entity_col=entity_col,
        resolved=resolved,
        time_col=time_col,
        debug_mode=debug_mode,
        bic_percentile=mode_spec.initial_bic_percentile(request, config),
        logger=logger,
    )
    consistent_weights = analyzer_settings['consistent_weights']
    weight_metric_col = mode_spec.weight_metric_col(request)

    try:
        weighting_result = analyzer.fit_privacy_weights(df, weight_metric_col, dimensions)
    except ValueError as exc:
        _handle_optimization_failure(
            exc,
            analyzer=analyzer,
            compliance_context=compliance_context,
            logger=logger,
        )

    results = mode_spec.run_analysis(request, analyzer, df, dimensions, config)

    secondary_results_df = None
    if request.secondary_metrics:
        secondary_results_df = get_balanced_metrics_df(
            df=df,
            analyzer=analyzer,
            secondary_metrics=request.secondary_metrics,
            weight_lookup=WeightLookup.from_weighting_result(weighting_result),
            **mode_spec.secondary_metrics_kwargs(request, dimensions),
        )

    dimensions_analyzed = len(results) if request.is_share else len(dimensions)
    dimension_names = list(results.keys()) if request.is_share else dimensions

    metadata = {
        **build_common_run_metadata(
            args,
            resolved,
            analyzer,
            resolved_entity=resolved_entity,
            entity_col=entity_col,
            total_records=len(df),
            unique_entities=df[entity_col].nunique(),
            dimensions_analyzed=dimensions_analyzed,
            dimension_names=dimension_names,
            secondary_metrics=request.secondary_metrics,
            debug_mode=debug_mode,
            consistent_weights=consistent_weights,
            include_privacy_validation=output_settings.include_privacy_validation,
            include_impact_summary=output_settings.include_impact_summary,
            include_preset_comparison=output_settings.include_preset_comparison,
            include_calculated_metrics=output_settings.include_calculated_metrics,
            output_format=output_settings.output_format,
            consistency_mode=analyzer_settings['consistency_mode'],
            enforce_single_weight_set=analyzer_settings['enforce_single_weight_set'],
        ),
        **mode_spec.build_mode_metadata(
            request=request,
            config=config,
            analyzer=analyzer,
            resolved=resolved,
            results=results,
            consistent_weights=consistent_weights,
            output_settings=output_settings,
            observability=observability,
            weighting_result=weighting_result,
        ),
    }
    metadata.update(
        RunSummary(
            entity=str(metadata.get('entity', 'PEER-ONLY')),
            entity_column=entity_col,
            total_records=len(df),
            unique_entities=int(df[entity_col].nunique()),
            peer_count=int(metadata.get('peer_count', 0)),
            dimensions_analyzed=dimensions_analyzed,
            dimension_names=list(dimension_names),
            preset=getattr(args, 'preset', None),
            compliance_posture=config.get('compliance_posture'),
            debug_mode=debug_mode,
            consistent_weights=consistent_weights,
            output_format=output_settings.output_format,
            timestamp=metadata.get('timestamp'),
            privacy_rule=getattr(analyzer, 'privacy_rule_name', None),
        ).to_metadata_dict()
    )

    diagnostics = collect_run_diagnostics(
        analyzer=analyzer,
        df=df,
        validation_metric_col=weight_metric_col,
        dimensions=dimensions,
        debug_mode=debug_mode,
        include_privacy_validation=output_settings.include_privacy_validation,
        consistent_weights=consistent_weights,
        logger=logger,
        weighting_result=weighting_result,
        include_audit_log=output_settings.include_audit_log,
    )
    metadata.update(diagnostics['metadata_updates'])
    compliance_summary = build_compliance_summary(
        posture=compliance_context['compliance_posture'],
        acknowledgement_given=compliance_context['acknowledgement_given'],
        privacy_validation_df=diagnostics['compliance_privacy_validation_df'],
        structural_infeasibility=metadata.get('structural_infeasibility_summary', {}),
        data_quality=data_quality,
    ).to_dict()
    metadata['compliance_summary'] = compliance_summary
    metadata['control3_policy'] = compliance_context.get('control3_policy')
    metadata['run_status'] = compliance_summary['run_status']
    metadata['compliance_verdict'] = compliance_summary['compliance_verdict']
    metadata['acknowledgement_state'] = compliance_summary['acknowledgement_state']
    metadata['posture_consistent'] = compliance_summary['posture_consistent']
    plan = build_analysis_plan(
        request,
        resolved,
        entity=resolved_entity,
        entity_column=entity_col,
        dimensions=dimensions,
        output_settings=output_settings,
    )
    analysis_result = finalize_analysis_result(
        plan=plan,
        weighting_result=weighting_result,
        privacy_validation=metadata.get('privacy_validation_result', diagnostics['compliance_privacy_validation_df']),
        data_quality=data_quality,
        results=results,
        compliance_summary=compliance_summary,
    )
    metadata.update(analysis_result_to_metadata(analysis_result))

    preset_comparison_df = None
    if output_settings.include_preset_comparison:
        preset_comparison_df = execute_preset_comparison(
            df=df,
            metric_col=weight_metric_col,
            entity_col=entity_col,
            dimensions=dimensions,
            target_entity=resolved_entity,
            time_col=time_col,
            logger=logger,
            analyzer_factory=build_dimensional_analyzer,
            **mode_spec.preset_comparison_extra(request),
        )
        if preset_comparison_df is not None and not preset_comparison_df.empty:
            metadata['preset_comparison'] = preset_comparison_df.to_dict('records')

    impact_df, impact_summary_df, impact_metadata = mode_spec.compute_impact(
        request=request,
        analyzer=analyzer,
        df=df,
        dimensions=dimensions,
        resolved_entity=resolved_entity,
        output_settings=output_settings,
        logger=logger,
        weighting_result=weighting_result,
    )
    metadata.update(impact_metadata)

    analysis_output_file = mode_spec.resolve_output_filename(request, resolved_entity, results)
    artifacts = build_analysis_artifacts(
        analysis_result=analysis_result,
        metadata=metadata,
        diagnostics=diagnostics,
        secondary_results_df=secondary_results_df,
        preset_comparison_df=preset_comparison_df,
        impact_df=impact_df,
        impact_summary_df=impact_summary_df,
        validation_issues=validation_issues,
        analysis_output_file=analysis_output_file,
        analyzer=analyzer,
        compliance_summary=compliance_summary,
    )

    artifacts = write_outputs(request, artifacts, config=config, logger=logger)
    if request.export_balanced_csv:
        mode_spec.export_balanced_csv_fn(
            request=request,
            results=results,
            analysis_output_file=analysis_output_file,
            df=df,
            analyzer=analyzer,
            dimensions=dimensions,
            output_settings=output_settings,
            logger=logger,
            weighting_result=weighting_result,
        )
        artifacts.csv_output = analysis_output_file.rsplit('.', 1)[0] + '_balanced.csv'

        if config.get('output', 'validate_export', default=True):
            metadata['export_validation'] = _validate_balanced_export(
                analysis_output_file=analysis_output_file,
                csv_output=artifacts.csv_output,
                is_rate=request.is_rate,
                compliance_posture=compliance_context['compliance_posture'],
                logger=logger,
            )

    artifacts.report_paths = build_report_paths(
        output_settings.output_format,
        analysis_output_file,
        artifacts.publication_output,
    )
    if output_settings.include_audit_log:
        artifacts.audit_log_output = write_audit_log(
            config,
            analysis_output_file=analysis_output_file,
            metadata=metadata,
            report_paths=artifacts.report_paths,
            dimensions_analyzed=dimensions_analyzed,
            csv_output=artifacts.csv_output,
            impact_df=impact_df,
            privacy_validation_df=artifacts.privacy_validation_df,
            validation_issues=validation_issues,
        )
    if output_settings.include_audit_package:
        artifacts.audit_package_output = write_audit_package(
            analysis_output_file=analysis_output_file,
            report_paths=[
                *(artifacts.report_paths or []),
                *([artifacts.json_output] if artifacts.json_output else []),
            ],
            csv_output=artifacts.csv_output,
            audit_log_output=artifacts.audit_log_output,
            config_snapshot=config.config,
            metadata=metadata,
        )
    return artifacts


def execute_share_run(request: AnalysisRunRequest, logger: logging.Logger) -> AnalysisArtifacts:
    return _execute_run(request, SHARE_MODE_SPEC, logger)


def execute_rate_run(request: AnalysisRunRequest, logger: logging.Logger) -> AnalysisArtifacts:
    return _execute_run(
        request,
        RATE_MODE_SPEC,
        logger,
        extra_config_overrides={'fraud_in_bps': request.fraud_in_bps},
    )
