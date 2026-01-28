#!/usr/bin/env python
"""
Calculate Nubank's market share against balanced vs raw peer data.

This script compares:
1. Balanced market data (privacy-compliant weighted sums)
2. Raw/unbalanced market data (simple totals)

To measure the distortion introduced by the privacy-compliance process.

Market Share = Nubank / (Nubank + Peers) * 100
"""

import pandas as pd
from pathlib import Path


def load_full_data(csv_path: str) -> pd.DataFrame:
    """Load the full original dataset."""
    return pd.read_csv(csv_path)


def load_nubank_data(csv_path: str, entity_name: str = "NU PAGAMENTOS SA") -> pd.DataFrame:
    """Load and filter original data for the target entity."""
    df = pd.read_csv(csv_path)
    return df[df['issuer_name'] == entity_name].copy()


def load_balanced_data(balanced_csv_path: str) -> pd.DataFrame:
    """Load the balanced market data."""
    return pd.read_csv(balanced_csv_path)


def calculate_raw_market_totals(
    full_df: pd.DataFrame,
    dimension: str,
    category: str,
    time_period: str,
    entity_name: str = "NU PAGAMENTOS SA"
) -> tuple:
    """Calculate raw market totals for peers (excluding target entity)."""
    # Filter for this dimension/category/time, excluding the target entity
    peers_df = full_df[
        (full_df[dimension] == category) &
        (full_df['ano_mes'] == time_period) &
        (full_df['issuer_name'] != entity_name)
    ]
    
    raw_volume = peers_df['volume_brl'].sum()
    raw_count = peers_df['txn_count'].sum()
    
    return raw_volume, raw_count


def calculate_share_comparison(
    original_csv: str,
    balanced_csv: str,
    entity_name: str = "NU PAGAMENTOS SA"
) -> pd.DataFrame:
    """
    Calculate Nubank's share against both balanced and raw market data.
    
    Market Share = Nubank / (Nubank + Peers) * 100
    
    Returns a DataFrame with:
    - Balanced share (privacy-compliant weighted)
    - Raw share (simple peer totals)
    - Distortion (difference between balanced and raw)
    """
    # Load data
    full_df = load_full_data(original_csv)
    nubank_df = full_df[full_df['issuer_name'] == entity_name].copy()
    balanced_df = load_balanced_data(balanced_csv)
    
    results = []
    
    for _, balanced_row in balanced_df.iterrows():
        dimension = balanced_row['Dimension']
        category = balanced_row['Category']
        time_period = balanced_row['ano_mes']
        balanced_peer_volume = balanced_row['volume_brl']
        balanced_peer_count = balanced_row['txn_count']
        
        # Filter Nubank data for this dimension/category/time
        nubank_filtered = nubank_df[
            (nubank_df[dimension] == category) &
            (nubank_df['ano_mes'] == time_period)
        ]
        
        # Sum Nubank's values
        nubank_volume = nubank_filtered['volume_brl'].sum()
        nubank_count = nubank_filtered['txn_count'].sum()
        
        # Get raw peer totals (excluding Nubank)
        raw_peer_volume, raw_peer_count = calculate_raw_market_totals(
            full_df, dimension, category, time_period, entity_name
        )
        
        # Calculate TOTAL MARKET for each scenario
        raw_total_volume = nubank_volume + raw_peer_volume
        raw_total_count = nubank_count + raw_peer_count
        balanced_total_volume = nubank_volume + balanced_peer_volume
        balanced_total_count = nubank_count + balanced_peer_count
        
        # Calculate shares: Nubank / Total Market * 100
        raw_vol_share = (nubank_volume / raw_total_volume * 100) if raw_total_volume > 0 else 0
        raw_cnt_share = (nubank_count / raw_total_count * 100) if raw_total_count > 0 else 0
        balanced_vol_share = (nubank_volume / balanced_total_volume * 100) if balanced_total_volume > 0 else 0
        balanced_cnt_share = (nubank_count / balanced_total_count * 100) if balanced_total_count > 0 else 0
        
        # Calculate distortion (how much the balancing process changed the share)
        vol_distortion = balanced_vol_share - raw_vol_share
        cnt_distortion = balanced_cnt_share - raw_cnt_share
        
        results.append({
            'Dimension': dimension,
            'Category': category,
            'Time_Period': time_period,
            'Nubank_Volume': nubank_volume,
            'Raw_Peer_Volume': raw_peer_volume,
            'Balanced_Peer_Volume': balanced_peer_volume,
            'Total_Raw_Volume': raw_total_volume,
            'Total_Balanced_Volume': balanced_total_volume,
            'Raw_Vol_Share_Pct': round(raw_vol_share, 2),
            'Balanced_Vol_Share_Pct': round(balanced_vol_share, 2),
            'Vol_Distortion_pp': round(vol_distortion, 2),
            'Nubank_Count': nubank_count,
            'Raw_Peer_Count': raw_peer_count,
            'Balanced_Peer_Count': balanced_peer_count,
            'Total_Raw_Count': raw_total_count,
            'Total_Balanced_Count': balanced_total_count,
            'Raw_Cnt_Share_Pct': round(raw_cnt_share, 2),
            'Balanced_Cnt_Share_Pct': round(balanced_cnt_share, 2),
            'Cnt_Distortion_pp': round(cnt_distortion, 2)
        })
    
    return pd.DataFrame(results)


def print_distortion_summary(results_df: pd.DataFrame) -> None:
    """Print a summary comparing balanced vs raw shares."""
    print("\n" + "="*80)
    print("NUBANK MARKET SHARE: BALANCED vs RAW COMPARISON")
    print("(Distortion = Balanced Share - Raw Share, in percentage points)")
    print("="*80)
    
    for dimension in results_df['Dimension'].unique():
        dim_df = results_df[results_df['Dimension'] == dimension]
        
        print(f"\n{'='*60}")
        print(f"  {dimension.upper()}")
        print(f"{'='*60}")
        
        for category in dim_df['Category'].unique():
            cat_df = dim_df[dim_df['Category'] == category]
            
            # Calculate averages
            avg_raw_vol = cat_df['Raw_Vol_Share_Pct'].mean()
            avg_balanced_vol = cat_df['Balanced_Vol_Share_Pct'].mean()
            avg_vol_distortion = cat_df['Vol_Distortion_pp'].mean()
            
            avg_raw_cnt = cat_df['Raw_Cnt_Share_Pct'].mean()
            avg_balanced_cnt = cat_df['Balanced_Cnt_Share_Pct'].mean()
            avg_cnt_distortion = cat_df['Cnt_Distortion_pp'].mean()
            
            print(f"\n  {category}:")
            print(f"    VOLUME SHARE:")
            print(f"      Raw Average:      {avg_raw_vol:6.2f}%")
            print(f"      Balanced Average: {avg_balanced_vol:6.2f}%")
            print(f"      Distortion:       {avg_vol_distortion:+6.2f} pp")
            print(f"    COUNT SHARE:")
            print(f"      Raw Average:      {avg_raw_cnt:6.2f}%")
            print(f"      Balanced Average: {avg_balanced_cnt:6.2f}%")
            print(f"      Distortion:       {avg_cnt_distortion:+6.2f} pp")


def main():
    # File paths
    script_dir = Path(__file__).parent
    original_csv = script_dir / "data" / "e176097_tpv_nubank_filtered_affl.csv"
    balanced_csv = script_dir / "benchmark_share_NU_PAGAMENTOS_SA_20260108_111403_balanced.csv"
    
    print(f"Loading original data: {original_csv}")
    print(f"Loading balanced data: {balanced_csv}")
    
    # Calculate comparison
    results_df = calculate_share_comparison(
        str(original_csv),
        str(balanced_csv),
        entity_name="NU PAGAMENTOS SA"
    )
    
    # Print distortion summary
    print_distortion_summary(results_df)
    
    # Save detailed results
    output_path = script_dir / "nubank_share_distortion_analysis.csv"
    results_df.to_csv(output_path, index=False)
    print(f"\n\nDetailed results saved to: {output_path}")
    
    # Summary table
    print("\n\n" + "="*80)
    print("SUMMARY TABLE: Average Distortion by Dimension/Category")
    print("="*80)
    summary = results_df.groupby(['Dimension', 'Category']).agg({
        'Raw_Vol_Share_Pct': 'mean',
        'Balanced_Vol_Share_Pct': 'mean',
        'Vol_Distortion_pp': 'mean',
        'Raw_Cnt_Share_Pct': 'mean',
        'Balanced_Cnt_Share_Pct': 'mean',
        'Cnt_Distortion_pp': 'mean'
    }).round(2)
    print(summary.to_string())
    
    return results_df


if __name__ == "__main__":
    main()

