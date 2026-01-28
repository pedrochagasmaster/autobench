"""Analyze total volume change in peer-only mode."""
import pandas as pd

# Compare raw vs balanced totals for compliance_strict
print("=" * 70)
print("VOLUME CHANGE ANALYSIS - PEER ONLY MODE (compliance_strict)")
print("=" * 70)

# Load data
raw_std = pd.read_csv('data/e176097_tpv_nubank_filtered_std.csv')
bal_std = pd.read_csv('benchmark_share_PEER_ONLY_20260108_115757_balanced.csv')

raw_affl = pd.read_csv('data/e176097_tpv_nubank_filtered_affl.csv')
bal_affl = pd.read_csv('benchmark_share_PEER_ONLY_20260108_115804_balanced.csv')

for name, raw_df, bal_df in [('STD', raw_std, bal_std), ('AFFL', raw_affl, bal_affl)]:
    print(f"\n{name} Dataset:")
    print("-" * 50)
    
    for cat in bal_df['Category'].unique():
        raw_total = raw_df[raw_df['function_variant'] == cat]['volume_brl'].sum()
        bal_total = bal_df[bal_df['Category'] == cat]['volume_brl'].sum()
        
        pct_change = (bal_total - raw_total) / raw_total * 100 if raw_total > 0 else 0
        
        status = "✓" if abs(pct_change) < 5 else "✗"
        print(f"  {cat:<20} | Raw: {raw_total/1e12:.2f}T | Bal: {bal_total/1e12:.2f}T | Change: {pct_change:+.1f}% {status}")
