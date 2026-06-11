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
from core.preset_comparison import run_preset_comparison as _run_shared_preset_comparison
from core.analysis_run import (
    build_dimensional_analyzer,
    build_run_request,
    execute_rate_run,
    execute_run,
    execute_share_run,
    RunBlocked,
)
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
    except Exception:
        return ""


def add_common_run_flags(parser: argparse.ArgumentParser, *, preset_choices: list) -> None:
    """Register CLI flags shared by share and rate analysis subcommands."""
    parser.add_argument('--csv', required=True, help='Path to CSV input file')
    parser.add_argument('--entity', help='Name of the entity to benchmark (omit for peer-only analysis)')
    parser.add_argument('--entity-col', default='issuer_name', help='Entity identifier column name (default: issuer_name)')
    parser.add_argument('--output', '-o', help='Output file path (default: auto-generated)')

    dim_group = parser.add_mutually_exclusive_group()
    dim_group.add_argument('--dimensions', nargs='+', help='Specific dimensions to analyze')
    dim_group.add_argument('--auto', action='store_true', default=None, help='Auto-detect all available dimensions')

    parser.add_argument('--time-col', help='Time column name for time-aware consistency (e.g., ano_mes, year_month)')
    parser.add_argument('--config', help='Configuration file (YAML)')
    parser.add_argument('--preset', choices=preset_choices, help='Preset configuration name')
    parser.add_argument(
        '--compliance-posture',
        choices=['strict', 'best_effort', 'accuracy_first'],
        help='Explicit final compliance posture for this run',
    )
    parser.add_argument(
        '--acknowledge-accuracy-first',
        action='store_true',
        default=None,
        help='Required acknowledgement for accuracy_first runs',
    )
    parser.add_argument('--debug', action='store_true', default=None, help='Enable debug mode (includes unweighted averages and weight details)')
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], help='Logging level (default: INFO)')
    parser.add_argument(
        '--per-dimension-weights',
        action='store_true',
        default=None,
        help='Optimize each dimension independently (disables global weighting mode)',
    )
    parser.add_argument('--export-balanced-csv', action='store_true', help='Export balanced metrics to CSV')
    parser.add_argument('--audit-package', action='store_true', default=None, help='Create an audit package zip with reports, CSV, audit log, and config snapshot')
    parser.add_argument(
        '--lean',
        action='store_true',
        default=None,
        help='Minimize memory use for large CSVs by projecting columns and disabling optional heavy artifacts',
    )
    parser.add_argument('--compare-presets', action='store_true', default=None, help='Compare all presets and report impact for each')
    parser.add_argument('--analyze-impact', action='store_true', default=None, help='Include impact details and summary sheets in output')
    parser.add_argument('--analyze-distortion', action='store_true', default=None, help='Alias for --analyze-impact (deprecated)')
    parser.add_argument(
        '--validate-input',
        action='store_true',
        default=None,
        dest='validate_input',
        help='Enable input data validation before analysis (default: enabled)',
    )
    parser.add_argument('--no-validate-input', action='store_false', dest='validate_input', help='Disable input data validation')
    parser.add_argument(
        '--validate-export',
        action='store_true',
        default=None,
        dest='validate_export',
        help='Cross-validate balanced CSV against the workbook on export (default: enabled)',
    )
    parser.add_argument(
        '--no-validate-export',
        action='store_false',
        dest='validate_export',
        help='Disable balanced CSV cross-validation on export',
    )
    parser.add_argument(
        '--output-format',
        choices=['analysis', 'publication', 'both'],
        default=None,
        help='Output format: analysis (default), publication, or both',
    )
    parser.add_argument(
        '--publication-format',
        action='store_const',
        const='publication',
        dest='output_format',
        help='Convenience alias for --output-format=publication',
    )
    parser.add_argument('--include-calculated', action='store_true', default=None, help='Include calculated metrics in balanced CSV export')
    parser.add_argument('--auto-subset-search', action='store_true', default=None, help='Automatically search for largest feasible global dimension subset')
    parser.add_argument('--subset-search-max-tests', type=int, help='Maximum attempts during subset search')
    parser.add_argument('--trigger-subset-on-slack', action='store_true', default=None, help='Trigger subset search if LP uses slack')
    parser.add_argument('--max-cap-slack', type=float, help='Slack sum threshold to trigger subset search')
    parser.add_argument(
        '--privacy-basis',
        choices=['clearing_spend', 'transaction_count', 'transaction_amount'],
        help='Basis used for Control 3 concentration checks; fraud/chargeback issuer benchmarking requires clearing_spend',
    )
    parser.add_argument(
        '--contains-digital-wallet-metrics',
        action='store_true',
        default=None,
        help='Declare that the output contains digital wallet metrics and therefore requires Privacy review',
    )
    parser.add_argument(
        '--digital-wallet-review-approved',
        action='store_true',
        default=None,
        help='Declare that required Privacy review/approval has been obtained for digital wallet metrics',
    )
    parser.add_argument(
        '--contains-top-merchant-output',
        action='store_true',
        default=None,
        help='Declare that the output would include a top-merchant list; Control 3 blocks this deliverable',
    )
    parser.add_argument(
        '--dual-entity-axis',
        action='store_true',
        default=None,
        help='Declare that the benchmark involves two protected entity axes and requires Privacy review',
    )
    parser.add_argument(
        '--dual-entity-axis-review-approved',
        action='store_true',
        default=None,
        help='Declare that required Privacy review/approval has been obtained for dual entity axis benchmarking',
    )
    parser.add_argument(
        '--recurring-deliverable',
        action='store_true',
        default=None,
        help='Declare that this is a recurring deliverable requiring re-check evidence',
    )
    parser.add_argument(
        '--last-privacy-recheck-date',
        help='Date of the latest privacy compliance re-check in YYYY-MM-DD format',
    )
    parser.add_argument(
        '--peer-group-altered',
        action='store_true',
        default=None,
        help='Declare that the peer group changed since the last recurring deliverable',
    )


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
    add_common_run_flags(share_parser, preset_choices=preset_choices)
    share_parser.add_argument('--metric', required=True,
                             help='Metric column name to analyze (e.g., txn_cnt, tpv, transaction_count, transaction_amount)')
    share_parser.add_argument('--secondary-metrics', nargs='+',
                             help='Secondary metric columns to analyze using weights derived from the primary metric (space-separated list)')

    # ========================================================================
    # RATE ANALYSIS COMMAND
    # ========================================================================
    rate_parser = subparsers.add_parser(
        'rate',
        help='Rate-based dimensional analysis',
        description='Analyze approval rates or fraud rates across dimensions'
    )
    add_common_run_flags(rate_parser, preset_choices=preset_choices)
    rate_parser.add_argument('--total-col', required=True,
                            help='Total transactions column (e.g., txn_cnt)')
    rate_parser.add_argument('--secondary-metrics', nargs='+',
                            help='Secondary metric columns (e.g., txn_count) to analyze using weights derived from the total column (space-separated list)')
    rate_parser.add_argument('--approved-col',
                            help='Approved transactions column (for approval rate)')
    rate_parser.add_argument('--fraud-col',
                            help='Fraud transactions column (for fraud rate)')
    rate_parser.add_argument('--fraud-in-bps', action='store_true', default=None,
                            dest='fraud_in_bps',
                            help='Convert fraud rates to basis points in publication format (default: enabled)')
    rate_parser.add_argument('--no-fraud-in-bps', action='store_false', dest='fraud_in_bps',
                            help='Keep fraud rates as percentages in publication format')

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
            print("[FAIL] Configuration validation failed:")
            for error in errors:
                print(f"  {error}")
            return 1
    
    elif args.config_command == 'generate':
        template_path = Path(__file__).parent / 'config' / 'template.yaml'
        output_path = Path(args.output_file)
        
        if not template_path.exists():
            print(f"[FAIL] Template file not found: {template_path}")
            print("  Please ensure the config/template.yaml file exists.")
            return 1
        
        if output_path.exists():
            print(f"[FAIL] File already exists: {output_path}")
            print("  Please choose a different filename or delete the existing file.")
            return 1
        
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(template_path, output_path)
            print(f"[OK] Configuration template created: {output_path}")
            print("  Edit this file to customize your analysis settings.")
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
    print("Version: 3.0.0")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Platform: {platform.system()} {platform.release()}")


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
        analyzer_factory=build_dimensional_analyzer,
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
