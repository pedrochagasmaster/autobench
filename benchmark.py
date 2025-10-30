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

# Import core modules
from core.dimensional_analyzer import DimensionalAnalyzer
from core.data_loader import DataLoader
from utils.config_manager import ConfigManager
from utils.logger import setup_logging


def get_presets_help() -> str:
    """Generate help text for available presets."""
    try:
        with open('presets.json', 'r') as f:
            presets = json.load(f).get('presets', {})
            if not presets:
                return ""
            
            help_text = "\nAVAILABLE PRESETS:\n"
            for name, config in presets.items():
                help_text += f"  {name:15s}: {config.get('description', 'No description')}\n"
            return help_text
    except:
        return ""


def create_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    
    parser = argparse.ArgumentParser(
        prog='benchmark',
        description='Privacy-Compliant Dimensional Benchmarking Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
EXAMPLES:
  # Share analysis (transaction count distribution)
  python benchmark.py share --csv data.csv --entity "BANCO SANTANDER" --metric txn_cnt

  # Share analysis (transaction amount distribution)
  python benchmark.py share --csv data.csv --entity "BANCO SANTANDER" --metric tpv

  # Rate analysis (approval rates by dimension)
  python benchmark.py rate --csv data.csv --entity "BANCO SANTANDER" \\
    --total-col txn_cnt --approved-col app_cnt

  # Fraud rate analysis
  python benchmark.py rate --csv data.csv --entity "BANCO SANTANDER" \\
    --total-col app_cnt --fraud-col fraud_cnt --fraud-mode

  # Auto-detect all dimensions
  python benchmark.py share --csv data.csv --entity "BANCO SANTANDER" --metric txn_cnt --auto

  # Specify dimensions manually
  python benchmark.py share --csv data.csv --entity "BANCO SANTANDER" \\
    --metric txn_cnt --dimensions flag_domestic cp_cnp tipo_wallet

  # Use preset and custom output
  python benchmark.py share --csv data.csv --entity "BANCO SANTANDER" \\
    --metric txn_cnt --preset conservative --output my_analysis.xlsx

  # List available presets
  python benchmark.py presets

{get_presets_help()}
        """
    )
    
    # Create subparsers for different commands
    subparsers = parser.add_subparsers(dest='command', help='Analysis type')
    
    # Get available preset choices
    def get_preset_choices():
        try:
            with open('presets.json', 'r') as f:
                return list(json.load(f).get('presets', {}).keys())
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
    share_parser.add_argument('--entity', required=True,
                             help='Name of the entity to benchmark')
    share_parser.add_argument('--metric', required=True,
                             choices=['txn_cnt', 'tpv', 'transaction_count', 'transaction_amount'],
                             help='Metric to analyze (txn_cnt or tpv)')
    
    # Dimension selection
    dim_group = share_parser.add_mutually_exclusive_group()
    dim_group.add_argument('--dimensions', nargs='+',
                          help='Specific dimensions to analyze (e.g., flag_domestic cp_cnp)')
    dim_group.add_argument('--auto', action='store_true',
                          help='Auto-detect all available dimensions')
    
    # Optional arguments
    share_parser.add_argument('--entity-col', default='issuer_name',
                             help='Entity identifier column name (default: issuer_name)')
    share_parser.add_argument('--output', '-o',
                             help='Output file path (default: auto-generated)')
    share_parser.add_argument('--bic-percentile', type=float, default=0.85,
                             help='Best-in-class percentile (default: 0.85)')
    share_parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                             default='INFO', help='Logging level')
    share_parser.add_argument('--preset', choices=preset_choices,
                             help='Use preset configuration')
    share_parser.add_argument('--debug', action='store_true',
                             help='Enable debug mode (includes unweighted averages and weight details)')
    share_parser.add_argument('--consistent-weights', action='store_true',
                             help='Use same privacy-constrained weights across all dimensions (global weighting)')
    
    # Weight algorithm parameters
    share_parser.add_argument('--max-iterations', type=int, default=1000,
                             help='Maximum iterations for weight convergence (default: 1000)')
    share_parser.add_argument('--tolerance', type=float, default=1.0,
                             help='Tolerance for privacy violations in percentage points (default: 1.0)')
    share_parser.add_argument('--max-weight', type=float, default=10.0,
                             help='Maximum weight multiplier allowed (default: 10.0)')
    share_parser.add_argument('--min-weight', type=float, default=0.01,
                             help='Minimum weight multiplier allowed (default: 0.01)')
    share_parser.add_argument('--volume-preservation', type=float, default=0.5,
                             help='Volume preservation strength 0.0-1.0 (default: 0.5)')
    
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
    rate_parser.add_argument('--entity', required=True,
                            help='Name of the entity to benchmark')
    rate_parser.add_argument('--total-col', required=True,
                            help='Total transactions column (e.g., txn_cnt)')
    
    # Rate type selection
    rate_type = rate_parser.add_mutually_exclusive_group(required=True)
    rate_type.add_argument('--approved-col',
                          help='Approved transactions column (for approval rate)')
    rate_type.add_argument('--fraud-col',
                          help='Fraud transactions column (for fraud rate)')
    
    # Fraud mode flag
    rate_parser.add_argument('--fraud-mode', action='store_true',
                            help='Calculate fraud rates (use 15th percentile for BIC)')
    
    # Dimension selection
    rate_dim_group = rate_parser.add_mutually_exclusive_group()
    rate_dim_group.add_argument('--dimensions', nargs='+',
                               help='Specific dimensions to analyze')
    rate_dim_group.add_argument('--auto', action='store_true',
                               help='Auto-detect all available dimensions')
    
    # Optional arguments
    rate_parser.add_argument('--entity-col', default='issuer_name',
                            help='Entity identifier column name (default: issuer_name)')
    rate_parser.add_argument('--output', '-o',
                            help='Output file path (default: auto-generated)')
    rate_parser.add_argument('--bic-percentile', type=float, default=0.85,
                            help='BIC percentile for approval rate (default: 0.85, use 0.15 for fraud)')
    rate_parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                            default='INFO', help='Logging level')
    rate_parser.add_argument('--preset', choices=preset_choices,
                            help='Use preset configuration')
    rate_parser.add_argument('--debug', action='store_true',
                            help='Enable debug mode (includes unweighted averages and weight details)')
    rate_parser.add_argument('--consistent-weights', action='store_true',
                            help='Use same privacy-constrained weights across all dimensions (global weighting)')
    
    # ========================================================================
    # PRESETS COMMAND
    # ========================================================================
    presets_parser = subparsers.add_parser(
        'presets',
        help='List available preset configurations'
    )
    
    return parser


def apply_preset(args: argparse.Namespace) -> None:
    """Apply preset configuration to arguments."""
    if not hasattr(args, 'preset') or not args.preset:
        return
    
    try:
        with open('presets.json', 'r') as f:
            presets = json.load(f).get('presets', {})
            
        if args.preset not in presets:
            print(f"Warning: Preset '{args.preset}' not found")
            return
        
        preset = presets[args.preset]
        print(f"Applying preset: {args.preset} - {preset.get('description', '')}")
        
        # Apply preset values if not already specified
        if hasattr(args, 'bic_percentile') and args.bic_percentile == 0.85:
            if 'bic_percentile' in preset:
                args.bic_percentile = preset['bic_percentile']
                
    except Exception as e:
        print(f"Warning: Could not load preset: {e}")


def list_presets() -> None:
    """Display available presets."""
    try:
        with open('presets.json', 'r') as f:
            presets = json.load(f).get('presets', {})
        
        if not presets:
            print("No presets found. Create a presets.json file.")
            return
        
        print("\n" + "="*80)
        print("AVAILABLE PRESET CONFIGURATIONS")
        print("="*80)
        
        for name, config in presets.items():
            print(f"\n{name.upper()}:")
            print(f"  Description: {config.get('description', 'N/A')}")
            if 'bic_percentile' in config:
                print(f"  BIC Percentile: {config['bic_percentile']}")
            if 'participants' in config:
                print(f"  Min Participants: {config['participants']}")
            if 'max_percent' in config:
                print(f"  Max Concentration: {config['max_percent']}%")
        
        print("\n" + "="*80)
        
    except FileNotFoundError:
        print("No presets.json file found.")
    except Exception as e:
        print(f"Error loading presets: {e}")


def run_share_analysis(args: argparse.Namespace, logger: logging.Logger) -> int:
    """Execute share-based dimensional analysis."""
    logger.info("Starting share-based dimensional analysis")
    
    try:
        # Load data
        config = ConfigManager()
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
        
        # Map metric name - the data_loader already standardizes column names
        # So we need to use the standardized names
        metric_col = args.metric
        # if metric_col == 'txn_cnt':
        #     metric_col = 'transaction_count'
        # elif metric_col == 'tpv':
        #     metric_col = 'transaction_amount'
        # If user already specified transaction_count or transaction_amount, keep it as is
        
        # Validate metric column exists
        if metric_col not in df.columns:
            logger.error(f"Metric column '{metric_col}' not found in data")
            logger.error(f"Available columns: {', '.join(df.columns.tolist())}")
            return 1
        
        logger.info(f"Using entity column: {entity_col}")
        logger.info(f"Analyzing metric: {metric_col}")
        
        # Get unique entities and counts for metadata
        unique_entities = df[entity_col].nunique()
        total_records = len(df)
        
        # Initialize analyzer
        debug_mode = getattr(args, 'debug', False)
        consistent_weights = getattr(args, 'consistent_weights', False)
        analyzer = DimensionalAnalyzer(
            target_entity=args.entity,
            entity_column=entity_col,
            bic_percentile=args.bic_percentile,
            debug_mode=debug_mode,
            consistent_weights=consistent_weights,
            max_iterations=getattr(args, 'max_iterations', 1000),
            tolerance=getattr(args, 'tolerance', 1.0),
            max_weight=getattr(args, 'max_weight', 10.0),
            min_weight=getattr(args, 'min_weight', 0.01),
            volume_preservation_strength=getattr(args, 'volume_preservation', 0.5)
        )
        
        # Determine dimensions
        if args.dimensions:
            dimensions = args.dimensions
            logger.info(f"Using specified dimensions: {dimensions}")
        else:
            dimensions = analyzer.identify_dimensional_columns(df)
            logger.info(f"Auto-detected {len(dimensions)} dimensions: {dimensions}")
        
        # Calculate global weights if consistent_weights mode is enabled
        # This must be done BEFORE analyzing dimensions to ensure weights work for ALL categories
        if args.consistent_weights:
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
            'entity': args.entity,
            'analysis_type': 'share',
            'metric': metric_col,
            'entity_column': entity_col,
            'total_records': total_records,
            'unique_entities': unique_entities,
            'peer_count': unique_entities - 1,
            'bic_percentile': args.bic_percentile,
            'dimensions_analyzed': len(results),
            'dimension_names': list(results.keys()),
            'preset': getattr(args, 'preset', None),
            'debug_mode': debug_mode,
            'timestamp': datetime.now()
        }
        
        # Get weights data if debug mode
        weights_df = None
        if debug_mode:
            weights_df = analyzer.get_weights_dataframe()
            if not weights_df.empty:
                logger.info(f"Captured weights data: {len(weights_df)} weight entries")
        
        # Generate output
        output_file = args.output or f"benchmark_share_{args.entity.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        generate_excel_report(results, output_file, args.entity, 'share', logger, metadata, weights_df)
        
        print(f"\n{'='*80}")
        print("SHARE ANALYSIS COMPLETE")
        print(f"{'='*80}")
        print(f"Entity: {args.entity}")
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
        # Load data
        config = ConfigManager()
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
        
        # Determine numerator column (approved or fraud)
        numerator_col = args.approved_col or args.fraud_col
        if numerator_col not in df.columns:
            logger.error(f"Column '{numerator_col}' not found in data")
            return 1
        
        if args.total_col not in df.columns:
            logger.error(f"Total column '{args.total_col}' not found in data")
            return 1
        
        # Set BIC percentile based on fraud mode
        if args.fraud_mode:
            bic_percentile = 0.15  # Lower is better for fraud
            logger.info("Fraud rate mode: Using 15th percentile for BIC")
        else:
            bic_percentile = args.bic_percentile
            logger.info(f"Approval rate mode: Using {bic_percentile*100}th percentile for BIC")
        
        logger.info(f"Using entity column: {entity_col}")
        logger.info(f"Rate calculation: {numerator_col} / {args.total_col}")
        
        # Get unique entities and counts for metadata
        unique_entities = df[entity_col].nunique()
        total_records = len(df)
        
        # Initialize analyzer
        # Initialize analyzer
        debug_mode = getattr(args, 'debug', False)
        consistent_weights = getattr(args, 'consistent_weights', False)
        analyzer = DimensionalAnalyzer(
            target_entity=args.entity,
            entity_column=entity_col,
            bic_percentile=bic_percentile,
            debug_mode=debug_mode,
            consistent_weights=consistent_weights,
            max_iterations=getattr(args, 'max_iterations', 1000),
            tolerance=getattr(args, 'tolerance', 1.0),
            max_weight=getattr(args, 'max_weight', 10.0),
            min_weight=getattr(args, 'min_weight', 0.01),
            volume_preservation_strength=getattr(args, 'volume_preservation', 0.5)
        )
        
        # Determine dimensions
        if args.dimensions:
            dimensions = args.dimensions
            logger.info(f"Using specified dimensions: {dimensions}")
        else:
            dimensions = analyzer.identify_dimensional_columns(df)
            logger.info(f"Auto-detected {len(dimensions)} dimensions: {dimensions}")
        
        # Calculate global weights if consistent_weights mode is enabled
        # This must be done BEFORE analyzing dimensions to ensure weights work for ALL categories
        if consistent_weights:
            analyzer.calculate_global_privacy_weights(df, args.total_col, dimensions)
        
        # Run analysis
        results = {}
        for dim in dimensions:
            try:
                result_df = analyzer.analyze_dimension_rate(
                    df=df,
                    dimension_column=dim,
                    total_col=args.total_col,
                    numerator_col=numerator_col
                )
                results[dim] = result_df
            except Exception as e:
                logger.error(f"Error analyzing dimension {dim}: {e}")
                continue
        
        if not results:
            logger.error("No analysis results generated")
            return 1
        
        # Collect metadata for report
        rate_type = 'fraud' if args.fraud_mode else 'approval'
        metadata = {
            'entity': args.entity,
            'analysis_type': f'{rate_type}_rate',
            'rate_type': rate_type,
            'numerator_col': numerator_col,
            'total_col': args.total_col,
            'entity_column': entity_col,
            'total_records': total_records,
            'unique_entities': unique_entities,
            'peer_count': unique_entities - 1,
            'bic_percentile': bic_percentile,
            'dimensions_analyzed': len(results),
            'dimension_names': list(results.keys()),
            'preset': getattr(args, 'preset', None),
            'debug_mode': debug_mode,
            'timestamp': datetime.now()
        }
        
        # Get weights data if debug mode
        weights_df = None
        if debug_mode:
            weights_df = analyzer.get_weights_dataframe()
            if not weights_df.empty:
                logger.info(f"Captured weights data: {len(weights_df)} weight entries")
        
        # Generate output
        output_file = args.output or f"benchmark_{rate_type}_rate_{args.entity.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        generate_excel_report(results, output_file, args.entity, f'{rate_type}_rate', logger, metadata, weights_df)
        
        print(f"\n{'='*80}")
        print(f"{rate_type.upper()} RATE ANALYSIS COMPLETE")
        print(f"{'='*80}")
        print(f"Entity: {args.entity}")
        print(f"Rate Type: {rate_type}")
        print(f"Dimensions Analyzed: {len(results)}")
        print(f"Report: {output_file}")
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
    weights_df: Optional[Any] = None
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
    ws_summary.column_dimensions['B'].width = 40
    
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
    
    wb.save(output_file)
    logger.info(f"Report saved to: {output_file}")


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    
    if len(sys.argv) == 1:
        parser.print_help()
        return 0
    
    args = parser.parse_args()
    
    # Handle presets command
    if args.command == 'presets':
        list_presets()
        return 0
    
    if not args.command:
        parser.print_help()
        return 0
    
    # Setup logging
    logger = setup_logging(args.log_level, f"benchmark_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    
    # Apply preset if specified
    apply_preset(args)
    
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
