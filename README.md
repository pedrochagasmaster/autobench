# Privacy-Compliant Peer Benchmark Tool

<div align="center">

**Compare financial entities against privacy-compliant peer benchmarks with one-click analysis**

[![Version](https://img.shields.io/badge/version-3.0.0-blue.svg)](https://github.com)
[![Python](https://img.shields.io/badge/python-3.8+-green.svg)](https://python.org)
[![Status](https://img.shields.io/badge/status-production--ready-brightgreen.svg)](https://github.com)

[Quick Start](#-quick-start) · [TUI Guide](#-using-the-tui) · [CLI Reference](#-cli-reference) · [Presets](#-choosing-the-right-preset) · [FAQ](#-frequently-asked-questions)

</div>

---

## 🎯 What It Does

The Peer Benchmark Tool compares banks, issuers, and merchants against their peer groups while **automatically enforcing Mastercard Control 3.2 privacy rules**. It prevents any single competitor from dominating your benchmark—a regulatory requirement for financial reporting.

<table>
<tr>
<td width="50%">

### ✅ What You Get
- Entity vs peer comparison across dimensions
- Privacy-weighted averages (no single peer dominates)
- Best-in-Class benchmarks (85th/15th percentile)
- Full audit trail for compliance

</td>
<td width="50%">

### 🔒 What's Protected
- Individual peer performance is masked
- Concentration limits enforced automatically
- Regulatory compliance built-in
- No manual privacy calculations needed

</td>
</tr>
</table>

---

## ⚡ Quick Start

### Option A: Interactive TUI *(Recommended for new users)*

```bash
pip install -r requirements.txt
python tui_app.py
```

> 💡 **Tip:** The TUI automatically discovers CSV files in your current directory and `data/` folder.

### Option B: Command Line

```powershell
# Install once
pip install -r requirements.txt

# Run share analysis
py benchmark.py share --csv data/sample.csv --entity "BANCO SANTANDER" --metric txn_cnt --auto

# Run rate analysis  
py benchmark.py rate --csv data/sample.csv --entity "BANCO SANTANDER" --total-col total --approved-col approved --auto
```

> 📁 **Output:** Excel report saved to current directory with timestamp.

---

## 🖥️ Using the TUI

The Terminal User Interface provides a guided experience:

```
┌─────────────────────────────────────────────────────────────┐
│  📂 SELECT CSV         data/monthly_transactions.csv       │
│  🏢 ENTITY COLUMN      issuer_name                         │
│  🎯 TARGET ENTITY      BANCO SANTANDER                     │
│  ⚙️  PRESET            balanced_default                    │
├─────────────────────────────────────────────────────────────┤
│  [SHARE]  Primary Metric:  txn_cnt                          │
│  [RATE]   Total: amt_total  Approved: amt_approved          │
├─────────────────────────────────────────────────────────────┤
│  [ 🚀 RUN ANALYSIS ]                                        │
└─────────────────────────────────────────────────────────────┘
```

### Step-by-Step Workflow

| Step | Action | Tips |
|------|--------|------|
| 1️⃣ | Select your CSV file | Files from `.` and `data/` shown automatically |
| 2️⃣ | Choose entity column | Usually `issuer_name` or `bank_name` |
| 3️⃣ | Select target entity | Dropdown populates from your data |
| 4️⃣ | Pick a preset | Start with `balanced_default` |
| 5️⃣ | Configure analysis tab | Share (volume) or Rate (approval/fraud) |
| 6️⃣ | Click **Run Analysis** | Watch the log for progress |

> ⌨️ **Keyboard Shortcuts:** `Ctrl+O` Open File · `Ctrl+R` Run · `F1` Help · `Esc` Cancel

---

## 📊 Analysis Types

<table>
<tr>
<th width="50%">📈 Share Analysis</th>
<th width="50%">📉 Rate Analysis</th>
</tr>
<tr>
<td>

**Question:** *How is volume distributed?*

```
Category     You    Peers   Gap
CREDIT      45.2%   38.5%  +6.7pp ✓
DEBIT       42.3%   48.2%  -5.9pp
PREPAID     12.5%   13.3%  -0.8pp
```

**Use for:**
- Market positioning
- Product mix analysis
- Strategic planning

</td>
<td>

**Question:** *How do rates compare?*

```
Category     You    Peers   Gap
POS         92.1%   89.5%  +2.6pp ✓
ECOMMERCE   85.3%   82.1%  +3.2pp ✓
ATM         97.2%   96.8%  +0.4pp
```

**Use for:**
- Authorization optimization
- Fraud benchmarking
- Risk assessment

</td>
</tr>
</table>

---

## 🎛️ Choosing the Right Preset

> 🤔 **Not sure which to pick?** Start with `balanced_default` — it works for 90% of use cases.

| Preset | Best For | What Happens |
|--------|----------|--------------|
| 🟢 **`balanced_default`** | Day-to-day analysis | Allows 2% tolerance; fastest |
| 🔴 **`compliance_strict`** | Regulatory reports | Zero violations; may split dimensions |
| 🟡 **`strategic_consistency`** | Executive dashboards | Keeps all dimensions together |
| 🟣 **`research_exploratory`** | Difficult datasets | Very relaxed; use for exploration |

### 🌳 Decision Tree

```
📋 Is this report for a regulator or auditor?
│
├─ YES ──────────────────────────────► 🔴 compliance_strict
│
└─ NO ── Do you need ONE consistent set of weights?
         │
         ├─ YES (executive dashboard) ► 🟡 strategic_consistency
         │
         └─ NO (standard analysis) ──► 🟢 balanced_default ⭐
```

---

## 🔐 Privacy Compliance (Automatic)

The tool **auto-detects** your peer count and applies the correct privacy rule:

| Rule | Min Peers | Max Share | Additional Requirements | Compliant Example |
|------|-----------|-----------|------------------------|-------------------|
| **5/25** | 5 | 25% | — | [25, 25, 25, 24, 1] |
| **6/30** | 6 | 30% | ≥3 participants must be ≥7% | [30, 24.5, 24.5, 7, 7, 7] |
| **7/35** | 7 | 35% | ≥2 participants ≥15%, ≥1 additional ≥8% | [35, 15, 15, 8.75, 8.75, 8.75, 8.75] |
| **10/40** | 10 | 40% | ≥2 participants ≥20%, ≥1 additional ≥10% | [40, 20, 20, 10, 1.6, 1.6, 1.6, 1.6, 1.6, 1.6] |
| **4/35** | 4 | 35% | Merchant benchmarking only | — |

> ⚠️ **You never configure privacy caps manually.** The tool handles this automatically based on your data.

---

## 📁 Input Data Requirements

### Data Format

Your CSV must be **pre-aggregated** — one row per entity × dimension combination:

```csv
issuer_name,card_type,channel,txn_cnt,approved_cnt,fraud_cnt
BANCO SANTANDER,CREDIT,POS,125000,108750,412
BANCO SANTANDER,CREDIT,ECOM,80000,68000,340
BANCO SANTANDER,DEBIT,POS,200000,186000,372
ITAU UNIBANCO,CREDIT,POS,180000,162000,540
```

### ✅ Data Checklist

Before running analysis, verify:

- [ ] **Entity names consistent** — `Santander` ≠ `SANTANDER` (case-sensitive!)
- [ ] **At least 4 entities** — Required for privacy compliance
- [ ] **No nulls** in entity or metric columns
- [ ] **Same currency** for all amounts
- [ ] **Pre-aggregated** — Tool doesn't sum raw transactions

> 💡 **Pro Tip:** Run `py benchmark.py config list` to see available presets before starting.

---

## 📋 CLI Reference

### Essential Commands

```powershell
# Share Analysis
py benchmark.py share --csv FILE --entity NAME --metric COLUMN --dimensions DIM1 DIM2

# Rate Analysis  
py benchmark.py rate --csv FILE --entity NAME --total-col COLUMN --approved-col COLUMN

# Configuration
py benchmark.py config list                    # Show presets
py benchmark.py config show PRESET             # View preset details
py benchmark.py config generate OUTPUT.yaml    # Create custom config
```

### All Flags

<details>
<summary><strong>📌 Click to expand full flag reference</strong></summary>

| Flag | Type | Description |
|------|------|-------------|
| `--csv` | Required | Input CSV file path |
| `--entity` | Optional | Target entity name (omit for peer-only) |
| `--entity-col` | Optional | Entity column name (default: `issuer_name`) |
| `--metric` | Share | Metric column for share analysis |
| `--total-col` | Rate | Denominator column |
| `--approved-col` | Rate | Approval numerator |
| `--fraud-col` | Rate | Fraud numerator |
| `--dimensions` | Optional | Space-separated dimension columns |
| `--auto` | Flag | Auto-detect dimensions |
| `--time-col` | Optional | Time column for temporal consistency |
| `--preset` | Optional | Use preset configuration |
| `--config` | Optional | Use custom YAML config |
| `--output` | Optional | Output file path |
| `--debug` | Flag | Include debug sheets |
| `--export-balanced-csv` | Flag | Export balanced CSV alongside Excel |

</details>

---

## 📈 Understanding Your Output

### Excel Report Structure

| Sheet | What's Inside | Always? |
|-------|---------------|---------|
| **Summary** | Inputs, settings, key stats | ✅ |
| **[Dimension]** | Per-category comparisons | ✅ |
| **Weight Methods** | How weights were calculated | ✅ |
| **Rank Changes** | Before/after peer rankings | ✅ |
| **Peer Weights** | Actual multipliers | `--debug` |
| **Privacy Validation** | Compliance verification | `--debug` |

### Reading the Results

```
           Entity    Peer Avg    BIC       Gap
CREDIT     45.2%     38.5%      48.1%    +6.7pp
           ▲         ▲          ▲        ▲
           Your      Weighted   Best in  You vs
           value     peer avg   Class    Peers
```

| Gap | Meaning |
|-----|---------|
| `+6.7pp` | You're **outperforming** peers by 6.7 percentage points |
| `-3.2pp` | You're **underperforming** peers |
| `0.0pp` | Exactly at peer average |

---

## 🚀 Common Workflows

### Workflow 1: Monthly Performance Report

```powershell
py benchmark.py rate ^
  --csv data/march_2024.csv ^
  --entity "BANCO SANTANDER" ^
  --total-col amt_total ^
  --approved-col amt_approved ^
  --dimensions card_type channel ^
  --preset balanced_default ^
  --output reports/march_2024_benchmark.xlsx
```

### Workflow 2: Regulatory Compliance Report

```powershell
py benchmark.py share ^
  --csv data/q1_aggregated.csv ^
  --entity "ITAU UNIBANCO" ^
  --metric transaction_count ^
  --dimensions flag_domestic card_type ^
  --preset compliance_strict ^
  --debug ^
  --output reports/q1_compliance.xlsx
```

### Workflow 3: Executive Dashboard Data

```powershell
py benchmark.py rate ^
  --csv data/ytd.csv ^
  --entity "BRADESCO" ^
  --total-col total ^
  --approved-col approved ^
  --fraud-col fraud ^
  --dimensions card_type merchant_category region ^
  --time-col year_month ^
  --preset strategic_consistency ^
  --export-balanced-csv ^
  --output reports/dashboard_data.xlsx
```

### Workflow 4: Market Landscape Analysis (No Target)

```powershell
py benchmark.py share ^
  --csv data/industry.csv ^
  --metric tpv ^
  --auto ^
  --preset balanced_default
```

> 💡 **Tip:** Omitting `--entity` runs peer-only analysis — great for understanding market structure.

---

## ❓ Frequently Asked Questions

<details>
<summary><strong>Why does my entity name not match?</strong></summary>

Entity names are **case-sensitive**. Check your CSV:
- ✅ `"BANCO SANTANDER"` matches `"BANCO SANTANDER"`
- ❌ `"Banco Santander"` does NOT match `"BANCO SANTANDER"`

**Fix:** Copy the exact name from your CSV.
</details>

<details>
<summary><strong>What does "LP Infeasible" mean?</strong></summary>

This is **normal** for complex datasets. It means the Linear Programming solver couldn't find weights satisfying all privacy constraints simultaneously.

**What happens:** The tool automatically falls back to per-dimension solving or Bayesian optimization.

**Check:** The Weight Methods sheet shows which method was used for each dimension.
</details>

<details>
<summary><strong>Can I analyze without a target entity?</strong></summary>

Yes! Omit the `--entity` flag for **peer-only mode**:

```powershell
py benchmark.py share --csv data.csv --metric txn_cnt --auto
```

This analyzes peer distributions without comparing to a specific entity.
</details>

<details>
<summary><strong>How do I export data for Tableau/PowerBI?</strong></summary>

Use the `--export-balanced-csv` flag:

```powershell
py benchmark.py rate --csv data.csv --total-col total --approved-col approved --export-balanced-csv
```

This creates `report_balanced.csv` with privacy-weighted totals ready for import.
</details>

<details>
<summary><strong>Why are some dimensions using different weight methods?</strong></summary>

When global weights can't satisfy privacy constraints for ALL dimensions, the tool:
1. Finds the largest subset that works globally
2. Solves remaining dimensions independently

Check the **Weight Methods** sheet to see:
- `Global-LP` — Solved with all dimensions
- `Per-Dimension-LP` — Solved independently
- `Per-Dimension-Bayesian` — LP failed, Bayesian fallback
</details>

---

## 🛠️ Troubleshooting

| Problem | Solution |
|---------|----------|
| 🔴 "Entity not found" | Names are **case-sensitive** — match exactly |
| 🔴 "Column not found" | Check column names after loading (lowercase + underscores) |
| 🟡 "No valid dimensions" | Use `--dimensions` explicitly instead of `--auto` |
| 🟡 High slack in output | Try `strategic_consistency` preset |
| 🟢 "LP Infeasible" | Normal! Tool uses fallback automatically |

### Debug Mode

Add `--debug` to any command for extra diagnostic sheets:

```powershell
py benchmark.py share --csv data.csv --entity "BANK" --metric txn_cnt --auto --debug
```

### Validate CSV Output

```powershell
py utils/csv_validator.py report.xlsx report_balanced.csv --verbose
```

---

## 📦 Installation

### Quick Install

```bash
pip install -r requirements.txt
```

### Dependencies

| Package | Purpose |
|---------|---------|
| `pandas` | Data processing |
| `numpy` | Numerical operations |
| `openpyxl` | Excel output |
| `PyYAML` | Configuration |
| `scipy` | LP optimization |
| `textual` | TUI framework |

### Server Deployment

For shared server deployment, see [SETUP.md](SETUP.md).

---

## 📚 Additional Resources

| Document | Purpose |
|----------|---------|
| [AGENTS.md](AGENTS.md) | AI agent development guide |
| [SETUP.md](SETUP.md) | Server deployment instructions |
| [utils/CSV_VALIDATOR_README.md](utils/CSV_VALIDATOR_README.md) | CSV validation documentation |

---

<div align="center">

**Built for Mastercard Privacy Compliance** · Version 3.0.0

</div>