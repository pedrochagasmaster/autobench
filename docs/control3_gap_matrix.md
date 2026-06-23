# Control 3 Canonical Gap Matrix

Source: `docs/control-3-customer-merchant-performance-v5-20260603.md`

This matrix records how the tool handles each canonical Control 3 policy area. "Manual approval required" means the tool cannot verify the legal/business evidence from transaction data, so it blocks declared sensitive runs unless explicit review evidence is supplied.

| Canonical rule area | Tool status | Enforcement or rationale | Evidence |
|---|---|---|---|
| Control 3.2 benchmark numeric rules: 5/25, 6/30, 7/35, 10/40 | Enforced | `PrivacyValidator` and `evaluate_rule` select and evaluate the configured numeric rule, including secondary participant thresholds. | `core/privacy_rules.py`, `core/privacy_validator.py`, `tests/test_privacy_rules_engine.py`, `tests/test_privacy_rules_config.py` |
| Control 3.2 merchant-only 4/35 | Enforced | Rule selection only returns `4/35` when `merchant_mode` is true and peer count is 4. | `PrivacyValidator.select_rule`, `tests/test_privacy_rules_config.py` |
| Citi/Citibank protected-entity maximum 25% cap | Enforced when protected entity is configured | Protected entities default to a 25% cap even when the selected peer rule allows 30%, 35%, or 40%. | `PrivacyValidator.PROTECTED_ENTITY_DEFAULT_MAX_CONCENTRATION`, `tests/test_privacy_rules_config.py` |
| Fraud and chargeback issuer benchmarking concentration basis | Enforced as a run precondition | Fraud/chargeback rate runs must explicitly declare `privacy_basis: clearing_spend` or `--privacy-basis clearing_spend`; missing or different basis blocks execution. | `core/control3_policy.py`, `core/analysis_run.py`, `tests/test_control3_policy_gates.py` |
| Control 3.3 publication confidentiality for peer group/category composition | Enforced for publication diagnostics | Publication copies of peer-composition diagnostic sheets are redacted before workbook rendering. Analysis workbooks remain unchanged for internal review. | `core/output_artifacts.py`, `tests/test_control3_policy_gates.py` |
| Top-merchant list deliverables | Enforced as hard block | Runs declared with `contains_top_merchant_output` are blocked, including when Privacy approval is marked true, because the canonical doc says these deliverables may not be created. | `core/control3_policy.py`, `tests/test_control3_policy_gates.py` |
| Dual-entity-axis benchmark protection | Manual approval required | The tool cannot prove both entity axes are independently protected from one primary dataset. Runs declared with `dual_entity_axis` require `privacy_review_approved`. | `core/control3_policy.py`, `tests/test_control3_policy_gates.py` |
| Digital-wallet metrics or recipient | Manual approval required | Runs declared with `contains_digital_wallet_metrics` require `privacy_review_approved` before execution. | `core/control3_policy.py`, `tests/test_control3_policy_gates.py` |
| Recurring deliverable re-check when peer group changes | Enforced as evidence gate | Declared recurring runs with `peer_group_altered` require a current `last_privacy_recheck_date`. | `core/control3_policy.py`, `tests/test_control3_policy_gates.py` |
| Recurring deliverable annual re-check | Enforced as evidence gate | Declared recurring runs are blocked when `last_privacy_recheck_date` is missing or older than 365 days. | `core/control3_policy.py`, `tests/test_control3_policy_gates.py` |
| Merchant delivery using issuer/acquirer-specific segmentation | Manual approval required / out of automated scope | The canonical rule depends on contract rights, written permissions, and whether data is merchant-supplied. The tool does not inspect contracts, so this remains a manual approval requirement outside the optimizer. | Documented here; no automated gate unless the run declares digital-wallet, top-merchant, or dual-axis sensitivity. |
| Interchange metrics to merchants | Out of scope | The current CLI supports share/rate benchmarking over supplied columns; it does not identify interchange fee metrics semantically. If such a metric is supplied, users must handle legal approval outside this tool. | Documented here. |
| Retail parks, malls, publishers, M&A, franchise, reseller, and individual-level merchant use cases | Out of scope | These canonical scenarios require contractual/legal facts and recipient context that are not derivable from the benchmark dataset. | Documented here. |
| Best-in-class privacy-preserving ranking | Enforced by existing analysis path | Best-in-class uses percentile/rank-style peer aggregation rather than disclosing a specific entity's performance. | `DimensionalAnalyzer`, `AnalysisCalculator`, existing workbook tests |

## Operator Notes

Use these declarations for policy gates that cannot be inferred safely:

```yaml
control3:
  privacy_basis: clearing_spend
  contains_digital_wallet_metrics: false
  privacy_review_approved: false
  contains_top_merchant_output: false
  dual_entity_axis: false
  recurring_deliverable: false
  last_privacy_recheck_date: null
  peer_group_altered: false
```

Fraud or chargeback issuer benchmarking must set `privacy_basis: clearing_spend`. Digital-wallet and dual-entity-axis runs require explicit Privacy review approval. Top-merchant list output is blocked rather than approval-gated.
