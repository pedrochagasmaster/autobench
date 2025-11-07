# Privacy-Compliant Peer Benchmark Tool (v2.1)

**Status: Production-ready. All core features implemented and validated.**

## What is This Tool?

The Privacy-Compliant Peer Benchmark Tool is a sophisticated dimensional analysis system designed to compare financial entities (banks, issuers, merchants) against their peer groups while strictly enforcing Mastercard privacy compliance rules (Control 3.2). The tool enables you to understand how a target entity performs across multiple business dimensions without compromising the confidentiality of individual peer performance.

### Business Value

**For Strategic Analysis:**
- Compare your institution's performance against competitors across multiple dimensions (transaction types, card products, regions, etc.)
- Identify areas where you lead the market and areas needing improvement
- Understand market structure and peer distributions without requiring a specific benchmark target

**For Compliance:**
- Automatically enforces Mastercard Control 3.2 privacy rules
- Prevents single peer concentration from dominating benchmarks
- Provides full audit trails and transparency reports
- Validates privacy constraints across all dimensions and time periods

**For Decision Making:**
- Best-in-Class (BIC) percentile benchmarks show top-tier performance targets
- Balanced Peer Averages provide fair comparisons adjusting for market concentration
- Multi-dimensional insights reveal patterns across products, channels, geographies, and time

### What Makes This Tool Unique?

1. **Privacy-First Design**: Uses advanced Linear Programming (LP) optimization to compute peer weights that satisfy strict privacy caps while preserving market structure
2. **Dimensional Intelligence**: Automatically analyzes any dimensional breakdown in your data (product types, merchant categories, card types, regions, etc.)
3. **Time-Aware Consistency**: When analyzing time-series data, ensures weights remain consistent across all time periods and category combinations
4. **Transparent Diagnostics**: Provides detailed explanations of how weights were calculated, which dimensions were feasible, and where structural constraints exist
5. **Flexible Analysis Modes**: Supports share analysis (volume distribution), rate analysis (approval/fraud rates), peer-only mode (no target entity), and simultaneous multi-rate analysis

**New in v2.1:**
- **Peer-only mode**: Analyze peer distributions and market structure without specifying a target entity
- **Multi-rate analysis**: Simultaneously analyze approval rates and fraud rates in a single run with shared privacy-compliant weights
- **Time-aware consistency**: Global weights work across all time periods and categories, ensuring temporal consistency
- **Time-dimension output**: When `--time-col` is set, dimension sheets show metrics for each time-category combination plus aggregated "General" rows
- **Enhanced diagnostics**: Structural infeasibility analysis, subset search reporting, rank change tracking, and privacy validation sheets

This is the actively maintained v2 CLI. Legacy notebooks and experimental scripts are archived in the `old/` directory for reference only.

---

## Table of Contents

- [Core Features](#core-features)
- [Understanding the Analysis Types](#understanding-the-analysis-types)
- [Installation](#installation)
- [Quick Start Guide](#quick-start-guide)
- [Input Data Requirements](#input-data-requirements)
- [Command-Line Interface](#command-line-interface)
- [Privacy Rules and Compliance](#privacy-rules-and-compliance)
- [Analysis Modes](#analysis-modes)
- [Advanced Features](#advanced-features)
- [Excel Report Contents](#excel-report-contents)
- [Tuning and Optimization](#tuning-and-optimization)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Additional Documentation](#additional-documentation)

---

## Core Features

### Analysis Capabilities

**Share Analysis**: Understand how transaction volumes (count or amount) are distributed across dimensional categories
- Example: "What percentage of our domestic transactions are we capturing compared to peers?"
- Compares your entity's share in each category (e.g., domestic vs international, card-present vs card-not-present)
- Identifies categories where you're over-indexed or under-indexed vs the peer group

**Rate Analysis**: Analyze approval rates and/or fraud rates across business dimensions
- Approval Rate: What percentage of transactions are approved (higher is better)
- Fraud Rate: What percentage of approved transactions are fraudulent (lower is better)
- Example: "Is our approval rate for digital wallet transactions competitive with peers?"
- Both rates can be analyzed simultaneously with shared privacy-compliant weights

**Peer-Only Mode**: Analyze market structure and peer distributions without comparing to a specific target entity
- Useful for landscape analysis, market sizing, and understanding competitive dynamics
- All entities treated as peers with no target-specific comparisons

### Privacy Compliance

**Built-in Privacy Enforcement**: Automatically applies Mastercard Control 3.2 peer concentration caps
- Different caps based on peer count: 4/35, 5/25, 6/30, 7/35, 10/40
- Prevents any single peer from dominating the benchmark calculation
- Applied per category within each dimension after weighting adjustments

**Global Consistent Weighting** (optional): Calculates one set of peer weights that work across all dimensions
- Uses Linear Programming (LP) with rank-preserving objective to find optimal weights
- Ensures privacy compliance in every category of every dimension simultaneously
- Maintains consistency across time periods when `--time-col` is specified
- Includes tolerance modeling via slack variables with configurable penalties

**Time-Aware Consistency**: When analyzing time-series data, ensures privacy compliance across:
- Total monthly volumes (privacy rule for each month)
- Monthly category volumes (privacy rule for each month-dimension-category combination)
- Same peer weights satisfy all temporal and categorical constraints

### Transparency and Diagnostics

**Weight Methods Tab**: Shows exactly how weights were calculated for each dimension
- Identifies which method succeeded: Global LP, Per-Dimension LP, Heuristic, or Global Weights (dropped)
- Displays the actual multiplier applied to each peer
- Enables auditing and validation of the weighting methodology

**Subset Search Tab**: When searching for feasible global dimension subsets, records:
- Every attempted dimension combination
- Success/failure status and reasons
- Slack usage statistics (how much privacy caps were relaxed)
- Enables understanding of which dimension combinations are feasible together

**Structural Diagnostics**: Quantifies fundamental infeasibility drivers
- Structural Summary: Per-dimension counts of infeasible categories and worst margins
- Structural Detail: Row-level analysis showing which specific peer-category combinations are structurally impossible
- Helps decide whether to merge categories, relax bounds, or exclude dimensions

**Rank Changes**: Tracks how privacy adjustments affect peer ordering
- Shows baseline rank (by raw volume) vs adjusted rank (after privacy weights)
- Identifies which peers moved up or down and by how many positions
- Summary section highlights top movers by absolute rank delta

**Privacy Validation Sheet** (debug mode): Detailed compliance verification
- Shows original and balanced volume shares for every peer in every dimension-category-(time) combination
- Displays compliance status, privacy cap, tolerance, and violation margins
- Violations highlighted in red for immediate identification
- Enables granular validation that privacy rules are satisfied across all breaks

**Rich Excel Output**: Professional reports with multiple analytical sheets
- Summary sheet with metadata, inputs, and key findings
- One sheet per dimension with target vs peer comparisons
- Debug sheets showing unweighted metrics before privacy adjustments
- Full audit trail for regulatory and compliance review

---

## Understanding the Analysis Types

### Share Analysis: Volume Distribution

Share analysis examines how transaction volumes are distributed across dimensional categories. It answers questions like:
- "What percentage of total transaction volume occurs in each product category?"
- "How does our entity's distribution compare to the peer group?"

**What It Measures:**
- Your entity's share (%) in each category
- Balanced Peer Average share (%) after privacy adjustments
- Best-in-Class (BIC) performance at the 85th percentile
- Gap between your performance and peer benchmarks

**When to Use:**
- Understanding market positioning across product lines, channels, or regions
- Identifying over-indexed or under-indexed segments
- Strategic planning for market expansion or optimization

**Metrics Supported:**
- `transaction_count` (or alias `txn_cnt`): Number of transactions
- `transaction_amount` (or alias `tpv`): Total transaction value

**Example Output:**
```
Dimension: flag_domestic
Category        Target  Peer Avg  BIC    Gap
Domestic        65.3%   58.2%     68.1%  +7.1pp
International   34.7%   41.8%     31.9%  -7.1pp
```

This shows the entity is over-indexed in domestic transactions (+7.1pp above peer average) and under-indexed internationally.

### Rate Analysis: Approval and Fraud Rates

Rate analysis examines approval rates (percentage of transactions approved) and fraud rates (percentage of approved transactions that are fraudulent). It answers questions like:
- "Is our approval rate competitive with industry peers?"
- "Are we experiencing higher fraud rates than the peer group?"

**What It Measures:**
- Your entity's rate (%) in each category
- Balanced Peer Average rate (%) after privacy adjustments
- Best-in-Class (BIC) performance benchmarks:
  - Approval rate: 85th percentile (higher is better)
  - Fraud rate: 15th percentile (lower is better)
- Gap between your performance and peer benchmarks

**When to Use:**
- Evaluating authorization strategy effectiveness
- Benchmarking fraud detection and prevention performance
- Identifying dimensional segments with optimization opportunities
- Comparing performance across product types, channels, or risk segments

**Components Required:**
- `--total-col`: Denominator (total transactions or total approved)
- `--approved-col`: For approval rate analysis (optional if fraud-only)
- `--fraud-col`: For fraud rate analysis (optional if approval-only)
- Both can be specified for simultaneous multi-rate analysis

**Example Output (Approval Rate):**
```
Dimension: card_type
Category      Target  Peer Avg  BIC    Gap
Credit        89.2%   87.5%     91.3%  +1.7pp
Debit         92.8%   90.1%     94.2%  +2.7pp
Prepaid       85.4%   86.8%     89.6%  -1.4pp
```

**Example Output (Fraud Rate):**
```
Dimension: card_type
Category      Target  Peer Avg  BIC    Gap
Credit        0.34%   0.28%     0.15%  +0.06pp
Debit         0.19%   0.21%     0.10%  -0.02pp
Prepaid       0.42%   0.35%     0.18%  +0.07pp
```

### Peer-Only Mode: Market Landscape Analysis

Peer-only mode analyzes the collective peer group without comparing to a specific target entity. It answers questions like:
- "How is transaction volume distributed across peers in each category?"
- "What does the competitive landscape look like?"
- "What are the peer concentration levels before privacy adjustments?"

**What It Measures:**
- Balanced Peer Average (%) across all peers
- Distribution statistics (10th, 25th, 50th, 75th, 90th percentiles)
- Best-in-Class (BIC) performance benchmarks
- No target-specific comparisons

**When to Use:**
- Exploratory analysis before selecting a benchmark target
- Understanding overall market structure and concentration
- Establishing baseline benchmarks for reporting
- Academic or research analysis without a specific entity focus

**How to Use:**
- Simply omit the `--entity` parameter from your command
- All entities in the dataset are treated as peers
- Output files named with `PEER_ONLY` identifier

**Key Differences from Target Mode:**
- Peer count = total unique entities (not unique entities - 1)
- No target columns in output: `target_share`, `target_rate`, `target_rank`, `delta`
- All dimensional analysis focuses on peer distributions only

---

## Installation

### System Requirements

**Operating System:**
- Windows 10/11 (PowerShell v5.1 or later)
- macOS 10.14+ (with bash or zsh)
- Linux (any modern distribution)

**Python Requirements:**
- Python 3.10 or higher (tested on Python 3.12)
- pip package manager
- Virtual environment support recommended

**Hardware:**
- Minimum: 4GB RAM, 2 CPU cores
- Recommended: 8GB+ RAM, 4+ CPU cores for large datasets
- Disk space: 500MB for installation, additional space for data and reports

### Dependencies

The tool requires the following Python packages (automatically installed via `requirements.txt`):

**Core Data Processing:**
- `pandas>=1.3.0`: Data manipulation and analysis
- `numpy>=1.21.0`: Numerical computing
- `python-dateutil>=2.8.0`: Date/time utilities

**Excel Support:**
- `openpyxl>=3.0.0`: Excel file reading and writing with formatting

**Optimization:**
- `scipy>=1.8.0`: **Recommended** - Enables strict LP solver (HiGHS) for global weight optimization
  - Without SciPy: Tool falls back to heuristic weighting (still privacy-compliant but less optimal)
  - With SciPy: Uses advanced Linear Programming for best weight solutions

**Machine Learning:**
- `scikit-learn>=1.0.0`: Distance calculations and similarity metrics

**Optional Database Support:**
- `pypyodbc>=1.3.6`: SQL database connectivity (only needed if using SQL data sources)

### Installation Steps

#### Windows (PowerShell)

**Option 1: Automated Setup (Recommended)**

The repository includes a PowerShell setup script that verifies your environment and installs everything automatically:

```powershell
# Navigate to the tool directory
cd "c:\Users\YourName\Documents\Peer Benchmark Tool"

# Run the setup script
.\setup.ps1
```

The script will:
1. Check Python version (requires 3.8+, recommends 3.10+)
2. Verify pip is installed and up-to-date
3. Install all required dependencies from `requirements.txt`
4. Create necessary directories (`data/`, `output/`)
5. Verify the installation by running a test command
6. Display usage examples

**Option 2: Manual Installation**

If you prefer manual setup or the script fails:

```powershell
# Verify Python installation
python --version  # Should show Python 3.10 or higher

# Upgrade pip to latest version
python -m pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Verify installation
python benchmark.py --help
```

#### macOS / Linux

```bash
# Verify Python installation
python3 --version  # Should show Python 3.10 or higher

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # macOS/Linux

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Verify installation
python benchmark.py --help
```

### Virtual Environment Setup (Recommended)

Using a virtual environment isolates the tool's dependencies from your system Python:

**Windows PowerShell:**
```powershell
# Create virtual environment
python -m venv venv

# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# When done, deactivate
deactivate
```

**macOS/Linux:**
```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# When done, deactivate
deactivate
```

### Verifying Installation

After installation, verify everything works:

```powershell
# Check CLI is accessible
python benchmark.py --help

# List available presets
python benchmark.py presets

# View share analysis help
python benchmark.py share --help

# View rate analysis help
python benchmark.py rate --help
```

If all commands execute without errors, your installation is complete!

### Troubleshooting Installation

**Python Not Found:**
- Windows: Install from [python.org](https://www.python.org/downloads/) and ensure "Add Python to PATH" is checked
- macOS: Install via Homebrew: `brew install python3`
- Linux: Use package manager: `sudo apt install python3 python3-pip`

**Permission Errors:**
- Windows: Run PowerShell as Administrator
- macOS/Linux: Use `sudo` for system-wide installation or use virtual environment

**SciPy Installation Fails:**
- Windows: May require Visual C++ Build Tools from [Microsoft](https://visualstudio.microsoft.com/downloads/)
- Alternative: Use pre-built wheels from [https://www.lfd.uci.edu/~gohlke/pythonlibs/](https://www.lfd.uci.edu/~gohlke/pythonlibs/)

**Import Errors:**
- Ensure you're using the same Python interpreter that installed the packages
- Check virtual environment is activated if you created one
- Verify all packages in `requirements.txt` installed successfully: `pip list`

---

## Input Data Requirements

### Overview

The tool accepts aggregated transactional data in CSV format (SQL support available via configuration). Data must be pre-aggregated by entity and dimensions - the tool does not aggregate raw transactions.

**Key Concept**: Each row represents the performance of one entity in one specific dimensional combination. For example:
- Row 1: Bank A, Domestic, Card Present, 1000 transactions
- Row 2: Bank A, Domestic, Card Not Present, 500 transactions
- Row 3: Bank A, International, Card Present, 200 transactions
- etc.

### Data Normalization

The `DataLoader` automatically normalizes column names for consistency:
- Converts to lowercase
- Replaces spaces with underscores
- Maps common aliases to standardized names

All column mappings are defined in `utils/config_manager.py`. You can extend these mappings if your data uses different column names.

### Required Columns

#### For SHARE Analysis

**Entity Identifier Column:**
- **Purpose**: Identifies each entity (bank, issuer, merchant)
- **Default name**: `issuer_name`
- **Can override** with `--entity-col` parameter
- **Recognized aliases**:
  - `issuer_name`
  - `merchant_id`, `merchant_name`
  - `bank_name`
  - `institution_name`
- **Data type**: String
- **Example values**: "BANCO SANTANDER", "ITAU UNIBANCO", "BRADESCO"

**Metric Column (choose one):**

1. **Transaction Count** (for count-based share analysis):
   - **Standardized name**: `transaction_count`
   - **Recognized aliases**: `txn_count`, `txn_cnt`, `total_txns`, `count`, `cnt`
   - **Data type**: Integer (positive)
   - **Represents**: Number of transactions in this entity-dimension combination
   - **Use CLI parameter**: `--metric transaction_count` or `--metric txn_cnt`

2. **Transaction Amount** (for value-based share analysis):
   - **Standardized name**: `transaction_amount`
   - **Recognized aliases**: `txn_amt`, `total_amount`, `tpv`, `amount`, `volume`
   - **Data type**: Float/Decimal (positive)
   - **Represents**: Total monetary value of transactions (in any currency, but must be consistent)
   - **Use CLI parameter**: `--metric transaction_amount` or `--metric tpv`

#### For RATE Analysis

**Entity Identifier Column:** (same as share analysis above)

**Total Column (Required):**
- **Purpose**: Denominator for rate calculation
- **Specified with**: `--total-col <column_name>`
- **Data type**: Integer (positive)
- **For approval rates**: Total transactions attempted
- **For fraud rates**: Total approved transactions
- **Example column names**: `total_count`, `auth_total`, `app_cnt`

**Numerator Column(s) (At least one required):**

1. **Approved Column** (for approval rate analysis):
   - **Purpose**: Numerator for approval rate calculation
   - **Specified with**: `--approved-col <column_name>`
   - **Recognized aliases**: `appr_txns`, `approved_count`, `auth_approved`, `appr_count`
   - **Data type**: Integer (positive, ≤ total_col value)
   - **Formula**: Approval Rate = approved_count / total_count × 100%
   - **Example**: If total=1000 and approved=850, approval rate = 85%

2. **Fraud Column** (for fraud rate analysis):
   - **Purpose**: Numerator for fraud rate calculation
   - **Specified with**: `--fraud-col <column_name>`
   - **Recognized aliases**: `fraud_cnt`, `qt_fraud`, `fraud_tran`
   - **Data type**: Integer (positive, ≤ total_col value for fraud rates)
   - **Formula**: Fraud Rate = fraud_count / approved_count × 100%
   - **Example**: If approved=850 and fraud=7, fraud rate = 0.82%

**Note on Multi-Rate Analysis:**
- You can specify **both** `--approved-col` and `--fraud-col` in the same command
- The tool performs both analyses simultaneously with shared privacy weights
- Results are combined in a single Excel file with side-by-side metrics
- Privacy constraints based on the shared denominator ensure consistency

### Dimensional Columns

**Purpose**: Define business dimensions for breakdown analysis (product types, channels, regions, risk segments, etc.)

**How to specify**:
- **Auto-detection**: Use `--auto` flag to automatically analyze all non-metric, non-entity columns
- **Manual selection**: Use `--dimensions col1 col2 col3` to specify exact columns

**Data type**: String or Integer (categorical values)

**Common Examples**:
- `flag_domestic`: Domestic vs International (values: "D", "I" or "Domestic", "International")
- `cp_cnp`: Card Present vs Card Not Present (values: "CP", "CNP")
- `card_type`: Card product type (values: "CREDIT", "DEBIT", "PREPAID")
- `merchant_category`: MCC categories (values: "GROCERIES", "FUEL", "RESTAURANTS")
- `product_group`: Product groupings (values: "PREMIUM", "STANDARD", "BASIC")
- `risk_segment`: Risk-based segments (values: "LOW_RISK", "MEDIUM_RISK", "HIGH_RISK")
- `channel`: Transaction channel (values: "POS", "ECOMMERCE", "ATM", "MOBILE")
- `ano_mes` or `year_month`: Time period (values: "2024-01", "2024-02", etc.)

**Best Practices**:
- Use clear, descriptive values
- Keep categories mutually exclusive within each dimension
- Avoid too many categories (>20) in a single dimension as it may cause privacy constraint issues
- If using time dimensions with `--time-col`, ensure the time column uses sortable values

### Optional: Time Column

**Purpose**: Enable time-aware consistency for analyses spanning multiple time periods

**Specified with**: `--time-col <column_name>`

**Common names**: `ano_mes`, `year_month`, `month`, `period`, `date`

**Data type**: String or Date (must be sortable)

**Format examples**:
- `2024-01`, `2024-02`, `2024-03` (YYYY-MM format)
- `202401`, `202402`, `202403` (YYYYMM format)
- `2024Q1`, `2024Q2` (quarterly)
- `Jan-2024`, `Feb-2024` (month-year)

**When to use**:
- Analyzing performance across multiple months/quarters
- Ensuring peer weights remain consistent across all time periods
- Requires `--consistent-weights` flag to enable time-aware consistency mode
- Creates constraints for both monthly totals and monthly category combinations

**Effect on output**:
- Dimension sheets include rows for each time-category combination
- Plus "General" aggregated rows showing overall performance across time
- Example: For dimension `card_type` and time periods Jan/Feb/Mar, you'll see:
  - CREDIT (Jan), CREDIT (Feb), CREDIT (Mar), CREDIT (General)
  - DEBIT (Jan), DEBIT (Feb), DEBIT (Mar), DEBIT (General)
  - etc.

### Example Data Structure

**Share Analysis Example (CSV):**
```csv
issuer_name,flag_domestic,cp_cnp,card_type,transaction_count,transaction_amount
BANCO SANTANDER,Domestic,CP,CREDIT,125000,15000000.00
BANCO SANTANDER,Domestic,CP,DEBIT,200000,8000000.00
BANCO SANTANDER,Domestic,CNP,CREDIT,80000,12000000.00
BANCO SANTANDER,International,CP,CREDIT,15000,3000000.00
ITAU UNIBANCO,Domestic,CP,CREDIT,180000,22000000.00
ITAU UNIBANCO,Domestic,CP,DEBIT,250000,10000000.00
```

**Rate Analysis Example (CSV):**
```csv
issuer_name,flag_domestic,card_type,total_count,approved_count,fraud_count
BANCO SANTANDER,Domestic,CREDIT,125000,108750,412
BANCO SANTANDER,Domestic,DEBIT,200000,186000,372
BANCO SANTANDER,International,CREDIT,15000,12000,78
ITAU UNIBANCO,Domestic,CREDIT,180000,162000,540
ITAU UNIBANCO,Domestic,DEBIT,250000,235000,475
```

**Time-Series Example (CSV):**
```csv
issuer_name,ano_mes,flag_domestic,card_type,transaction_count
BANCO SANTANDER,2024-01,Domestic,CREDIT,40000
BANCO SANTANDER,2024-02,Domestic,CREDIT,42000
BANCO SANTANDER,2024-03,Domestic,CREDIT,43000
BANCO SANTANDER,2024-01,Domestic,DEBIT,65000
BANCO SANTANDER,2024-02,Domestic,DEBIT,67000
```

### Data Quality Requirements

**Completeness:**
- All required columns must be present (will error if missing)
- No NULL values in entity identifier or metric columns
- Dimensional columns can have NULL/empty values (treated as a category)

**Consistency:**
- Currency must be consistent across all rows (tool doesn't convert currencies)
- Time formats must be consistent if using `--time-col`
- Entity names must be consistent (case-sensitive): "Santander" ≠ "SANTANDER"

**Granularity:**
- Data must be pre-aggregated (tool doesn't sum transaction-level records)
- Each row represents one entity × dimension1 × dimension2 × ... combination
- Typically monthly aggregates, but can be any consistent period

**Validation:**
- For rate analysis: approved_count ≤ total_count
- For fraud analysis: fraud_count ≤ approved_count (if fraud is of approved transactions)
- All counts/amounts must be non-negative
- At least 4 unique entities required for privacy compliance (warns if <4)

### Tips for Data Preparation

1. **Entity Naming**: Use consistent, official entity names. The tool is case-sensitive.
2. **Dimension Values**: Use short, clear codes rather than long descriptions (easier to read in reports).
3. **Aggregation Level**: Monthly aggregation is typical and works well with time-aware consistency.
4. **Missing Combinations**: If an entity-dimension combination has zero transactions, you can either:
   - Include it with 0 values (preferred for completeness)
   - Omit it (tool treats missing as zero)
5. **Currency**: If using `transaction_amount`, convert all values to a single currency before analysis.
6. **Preprocessing**: Remove test entities, invalid transactions, and outliers before aggregation.
7. **Dimension Cardinality**: Dimensions with 100+ categories may cause performance issues; consider grouping.

### Extending Column Mappings

If your data uses custom column names not recognized by the tool, you can extend the mappings in `utils/config_manager.py`:

```python
DEFAULT_COLUMN_MAPPING = {
    # Your custom column names
    'your_entity_column': 'entity_identifier',
    'your_txn_column': 'transaction_count',
    # ... add more mappings
}
```

Alternatively, rename your columns in the CSV to match the tool's standardized names or recognized aliases.

---

## Quick Start Guide

This section provides practical examples to get you started quickly. All examples use Windows PowerShell syntax, but they work on macOS/Linux with minor path adjustments (`\` → `/`).

### Basic Commands

**Note on Python Launcher**: These examples use `py` (Windows Python Launcher) which automatically uses the correct Python version. On macOS/Linux, use `python3` instead.

### Example 1: Basic Share Analysis with Auto-Detection

**Scenario**: You want to understand how Banco Santander's transaction volume is distributed across all available dimensions.

**Command:**
```powershell
py benchmark.py share `
  --csv data\sample.csv `
  --entity "BANCO SANTANDER" `
  --metric transaction_count `
  --auto
```

**What this does:**
- **`share`**: Runs share analysis (volume distribution)
- **`--csv data\sample.csv`**: Loads data from the specified CSV file
- **`--entity "BANCO SANTANDER"`**: Compares this entity against peers
- **`--metric transaction_count`**: Analyzes transaction count distribution
- **`--auto`**: Automatically detects and analyzes all dimensional columns

**Output**: Excel file with one sheet per dimension showing:
- Santander's share (%) in each category
- Balanced Peer Average (%) after privacy adjustments
- Best-in-Class (85th percentile)
- Gap from peer average

**File naming**: `benchmark_share_BANCO_SANTANDER_20241107_143022.xlsx`

---

### Example 2: Share Analysis with Manual Dimension Selection

**Scenario**: You only want to analyze specific dimensions (domestic/international, card present/not present, purchase type).

**Command:**
```powershell
py benchmark.py share `
  --csv data\sample.csv `
  --entity "BANCO SANTANDER" `
  --metric transaction_amount `
  --dimensions flag_domestic cp_cnp tipo_compra
```

**What this does:**
- Same as Example 1, but:
- **`--metric transaction_amount`**: Analyzes value (TPV) distribution instead of count
- **`--dimensions flag_domestic cp_cnp tipo_compra`**: Only analyzes these three dimensions

**When to use**: When you know exactly which dimensions matter for your analysis and want faster execution.

---

### Example 3: Peer-Only Mode (No Target Entity)

**Scenario**: You want to understand the overall peer landscape without comparing to a specific entity.

**Command:**
```powershell
py benchmark.py share `
  --csv data\sample.csv `
  --metric transaction_count `
  --auto
```

**What this does:**
- **No `--entity` parameter**: Treats all entities as peers
- Provides peer distribution statistics without target-specific comparisons
- Useful for market research and exploratory analysis

**Output differences**:
- No "Target" columns in dimension sheets
- Filename includes `PEER_ONLY` identifier
- Peer count = total unique entities (not unique entities - 1)

---

### Example 4: Approval Rate Analysis

**Scenario**: You want to benchmark Santander's approval rates across dimensions.

**Command:**
```powershell
py benchmark.py rate `
  --csv data\sample.csv `
  --entity "BANCO SANTANDER" `
  --total-col total_count `
  --approved-col approved_count `
  --auto
```

**What this does:**
- **`rate`**: Runs rate analysis mode
- **`--total-col total_count`**: Column with total transactions (denominator)
- **`--approved-col approved_count`**: Column with approved transactions (numerator)
- **`--auto`**: Analyzes all dimensions

**Formula**: Approval Rate = approved_count / total_count × 100%

**Output**: Shows approval rates with 85th percentile BIC (higher is better).

---

### Example 5: Fraud Rate Analysis

**Scenario**: You want to benchmark fraud rates to identify high-risk segments.

**Command:**
```powershell
py benchmark.py rate `
  --csv data\sample.csv `
  --entity "BANCO SANTANDER" `
  --total-col total_count `
  --fraud-col fraud_count `
  --auto
```

**What this does:**
- **`--fraud-col fraud_count`**: Column with fraud transactions
- Tool automatically uses 15th percentile BIC for fraud (lower is better)

**Formula**: Fraud Rate = fraud_count / total_count × 100%

**Interpretation**: Categories where you're below peer average and BIC are performing well.

---

### Example 6: Multi-Rate Analysis (Approval + Fraud Simultaneously)

**Scenario**: You want to analyze both approval and fraud rates in a single run for comprehensive insights.

**Command:**
```powershell
py benchmark.py rate `
  --csv data\sample.csv `
  --entity "BANCO SANTANDER" `
  --total-col total_count `
  --approved-col approved_count `
  --fraud-col fraud_count `
  --dimensions flag_domestic card_type
```

**What this does:**
- **Both `--approved-col` and `--fraud-col`**: Analyzes both rates simultaneously
- Single Excel file with combined dimension sheets showing both metrics side-by-side
- Shared privacy-compliant weights ensure consistency
- Approval metrics in green, fraud metrics in orange (color-coded headers)

**Key advantage**: Efficient single-pass analysis with consistent privacy weighting.

---

### Example 7: Time-Aware Consistency

**Scenario**: You're analyzing 3 months of data and want peer weights that remain consistent across all time periods.

**Command:**
```powershell
py benchmark.py share `
  --csv data\sample.csv `
  --entity "BANCO SANTANDER" `
  --metric transaction_count `
  --auto `
  --consistent-weights `
  --time-col ano_mes `
  --debug
```

**What this does:**
- **`--consistent-weights`**: Calculates one global set of peer weights
- **`--time-col ano_mes`**: Specifies the time period column
- **`--debug`**: Includes debug sheets (Peer Weights, original metrics)

**Result**: 
- Same peer weights applied across all months and all dimension-category-month combinations
- Dimension sheets show rows for each category-month combination plus "General" aggregates
- Privacy constraints satisfied in every month and every category of every dimension

**When to use**: Time-series analysis where you need temporal consistency in benchmarks.

---

### Example 8: Advanced Subset Search

**Scenario**: You have many dimensions and want the tool to find the largest set of dimensions that can use global consistent weights.

**Command:**
```powershell
py benchmark.py share `
  --csv data\sample.csv `
  --entity "BANCO SANTANDER" `
  --metric transaction_count `
  --auto `
  --consistent-weights `
  --auto-subset-search `
  --subset-search-max-tests 500 `
  --debug
```

**What this does:**
- **`--auto-subset-search`**: Automatically searches for largest feasible dimension subset
- If full LP is infeasible, searches for best subset that works
- Records all attempts in the Subset Search tab
- Can use greedy or random search mode (see below)
- **`--subset-search-max-tests 500`**: Allows up to 500 search attempts (default: 200)
- **`--debug`**: Includes Subset Search tab showing all attempts

**Use case**: When full LP with all dimensions is infeasible, this finds the best subset that works.

---

### Example 9: Custom Output File and Parameters

**Scenario**: You want fine control over the output file name and privacy parameters.

**Command:**
```powershell
py benchmark.py share `
  --csv data\transactions_q1.csv `
  --entity "BANCO SANTANDER" `
  --metric transaction_count `
  --dimensions flag_domestic cp_cnp card_type `
  --output reports\santander_q1_analysis.xlsx `
  --bic-percentile 0.90 `
  --consistent-weights `
  --max-weight 5.0 `
  --tolerance 2.0 `
  --debug
```

**What this does:**
- **`--output reports\santander_q1_analysis.xlsx`**: Custom output filename
- **`--bic-percentile 0.90`**: 90th percentile BIC instead of default 85th
- **`--max-weight 5.0`**: Limits peer weight multipliers to 5× (default: 10×)
- **`--tolerance 2.0`**: Allows 2 percentage points tolerance on privacy caps (default: 1.0)

**When to use**: When you need stricter control or more relaxed privacy constraints.

---

### Example 10: Peer-Only Multi-Rate with Time Awareness

**Scenario**: Analyze peer group approval and fraud trends across time without a target entity.

**Command:**
```powershell
py benchmark.py rate `
  --csv data\monthly_data.csv `
  --total-col amt_total `
  --approved-col amt_approved `
  --fraud-col amt_fraud `
  --dimensions product_group flag_domestic `
  --consistent-weights `
  --time-col year_month `
  --debug
```

**What this does:**
- **No `--entity`**: Peer-only mode
- **Both rate types**: Simultaneous approval and fraud analysis
- **Time-aware**: Consistent weights across all months
- **Multi-dimensional**: Analyzes product groups and domestic/international

**Output**: Comprehensive peer landscape report showing how approval and fraud rates vary across products, regions, and time.

---

### Command Syntax Tips

**PowerShell Line Continuation:**
- Use backtick `` ` `` at end of line to continue on next line
- Makes long commands more readable

**Quoting Entity Names:**
- Use quotes if entity name contains spaces: `--entity "BANCO SANTANDER"`
- No quotes needed if no spaces: `--entity Santander`

**Path Separators:**
- Windows PowerShell: Use backslash `\` → `data\sample.csv`
- macOS/Linux: Use forward slash `/` → `data/sample.csv`

**Multiple Dimensions:**
- Space-separated list: `--dimensions dim1 dim2 dim3`
- No commas or quotes needed

---

### Next Steps

After running your first analysis:

1. **Review the Excel Output**: Open the generated file and examine the Summary sheet first
2. **Check Dimension Sheets**: Look at each dimension to understand your positioning
3. **Review Weight Methods** (if using `--consistent-weights`): See how weights were calculated
4. **Examine Debug Sheets** (if using `--debug`): Compare weighted vs unweighted metrics
5. **Read Subset Search Results** (if used): Understand which dimension combinations are feasible

For more advanced usage, see the [Command-Line Interface](#command-line-interface) section below.

---

## Command-Line Interface

### Overview

The tool provides two main analysis commands (`share` and `rate`) plus a `presets` command for viewing available configurations. Each command has its own set of parameters, though many are shared between them.

### Getting Help

```powershell
# General help
python benchmark.py --help

# Share analysis help
python benchmark.py share --help

# Rate analysis help
python benchmark.py rate --help

# List available presets
python benchmark.py presets
```

### General Parameters (Both Share and Rate)

These parameters apply to both share and rate analysis:

#### Data Source
- **`--csv <path>`** (Required)
  - Path to input CSV file
  - Can be absolute or relative path
  - Windows example: `--csv data\transactions.csv`
  - macOS/Linux example: `--csv data/transactions.csv`

#### Entity Identification
- **`--entity <name>`** (Optional for peer-only mode)
  - Name of target entity to benchmark
  - Must exactly match entity name in data (case-sensitive)
  - Omit for peer-only analysis (no target)
  - Example: `--entity "BANCO SANTANDER"`

- **`--entity-col <column>`** (Optional, default: `issuer_name`)
  - Name of column containing entity identifiers
  - Override if your data uses different column name
  - Example: `--entity-col bank_name`

#### Output Control
- **`--output <path>`** or **`-o <path>`** (Optional)
  - Custom output file path for Excel report
  - If omitted, auto-generates filename with timestamp
  - Multi-rate analysis: Single file with combined sheets
  - Example: `--output reports\q1_analysis.xlsx`

#### Analysis Configuration
- **`--bic-percentile <float>`** (Optional, default: 0.85)
  - Percentile for Best-in-Class calculation
  - Share/Approval: 0.85 = 85th percentile (higher is better)
  - Fraud: Tool automatically uses 0.15 = 15th percentile (lower is better)
  - Range: 0.0 to 1.0
  - Example: `--bic-percentile 0.90` for 90th percentile

#### Dimension Selection (Choose One)
- **`--dimensions <col1> <col2> ...`** (Manual selection)
  - Space-separated list of dimension column names
  - Analyzes only specified dimensions
  - Faster than auto-detection
  - Example: `--dimensions flag_domestic cp_cnp card_type`

- **`--auto`** (Auto-detection)
  - Automatically detects all non-entity, non-metric columns as dimensions
  - Convenient but may include unwanted columns
  - Mutually exclusive with `--dimensions`

#### Logging and Debug
- **`--log-level {DEBUG,INFO,WARNING,ERROR}`** (Optional, default: INFO)
  - Controls verbosity of console and log file output
  - DEBUG: Detailed diagnostic information
  - INFO: General progress information
  - WARNING: Only warnings and errors
  - ERROR: Only errors
  - Example: `--log-level DEBUG`

- **`--debug`** (Optional flag)
  - Enables comprehensive debug output in Excel report
  - **Adds Peer Weights tab** showing balanced/unbalanced volumes and multipliers
  - **Adds original metrics columns** in dimension sheets:
    - Share analysis: Original Peer Average (%), Original Total Volume, Weight Effect (pp)
    - Rate analysis: Original Peer Average (%), Original Total Numerator, Original Total Denominator, Weight Effect (pp)
  - **Adds Privacy Validation tab** (when used with `--consistent-weights`)
  - Recommended for auditing and understanding weight adjustments
  - Example: `--debug`

#### Global Weighting
- **`--consistent-weights`** (Optional flag)
  - Calculates ONE set of peer weights applied across ALL dimensions
  - Uses Linear Programming to find optimal weights satisfying privacy constraints globally
  - Without this flag: Each dimension gets independent weights (per-dimension mode)
  - More computationally intensive but ensures consistency
  - Recommended for cross-dimensional comparability
  - Example: `--consistent-weights`

#### Time-Aware Analysis
- **`--time-col <column>`** (Optional)
  - Name of time period column in your data
  - Enables time-aware consistency when used with `--consistent-weights`
  - Must contain sortable time values (YYYY-MM, YYYYMM, etc.)
  - Dimension sheets will show time-category combinations plus "General" aggregates
  - Example: `--time-col ano_mes`

#### Preset Configurations
- **`--preset <name>`** (Optional)
  - Apply predefined configuration preset
  - Presets defined in `presets.json`
  - View available presets: `python benchmark.py presets`
  - Example: `--preset conservative`

### Weight Optimization Parameters

These advanced parameters control the Linear Programming solver behavior when `--consistent-weights` is enabled:

#### Basic Constraints
- **`--max-iterations <int>`** (Optional, default: 1000)
  - Maximum iterations for weight convergence
  - Higher values allow more optimization attempts
  - Range: 100-10000 typical
  - Example: `--max-iterations 2000`

- **`--tolerance <float>`** (Optional, default: 1.0)
  - Tolerance for privacy violations in percentage points
  - Lower = stricter privacy enforcement
  - Higher = more flexibility (easier to find solutions)
  - Range: 0.5-5.0 typical
  - Example: `--tolerance 2.0`

- **`--max-weight <float>`** (Optional, default: 10.0)
  - Maximum peer weight multiplier allowed
  - Limits how much any peer's weight can be increased
  - Higher = more flexibility, but can distort benchmarks
  - Range: 2.0-100.0 typical
  - Example: `--max-weight 5.0`

- **`--min-weight <float>`** (Optional, default: 0.01)
  - Minimum peer weight multiplier allowed
  - Limits how much any peer's weight can be decreased
  - Lower = more flexibility
  - Range: 0.001-0.5 typical
  - Example: `--min-weight 0.05`

- **`--volume-preservation <float>`** (Optional, default: 0.5)
  - Strength of rank preservation in optimization (0.0-1.0)
  - 0.0 = No rank preservation (weights can freely reorder peers)
  - 1.0 = Strong rank preservation (maintain original peer ordering)
  - Controls how much the LP tries to preserve original peer market share ranking
  - Also known as rank_preservation_strength internally
  - Example: `--volume-preservation 0.2`

#### Advanced Search Options

- **`--prefer-slacks-first`** (Optional flag)
  - Try full-dimension LP with slacks-first approach before dropping dimensions
  - Sets rank penalty to 0 initially to probe feasibility with slack variables
  - Useful for diagnosing whether infeasibility is due to rank constraints
  - Example: `--prefer-slacks-first`

- **`--auto-subset-search`** (Optional flag)
  - Automatically search for largest feasible global dimension subset
  - If full LP is infeasible, searches for best subset that works
  - Records all attempts in "Subset Search" Excel tab
  - Can use greedy or random search mode (see below)
  - Example: `--auto-subset-search`

- **`--subset-search-max-tests <int>`** (Optional, default: 200)
  - Maximum attempts during subset search
  - Higher = more thorough search, longer runtime
  - Only applies when `--auto-subset-search` is enabled
  - Range: 50-1000 typical
  - Example: `--subset-search-max-tests 500`

- **`--greedy-subset-search`** (Optional flag, DEFAULT)
  - Use greedy search algorithm for subset search
  - Removes most unbalanced dimension one at a time
  - Attempts to re-add dimensions after each removal
  - Fast and deterministic
  - This is the default behavior
  - Example: `--greedy-subset-search`

- **`--no-greedy-subset-search`** (Optional flag)
  - Use random search algorithm instead of greedy
  - Tests random dimension combinations: n-1, n-2, n-3, ...
  - More thorough but non-deterministic
  - Useful when greedy gets stuck or produces suboptimal results
  - Example: `--no-greedy-subset-search`

- **`--trigger-subset-on-slack`** (Optional flag, DEFAULT)
  - Trigger subset search if LP uses excessive slack
  - Even if LP returns "success," checks if slack usage is too high
  - Helps find solutions with less cap relaxation
  - This is the default behavior
  - Example: `--trigger-subset-on-slack`

- **`--no-trigger-subset-on-slack`** (Optional flag)
  - Disable automatic subset search on slack usage
  - Only triggers subset search on explicit LP failure
  - Example: `--no-trigger-subset-on-slack`

- **`--max-cap-slack <float>`** (Optional, default: 0.0)
  - Slack sum threshold as percentage of total volume
  - If LP slack exceeds this, subset search is triggered
  - 0.0 = trigger on any slack usage
  - Higher values allow more slack before triggering
  - Range: 0.0-5.0 typical
  - Example: `--max-cap-slack 1.0`

### Share Analysis Specific Parameters

#### Metric Selection (Required)
- **`--metric {txn_cnt, tpv, transaction_count, transaction_amount}`** (Required)
  - Metric to analyze for share distribution
  - **transaction_count** or **txn_cnt**: Count of transactions
  - **transaction_amount** or **tpv**: Total transaction value
  - Example: `--metric transaction_count`

### Rate Analysis Specific Parameters

#### Columns (Required)
- **`--total-col <column>`** (Required)
  - Column containing denominator for rate calculation
  - For approval rate: total transactions attempted
  - For fraud rate: typically approved transactions
  - Example: `--total-col amt_total`

- **`--approved-col <column>`** (Optional, but one of approved/fraud required)
  - Column containing approved transactions (numerator for approval rate)
  - Formula: Approval Rate = approved_col / total_col × 100%
  - BIC automatically set to 85th percentile (higher is better)
  - Example: `--approved-col amt_approved`

- **`--fraud-col <column>`** (Optional, but one of approved/fraud required)
  - Column containing fraud transactions (numerator for fraud rate)
  - Formula: Fraud Rate = fraud_col / total_col × 100%
  - BIC automatically set to 15th percentile (lower is better)
  - Example: `--fraud-col amt_fraud`

**Note:** You can specify **both** `--approved-col` and `--fraud-col` for simultaneous multi-rate analysis. The tool will generate a single Excel file with both rate types shown side-by-side in each dimension sheet.

#### Weight Parameters
All weight optimization parameters listed above (`--max-iterations`, `--tolerance`, `--max-weight`, `--min-weight`, `--volume-preservation`, and advanced search options) are fully supported for rate analysis with identical behavior.

### Parameter Combination Guidelines

**Minimal Run (Share)**:
```powershell
python benchmark.py share --csv data.csv --entity "Bank A" --metric txn_cnt --auto
```

**Minimal Run (Rate)**:
```powershell
python benchmark.py rate --csv data.csv --entity "Bank A" --total-col total --approved-col approved --auto
```

**Production Run with Global Weights**:
```powershell
python benchmark.py share --csv data.csv --entity "Bank A" --metric txn_cnt --dimensions dim1 dim2 dim3 --consistent-weights --debug --output report.xlsx
```

**Advanced Tuning Run**:
```powershell
python benchmark.py share --csv data.csv --entity "Bank A" --metric txn_cnt --auto --consistent-weights --time-col month --auto-subset-search --no-greedy-subset-search --subset-search-max-tests 500 --max-weight 5.0 --tolerance 2.0 --debug
```

---

General

  - `--csv <path>`: Input CSV file
  - `--entity <name>`: Target entity (optional - omit for peer-only mode)
  - `--entity-col <col>`: Entity identifier (default `issuer_name`)
  - `--output/-o <file>`: Excel output (auto‑named if omitted; multi-rate adds suffix)
  - `--bic-percentile <float>`: Default 0.85 for approval rates
  - `--log-level {DEBUG,INFO,WARNING,ERROR}`: Default INFO
  - `--debug`: Adds Peer Weights tab and extra details. In dimension sheets, includes original (unweighted) peer metrics before privacy adjustments:
      - **Share analysis**: Original Peer Average (%), Original Total Volume, Weight Effect (pp)
      - **Rate analysis**: Original Peer Average (%), Original Total Numerator, Original Total Denominator, Weight Effect (pp)
  - `--consistent-weights`: Compute one global set of peer multipliers for all dimensions
  - `--time-col <column>`: Time column for time-aware consistency (e.g., ano\_mes, year\_month)

Share specific

  - `--metric {txn_cnt,tpv,transaction_count,transaction_amount}`
  - Dimensions: `--auto` or `--dimensions <col...>`
  - Weighting params: `--max-iterations`, `--tolerance` (pp), `--max-weight`, `--min-weight`, `--volume-preservation`
  - Advanced search/diagnostics:
      - `--prefer-slacks-first`: Try full‑dimension LP with rank penalty 0 to probe feasibility with slacks
      - `--auto-subset-search`: Search largest feasible global dimension subset
      - `--subset-search-max-tests <int>`: Limit attempts (default 200)
      - `--greedy-subset-search` / `--no-greedy-subset-search`: Use greedy (remove one dim at a time) vs random search (test random n-1, n-2, ... combinations) (default: greedy enabled)
      - `--trigger-subset-on-slack` / `--no-trigger-subset-on-slack`: If LP uses slack above threshold, auto-run subset search (default on)
      - `--max-cap-slack <float>`: Slack sum threshold as percentage of total volume to trigger subset search (default 0.0)

Rate specific

  - One or both of `--approved-col` or `--fraud-col` (at least one required)
  - `--total-col <col>` (denominator, required)
  - Dimensions: `--auto` or `--dimensions <col...>`
  - BIC percentiles automatically set: 85th for approval (higher is better), 15th for fraud (lower is better)
  - When both rate types specified: single Excel file with prefixed dimension sheets (`Approval_*`, `Fraud_*`)
  - **Weighting params**: Same as share analysis - `--max-iterations`, `--tolerance`, `--max-weight`, `--min-weight`, `--volume-preservation`
  - **Advanced search/diagnostics**: Same as share analysis - `--prefer-slacks-first`, `--auto-subset-search`, `--subset-search-max-tests`, `--greedy-subset-search`, `--trigger-subset-on-slack`, `--max-cap-slack`

Presets and help

```powershell
py benchmark.py presets
py benchmark.py --help; py benchmark.py share --help; py benchmark.py rate --help
```

-----

## Privacy rules and caps

Applied cap is a function of peer count:

  - **With target entity**: Peer count = unique entities - 1 (excludes target)
  - **Peer-only mode**: Peer count = unique entities (all are peers)

Cap thresholds by peer count:

  - ≥10 peers → 40%
  - 7–9 peers → 35%
  - 6 peers → 30%
  - 5 peers → 25%
  - 4 peers → 35%
  - \<4 peers → 50% (warning: below minimum for compliance)

Caps apply per category within each dimension after weighting. The tool prevents any single peer from exceeding the cap in the adjusted share used to compute Balanced Peer Averages.

-----

## Peer-only mode

Analyze peer distributions without a target entity by omitting the `--entity` parameter.

**Key differences:**

  - All entities in the dataset are treated as peers
  - Peer count = total unique entities (not unique entities - 1)
  - Output excludes target-specific columns: `target_share`, `target_rate`, `target_rank`, `delta`
  - Output files named with `PEER_ONLY` identifier when no custom name provided
  - Works with both share and rate analysis

**Use cases:**

  - Market landscape analysis without a specific benchmark target
  - Exploratory analysis to understand peer distributions
  - Establishing baseline benchmarks before selecting a target entity

**Example:**

```powershell
py benchmark.py share --csv data\peers.csv --metric transaction_count --dimensions flag_domestic card_type --consistent-weights --time-col ano_mes
```

Output: `benchmark_share_PEER_ONLY_20251106_121649.xlsx`

-----

## Multi-rate analysis

Analyze both approval and fraud rates simultaneously by specifying both `--approved-col` and `--fraud-col`.

**Key features:**

  - **Shared weights**: Privacy-constrained weights are calculated ONCE based on the shared denominator (`--total-col`)
  - **Single Excel file**: Both rate types combined in one report with side-by-side columns in each dimension sheet
  - **Combined dimension sheets**: Each dimension shows both approval and fraud metrics together for easy comparison
      - Approval columns: `Approval_Entity_Rate`, `Approval_Peer_Avg`, `Approval_Peer_BIC`, `Approval_Gap`
      - Fraud columns: `Fraud_Entity_Rate`, `Fraud_Peer_Avg`, `Fraud_Peer_BIC`, `Fraud_Gap`
      - Color-coded headers: Green for approval metrics, orange for fraud metrics
  - **Debug mode enhancements**: With `--debug` flag, dimension sheets include:
      - **Original metrics**: Unweighted peer averages and total volumes before privacy adjustments are applied
      - **Weight effect**: Shows the impact of privacy weighting in percentage points (Balanced Average - Original Average)
      - **Share analysis columns**: Original Peer Average (%), Original Total Volume, Weight Effect (pp)
      - **Rate analysis columns**: Original Peer Average (%), Original Total Numerator, Original Total Denominator, Weight Effect (pp)
      - Peer count per category
  - Approval rates: 85th percentile BIC (higher is better)
  - Fraud rates: 15th percentile BIC (lower is better)
  - Privacy compliance: Constraints applied to the common denominator ensure consistent privacy across both analyses

**Rationale:**
Since both approval and fraud rates share the same denominator, the privacy constraints are based on the total volume. This allows calculating weights once and applying them to both numerators, ensuring efficiency and consistency. Combining metrics in the same dimension sheet enables direct side-by-side comparison.

**Example:**

```powershell
py benchmark.py rate --csv data\transactions.csv --total-col amt_total --approved-col amt_approved --fraud-col amt_fraud --dimensions product_group flag_domestic --consistent-weights --time-col year_month --debug --output benchmark_analysis.xlsx
```

Output: `benchmark_analysis.xlsx` (single file with combined dimension sheets showing both approval and fraud metrics)

-----

## Time-aware consistency (advanced)

When `--time-col` is specified with `--consistent-weights`, the tool enforces a time-aware consistency model:

**Conceptual strategy:**

  - The same peer weights must work across **all time periods** and **all time-category combinations**
  - Monthly weighted volumes must follow privacy rules for each month
  - Monthly weighted volumes for each category of each dimension must follow privacy rules for each month-category combination

**Technical implementation:**

  - Expands the LP formulation to include constraints for each time period
  - Adds monthly total volume constraints: `m_p * vol_{p,month} ≤ cap * Σ_j m_j * vol_{j,month}`
  - Adds monthly category constraints: `m_p * vol_{p,month,cat} ≤ cap * Σ_j m_j * vol_{j,month,cat}`
  - Single set of weights `m_p` satisfies privacy rules across all time-dimension-category combinations

**Usage:**

```powershell
py benchmark.py share --csv data\sample.csv --entity "BANCO SANTANDER" --metric transaction_count --auto --consistent-weights --time-col ano_mes
```

This ensures temporal consistency: peer weights remain constant across months while satisfying privacy constraints in every month and every category of every dimension.

-----

## Weighting engine (deep dive)

Terminology

  - v\_{p,c}: Raw volume for peer p in category c (across all chosen dimensions when solving globally).
  - m\_p: Peer multiplier (weight) constrained to [min\_weight, max\_weight].
  - cap: The privacy cap (e.g., 0.35 for 7/35) for the dimension’s peer count.
  - tol: Tolerance in percentage points, modeled as slack penalty strength.

Global LP formulation

  - Decision variables: m\_p ≥ 0, absolute‑deviation auxiliaries t^+\_p, t^-*p, cap slack s*{p,c} ≥ 0, and optional rank slacks.
  - Adjusted concentration per (p,c): a\_{p,c}(m) = m\_p v\_{p,c} − cap · Σ\_j m\_j v\_{j,c}.
  - Cap constraints with slacks: a\_{p,c}(m) − s\_{p,c} ≤ 0.
  - Bounds: min\_weight ≤ m\_p ≤ max\_weight.
  - Objective (rank‑preserving, L1 around 1):
      - Minimize Σ\_p (t^+*p + t^-*p) + λ\_rank · Φ\_rank(m) + λ\_cap · Σ*{p,c} s*{p,c},
      - with t^+\_p − t^-\_p = m\_p − 1 to encode |m\_p − 1|.
      - Rank term Φ\_rank promotes preserving the original peer order (strength derived from `--volume-preservation`).
  - Slack penalty λ\_cap ≈ 100 / tolerance\_pp so that lower tolerance increases the cost of relaxing caps.
  - Solver: SciPy `linprog` (HiGHS). Automatic fallback among HiGHS variants; captures diagnostics (max/sum slack, method used).

Behavior and fallbacks

1)  Full‑set LP attempt (rank term applied). If infeasible and `--prefer-slacks-first` is set, a second probe sets rank strength to 0 to see if slacks can make it solvable; heavy slack usage is flagged in logs and validation.
2)  Auto subset search (`--auto-subset-search`): Two modes available:
      - **Greedy mode (default)**: `--greedy-subset-search` removes the most unbalanced dimension one at a time with attempts to re‑add; returns the largest feasible global dimension set and associated weights.
      - **Random mode**: `--no-greedy-subset-search` randomly tests dimension subsets starting with n-1 combinations, then n-2, continuing until a feasible solution is found or max tests reached. Stops as soon as a feasible subset at the current size is found (no need to test smaller subsets).
      - All attempts are recorded in the Subset Search tab.
3)  Greedy dimension dropping: If still infeasible, drop dimensions until feasible.
4)  Per‑dimension solves: For dimensions dropped from the global set, compute per‑dimension LP weights or use the heuristic; ensure each dimension is still privacy‑compliant.

Heuristic (when LP is unavailable or as fallback)

  - Iteratively down‑weights violators (peers near/over cap) and up‑weights under‑represented peers within [min,max], guided by the cap gap and a soft rank preservation pull.
  - Stops after `--max-iterations` or when all categories validate.

Balanced Peer Average (used in reports)

  - For share: Σ\_p metric\_p × adjusted\_share\_p with adjusted\_share capped by the privacy rule.
  - For rate: Weighted by adjusted totals to form a balanced peer rate.

-----

## Structural infeasibility diagnostics

Goal: Determine when constraints cannot be satisfied regardless of m within bounds.

For each (dimension, category, peer):

  - Compute minimal possible adjusted share of peer p if everyone else takes their most favorable bounds:
      - min\_adj\_share\_p = (min\_w · v\_{p}) / (min\_w · v\_{p} + max\_w · Σ\_{j≠p} v\_{j}).
  - If min\_adj\_share\_p \> cap + tolerance, the category is structurally infeasible (no feasible m exists).

Outputs

  - Structural Summary tab: Per dimension counts of infeasible categories/peers and worst margins over cap.
  - Structural Detail tab: Row‑level diagnostics with dimension, category, peer, min\_adj\_share, cap, tolerance, and margin.

Use these to decide whether to merge/re‑bin categories, relax bounds, or exclude specific dimensions from the global set.

-----

## Excel Report Contents

The tool generates comprehensive Excel workbooks with multiple sheets providing different analytical perspectives. The exact sheets included depend on your analysis mode (share/rate), flags (`--debug`, `--consistent-weights`), and whether you're using time-aware or multi-rate analysis.

### Always Included Sheets

#### 1. Summary Sheet

The Summary sheet provides an overview of your analysis configuration and key findings:

**Basic Information Section:**
- Analysis type (SHARE ANALYSIS SUMMARY or RATE ANALYSIS SUMMARY)
- Target entity name (or "PEER-ONLY" if no target specified)
- Timestamp of analysis
- Input file path
- Log level used

**Input Parameters Section:**
- Entity column used
- Metric analyzed (for share) or columns used (for rate)
- BIC percentile(s) applied
- Debug mode status
- Consistent weights status  
- Time column (if time-aware analysis)

**Data Information Section:**
- Total records processed
- Unique entities in dataset
- Peer count (excludes target if specified)
- Dimensions analyzed (count and names)

**Privacy Rule Applied:**
- Peer count and applicable privacy cap percentage
- Example: "6 peers → 30% cap per category"

**LP/Slack Diagnostics** (when `--consistent-weights` used):
- LP solver method used (HiGHS, HiGHS-DS, HiGHS-IPM)
- Max slack percentage (how much privacy caps were relaxed)
- Sum slack percentage (total relaxation across all constraints)
- Number of variables and constraints in the optimization problem
- Lambda cap (penalty strength for slack usage)

**Rank Changes - Top Movers** (when `--consistent-weights` used):
- Quick summary showing top 5 peers by absolute rank change
- Shows which peers moved up/down most due to privacy weighting
- Links to full "Rank Changes" tab for complete details

**Dimensions Analyzed:**
- Table listing each dimension with category counts
- Helps you quickly see the structure of your analysis

#### 2. Dimension Sheets (One Per Dimension)

Each dimension gets its own sheet showing category-level analysis.

**Standard Columns (With Target Entity):**
- **Category**: The dimensional category (e.g., "Domestic", "Credit Card", "E-commerce")
- **Time Column** (if `--time-col` used): Time period for this row (e.g., "2024-01", "2024-Q1")
- **Balanced Peer Average (%)**: Privacy-weighted peer average share/rate
- **BIC (%)**: Best-in-Class benchmark (85th percentile for approval, 15th for fraud)
- **Target Share/Rate (%)**: Your entity's performance in this category
- **Distance to Peer (pp)**: Gap between target and balanced peer average (percentage points)
- **Target Rank**: Your entity's rank among all entities in this category

**Additional Debug Columns** (when `--debug` is enabled):

For **Share Analysis**:
- **Original Peer Average (%)**: Unweighted peer average before privacy adjustments
- **Original Total Volume**: Total peer volume in this category (raw sum)
- **Weight Effect (pp)**: Impact of privacy weighting = Balanced Avg - Original Avg
  - Positive: Privacy weighting increased the benchmark (under-represented peers had higher shares)
  - Negative: Privacy weighting decreased the benchmark (dominant peers had lower shares)
  - Near zero: Privacy weighting had minimal impact

For **Rate Analysis**:
- **Original Peer Average (%)**: Unweighted peer rate before privacy adjustments
- **Original Total Numerator**: Total numerator volume (approved/fraud transactions)
- **Original Total Denominator**: Total denominator volume (total transactions)
- **Weight Effect (pp)**: Impact of privacy weighting = Balanced Rate - Original Rate

**Peer-Only Mode** (when `--entity` is omitted):
- No target columns: Target Share/Rate, Target Rank, Distance to Peer
- Shows only peer distribution statistics:
  - Category, Balanced Peer Average, BIC
  - Plus peer percentiles: 10th, 25th, 50th (median), 75th, 90th
  - Debug columns (if enabled): Original averages and weight effects

**Time-Dimension Output** (when `--time-col` is specified):
- **Multiple rows per category**: One row for each time period
  - Example: "Domestic" category with 12 months = 12 rows
- **"General" row per category**: Aggregated across all time periods
  - Provides overall category performance for comparison with time-specific variations
  - Always appears last for each category
- **Row ordering**: Categories appear in order, then time periods chronologically, then "General"

Example structure:
```
Category    Time Column    Balanced Peer Avg    BIC    Target Share    Distance
Domestic    2024-01       51.85%               70.82%  12.74%         -39.11pp
Domestic    2024-02       44.76%               54.78%  53.52%         +8.76pp
Domestic    2024-03       54.41%               75.60%  50.34%         -4.07pp
Domestic    General       49.33%               60.80%  41.92%         -7.41pp
International 2024-01     48.15%               29.18%  87.26%         +39.11pp
...
```

**Multi-Rate Analysis** (when both `--approved-col` and `--fraud-col` specified):
- **Single Excel file** with both rate types combined
- Each dimension sheet shows approval AND fraud metrics **side-by-side**
- Column naming convention:
  - Approval columns: `Approval_Entity_Rate`, `Approval_Peer_Avg`, `Approval_Peer_BIC`, `Approval_Gap`
  - Fraud columns: `Fraud_Entity_Rate`, `Fraud_Peer_Avg`, `Fraud_Peer_BIC`, `Fraud_Gap`
- **Color-coded headers**:
  - Green fill for approval metric columns (higher is better)
  - Orange fill for fraud metric columns (lower is better)
- Enables direct side-by-side comparison of both rate types

### Debug Mode Sheets

These sheets only appear when `--debug` flag is enabled:

#### 3. Peer Weights Tab

Shows the complete picture of how privacy weighting affected each peer's contribution to benchmarks.

**Columns:**
- **Scope**: "Global" (for global weights) or "Per-Dimension" (dimension-specific weights)
- **Dimension**: Dimension name (null for Global scope)
- **Peer**: Peer entity name
- **Multiplier**: Weight multiplier applied (e.g., 1.0 = no change, 1.5 = 50% increase, 0.6 = 40% decrease)
- **Unbalanced_Volume**: Original peer volume before any weighting
- **Unbalanced_Share_%**: Original peer market share (%)
- **Balanced_Volume**: Adjusted volume after multiplier (= Unbalanced_Volume × Multiplier)
- **Balanced_Share_%**: Adjusted market share after privacy weighting (%)
- **Legacy columns** (for backward compatibility): Volume, Weight_%

**Use Cases:**
- **Privacy Impact Analysis**: See how much weighting changed peer contributions
  - Multipliers < 1.0: Peers were down-weighted (typically dominated some categories)
  - Multipliers > 1.0: Peers were up-weighted (typically under-represented)
  - Multipliers = 1.0: No adjustment needed (already privacy-compliant)
- **Dominant Peer Identification**: Find which peers were constrained by privacy caps
- **Volume Redistribution Tracking**: Understand how share percentages rebalanced
- **Validation**: Verify calculations (Balanced = Unbalanced × Multiplier)

**Example Interpretation:**
```
Peer    Multiplier  Unbalanced_%  Balanced_%  Effect
Bank_A  0.6000      35.71%        25.00%      -10.71pp  ← Down-weighted (dominated categories)
Bank_B  1.2000      21.43%        30.00%      +8.57pp   ← Up-weighted (under-represented)
Bank_C  1.0000      22.24%        22.24%      +0.00pp   ← No change needed
```

#### 4. Privacy Validation Tab

**Only appears when BOTH `--debug` AND `--consistent-weights` are enabled.**

Provides granular validation that privacy rules are satisfied across **every single dimension-category-(time) combination**. This is the most detailed compliance view.

**Columns:**
- **Dimension**: The dimension being validated
- **Time_Period**: Time period (only when `--time-col` is used)
- **Category**: Category within the dimension
- **Peer**: Individual peer entity
- **Weight_Source**: "Global" or "Per-Dimension" (which weights were used)
- **Multiplier**: The weight multiplier for this peer
- **Original_Volume**: Unweighted volume for this peer-category combination
- **Original_Share_%**: Unweighted market share in this category
- **Balanced_Volume**: Privacy-weighted volume
- **Balanced_Share_%**: Privacy-weighted market share
- **Privacy_Cap_%**: The applicable cap (30% for 6 peers, 35% for 7 peers, etc.)
- **Tolerance_%**: The tolerance setting used
- **Compliant**: "Yes" or "No"
- **Violation_Margin_%**: Amount by which cap is exceeded (if any)

**Visual Features:**
- **Red highlighting**: Violations (Compliant = "No") are highlighted in red
- Sortable/filterable in Excel for detailed analysis
- Comprehensive view (can be 500+ rows for complex analyses)

**Use Cases:**
- **Compliance Auditing**: Verify every break satisfies privacy rules
- **Parameter Tuning**: Identify hardest-to-satisfy dimension-category combinations
- **Time Analysis**: See how compliance varies across time periods
- **Peer Behavior**: Understand which peers dominate which categories
- **Root Cause Analysis**: When LP fails, see exactly which constraints are problematic

**Example:**
```
Dimension     Category   Peer    Balanced_%  Cap%   Compliant  Violation
flag_domestic Domestic   Bank_A  28.5%       30%    Yes        -1.5%
flag_domestic Domestic   Bank_B  31.2%       30%    No         +1.2%  ← VIOLATION
cp_cnp        CNP        Bank_A  29.8%       30%    Yes        -0.2%
```

### Consistent Weights Sheets

These sheets only appear when `--consistent-weights` flag is enabled:

#### 5. Weight Methods Tab

Shows exactly how weights were calculated for each dimension and the specific multipliers applied.

**Columns:**
- **Dimension**: Dimension name
- **Peer**: Peer entity
- **Method**: Weight calculation method used:
  - "Global LP": Peer uses global weights from Linear Programming
  - "Per-Dimension LP": Dimension-specific LP weights (when dimension was dropped from global set)
  - "Per-Dimension Heuristic": Dimension-specific heuristic weights (LP failed for this dimension)
  - "Global Weights (dropped)": Dimension was dropped from global optimization
- **Multiplier**: The actual weight multiplier value

**Use Cases:**
- **Methodology Transparency**: Understand which method succeeded for each dimension
- **Troubleshooting**: Identify dimensions that required fallback methods
- **Auditing**: Document weight calculation approach for compliance
- **Optimization Analysis**: See impact of global vs per-dimension weights

#### 6. Subset Search Tab

**Only appears when `--auto-subset-search` is enabled.**

Records all attempts to find the largest feasible global dimension subset.

**Columns:**
- **Attempt**: Sequential attempt number
- **Dimensions_Tested**: Which dimensions were included in this attempt
- **Dimension_Count**: Number of dimensions in this subset
- **Result**: "Feasible" or "Infeasible"
- **Max_Slack_%**: Maximum slack percentage used (if feasible)
- **Sum_Slack_%**: Total slack percentage across all constraints
- **Notes**: Additional information (e.g., "Best solution found")

**Use Cases:**
- **Search Progress**: See how the algorithm explored dimension combinations
- **Feasibility Understanding**: Understand why certain combinations work/don't work
- **Comparison**: Evaluate greedy vs random search performance
- **Documentation**: Audit trail of subset search process

**Example:**
```
Attempt  Dimensions_Tested                  Count  Result      Max_Slack  Notes
1        [A,B,C,D,E]                       5      Infeasible  N/A        Full set failed
2        [A,B,C,D] (dropped E)             4      Infeasible  N/A        E removed
3        [A,B,D] (dropped C)               3      Feasible    2.3%       Best solution
4        [A,B,C,D] (re-added C)            4      Infeasible  N/A        Cannot re-add C
```

#### 7. Structural Summary Tab

Quantifies fundamental infeasibility drivers by dimension.

**Columns:**
- **Dimension**: Dimension name
- **Infeasible_Categories**: Number of categories structurally infeasible
- **Infeasible_Peers**: Number of peer-category combinations structurally infeasible
- **Worst_Margin_Over_Cap_%**: Largest violation margin (how far over cap)
- **Notes**: Summary of issues

**Use Cases:**
- **Root Cause Identification**: Find dimensions causing infeasibility
- **Category Merging Decisions**: Identify categories that should be combined
- **Parameter Adjustment**: Determine if bounds need relaxation

#### 8. Structural Detail Tab

Row-level diagnostics for every structurally infeasible peer-category combination.

**Columns:**
- **Dimension**: Dimension name
- **Category**: Category name
- **Peer**: Peer entity
- **Min_Adj_Share_%**: Minimum possible adjusted share (even with optimal weights)
- **Privacy_Cap_%**: The applicable cap
- **Tolerance_%**: Tolerance setting
- **Margin_Over_Cap_%**: How much the min share exceeds the cap
- **Notes**: Explanation

**Use Cases:**
- **Detailed Troubleshooting**: Understand exactly which combinations are impossible
- **Data Quality**: Identify if a peer dominates a category too heavily
- **Remediation Planning**: Decide on category merges or peer exclusions

#### 9. Rank Changes Tab

Shows how privacy weighting affected peer ordering.

**Columns:**
- **Peer**: Peer entity name
- **Base_Share_%**: Original market share (unweighted)
- **Adjusted_Share_%**: Privacy-weighted market share
- **Base_Rank**: Original rank (1 = largest share)
- **Adjusted_Rank**: Rank after privacy weighting
- **Delta**: Rank change (Adjusted_Rank - Base_Rank)
  - Negative: Moved up (improved ranking)
  - Positive: Moved down (lower ranking)
  - Zero: No rank change

**Use Cases:**
- **Rank Preservation Analysis**: See how well original ordering was maintained
- **Outlier Identification**: Find peers whose ranks changed significantly
- **Weight Impact**: Understand redistribution effects

### File Naming Conventions

**Share Analysis:**
- With entity: `benchmark_share_ENTITY_NAME_YYYYMMDD_HHMMSS.xlsx`
- Peer-only: `benchmark_share_PEER_ONLY_YYYYMMDD_HHMMSS.xlsx`
- Custom output: Uses your specified filename

**Rate Analysis (Single Rate):**
- Approval: `benchmark_approval_rate_ENTITY_NAME_YYYYMMDD_HHMMSS.xlsx`
- Fraud: `benchmark_fraud_rate_ENTITY_NAME_YYYYMMDD_HHMMSS.xlsx`

**Multi-Rate Analysis:**
- Single file: `benchmark_multi_rate_ENTITY_NAME_YYYYMMDD_HHMMSS.xlsx`
- Custom output: Uses your specified filename (single file with combined sheets)

---

## Tuning recipes

  - **Include more dimensions globally**: Lower `--rank/--volume-preservation` strength, loosen bounds (higher `--max-weight`, lower `--min-weight`), and enable `--auto-subset-search`.
  - **Avoid masking violations**: Prefer disabling `--prefer-slacks-first` for production. If enabled, verify slack totals in logs and the Subset Search results.
  - **Tight vs loose tolerance**: Lower `--tolerance` raises slack penalty (harder to use slacks). Higher tolerance allows limited slack but validation will still flag cap breaches.
  - **Greedy vs Random subset search**:
      - Use greedy mode (default) for faster, deterministic results when you want to quickly find a feasible subset.
      - Use random mode (`--no-greedy-subset-search`) when greedy gets stuck or you want to explore different dimension combinations. Random mode tests all size n-1 subsets (shuffled) before moving to n-2, potentially finding better global solutions at the cost of more computation.
      - Increase `--subset-search-max-tests` (e.g., 500-1000) for random mode to allow more exploration.
  - **Time-aware consistency**:
      - Use `--time-col` with `--consistent-weights` when you need weights that remain constant across time periods.
      - This creates significantly more constraints (time periods × categories) and may require looser bounds or higher tolerance.
      - Consider using `--max-cap-slack 0.1` to allow minimal slack when time constraints make the problem very constrained.
  - **Peer-only mode**: Omit `--entity` to analyze peer distributions without a target. Useful for market landscape analysis or exploratory work before selecting a benchmark target.
  - **Multi-rate analysis**: Specify both `--approved-col` and `--fraud-col` to analyze approval and fraud rates simultaneously with a single command, generating a combined report.

-----

## Project structure

  - `benchmark.py`: CLI entry point and Excel writer.
  - `core/`
      - `dimensional_analyzer.py`: Share/Rate computation, LP/heuristic weighting, subset search, diagnostics.
      - `data_loader.py`: CSV loading, normalization, auto dimension discovery.
      - `privacy_validator.py`, `report_generator.py`: Helpers.
  - `utils/`
      - `config_manager.py`: Column mappings, presets, optional SQL config.
      - `logger.py`: Logging setup.
  - `data/`: Example datasets (sensitive data should be redacted).
  - `old/`: Legacy notebooks/scripts.

-----

## Troubleshooting

  - **Column not found**: Prefer standardized names or extend `config_manager.py` mappings.
  - **Too few peers (\<4)**: Tool warns; results may not meet minimum privacy requirements.
  - **LP infeasible**: Inspect Structural tabs; consider relaxing bounds or removing problematic dimensions; enable `--auto-subset-search`.
  - **Missing Peer Weights**: Add `--debug`.
  - **Excel write error**: If the file is open, PowerShell locks it. Save to a new filename or close the workbook.
  - **Multi-rate analysis not running both**: Ensure both `--approved-col` and `--fraud-col` are specified.
  - **Peer-only mode not working**: Verify `--entity` parameter is completely omitted (not empty string).

-----

## Compliance note

This tool enforces per‑category peer concentration caps aligned with Mastercard Control 3.2. It does not anonymize inputs; handle source data securely and validate outputs per your organization’s standards.
