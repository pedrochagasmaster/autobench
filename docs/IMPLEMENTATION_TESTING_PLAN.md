# Implementation & Testing Plan (Impact Standardization + CSV/Validator Alignment + Audit + Privacy Additional Constraints)

**Scope**
- Fix share balanced CSV export bug
- Align CSV validator with current export schema (Impact-based columns)
- Confirm audit logs and Privacy Validation columns are correct
- Validate publication outputs
- Add/adjust tests as needed

---

## 0) Preflight & Context

1) Open and read:
   - `AGENTS.md`
   - `docs/OPERATIONAL_GAINS_REVIEW.md`
2) Note new behavior expectations:
   - Additional Control 3.2 constraints enforced
   - Impact terminology standardization
   - Debug sheets / privacy validation / impact summary on by default
   - Audit log should always be created

---

## 1) Fix Share Balanced CSV Export Bug

**Problem**
- Share CSV export currently logs: “No data to export for share analysis CSV”.
- Root cause is indentation in `export_balanced_csv` loop — processing is incorrectly nested under `if include_calculated and not target_entity`, which causes `export_rows` to remain empty for normal target entity analysis.

**File**
- `benchmark.py`

**Where**
- `export_balanced_csv()` — share branch near:
  - `elif analysis_type == 'share'...`
  - The loop that processes categories and appends `export_rows`.

**Steps**
1) Open `benchmark.py`.
2) Locate `export_balanced_csv` share branch.
3) Move the block that loops categories/time periods **out of**:
   ```python
   if include_calculated and not target_entity:
       logger.info(...)
   ```
   so that the loop always runs.
4) Keep the `if include_calculated and not target_entity` branch only for the logging statement.
5) Ensure that for:
   - **target_entity present**: include `Raw_*`, `Balanced_*`, `*_Share_%`, `*_Impact_PP` columns if `include_calculated=True`.
   - **peer-only**: include `Balanced_*`, and if `include_calculated=True`, allow `Raw_*` but leave `*_Share_%` and `*_Impact_PP` as `None`.
6) Confirm `export_rows` is appended for every dimension/category/time_period.

**Expected outcome**
- `_balanced.csv` created for share analysis when `--export-balanced-csv` is used, regardless of `include_calculated`.

---

## 2) CSV Validator Alignment (Rate Export Schema)

**Problem**
- `utils/csv_validator.py` expects rate CSV columns like `Balanced_Total` and `Balanced_Approval_Total`, but `export_balanced_csv` writes metric names (`total_txn`, `txn_count`) for rate CSVs.

**Options**
- **Preferred (compatibility)**: Update validator to accept either schema.
- **Alternative**: Update exporter to include both naming schemes (adds backward compatibility but more columns).

**File**
- `utils/csv_validator.py`

**Steps**
1) Open `utils/csv_validator.py`.
2) Find the rate validation logic that checks CSV column names.
3) Make it accept **either**:
   - `Balanced_Total` / `Balanced_Approval_Total` / `Balanced_Fraud_Total`
   **OR**
   - actual metric names used in the CSV (from CLI: `total_col`, `approved_col`, `fraud_col`)
4) Detect which scheme is present:
   - If `Balanced_Total` exists, proceed as-is.
   - Else, use CLI metric names passed in validator (it can infer from Excel Summary sheet or map to CSV via header name).
5) Update error message to reflect both allowed schemas.

**Expected outcome**
- `py utils\csv_validator.py ...` succeeds for rate CSVs created by current exporter.

---

## 3) Audit Log Validation

**Goal**
Ensure audit log is created in both share + rate flows and has key fields.

**Files**
- `benchmark.py`
- `core/report_generator.py`

**Steps**
1) Confirm `ReportGenerator.create_audit_log()` is called in:
   - Share flow: after report generation
   - Rate flow: after report generation
2) Ensure `results_summary` contains:
   - `dimensions_analyzed`
   - `categories_analyzed`
   - `impact_mean_abs_pp`
   - `privacy_rule`
   - `additional_constraint_violations_count`
   - `privacy_validation_rows`
   - `outputs`, `balanced_csv`
3) Open one audit log file and confirm content.

**Expected outcome**
- `<report>_audit.log` exists and includes metadata + results summary.

---

## 4) Privacy Validation Columns Check

**Goal**
Ensure additional constraints are visible in the Privacy Validation sheet.

**File**
- `core/dimensional_analyzer.py` (already implemented)

**Check**
1) Open generated report and verify columns:
   - `Additional_Constraints_Passed`
   - `Additional_Constraint_Detail`
2) Verify rows with violations show `No` and include rule-specific text.

---

## 5) Publication Output Check

**Goal**
Ensure publication outputs are created when `--output-format both`.

**Files**
- `benchmark.py`
- `core/report_generator.py`

**Steps**
1) Run share + rate with `--output-format both`.
2) Confirm `_publication.xlsx` exists.
3) Verify publication workbook has only `Executive Summary` and dimension tabs.

---

## 6) Impact Terminology Sanity Checks

**Goal**
Ensure consistent “Impact” naming across outputs and CSVs.

**Files**
- `benchmark.py`
- `core/dimensional_analyzer.py`
- `tests/test_enhanced_features.py`

**Checks**
1) Confirm Impact Analysis sheet title and columns:
   - `Impact_PP` (share)
   - `*_Impact_PP` (rate)
2) Confirm CSV uses `Impact_PP` suffix in share and rate, if `include_calculated` is true.
3) Confirm preset comparison shows `Mean_Abs_Impact_PP`.

---

## 7) Testing Plan (Commands + Expected Outcomes)

### 7.1 Unit Tests
```
py -m pytest
```
Expected: all tests pass.

### 7.2 Share Analysis (with CSV + publication)
```
py benchmark.py share --csv data\e176097_tpv_nubank_filtered.csv --entity "ITAU UNIBANCO S.A." --metric volume_brl --dimensions product_cd credit_debit_ind --time-col ano_mes --export-balanced-csv --output-format both
```
Expected:
- `.xlsx` report + `_publication.xlsx`
- `_balanced.csv` now generated
- `_audit.log` created

### 7.3 Rate Analysis (with CSV + publication)
```
py benchmark.py rate --csv data\e176097_tpv_nubank_filtered.csv --entity "ITAU UNIBANCO S.A." --total-col total_txn --approved-col txn_count --dimensions product_cd credit_debit_ind --time-col ano_mes --export-balanced-csv --output-format both
```
Expected:
- `.xlsx` report + `_publication.xlsx`
- `_balanced.csv` generated
- `_audit.log` created

### 7.4 CSV Validation
```
py utils\csv_validator.py benchmark_approval_rate_ITAU_UNIBANCO_S.A._<timestamp>.xlsx benchmark_approval_rate_ITAU_UNIBANCO_S.A._<timestamp>_balanced.csv --verbose
```
Expected: should pass once validator is updated.

### 7.5 Workbook Inspection (spot checks)
Use quick script or open in Excel:
- Validate sheets list (Summary, Impact Analysis, Privacy Validation, Weight Methods).
- Check Privacy Validation has additional constraint columns.
- Check Impact Analysis contains expected headers.

---

## 8) Specific Fixes Required After Running Plan

**Known failures today**
- Share CSV not generated ? fix export loop indentation.
- CSV validator fails with “No rate columns found” ? update validator schema to accept new CSV structure.

---

## 9) Files Likely Modified

- `benchmark.py`  
  (share CSV export fix, possibly schema alignment)
- `utils/csv_validator.py`  
  (schema tolerance for rate CSVs)
- `tests/test_enhanced_features.py`  
  (if new columns or logic requires assertions)

---

## 10) Deliverables Checklist

- [ ] Share `_balanced.csv` produced
- [ ] Rate `_balanced.csv` produced
- [ ] CSV validator passes for rate
- [ ] Audit log created for both runs
- [ ] Publication workbook created for both
- [ ] Impact Analysis sheets present and correct
- [ ] Privacy Validation includes additional constraint columns
- [ ] Pytest passes
