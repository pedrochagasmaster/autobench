# Control 3 Implementation Summary

Commit: `a6777a5 feat: enforce Control 3 policy gates`

Canonical source: `docs/control-3-customer-merchant-performance-v5-20260603.md`

## What Changed

This work aligned the benchmark tool with the canonical Control 3 privacy documentation by adding enforceable safeguards around the existing privacy optimizer. The numeric privacy rules remain in the existing validator path, while policy requirements that cannot be inferred safely from transaction data are handled as explicit run-level gates.

## Enforcement Added

| Area | Implementation |
|---|---|
| Control 3.2 numeric rules | Existing `core/privacy_rules.py` and `core/privacy_validator.py` continue to enforce 5/25, 6/30, 7/35, and 10/40, with regression coverage preserved. |
| Merchant-only 4/35 | `PrivacyValidator.select_rule()` only selects `4/35` when `merchant_mode=True`. |
| Citi protected cap | Protected entities now default to a 25% cap through `PrivacyValidator.PROTECTED_ENTITY_DEFAULT_MAX_CONCENTRATION`. |
| Fraud/chargeback basis | New `core/control3_policy.py` blocks fraud or chargeback rate runs unless `privacy_basis` is `clearing_spend`. |
| Digital wallets | Runs declared with digital-wallet metrics require `privacy_review_approved=True`. |
| Top merchants | Runs declared with top-merchant list output are hard-blocked. |
| Dual entity axes | Runs declared with dual protected entity axes require Privacy review approval. |
| Recurring deliverables | Declared recurring runs require re-check evidence when the peer group changes and at least annually. |
| Control 3.3 publication confidentiality | Publication workbooks keep evidence sheets but redact peer-composition content before rendering. |

## New User-Facing Declarations

CLI flags were added for policy evidence:

```powershell
--privacy-basis clearing_spend
--contains-digital-wallet-metrics
--privacy-review-approved
--contains-top-merchant-output
--dual-entity-axis
--recurring-deliverable
--last-privacy-recheck-date YYYY-MM-DD
--peer-group-altered
```

The same fields are available in config files under:

```yaml
control3:
  privacy_basis: null
  contains_digital_wallet_metrics: false
  privacy_review_approved: false
  contains_top_merchant_output: false
  dual_entity_axis: false
  recurring_deliverable: false
  last_privacy_recheck_date: null
  peer_group_altered: false
```

## Tests Added or Updated

New targeted regression tests live in `tests/test_control3_policy_gates.py` and cover:

- fraud/chargeback clearing-spend basis blocking and allow path
- digital-wallet Privacy review gating
- top-merchant hard block
- dual-entity-axis Privacy review gating
- recurring re-check requirements
- precondition integration through `enforce_compliance_preconditions`
- publication redaction of peer evidence

Existing tests were updated where fraud runs are intentionally valid, so those commands now declare `--privacy-basis clearing_spend`.

## Documentation Added

`docs/control3_gap_matrix.md` maps every canonical rule area to one of:

- enforced
- manual approval required
- out of scope with rationale

## Verification

Both required checks passed after the implementation:

```powershell
py scripts/perform_gate_test.py
# Passed 18, Failed 0, Errors 0

py -m pytest -q
# 163 passed, 2 warnings
```

## Notes

The original exported Word document remains untracked:

`docs/Control 3 - Customer_Merchant Performance-v5-20260603_075246.docx`

The committed canonical source is the markdown file named in the objective, plus its referenced media image.
