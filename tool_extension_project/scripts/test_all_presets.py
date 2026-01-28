"""
Comprehensive Preset Testing Script for Peer Benchmark Tool

This script tests all presets and custom configurations against a dataset,
compares distortion results, and outputs a summary table.

Usage:
    py test_all_presets.py --csv data/your_file.csv --entity "YOUR ENTITY" --metric volume_brl

All parameters are passed directly to benchmark.py share command.
"""
import subprocess
import pandas as pd
import argparse
import os
import sys
from pathlib import Path
from datetime import datetime
import glob
import shutil

# Define configurations to test
CONFIGURATIONS = [
    # Standard presets
    {"name": "compliance_strict", "preset": "compliance_strict", "flags": []},
    {"name": "balanced_default", "preset": "balanced_default", "flags": []},
    {"name": "research_exploratory", "preset": "research_exploratory", "flags": []},
    {"name": "strategic_consistency", "preset": "strategic_consistency", "flags": []},
    
    # Custom presets
    {"name": "low_distortion", "preset": "low_distortion", "flags": []},
    {"name": "minimal_distortion", "preset": "minimal_distortion", "flags": []},
    
    # Standard presets with per-dimension weights
    {"name": "balanced_default+perdim", "preset": "balanced_default", "flags": ["--per-dimension-weights"]},
    {"name": "research_exploratory+perdim", "preset": "research_exploratory", "flags": ["--per-dimension-weights"]},
    
    # Custom presets with per-dimension weights
    {"name": "low_distortion+perdim", "preset": "low_distortion", "flags": ["--per-dimension-weights"]},
    {"name": "minimal_distortion+perdim", "preset": "minimal_distortion", "flags": ["--per-dimension-weights"]},
]


def run_benchmark(csv_path: str, entity: str, metric: str, entity_col: str, 
                  dimensions: str, time_col: str, secondary_metrics: list,
                  preset: str, flags: list, output_dir: Path) -> Path:
    """Run benchmark command and return path to balanced CSV."""
    
    cmd = [
        "py", "benchmark.py", "share",
        "--csv", csv_path,
        "--metric", metric,
        "--entity-col", entity_col,
        "--preset", preset,
        "--dimensions", dimensions,
        "--time-col", time_col,
        "--export-balanced-csv"
    ]
    
    # Only add entity if specified (peer-only analysis if omitted)
    if entity:
        cmd.extend(["--entity", entity])
    
    for sm in secondary_metrics:
        cmd.extend(["--secondary-metrics", sm])
    
    cmd.extend(flags)
    
    print(f"  Running: {preset} {' '.join(flags)}...", end=" ", flush=True)
    
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(output_dir.parent))
    
    if result.returncode != 0:
        print("FAILED")
        print(f"    Error: {result.stderr[:200]}")
        return None
    
    # Find most recent balanced CSV
    balanced_files = sorted(
        glob.glob(str(output_dir.parent / "*balanced*.csv")),
        key=os.path.getmtime,
        reverse=True
    )
    
    if balanced_files:
        print("OK")
        return Path(balanced_files[0])
    else:
        print("NO OUTPUT")
        return None


def calculate_distortion(original_csv: Path, balanced_csv: Path, 
                         entity: str, entity_col: str, 
                         metric: str, dimension_col: str, time_col: str) -> pd.DataFrame:
    """Calculate distortion between raw and balanced market shares.
    
    If entity is None (peer-only mode), calculates distortion for all entities.
    """
    
    # Load data
    raw_df = pd.read_csv(original_csv)
    balanced_df = pd.read_csv(balanced_csv)
    
    results = []
    
    for _, balanced_row in balanced_df.iterrows():
        category = balanced_row['Category']
        time_period = balanced_row[time_col]
        
        # Get raw data for this category and time
        raw_subset = raw_df[
            (raw_df[dimension_col] == category) &
            (raw_df[time_col] == time_period)
        ]
        
        if entity:
            # Entity mode: compare entity share vs balanced peer total
            entity_raw = raw_subset[raw_subset[entity_col] == entity][metric].sum()
            peers_raw = raw_subset[raw_subset[entity_col] != entity][metric].sum()
            peers_balanced = balanced_row[metric]
            
            raw_total = entity_raw + peers_raw
            balanced_total = entity_raw + peers_balanced
            
            if raw_total > 0 and balanced_total > 0:
                raw_share = entity_raw / raw_total * 100
                balanced_share = entity_raw / balanced_total * 100
                distortion = balanced_share - raw_share
                
                results.append({
                    'Category': category,
                    'Time': time_period,
                    'Raw_Share': raw_share,
                    'Balanced_Share': balanced_share,
                    'Distortion_pp': distortion
                })
        else:
            # Peer-only mode: all entities balanced, compare raw vs balanced totals
            raw_total = raw_subset[metric].sum()
            balanced_total = balanced_row[metric]
            
            # In peer-only mode, calculate how much the balanced differs from raw
            if raw_total > 0:
                # Distortion as % difference in total volume
                distortion_pct = (balanced_total - raw_total) / raw_total * 100
                
                results.append({
                    'Category': category,
                    'Time': time_period,
                    'Raw_Total': raw_total,
                    'Balanced_Total': balanced_total,
                    'Distortion_pp': distortion_pct
                })
    
    return pd.DataFrame(results)


def summarize_distortion(distortion_df: pd.DataFrame) -> pd.DataFrame:
    """Summarize distortion by category."""
    return distortion_df.groupby('Category')['Distortion_pp'].agg(
        ['mean', 'min', 'max', 'std']
    ).round(2)


def main():
    parser = argparse.ArgumentParser(description='Test all presets and compare distortion')
    parser.add_argument('--csv', required=True, help='Path to input CSV file')
    parser.add_argument('--entity', default=None, help='Target entity name (omit for peer-only analysis)')
    parser.add_argument('--metric', required=True, help='Primary metric column')
    parser.add_argument('--entity-col', default='issuer_name', help='Entity column name')
    parser.add_argument('--dimensions', default='function_variant', help='Dimension column')
    parser.add_argument('--time-col', default='ano_mes', help='Time column')
    parser.add_argument('--secondary-metrics', nargs='*', default=['txn_count'], help='Secondary metrics')
    parser.add_argument('--output', default='preset_comparison_results.csv', help='Output file')
    
    args = parser.parse_args()
    
    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}")
        sys.exit(1)
    
    output_dir = csv_path.parent
    
    print("=" * 70)
    print("PEER BENCHMARK PRESET COMPARISON TEST")
    print("=" * 70)
    print(f"Input: {csv_path}")
    print(f"Entity: {args.entity if args.entity else '(None - peer-only mode)'}")
    print(f"Metric: {args.metric}")
    print(f"Dimensions: {args.dimensions}")
    print(f"Time Column: {args.time_col}")
    print(f"Configurations to test: {len(CONFIGURATIONS)}")
    print("=" * 70)
    print()
    
    all_results = []
    
    for config in CONFIGURATIONS:
        config_name = config["name"]
        preset = config["preset"]
        flags = config["flags"]
        
        # Run benchmark
        balanced_csv = run_benchmark(
            csv_path=str(csv_path),
            entity=args.entity,
            metric=args.metric,
            entity_col=args.entity_col,
            dimensions=args.dimensions,
            time_col=args.time_col,
            secondary_metrics=args.secondary_metrics,
            preset=preset,
            flags=flags,
            output_dir=output_dir
        )
        
        if balanced_csv is None:
            continue
        
        # Calculate distortion
        distortion_df = calculate_distortion(
            original_csv=csv_path,
            balanced_csv=balanced_csv,
            entity=args.entity,
            entity_col=args.entity_col,
            metric=args.metric,
            dimension_col=args.dimensions,
            time_col=args.time_col
        )
        
        # Summarize
        summary = summarize_distortion(distortion_df)
        
        for category in summary.index:
            all_results.append({
                'Config': config_name,
                'Category': category,
                'Mean_Distortion_pp': summary.loc[category, 'mean'],
                'Min_Distortion_pp': summary.loc[category, 'min'],
                'Max_Distortion_pp': summary.loc[category, 'max'],
                'Pass': abs(summary.loc[category, 'mean']) < 5.0
            })
    
    # Create results DataFrame
    results_df = pd.DataFrame(all_results)
    
    if len(results_df) == 0:
        print("\nNo results generated. Check for errors above.")
        sys.exit(1)
    
    # Pivot table for comparison
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    
    pivot = results_df.pivot_table(
        index='Category',
        columns='Config',
        values='Mean_Distortion_pp',
        aggfunc='first'
    ).round(2)
    
    print("\nMean Distortion by Category and Config (pp):")
    print("-" * 70)
    print(pivot.to_string())
    
    # Find best config per category
    print("\n" + "-" * 70)
    print("BEST CONFIGURATION PER CATEGORY:")
    print("-" * 70)
    for category in pivot.index:
        row = pivot.loc[category]
        best_config = row.abs().idxmin()
        best_value = row[best_config]
        status = "PASS" if abs(best_value) < 5.0 else "FAIL"
        print(f"  {category:<20} | {best_config:<30} | {best_value:>+6.2f}pp | {status}")
    
    # Overall summary
    print("\n" + "-" * 70)
    print("OVERALL BEST CONFIGURATION:")
    print("-" * 70)
    avg_abs = pivot.abs().mean()
    best_overall = avg_abs.idxmin()
    print(f"  {best_overall} (avg abs distortion: {avg_abs[best_overall]:.2f}pp)")
    
    # Save detailed results
    results_df.to_csv(args.output, index=False)
    print(f"\nDetailed results saved to: {args.output}")
    
    # Check if any config achieves < 5pp for all categories
    print("\n" + "=" * 70)
    print("PASS/FAIL SUMMARY (target: all categories < 5pp)")
    print("=" * 70)
    
    for config_name in results_df['Config'].unique():
        config_data = results_df[results_df['Config'] == config_name]
        all_pass = config_data['Pass'].all()
        failed = config_data[~config_data['Pass']]['Category'].tolist()
        status = "✓ PASS" if all_pass else f"✗ FAIL ({', '.join(failed)})"
        print(f"  {config_name:<35} {status}")


if __name__ == "__main__":
    main()
