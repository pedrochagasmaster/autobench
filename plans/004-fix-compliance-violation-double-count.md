# Plan 004: Fix double-counting of privacy violations in the compliance summary

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat e0950c4..HEAD -- core/compliance.py tests/test_compliance_summary.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: plans/003-analysis-run-integration-test.md (recommended, not strictly required)
- **Category**: bug
- **Planned at**: commit `e0950c4`, 2026-06-10

## Why this matters

`build_compliance_summary` counts privacy violations twice: once as the number of validation rows with `strict_compliant=False`, and then **adds** `strict_final_validation["total_violations"]`, which independently recounts primary-cap failures, participant failures, secondary failures, and relaxed rows from the *same* rows. A single cap-violating peer row therefore inflates the `violations` counter (typically 2× or more), which distorts `run_status` severity reporting, audit logs, and any downstream gating on the violation count. Counts must be accurate before plan 006 starts blocking publication outputs on them.

## Current state

- `core/compliance.py:278-292` — the double count:

```python
violations = 0
if isinstance(privacy_validation, PrivacyValidationResult):
    violations = int(sum(1 for row in privacy_validation.rows if not row.strict_compliant))
elif privacy_validation_df is not None and not privacy_validation_df.empty:
    ...  # df fallback counting

details: Dict[str, Any] = {}
strict_final_validation = build_strict_final_validation(privacy_validation)
if strict_final_validation.get("checked"):
    details["strict_final_validation"] = strict_final_validation
    violations += int(strict_final_validation.get("total_violations", 0))   # <-- adds a recount
```

- `core/compliance.py:183-188` — `total_violations` composition inside `build_strict_final_validation`:

```python
result["total_violations"] = int(
    result["primary_cap_fail_rows"]
    + result["participant_count_fail_categories"]
    + result["secondary_rule_fail_categories"]
    + result["relaxed_rows"]
)
```

  `primary_cap_fail_rows` (lines 135-145) counts rows where `balanced_share_pct > primary_cap_pct` — the same rows that already have `strict_compliant=False` in the row-level count.
- `ComplianceSummary.to_dict()` (lines 216-240) derives `run_status` from `self.violations > 0` and the verdict from `has_violations` — so the boolean behavior is unchanged by fixing the count; only the magnitude is wrong today.
- Existing tests: `tests/test_compliance_summary.py` — the pattern file for assertions on `build_compliance_summary`.
- Note: `strict_final_validation` is the *canonical* strict recount (it covers primary cap AND category-level participant/secondary failures AND relaxation usage, which the row-level count partially misses). The row-level count is the redundant one.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Targeted tests | `py -m pytest tests/test_compliance_summary.py -q` | all pass |
| Full suite | `py -m pytest tests/ -q` | all pass |
| Gate | `py scripts/perform_gate_test.py` | exit 0 |
| Typecheck | `py -m mypy core/ utils/` | exit 0 |

## Scope

**In scope**:
- `core/compliance.py`
- `tests/test_compliance_summary.py` (extend)

**Out of scope**:
- `core/privacy_validation.py`, `core/privacy_rules.py` — row construction and rule evaluation are correct; only the summary aggregation double-counts.
- Any change to the `run_status` / `compliance_verdict` *string values* — downstream consumers (gate verification, audit packages) read them.

## Git workflow

- Branch: `advisor/004-compliance-violation-count`
- Commit message style: `fix: stop double-counting compliance violations`
- Do NOT push or open a PR unless instructed.

## Steps

### Step 1: Write the failing test first

In `tests/test_compliance_summary.py`, add a test that builds a `PrivacyValidationResult` containing exactly **one** row that violates the primary cap (e.g. `balanced_share_pct=30.0`, `primary_cap_pct=25.0`, `strict_compliant=False`, rule `5/25`, with 4 compliant sibling rows in the same `(dimension, category, time_period)` group so participant count passes and only the cap fails). The construction pattern to copy is the existing 5-row fixture at `tests/test_compliance_summary.py:165-186` — same `PrivacyValidationRow` fields, same grouping. Assert:

```python
summary = build_compliance_summary(posture="strict", privacy_validation_df=validation_result)
assert summary.violations == 1
```

Run it; it should fail with `violations == 2` (row count 1 + strict recount 1), confirming the bug.

**Verify**: `py -m pytest tests/test_compliance_summary.py -q -k <new test name>` → fails with the double count.

### Step 2: Make `strict_final_validation` the single source of violation counts

In `build_compliance_summary` (`core/compliance.py:278-292`):

- When `strict_final_validation.get("checked")` is true, set `violations = int(strict_final_validation.get("total_violations", 0))` — replacing, not adding to, the row-level count.
- Keep the row-level / DataFrame-fallback count **only** for the case where `strict_final_validation` is not checked (i.e., legacy DataFrame inputs where `build_strict_final_validation` returns `checked=False` — it only processes `PrivacyValidationResult.rows`; confirm by reading `build_strict_final_validation`'s input handling at the top of the function and `_as_validation_dataframe` usage at lines 272-277).

The resulting logic:

```python
violations = 0
strict_final_validation = build_strict_final_validation(privacy_validation)
if strict_final_validation.get("checked"):
    details["strict_final_validation"] = strict_final_validation
    violations = int(strict_final_validation.get("total_violations", 0))
elif isinstance(privacy_validation, PrivacyValidationResult):
    violations = int(sum(1 for row in privacy_validation.rows if not row.strict_compliant))
elif privacy_validation_df is not None and not privacy_validation_df.empty:
    ...  # existing df fallback unchanged
```

**Verify**: `py -m pytest tests/test_compliance_summary.py -q` → all pass including the new test.

### Step 3: Add a multi-failure-mode test

One row violating the cap **and** the category failing the secondary rule should count each failure mode once (`total_violations == primary_cap_fail_rows + secondary_rule_fail_categories`). Worked example to target: a single `(dimension, category, time_period)` group under rule `6/30` with 6 rows where one peer holds 31% (1 primary-cap fail row) and only two peers are ≥7% (secondary tier `≥3 at ≥7%` fails → 1 secondary fail category) → expected `violations == 2`, asserted exactly. Derive row shares that sum to 100 (e.g. 31, 8, 7, 6.9, 6.9, 40.2 split across remaining peers — compute and pin the exact values in the test). This documents that category-level and row-level failures are distinct, intentional contributions.

**Verify**: `py -m pytest tests/test_compliance_summary.py -q` → all pass.

### Step 4: Full verification

**Verify**: `py -m pytest tests/ -q` → all pass; `py scripts/perform_gate_test.py` → exit 0; `py -m mypy core/ utils/` → exit 0.

If any existing test asserted an inflated violation count, update that assertion to the correct count and call it out in the commit message.

## Test plan

- New: single-cap-violation → `violations == 1`; combined cap+secondary → exact expected count; zero-violation input → `violations == 0` (likely already covered — check before duplicating).
- Pattern: existing tests in `tests/test_compliance_summary.py`.

## Done criteria

- [ ] New single-violation test asserts `violations == 1` and passes
- [ ] `py -m pytest tests/ -q` exits 0
- [ ] `py scripts/perform_gate_test.py` exits 0
- [ ] `py -m mypy core/ utils/` exits 0
- [ ] `git status` shows only `core/compliance.py` and `tests/test_compliance_summary.py` modified
- [ ] `plans/README.md` status row updated

## STOP conditions

- `build_strict_final_validation` turns out to handle plain DataFrames too (i.e. the fallback branch in Step 2 would be dead) — re-read and adapt, but if the input model is materially different from the excerpt, stop and report.
- The gate fails after the change on a compliance-verdict check — that means some gate case's verdict depended on the inflated count (boolean shouldn't change, but if it does, report; don't tweak gate expectations).

## Maintenance notes

- Plan 006 (strict-posture publication gate) keys off `violations > 0`; the boolean is unchanged here, but reviewers should confirm no consumer reads the violation *magnitude* expecting the old inflated semantics (`rg -n "total_violations|\.violations" core/ utils/ scripts/`).
- Relaxed rows count as violations in strict accounting (`relaxed_rows` term). That is intentional Control 3.2 strictness — do not "fix" it.
