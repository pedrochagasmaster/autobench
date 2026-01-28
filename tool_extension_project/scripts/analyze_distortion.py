"""
Calculate distortion between raw and balanced market shares
Shows the impact of privacy balancing on Nubank's market share estimates
"""
import pandas as pd
from pathlib import Path


def calculate_raw_shares(raw_df: pd.DataFrame, entity: str = "NU PAGAMENTOS SA") -> pd.DataFrame:
    """Calculate raw market shares without balancing."""
    grouped = raw_df.groupby(['ano', 'function_variant', 'issuer_name']).agg({
        'volume_brl': 'sum',
        'txn_count': 'sum'
    }).reset_index()
    
    results = []
    
    for (year, func_var), group in grouped.groupby(['ano', 'function_variant']):
        nubank = group[group['issuer_name'] == entity]
        total = group
        
        nubank_vol = nubank['volume_brl'].sum()
        nubank_cnt = nubank['txn_count'].sum()
        total_vol = total['volume_brl'].sum()
        total_cnt = total['txn_count'].sum()
        
        vol_share = (nubank_vol / total_vol * 100) if total_vol > 0 else 0
        cnt_share = (nubank_cnt / total_cnt * 100) if total_cnt > 0 else 0
        
        parts = func_var.split(' / ')
        function = parts[0] if len(parts) > 0 else ''
        tier = parts[1] if len(parts) > 1 else ''
        
        results.append({
            'Year': int(year),
            'Function': function,
            'Tier': tier,
            'Volume_Share_Raw': vol_share,
            'Count_Share_Raw': cnt_share
        })
    
    return pd.DataFrame(results)


def calculate_balanced_shares(
    raw_df: pd.DataFrame,
    balanced_df: pd.DataFrame,
    entity: str = "NU PAGAMENTOS SA",
    time_col: str = "ano"
) -> pd.DataFrame:
    """Calculate balanced market shares."""
    results = []
    nubank_data = raw_df[raw_df['issuer_name'] == entity].copy()
    
    for _, bal_row in balanced_df.iterrows():
        category = bal_row['Category']
        year = bal_row[time_col]
        
        nubank = nubank_data[
            (nubank_data['function_variant'] == category) &
            (nubank_data[time_col] == year)
        ]
        
        nubank_vol = nubank['volume_brl'].sum()
        nubank_cnt = nubank['txn_count'].sum()
        
        peer_vol_balanced = bal_row['volume_brl']
        peer_cnt_balanced = bal_row['txn_count']
        
        total_vol = nubank_vol + peer_vol_balanced
        total_cnt = nubank_cnt + peer_cnt_balanced
        
        vol_share = (nubank_vol / total_vol * 100) if total_vol > 0 else 0
        cnt_share = (nubank_cnt / total_cnt * 100) if total_cnt > 0 else 0
        
        parts = category.split(' / ')
        function = parts[0] if len(parts) > 0 else ''
        tier = parts[1] if len(parts) > 1 else ''
        
        results.append({
            'Year': int(year),
            'Function': function,
            'Tier': tier,
            'Volume_Share_Balanced': vol_share,
            'Count_Share_Balanced': cnt_share
        })
    
    return pd.DataFrame(results)


def main():
    script_dir = Path(__file__).parent
    raw_csv = script_dir / "data" / "e176097_tpv_nubank_extended_std.csv"
    balanced_csv = script_dir / "benchmark_share_NU_PAGAMENTOS_SA_20260109_115832_balanced.csv"
    
    print("Loading data...")
    raw_df = pd.read_csv(raw_csv)
    balanced_df = pd.read_csv(balanced_csv)
    
    print("Calculating raw shares...")
    raw_shares = calculate_raw_shares(raw_df)
    
    print("Calculating balanced shares...")
    balanced_shares = calculate_balanced_shares(raw_df, balanced_df)
    
    # Merge and calculate distortion
    print("Calculating distortion...")
    merged = pd.merge(
        raw_shares,
        balanced_shares,
        on=['Year', 'Function', 'Tier'],
        how='inner'
    )
    
    merged['Volume_Distortion_pp'] = merged['Volume_Share_Balanced'] - merged['Volume_Share_Raw']
    merged['Count_Distortion_pp'] = merged['Count_Share_Balanced'] - merged['Count_Share_Raw']
    
    # Map tiers
    def map_tier(tier):
        if tier in ['Gold', 'Standard']:
            return 'Gold + Standard'
        else:
            return tier
    
    merged['Tier_Mapped'] = merged['Tier'].apply(map_tier)
    
    # Aggregate by mapped tier
    agg_merged = merged.groupby(['Year', 'Function', 'Tier_Mapped']).agg({
        'Volume_Share_Raw': 'sum',
        'Volume_Share_Balanced': 'sum',
        'Volume_Distortion_pp': 'sum',
        'Count_Share_Raw': 'sum',
        'Count_Share_Balanced': 'sum',
        'Count_Distortion_pp': 'sum'
    }).reset_index()
    
    # Create pivot tables
    print("\n" + "="*80)
    print("VOLUME MARKET SHARE DISTORTION")
    print("="*80)
    
    vol_pivot = agg_merged.pivot_table(
        index=['Function', 'Tier_Mapped'],
        columns='Year',
        values='Volume_Distortion_pp',
        aggfunc='first'
    ).round(1)
    
    print(vol_pivot)
    
    print("\n" + "="*80)
    print("TRANSACTION COUNT MARKET SHARE DISTORTION")
    print("="*80)
    
    cnt_pivot = agg_merged.pivot_table(
        index=['Function', 'Tier_Mapped'],
        columns='Year',
        values='Count_Distortion_pp',
        aggfunc='first'
    ).round(1)
    
    print(cnt_pivot)
    
    # Save detailed report
    output_file = script_dir / "market_share_distortion_analysis.csv"
    agg_merged.to_csv(output_file, index=False)
    print(f"\n\nDetailed distortion analysis saved to: {output_file}")
    
    # Summary statistics
    print("\n" + "="*80)
    print("DISTORTION SUMMARY STATISTICS")
    print("="*80)
    print("\nVolume Distortion (percentage points):")
    print(f"  Mean: {agg_merged['Volume_Distortion_pp'].mean():.2f} pp")
    print(f"  Min:  {agg_merged['Volume_Distortion_pp'].min():.2f} pp")
    print(f"  Max:  {agg_merged['Volume_Distortion_pp'].max():.2f} pp")
    
    print("\nTransaction Count Distortion (percentage points):")
    print(f"  Mean: {agg_merged['Count_Distortion_pp'].mean():.2f} pp")
    print(f"  Min:  {agg_merged['Count_Distortion_pp'].min():.2f} pp")
    print(f"  Max:  {agg_merged['Count_Distortion_pp'].max():.2f} pp")


if __name__ == "__main__":
    main()
