# CSV Validator

## Overview

The `csv_validator.py` script validates that the balanced totals exported to CSV correctly produce the approval rates and fraud rates shown in the Excel benchmark report.

## Purpose

When using the `--export-balanced-csv` flag, the tool exports weighted balanced totals for each dimension-category-(time) combination. This validator ensures data integrity by:

1. Loading the CSV balanced totals (Balanced_Total, Balanced_Approval_Total, Balanced_Fraud_Total)
2. Loading the Excel rate values (Approval rates and Fraud rates)
3. Calculating rates from CSV: `rate = balanced_numerator / balanced_total`
4. Comparing calculated rates against Excel rates
5. Reporting any discrepancies beyond the specified tolerance

## Usage

### Basic Usage

```bash
py utils/csv_validator.py <excel_file> <csv_file>
```

**Example:**
```bash
py utils/csv_validator.py carrefour_with_time.xlsx carrefour_with_time_balanced.csv
```

### With Custom Tolerance

```bash
py utils/csv_validator.py <excel_file> <csv_file> --tolerance 0.001
```

The tolerance is specified as a decimal (e.g., 0.001 = 0.1% difference allowed).

**Default tolerance:** 0.0001 (0.01%)

### Verbose Mode

```bash
py utils/csv_validator.py <excel_file> <csv_file> --verbose
```

Shows detailed information about each failed validation, including:
- Category name
- Rate type (approval/fraud)
- CSV calculated rate
- Excel rate
- Absolute difference

## How It Works

### CSV Structure

The CSV file contains these columns:
- **Dimension**: The dimension name (e.g., fl_token, poi, flag_recurring)
- **Category**: The category value within the dimension
- **year_month**: Time period (optional, only if --time-col was used)
- **Balanced_Total**: Weighted sum of total transactions/amounts
- **Balanced_Approval_Total**: Weighted sum of approved transactions/amounts
- **Balanced_Fraud_Total**: Weighted sum of fraud transactions/amounts

### Excel Structure

For multi-rate analysis, Excel sheets contain columns like:
- **Approval_Balanced Peer Average (%)**: Approval rate as percentage
- **Fraud_Balanced Peer Average (%)**: Fraud rate as percentage
- **Approval_year_month**: Time period for approval data
- **Fraud_year_month**: Time period for fraud data

### Validation Logic

For each dimension, category, and time period:

1. **Extract CSV values:**
   ```python
   balanced_total = CSV[Balanced_Total]
   balanced_approval = CSV[Balanced_Approval_Total]
   balanced_fraud = CSV[Balanced_Fraud_Total]
   ```

2. **Calculate rates:**
   ```python
   approval_rate = balanced_approval / balanced_total
   fraud_rate = balanced_fraud / balanced_total
   ```

3. **Extract Excel rates:**
   ```python
   excel_approval_rate = Excel[Approval_Balanced Peer Average (%)] / 100
   excel_fraud_rate = Excel[Fraud_Balanced Peer Average (%)] / 100
   ```

4. **Compare:**
   ```python
   if abs(csv_rate - excel_rate) > tolerance:
       # Report failure
   ```

## Output Example

### Successful Validation

```
================================================================================
CSV TO EXCEL RATE VALIDATION
================================================================================
Excel File: carrefour_with_time.xlsx
CSV File: carrefour_with_time_balanced.csv
Tolerance: 0.000100 (0.0100%)
================================================================================

Loading CSV data...
  ✓ Loaded 72 rows
Loading Excel data...
  ✓ Loaded 3 dimension sheets
Rate Types: approval, fraud
Time-Aware: Yes (year_month column detected)

Validating dimension: fl_token
  ✓ PASS - 48/48 checks passed

Validating dimension: flag_recurring
  ✓ PASS - 32/32 checks passed

Validating dimension: poi
  ✓ PASS - 48/48 checks passed

================================================================================
VALIDATION SUMMARY
================================================================================
Dimensions Validated: 3
Total Checks: 128
Passed: 128 (100.0%)
Failed: 0 (0.0%)
Skipped: 0 (0.0%)

✓ ALL VALIDATIONS PASSED!
  CSV balanced totals correctly produce Excel rates within 0.0100% tolerance
================================================================================
```

### Failed Validation (with --verbose)

```
Validating dimension: fl_token
  ✗ FAIL - 46/48 checks passed
    Failed: 2
      • Non-tokenized (fraud): CSV=0.0950% vs Excel=0.0955% (Δ=0.0005%)
      • Tokenized (approval): CSV=74.5012% vs Excel=74.5100% (Δ=0.0088%)
```

## Exit Codes

- **0**: All validations passed
- **1**: One or more validations failed, or error occurred

## Integration with Workflow

Recommended workflow when using `--export-balanced-csv`:

1. **Run analysis with CSV export:**
   ```bash
   py benchmark.py rate --csv data.csv --total-col amt_total \
     --approved-col amt_approved --fraud-col amt_fraud \
     --dimensions flag_recurring fl_token poi \
     --time-col year_month \
     --export-balanced-csv \
     --preset compliance_strict \
     --output report.xlsx
   ```

2. **Validate the CSV:**
   ```bash
   py utils/csv_validator.py report.xlsx report_balanced.csv
   ```

3. **If validation passes:** CSV is ready for downstream use (BI tools, databases, etc.)

4. **If validation fails:** Investigate discrepancies - may indicate:
   - Rounding errors (increase tolerance)
   - Missing data in CSV or Excel
   - Bug in CSV export logic

## Technical Notes

### Time-Aware Analysis

When `--time-col` is used:
- CSV has a `year_month` column with time periods
- Excel has separate time columns per rate type (e.g., `Approval_year_month`, `Fraud_year_month`)
- Validator matches rows by dimension + category + time period

### Multi-Rate vs Single-Rate

- **Multi-rate:** Both approval and fraud analyzed together, shared weights
  - Excel format: `Approval_Balanced Peer Average (%)`, `Fraud_Balanced Peer Average (%)`
- **Single-rate:** Only one rate type
  - Excel format: `Peer_Balanced_Approval_%` or similar

The validator automatically detects both formats.

### Skipped Checks

Checks are skipped when:
- CSV row not found (dimension/category/time combination missing)
- Excel rate column not found
- Excel row not found
- Rate values are NULL/NaN

This is normal for dimensions with sparse data or when Excel filters out certain categories.

## Troubleshooting

### All Checks Skipped

**Symptom:** Validator reports 100% skipped
```
Skipped: 144 (100.0%)
```

**Causes:**
- Column name mismatch between CSV and Excel
- Dimension names don't match (e.g., `/` vs `_` in sheet names)
- Time periods in different formats (datetime vs string)

**Solution:** Run with `--verbose` to see which columns are being searched for.

### High Failure Rate on Fraud Rates

**Symptom:** Approval rates pass, fraud rates fail systematically

**Cause:** Fraud rates are typically very small (0.01% - 1%), so rounding errors are proportionally larger.

**Solution:** Increase tolerance slightly:
```bash
py utils/csv_validator.py report.xlsx report_balanced.csv --tolerance 0.0005
```

### Missing Dimensions in Excel

**Symptom:** 
```
⚠ Skipping dimension_name: No matching Excel sheet found
```

**Cause:** Excel sheet name was truncated or sanitized (max 31 chars, no `/\` characters).

**Solution:** Check actual sheet names in Excel - validator tries both exact match and with `/` replaced by `_`.

## Dependencies

- pandas
- openpyxl

Install with:
```bash
pip install pandas openpyxl
```

## Related Documentation

- [BALANCED_CSV_EXPORT.md](../BALANCED_CSV_EXPORT.md) - CSV export feature documentation
- [README.md](../README.md) - Main tool documentation
