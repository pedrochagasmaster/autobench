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
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

import pandas as pd

# Import core modules
from core.dimensional_analyzer import DimensionalAnalyzer
from core.data_loader import DataLoader
from utils.config_manager import ConfigManager
from utils.logger import setup_logging


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
    except:
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
        except:
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
    dim_group.add_argument('--auto', action='store_true',
                          help='Auto-detect all available dimensions')
    
    # Time awareness
    share_parser.add_argument('--time-col', 
                             help='Time column name for time-aware consistency (e.g., ano_mes, year_month)')
    
    # Configuration
    share_parser.add_argument('--config',
                             help='Configuration file (YAML)')
    share_parser.add_argument('--preset', choices=preset_choices,
                             help='Preset configuration name')
    
    # Debug/Logging
    share_parser.add_argument('--debug', action='store_true',
                             help='Enable debug mode (includes unweighted averages and weight details)')
    share_parser.add_argument('--log-level',
                             choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                             help='Logging level (default: INFO)')
    share_parser.add_argument('--per-dimension-weights', action='store_true',
                             help='Optimize each dimension independently (disables global weighting mode)')
    share_parser.add_argument('--export-balanced-csv', action='store_true',
                             help='Export balanced shares and volumes to CSV (without weights or original values)')

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
    rate_dim_group.add_argument('--auto', action='store_true',
                               help='Auto-detect all dimensions')
    
    # Time awareness
    rate_parser.add_argument('--time-col', 
                            help='Time column name for time-aware consistency (e.g., ano_mes, year_month)')
    
    # Configuration
    rate_parser.add_argument('--config',
                            help='Configuration file (YAML)')
    rate_parser.add_argument('--preset', choices=preset_choices,
                            help='Preset configuration name')
    
    # Debug/Logging
    rate_parser.add_argument('--debug', action='store_true',
                            help='Enable debug mode (includes unweighted averages and weight details)')
    rate_parser.add_argument('--log-level',
                            choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                            help='Logging level (default: INFO)')
    rate_parser.add_argument('--per-dimension-weights', action='store_true',
                            help='Optimize each dimension independently (disables global weighting mode)')
    rate_parser.add_argument('--export-balanced-csv', action='store_true',
                            help='Export balanced shares and volumes to CSV (without weights or original values)')
    
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
            print(f"✓ Configuration file is valid: {args.config_file}")
            return 0
        else:
            print(f"✗ Configuration validation failed:")
            for error in errors:
                print(f"  {error}")
            return 1
    
    elif args.config_command == 'generate':
        template_path = Path(__file__).parent / 'config' / 'template.yaml'
        output_path = Path(args.output_file)
        
        if not template_path.exists():
            print(f"✗ Template file not found: {template_path}")
            print(f"  Please ensure the config/template.yaml file exists.")
            return 1
        
        if output_path.exists():
            print(f"✗ File already exists: {output_path}")
            print(f"  Please choose a different filename or delete the existing file.")
            return 1
        
        try:
            shutil.copy(template_path, output_path)
            print(f"✓ Configuration template created: {output_path}")
            print(f"  Edit this file to customize your analysis settings.")
            print(f"  Validate with: benchmark config validate {output_path}")
            return 0
        except Exception as e:
            print(f"✗ Failed to create config file: {e}")
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


def run_share_analysis(args: argparse.Namespace, logger: logging.Logger) -> int:
    """Execute share-based dimensional analysis."""
    logger.info("Starting share-based dimensional analysis")
    
    try:
        # Create CLI overrides dictionary
        cli_overrides = {
            'entity_col': args.entity_col,
            'time_col': getattr(args, 'time_col', None),
            'debug': getattr(args, 'debug', False),
            'log_level': getattr(args, 'log_level', None),
            'auto': getattr(args, 'auto', False),
        }
        
        # Initialize ConfigManager with hierarchy
        config = ConfigManager(
            config_file=getattr(args, 'config', None),
            preset=getattr(args, 'preset', None),
            cli_overrides=cli_overrides
        )
        
        # Load data
        data_loader = DataLoader(config)
        df = data_loader.load_data(args)
        logger.info(f"Loaded {len(df)} records with {len(df.columns)} columns")
        
        # Get entity column from config
        entity_col = config.get('input', 'entity_col')
        
        # Determine entity column
        if entity_col in df.columns:
            pass  # Use config value
        elif 'issuer_name' in df.columns:
            entity_col = 'issuer_name'
        elif 'entity_identifier' in df.columns:
            entity_col = 'entity_identifier'
        else:
            logger.error(f"Entity column '{entity_col}' not found in data")
            return 1
        
        # Validate metric column exists (use exact name as specified by user)
        metric_col = args.metric
        if metric_col not in df.columns:
            logger.error(f"Metric column '{metric_col}' not found in data")
            logger.error(f"Available columns: {', '.join(df.columns.tolist())}")
            return 1
        
        logger.info(f"Using entity column: {entity_col}")
        logger.info(f"Analyzing metric: {metric_col}")
        
        # Check for peer-only mode
        if args.entity is None:
            logger.info("Running in PEER-ONLY mode (no target entity specified)")
        else:
            logger.info(f"Target entity: {args.entity}")
        
        # Get configuration values
        opt_config = config.config['optimization']
        analysis_config = config.config['analysis']
        
        # Log configuration source
        if getattr(args, 'preset', None):
            logger.info(f"Using preset: {args.preset}")
        if getattr(args, 'config', None):
            logger.info(f"Using config file: {args.config}")
        
        # Get unique entities and counts for metadata
        unique_entities = df[entity_col].nunique()
        total_records = len(df)
        
        # Initialize analyzer with config values
        debug_mode = config.get('output', 'include_debug_sheets', default=False)
        # Consistent weights is now the default (global weighting mode)
        # Use --per-dimension-weights flag to disable it
        consistent_weights = not getattr(args, 'per_dimension_weights', False)
        time_col = config.get('input', 'time_col')
        
        analyzer = DimensionalAnalyzer(
            target_entity=args.entity,
            entity_column=entity_col,
            bic_percentile=analysis_config.get('best_in_class_percentile', 0.85),
            debug_mode=debug_mode,
            consistent_weights=consistent_weights,
            max_iterations=opt_config['linear_programming']['max_iterations'],
            tolerance=opt_config['linear_programming']['tolerance'],
            max_weight=opt_config['bounds']['max_weight'],
            min_weight=opt_config['bounds']['min_weight'],
            volume_preservation_strength=opt_config['constraints']['volume_preservation'],
            prefer_slacks_first=opt_config['subset_search'].get('prefer_slacks_first', False),
            auto_subset_search=opt_config['subset_search'].get('enabled', True),
            subset_search_max_tests=opt_config['subset_search'].get('max_attempts', 200),
            greedy_subset_search=(opt_config['subset_search'].get('strategy', 'greedy') == 'greedy'),
            trigger_subset_on_slack=opt_config['subset_search'].get('trigger_on_slack', True),
            max_cap_slack=opt_config['subset_search'].get('max_slack_threshold', 0.0),
            time_column=getattr(args, 'time_col', None),
        )
        
        # Determine dimensions
        if args.dimensions:
            dimensions = args.dimensions
            logger.info(f"Using specified dimensions: {dimensions}")
        else:
            # Auto-detect dimensions via DataLoader
            dimensions = data_loader.get_available_dimensions(df)
            logger.info(f"Auto-detected {len(dimensions)} dimensions: {dimensions}")

        # Calculate global weights if consistent_weights mode is enabled (default)
        if consistent_weights:
            analyzer.calculate_global_privacy_weights(df, metric_col, dimensions)

        # Run analysis
        results = {}
        for dim in dimensions:
            try:
                result_df = analyzer.analyze_dimension_share(
                    df=df,
                    dimension_column=dim,
                    metric_col=metric_col
                )
                results[dim] = result_df
            except Exception as e:
                logger.error(f"Error analyzing dimension {dim}: {e}")
                continue

        if not results:
            logger.error("No analysis results generated")
            return 1

        # Collect metadata for report
        metadata = {
            'entity': args.entity if args.entity else 'PEER-ONLY',
            'analysis_type': 'share',
            'metric': metric_col,
            'entity_column': entity_col,
            'total_records': total_records,
            'unique_entities': unique_entities,
            'peer_count': unique_entities if args.entity is None else unique_entities - 1,
            'bic_percentile': config.get('analysis', 'best_in_class_percentile'),
            'dimensions_analyzed': len(results),
            'dimension_names': list(results.keys()),
            'preset': getattr(args, 'preset', None),
            'debug_mode': debug_mode,
            'consistent_weights': consistent_weights,
            'timestamp': datetime.now(),
            # New: capture all input parameters
            'input_csv': getattr(args, 'csv', None),
            'log_level': getattr(args, 'log_level', None),
            'dimensions_mode': 'manual' if bool(getattr(args, 'dimensions', None)) else ('auto' if getattr(args, 'auto', False) else 'manual'),
            'dimensions_requested': getattr(args, 'dimensions', None),
            'entity_col_arg': getattr(args, 'entity_col', None),
            'max_iterations': getattr(args, 'max_iterations', None),
            'tolerance_pp': getattr(args, 'tolerance', None),
            'max_weight': getattr(args, 'max_weight', None),
            'min_weight': getattr(args, 'min_weight', None),
            'volume_preservation_strength': getattr(args, 'volume_preservation', None),
            'rank_preservation_strength': getattr(analyzer, 'rank_preservation_strength', None),
            'prefer_slacks_first': getattr(args, 'prefer_slacks_first', False),
            'auto_subset_search': getattr(args, 'auto_subset_search', False),
            'subset_search_max_tests': getattr(args, 'subset_search_max_tests', 200),
            'trigger_subset_on_slack': getattr(args, 'trigger_subset_on_slack', True),
            'max_cap_slack': getattr(args, 'max_cap_slack', 0.0),
            'analyzer_ref': analyzer,
            'last_lp_stats': getattr(analyzer, 'last_lp_stats', {}),
            'slack_subset_triggered': getattr(analyzer, 'slack_subset_triggered', False),
        }
        
        # Calculate rank preservation strength for metadata (new for v2.0)
        if consistent_weights:
            metadata['global_dimensions_used'] = getattr(analyzer, 'global_dimensions_used', [])
            metadata['removed_dimensions'] = getattr(analyzer, 'removed_dimensions', [])
            metadata['per_dimension_weighted'] = list(getattr(analyzer, 'per_dimension_weights', {}).keys())
            # capture subset search attempts if any
            metadata['subset_search_results'] = getattr(analyzer, 'subset_search_results', [])

        # Get weights data if debug mode
        weights_df = None
        privacy_validation_df = None
        export_csv = getattr(args, 'export_balanced_csv', False)
        
        if debug_mode:
            weights_df = analyzer.get_weights_dataframe()
            if not weights_df.empty:
                logger.info(f"Captured weights data: {len(weights_df)} weight entries")
        
        # Build privacy validation dataframe if debug mode OR CSV export is requested
        if (debug_mode or export_csv) and consistent_weights:
            privacy_validation_df = analyzer.build_privacy_validation_dataframe(df, metric_col, dimensions)
            if not privacy_validation_df.empty:
                logger.info(f"Built privacy validation data: {len(privacy_validation_df)} validation entries")
        
        # Build method breakdown tab (final tab)
        method_breakdown_df = None
        if consistent_weights:
            rows = []
            dims_all = list(dimensions)
            used_dims = set(getattr(analyzer, 'global_dimensions_used', []))
            removed_dims = set(getattr(analyzer, 'removed_dimensions', []))
            per_dim_dict: Dict[str, Dict[str, float]] = getattr(analyzer, 'per_dimension_weights', {})
            weight_methods: Dict[str, str] = getattr(analyzer, 'weight_methods', {})
            global_w = getattr(analyzer, 'global_weights', {})
            peers = set(global_w.keys())
            for d, wmap in per_dim_dict.items():
                peers.update(wmap.keys())
            for dim in dims_all:
                # Use weight_methods if available, otherwise determine from context
                if dim in weight_methods:
                    method = weight_methods[dim]
                elif dim in per_dim_dict:
                    method = 'Per-Dimension-LP'
                elif dim in used_dims:
                    method = 'Global-LP'
                elif dim in removed_dims:
                    method = 'Global weights (dropped in LP)'
                else:
                    method = 'Global weights'
                # rows per peer
                peer_list = sorted(peers)
                for p in peer_list:
                    if dim in per_dim_dict and p in per_dim_dict[dim]:
                        mult = float(per_dim_dict[dim][p])
                    else:
                        mult = float(global_w.get(p, {}).get('multiplier', 1.0))
                    global_weight_pct = global_w.get(p, {}).get('weight', None)
                    rows.append({
                        'Dimension': dim,
                        'Method': method,
                        'Peer': p,
                        'Multiplier': round(mult, 6),
                        'Global_Weight_%': round(global_weight_pct, 4) if isinstance(global_weight_pct, (int, float)) else None
                    })
            if rows:
                method_breakdown_df = pd.DataFrame(rows)
        
        # Generate output
        entity_name = args.entity.replace(' ', '_') if args.entity else 'PEER_ONLY'
        output_file = args.output or f"benchmark_share_{entity_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        generate_excel_report(results, output_file, args.entity or 'PEER-ONLY', 'share', logger, metadata, weights_df, method_breakdown_df, privacy_validation_df)
        
        # Export balanced CSV if requested
        if getattr(args, 'export_balanced_csv', False):
            export_balanced_csv(results, output_file, logger, analysis_type='share')
        
        print(f"\n{'='*80}")
        print("SHARE ANALYSIS COMPLETE")
        print(f"{'='*80}")
        print(f"Entity: {args.entity if args.entity else 'PEER-ONLY MODE'}")
        print(f"Metric: {metric_col}")
        print(f"Dimensions Analyzed: {len(results)}")
        print(f"Report: {output_file}")
        print(f"{'='*80}\n")
        
        return 0
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        return 1


def run_rate_analysis(args: argparse.Namespace, logger: logging.Logger) -> int:
    """Execute rate-based dimensional analysis."""
    logger.info("Starting rate-based dimensional analysis")
    
    try:
        # Validate that at least one rate type is specified
        if not args.approved_col and not args.fraud_col:
            logger.error("At least one of --approved-col or --fraud-col must be specified")
            return 1
        
        # Create CLI overrides dictionary
        cli_overrides = {
            'entity_col': args.entity_col,
            'time_col': getattr(args, 'time_col', None),
            'debug': getattr(args, 'debug', False),
            'log_level': getattr(args, 'log_level', None),
            'auto': getattr(args, 'auto', False),
        }
        
        # Initialize ConfigManager with hierarchy
        config = ConfigManager(
            config_file=getattr(args, 'config', None),
            preset=getattr(args, 'preset', None),
            cli_overrides=cli_overrides
        )
        data_loader = DataLoader(config)
        df = data_loader.load_data(args)
        logger.info(f"Loaded {len(df)} records with {len(df.columns)} columns")
        
        # Determine entity column
        if args.entity_col in df.columns:
            entity_col = args.entity_col
        elif 'issuer_name' in df.columns:
            entity_col = 'issuer_name'
        elif 'entity_identifier' in df.columns:
            entity_col = 'entity_identifier'
        else:
            logger.error(f"Entity column '{args.entity_col}' not found in data")
            return 1
        
        # Validate columns exist (use exact names as specified by user)
        total_col = args.total_col
        if total_col not in df.columns:
            logger.error(f"Total column '{total_col}' not found in data")
            logger.error(f"Available columns: {', '.join(df.columns.tolist())}")
            return 1
        
        rate_types = []
        numerator_cols = {}
        bic_percentiles = {}
        
        # Get BIC percentile from config
        default_bic = config.get('analysis', 'best_in_class_percentile', default=0.85)
        
        if args.approved_col:
            if args.approved_col not in df.columns:
                logger.error(f"Approved column '{args.approved_col}' not found in data")
                logger.error(f"Available columns: {', '.join(df.columns.tolist())}")
                return 1
            rate_types.append('approval')
            numerator_cols['approval'] = args.approved_col
            bic_percentiles['approval'] = default_bic  # Higher is better
            logger.info(f"Approval rate calculation: {args.approved_col} / {total_col}")
        
        if args.fraud_col:
            if args.fraud_col not in df.columns:
                logger.error(f"Fraud column '{args.fraud_col}' not found in data")
                logger.error(f"Available columns: {', '.join(df.columns.tolist())}")
                return 1
            rate_types.append('fraud')
            numerator_cols['fraud'] = args.fraud_col
            bic_percentiles['fraud'] = 0.15  # Lower is better for fraud
            logger.info(f"Fraud rate calculation: {args.fraud_col} / {total_col}")
        
        logger.info(f"Using entity column: {entity_col}")
        logger.info(f"Analyzing rate types: {', '.join(rate_types)}")
        
        # Get unique entities and counts for metadata
        unique_entities = df[entity_col].nunique()
        total_records = len(df)
        
        # Determine dimensions
        debug_mode = config.get('output', 'include_debug_sheets', default=False)
        # Consistent weights is now the default (global weighting mode)
        # Use --per-dimension-weights flag to disable it
        consistent_weights = not getattr(args, 'per_dimension_weights', False)
        
        if args.dimensions:
            dimensions = args.dimensions
            logger.info(f"Using specified dimensions: {dimensions}")
        else:
            dimensions = data_loader.get_available_dimensions(df)
            logger.info(f"Auto-detected {len(dimensions)} dimensions: {dimensions}")
        
        # Get configuration values
        opt_config = config.config['optimization']
        analysis_config = config.config['analysis']
        
        # Initialize analyzer ONCE with first rate type's BIC (we'll override per-dimension)
        # The key insight: weights are based on total_col, not the numerator
        first_rate_type = rate_types[0]
        analyzer = DimensionalAnalyzer(
            target_entity=args.entity,
            entity_column=entity_col,
            bic_percentile=bic_percentiles[first_rate_type],  # Used for first rate type
            debug_mode=debug_mode,
            consistent_weights=consistent_weights,
            max_iterations=opt_config['linear_programming']['max_iterations'],
            tolerance=opt_config['linear_programming']['tolerance'],
            max_weight=opt_config['bounds']['max_weight'],
            min_weight=opt_config['bounds']['min_weight'],
            volume_preservation_strength=opt_config['constraints']['volume_preservation'],
            prefer_slacks_first=opt_config['subset_search'].get('prefer_slacks_first', False),
            auto_subset_search=opt_config['subset_search'].get('enabled', True),
            subset_search_max_tests=opt_config['subset_search'].get('max_attempts', 200),
            greedy_subset_search=(opt_config['subset_search'].get('strategy', 'greedy') == 'greedy'),
            trigger_subset_on_slack=opt_config['subset_search'].get('trigger_on_slack', True),
            max_cap_slack=opt_config['subset_search'].get('max_slack_threshold', 0.0),
            time_column=getattr(args, 'time_col', None),
        )
        
        # Calculate global weights ONCE based on total_col
        # These weights apply to both rate types since they share the same denominator
        if consistent_weights:
            logger.info(f"\nCalculating global privacy-constrained weights based on {total_col}")
            analyzer.calculate_global_privacy_weights(df, total_col, dimensions)
            logger.info("Global weights will be used for all rate types")
        
        # Store results for each rate type
        all_results = {}
        
        # Analyze each rate type using the SAME weights
        for rate_type in rate_types:
            logger.info(f"\n{'='*60}")
            logger.info(f"Analyzing {rate_type.upper()} RATE")
            logger.info(f"{'='*60}")
            
            numerator_col = numerator_cols[rate_type]
            bic_percentile = bic_percentiles[rate_type]
            
            # Update BIC percentile for this rate type (used for BIC calculation, not weights)
            analyzer.bic_percentile = bic_percentile
            logger.info(f"Using {bic_percentile*100}th percentile for BIC")
            
            # Run analysis for this rate type
            results = {}
            for dim in dimensions:
                try:
                    result_df = analyzer.analyze_dimension_rate(
                        df=df,
                        dimension_column=dim,
                        total_col=total_col,
                        numerator_col=numerator_col
                    )
                    results[dim] = result_df
                except Exception as e:
                    logger.error(f"Error analyzing dimension {dim}: {e}")
                    continue
            
            if not results:
                logger.warning(f"No analysis results generated for {rate_type} rate")
                continue
            
            # Store results
            all_results[rate_type] = results
        
        if not all_results:
            logger.error("No analysis results generated for any rate type")
            return 1
        
        # Collect common metadata
        metadata = {
            'entity': args.entity or 'PEER-ONLY',
            'analysis_type': 'multi_rate' if len(all_results) > 1 else f'{rate_types[0]}_rate',
            'rate_types': rate_types,
            'approved_col': getattr(args, 'approved_col', None),
            'fraud_col': getattr(args, 'fraud_col', None),
            'total_col': total_col,
            'entity_column': entity_col,
            'total_records': total_records,
            'unique_entities': unique_entities,
            'peer_count': unique_entities if args.entity is None else (unique_entities - 1),
            'dimensions_analyzed': len(dimensions),
            'dimension_names': dimensions,
            'preset': getattr(args, 'preset', None),
            'debug_mode': debug_mode,
            'consistent_weights': consistent_weights,
            'timestamp': datetime.now(),
            'input_csv': getattr(args, 'csv', None),
            'log_level': getattr(args, 'log_level', None),
            'dimensions_mode': 'manual' if bool(getattr(args, 'dimensions', None)) else ('auto' if getattr(args, 'auto', False) else 'manual'),
            'dimensions_requested': getattr(args, 'dimensions', None),
            'entity_col_arg': getattr(args, 'entity_col', None),
            'max_iterations': getattr(args, 'max_iterations', None),
            'tolerance_pp': getattr(args, 'tolerance', None),
            'max_weight': getattr(args, 'max_weight', None),
            'min_weight': getattr(args, 'min_weight', None),
            'volume_preservation_strength': getattr(args, 'volume_preservation', None),
            'rank_preservation_strength': getattr(analyzer, 'rank_preservation_strength', None),
            'bic_percentiles': bic_percentiles,  # Store both BIC percentiles
        }
        
        # Get weights data if debug mode (same weights for all rate types)
        weights_df = None
        privacy_validation_df = None
        export_csv = getattr(args, 'export_balanced_csv', False)
        
        if debug_mode:
            weights_df = analyzer.get_weights_dataframe()
            if not weights_df.empty:
                logger.info(f"Captured weights data: {len(weights_df)} weight entries")
        
        # Build privacy validation dataframe if debug mode OR CSV export is requested (based on total_col for rate analysis)
        if (debug_mode or export_csv) and consistent_weights:
            privacy_validation_df = analyzer.build_privacy_validation_dataframe(df, total_col, dimensions)
            if not privacy_validation_df.empty:
                logger.info(f"Built privacy validation data: {len(privacy_validation_df)} validation entries")
        
        # Build method breakdown tab (same for all rate types since weights are shared)
        method_breakdown_df = None
        if consistent_weights:
            rows = []
            dims_all = list(dimensions)
            used_dims = set(getattr(analyzer, 'global_dimensions_used', []))
            removed_dims = set(getattr(analyzer, 'removed_dimensions', []))
            per_dim_dict: Dict[str, Dict[str, float]] = getattr(analyzer, 'per_dimension_weights', {})
            weight_methods: Dict[str, str] = getattr(analyzer, 'weight_methods', {})
            global_w = getattr(analyzer, 'global_weights', {})
            peers = set(global_w.keys())
            for d, wmap in per_dim_dict.items():
                peers.update(wmap.keys())
            for dim in dims_all:
                # Use weight_methods if available, otherwise determine from context
                if dim in weight_methods:
                    method = weight_methods[dim]
                elif dim in per_dim_dict:
                    method = 'Per-Dimension-LP'
                elif dim in used_dims:
                    method = 'Global-LP'
                elif dim in removed_dims:
                    method = 'Global weights (dropped in LP)'
                else:
                    method = 'Global weights'
                # rows per peer
                peer_list = sorted(peers)
                for p in peer_list:
                    if dim in per_dim_dict and p in per_dim_dict[dim]:
                        mult = float(per_dim_dict[dim][p])
                    else:
                        mult = float(global_w.get(p, {}).get('multiplier', 1.0))
                    global_weight_pct = global_w.get(p, {}).get('weight', None)
                    rows.append({
                        'Dimension': dim,
                        'Method': method,
                        'Peer': p,
                        'Multiplier': round(mult, 6),
                        'Global_Weight_%': round(global_weight_pct, 4) if isinstance(global_weight_pct, (int, float)) else None
                    })
            if rows:
                method_breakdown_df = pd.DataFrame(rows)
                logger.info(f"Built method breakdown data: {len(method_breakdown_df)} entries")
        
        # Generate single output file
        entity_name = args.entity.replace(' ', '_') if args.entity else 'PEER_ONLY'
        if args.output:
            output_file = args.output
        elif len(all_results) > 1:
            output_file = f"benchmark_multi_rate_{entity_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        else:
            output_file = f"benchmark_{rate_types[0]}_rate_{entity_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        # Generate report with all rate types
        generate_multi_rate_excel_report(all_results, output_file, args.entity or 'PEER-ONLY', logger, metadata, weights_df, numerator_cols, bic_percentiles, privacy_validation_df, method_breakdown_df)
        
        # Export balanced CSV if requested
        if getattr(args, 'export_balanced_csv', False):
            export_balanced_csv(
                None, output_file, logger, 
                analysis_type='rate', 
                all_results=all_results,
                df=df,
                analyzer=analyzer,
                dimensions=dimensions,
                total_col=total_col,
                numerator_cols=numerator_cols
            )
        
        # Print summary
        print(f"\n{'='*80}")
        print(f"RATE ANALYSIS COMPLETE")
        print(f"{'='*80}")
        if args.entity:
            print(f"Entity: {args.entity}")
        else:
            print(f"Mode: PEER-ONLY (No Target Entity)")
        print(f"Rate Types Analyzed: {', '.join([rt.upper() for rt in all_results.keys()])}")
        print(f"Dimensions Analyzed: {len(dimensions)}")
        print(f"Report: {output_file}")
        if len(all_results) > 1:
            print(f"Note: Both rate types use same privacy-constrained weights (based on {args.total_col})")
        print(f"{'='*80}\n")
        
        return 0
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        return 1


def generate_excel_report(
    results: Dict[str, Any],
    output_file: str,
    entity_name: str,
    analysis_type: str,
    logger: logging.Logger,
    metadata: Optional[Dict[str, Any]] = None,
    weights_df: Optional[Any] = None,
    method_breakdown_df: Optional[pd.DataFrame] = None,
    privacy_validation_df: Optional[pd.DataFrame] = None
) -> None:
    """Generate Excel report with dimensional analysis results."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        logger.error("openpyxl not installed. Install with: pip install openpyxl")
        raise
    
    wb = Workbook()
    wb.remove(wb.active)
    
    # Summary sheet with enhanced metadata
    ws_summary = wb.create_sheet("Summary")
    ws_summary.column_dimensions['A'].width = 30
    ws_summary.column_dimensions['B'].width = 60
    
    row = 1
    ws_summary[f'A{row}'] = f"{analysis_type.upper()} ANALYSIS SUMMARY"
    ws_summary[f'A{row}'].font = Font(bold=True, size=14)
    row += 2
    
    # Basic information
    ws_summary[f'A{row}'] = "BASIC INFORMATION"
    ws_summary[f'A{row}'].font = Font(bold=True, size=11)
    row += 1
    
    ws_summary[f'A{row}'] = "Target Entity:"
    ws_summary[f'B{row}'] = entity_name
    row += 1
    
    ws_summary[f'A{row}'] = "Analysis Type:"
    ws_summary[f'B{row}'] = analysis_type
    row += 1
    
    ws_summary[f'A{row}'] = "Timestamp:"
    ws_summary[f'B{row}'] = metadata.get('timestamp', datetime.now()).strftime('%Y-%m-%d %H:%M:%S') if metadata else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    row += 2
    
    # Input parameters
    if metadata:
        ws_summary[f'A{row}'] = "INPUT PARAMETERS"
        ws_summary[f'A{row}'].font = Font(bold=True, size=11)
        row += 1

        def write_input(label: str, value: Any):
            nonlocal row
            ws_summary[f'A{row}'] = label
            ws_summary[f'B{row}'] = value if value is not None else 'N/A'
            row += 1
        
        write_input("CSV Path:", metadata.get('input_csv'))
        write_input("Output File:", output_file)
        write_input("Entity Column (arg):", metadata.get('entity_col_arg', metadata.get('entity_column')))
        # Share/Rate specific inputs
        if metadata.get('analysis_type') == 'share':
            write_input("Metric:", metadata.get('metric'))
        else:
            write_input("Rate Type:", metadata.get('rate_type'))
            write_input("Numerator Column:", metadata.get('numerator_col'))
            write_input("Total Column:", metadata.get('total_col'))
            write_input("Fraud Mode:", metadata.get('fraud_mode'))
        # Dimension selection
        write_input("Dimensions Mode:", metadata.get('dimensions_mode'))
        dims_req = metadata.get('dimensions_requested')
        if dims_req:
            write_input("Dimensions Requested:", ", ".join(map(str, dims_req)))
        # General controls
        write_input("BIC Percentile:", metadata.get('bic_percentile'))
        write_input("Log Level:", metadata.get('log_level'))
        write_input("Preset:", metadata.get('preset'))
        write_input("Debug Mode:", 'ENABLED' if metadata.get('debug_mode') else 'DISABLED')
        write_input("Consistent Weights:", 'ENABLED' if metadata.get('consistent_weights') else 'DISABLED')
        # Weight algorithm parameters
        write_input("Max Iterations:", metadata.get('max_iterations'))
        write_input("Tolerance (pp):", metadata.get('tolerance_pp'))
        write_input("Max Weight:", metadata.get('max_weight'))
        write_input("Min Weight:", metadata.get('min_weight'))
        write_input("Volume Preservation (input):", metadata.get('volume_preservation_strength'))
        write_input("Rank Preservation Strength:", metadata.get('rank_preservation_strength'))
        row += 1
    
    # Data information
    if metadata:
        ws_summary[f'A{row}'] = "DATA INFORMATION"
        ws_summary[f'A{row}'].font = Font(bold=True, size=11)
        row += 1
        
        ws_summary[f'A{row}'] = "Total Records:"
        ws_summary[f'B{row}'] = metadata.get('total_records', 'N/A')
        row += 1
        
        ws_summary[f'A{row}'] = "Entity Column:"
        ws_summary[f'B{row}'] = metadata.get('entity_column', 'N/A')
        row += 1
        
        ws_summary[f'A{row}'] = "Unique Entities in Data:"
        ws_summary[f'B{row}'] = metadata.get('unique_entities', 'N/A')
        row += 1
        
        ws_summary[f'A{row}'] = "Peer Count:"
        ws_summary[f'B{row}'] = metadata.get('peer_count', 'N/A')
        row += 1
        
        if 'metric' in metadata:
            ws_summary[f'A{row}'] = "Metric Analyzed:"
            ws_summary[f'B{row}'] = metadata.get('metric', 'N/A')
            row += 1
        
        if 'rate_type' in metadata:
            ws_summary[f'A{row}'] = "Rate Type:"
            ws_summary[f'B{row}'] = metadata.get('rate_type', 'N/A')
            row += 1
            
            ws_summary[f'A{row}'] = "Numerator Column:"
            ws_summary[f'B{row}'] = metadata.get('numerator_col', 'N/A')
            row += 1
            
            ws_summary[f'A{row}'] = "Total Column:"
            ws_summary[f'B{row}'] = metadata.get('total_col', 'N/A')
            row += 1
        
        row += 1
        
        # Privacy & methodology
        ws_summary[f'A{row}'] = "PRIVACY & METHODOLOGY"
        ws_summary[f'A{row}'].font = Font(bold=True, size=11)
        row += 1
        
        ws_summary[f'A{row}'] = "Privacy Compliance:"
        ws_summary[f'B{row}'] = "Mastercard Control 3.2"
        row += 1
        
        # Determine which privacy rule applies (based on PEER count, not including target)
        peer_count = metadata.get('peer_count', 0)
        if peer_count >= 10:
            privacy_rule = "10/40 Rule (10 peers min, 40% max concentration)"
        elif peer_count >= 7:
            privacy_rule = "7/35 Rule (7 peers min, 35% max concentration)"
        elif peer_count >= 6:
            privacy_rule = "6/30 Rule (6 peers min, 30% max concentration)"
        elif peer_count >= 5:
            privacy_rule = "5/25 Rule (5 peers min, 25% max concentration)"
        elif peer_count >= 4:
            privacy_rule = "4/35 Rule (4 peers min, 35% max concentration)"
        else:
            privacy_rule = f"WARNING: Only {peer_count} peers - insufficient for privacy compliance (minimum 4 required)"
        
        ws_summary[f'A{row}'] = "Applied Privacy Rule:"
        ws_summary[f'B{row}'] = privacy_rule
        row += 1
        
        ws_summary[f'A{row}'] = "BIC Percentile:"
        bic_pct = metadata.get('bic_percentile', 0.85)
        ws_summary[f'B{row}'] = f"{int(bic_pct * 100)}th percentile"
        row += 1
        
        ws_summary[f'A{row}'] = "Balanced Average Method:"
        ws_summary[f'B{row}'] = "Weighted (sum of peer values / sum of peer totals)"
        row += 1
        
        if metadata.get('debug_mode'):
            ws_summary[f'A{row}'] = "Debug Mode:"
            ws_summary[f'B{row}'] = "ENABLED (includes unweighted averages)"
            row += 1
        
        if metadata.get('preset'):
            ws_summary[f'A{row}'] = "Preset Used:"
            ws_summary[f'B{row}'] = metadata.get('preset')
            row += 1
        
        row += 1

    # If Rank Changes available, add a short top-movers section to Summary
    try:
        rank_df = None
        if metadata and 'analyzer_ref' in metadata:
            ana = metadata['analyzer_ref']
            rank_df = getattr(ana, 'rank_changes_df', None)
        if rank_df is not None and hasattr(rank_df, 'empty') and not rank_df.empty:
            ws_summary[f'A{row}'] = "RANK CHANGES (Top Movers)"
            ws_summary[f'A{row}'].font = Font(bold=True, size=11)
            row += 1
            # Top 5 by absolute Delta
            top = rank_df.copy()
            top['Abs_Delta'] = (top['Delta']).abs()
            top = top.sort_values(['Abs_Delta', 'Adjusted_Rank'], ascending=[False, True]).head(5)
            for _, r in top.iterrows():
                ws_summary[f'A{row}'] = str(r['Peer'])
                ws_summary[f'B{row}'] = f"Base→Adj: {int(r['Base_Rank'])}→{int(r['Adjusted_Rank'])} (Δ {int(r['Delta'])})"
                row += 1
            row += 1
    except Exception as e:
        logger.warning(f"Could not add Rank Changes summary: {e}")

    # Dimensions analyzed
    ws_summary[f'A{row}'] = "DIMENSIONS ANALYZED"
    ws_summary[f'A{row}'].font = Font(bold=True, size=11)
    row += 1
    
    ws_summary[f'A{row}'] = "Total Dimensions:"
    ws_summary[f'B{row}'] = len(results)
    row += 1
    row += 1
    
    ws_summary[f'A{row}'] = "Dimension"
    ws_summary[f'B{row}'] = "Categories"
    ws_summary[f'A{row}'].font = Font(bold=True)
    ws_summary[f'B{row}'].font = Font(bold=True)
    ws_summary[f'A{row}'].fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
    ws_summary[f'B{row}'].fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
    
    for dim_name, dim_df in results.items():
        row += 1
        ws_summary[f'A{row}'] = dim_name
        ws_summary[f'B{row}'] = len(dim_df)
    
    # Create dimension sheets
    for dim_name, dim_df in results.items():
        sheet_name = dim_name[:31].replace('/', '_').replace('\\', '_')
        ws = wb.create_sheet(sheet_name)
        
        ws['A1'] = f"Dimension: {dim_name}"
        ws['A1'].font = Font(bold=True, size=12)
        
        # Write headers
        for c_idx, col_name in enumerate(dim_df.columns, start=1):
            cell = ws.cell(row=3, column=c_idx, value=col_name)
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
        
        # Write data
        for r_idx, row_data in enumerate(dim_df.itertuples(index=False), start=4):
            for c_idx, value in enumerate(row_data, start=1):
                ws.cell(row=r_idx, column=c_idx, value=value)
        
        # Auto-size columns for this dimension sheet
        for col in ws.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except Exception:
                    pass
            ws.column_dimensions[column].width = min(max_length + 2, 50)

    # Add Peer Weights tab if provided (outside the dimension loop)
    if weights_df is not None and hasattr(weights_df, 'empty') and not weights_df.empty:
        ws_weights = wb.create_sheet("Peer Weights")
        ws_weights['A1'] = "Peer Weights"
        ws_weights['A1'].font = Font(bold=True, size=12)

        ws_weights['A2'] = "Adjusted_Share = Adjusted_Volume ÷ Sum(All Adjusted_Volumes) [capped at Max_Concentration]"
        ws_weights['A2'].font = Font(italic=True, size=9)
        ws_weights['A3'] = "Peer_Balanced_Avg = Sum(Metric × Adjusted_Share) - ensures no peer > Max_Concentration"
        ws_weights['A3'].font = Font(italic=True, size=9)

        # Write headers
        for c_idx, col_name in enumerate(weights_df.columns, start=1):
            cell = ws_weights.cell(row=5, column=c_idx, value=col_name)
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")

        # Write data
        for r_idx, row_data in enumerate(weights_df.itertuples(index=False), start=6):
            for c_idx, value in enumerate(row_data, start=1):
                ws_weights.cell(row=r_idx, column=c_idx, value=value)

        # Auto-size columns for Peer Weights
        for col in ws_weights.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except Exception:
                    pass
            ws_weights.column_dimensions[column].width = min(max_length + 2, 50)

        logger.info("Added Peer Weights tab with weight calculations and contributions")

    # Add final Weight Methods tab if provided
    if method_breakdown_df is not None and not method_breakdown_df.empty:
        ws_methods = wb.create_sheet("Weight Methods")
        ws_methods['A1'] = "Dimension Weighting Methods"
        ws_methods['A1'].font = Font(bold=True, size=12)
        
        # Write headers
        for c_idx, col_name in enumerate(method_breakdown_df.columns, start=1):
            cell = ws_methods.cell(row=3, column=c_idx, value=col_name)
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
        
        # Write data
        for r_idx, row_data in enumerate(method_breakdown_df.itertuples(index=False), start=4):
            for c_idx, value in enumerate(row_data, start=1):
                ws_methods.cell(row=r_idx, column=c_idx, value=value)
        
        # Auto-size columns
        for col in ws_methods.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except Exception:
                    pass
            ws_methods.column_dimensions[column].width = min(max_length + 2, 60)

    # Subset Search tab if attempts were recorded
    try:
        attempts = metadata.get('subset_search_results') if metadata else None
        if attempts:
            ws_ss = wb.create_sheet("Subset Search")
            ws_ss['A1'] = "Auto Subset Search Attempts"
            ws_ss['A1'].font = Font(bold=True, size=12)
            # Stable columns aligned with analyzer keys
            cols_sorted = ['Attempt', 'Count', 'Dimensions', 'Success', 'Max_Slack', 'Sum_Slack', 'Method', 'Note']
            for c_idx, col_name in enumerate(cols_sorted, start=1):
                cell = ws_ss.cell(row=3, column=c_idx, value=col_name)
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
            for r_idx, d in enumerate(attempts, start=4):
                ws_ss.cell(row=r_idx, column=1, value=d.get('Attempt'))
                ws_ss.cell(row=r_idx, column=2, value=d.get('Count'))
                # Join list of dims into a string for Excel
                dims_val = d.get('Dimensions')
                if isinstance(dims_val, (list, tuple)):
                    dims_val = ", ".join(map(str, dims_val))
                ws_ss.cell(row=r_idx, column=3, value=dims_val)
                ws_ss.cell(row=r_idx, column=4, value=d.get('Success'))
                ws_ss.cell(row=r_idx, column=5, value=d.get('Max_Slack'))
                ws_ss.cell(row=r_idx, column=6, value=d.get('Sum_Slack'))
                ws_ss.cell(row=r_idx, column=7, value=d.get('Method'))
                ws_ss.cell(row=r_idx, column=8, value=d.get('Note'))
            for col in ws_ss.columns:
                max_length = 0
                column = col[0].column_letter
                for cell in col:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except Exception:
                        pass
                ws_ss.column_dimensions[column].width = min(max_length + 2, 80)
    except Exception as e:
        logger.warning(f"Could not add Subset Search sheet: {e}")

    # New: Structural infeasibility diagnostics tabs if available via analyzer metadata
    try:
        structural_detail = None
        structural_summary = None
        if metadata and 'analyzer_ref' in metadata:
            ana = metadata['analyzer_ref']
            structural_detail = getattr(ana, 'structural_detail_df', None)
            structural_summary = getattr(ana, 'structural_summary_df', None)
        # fallback if metadata carries dataframes directly in future
        if structural_summary is not None and hasattr(structural_summary, 'empty') and not structural_summary.empty:
            ws_sum = wb.create_sheet("Structural Summary")
            ws_sum['A1'] = "Structural Infeasibility by Dimension"
            ws_sum['A1'].font = Font(bold=True, size=12)
            df_sum = structural_summary
            for c_idx, col_name in enumerate(df_sum.columns, start=1):
                cell = ws_sum.cell(row=3, column=c_idx, value=col_name)
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
            for r_idx, row_data in enumerate(df_sum.itertuples(index=False), start=4):
                for c_idx, value in enumerate(row_data, start=1):
                    ws_sum.cell(row=r_idx, column=c_idx, value=value)
            for col in ws_sum.columns:
                max_length = 0
                column = col[0].column_letter
                for cell in col:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except Exception:
                        pass
                ws_sum.column_dimensions[column].width = min(max_length + 2, 60)
        if structural_detail is not None and hasattr(structural_detail, 'empty') and not structural_detail.empty:
            ws_det = wb.create_sheet("Structural Detail")
            ws_det['A1'] = "Per-Category Structural Feasibility"
            ws_det['A1'].font = Font(bold=True, size=12)
            df_det = structural_detail
            for c_idx, col_name in enumerate(df_det.columns, start=1):
                cell = ws_det.cell(row=3, column=c_idx, value=col_name)
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
            for r_idx, row_data in enumerate(df_det.itertuples(index=False), start=4):
                for c_idx, value in enumerate(row_data, start=1):
                    ws_det.cell(row=r_idx, column=c_idx, value=value)
            for col in ws_det.columns:
                max_length = 0
                column = col[0].column_letter
                for cell in col:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except Exception:
                        pass
                ws_det.column_dimensions[column].width = min(max_length + 2, 80)
    except Exception as e:
        logger.warning(f"Could not add structural diagnostics sheets: {e}")

    # Rank Changes full sheet (Milestone 2)
    try:
        rank_df = None
        if metadata and 'analyzer_ref' in metadata:
            ana = metadata['analyzer_ref']
            rank_df = getattr(ana, 'rank_changes_df', None)
        if rank_df is not None and hasattr(rank_df, 'empty') and not rank_df.empty:
            ws_rank = wb.create_sheet("Rank Changes")
            ws_rank['A1'] = "Peer Rank Changes (Baseline vs Adjusted)"
            ws_rank['A1'].font = Font(bold=True, size=12)
            for c_idx, col_name in enumerate(rank_df.columns, start=1):
                cell = ws_rank.cell(row=3, column=c_idx, value=col_name)
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
            for r_idx, row_data in enumerate(rank_df.itertuples(index=False), start=4):
                for c_idx, value in enumerate(row_data, start=1):
                    ws_rank.cell(row=r_idx, column=c_idx, value=value)
            for col in ws_rank.columns:
                max_length = 0
                column = col[0].column_letter
                for cell in col:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except Exception:
                        pass
                ws_rank.column_dimensions[column].width = min(max_length + 2, 60)
    except Exception as e:
        logger.warning(f"Could not add Rank Changes sheet: {e}")

    # Privacy Validation sheet (debug mode)
    if privacy_validation_df is not None and not privacy_validation_df.empty:
        try:
            ws_validation = wb.create_sheet("Privacy Validation")
            ws_validation['A1'] = "Privacy Compliance Validation"
            ws_validation['A1'].font = Font(bold=True, size=12)
            ws_validation['A2'] = "Detailed breakdown showing original and balanced volume shares for each dimension-category-(time) combination"
            ws_validation['A2'].font = Font(italic=True)
            for c_idx, col_name in enumerate(privacy_validation_df.columns, start=1):
                cell = ws_validation.cell(row=4, column=c_idx, value=col_name)
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
            for r_idx, row_data in enumerate(privacy_validation_df.itertuples(index=False), start=5):
                for c_idx, value in enumerate(row_data, start=1):
                    cell = ws_validation.cell(row=r_idx, column=c_idx, value=value)
                    # Highlight violations in red
                    if c_idx == privacy_validation_df.columns.get_loc('Compliant') + 1 and value == 'No':
                        cell.fill = PatternFill(start_color="FFE6E6", end_color="FFE6E6", fill_type="solid")
            for col in ws_validation.columns:
                max_length = 0
                column = col[0].column_letter
                for cell in col:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except Exception:
                        pass
                ws_validation.column_dimensions[column].width = min(max_length + 2, 50)
            logger.info("Added Privacy Validation tab")
        except Exception as e:
            logger.warning(f"Could not add Privacy Validation sheet: {e}")

    wb.save(output_file)
    logger.info(f"Report saved to: {output_file}")


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
    method_breakdown_df: Optional[pd.DataFrame] = None
) -> None:
    """Generate Excel report with multiple rate types using shared weights.
    
    For multi-rate analysis, combines both rate types into the same dimension sheets
    with side-by-side columns for easy comparison.
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        logger.error("openpyxl not installed. Install with: pip install openpyxl")
        raise
    
    wb = Workbook()
    wb.remove(wb.active)
    
    rate_types = list(all_results.keys())
    is_multi_rate = len(rate_types) > 1
    debug_mode = metadata.get('debug_mode', False)
    
    # Summary sheet with enhanced metadata
    ws_summary = wb.create_sheet("Summary")
    ws_summary.column_dimensions['A'].width = 30
    ws_summary.column_dimensions['B'].width = 60
    
    row = 1
    if is_multi_rate:
        ws_summary[f'A{row}'] = "MULTI-RATE ANALYSIS SUMMARY"
    else:
        ws_summary[f'A{row}'] = f"{rate_types[0].upper()} RATE ANALYSIS SUMMARY"
    ws_summary[f'A{row}'].font = Font(bold=True, size=14)
    row += 2
    
    # Basic information
    ws_summary[f'A{row}'] = "BASIC INFORMATION"
    ws_summary[f'A{row}'].font = Font(bold=True)
    row += 1
    
    ws_summary[f'A{row}'] = "Entity"
    ws_summary[f'B{row}'] = entity_name
    row += 1
    
    if is_multi_rate:
        ws_summary[f'A{row}'] = "Analysis Type"
        ws_summary[f'B{row}'] = "Multi-Rate (Approval & Fraud)"
        row += 1
        
        ws_summary[f'A{row}'] = "Approval Column"
        ws_summary[f'B{row}'] = numerator_cols.get('approval', 'N/A') if numerator_cols else 'N/A'
        row += 1
        
        ws_summary[f'A{row}'] = "Fraud Column"
        ws_summary[f'B{row}'] = numerator_cols.get('fraud', 'N/A') if numerator_cols else 'N/A'
        row += 1
        
        ws_summary[f'A{row}'] = "Total Column (Shared Denominator)"
        ws_summary[f'B{row}'] = metadata.get('total_col', 'N/A')
        row += 1
        
        ws_summary[f'A{row}'] = "Approval BIC Percentile"
        ws_summary[f'B{row}'] = f"{bic_percentiles.get('approval', 0.85)*100:.0f}th (higher is better)" if bic_percentiles else "85th"
        row += 1
        
        ws_summary[f'A{row}'] = "Fraud BIC Percentile"
        ws_summary[f'B{row}'] = f"{bic_percentiles.get('fraud', 0.15)*100:.0f}th (lower is better)" if bic_percentiles else "15th"
        row += 1
    else:
        rate_type = rate_types[0]
        ws_summary[f'A{row}'] = "Analysis Type"
        ws_summary[f'B{row}'] = f"{rate_type.capitalize()} Rate"
        row += 1
        
        ws_summary[f'A{row}'] = f"{rate_type.capitalize()} Column"
        ws_summary[f'B{row}'] = numerator_cols.get(rate_type, 'N/A') if numerator_cols else 'N/A'
        row += 1
        
        ws_summary[f'A{row}'] = "Total Column"
        ws_summary[f'B{row}'] = metadata.get('total_col', 'N/A')
        row += 1
        
        ws_summary[f'A{row}'] = "BIC Percentile"
        ws_summary[f'B{row}'] = f"{bic_percentiles.get(rate_type, 0.85)*100:.0f}th" if bic_percentiles else "85th"
        row += 1
    
    ws_summary[f'A{row}'] = "Dimensions Analyzed"
    ws_summary[f'B{row}'] = ', '.join(metadata.get('dimension_names', []))
    row += 1
    
    ws_summary[f'A{row}'] = "Total Records"
    ws_summary[f'B{row}'] = metadata.get('total_records', 'N/A')
    row += 1
    
    ws_summary[f'A{row}'] = "Unique Entities"
    ws_summary[f'B{row}'] = metadata.get('unique_entities', 'N/A')
    row += 1
    
    ws_summary[f'A{row}'] = "Peer Count"
    ws_summary[f'B{row}'] = metadata.get('peer_count', 'N/A')
    row += 1
    
    if metadata.get('consistent_weights', False):
        ws_summary[f'A{row}'] = "Weight Strategy"
        if is_multi_rate:
            ws_summary[f'B{row}'] = "Global weights (shared across all dimensions and rate types, based on total_col)"
        else:
            ws_summary[f'B{row}'] = "Global weights (shared across all dimensions)"
        ws_summary[f'B{row}'].font = Font(bold=True, color="0000FF")
        row += 1
    
    ws_summary[f'A{row}'] = "Timestamp"
    ws_summary[f'B{row}'] = str(metadata.get('timestamp', ''))
    row += 2
    
    # Add note about shared weights for multi-rate
    if is_multi_rate:
        ws_summary[f'A{row}'] = "IMPORTANT NOTE"
        ws_summary[f'A{row}'].font = Font(bold=True, color="FF0000")
        row += 1
        ws_summary[f'A{row}'] = "Privacy-constrained weights are calculated ONCE based on the total column."
        row += 1
        ws_summary[f'A{row}'] = "The same weights are applied to both approval and fraud rate calculations,"
        row += 1
        ws_summary[f'A{row}'] = "ensuring consistent privacy compliance across both analyses."
        row += 2
    
    # Create dimension sheets - combine rate types if multi-rate
    if is_multi_rate:
        # Get all dimensions from first rate type (should be same for all)
        dimensions = list(all_results[rate_types[0]].keys())
        
        for dimension in dimensions:
            sheet_name = dimension[:31] if len(dimension) > 31 else dimension
            ws = wb.create_sheet(sheet_name)
            
            # Get results for both rate types
            approval_df = all_results.get('approval', {}).get(dimension)
            fraud_df = all_results.get('fraud', {}).get(dimension)
            
            if approval_df is None or fraud_df is None:
                logger.warning(f"Missing data for dimension {dimension}")
                continue
            
            # Merge the dataframes side by side
            # Start with category column
            combined_df = approval_df[['Category']].copy()
            
            # Add approval rate columns
            for col in approval_df.columns:
                if col != 'Category':
                    if 'Unweighted' in col or 'Original' in col or 'Peer_Count' in col:
                        if debug_mode:
                            combined_df[f'Approval_{col}'] = approval_df[col]
                    else:
                        combined_df[f'Approval_{col}'] = approval_df[col]
            
            # Add fraud rate columns
            for col in fraud_df.columns:
                if col != 'Category':
                    if 'Unweighted' in col or 'Original' in col or 'Peer_Count' in col:
                        if debug_mode:
                            combined_df[f'Fraud_{col}'] = fraud_df[col]
                    else:
                        combined_df[f'Fraud_{col}'] = fraud_df[col]
            
            # Write headers with formatting
            for col_idx, col_name in enumerate(combined_df.columns, start=1):
                cell = ws.cell(row=1, column=col_idx)
                cell.value = col_name
                cell.font = Font(bold=True)
                
                # Color code by rate type
                if 'Approval_' in col_name:
                    cell.fill = PatternFill(start_color="C6E0B4", end_color="C6E0B4", fill_type="solid")  # Green
                elif 'Fraud_' in col_name:
                    cell.fill = PatternFill(start_color="F4B084", end_color="F4B084", fill_type="solid")  # Orange
                else:
                    cell.fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")  # Gray
            
            # Write data
            for row_idx, row_data in enumerate(combined_df.values, start=2):
                for col_idx, value in enumerate(row_data, start=1):
                    ws.cell(row=row_idx, column=col_idx, value=value)
            
            # Auto-size columns
            for col in ws.columns:
                max_length = 0
                column = col[0].column_letter
                for cell in col:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except Exception:
                        pass
                ws.column_dimensions[column].width = min(max_length + 2, 50)
    else:
        # Single rate type - use original logic
        rate_type = rate_types[0]
        results = all_results[rate_type]
        
        for dimension, result_df in results.items():
            sheet_name = dimension[:31] if len(dimension) > 31 else dimension
            ws = wb.create_sheet(sheet_name)
            
            # Write headers
            for col_idx, col_name in enumerate(result_df.columns, start=1):
                cell = ws.cell(row=1, column=col_idx)
                cell.value = col_name
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color="CCCCCC", end_color="CCCCCC", fill_type="solid")
            
            # Write data
            for row_idx, row_data in enumerate(result_df.values, start=2):
                for col_idx, value in enumerate(row_data, start=1):
                    ws.cell(row=row_idx, column=col_idx, value=value)
            
            # Auto-size columns
            for col in ws.columns:
                max_length = 0
                column = col[0].column_letter
                for cell in col:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except Exception:
                        pass
                ws.column_dimensions[column].width = min(max_length + 2, 50)
    
    # Add weights tab if available (same for all rate types)
    if weights_df is not None and not weights_df.empty:
        ws_weights = wb.create_sheet("Peer Weights")
        
        # Write headers
        for col_idx, col_name in enumerate(weights_df.columns, start=1):
            cell = ws_weights.cell(row=1, column=col_idx)
            cell.value = col_name
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="CCCCCC", end_color="CCCCCC", fill_type="solid")
        
        # Write data
        for row_idx, row_data in enumerate(weights_df.values, start=2):
            for col_idx, value in enumerate(row_data, start=1):
                ws_weights.cell(row=row_idx, column=col_idx, value=value)
        
        logger.info("Added Peer Weights tab with weight calculations and contributions")
    
    # Privacy Validation sheet (debug mode - same for all rate types)
    if privacy_validation_df is not None and not privacy_validation_df.empty:
        try:
            ws_validation = wb.create_sheet("Privacy Validation")
            ws_validation['A1'] = "Privacy Compliance Validation"
            ws_validation['A1'].font = Font(bold=True, size=12)
            ws_validation['A2'] = "Detailed breakdown showing original and balanced volume shares for each dimension-category-(time) combination"
            ws_validation['A2'].font = Font(italic=True)
            for c_idx, col_name in enumerate(privacy_validation_df.columns, start=1):
                cell = ws_validation.cell(row=4, column=c_idx, value=col_name)
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
            for r_idx, row_data in enumerate(privacy_validation_df.itertuples(index=False), start=5):
                for c_idx, value in enumerate(row_data, start=1):
                    cell = ws_validation.cell(row=r_idx, column=c_idx, value=value)
                    # Highlight violations in red
                    if c_idx == privacy_validation_df.columns.get_loc('Compliant') + 1 and value == 'No':
                        cell.fill = PatternFill(start_color="FFE6E6", end_color="FFE6E6", fill_type="solid")
            for col in ws_validation.columns:
                max_length = 0
                column = col[0].column_letter
                for cell in col:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except Exception:
                        pass
                ws_validation.column_dimensions[column].width = min(max_length + 2, 50)
            logger.info("Added Privacy Validation tab")
        except Exception as e:
            logger.warning(f"Could not add Privacy Validation sheet: {e}")
    
    # Add final Weight Methods tab if provided (same for all rate types)
    if method_breakdown_df is not None and not method_breakdown_df.empty:
        try:
            ws_methods = wb.create_sheet("Weight Methods")
            ws_methods['A1'] = "Dimension Weighting Methods"
            ws_methods['A1'].font = Font(bold=True, size=12)
            ws_methods['A2'] = "Shows which calculation method was used for each dimension (Global LP, Per-Dimension LP, or Per-Dimension Bayesian)"
            ws_methods['A2'].font = Font(italic=True)
            
            # Write headers
            for c_idx, col_name in enumerate(method_breakdown_df.columns, start=1):
                cell = ws_methods.cell(row=4, column=c_idx, value=col_name)
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
            
            # Write data
            for r_idx, row_data in enumerate(method_breakdown_df.itertuples(index=False), start=5):
                for c_idx, value in enumerate(row_data, start=1):
                    ws_methods.cell(row=r_idx, column=c_idx, value=value)
            
            # Auto-size columns
            for col in ws_methods.columns:
                max_length = 0
                column = col[0].column_letter
                for cell in col:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except Exception:
                        pass
                ws_methods.column_dimensions[column].width = min(max_length + 2, 60)
            
            logger.info("Added Weight Methods tab showing calculation methods per dimension")
        except Exception as e:
            logger.warning(f"Could not add Weight Methods sheet: {e}")
    
    # Save workbook
    wb.save(output_file)
    logger.info(f"Report saved to: {output_file}")


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
    numerator_cols: Optional[Dict[str, str]] = None
) -> None:
    """
    Export balanced totals to CSV in concatenated dimension format.
    
    For rate analysis: exports dimension, category, balanced_total, balanced_approval_total, balanced_fraud_total
    The balanced totals are weighted sums: sum(peer_value * weight) across all peers
    
    For share analysis: exports dimension, category, and balanced volumes
    
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
            if dimension in analyzer.per_dimension_weights and peer in analyzer.per_dimension_weights[dimension]:
                return float(analyzer.per_dimension_weights[dimension][peer])
            if hasattr(analyzer, 'global_weights') and peer in analyzer.global_weights:
                return float(analyzer.global_weights[peer].get('multiplier', 1.0))
            return 1.0
        
        # Check if time column is available
        time_col = analyzer.time_column if hasattr(analyzer, 'time_column') else None
        has_time = time_col and time_col in df.columns
        
        # Process each dimension
        for dimension in dimensions:
            # Aggregate data by entity, dimension category, and optionally time
            group_cols = [entity_col, dimension]
            if has_time:
                group_cols.append(time_col)
            
            agg_dict = {total_col: 'sum'}
            
            # Add numerator columns
            if numerator_cols:
                for num_col in numerator_cols.values():
                    if num_col in df.columns:
                        agg_dict[num_col] = 'sum'
            
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
                    
                    for _, row in cat_df.iterrows():
                        peer = row[entity_col]
                        weight = get_weight(dimension, peer)
                        
                        # Weighted total (denominator)
                        balanced_total += row[total_col] * weight
                        
                        # Weighted approval numerator
                        if numerator_cols and 'approval' in numerator_cols:
                            approval_col = numerator_cols['approval']
                            if approval_col in row.index:
                                balanced_approval += row[approval_col] * weight
                        
                        # Weighted fraud numerator  
                        if numerator_cols and 'fraud' in numerator_cols:
                            fraud_col = numerator_cols['fraud']
                            if fraud_col in row.index:
                                balanced_fraud += row[fraud_col] * weight
                    
                    # Add row to export
                    row_data = {
                        'Dimension': dimension,
                        'Category': category,
                    }
                    
                    # Add time period if applicable
                    if has_time:
                        row_data[time_col] = time_period
                    
                    row_data.update({
                        'Balanced_Total': round(balanced_total, 2),
                        'Balanced_Approval_Total': round(balanced_approval, 2) if balanced_approval > 0 else None,
                        'Balanced_Fraud_Total': round(balanced_fraud, 2) if balanced_fraud > 0 else None
                    })
                    
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
        
    elif analysis_type == 'share' and results:
        # Share analysis: export dimension, category, and balanced metric
        export_rows = []
        
        for dimension, dim_df in results.items():
            if dim_df is None or dim_df.empty:
                continue
            
            categories = dim_df['Category'].unique() if 'Category' in dim_df.columns else []
            
            for category in categories:
                category_rows = dim_df[dim_df['Category'] == category]
                if category_rows.empty:
                    continue
                
                row_data = {
                    'Dimension': dimension,
                    'Category': category,
                    'Balanced_Metric': None
                }
                
                # Get balanced metric value
                if 'Peer_Balanced_Avg' in category_rows.columns:
                    row_data['Balanced_Metric'] = category_rows.iloc[0]['Peer_Balanced_Avg']
                elif 'Peer_Metric' in category_rows.columns:
                    row_data['Balanced_Metric'] = category_rows.iloc[0]['Peer_Metric']
                
                export_rows.append(row_data)
        
        if not export_rows:
            logger.warning("No data to export for share analysis CSV")
            return
        
        # Create DataFrame and export
        export_df = pd.DataFrame(export_rows)
        export_df = export_df.sort_values(['Dimension', 'Category'])
        export_df.to_csv(csv_output, index=False)
        logger.info(f"Balanced share data CSV exported to: {csv_output}")
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
