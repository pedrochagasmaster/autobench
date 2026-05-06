#!/usr/bin/env python
"""
Privacy-Compliant Benchmarking Tool

A dimensional analysis tool for comparing entity performance against peer groups
while maintaining Mastercard privacy compliance (Control 3.2).

Supports:
- Share Analysis: Transaction count/amount distribution across dimensions
- Rate Analysis: Approval rates and fraud rates across dimensions

Version: 2.0
"""

import argparse
import sys
import json
import logging
import gc
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

import pandas as pd

# Import core modules
from core.dimensional_analyzer import DimensionalAnalyzer
from core.data_loader import ValidationSeverity
from core.report_generator import ReportGenerator
from core.privacy_validator import PrivacyValidator
from core.preset_comparison import run_preset_comparison as _run_shared_preset_comparison
from core.analysis_run import (
    build_common_run_metadata,
    build_dimensional_analyzer as _analysis_run_build_dimensional_analyzer,
    build_report_paths,
    build_run_config,
    build_run_request,
    collect_run_diagnostics,
    execute_rate_run,
    execute_run,
    execute_share_run,
    prepare_run_data,
    resolve_consistency_mode as _analysis_run_resolve_consistency_mode,
    resolve_dimensions,
    resolve_output_settings,
    resolve_target_entity,
    validate_analysis_input,
    write_audit_log,
    RunBlocked,
)
from utils.config_manager import ConfigManager
from utils.logger import setup_logging

# Best preset marker for comparison tables
BEST_PRESET_MARKER = '*'


def _resolve_consistency_mode(
    opt_config: Dict[str, Any],
    logger: logging.Logger,
) -> Tuple[bool, str]:
    """Compatibility wrapper for the shared analysis-run helper."""
    return _analysis_run_resolve_consistency_mode(opt_config, logger)


def _build_dimensional_analyzer(
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
    """Compatibility wrapper for the shared analysis-run helper."""
    return _analysis_run_build_dimensional_analyzer(
        target_entity=target_entity,
        entity_col=entity_col,
        analysis_config=analysis_config,
        opt_config=opt_config,
        time_col=time_col,
        debug_mode=debug_mode,
        bic_percentile=bic_percentile,
        logger=logger,
        consistent_weights=consistent_weights,
    )


def get_presets_help() -> str:
    """Generate help text for available presets."""
    try:
        from utils.preset_manager import PresetManager
        preset_mgr = PresetManager()
        presets = preset_mgr.list_presets()
        if not presets:
            return ""
        
        help_text = "\nAVAILABLE PRESETS:\n"
        for name in presets:
            desc = preset_mgr.get_preset_description(name) or "No description"
            help_text += f"  {name:20s}: {desc}\n"
        return help_text
    except Exception:
        return ""


def create_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    
    parser = argparse.ArgumentParser(
        prog='benchmark',
        description='Privacy-Compliant Dimensional Benchmarking Tool v3.0',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
EXAMPLES:
  # Share analysis with preset
  python benchmark.py share --csv data.csv --entity "BANCO SANTANDER" --metric txn_cnt --preset standard

  # Share analysis with custom config
  python benchmark.py share --csv data.csv --entity "BANCO SANTANDER" --metric txn_cnt --config my_config.yaml

  # Rate analysis (approval rates)
  python benchmark.py rate --csv data.csv --entity "BANCO SANTANDER" \\
    --total-col txn_cnt --approved-col app_cnt --preset conservative

  # List available presets
  python benchmark.py config list

  # Show preset details
  python benchmark.py config show conservative

  # Generate config template
  python benchmark.py config generate my_config.yaml

  # Validate config file
  python benchmark.py config validate my_config.yaml

{get_presets_help()}
        """
    )
    
    # Add version flag
    parser.add_argument('--version', action='store_true',
                       help='Show version information')
    
    # Create subparsers for different commands
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Get available preset choices
    def get_preset_choices():
        try:
            from utils.preset_manager import PresetManager
            preset_mgr = PresetManager()
            return preset_mgr.list_presets()
        except Exception:
            return []
    
    preset_choices = get_preset_choices()
    
    # ========================================================================
    # SHARE ANALYSIS COMMAND
    # ========================================================================
    share_parser = subparsers.add_parser(
        'share',
        help='Share-based dimensional analysis',
        description='Analyze how an entity\'s volume is distributed across dimensions'
    )
    
    # Required arguments
    share_parser.add_argument('--csv', required=True, 
                             help='Path to CSV input file')
    share_parser.add_argument('--metric', required=True,
                             help='Metric column name to analyze (e.g., txn_cnt, tpv, transaction_count, transaction_amount)')
    
    # Secondary metrics (can specify multiple)
    share_parser.add_argument('--secondary-metrics', nargs='+',
                             help='Secondary metric columns to analyze using weights derived from the primary metric (space-separated list)')
    
    # Optional - Essential
    share_parser.add_argument('--entity',
                             help='Name of the entity to benchmark (omit for peer-only analysis)')
    share_parser.add_argument('--entity-col', default='issuer_name',
                             help='Entity identifier column name (default: issuer_name)')
    share_parser.add_argument('--output', '-o',
                             help='Output file path (default: auto-generated)')
    
    # Dimension selection
    dim_group = share_parser.add_mutually_exclusive_group()
    dim_group.add_argument('--dimensions', nargs='+',
                          help='Specific dimensions to analyze (e.g., flag_domestic cp_cnp)')
    # NOTE: default=None with store_true allows distinguishing "not provided" from
    # "explicitly False", enabling clean CLI-to-config override logic
    dim_group.add_argument('--auto', action='store_true', default=None,
                          help='Auto-detect all available dimensions')
    
    # Time awareness
    share_parser.add_argument('--time-col', 
                             help='Time column name for time-aware consistency (e.g., ano_mes, year_month)')
    
    # Configuration
    share_parser.add_argument('--config',
                             help='Configuration file (YAML)')
    share_parser.add_argument('--preset', choices=preset_choices,
                             help='Preset configuration name')
    share_parser.add_argument('--compliance-posture',
                             choices=['strict', 'best_effort', 'accuracy_first'],
                             help='Explicit final compliance posture for this run')
    share_parser.add_argument('--acknowledge-accuracy-first', action='store_true', default=None,
                             help='Required acknowledgement for accuracy_first runs')
    
    # Debug/Logging
    share_parser.add_argument('--debug', action='store_true', default=None,
                             help='Enable debug mode (includes unweighted averages and weight details)')
    share_parser.add_argument('--log-level',
                             choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                             help='Logging level (default: INFO)')
    share_parser.add_argument('--per-dimension-weights', action='store_true', default=None,
                             help='Optimize each dimension independently (disables global weighting mode)')
    share_parser.add_argument('--export-balanced-csv', action='store_true',
                             help='Export balanced shares and volumes to CSV (without weights or original values)')
    
    # Enhanced Analysis Options
    share_parser.add_argument('--compare-presets', action='store_true', default=None,
                             help='Compare all presets and report impact for each')
    share_parser.add_argument('--analyze-impact', action='store_true', default=None,
                             help='Include impact details and summary sheets in output')
    share_parser.add_argument('--analyze-distortion', action='store_true', default=None,
                             help='Alias for --analyze-impact (deprecated)')
    share_parser.add_argument('--validate-input', action='store_true', default=None,
                             dest='validate_input',
                             help='Enable input data validation before analysis (default: enabled)')
    share_parser.add_argument('--no-validate-input', action='store_false', dest='validate_input',
                             help='Disable input data validation')
    share_parser.add_argument('--output-format', choices=['analysis', 'publication', 'both'],
                             default=None,
                             help='Output format: analysis (default), publication, or both')
    share_parser.add_argument('--publication-format', action='store_const', const='publication',
                             dest='output_format',
                             help='Convenience alias for --output-format=publication')
    share_parser.add_argument('--include-calculated', action='store_true', default=None,
                             help='Include calculated metrics (raw/balanced share, impact) in balanced CSV export')

    # Advanced Optimization
    share_parser.add_argument('--auto-subset-search', action='store_true', default=None,
                             help='Automatically search for largest feasible global dimension subset')
    share_parser.add_argument('--subset-search-max-tests', type=int,
                             help='Maximum attempts during subset search')
    share_parser.add_argument('--trigger-subset-on-slack', action='store_true', default=None,
                             help='Trigger subset search if LP uses slack')
    share_parser.add_argument('--max-cap-slack', type=float,
                             help='Slack sum threshold to trigger subset search')

    # ========================================================================
    # RATE ANALYSIS COMMAND
    # ========================================================================
    rate_parser = subparsers.add_parser(
        'rate',
        help='Rate-based dimensional analysis',
        description='Analyze approval rates or fraud rates across dimensions'
    )
    
    # Required arguments
    rate_parser.add_argument('--csv', required=True,
                            help='Path to CSV input file')
    rate_parser.add_argument('--total-col', required=True,
                            help='Total transactions column (e.g., txn_cnt)')
    
    # Secondary metrics (can specify multiple)
    rate_parser.add_argument('--secondary-metrics', nargs='+',
                            help='Secondary metric columns (e.g., txn_count) to analyze using weights derived from the total column (space-separated list)')
    
    # Rate type selection (both can be specified for simultaneous analysis)
    rate_parser.add_argument('--approved-col',
                            help='Approved transactions column (for approval rate)')
    rate_parser.add_argument('--fraud-col',
                            help='Fraud transactions column (for fraud rate)')
    
    # Optional - Essential
    rate_parser.add_argument('--entity',
                            help='Name of the entity to benchmark (omit for peer-only analysis)')
    rate_parser.add_argument('--entity-col', default='issuer_name',
                            help='Entity identifier column name (default: issuer_name)')
    rate_parser.add_argument('--output', '-o',
                            help='Output file path (default: auto-generated)')
    
    # Dimension selection
    rate_dim_group = rate_parser.add_mutually_exclusive_group()
    rate_dim_group.add_argument('--dimensions', nargs='+',
                               help='Specific dimensions to analyze')
    rate_dim_group.add_argument('--auto', action='store_true', default=None,
                               help='Auto-detect all dimensions')
    
    # Time awareness
    rate_parser.add_argument('--time-col', 
                            help='Time column name for time-aware consistency (e.g., ano_mes, year_month)')
    
    # Configuration
    rate_parser.add_argument('--config',
                            help='Configuration file (YAML)')
    rate_parser.add_argument('--preset', choices=preset_choices,
                            help='Preset configuration name')
    rate_parser.add_argument('--compliance-posture',
                            choices=['strict', 'best_effort', 'accuracy_first'],
                            help='Explicit final compliance posture for this run')
    rate_parser.add_argument('--acknowledge-accuracy-first', action='store_true', default=None,
                            help='Required acknowledgement for accuracy_first runs')
    
    # Debug/Logging
    rate_parser.add_argument('--debug', action='store_true', default=None,
                            help='Enable debug mode (includes unweighted averages and weight details)')
    rate_parser.add_argument('--log-level',
                            choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                            help='Logging level (default: INFO)')
    rate_parser.add_argument('--per-dimension-weights', action='store_true', default=None,
                            help='Optimize each dimension independently (disables global weighting mode)')
    rate_parser.add_argument('--export-balanced-csv', action='store_true',
                            help='Export balanced shares and volumes to CSV (without weights or original values)')
    
    # Enhanced Analysis Options
    rate_parser.add_argument('--compare-presets', action='store_true', default=None,
                            help='Compare all presets and report impact for each')
    rate_parser.add_argument('--analyze-impact', action='store_true', default=None,
                            help='Include impact details and summary sheets in output')
    rate_parser.add_argument('--analyze-distortion', action='store_true', default=None,
                            help='Alias for --analyze-impact (deprecated)')
    rate_parser.add_argument('--validate-input', action='store_true', default=None,
                            dest='validate_input',
                            help='Enable input data validation before analysis (default: enabled)')
    rate_parser.add_argument('--no-validate-input', action='store_false', dest='validate_input',
                            help='Disable input data validation')
    rate_parser.add_argument('--output-format', choices=['analysis', 'publication', 'both'],
                            default=None,
                            help='Output format: analysis (default), publication, or both')
    rate_parser.add_argument('--publication-format', action='store_const', const='publication',
                            dest='output_format',
                            help='Convenience alias for --output-format=publication')
    rate_parser.add_argument('--include-calculated', action='store_true', default=None,
                            help='Include calculated metrics (rate impact) in balanced CSV export')
    rate_parser.add_argument('--fraud-in-bps', action='store_true', default=None,
                            dest='fraud_in_bps',
                            help='Convert fraud rates to basis points in publication format (default: enabled)')
    rate_parser.add_argument('--no-fraud-in-bps', action='store_false', dest='fraud_in_bps',
                            help='Keep fraud rates as percentages in publication format')
    
    # Advanced Optimization
    rate_parser.add_argument('--auto-subset-search', action='store_true', default=None,
                            help='Automatically search for largest feasible global dimension subset')
    rate_parser.add_argument('--subset-search-max-tests', type=int,
                            help='Maximum attempts during subset search')
    rate_parser.add_argument('--trigger-subset-on-slack', action='store_true', default=None,
                            help='Trigger subset search if LP uses slack')
    rate_parser.add_argument('--max-cap-slack', type=float,
                            help='Slack sum threshold to trigger subset search')

    # ========================================================================
    # CONFIG MANAGEMENT COMMAND
    # ========================================================================
    config_parser = subparsers.add_parser(
        'config',
        help='Manage configurations and presets'
    )
    
    config_subparsers = config_parser.add_subparsers(dest='config_command',
                                                     help='Config management command')
    
    # List presets
    config_subparsers.add_parser('list',
                                 help='List available presets')
    
    # Show preset
    show_parser = config_subparsers.add_parser('show',
                                               help='Show preset details')
    show_parser.add_argument('preset_name',
                            help='Preset name')
    
    # Validate config
    validate_parser = config_subparsers.add_parser('validate',
                                                   help='Validate config file')
    validate_parser.add_argument('config_file',
                                help='Config file path')
    
    # Generate template
    generate_parser = config_subparsers.add_parser('generate',
                                                   help='Generate config template')
    generate_parser.add_argument('output_file',
                                help='Output file path')
    
    return parser


def handle_config_command(args: argparse.Namespace) -> int:
    """Handle config subcommands.
    
    Args:
        args: Parsed command-line arguments
        
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    import shutil
    from utils.preset_manager import PresetManager
    from utils.validators import validate_config_file
    
    preset_mgr = PresetManager()
    
    if args.config_command == 'list':
        print(preset_mgr.format_preset_list())
        return 0
    
    elif args.config_command == 'show':
        print(preset_mgr.format_preset_detail(args.preset_name))
        return 0
    
    elif args.config_command == 'validate':
        is_valid, errors = validate_config_file(Path(args.config_file))
        if is_valid:
            print(f"[OK] Configuration file is valid: {args.config_file}")
            return 0
        else:
            print(f"[FAIL] Configuration validation failed:")
            for error in errors:
                print(f"  {error}")
            return 1
    
    elif args.config_command == 'generate':
        template_path = Path(__file__).parent / 'config' / 'template.yaml'
        output_path = Path(args.output_file)
        
        if not template_path.exists():
            print(f"[FAIL] Template file not found: {template_path}")
            print(f"  Please ensure the config/template.yaml file exists.")
            return 1
        
        if output_path.exists():
            print(f"[FAIL] File already exists: {output_path}")
            print(f"  Please choose a different filename or delete the existing file.")
            return 1
        
        try:
            shutil.copy(template_path, output_path)
            print(f"[OK] Configuration template created: {output_path}")
            print(f"  Edit this file to customize your analysis settings.")
            print(f"  Validate with: benchmark config validate {output_path}")
            return 0
        except Exception as e:
            print(f"[FAIL] Failed to create config file: {e}")
            return 1
    
    else:
        print("Usage: benchmark config {list|show|validate|generate}")
        print("  list                    List available presets")
        print("  show PRESET             Show preset details")
        print("  validate PATH           Validate a config file")
        print("  generate PATH           Generate a template config file")
        return 1


def print_version() -> None:
    """Print version information."""
    import sys
    import platform
    
    print("Privacy-Compliant Peer Benchmark Tool")
    print(f"Version: 3.0.0")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Platform: {platform.system()} {platform.release()}")


def list_presets() -> None:
    """Display available presets (deprecated - use 'benchmark config list')."""
    print("Note: 'benchmark presets' is deprecated. Use 'benchmark config list' instead.\n")
    from utils.preset_manager import PresetManager
    preset_mgr = PresetManager()
    print(preset_mgr.format_preset_list())


def run_preset_comparison(
    df: pd.DataFrame,
    metric_col: str,
    entity_col: str,
    dimensions: list,
    target_entity: Optional[str],
    time_col: Optional[str],
    analysis_type: str,
    logger: logging.Logger,
    total_col: Optional[str] = None,
    numerator_cols: Optional[Dict[str, str]] = None
) -> pd.DataFrame:
    """Compatibility wrapper over the shared preset-comparison seam."""
    return _run_shared_preset_comparison(
        df=df,
        metric_col=metric_col,
        entity_col=entity_col,
        dimensions=list(dimensions),
        target_entity=target_entity,
        time_col=time_col,
        analysis_type=analysis_type,
        logger=logger,
        analyzer_factory=_build_dimensional_analyzer,
        total_col=total_col,
        numerator_cols=numerator_cols,
    )


def run_share_analysis(args: argparse.Namespace, logger: logging.Logger) -> int:
    """Thin CLI adapter over the shared analysis-run executor."""
    logger.info("Starting share-based dimensional analysis")
    try:
        request = build_run_request('share', args)
        artifacts = execute_share_run(request, logger)
        print(f"\n{'='*80}")
        print("SHARE ANALYSIS COMPLETE")
        print(f"{'='*80}")
        print(f"Entity: {artifacts.metadata.get('entity', 'PEER-ONLY MODE')}")
        print(f"Metric: {artifacts.metadata.get('metric')}")
        print(f"Compliance Posture: {artifacts.metadata.get('compliance_posture')}")
        print(f"Compliance Verdict: {artifacts.metadata.get('compliance_verdict')}")
        print(f"Acknowledgement State: {artifacts.metadata.get('acknowledgement_state')}")
        if artifacts.metadata.get('compliance_posture') == 'best_effort':
            print("WARNING: best_effort posture may complete with labeled non-compliant outputs.")
        if artifacts.metadata.get('compliance_posture') == 'accuracy_first':
            print("WARNING: accuracy_first posture prioritizes analytical fidelity over strict compliance.")
        print(f"Dimensions Analyzed: {len(artifacts.results)}")
        print(f"Report: {', '.join(artifacts.report_paths)}")
        print(f"{'='*80}\n")
        return 0
    except RunBlocked as e:
        logger.error(f"Analysis blocked: {e}")
        print(f"Analysis blocked: {e}")
        print(json.dumps(e.compliance_summary, indent=2, default=str))
        return 1
    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        return 1


def run_rate_analysis(args: argparse.Namespace, logger: logging.Logger) -> int:
    """Thin CLI adapter over the shared analysis-run executor."""
    logger.info("Starting rate-based dimensional analysis")
    try:
        request = build_run_request('rate', args)
        artifacts = execute_rate_run(request, logger)
        print(f"\n{'='*80}")
        print("RATE ANALYSIS COMPLETE")
        print(f"{'='*80}")
        print(f"Entity: {artifacts.metadata.get('entity', 'PEER-ONLY MODE')}")
        print(f"Rate Types Analyzed: {', '.join([rt.upper() for rt in artifacts.metadata.get('rate_types', [])])}")
        print(f"Compliance Posture: {artifacts.metadata.get('compliance_posture')}")
        print(f"Compliance Verdict: {artifacts.metadata.get('compliance_verdict')}")
        print(f"Acknowledgement State: {artifacts.metadata.get('acknowledgement_state')}")
        if artifacts.metadata.get('compliance_posture') == 'best_effort':
            print("WARNING: best_effort posture may complete with labeled non-compliant outputs.")
        if artifacts.metadata.get('compliance_posture') == 'accuracy_first':
            print("WARNING: accuracy_first posture prioritizes analytical fidelity over strict compliance.")
        print(f"Dimensions Analyzed: {len(artifacts.metadata.get('dimension_names', []))}")
        print(f"Report: {', '.join(artifacts.report_paths)}")
        print(f"{'='*80}\n")
        return 0
    except RunBlocked as e:
        logger.error(f"Analysis blocked: {e}")
        print(f"Analysis blocked: {e}")
        print(json.dumps(e.compliance_summary, indent=2, default=str))
        return 1
    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        return 1


def _save_workbook_with_retries(
    wb: Any,
    output_file: str,
    logger: logging.Logger,
    max_attempts: int = 3,
) -> None:
    from core.excel_reports import _save_workbook_with_retries as _shared_save_workbook_with_retries

    _shared_save_workbook_with_retries(wb, output_file, logger, max_attempts=max_attempts)


def generate_excel_report(
    results: Dict[str, Any],
    output_file: str,
    entity_name: str,
    analysis_type: str,
    logger: logging.Logger,
    metadata: Optional[Dict[str, Any]] = None,
    weights_df: Optional[Any] = None,
    method_breakdown_df: Optional[pd.DataFrame] = None,
    privacy_validation_df: Optional[pd.DataFrame] = None,
    secondary_results: Optional[Dict[str, Any]] = None,
    preset_comparison_df: Optional[pd.DataFrame] = None,
    impact_df: Optional[pd.DataFrame] = None,
    impact_summary_df: Optional[pd.DataFrame] = None,
    validation_issues: Optional[Any] = None,
    config: Optional[Any] = None,
) -> None:
    from core.excel_reports import generate_excel_report as _shared_generate_excel_report

    _shared_generate_excel_report(
        results,
        output_file,
        entity_name,
        analysis_type,
        logger,
        metadata,
        weights_df,
        method_breakdown_df,
        privacy_validation_df,
        secondary_results,
        preset_comparison_df,
        impact_df,
        impact_summary_df,
        validation_issues,
        config=config,
    )


def generate_multi_rate_excel_report(
    all_results: Dict[str, Dict[str, Any]],
    output_file: str,
    entity_name: str,
    logger: logging.Logger,
    metadata: Dict[str, Any],
    weights_df: Optional[Any] = None,
    numerator_cols: Optional[Dict[str, str]] = None,
    bic_percentiles: Optional[Dict[str, float]] = None,
    privacy_validation_df: Optional[pd.DataFrame] = None,
    method_breakdown_df: Optional[pd.DataFrame] = None,
    secondary_results: Optional[Dict[str, Any]] = None,
    preset_comparison_df: Optional[pd.DataFrame] = None,
    impact_df: Optional[pd.DataFrame] = None,
    impact_summary_df: Optional[pd.DataFrame] = None,
    validation_issues: Optional[Any] = None,
    config: Optional[Any] = None,
) -> None:
    from core.excel_reports import generate_multi_rate_excel_report as _shared_generate_multi_rate_excel_report

    _shared_generate_multi_rate_excel_report(
        all_results,
        output_file,
        entity_name,
        logger,
        metadata,
        weights_df,
        numerator_cols,
        bic_percentiles,
        privacy_validation_df,
        method_breakdown_df,
        secondary_results,
        preset_comparison_df,
        impact_df,
        impact_summary_df,
        validation_issues,
        config=config,
    )


def get_balanced_metrics_df(
    df: pd.DataFrame,
    analyzer: DimensionalAnalyzer,
    dimensions: list,
    metric_col: Optional[str] = None,
    secondary_metrics: Optional[list] = None,
    total_col: Optional[str] = None,
    numerator_cols: Optional[Dict[str, str]] = None
) -> pd.DataFrame:
    """
    Calculate balanced metrics for primary and secondary metrics.
    Returns a DataFrame with columns: Dimension, Category, [Time], Balanced_{Metric}...
    """
    rows = []
    entity_col = analyzer.entity_column
    
    # Get global weights or per-dimension weights
    def get_weight(dimension: str, peer: str) -> float:
        """Get weight multiplier for a peer in a dimension."""
        if dimension in analyzer.per_dimension_weights and peer in analyzer.per_dimension_weights[dimension]:
            return float(analyzer.per_dimension_weights[dimension][peer])
        if hasattr(analyzer, 'global_weights') and peer in analyzer.global_weights:
            return float(analyzer.global_weights[peer].get('multiplier', 1.0))
        return 1.0
    
    # Check if time column is available
    time_col = analyzer.time_column if hasattr(analyzer, 'time_column') else None
    has_time = time_col and time_col in df.columns
    
    # Build list of metrics to calculate
    metrics_to_calculate = []
    
    # Share analysis primary metric
    if metric_col:
        metrics_to_calculate.append(('Primary', metric_col))
        
    # Rate analysis metrics
    if total_col:
        metrics_to_calculate.append(('Total', total_col))
        if numerator_cols:
            for key, col in numerator_cols.items():
                if col in df.columns:
                    metrics_to_calculate.append((f'Approval_{key.capitalize()}' if key == 'approval' else f'Fraud_{key.capitalize()}' if key == 'fraud' else key.capitalize(), col))

    # Secondary metrics
    if secondary_metrics:
        for sec_metric in secondary_metrics:
            if sec_metric in df.columns:
                metrics_to_calculate.append(('Secondary', sec_metric))
    
    # Process each dimension
    for dimension in dimensions:
        # Aggregate data by entity, dimension category, and optionally time
        group_cols = [entity_col, dimension]
        # Only add time_col if it's different from the current dimension
        if has_time and time_col != dimension:
            group_cols.append(time_col)
        
        # Build aggregation dict - exclude columns that are part of groupby
        agg_dict = {}
        for _, metric in metrics_to_calculate:
            if metric in df.columns and metric not in group_cols:
                agg_dict[metric] = 'sum'
        
        if not agg_dict:
            continue
            
        entity_dim_agg = df.groupby(group_cols).agg(agg_dict).reset_index()
        
        # Get unique categories
        categories = entity_dim_agg[dimension].unique()
        
        # Get unique time periods if applicable
        time_periods = sorted(entity_dim_agg[time_col].unique()) if has_time else [None]
        
        for category in categories:
            for time_period in time_periods:
                # Filter to this category (and time period if applicable)
                if has_time:
                    cat_df = entity_dim_agg[
                        (entity_dim_agg[dimension] == category) & 
                        (entity_dim_agg[time_col] == time_period)
                    ]
                else:
                    cat_df = entity_dim_agg[entity_dim_agg[dimension] == category]
                
                if cat_df.empty:
                    continue
                
                # Build row data
                row_data = {
                    'Dimension': dimension,
                    'Category': category,
                }
                
                # Add time period if applicable
                if has_time:
                    row_data[time_col] = time_period
                
                # Calculate balanced metric for each metric column
                for metric_type, metric in metrics_to_calculate:
                    if metric not in cat_df.columns:
                        continue
                        
                    balanced_metric = 0.0
                    for _, row in cat_df.iterrows():
                        peer = row[entity_col]
                        weight = get_weight(dimension, peer)
                        balanced_metric += row[metric] * weight
                    
                    # Column name based on metric type
                    if metric_type == 'Primary':
                        col_name = f'Balanced_{metric}'
                    elif metric_type == 'Total':
                        col_name = 'Balanced_Total'
                    elif metric_type.startswith('Approval'):
                        col_name = 'Balanced_Approval_Total' # Standardize name for rate analysis
                    elif metric_type.startswith('Fraud'):
                        col_name = 'Balanced_Fraud_Total' # Standardize name for rate analysis
                    elif metric_type == 'Secondary':
                        col_name = metric
                    else:
                        col_name = f'Balanced_{metric}'
                        
                    row_data[col_name] = round(balanced_metric, 2)
                
                rows.append(row_data)
    
    if not rows:
        return pd.DataFrame()
    
    # Create DataFrame
    result_df = pd.DataFrame(rows)
    
    # Sort by Dimension, Time (if present), then Category
    sort_cols = ['Dimension']
    if has_time and time_col in result_df.columns:
        sort_cols.append(time_col)
    sort_cols.append('Category')
    
    return result_df.sort_values(sort_cols)


def export_balanced_csv(
    results: Optional[Dict[str, pd.DataFrame]], 
    output_file: str, 
    logger: logging.Logger,
    analysis_type: str = 'share',
    all_results: Optional[Dict[str, Dict[str, pd.DataFrame]]] = None,
    df: Optional[pd.DataFrame] = None,
    analyzer: Optional[Any] = None,
    dimensions: Optional[list] = None,
    total_col: Optional[str] = None,
    numerator_cols: Optional[Dict[str, str]] = None,
    metric_col: Optional[str] = None,
    secondary_metrics: Optional[list] = None,
    include_calculated: bool = False
) -> None:
    """
    Export balanced metrics to CSV in concatenated dimension format.
    
    For rate analysis: exports dimension, category, balanced_total, balanced_approval_total, balanced_fraud_total
    The balanced totals are weighted sums: sum(peer_value * weight) across all peers
    
    For share analysis: exports dimension, category, balanced metric values (for primary and secondary metrics)
    The balanced metrics are weighted sums: sum(peer_metric_value * weight) across all peers
    
    Args:
        results: Results dictionary for share analysis (dimension -> DataFrame)
        output_file: Base output file path (will change extension to .csv)
        logger: Logger instance
        analysis_type: Type of analysis ('share' or 'rate')
        all_results: For rate analysis, dict of rate_type -> results (e.g., {'approval': {...}, 'fraud': {...}})
        df: Source dataframe for recalculating weighted totals
        analyzer: Analyzer instance with weights
        dimensions: List of dimensions analyzed
        total_col: Total column name (for rate analysis)
        numerator_cols: Dict mapping rate_type to numerator column name
        metric_col: Primary metric column name (for share analysis)
        secondary_metrics: List of secondary metric columns (for share analysis)
    """
    # Create CSV filename from Excel filename
    csv_output = output_file.rsplit('.', 1)[0] + '_balanced.csv'
    
    if analysis_type == 'rate' and all_results and df is not None and analyzer is not None:
        # Rate analysis: calculate weighted totals for each dimension-category
        export_rows = []
        
        # Get entity column and weights
        entity_col = analyzer.entity_column
        
        # Get global weights or per-dimension weights
        def get_weight(dimension: str, peer: str) -> float:
            """Get weight multiplier for a peer in a dimension."""
            weight = 1.0
            if hasattr(analyzer, 'global_weights') and peer in analyzer.global_weights:
                weight = float(analyzer.global_weights[peer].get('multiplier', 1.0))
            if dimension in analyzer.per_dimension_weights and peer in analyzer.per_dimension_weights[dimension]:
                weight = float(analyzer.per_dimension_weights[dimension][peer])
            return weight
        
        # Check if time column is available
        time_col = analyzer.time_column if hasattr(analyzer, 'time_column') else None
        has_time = time_col and time_col in df.columns
        
        # Get secondary metrics from caller
        secondary_metrics_list = getattr(analyzer, 'secondary_metrics', None)
        
        # Process each dimension
        for dimension in dimensions:
            # Aggregate data by entity, dimension category, and optionally time
            group_cols = [entity_col, dimension]
            # Only add time_col if it's different from the current dimension
            if has_time and time_col != dimension:
                group_cols.append(time_col)
            
            # Build aggregation dict - exclude columns that are part of groupby
            agg_dict = {}
            if total_col not in group_cols:
                agg_dict[total_col] = 'sum'
            
            # Add numerator columns (exclude those in group_cols)
            if numerator_cols:
                for num_col in numerator_cols.values():
                    if num_col in df.columns and num_col not in group_cols:
                        agg_dict[num_col] = 'sum'
            
            # Add secondary metrics (exclude those in group_cols)
            if secondary_metrics_list:
                for sec_metric in secondary_metrics_list:
                    if sec_metric in df.columns and sec_metric not in group_cols:
                        agg_dict[sec_metric] = 'sum'
            
            if not agg_dict:
                continue
                
            entity_dim_agg = df.groupby(group_cols).agg(agg_dict).reset_index()
            
            # Get unique categories
            categories = entity_dim_agg[dimension].unique()
            
            # Get unique time periods if applicable
            time_periods = sorted(entity_dim_agg[time_col].unique()) if has_time else [None]
            
            for category in categories:
                for time_period in time_periods:
                    # Filter to this category (and time period if applicable)
                    if has_time:
                        cat_df = entity_dim_agg[
                            (entity_dim_agg[dimension] == category) & 
                            (entity_dim_agg[time_col] == time_period)
                        ]
                    else:
                        cat_df = entity_dim_agg[entity_dim_agg[dimension] == category]
                    
                    if cat_df.empty:
                        continue
                    
                    # Calculate weighted totals
                    balanced_total = 0.0
                    balanced_approval = 0.0
                    balanced_fraud = 0.0
                    secondary_balanced = {}
                    
                    # Calculate raw totals if requested
                    raw_total = 0.0
                    raw_approval = 0.0
                    raw_fraud = 0.0
                    secondary_raw = {}

                    # Peer-only totals for weight-effect calculations
                    raw_peer_total = 0.0
                    raw_peer_approval = 0.0
                    raw_peer_fraud = 0.0
                    balanced_peer_total = 0.0
                    balanced_peer_approval = 0.0
                    balanced_peer_fraud = 0.0
                    
                    # Initialize secondary metrics dict
                    if secondary_metrics_list:
                        for sec_metric in secondary_metrics_list:
                            if sec_metric in cat_df.columns:
                                secondary_balanced[sec_metric] = 0.0
                                if include_calculated:
                                    secondary_raw[sec_metric] = 0.0
                    
                    for _, row in cat_df.iterrows():
                        peer = row[entity_col]
                        weight = get_weight(dimension, peer)
                        is_target = analyzer.target_entity is not None and peer == analyzer.target_entity

                        # Balanced totals should always be peer-only
                        if not is_target:
                            # Weighted total (denominator)
                            balanced_total += row[total_col] * weight
                            balanced_peer_total += row[total_col] * weight

                            # Weighted approval numerator
                            if approval_col := numerator_cols.get('approval'):
                                if approval_col in row.index:
                                    balanced_approval += row[approval_col] * weight
                                    balanced_peer_approval += row[approval_col] * weight

                            # Weighted fraud numerator
                            if fraud_col := numerator_cols.get('fraud'):
                                if fraud_col in row.index:
                                    balanced_fraud += row[fraud_col] * weight
                                    balanced_peer_fraud += row[fraud_col] * weight

                            # Weighted secondary metrics
                            for sec_metric in secondary_balanced.keys():
                                if sec_metric in row.index:
                                    secondary_balanced[sec_metric] += row[sec_metric] * weight

                        # Raw totals if requested (peer-only)
                        if include_calculated and not is_target:
                            raw_total += row[total_col]
                            raw_peer_total += row[total_col]

                            if approval_col := numerator_cols.get('approval'):
                                if approval_col in row.index:
                                    raw_approval += row[approval_col]
                                    raw_peer_approval += row[approval_col]

                            if fraud_col := numerator_cols.get('fraud'):
                                if fraud_col in row.index:
                                    raw_fraud += row[fraud_col]
                                    raw_peer_fraud += row[fraud_col]

                            for sec_metric in secondary_raw.keys():
                                if sec_metric in row.index:
                                    secondary_raw[sec_metric] += row[sec_metric]
                    
                    # Add row to export
                    row_data = {
                        'Dimension': dimension,
                        'Category': category,
                    }
                    
                    if include_calculated:
                        # Add raw and balanced rates and impact
                        if total_col:
                            row_data['Raw_Total'] = raw_total
                            row_data['Balanced_Total'] = balanced_total
                        
                        # Approval
                        if numerator_cols.get('approval'):
                            row_data['Balanced_Approval_Total'] = balanced_approval
                            # Calculate rates in %
                            raw_rate = (raw_peer_approval / raw_peer_total * 100) if raw_peer_total > 0 else 0.0
                            bal_rate = (balanced_peer_approval / balanced_peer_total * 100) if balanced_peer_total > 0 else 0.0
                            row_data['Raw_Approval_Rate_%'] = raw_rate
                            row_data['Balanced_Approval_Rate_%'] = bal_rate
                            row_data['Approval_Impact_PP'] = bal_rate - raw_rate
                            
                        # Fraud
                        if numerator_cols.get('fraud'):
                            row_data['Balanced_Fraud_Total'] = balanced_fraud
                            # Calculate rates in pp for consistency with impact
                            raw_fraud_rate = (raw_peer_fraud / raw_peer_total * 100) if raw_peer_total > 0 else 0.0
                            bal_fraud_rate = (balanced_peer_fraud / balanced_peer_total * 100) if balanced_peer_total > 0 else 0.0
                            row_data['Raw_Fraud_Rate_%'] = raw_fraud_rate
                            row_data['Balanced_Fraud_Rate_%'] = bal_fraud_rate
                            row_data['Fraud_Impact_PP'] = bal_fraud_rate - raw_fraud_rate
                    
                    # Add time period if applicable
                    if has_time:
                        row_data[time_col] = time_period
                    
                    # Use dynamic column names based on input columns
                    row_data[total_col] = round(balanced_total, 2)
                    
                    if numerator_cols:
                        if approval_col := numerator_cols.get('approval'):
                            row_data[approval_col] = round(balanced_approval, 2) if balanced_approval > 0 else None
                        if fraud_col := numerator_cols.get('fraud'):
                            row_data[fraud_col] = round(balanced_fraud, 2) if balanced_fraud > 0 else None
                    
                    # Add secondary metrics to row
                    for sec_metric, sec_value in secondary_balanced.items():
                        row_data[sec_metric] = round(sec_value, 2)
                    
                    export_rows.append(row_data)
        
        if not export_rows:
            logger.warning("No data to export for rate analysis CSV")
            return
        
        # Create DataFrame and export
        export_df = pd.DataFrame(export_rows)
        
        # Sort by Dimension, Time (if present), then Category
        sort_cols = ['Dimension']
        if has_time and time_col in export_df.columns:
            sort_cols.append(time_col)
        sort_cols.append('Category')
        
        export_df = export_df.sort_values(sort_cols)
        export_df.to_csv(csv_output, index=False)
        logger.info(f"Balanced rate data CSV exported to: {csv_output}")
        print(f"Balanced CSV: {csv_output}")
        
    elif analysis_type == 'share' and results and df is not None and analyzer is not None:
        # Share analysis: calculate balanced metrics for each dimension-category
        export_rows = []
        
        # Get entity column and weights
        entity_col = analyzer.entity_column
        
        # Get global weights or per-dimension weights
        def get_weight(dimension: str, peer: str) -> float:
            """Get weight multiplier for a peer in a dimension."""
            weight = 1.0
            if hasattr(analyzer, 'global_weights') and peer in analyzer.global_weights:
                weight = float(analyzer.global_weights[peer].get('multiplier', 1.0))
            if dimension in analyzer.per_dimension_weights and peer in analyzer.per_dimension_weights[dimension]:
                weight = float(analyzer.per_dimension_weights[dimension][peer])
            return weight
        
        # Check if time column is available
        time_col = analyzer.time_column if hasattr(analyzer, 'time_column') else None
        has_time = time_col and time_col in df.columns
        
        # Build list of metrics to calculate (primary + secondary)
        metrics_to_calculate = []
        if metric_col:
            metrics_to_calculate.append(('Primary', metric_col))
        if secondary_metrics:
            for sec_metric in secondary_metrics:
                if sec_metric in df.columns:
                    metrics_to_calculate.append(('Secondary', sec_metric))
        
        target_entity = analyzer.target_entity
        if include_calculated and not target_entity:
            logger.info("Peer-only mode: skipping target-vs-peer share calculations in balanced CSV.")

        # Process each dimension
        for dimension in dimensions:
            # Aggregate data by entity, dimension category, and optionally time
            group_cols = [entity_col, dimension]
            # Only add time_col if it's different from the current dimension
            if has_time and time_col != dimension:
                group_cols.append(time_col)

            # Build aggregation dict for all metrics - exclude columns that are part of groupby
            agg_dict = {}
            for _, metric in metrics_to_calculate:
                if metric in df.columns and metric not in group_cols:
                    agg_dict[metric] = 'sum'

            if not agg_dict:
                continue

            entity_dim_agg = df.groupby(group_cols).agg(agg_dict).reset_index()

            # Get unique categories
            categories = entity_dim_agg[dimension].unique()

            # Get unique time periods if applicable
            time_periods = sorted(entity_dim_agg[time_col].unique()) if has_time else [None]

            for category in categories:
                for time_period in time_periods:
                    # Filter to this category (and time period if applicable)
                    if has_time:
                        cat_df = entity_dim_agg[
                            (entity_dim_agg[dimension] == category) &
                            (entity_dim_agg[time_col] == time_period)
                        ]
                    else:
                        cat_df = entity_dim_agg[entity_dim_agg[dimension] == category]

                    if cat_df.empty:
                        continue

                    # Calculate metrics
                    balanced_metric_values = {}
                    raw_metric_values = {}

                    # Initialize values
                    for m_type, m_col in metrics_to_calculate:
                        balanced_metric_values[m_col] = 0.0
                        if include_calculated:
                            raw_metric_values[m_col] = 0.0

                    for _, row in cat_df.iterrows():
                        peer = row[entity_col]
                        if analyzer.target_entity is not None and peer == analyzer.target_entity:
                            continue
                        weight = get_weight(dimension, peer)

                        for m_type, m_col in metrics_to_calculate:
                            if m_col in row:
                                val = row[m_col]
                                balanced_metric_values[m_col] += val * weight
                                if include_calculated:
                                    raw_metric_values[m_col] += val

                    # Add row to export
                    row_data = {
                        'Dimension': dimension,
                        'Category': category,
                    }

                    # Add metric values
                    for m_type, m_col in metrics_to_calculate:
                        # Use original metric name for column header
                        clean_name = m_col
                        row_data[f'Balanced_{clean_name}'] = round(balanced_metric_values[m_col], 2)

                        if include_calculated:
                            row_data[f'Raw_{clean_name}'] = round(raw_metric_values[m_col], 2)

                            # Calculate shares and impact
                            if target_entity:
                                target_rows = cat_df[cat_df[entity_col] == target_entity]
                                peer_rows = cat_df[cat_df[entity_col] != target_entity]
                                target_val = float(target_rows[m_col].sum()) if not target_rows.empty else 0.0
                                raw_peer_total = float(peer_rows[m_col].sum()) if not peer_rows.empty else 0.0
                                balanced_peer_total = 0.0
                                for _, prow in peer_rows.iterrows():
                                    peer = prow[entity_col]
                                    weight = get_weight(dimension, peer)
                                    balanced_peer_total += float(prow[m_col]) * weight
                                raw_denom = target_val + raw_peer_total
                                bal_denom = target_val + balanced_peer_total
                                raw_share = (target_val / raw_denom * 100.0) if raw_denom > 0 else 0.0
                                bal_share = (target_val / bal_denom * 100.0) if bal_denom > 0 else 0.0
                                row_data[f'Raw_{clean_name}_Share_%'] = round(raw_share, 4)
                                row_data[f'Balanced_{clean_name}_Share_%'] = round(bal_share, 4)
                                row_data[f'{clean_name}_Impact_PP'] = round(bal_share - raw_share, 4)
                            else:
                                row_data[f'Raw_{clean_name}_Share_%'] = None
                                row_data[f'Balanced_{clean_name}_Share_%'] = None
                                row_data[f'{clean_name}_Impact_PP'] = None

                    # Add time period if applicable
                    if has_time:
                        row_data[time_col] = time_period

                    export_rows.append(row_data)
        
        if not export_rows:
            logger.warning("No data to export for share analysis CSV")
            return
        
        # Create DataFrame and export
        export_df = pd.DataFrame(export_rows)
        
        # Sort by Dimension, Time (if present), then Category
        sort_cols = ['Dimension']
        if has_time and time_col in export_df.columns:
            sort_cols.append(time_col)
        sort_cols.append('Category')
        
        export_df = export_df.sort_values(sort_cols)
        export_df.to_csv(csv_output, index=False)
        logger.info(f"Balanced share metrics CSV exported to: {csv_output}")
        print(f"Balanced CSV: {csv_output}")
    
    else:
        logger.warning("No valid results provided for CSV export")
        return


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    
    if len(sys.argv) == 1:
        parser.print_help()
        return 0
    
    args = parser.parse_args()
    
    # Handle version flag
    if hasattr(args, 'version') and args.version:
        print_version()
        return 0
    
    # Handle config command
    if args.command == 'config':
        return handle_config_command(args)
    
    # Handle deprecated presets command
    if args.command == 'presets':
        list_presets()
        return 0
    
    if not args.command:
        parser.print_help()
        return 0
    
    # Setup logging for analysis commands
    log_level = getattr(args, 'log_level', None) or 'INFO'
    logger = setup_logging(log_level, f"benchmark_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    
    # Route to appropriate handler
    if args.command == 'share':
        return run_share_analysis(args, logger)
    elif args.command == 'rate':
        return run_rate_analysis(args, logger)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
