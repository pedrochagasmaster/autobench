"""Shared orchestration helpers for analysis run setup."""

from __future__ import annotations

import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from core.compliance import build_blocked_compliance_summary, build_compliance_summary
from core.contracts import AnalysisArtifacts, AnalysisRunRequest, PreparedDataset
from core.data_loader import DataLoader, ValidationIssue, ValidationSeverity
from core.dimensional_analyzer import DimensionalAnalyzer
from core.observability import RunObservability
from core.output_artifacts import write_outputs
from core.preset_comparison import run_preset_comparison as execute_preset_comparison
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
    'compliance_posture',
)


def resolve_consistency_mode(
    opt_config: Dict[str, Any],
    logger: logging.Logger,
) -> Tuple[bool, str]:
    """Translate config consistency mode into a bool for the analyzer."""
    consistency_mode = opt_config.get('constraints', {}).get('consistency_mode', 'global')
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
    analysis_config: Dict[str, Any],
    opt_config: Dict[str, Any],
    time_col: Optional[str],
    debug_mode: bool,
    bic_percentile: float,
    logger: logging.Logger,
    consistent_weights: Optional[bool] = None,
) -> Tuple[DimensionalAnalyzer, Dict[str, Any]]:
    """Build a DimensionalAnalyzer from merged config."""
    dyn_constraints = opt_config.get('constraints', {}).get('dynamic_constraints', {})
    if consistent_weights is None:
        consistent_weights, consistency_mode = resolve_consistency_mode(opt_config, logger)
    else:
        consistency_mode = opt_config.get('constraints', {}).get('consistency_mode', 'global')

    rank_penalty_weight = opt_config['linear_programming'].get('rank_penalty_weight', 1.0)
    volume_preservation = opt_config['constraints']['volume_preservation']
    rank_preservation_strength = volume_preservation * float(rank_penalty_weight)
    lambda_penalty = opt_config['linear_programming'].get('lambda_penalty')
    bayesian_max_iterations = opt_config.get('bayesian', {}).get('max_iterations', 500)
    bayesian_learning_rate = opt_config.get('bayesian', {}).get('learning_rate', 0.01)
    violation_penalty_weight = opt_config.get('bayesian', {}).get('violation_penalty_weight', 1000.0)
    enforce_single_weight_set = bool(
        opt_config.get('constraints', {}).get('enforce_single_weight_set', False)
    )

    analyzer = DimensionalAnalyzer(
        target_entity=target_entity,
        entity_column=entity_col,
        bic_percentile=bic_percentile,
        debug_mode=debug_mode,
        consistent_weights=consistent_weights,
        merchant_mode=analysis_config.get('merchant_mode', False),
        rank_constraint_mode=opt_config['linear_programming'].get('rank_constraints', {}).get('mode', 'all'),
        rank_constraint_k=opt_config['linear_programming'].get('rank_constraints', {}).get('neighbor_k', 1),
        max_iterations=opt_config['linear_programming']['max_iterations'],
        tolerance=opt_config['linear_programming']['tolerance'],
        max_weight=opt_config['bounds']['max_weight'],
        min_weight=opt_config['bounds']['min_weight'],
        volume_preservation_strength=rank_preservation_strength,
        prefer_slacks_first=opt_config['subset_search'].get('prefer_slacks_first', False),
        auto_subset_search=opt_config['subset_search'].get('enabled', True),
        subset_search_max_tests=opt_config['subset_search'].get('max_attempts', 200),
        greedy_subset_search=(opt_config['subset_search'].get('strategy', 'greedy') == 'greedy'),
        trigger_subset_on_slack=opt_config['subset_search'].get('trigger_on_slack', True),
        max_cap_slack=opt_config['subset_search'].get('max_slack_threshold', 0.0),
        time_column=time_col,
        volume_weighted_penalties=opt_config['linear_programming'].get('volume_weighted_penalties', False),
        volume_weighting_exponent=opt_config['linear_programming'].get('volume_weighting_exponent', 1.0),
        lambda_penalty=lambda_penalty,
        enforce_additional_constraints=opt_config.get('constraints', {}).get('enforce_additional_constraints', True),
        dynamic_constraints_enabled=dyn_constraints.get('enabled', True),
        min_peer_count_for_constraints=dyn_constraints.get('min_peer_count', 4),
        min_effective_peer_count=dyn_constraints.get('min_effective_peer_count', 3.0),
        min_category_volume_share=dyn_constraints.get('min_category_volume_share', 0.001),
        min_overall_volume_share=dyn_constraints.get('min_overall_volume_share', 0.0005),
        min_representativeness=dyn_constraints.get('min_representativeness', 0.1),
        dynamic_threshold_scale_floor=dyn_constraints.get('threshold_scale_floor', 0.6),
        dynamic_count_scale_floor=dyn_constraints.get('count_scale_floor', 0.5),
        representativeness_penalty_floor=dyn_constraints.get('penalty_floor', 0.25),
        representativeness_penalty_power=dyn_constraints.get('penalty_power', 1.0),
        bayesian_max_iterations=bayesian_max_iterations,
        bayesian_learning_rate=bayesian_learning_rate,
        violation_penalty_weight=violation_penalty_weight,
        enforce_single_weight_set=enforce_single_weight_set,
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


def build_common_run_metadata(
    args: argparse.Namespace,
    config: ConfigManager,
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
    opt_config = config.config.get('optimization', {})
    peer_count = unique_entities if resolved_entity is None else max(unique_entities - 1, 0)

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
        'compliance_posture': config.get('compliance_posture'),
        'acknowledgement_state': (
            'required_and_given'
            if config.get('compliance_posture') == 'accuracy_first' and getattr(args, 'acknowledge_accuracy_first', False)
            else ('required_missing' if config.get('compliance_posture') == 'accuracy_first' else 'not_required')
        ),
        'debug_mode': debug_mode,
        'consistent_weights': consistent_weights,
        'merchant_mode': config.get('analysis', 'merchant_mode', default=False),
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
        'max_iterations': opt_config.get('linear_programming', {}).get('max_iterations'),
        'tolerance_pp': opt_config.get('linear_programming', {}).get('tolerance'),
        'max_weight': opt_config.get('bounds', {}).get('max_weight'),
        'min_weight': opt_config.get('bounds', {}).get('min_weight'),
        'volume_preservation_strength': opt_config.get('constraints', {}).get('volume_preservation'),
        'rank_penalty_weight': opt_config.get('linear_programming', {}).get('rank_penalty_weight'),
        'rank_preservation_strength': getattr(analyzer, 'rank_preservation_strength', None),
        'prefer_slacks_first': opt_config.get('subset_search', {}).get('prefer_slacks_first'),
        'lambda_penalty': opt_config.get('linear_programming', {}).get('lambda_penalty'),
        'volume_weighted_penalties': opt_config.get('linear_programming', {}).get('volume_weighted_penalties'),
        'volume_weighting_exponent': opt_config.get('linear_programming', {}).get('volume_weighting_exponent'),
        'subset_search_enabled': opt_config.get('subset_search', {}).get('enabled'),
        'subset_search_strategy': opt_config.get('subset_search', {}).get('strategy'),
        'subset_search_max_tests': opt_config.get('subset_search', {}).get('max_attempts'),
        'subset_search_trigger_on_slack': opt_config.get('subset_search', {}).get('trigger_on_slack'),
        'subset_search_max_slack_threshold': opt_config.get('subset_search', {}).get('max_slack_threshold'),
        'bayesian_max_iterations': opt_config.get('bayesian', {}).get('max_iterations'),
        'bayesian_learning_rate': opt_config.get('bayesian', {}).get('learning_rate'),
        'violation_penalty_weight': opt_config.get('bayesian', {}).get('violation_penalty_weight'),
        'structural_infeasibility_summary': analyzer.get_structural_infeasibility_summary(),
        'privacy_rule': getattr(analyzer, 'privacy_rule_name', None),
        'additional_constraints_enforced': getattr(analyzer, 'enforce_additional_constraints', False),
        'additional_constraint_violations_count': len(getattr(analyzer, 'additional_constraint_violations', []) or []),
        'dynamic_constraints_enabled': getattr(analyzer, 'dynamic_constraints_enabled', False),
        'dynamic_constraints_stats': getattr(analyzer, 'dynamic_constraint_stats', {}),
        'dynamic_constraints_config': opt_config.get('constraints', {}).get('dynamic_constraints', {}),
        'impact_thresholds': {
            'high_pp': config.get(
                'output',
                'impact_thresholds',
                'high_pp',
                default=config.get('output', 'distortion_thresholds', 'high_distortion_pp', default=1.0)
            ),
            'low_pp': config.get(
                'output',
                'impact_thresholds',
                'low_pp',
                default=config.get('output', 'distortion_thresholds', 'low_distortion_pp', default=0.25)
            ),
        },
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
        # TUI validation often preloads a frame before execution; normalize again here
        # so preloaded and CSV-loaded paths share the same canonical column handling.
        df = data_loader._normalize_columns(df.copy())
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
    export_csv: bool,
    consistent_weights: bool,
    logger: logging.Logger,
) -> Dict[str, Any]:
    """Collect debug-oriented run artifacts shared by share and rate flows."""
    weights_df = None
    privacy_validation_df = None
    method_breakdown_df = None
    metadata_updates: Dict[str, Any] = {}

    if debug_mode:
        weights_df = analyzer.get_weights_dataframe()
        if not weights_df.empty:
            logger.info(f"Captured weights data: {len(weights_df)} weight entries")

    privacy_validation_df = analyzer.build_privacy_validation_dataframe(df, validation_metric_col, dimensions)
    if not privacy_validation_df.empty:
        logger.info(f"Built privacy validation data: {len(privacy_validation_df)} validation entries")
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
    used_dims = set(getattr(analyzer, 'global_dimensions_used', []))
    removed_dims = set(getattr(analyzer, 'removed_dimensions', []))
    per_dim_dict: Dict[str, Dict[str, float]] = getattr(analyzer, 'per_dimension_weights', {})
    weight_methods: Dict[str, str] = getattr(analyzer, 'weight_methods', {})
    global_w = getattr(analyzer, 'global_weights', {})
    peers = set(global_w.keys())
    for dim_name, weight_map in per_dim_dict.items():
        peers.update(weight_map.keys())
    if not peers and privacy_validation_df is not None and not privacy_validation_df.empty and 'Peer' in privacy_validation_df.columns:
        peers.update(str(peer) for peer in privacy_validation_df['Peer'].dropna().unique())
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

    return {
        'weights_df': weights_df,
        'privacy_validation_df': privacy_validation_df,
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
    audit_metadata = {}
    for key, value in metadata.items():
        if key == 'analyzer_ref':
            continue
        if hasattr(value, 'shape'):
            audit_metadata[key] = f"DataFrame rows={value.shape[0]} cols={value.shape[1]}"
        else:
            audit_metadata[key] = value
    ReportGenerator(config).create_audit_log(audit_log_file, audit_metadata, results_summary)
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
    return {
        'compliance_posture': posture,
        'acknowledgement_given': acknowledgement_given,
    }


def build_run_request(mode: str, args: argparse.Namespace) -> AnalysisRunRequest:
    return AnalysisRunRequest.from_namespace(mode, args)


def execute_run(request: AnalysisRunRequest, logger: logging.Logger) -> AnalysisArtifacts:
    if request.is_share:
        return execute_share_run(request, logger)
    if request.is_rate:
        return execute_rate_run(request, logger)
    raise RunAborted(f"Unsupported analysis mode: {request.mode}")


def execute_share_run(request: AnalysisRunRequest, logger: logging.Logger) -> AnalysisArtifacts:
    args = request.to_namespace()
    config = build_run_config(args)
    compliance_context = enforce_compliance_preconditions(config, request)
    output_settings = resolve_output_settings(config)
    observability = RunObservability()
    observability.record('share-run-started', entity=request.entity, csv=request.csv)

    try:
        data_loader, df, entity_col, time_col = prepare_run_data(
            args,
            config,
            logger,
            preferred_entity_col=config.get('input', 'entity_col'),
        )
    except ValueError as exc:
        raise RunAborted(str(exc)) from exc

    metric_col = request.metric
    if not metric_col or metric_col not in df.columns:
        raise RunAborted(f"Metric column '{metric_col}' not found in data")

    validation_issues, should_abort = validate_analysis_input(
        df=df,
        config=config,
        data_loader=data_loader,
        analysis_type='share',
        metric_col=metric_col,
        entity_col=entity_col,
        dimensions=request.dimensions,
        time_col=time_col,
        target_entity=request.entity,
    )
    if should_abort:
        raise RunAborted('Analysis aborted due to validation errors')

    resolved_entity = resolve_target_entity(df, entity_col, request.entity, logger)
    if request.entity and resolved_entity is None:
        raise RunAborted('Target entity could not be resolved')

    dimensions = resolve_dimensions(args, config, data_loader, df, logger)
    if dimensions is None:
        raise RunAborted('No dimensions available for analysis')

    opt_config = config.config['optimization']
    analysis_config = config.config['analysis']
    debug_mode = config.get('output', 'include_debug_sheets', default=False)
    analyzer, analyzer_settings = build_dimensional_analyzer(
        target_entity=resolved_entity,
        entity_col=entity_col,
        analysis_config=analysis_config,
        opt_config=opt_config,
        time_col=time_col,
        debug_mode=debug_mode,
        bic_percentile=analysis_config.get('best_in_class_percentile', 0.85),
        logger=logger,
    )
    consistent_weights = analyzer_settings['consistent_weights']

    if consistent_weights:
        analyzer.calculate_global_privacy_weights(df, metric_col, dimensions)
    else:
        _, _, peers = analyzer._build_categories(df, metric_col, dimensions)
        rule_name, max_concentration = analyzer._get_privacy_rule(len(peers))
        analyzer._solve_per_dimension_weights(
            df,
            metric_col,
            dimensions,
            peers,
            max_concentration,
            None,
            rule_name,
        )

    results: Dict[str, Any] = {}
    for dim in dimensions:
        result_df = analyzer.analyze_dimension_share(df=df, dimension_column=dim, metric_col=metric_col)
        results[dim] = result_df
    if not results:
        raise RunAborted('No analysis results generated')

    secondary_results_df = None
    if request.secondary_metrics:
        from benchmark import get_balanced_metrics_df

        secondary_results_df = get_balanced_metrics_df(
            df=df,
            analyzer=analyzer,
            dimensions=dimensions,
            metric_col=metric_col,
            secondary_metrics=request.secondary_metrics,
        )

    metadata = {
        **build_common_run_metadata(
            args,
            config,
            analyzer,
            resolved_entity=resolved_entity,
            entity_col=entity_col,
            total_records=len(df),
            unique_entities=df[entity_col].nunique(),
            dimensions_analyzed=len(results),
            dimension_names=list(results.keys()),
            secondary_metrics=request.secondary_metrics,
            debug_mode=debug_mode,
            consistent_weights=consistent_weights,
            include_privacy_validation=output_settings['include_privacy_validation'],
            include_impact_summary=output_settings['include_impact_summary'],
            include_preset_comparison=output_settings['include_preset_comparison'],
            include_calculated_metrics=output_settings['include_calculated_metrics'],
            output_format=output_settings['output_format'],
            consistency_mode=analyzer_settings['consistency_mode'],
            enforce_single_weight_set=analyzer_settings['enforce_single_weight_set'],
        ),
        'analysis_type': 'share',
        'metric': metric_col,
        'bic_percentile': config.get('analysis', 'best_in_class_percentile'),
        'auto_subset_search': opt_config.get('subset_search', {}).get('enabled'),
        'trigger_subset_on_slack': opt_config.get('subset_search', {}).get('trigger_on_slack'),
        'max_cap_slack': opt_config.get('subset_search', {}).get('max_slack_threshold'),
        'analyzer_ref': analyzer,
        'last_lp_stats': getattr(analyzer, 'last_lp_stats', {}),
        'slack_subset_triggered': getattr(analyzer, 'slack_subset_triggered', False),
        'observability': observability.as_metadata(),
    }
    if consistent_weights:
        metadata['global_dimensions_used'] = getattr(analyzer, 'global_dimensions_used', [])
        metadata['removed_dimensions'] = getattr(analyzer, 'removed_dimensions', [])
        metadata['per_dimension_weighted'] = list(getattr(analyzer, 'per_dimension_weights', {}).keys())
        metadata['subset_search_results'] = getattr(analyzer, 'subset_search_results', [])

    diagnostics = collect_run_diagnostics(
        analyzer=analyzer,
        df=df,
        validation_metric_col=metric_col,
        dimensions=dimensions,
        debug_mode=debug_mode,
        include_privacy_validation=output_settings['include_privacy_validation'],
        export_csv=request.export_balanced_csv,
        consistent_weights=consistent_weights,
        logger=logger,
    )
    metadata.update(diagnostics['metadata_updates'])
    compliance_summary = build_compliance_summary(
        posture=compliance_context['compliance_posture'],
        acknowledgement_given=compliance_context['acknowledgement_given'],
        privacy_validation_df=diagnostics['privacy_validation_df'],
        structural_infeasibility=metadata.get('structural_infeasibility_summary', {}),
    ).to_dict()
    metadata['compliance_summary'] = compliance_summary
    metadata['run_status'] = compliance_summary['run_status']
    metadata['compliance_verdict'] = compliance_summary['compliance_verdict']
    metadata['acknowledgement_state'] = compliance_summary['acknowledgement_state']
    metadata['posture_consistent'] = compliance_summary['posture_consistent']

    preset_comparison_df = None
    if output_settings['include_preset_comparison']:
        preset_comparison_df = execute_preset_comparison(
            df=df,
            metric_col=metric_col,
            entity_col=entity_col,
            dimensions=dimensions,
            target_entity=resolved_entity,
            time_col=time_col,
            analysis_type='share',
            logger=logger,
            analyzer_factory=build_dimensional_analyzer,
        )
        if preset_comparison_df is not None and not preset_comparison_df.empty:
            metadata['preset_comparison'] = preset_comparison_df.to_dict('records')

    impact_df = None
    impact_summary_df = None
    if output_settings['include_impact_summary'] and resolved_entity:
        impact_df = analyzer.calculate_share_impact(df, metric_col, dimensions, resolved_entity)
        if impact_df is not None and not impact_df.empty:
            impact_summary = {
                'mean_impact_pp': round(impact_df['Impact_PP'].mean(), 4),
                'mean_abs_impact_pp': round(impact_df['Impact_PP'].abs().mean(), 4),
                'std_impact_pp': round(impact_df['Impact_PP'].std(), 4) if len(impact_df) > 1 else 0.0,
                'min_impact_pp': round(impact_df['Impact_PP'].min(), 4),
                'max_impact_pp': round(impact_df['Impact_PP'].max(), 4),
                'categories_analyzed': len(impact_df),
            }
            metadata['impact_summary'] = impact_summary
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
            metadata['impact_details'] = impact_df.to_dict('records')

    entity_name = resolved_entity.replace(' ', '_') if resolved_entity else 'PEER_ONLY'
    analysis_output_file = request.output or f"benchmark_share_{entity_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    output_path = Path(analysis_output_file)
    artifacts = AnalysisArtifacts(
        results=results,
        metadata=metadata,
        weights_df=diagnostics['weights_df'],
        method_breakdown_df=diagnostics['method_breakdown_df'],
        privacy_validation_df=diagnostics['privacy_validation_df'],
        secondary_results_df=secondary_results_df,
        preset_comparison_df=preset_comparison_df,
        impact_df=impact_df,
        impact_summary_df=impact_summary_df,
        validation_issues=validation_issues,
        analysis_output_file=str(output_path),
        publication_output=str(output_path.with_name(f"{output_path.stem}_publication{output_path.suffix}")),
        analyzer=analyzer,
        compliance_summary=compliance_summary,
    )

    artifacts = write_outputs(request, artifacts, config=config, logger=logger)
    if request.export_balanced_csv:
        from benchmark import export_balanced_csv

        export_balanced_csv(
            results,
            analysis_output_file,
            logger,
            analysis_type='share',
            df=df,
            analyzer=analyzer,
            dimensions=dimensions,
            metric_col=metric_col,
            secondary_metrics=request.secondary_metrics,
            include_calculated=output_settings['include_calculated_metrics'],
        )
        artifacts.csv_output = analysis_output_file.rsplit('.', 1)[0] + '_balanced.csv'

    artifacts.report_paths = build_report_paths(
        output_settings['output_format'],
        str(output_path),
        artifacts.publication_output,
    )
    if output_settings['include_audit_log']:
        write_audit_log(
            config,
            analysis_output_file=str(output_path),
            metadata=metadata,
            report_paths=artifacts.report_paths,
            dimensions_analyzed=len(results),
            csv_output=artifacts.csv_output,
            impact_df=impact_df,
            privacy_validation_df=artifacts.privacy_validation_df,
            validation_issues=validation_issues,
        )
    return artifacts


def execute_rate_run(request: AnalysisRunRequest, logger: logging.Logger) -> AnalysisArtifacts:
    if not request.approved_col and not request.fraud_col:
        raise RunAborted('At least one of --approved-col or --fraud-col must be specified')

    args = request.to_namespace()
    config = build_run_config(args, extra_overrides={'fraud_in_bps': request.fraud_in_bps})
    compliance_context = enforce_compliance_preconditions(config, request)
    output_settings = resolve_output_settings(config)
    observability = RunObservability()
    observability.record('rate-run-started', entity=request.entity, csv=request.csv)

    try:
        data_loader, df, entity_col, time_col = prepare_run_data(
            args,
            config,
            logger,
            preferred_entity_col=request.entity_col,
        )
    except ValueError as exc:
        raise RunAborted(str(exc)) from exc

    total_col = request.total_col
    if not total_col or total_col not in df.columns:
        raise RunAborted(f"Total column '{total_col}' not found in data")
    for column in [request.approved_col, request.fraud_col]:
        if column and column not in df.columns:
            raise RunAborted(f"Rate column '{column}' not found in data")

    validation_issues, should_abort = validate_analysis_input(
        df=df,
        config=config,
        data_loader=data_loader,
        analysis_type='rate',
        total_col=total_col,
        numerator_cols=request.numerator_cols,
        entity_col=entity_col,
        dimensions=request.dimensions,
        time_col=time_col,
        target_entity=request.entity,
    )
    if should_abort:
        raise RunAborted('Analysis aborted due to validation errors')

    resolved_entity = resolve_target_entity(df, entity_col, request.entity, logger)
    if request.entity and resolved_entity is None:
        raise RunAborted('Target entity could not be resolved')

    dimensions = resolve_dimensions(args, config, data_loader, df, logger)
    if dimensions is None:
        raise RunAborted('No dimensions available for analysis')

    bic_percentiles: Dict[str, float] = {}
    default_bic = config.get('analysis', 'best_in_class_percentile', default=0.85)
    fraud_bic = config.get('analysis', 'fraud_percentile', default=0.15)
    if request.approved_col:
        bic_percentiles['approval'] = default_bic
    if request.fraud_col:
        bic_percentiles['fraud'] = fraud_bic

    opt_config = config.config['optimization']
    analysis_config = config.config['analysis']
    debug_mode = config.get('output', 'include_debug_sheets', default=False)
    first_rate_type = request.rate_types[0]
    analyzer, analyzer_settings = build_dimensional_analyzer(
        target_entity=resolved_entity,
        entity_col=entity_col,
        analysis_config=analysis_config,
        opt_config=opt_config,
        time_col=time_col,
        debug_mode=debug_mode,
        bic_percentile=bic_percentiles[first_rate_type],
        logger=logger,
    )
    consistent_weights = analyzer_settings['consistent_weights']
    if consistent_weights:
        analyzer.calculate_global_privacy_weights(df, total_col, dimensions)
    else:
        _, _, peers = analyzer._build_categories(df, total_col, dimensions)
        rule_name, max_concentration = analyzer._get_privacy_rule(len(peers))
        analyzer._solve_per_dimension_weights(
            df,
            total_col,
            dimensions,
            peers,
            max_concentration,
            None,
            rule_name,
        )

    all_results: Dict[str, Any] = {}
    for rate_type in request.rate_types:
        analyzer.bic_percentile = bic_percentiles[rate_type]
        numerator_col = request.numerator_cols[rate_type]
        results: Dict[str, Any] = {}
        for dim in dimensions:
            results[dim] = analyzer.analyze_dimension_rate(
                df=df,
                dimension_column=dim,
                total_col=total_col,
                numerator_col=numerator_col,
            )
        if results:
            all_results[rate_type] = results
    if not all_results:
        raise RunAborted('No analysis results generated for any rate type')

    secondary_results_df = None
    if request.secondary_metrics:
        from benchmark import get_balanced_metrics_df

        secondary_results_df = get_balanced_metrics_df(
            df=df,
            analyzer=analyzer,
            dimensions=dimensions,
            total_col=total_col,
            secondary_metrics=request.secondary_metrics,
        )

    metadata = {
        **build_common_run_metadata(
            args,
            config,
            analyzer,
            resolved_entity=resolved_entity,
            entity_col=entity_col,
            total_records=len(df),
            unique_entities=df[entity_col].nunique(),
            dimensions_analyzed=len(dimensions),
            dimension_names=dimensions,
            secondary_metrics=request.secondary_metrics,
            debug_mode=debug_mode,
            consistent_weights=consistent_weights,
            include_privacy_validation=output_settings['include_privacy_validation'],
            include_impact_summary=output_settings['include_impact_summary'],
            include_preset_comparison=output_settings['include_preset_comparison'],
            include_calculated_metrics=output_settings['include_calculated_metrics'],
            output_format=output_settings['output_format'],
            consistency_mode=analyzer_settings['consistency_mode'],
            enforce_single_weight_set=analyzer_settings['enforce_single_weight_set'],
        ),
        'analysis_type': 'multi_rate' if len(all_results) > 1 else f"{request.rate_types[0]}_rate",
        'rate_types': request.rate_types,
        'approved_col': request.approved_col,
        'fraud_col': request.fraud_col,
        'total_col': total_col,
        'bic_percentiles': bic_percentiles,
        'fraud_in_bps': output_settings['fraud_in_bps'],
        'observability': observability.as_metadata(),
    }

    diagnostics = collect_run_diagnostics(
        analyzer=analyzer,
        df=df,
        validation_metric_col=total_col,
        dimensions=dimensions,
        debug_mode=debug_mode,
        include_privacy_validation=output_settings['include_privacy_validation'],
        export_csv=request.export_balanced_csv,
        consistent_weights=consistent_weights,
        logger=logger,
    )
    metadata.update(diagnostics['metadata_updates'])
    compliance_summary = build_compliance_summary(
        posture=compliance_context['compliance_posture'],
        acknowledgement_given=compliance_context['acknowledgement_given'],
        privacy_validation_df=diagnostics['privacy_validation_df'],
        structural_infeasibility=metadata.get('structural_infeasibility_summary', {}),
    ).to_dict()
    metadata['compliance_summary'] = compliance_summary
    metadata['run_status'] = compliance_summary['run_status']
    metadata['compliance_verdict'] = compliance_summary['compliance_verdict']
    metadata['acknowledgement_state'] = compliance_summary['acknowledgement_state']
    metadata['posture_consistent'] = compliance_summary['posture_consistent']

    preset_comparison_df = None
    if output_settings['include_preset_comparison']:
        preset_comparison_df = execute_preset_comparison(
            df=df,
            metric_col=total_col,
            entity_col=entity_col,
            dimensions=dimensions,
            target_entity=resolved_entity,
            time_col=time_col,
            analysis_type='rate',
            logger=logger,
            analyzer_factory=build_dimensional_analyzer,
            total_col=total_col,
            numerator_cols=request.numerator_cols,
        )
        if preset_comparison_df is not None and not preset_comparison_df.empty:
            metadata['preset_comparison'] = preset_comparison_df.to_dict('records')

    impact_df = None
    impact_summary_df = None
    if output_settings['include_impact_summary']:
        impact_df = analyzer.calculate_rate_impact(df, total_col, request.numerator_cols, dimensions)
        if impact_df is not None and not impact_df.empty:
            impact_summary = {}
            rate_cols = [col for col in impact_df.columns if col.endswith('_Impact_PP')]
            for col in rate_cols:
                rate_name = col.replace('_Impact_PP', '')
                impact_summary[f'{rate_name}_mean_abs_impact_pp'] = round(impact_df[col].abs().mean(), 4)
                impact_summary[f'{rate_name}_max_abs_impact_pp'] = round(impact_df[col].abs().max(), 4)
            if rate_cols:
                impact_summary['mean_abs_impact_pp'] = round(impact_df[rate_cols].abs().stack().mean(), 4)
            metadata['impact_summary'] = impact_summary
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
            metadata['impact_details'] = impact_df.to_dict('records')

    entity_name = resolved_entity.replace(' ', '_') if resolved_entity else 'PEER_ONLY'
    if request.output:
        analysis_output_file = request.output
    elif len(all_results) > 1:
        analysis_output_file = f"benchmark_multi_rate_{entity_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    else:
        analysis_output_file = f"benchmark_{request.rate_types[0]}_rate_{entity_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    output_path = Path(analysis_output_file)

    artifacts = AnalysisArtifacts(
        results=all_results,
        metadata=metadata,
        weights_df=diagnostics['weights_df'],
        method_breakdown_df=diagnostics['method_breakdown_df'],
        privacy_validation_df=diagnostics['privacy_validation_df'],
        secondary_results_df=secondary_results_df,
        preset_comparison_df=preset_comparison_df,
        impact_df=impact_df,
        impact_summary_df=impact_summary_df,
        validation_issues=validation_issues,
        analysis_output_file=str(output_path),
        publication_output=str(output_path.with_name(f"{output_path.stem}_publication{output_path.suffix}")),
        analyzer=analyzer,
        compliance_summary=compliance_summary,
    )

    artifacts = write_outputs(request, artifacts, config=config, logger=logger)
    if request.export_balanced_csv:
        from benchmark import export_balanced_csv

        analyzer.secondary_metrics = request.secondary_metrics
        export_balanced_csv(
            None,
            analysis_output_file,
            logger,
            analysis_type='rate',
            all_results=all_results,
            df=df,
            analyzer=analyzer,
            dimensions=dimensions,
            total_col=total_col,
            numerator_cols=request.numerator_cols,
            include_calculated=output_settings['include_calculated_metrics'],
        )
        artifacts.csv_output = analysis_output_file.rsplit('.', 1)[0] + '_balanced.csv'

    artifacts.report_paths = build_report_paths(
        output_settings['output_format'],
        str(output_path),
        artifacts.publication_output,
    )
    if output_settings['include_audit_log']:
        write_audit_log(
            config,
            analysis_output_file=str(output_path),
            metadata=metadata,
            report_paths=artifacts.report_paths,
            dimensions_analyzed=len(dimensions),
            csv_output=artifacts.csv_output,
            impact_df=impact_df,
            privacy_validation_df=artifacts.privacy_validation_df,
            validation_issues=validation_issues,
        )
    return artifacts
