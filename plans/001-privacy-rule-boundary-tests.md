# Plan 001: Add boundary-value unit tests for all five privacy rules and the PrivacyValidator DataFrame path

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat e0950c4..HEAD -- core/privacy_rules.py core/privacy_validator.py core/constants.py tests/test_privacy_rules_engine.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW
- **Depends on**: none
- **Category**: tests
- **Planned at**: commit `e0950c4`, 2026-06-10

## Why this matters

The five Mastercard Control 3.2 privacy rules (5/25, 6/30, 7/35, 10/40, 4/35) are a **legal compliance requirement** — see the "Privacy Caps" table in `AGENTS.md`. Today the rule engine has unit tests only at coarse values (26%, 6%, 19%); there is not a single test at a cap boundary (exactly 25.0 vs 25.0+ε), and the DataFrame-level enforcement methods `PrivacyValidator.validate_peer_group`, `calculate_concentration`, and `apply_weighting` are nearly untested. An off-by-epsilon regression in compliance classification would currently ship without any CI signal. This plan adds the missing boundary tests and a dedicated `PrivacyValidator` test module so future changes to the compliance core fail fast.

## Current state

- `core/privacy_rules.py` — canonical rule evaluation. The primary cap comparison (line 145–149):

```python
primary_failures = sum(
    1
    for value in share_values
    if value > rule.max_concentration + COMPARISON_EPSILON
)
```

  and the secondary-tier counting helper (line 61–62):

```python
def _count_at_or_above(values: Iterable[float], threshold: float) -> int:
    return sum(1 for value in values if float(value) + COMPARISON_EPSILON >= threshold)
```

- `core/constants.py:3` — `COMPARISON_EPSILON = 1e-6`.
- Rule definitions are loaded via `PrivacyValidator.get_rule_config(rule_name)` (see `core/privacy_rules.py:54-58`), backed by `config/privacy_rules.yaml`. Secondary requirements are cumulative tiers, e.g. 10/40 normalizes to `{"tier_1": (2, 20.0), "tier_2": (3, 10.0)}` (see `_secondary_requirements_from_config` docstring, `core/privacy_rules.py:70-75`).
- `tests/test_privacy_rules_engine.py` — existing tests for `evaluate_rule`; use this file's style as the pattern for new parametrized cases.
- `core/privacy_validator.py` — DataFrame-level enforcement. `validate_peer_group` (line ~416) returns `(is_compliant, warnings)`; note that a metric whose concentration frame is `None` (zero total) is skipped via `continue` at line 453–454 without failing compliance — characterize this current behavior in a test, do **not** change it in this plan.
- Rule semantics (from `AGENTS.md` / `README.md`): 5/25 = min 5 peers, max 25%; 6/30 = min 6, max 30%, ≥3 participants ≥7%; 7/35 = min 7, max 35%, ≥2 ≥15% plus ≥1 additional ≥8%; 10/40 = min 10, max 40%, ≥2 ≥20% plus ≥1 additional ≥10%; 4/35 = min 4, max 35% (merchant only).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Run new tests | `py -m pytest tests/test_privacy_rules_engine.py tests/test_privacy_validator.py -q` | all pass |
| Full unit suite | `py -m pytest tests/ -q` | all pass |
| Gate (final check) | `py scripts/perform_gate_test.py` | exit 0, 18 cases pass |
| Lint | `py -m ruff check --select E,F --ignore E501,F401 tests/` | exit 0 |

Use the `py` launcher, never `python`, per repo convention.

## Scope

**In scope** (the only files you should modify/create):
- `tests/test_privacy_rules_engine.py` (extend)
- `tests/test_privacy_validator.py` (create)

**Out of scope** (do NOT touch):
- `core/privacy_rules.py`, `core/privacy_validator.py`, `core/constants.py` — this plan characterizes existing behavior. If a boundary test reveals what looks like a bug, record it as a finding in your report; do not change product code.
- `config/privacy_rules.yaml` and anything under `presets/` — never modify shipped rule definitions.

## Git workflow

- Branch: `advisor/001-privacy-rule-boundary-tests`
- Commit style from `git log`: short imperative prefix, e.g. `test: add privacy rule boundary coverage`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add boundary parametrized cases to `tests/test_privacy_rules_engine.py`

Add a `@pytest.mark.parametrize` block calling `evaluate_rule(rule_name, shares)` from `core.privacy_rules`. Cover, for **each** of the five rules:

1. All shares exactly at the cap (e.g. for 5/25: five shares where the max is exactly `25.0`) → `primary_cap_passed is True` (the epsilon makes exact-cap pass).
2. One share at `cap + 0.001` (clearly above epsilon) → `primary_cap_passed is False`, `primary_cap_failures == 1`.
3. One share at `cap + 1e-8` (inside epsilon) → `primary_cap_passed is True` (characterizes epsilon semantics).
4. Secondary tier boundaries:
   - 6/30: exactly three participants at exactly `7.0` → `secondary_rule_passed is True`; three at `6.999` → `False`.
   - 7/35: two at `15.0` + one at `8.0` → `True`; two at `14.999` → `False`.
   - 10/40: two at `20.0` + one at `10.0` → `True`; two at `19.999` → `False`.
5. Participant-count boundaries: exactly `min_entities` participants → `participant_count_passed is True`; `min_entities - 1` → `False`. For each rule.

Construct share lists that sum to ≤100 (pad with small filler shares). Aim for ~20 new parametrized cases.

**Verify**: `py -m pytest tests/test_privacy_rules_engine.py -q` → all pass, count increased by ~20.

### Step 2: Create `tests/test_privacy_validator.py`

New module testing the DataFrame path with synthetic peer groups. Build small DataFrames like:

```python
import pandas as pd
from core.privacy_validator import PrivacyValidator

def _peer_group(volumes: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        {"issuer_name": list(volumes), "transaction_count": list(volumes.values())}
    )
```

**Critical**: `validate_peer_group`, `calculate_concentration`, and `apply_weighting` default to `entity_column='entity_identifier'` (see `core/privacy_validator.py:416-420`, `503-507`, `536-541`). Since the helper above uses `issuer_name`, you MUST pass `entity_column="issuer_name"` on every call, or every test fails on a missing column.

Tests to write:
1. `validate_peer_group` returns `(True, ...)` for a balanced 5-peer group under 5/25 (all shares 20%).
2. `validate_peer_group` returns `(False, ...)` when one peer holds 30% under 5/25.
3. `validate_peer_group` returns `(False, ...)` when only 4 peers exist under a 5-peer rule (min participants path).
4. `calculate_concentration` returns shares summing to ~100 and the correct per-entity percentages for a known input.
5. `apply_weighting` output: after weighting a group with one dominant peer, the dominant peer's weighted concentration is at or below the threshold passed in (assert with the same concentration computation).
6. Characterization: a metric column whose total is zero does **not** flip compliance to `False` (documents the `continue` at `core/privacy_validator.py:453-454`). Fixture shape: one DataFrame with two metric columns — `transaction_count` with valid balanced volumes and `zero_metric` with all zeros — then `validate_peer_group(df, metrics=["transaction_count", "zero_metric"], entity_column="issuer_name")`; assert the result equals the result with `metrics=["transaction_count"]` alone. Add a comment marking it as characterization of current behavior.
7. Protected entities: construct `PrivacyValidator(protected_entities=["PEER_A"], protected_max_concentration=10.0)` and assert a 15% PEER_A share fails. (Read `_check_entity_concentration` at `core/privacy_validator.py:259` first to confirm the exact failure surface — if protected-entity handling differs from this description, write the test to match actual behavior and note it.)

Use constructor defaults from `AGENTS.md`: `PrivacyValidator(min_participants=5, max_concentration=25.0, rule_name=...)`. For rule-specific tests pass the explicit rule string (e.g. `rule_name="5/25"`) — constructor numeric defaults alone do not select a named rule. Check the actual signature in `core/privacy_validator.py` before writing.

**Verify**: `py -m pytest tests/test_privacy_validator.py -q` → all pass.

### Step 3: Full verification

**Verify**: `py -m pytest tests/ -q` → all pass; `py scripts/perform_gate_test.py` → exit 0.

## Test plan

This plan **is** the test plan. Pattern: model parametrization style on existing tests in `tests/test_privacy_rules_engine.py`. No product code changes, so the gate must pass unchanged.

## Done criteria

- [ ] `py -m pytest tests/ -q` exits 0
- [ ] `py scripts/perform_gate_test.py` exits 0
- [ ] Every one of the 5 rules has at least: one exact-cap case, one over-cap case, one participant-count boundary case
- [ ] 6/30, 7/35, 10/40 each have secondary-tier boundary cases (pass and fail)
- [ ] `git status` shows only the two in-scope test files modified/created
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- A boundary test fails in a way that indicates the **engine** misclassifies (e.g. exact-cap fails, or a clear violation passes). That is a product bug — report it with the failing case; do not "fix" the test to match, and do not edit `core/`.
- `PrivacyValidator`'s constructor or `validate_peer_group` signature does not match the description here (drift).
- The secondary-requirement normalization produces tiers different from those documented in "Current state" (e.g. 10/40 tiers are not `(2, 20.0)` / `(3, 10.0)`).

## Maintenance notes

- These tests freeze the epsilon semantics (`COMPARISON_EPSILON = 1e-6`). If anyone changes the epsilon or comparison direction, these tests must be deliberately revisited — that is the point.
- Plan 005 (optimization-failure semantics) builds on this coverage; land this first.
- Deferred: tests for `PrivacyPolicy._dynamic_thresholds` (`core/privacy_policy.py`) — separate concern, noted in the audit as TESTS-03, not planned this round.
