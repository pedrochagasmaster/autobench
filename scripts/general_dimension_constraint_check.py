# %%
"""Notebook-style exploration for why `general` can produce identity weights.

This script is intentionally written with `# %%` cells so it can be opened in
VS Code/Jupyter directly and converted to `.ipynb` if needed.
"""

from pathlib import Path
from typing import Dict, List, Tuple
import sys

import pandas as pd

# Allow running as: py scripts/general_dimension_constraint_check.py
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.privacy_validator import PrivacyValidator


# %%
# Config: update the CSV path if you want to run against another file.
CSV_PATH = Path("data/csv_extractioN_dash_test_comma.csv")
ENTITY_COL = "issuer_name"
DIM_COL = "general"
METRIC_COL = "amount_txn_pure"


# %%
def compute_category_shares(
    df: pd.DataFrame, dimension: str, metric: str, entity_column: str
) -> Dict[str, pd.Series]:
    """Return peer share vectors (percent) by category for a given dimension."""
    shares_by_category: Dict[str, pd.Series] = {}
    for category, subset in df.groupby(dimension, dropna=False):
        peer_totals = subset.groupby(entity_column, dropna=False)[metric].sum()
        total = float(peer_totals.sum())
        if total <= 0:
            shares = pd.Series(dtype="float64")
        else:
            shares = (peer_totals / total * 100.0).sort_values(ascending=False)
        shares_by_category[str(category)] = shares
    return shares_by_category


def evaluate_rule_for_category(
    shares: pd.Series, rule_name: str
) -> Tuple[bool, List[str], float, int, int]:
    """Evaluate cap + additional constraints for a single category."""
    if shares.empty:
        return False, ["Empty share vector"], 0.0, 0, 0

    cfg = PrivacyValidator.get_rule_config(rule_name)
    cap = float(cfg.get("max_concentration", 0.0))
    max_share = float(shares.max())
    cap_ok = max_share <= cap
    additional_ok, details = PrivacyValidator.evaluate_additional_constraints(
        shares.astype(float).tolist(), rule_name
    )
    count_ge_20 = int((shares >= 20.0).sum())
    count_ge_10 = int((shares >= 10.0).sum())
    return cap_ok and additional_ok, details, max_share, count_ge_20, count_ge_10


# %%
df = pd.read_csv(CSV_PATH)
print(f"Loaded {len(df):,} rows from {CSV_PATH}")
print("Columns:", ", ".join(df.columns))
print()
print(f"Unique `{DIM_COL}` values: {df[DIM_COL].nunique(dropna=False)}")
print("Values:", df[DIM_COL].drop_duplicates().tolist())


# %%
# Rule selection is based on peer count in the analyzed scope.
peer_count = df[ENTITY_COL].nunique(dropna=True)
rule_name = PrivacyValidator.select_rule(peer_count, merchant_mode=False)
rule_cfg = PrivacyValidator.get_rule_config(rule_name)
cap = float(rule_cfg.get("max_concentration", 0.0))

print(f"Peer count: {peer_count}")
print(f"Selected privacy rule: {rule_name}")
print(f"Cap: {cap}%")


# %%
shares_by_category = compute_category_shares(
    df=df, dimension=DIM_COL, metric=METRIC_COL, entity_column=ENTITY_COL
)
print(f"Category count for `{DIM_COL}`: {len(shares_by_category)}")

for category, shares in shares_by_category.items():
    ok, details, max_share, c20, c10 = evaluate_rule_for_category(shares, rule_name)
    print()
    print(f"Category: {category}")
    print(f"Constraint status: {'PASS' if ok else 'FAIL'}")
    print(f"Max share: {max_share:.4f}% (cap={cap:.1f}%)")
    print(f"Count >=20%: {c20}")
    print(f"Count >=10%: {c10}")
    if details:
        print("Additional-constraint details:")
        for detail in details:
            print(f"- {detail}")
    print("Top 10 shares:")
    print(shares.head(10).to_string())


# %%
# Optional hard check: fail loudly if any category is non-compliant.
all_ok = True
for category, shares in shares_by_category.items():
    ok, _, _, _, _ = evaluate_rule_for_category(shares, rule_name)
    all_ok = all_ok and ok

assert all_ok, "At least one category violates selected privacy rule."
print("\nAll categories satisfy the selected privacy constraints at identity weights.")
