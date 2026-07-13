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
import platform
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

import pandas as pd

# Import core modules
from core.control3_policy import remediation_hint
from core.preset_comparison import run_preset_comparison as _run_shared_preset_comparison
from core.analysis_run import (
    build_dimensional_analyzer,
    build_run_request,
    execute_rate_run,
    execute_share_run,
    RunBlocked,
)
from core.telemetry.constants import DEFAULT_DAYS
from core.telemetry.identity import validate_username
from core.telemetry.reader import TelemetryReader
from core.telemetry.render import format_summary, format_who, sanitize_terminal
from core.telemetry import end_session, start_session
from utils.logger import setup_logging
from utils.preset_manager import PresetManager
from utils.validators import validate_config_file

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_STRICT_NON_COMPLIANT = 2

_GENERIC_VALIDATION_ABORT = "Analysis aborted due to validation errors"


def get_presets_help() -> str:
    """Generate help text for available presets."""
    try:
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
    available_presets = ', '.join(preset_choices) if preset_choices else 'none found'
    parser.add_argument('--preset', help=f'Preset configuration name (available: {available_presets})')
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
        '--report-format',
        choices=['xlsx', 'json'],
        default=None,
        help='xlsx (default) or json — json additionally writes a machine-readable <output>.json next to the workbook',
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
  python benchmark.py share --csv data.csv --entity "BANCO SANTANDER" --metric txn_cnt --preset balanced_default

  # Share analysis with custom config
  python benchmark.py share --csv data.csv --entity "BANCO SANTANDER" --metric txn_cnt --config my_config.yaml

  # Rate analysis (approval rates)
  python benchmark.py rate --csv data.csv --entity "BANCO SANTANDER" \\
    --total-col txn_cnt --approved-col app_cnt --preset compliance_strict

  # List available presets
  python benchmark.py config list

  # Show preset details
  python benchmark.py config show compliance_strict

  # Generate config template
  python benchmark.py config generate my_config.yaml

  # Validate config file
  python benchmark.py config validate my_config.yaml

  # Local telemetry reports (default last 30 days)
  python benchmark.py telemetry who
  python benchmark.py telemetry summary --user alice

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
            return PresetManager().list_presets()
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

    # ========================================================================
    # TELEMETRY REPORT COMMANDS
    # ========================================================================
    telemetry_parser = subparsers.add_parser(
        'telemetry',
        help='Report local offline telemetry (who / summary)',
    )
    telemetry_subparsers = telemetry_parser.add_subparsers(
        dest='telemetry_command',
        help='Telemetry report to show',
    )

    who_parser = telemetry_subparsers.add_parser(
        'who',
        help='List users with session and completion counts',
    )
    who_parser.add_argument(
        '--days',
        type=int,
        default=DEFAULT_DAYS,
        help=f'Include events from the last N days (default: {DEFAULT_DAYS})',
    )
    who_parser.add_argument(
        '--dir',
        default=None,
        help='Telemetry parent directory whose direct child is users/',
    )

    summary_parser = telemetry_subparsers.add_parser(
        'summary',
        help='Summarize surfaces, actions, and outcomes',
    )
    summary_parser.add_argument(
        '--days',
        type=int,
        default=DEFAULT_DAYS,
        help=f'Include events from the last N days (default: {DEFAULT_DAYS})',
    )
    summary_parser.add_argument(
        '--dir',
        default=None,
        help='Telemetry parent directory whose direct child is users/',
    )
    summary_parser.add_argument(
        '--user',
        default=None,
        help='Limit summary to one username',
    )
    
    return parser


def _telemetry_warn(message: str) -> None:
    """Print a visible, terminal-safe schema warning to stderr."""
    print(f"WARNING: {sanitize_terminal(str(message))}", file=sys.stderr)


def handle_telemetry_command(args: argparse.Namespace) -> int:
    """Handle telemetry who/summary without starting writers or sessions."""
    command = getattr(args, 'telemetry_command', None)
    if command not in ('who', 'summary'):
        print("Usage: benchmark telemetry {who|summary}")
        print("  who                     List users, sessions, last seen, completions")
        print("  summary                 Summarize surfaces, actions, and outcomes")
        return EXIT_FAILURE

    days = getattr(args, 'days', DEFAULT_DAYS)
    if isinstance(days, bool) or not isinstance(days, int) or days < 0:
        print("Error: --days must be a nonnegative integer.", file=sys.stderr)
        return EXIT_FAILURE

    shared_dir: Optional[Path] = None
    dir_arg = getattr(args, 'dir', None)
    if dir_arg is not None:
        path = Path(dir_arg)
        try:
            if path.exists() and not path.is_dir():
                print(
                    "Error: --dir must name a directory (parent of users/).",
                    file=sys.stderr,
                )
                return EXIT_FAILURE
        except OSError:
            print("Error: --dir is not usable.", file=sys.stderr)
            return EXIT_FAILURE
        shared_dir = path

    user = getattr(args, 'user', None)
    if user is not None:
        try:
            user = validate_username(user)
        except ValueError:
            print("Error: invalid username.", file=sys.stderr)
            return EXIT_FAILURE

    try:
        reader = TelemetryReader(shared_dir=shared_dir, warn=_telemetry_warn)
        if command == 'who':
            sys.stdout.write(format_who(reader.who(days=days)))
        else:
            sys.stdout.write(format_summary(reader.summary(days=days, user=user)))
        return EXIT_OK
    except (ValueError, OSError, KeyError):
        print("Error: unable to read telemetry.", file=sys.stderr)
        return EXIT_FAILURE


def handle_config_command(args: argparse.Namespace) -> int:
    """Handle config subcommands.
    
    Args:
        args: Parsed command-line arguments
        
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    preset_mgr = PresetManager()
    
    if args.config_command == 'list':
        print(preset_mgr.format_preset_list())
        return 0
    
    elif args.config_command == 'show':
        print(preset_mgr.format_preset_detail(args.preset_name))
        if args.preset_name not in preset_mgr.list_presets():
            return 1
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


def _validate_preset_arg(args: argparse.Namespace) -> Optional[str]:
    """Validate the ``--preset`` argument against the available presets.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments.

    Returns
    -------
    str or None
        A user-facing error message when ``--preset`` names an unknown preset,
        otherwise ``None``. This mirrors the ``ValueError`` raised by
        ``ConfigManager`` so the CLI and Python API report unknown presets
        consistently, both listing the available presets.
    """
    preset = getattr(args, 'preset', None)
    if not preset:
        return None
    available = PresetManager().list_presets()
    if preset not in available:
        listing = ', '.join(available) if available else 'none found'
        return f"Error: preset '{preset}' not found. Available presets: {listing}"
    return None


def print_version() -> None:
    """Print version information."""
    print("Privacy-Compliant Peer Benchmark Tool")
    print("Version: 3.0.0")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Platform: {platform.system()} {platform.release()}")


def _resolve_compliance_fields(artifacts) -> tuple[Optional[str], Optional[str]]:
    """Read compliance verdict and posture from run artifacts."""
    metadata = artifacts.metadata
    verdict = metadata.get("compliance_verdict")
    posture = metadata.get("compliance_posture")
    if verdict is not None and posture is not None:
        return verdict, posture

    summary = getattr(artifacts, "compliance_summary", None) or metadata.get("compliance_summary")
    if isinstance(summary, dict):
        verdict = verdict or summary.get("compliance_verdict")
        posture = posture or summary.get("posture") or summary.get("compliance_posture")
    return verdict, posture


def _print_run_metadata_warnings(metadata: Dict) -> None:
    """Print optional run warnings and disclosure counts from metadata."""
    run_warnings = list(metadata.get("run_warnings") or [])
    printed = set(run_warnings)
    for warning in run_warnings:
        print(f"WARNING: {warning}")

    suppressed = metadata.get("suppressed_categories") or []
    if suppressed:
        print(f"Suppressed categories: {len(suppressed)}")

    # Representativeness warnings are usually merged into run_warnings by the
    # artifact builder; only print ones that were not.
    representativeness = metadata.get("representativeness") or {}
    for warning in representativeness.get("warnings") or []:
        if warning not in printed:
            print(f"WARNING: {warning}")


def _resolve_exit_code(posture: Optional[str], verdict: Optional[str]) -> int:
    """Map compliance posture and verdict to a process exit code."""
    if posture == "strict" and verdict != "fully_compliant":
        print(f"STRICT POSTURE: verdict '{verdict}' -> exit code 2")
        return EXIT_STRICT_NON_COMPLIANT
    return EXIT_OK


def _format_analysis_failure_message(exc: Exception) -> str:
    """Prefer actionable detail from the exception chain when available."""
    primary = str(exc).strip()
    seen = {primary}
    chain_messages = [primary]

    current: Optional[BaseException] = exc
    while current is not None:
        cause = current.__cause__ or current.__context__
        if cause is None:
            break
        text = str(cause).strip()
        if text and text not in seen:
            seen.add(text)
            chain_messages.append(text)
        current = cause

    if isinstance(exc, RunBlocked):
        summary = getattr(exc, "compliance_summary", None)
        if isinstance(summary, dict):
            error_detail = summary.get("error")
            if isinstance(error_detail, str) and error_detail.strip():
                return error_detail.strip()

    if primary == _GENERIC_VALIDATION_ABORT:
        for text in chain_messages[1:]:
            lowered = text.lower()
            if "peer" in lowered or "minimum" in lowered or text.startswith("Only "):
                return text

    return primary


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
        print(f"Entity: {artifacts.metadata.get('entity', 'PEER-ONLY')}")
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
        _print_run_metadata_warnings(artifacts.metadata)
        print(f"{'='*80}\n")
        verdict, posture = _resolve_compliance_fields(artifacts)
        return _resolve_exit_code(posture, verdict)
    except RunBlocked as e:
        logger.error(f"Analysis blocked: {e}")
        print(f"Analysis blocked: {_format_analysis_failure_message(e)}")
        reason = e.compliance_summary.get("reason") if isinstance(e.compliance_summary, dict) else None
        hint = remediation_hint(reason)
        if hint:
            print(f"How to resolve: {hint}")
        print(json.dumps(e.compliance_summary, indent=2, default=str))
        return EXIT_FAILURE
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        logger.debug("Full traceback for analysis failure", exc_info=True)
        print(f"Analysis failed: {_format_analysis_failure_message(e)}")
        return EXIT_FAILURE


def run_rate_analysis(args: argparse.Namespace, logger: logging.Logger) -> int:
    """Thin CLI adapter over the shared analysis-run executor."""
    logger.info("Starting rate-based dimensional analysis")
    try:
        request = build_run_request('rate', args)
        artifacts = execute_rate_run(request, logger)
        print(f"\n{'='*80}")
        print("RATE ANALYSIS COMPLETE")
        print(f"{'='*80}")
        print(f"Entity: {artifacts.metadata.get('entity', 'PEER-ONLY')}")
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
        _print_run_metadata_warnings(artifacts.metadata)
        print(f"{'='*80}\n")
        verdict, posture = _resolve_compliance_fields(artifacts)
        return _resolve_exit_code(posture, verdict)
    except RunBlocked as e:
        logger.error(f"Analysis blocked: {e}")
        print(f"Analysis blocked: {_format_analysis_failure_message(e)}")
        reason = e.compliance_summary.get("reason") if isinstance(e.compliance_summary, dict) else None
        hint = remediation_hint(reason)
        if hint:
            print(f"How to resolve: {hint}")
        print(json.dumps(e.compliance_summary, indent=2, default=str))
        return EXIT_FAILURE
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        logger.debug("Full traceback for analysis failure", exc_info=True)
        print(f"Analysis failed: {_format_analysis_failure_message(e)}")
        return EXIT_FAILURE


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

    # Handle telemetry before analysis logging or session startup
    if args.command == 'telemetry':
        return handle_telemetry_command(args)
    
    if not args.command:
        parser.print_help()
        return 0

    # Validate preset selection consistently for both CLI and Python API
    if args.command in ('share', 'rate'):
        preset_error = _validate_preset_arg(args)
        if preset_error:
            print(preset_error)
            return 1
    
    # Setup logging for analysis commands
    log_level = getattr(args, 'log_level', None) or 'INFO'
    logger = setup_logging(log_level, f"benchmark_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    
    # Route to appropriate handler with a CLI session around usable analysis.
    # Telemetry helpers are best-effort and never raise.
    if args.command == 'share':
        start_session('cli_share')
        try:
            return run_share_analysis(args, logger)
        finally:
            end_session()
    elif args.command == 'rate':
        start_session('cli_rate')
        try:
            return run_rate_analysis(args, logger)
        finally:
            end_session()
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())

# E2E release exercise: cosmetic runtime change; no behavior change.

# E2E release exercise: cosmetic runtime change; no behavior change (2026-07-08T19:31:04Z).
