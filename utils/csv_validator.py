#!/usr/bin/env python
"""
CSV to Excel Rate Validation Script

Validates that the balanced totals in the exported CSV file correctly produce
the approval rates and fraud rates shown in the Excel benchmark report.

Usage:
    python utils/csv_validator.py <excel_file> <csv_file> [--tolerance PERCENT]

Example:
    python utils/csv_validator.py carrefour_with_time.xlsx carrefour_with_time_balanced.csv --tolerance 0.01
"""

import sys
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import pandas as pd
from openpyxl import load_workbook


def load_csv_data(csv_path: Path) -> pd.DataFrame:
    """Load the balanced CSV export file."""
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    
    df = pd.read_csv(csv_path)
    
    # Validate required columns
    required_cols = ['Dimension', 'Category']
    if not all(col in df.columns for col in required_cols):
        raise ValueError(f"CSV must contain columns: {required_cols}")
    
    return df


def load_excel_data(excel_path: Path) -> Dict[str, pd.DataFrame]:
    """Load dimension sheets from Excel benchmark report.
    
    Returns dictionary mapping dimension name to DataFrame.
    """
    if not excel_path.exists():
        raise FileNotFoundError(f"Excel file not found: {excel_path}")
    
    wb = load_workbook(excel_path, data_only=True)
    
    # Skip metadata sheets
    skip_sheets = {'Summary', 'Peer Weights', 'Weight Methods', 'Privacy Validation', 
                   'Subset Search', 'Structural Summary', 'Structural Detail', 'Rank Changes'}
    
    dimension_data = {}
    
    for sheet_name in wb.sheetnames:
        if sheet_name in skip_sheets:
            continue
        
        ws = wb[sheet_name]
        
        # Read sheet into DataFrame
        data = []
        headers = None
        
        for row_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
            # Find header row (usually row 3, contains "Category")
            if headers is None:
                if row and 'Category' in [str(cell) for cell in row if cell is not None]:
                    headers = [str(cell) if cell is not None else f'Unnamed_{i}' 
                              for i, cell in enumerate(row)]
                continue
            
            # Skip empty rows
            if not any(cell is not None for cell in row):
                continue
            
            data.append(row)
        
        if headers and data:
            df = pd.DataFrame(data, columns=headers)
            dimension_data[sheet_name] = df
    
    return dimension_data


def calculate_rate_from_csv(csv_df: pd.DataFrame, dimension: str, category: str, 
                            time_period: Optional[str], rate_type: str) -> Optional[float]:
    """Calculate rate from CSV balanced totals.
    
    Args:
        csv_df: CSV DataFrame
        dimension: Dimension name
        category: Category value
        time_period: Time period value (or None if no time column)
        rate_type: 'approval' or 'fraud'
    
    Returns:
        Calculated rate as decimal (e.g., 0.75 for 75%)
    """
    # Filter to matching row
    mask = (csv_df['Dimension'] == dimension) & (csv_df['Category'] == str(category))
    
    if time_period is not None and 'year_month' in csv_df.columns:
        # Convert time_period to match CSV format if needed
        mask = mask & (csv_df['year_month'] == time_period)
    
    matched = csv_df[mask]
    
    if len(matched) == 0:
        return None
    
    if len(matched) > 1:
        print(f"WARNING: Multiple matches found for {dimension}/{category}/{time_period}")
        return None
    
    row = matched.iloc[0]
    
    # Get balanced totals
    balanced_total = row.get('Balanced_Total')
    
    if rate_type == 'approval':
        balanced_numerator = row.get('Balanced_Approval_Total')
    elif rate_type == 'fraud':
        balanced_numerator = row.get('Balanced_Fraud_Total')
    else:
        raise ValueError(f"Unknown rate_type: {rate_type}")
    
    # Calculate rate
    if pd.isna(balanced_total) or pd.isna(balanced_numerator) or balanced_total == 0:
        return None
    
    rate = balanced_numerator / balanced_total
    return rate


def extract_rate_from_excel(excel_df: pd.DataFrame, category: str, 
                            rate_type: str, time_period: Optional[str] = None) -> Optional[float]:
    """Extract rate value from Excel dimension sheet.
    
    Args:
        excel_df: DataFrame from Excel dimension sheet
        category: Category value
        rate_type: 'approval' or 'fraud'
        time_period: Time period value (or None if no time column)
    
    Returns:
        Rate value as decimal (e.g., 0.75 for 75%)
    """
    # Find the rate column - try multiple patterns
    rate_cols = []
    
    # Pattern 1: Multi-rate format "Approval_Balanced Peer Average (%)"
    pattern1 = f"{rate_type.capitalize()}_Balanced Peer Average"
    rate_cols = [col for col in excel_df.columns if pattern1 in str(col) and '%' in str(col)]
    
    if not rate_cols:
        # Pattern 2: Single rate format "Peer_Balanced_Approval_%"
        pattern2 = f"Peer_Balanced_{rate_type.capitalize()}"
        rate_cols = [col for col in excel_df.columns if pattern2 in str(col) and '%' in str(col)]
    
    if not rate_cols:
        # Pattern 3: "Balanced_Approval_Rate"
        pattern3 = f"Balanced_{rate_type.capitalize()}_Rate"
        rate_cols = [col for col in excel_df.columns if pattern3 in str(col)]
    
    if not rate_cols:
        return None
    
    rate_col = rate_cols[0]
    
    # Find time column for multi-rate format if needed
    time_col = None
    if time_period is not None:
        time_col_pattern = f"{rate_type.capitalize()}_year_month"
        time_cols = [col for col in excel_df.columns if time_col_pattern in str(col)]
        if time_cols:
            time_col = time_cols[0]
        elif 'Time_Period' in excel_df.columns:
            time_col = 'Time_Period'
    
    # Filter to matching row
    # Convert both to strings for comparison (Excel may have numeric categories)
    excel_df_copy = excel_df.copy()
    excel_df_copy['Category'] = excel_df_copy['Category'].astype(str)
    mask = excel_df_copy['Category'] == str(category)
    
    if time_period is not None and time_col is not None:
        # Convert time_period to match Excel format (may be datetime)
        time_period_str = str(time_period)
        excel_df_copy[time_col] = excel_df_copy[time_col].astype(str)
        mask = mask & (excel_df_copy[time_col] == time_period_str)
    
    matched = excel_df_copy[mask]  # Use the copy with string conversions
    
    if len(matched) == 0:
        return None
    
    if len(matched) > 1:
        print(f"WARNING: Multiple matches in Excel for category {category}")
        return None
    
    row = matched.iloc[0]
    rate_value = row[rate_col]
    
    # Convert percentage to decimal if needed
    if pd.isna(rate_value):
        return None
    
    # Excel stores values as percentages (e.g., 75.5 for 75.5%)
    # Always divide by 100 to get decimal
    rate_value = rate_value / 100.0
    
    return rate_value


def validate_dimension(dimension: str, csv_df: pd.DataFrame, excel_df: pd.DataFrame,
                      rate_types: List[str], tolerance: float, has_time: bool) -> Dict[str, any]:
    """Validate all categories in a dimension.
    
    Returns:
        Dictionary with validation results
    """
    results = {
        'dimension': dimension,
        'total_checks': 0,
        'passed': 0,
        'failed': 0,
        'skipped': 0,
        'failures': []
    }
    
    # Get unique categories from CSV
    csv_categories = csv_df[csv_df['Dimension'] == dimension]['Category'].unique()
    
    for category in csv_categories:
        # Get time periods if applicable
        time_periods = [None]
        if has_time and 'year_month' in csv_df.columns:
            mask = (csv_df['Dimension'] == dimension) & (csv_df['Category'] == str(category))
            time_periods = csv_df[mask]['year_month'].unique()
        
        for time_period in time_periods:
            for rate_type in rate_types:
                results['total_checks'] += 1
                
                # Calculate rate from CSV
                csv_rate = calculate_rate_from_csv(csv_df, dimension, category, time_period, rate_type)
                
                # Extract rate from Excel
                excel_rate = extract_rate_from_excel(excel_df, category, rate_type, time_period)
                
                if csv_rate is None or excel_rate is None:
                    results['skipped'] += 1
                    continue
                
                # Compare rates
                diff = abs(csv_rate - excel_rate)
                
                if diff <= tolerance:
                    results['passed'] += 1
                else:
                    results['failed'] += 1
                    results['failures'].append({
                        'category': category,
                        'time_period': time_period,
                        'rate_type': rate_type,
                        'csv_rate': csv_rate,
                        'excel_rate': excel_rate,
                        'difference': diff,
                        'difference_pct': diff * 100
                    })
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description='Validate CSV balanced totals against Excel rates',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  # Basic validation
  python utils/csv_validator.py report.xlsx report_balanced.csv
  
  # With custom tolerance (0.1% = 0.001)
  python utils/csv_validator.py report.xlsx report_balanced.csv --tolerance 0.001
  
  # Verbose output
  python utils/csv_validator.py report.xlsx report_balanced.csv --verbose
        """
    )
    
    parser.add_argument('excel_file', help='Path to Excel benchmark report')
    parser.add_argument('csv_file', help='Path to balanced CSV export')
    parser.add_argument('--tolerance', type=float, default=0.0001,
                       help='Maximum allowed difference in rates (default: 0.0001 = 0.01%%)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Show detailed validation results')
    
    args = parser.parse_args()
    
    excel_path = Path(args.excel_file)
    csv_path = Path(args.csv_file)
    
    print(f"{'='*80}")
    print("CSV TO EXCEL RATE VALIDATION")
    print(f"{'='*80}")
    print(f"Excel File: {excel_path}")
    print(f"CSV File: {csv_path}")
    print(f"Tolerance: {args.tolerance:.6f} ({args.tolerance*100:.4f}%)")
    print(f"{'='*80}\n")
    
    # Load data
    try:
        print("Loading CSV data...")
        csv_df = load_csv_data(csv_path)
        print(f"  ✓ Loaded {len(csv_df)} rows")
        
        print("Loading Excel data...")
        excel_data = load_excel_data(excel_path)
        print(f"  ✓ Loaded {len(excel_data)} dimension sheets")
        
    except Exception as e:
        print(f"✗ Error loading data: {e}")
        return 1
    
    # Detect rate types from CSV columns
    rate_types = []
    if 'Balanced_Approval_Total' in csv_df.columns:
        rate_types.append('approval')
    if 'Balanced_Fraud_Total' in csv_df.columns:
        rate_types.append('fraud')
    
    if not rate_types:
        print("✗ No rate columns found in CSV")
        return 1
    
    print(f"Rate Types: {', '.join(rate_types)}")
    
    # Check for time column
    has_time = 'year_month' in csv_df.columns
    if has_time:
        print(f"Time-Aware: Yes (year_month column detected)")
    else:
        print(f"Time-Aware: No")
    
    print()
    
    # Validate each dimension
    all_results = []
    
    for dimension in csv_df['Dimension'].unique():
        # Find matching Excel sheet
        excel_df = None
        for sheet_name, df in excel_data.items():
            # Match by sheet name (exact or sanitized)
            if sheet_name == dimension or sheet_name.replace('_', '/') == dimension:
                excel_df = df
                break
        
        if excel_df is None:
            print(f"⚠ Skipping {dimension}: No matching Excel sheet found")
            continue
        
        print(f"Validating dimension: {dimension}")
        results = validate_dimension(dimension, csv_df, excel_df, rate_types, args.tolerance, has_time)
        all_results.append(results)
        
        # Print summary
        status = "✓ PASS" if results['failed'] == 0 else "✗ FAIL"
        print(f"  {status} - {results['passed']}/{results['total_checks']} checks passed")
        
        if results['failed'] > 0:
            print(f"    Failed: {results['failed']}")
            if args.verbose:
                for failure in results['failures']:
                    print(f"      • {failure['category']} ({failure['rate_type']}): "
                          f"CSV={failure['csv_rate']:.4%} vs Excel={failure['excel_rate']:.4%} "
                          f"(Δ={failure['difference_pct']:.4f}%)")
        
        if results['skipped'] > 0:
            print(f"    Skipped: {results['skipped']} (missing data)")
        
        print()
    
    # Overall summary
    total_checks = sum(r['total_checks'] for r in all_results)
    total_passed = sum(r['passed'] for r in all_results)
    total_failed = sum(r['failed'] for r in all_results)
    total_skipped = sum(r['skipped'] for r in all_results)
    
    print(f"{'='*80}")
    print("VALIDATION SUMMARY")
    print(f"{'='*80}")
    print(f"Dimensions Validated: {len(all_results)}")
    print(f"Total Checks: {total_checks}")
    print(f"Passed: {total_passed} ({total_passed/total_checks*100:.1f}%)")
    print(f"Failed: {total_failed} ({total_failed/total_checks*100:.1f}%)")
    print(f"Skipped: {total_skipped} ({total_skipped/total_checks*100:.1f}%)")
    
    if total_failed == 0:
        print(f"\n✓ ALL VALIDATIONS PASSED!")
        print(f"  CSV balanced totals correctly produce Excel rates within {args.tolerance*100:.4f}% tolerance")
        print(f"{'='*80}\n")
        return 0
    else:
        print(f"\n✗ VALIDATION FAILED")
        print(f"  {total_failed} rate calculations do not match within tolerance")
        print(f"  Review failures above or run with --verbose for details")
        print(f"{'='*80}\n")
        return 1


if __name__ == '__main__':
    sys.exit(main())
