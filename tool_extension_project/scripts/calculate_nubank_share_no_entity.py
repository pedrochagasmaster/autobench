"""
Generate Nubank share analysis for peer-only mode (no entity set).
In this mode, Nubank is ALSO balanced along with other peers.
"""
import pandas as pd
from pathlib import Path
import sys

def calculate_share_analysis_no_entity(original_csv: Path, balanced_csv: Path, 
                                       entity: str, entity_col: str, 
                                       metric: str, count_col: str,
                                       dimension_col: str, time_col: str) -> pd.DataFrame:
    """Calculate share distortion when entity is balanced along with peers."""
    
    raw_df = pd.read_csv(original_csv)
    balanced_df = pd.read_csv(balanced_csv)
    
    results = []
    
    for _, balanced_row in balanced_df.iterrows():
        category = balanced_row['Category']
        time_period = balanced_row[time_col]
        balanced_total_vol = balanced_row[metric]
        balanced_total_cnt = balanced_row[count_col]
        
        # Get raw data for this category and time
        raw_subset = raw_df[
            (raw_df[dimension_col] == category) &
            (raw_df[time_col] == time_period)
        ]
        
        # Get entity (Nubank) raw values
        entity_raw = raw_subset[raw_subset[entity_col] == entity]
        entity_raw_vol = entity_raw[metric].sum()
        entity_raw_cnt = entity_raw[count_col].sum()
        
        # Get raw totals 
        raw_total_vol = raw_subset[metric].sum()
        raw_total_cnt = raw_subset[count_col].sum()
        
        # In peer-only mode, we assume entity volume is scaled proportionally
        # Entity's balanced volume = Entity Raw Volume * (Balanced Total / Raw Total)
        if raw_total_vol > 0:
            scale_factor_vol = balanced_total_vol / raw_total_vol
            entity_balanced_vol = entity_raw_vol * scale_factor_vol
        else:
            scale_factor_vol = 1.0
            entity_balanced_vol = 0
            
        if raw_total_cnt > 0:
            scale_factor_cnt = balanced_total_cnt / raw_total_cnt
            entity_balanced_cnt = entity_raw_cnt * scale_factor_cnt
        else:
            scale_factor_cnt = 1.0
            entity_balanced_cnt = 0
        
        # Calculate shares
        raw_vol_share = (entity_raw_vol / raw_total_vol * 100) if raw_total_vol > 0 else 0
        balanced_vol_share = (entity_balanced_vol / balanced_total_vol * 100) if balanced_total_vol > 0 else 0
        
        raw_cnt_share = (entity_raw_cnt / raw_total_cnt * 100) if raw_total_cnt > 0 else 0
        balanced_cnt_share = (entity_balanced_cnt / balanced_total_cnt * 100) if balanced_total_cnt > 0 else 0
        
        # Note: With proportional scaling, shares should be identical
        vol_distortion = balanced_vol_share - raw_vol_share
        cnt_distortion = balanced_cnt_share - raw_cnt_share
        
        results.append({
            'Dimension': dimension_col,
            'Category': category,
            'Time_Period': time_period,
            'Nubank_Raw_Volume': entity_raw_vol,
            'Nubank_Balanced_Volume': entity_balanced_vol,
            'Total_Raw_Volume': raw_total_vol,
            'Total_Balanced_Volume': balanced_total_vol,
            'Raw_Vol_Share_Pct': round(raw_vol_share, 2),
            'Balanced_Vol_Share_Pct': round(balanced_vol_share, 2),
            'Vol_Distortion_pp': round(vol_distortion, 2),
            'Nubank_Raw_Count': entity_raw_cnt,
            'Nubank_Balanced_Count': entity_balanced_cnt,
            'Total_Raw_Count': raw_total_cnt,
            'Total_Balanced_Count': balanced_total_cnt,
            'Raw_Cnt_Share_Pct': round(raw_cnt_share, 2),
            'Balanced_Cnt_Share_Pct': round(balanced_cnt_share, 2),
            'Cnt_Distortion_pp': round(cnt_distortion, 2)
        })
    
    return pd.DataFrame(results)


def main():
    script_dir = Path(__file__).parent
    
    # Configuration
    entity = "NU PAGAMENTOS SA"
    entity_col = "issuer_name"
    metric = "volume_brl"
    count_col = "txn_count"
    dimension_col = "function_variant"
    time_col = "ano_mes"
    
    datasets = [
        {
            'name': 'std',
            'original': script_dir / "data" / "e176097_tpv_nubank_filtered_std.csv",
            'balanced': script_dir / "benchmark_share_PEER_ONLY_20260108_115757_balanced.csv",
            'output': script_dir / "nubank_share_analysis_no_entity_std.csv"
        },
        {
            'name': 'affl',
            'original': script_dir / "data" / "e176097_tpv_nubank_filtered_affl.csv",
            'balanced': script_dir / "benchmark_share_PEER_ONLY_20260108_115804_balanced.csv",
            'output': script_dir / "nubank_share_analysis_no_entity_affl.csv"
        }
    ]
    
    for ds in datasets:
        print(f"\n{'='*60}")
        print(f"Processing: {ds['name']}")
        print(f"{'='*60}")
        
        if not ds['original'].exists():
            print(f"  ERROR: Original file not found: {ds['original']}")
            continue
        if not ds['balanced'].exists():
            print(f"  ERROR: Balanced file not found: {ds['balanced']}")
            continue
        
        print(f"  Original: {ds['original'].name}")
        print(f"  Balanced: {ds['balanced'].name}")
        
        results_df = calculate_share_analysis_no_entity(
            original_csv=ds['original'],
            balanced_csv=ds['balanced'],
            entity=entity,
            entity_col=entity_col,
            metric=metric,
            count_col=count_col,
            dimension_col=dimension_col,
            time_col=time_col
        )
        
        results_df.to_csv(ds['output'], index=False)
        print(f"  Output: {ds['output'].name}")
        print(f"  Rows: {len(results_df)}")
        
        # Summary
        summary = results_df.groupby('Category').agg({
            'Vol_Distortion_pp': ['mean', 'min', 'max'],
            'Raw_Vol_Share_Pct': 'mean',
            'Balanced_Vol_Share_Pct': 'mean'
        }).round(2)
        
        print("\n  Summary by Category:")
        print(summary.to_string())


if __name__ == "__main__":
    main()
