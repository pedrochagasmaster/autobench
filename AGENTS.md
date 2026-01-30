# AGENTS.md - AI Agent Developer Guide

> **Purpose**: Complete context for AI agents working on this codebase. Read this **entirely** before making any changes.

---

## 🎯 Project Identity

**Privacy-Compliant Peer Benchmark Tool** — A dimensional analysis system comparing financial entities against peer groups while enforcing Mastercard Control 3.2 privacy compliance.

| Aspect | Details |
|--------|---------|
| **Domain** | Financial benchmarking (banks, issuers, merchants) |
| **Core Constraint** | Privacy caps prevent single-peer market dominance |
| **Primary Output** | Excel reports with privacy-weighted peer comparisons |
| **Interfaces** | CLI (`benchmark.py`) and TUI (`tui_app.py`) |
| **Config Version** | 3.0 (YAML-based) |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER INTERFACES                             │
├──────────────────────────────┬──────────────────────────────────────┤
│   benchmark.py (CLI)         │        tui_app.py (TUI)              │
│   - share subcommand         │        - Textual-based UI            │
│   - rate subcommand          │        - ListView for file browser   │
│   - config subcommand        │        - Select for dropdowns        │
└──────────────┬───────────────┴────────────────── ┬──────────────────┘
               │                                   │
               └───────────────┬───────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          CORE ENGINE                                │
├─────────────────────────────────────────────────────────────────────┤
│  core/data_loader.py          │  Ingestion, normalization, schema   │
│  core/dimensional_analyzer.py │  LP/Bayesian weight optimization    │
│  core/privacy_validator.py    │  Control 3.2 cap enforcement        │
│  core/report_generator.py     │  Excel output formatting            │
└─────────────────────────────────────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         UTILITIES                                   │
├─────────────────────────────────────────────────────────────────────┤
│  utils/config_manager.py   │  YAML parsing, hierarchy merging       │
│  utils/preset_manager.py   │  Preset loading from presets/          │
│  utils/validators.py       │  Config schema validation              │
│  utils/csv_validator.py    │  Output CSV vs Excel validation        │
│  utils/logger.py           │  Logging setup                         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## ⚠️ Critical Business Rules — NEVER BYPASS

### Privacy Caps (Mastercard Control 3.2)

These are **legal compliance requirements**. The tool auto-selects based on peer count:

| Rule | Min Peers | Max Concentration | Additional Requirements |
|------|-----------|-------------------|------------------------|
| **5/25** | 5 | 25% | — |
| **6/30** | 6 | 30% | ≥3 participants must be ≥7% |
| **7/35** | 7 | 35% | ≥2 participants ≥15%, ≥1 additional ≥8% |
| **10/40** | 10 | 40% | ≥2 participants ≥20%, ≥1 additional ≥10% |
| **4/35** | 4 | 35% | Merchant benchmarking only |

**Implementation**: `core/privacy_validator.py` → `PrivacyValidator`

### Configuration Integrity

> **ALL analysis logic MUST source parameters from the merged `opt_config` object, NOT raw CLI args**, to ensure presets are respected.

---

## 🔄 Weight Optimization Algorithm

```
┌─────────────────────────────────────────────────────────────────────┐
│  1. GLOBAL LP (SciPy linprog + HiGHS solver)                        │
│     - Variables: [m₀...mₚ, t⁺, t⁻, slack_cap, slack_rank]           │
│     - Objective: min(deviation from 1.0 + rank_penalty + slack)     │
│     - Constraints: m_p × v_{p,c} ≤ cap × Σ(m_j × v_{j,c})           │
└────────────────────────────┬────────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              ▼                              ▼
       ┌─────────────┐               ┌─────────────────┐
       │  SUCCESS    │               │    FAILURE      │
       │  (no slack) │               │  (infeasible)   │
       └──────┬──────┘               └────────┬────────┘
              │                               │
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────────────────┐
│ Validate against        │     │  2. SUBSET SEARCH                    │
│ tolerance threshold     │     │     Strategy: greedy or random       │
│ (trigger_on_slack)      │     │     Find largest feasible subset     │
└──────────┬──────────────┘     └────────────────────┬────────────────┘
           │                                          │
           ▼                               ┌──────────┴──────────┐
    Use Global Weights                     ▼                      ▼
    for all dimensions             Selected Dims           Dropped Dims
                                   → Global Weights        → Per-Dim LP
                                                                 │
                                                     ┌───────────┴───────────┐
                                                     ▼                       ▼
                                              ┌─────────────┐         ┌────────────┐
                                              │  LP Success │         │ LP Failure │
                                              └─────────────┘         └─────┬──────┘
                                                                            ▼
                                                                  ┌────────────────────┐
                                                                  │ 3. BAYESIAN        │
                                                                  │    L-BFGS-B        │
                                                                  │    scipy.minimize  │
                                                                  └────────────────────┘
```

**Key Method**: `DimensionalAnalyzer.calculate_global_privacy_weights()`

---

## 📁 File Structure

```
📁 Project Root
├── benchmark.py              # CLI entry point (~3000 lines)
├── tui_app.py                # TUI application (~1400 lines)
├── requirements.txt          # Dependencies
├── AGENTS.md                 # This file
├── 📁 docs/                  # Project documentation (Plans, Reviews, Gains)
├── 📁 core/                  # Business logic
│   ├── __init__.py              # Exports: DimensionalAnalyzer, PrivacyValidator, DataLoader
│   ├── dimensional_analyzer.py  # Core algorithm (~2200 lines) ⭐ CRITICAL
│   ├── data_loader.py           # Data ingestion + validation (~755 lines)
│   ├── privacy_validator.py     # Privacy enforcement (412 lines)
│   ├── report_generator.py      # Excel generation (~650 lines)
│   └── validation_runner.py     # Validation orchestration (121 lines)
├── 📁 utils/
│   ├── __init__.py              # Exports: ConfigManager, setup_logging
│   ├── config_manager.py        # Config handling (554 lines)
│   ├── preset_manager.py        # Preset loading
│   ├── validators.py            # Config schema validation
│   ├── csv_validator.py         # CSV output validation
│   ├── CSV_VALIDATOR_README.md  # Validator documentation
│   └── logger.py                # Logging setup
├── 📁 config/
│   └── template.yaml            # Default config template (v3.0)
├── 📁 presets/
│   ├── balanced_default.yaml      # tolerance=2.0, random search
│   ├── compliance_strict.yaml     # tolerance=0.0, greedy search
│   ├── research_exploratory.yaml  # Relaxed constraints
│   └── strategic_consistency.yaml # tolerance=25.0, volume-weighted
├── 📁 scripts/               # Helper scripts (Gate Test, Sweep Generator)
├── 📁 tests/                 # Unit tests
├── 📁 test_sweeps/           # Generated sweep test cases
├── 📁 tool_extension_project/ # Extension project components
├── 📁 data/                  # Input data (gitignored)
├── 📁 outputs/               # Generated reports (gitignored)
└── 📁 old/                   # Legacy code (reference only)
```

---

## ⚙️ Configuration System

### Hierarchy (Highest → Lowest Priority)

```
1. CLI arguments         (--entity, --csv, --output, --debug)
2. Custom config file    (--config my_config.yaml)
3. Preset file           (--preset compliance_strict)
4. Hard-coded defaults   (ConfigManager._get_default_config())
```

### Preset Quick Reference

| Preset | Intent | Tolerance | Vol-Weight | Subset |
|--------|--------|-----------|-----------|--------|
| `compliance_strict` | Regulatory | 0.0 | ❌ | greedy |
| `balanced_default` | Day-to-day | 2.0 | ❌ | random |
| `strategic_consistency` | Dashboards | 25.0 | ✅ 1.5x | ❌ |
| `research_exploratory` | Difficult data | 5.0 | ❌ | random |
| `low_distortion` | Low Distortion | 10.0 | ✅ 1.0x | ❌ |
| `minimal_distortion` | Max Accuracy | 100.0 | ✅ 2.0x | ❌ |

### Config Schema (v3.0)

```yaml
version: "3.0"           # REQUIRED - must be "3.0"
preset_name: "my_preset" # Optional - for presets
description: "..."       # Optional

optimization:
  bounds:
    max_weight: 10.0     # Maximum peer multiplier (>0)
    min_weight: 0.01     # Minimum peer multiplier (>0, <max)
  linear_programming:
    max_iterations: 1000 # Positive integer
    tolerance: 1.0       # >=0, in percentage points
    volume_weighted_penalties: false
    volume_weighting_exponent: 1.0
  constraints:
    volume_preservation: 0.5  # 0.0-1.0 (rank preservation strength)
  subset_search:
    enabled: true
    strategy: "greedy"        # "greedy" | "random"
    max_attempts: 200         # Positive integer
    trigger_on_slack: true
    max_slack_threshold: 0.0  # >=0
    prefer_slacks_first: false
  bayesian:
    max_iterations: 500
    learning_rate: 0.01

analysis:
  best_in_class_percentile: 0.85  # 0.0-1.0

output:
  format: "xlsx"                  # "xlsx" | "csv" | "json"
  include_debug_sheets: false
  include_privacy_validation: false
  log_level: "INFO"               # DEBUG|INFO|WARNING|ERROR
```

### ConfigManager API

```python
config = ConfigManager(
    config_file="my_config.yaml",  # Optional
    preset="compliance_strict",     # Optional
    cli_overrides={'debug': True}   # Optional
)

# Access nested values safely
max_weight = config.get("optimization", "bounds", "max_weight", default=10.0)
```

---

## 🖥️ TUI Integration (`tui_app.py`)

### Validation Workflow

The TUI implements a **validation-first** flow using `ValidationModal`:
1. User clicks "Run Analysis"
2. If validation enabled: Load DataFrame → Validate → Show modal if issues
3. Modal allows Proceed (if only warnings) or Cancel
4. On Proceed: Pass DataFrame to backend (avoids re-loading)

### Key TUI Widgets

| Widget | ID | Purpose |
|--------|----|---------|
| `Checkbox` | `validate_input` | Enable/disable input validation (default: True) |
| `Checkbox` | `compare_presets` | Run preset comparison |
| `Checkbox` | `analyze_distortion` | Include distortion sheets |
| `Checkbox` | `include_calculated` | Add raw/distortion columns to CSV |
| `Checkbox` | `fraud_in_bps` | Rate tab only: BPS formatting |
| `Select` | `output_format` | analysis/publication/both |
| `ValidationModal` | — | Shows validation errors/warnings |

### Backend Integration Notes

- `benchmark.py` modified to accept `args.df` (pre-loaded DataFrame)
- Prevents double data loading after validation
- All new flags passed via `cli_overrides` to ConfigManager

---

## ✨ Enhanced Analysis Features (New in v3.0)

### Input Validation

**Implementation**: `core/data_loader.py` → `validate_share_input()`, `validate_rate_input()`

**Returns**: `List[ValidationIssue]` with severity (ERROR/WARNING/INFO)

**CLI**: `--validate-input` (default) / `--no-validate-input`

**Checks**:
- Column existence and types
- Minimum peer count (4+)
- Null value detection
- Entity name consistency

### Distortion Analysis

**Implementation**: `benchmark.py` → `calculate_distortion_summary()`

**CLI**: `--analyze-distortion`

**Outputs**:
- **Distortion Summary Sheet**: Aggregate stats by dimension
- Enhanced CSV with `Distortion_PP` columns

### Preset Comparison

**Implementation**: `benchmark.py` → `run_preset_comparison()`

**CLI**: `--compare-presets`

**Outputs**:
- Preset Comparison sheet with mean distortion per preset
- ⭐ Best preset marker (lowest distortion)

### Output Formats

**CLI**: `--output-format {analysis|publication|both}` or `--publication-format`

**Config**: `output.output_format`

### Enhanced CSV Export

**CLI**: `--export-balanced-csv --include-calculated`

**Config**: `output.include_calculated_metrics`

**Columns added**: `Raw_Metric`, `Raw_Share_%`, `Balanced_Share_%`, `Distortion_PP`

---

## 🔧 Key Classes Reference

### DimensionalAnalyzer

**Location**: `core/dimensional_analyzer.py`

**Constructor Parameters**:
```python
DimensionalAnalyzer(
    target_entity: Optional[str],      # None for peer-only mode
    entity_column: str = "issuer_name",
    bic_percentile: float = 0.85,
    debug_mode: bool = False,
    consistent_weights: bool = True,   # Global vs per-dimension
    max_iterations: int = 1000,
    tolerance: float = 1.0,            # Privacy slack tolerance (pp)
    max_weight: float = 10.0,
    min_weight: float = 0.01,
    volume_preservation_strength: float = 0.5,  # Mapped to rank_preservation
    prefer_slacks_first: bool = False,
    auto_subset_search: bool = False,
    subset_search_max_tests: int = 200,
    greedy_subset_search: bool = True,
    trigger_subset_on_slack: bool = True,
    max_cap_slack: float = 0.0,
    time_column: Optional[str] = None,
    volume_weighted_penalties: bool = False,
    volume_weighting_exponent: float = 1.0,
)
```

**Key Instance Attributes** (after `calculate_global_privacy_weights`):
- `global_weights: Dict[str, Dict]` — peer → {volume, weight, multiplier, ...}
- `per_dimension_weights: Dict[str, Dict[str, float]]` — dim → peer → multiplier
- `weight_methods: Dict[str, str]` — dim → "Global-LP" | "Per-Dimension-LP" | "Per-Dimension-Bayesian"
- `last_lp_stats: Dict` — solver statistics
- `subset_search_results: List[Dict]` — search attempt logs
- `rank_changes_df: pd.DataFrame` — rank change tracking
- `privacy_validation_df: pd.DataFrame` — compliance validation

### DataLoader

**Location**: `core/data_loader.py`

| Method | Purpose |
|--------|---------|
| `load_from_csv(file_path)` | Load CSV with normalization |
| `_normalize_columns(df)` | Lowercase + underscores |
| `validate_minimal_schema(df)` | Check required columns |
| `get_available_dimensions(df)` | Auto-detect dimensions |

### PrivacyValidator

**Location**: `core/privacy_validator.py`

```python
PrivacyValidator(
    min_participants: int = 5,
    max_concentration: float = 25.0,
    rule_name: Optional[str] = None,
    protected_entities: Optional[List[str]] = None,
    protected_max_concentration: float = 25.0
)
```

| Method | Purpose |
|--------|---------|
| `validate_peer_group(peer_group, metrics, entity_column)` | Check concentration |
| `calculate_concentration(peer_group, metric, entity_column)` | Compute shares |
| `apply_weighting(peer_group, metric, threshold_pct)` | Adjust weights |

---

## 📊 Data Format Requirements

### Input Data Structure

Data must be **"long" format** — one row per entity-dimension combination:

```csv
issuer_name,flag_domestic,card_type,txn_cnt,tpv
BANCO SANTANDER,Domestic,CREDIT,125000,15000000
BANCO SANTANDER,Domestic,DEBIT,200000,8000000
ITAU UNIBANCO,Domestic,CREDIT,180000,22000000
```

### Column Normalization

`DataLoader._normalize_columns()` applies:
1. Convert to lowercase
2. Replace spaces with underscores

### Standard Column Aliases

| Input | Normalized To |
|-------|---------------|
| `txn_cnt`, `txn_count` | `transaction_count` |
| `tpv`, `amt` | `transaction_amount` |
| `appr_txns` | `approved_count` |
| `fraud_cnt` | `fraud_count` |

### CLI Gotcha

> **Column names in CLI flags must match the CSV AFTER normalization**, not before.

---

## 🖥️ TUI Development Patterns

### Architecture

The TUI is built with **Textual** framework and follows these patterns:

```
tui_app.py
├── BenchmarkApp (App)           # Main application
├── FileListItem (ListItem)      # Custom list item for file paths
├── LogHandler (logging.Handler) # Redirects logs to TUI
└── PresetHelpScreen (Screen)    # Modal help screen
```

### Widget Selection Rules

| Need | Widget | Why |
|------|--------|-----|
| Single file selection | `ListView` + `FileListItem` | Avoids ID collisions with paths |
| Single column/entity | `Select` | Dropdown with search |
| Multiple dimensions | `SelectionList` or `Input` | Multi-select or space-separated |
| Text input | `Input` | For secondary metrics, dimensions |

### Key Patterns

1. **Use `FileListItem`** for file lists to avoid ID collision issues with file paths:
```python
class FileListItem(ListItem):
    def __init__(self, file_path: str) -> None:
        super().__init__(Label(file_path))
        self.file_path = file_path  # Store path safely
```

2. **Populate `Select` widgets efficiently** — read headers only:
```python
headers = pd.read_csv(file_path, nrows=0).columns.tolist()
select_widget.set_options([(h, h) for h in headers])
```

3. **Load unique entities on column selection**:
```python
def load_unique_entities(self, column_name):
    df = pd.read_csv(self.current_file)
    unique_values = df[column_name].unique().tolist()
    self.entity_select.set_options([(v, v) for v in sorted(unique_values)])
```

4. **Use `Input` for multi-value fields** (dimensions, secondary metrics):
```python
# User enters: "flag_domestic card_type merchant_category"
dimensions = input_widget.value.split()
```

5. **File discovery pattern** — search current dir + `data/`:
```python
csv_files = glob.glob("*.csv") + glob.glob("data/*.csv")
```

### TUI Workflow

```
1. File Selection    → ListView populated from current dir + data/
2. Entity Column     → Select populated from CSV headers
3. Target Entity     → Select populated from unique values in selected column
4. Preset Selection  → Select populated from presets/ directory
5. Analysis Config   → Tab-based (Share / Rate)
6. Run Analysis      → Background thread execution
7. Log Display       → Real-time logging via LogHandler
```

### Coding Conventions for TUI

- **Log redirection**: Always use `LogHandler` to capture logs in the TUI
- **Background execution**: Run analysis in a thread to prevent UI freeze
- **CSS styling**: Defined in `BenchmarkApp.CSS` class variable
- **Keyboard bindings**: Defined in `BenchmarkApp.BINDINGS`

### TUI Classes Reference

| Class | Purpose |
|-------|---------|
| `BenchmarkApp` | Main Textual App with CSS and bindings |
| `FileListItem` | ListView item that safely stores file path |
| `LogHandler` | Redirects Python logging to TUI Log widget |
| `PresetHelpScreen` | Modal screen showing preset descriptions |

---

## 📋 CLI Command Reference

### Share Analysis

```powershell
py benchmark.py share ^
  --csv data\sample.csv ^
  --entity "BANCO SANTANDER" ^
  --metric transaction_count ^
  --dimensions flag_domestic card_type ^
  --time-col year_month ^
  --preset compliance_strict ^
  --debug ^
  --export-balanced-csv
```

### Rate Analysis

```powershell
py benchmark.py rate ^
  --csv data\sample.csv ^
  --entity "ENTITY_NAME" ^
  --total-col amt_total ^
  --approved-col amt_approved ^
  --fraud-col amt_fraud ^
  --dimensions flag_domestic card_type ^
  --time-col year_month ^
  --preset balanced_default
```

### Config Management

```powershell
py benchmark.py config list              # List presets
py benchmark.py config show <preset>     # Show preset details
py benchmark.py config validate <file>   # Validate config
py benchmark.py config generate <output> # Generate template
```

### Key Flags

| Flag | Analysis | Description |
|------|----------|-------------|
| `--csv` | Both | Input CSV file (required) |
| `--entity` | Both | Target entity (omit for peer-only) |
| `--metric` | Share | Metric column (required for share) |
| `--total-col` | Rate | Denominator column (required for rate) |
| `--approved-col` | Rate | Approval numerator |
| `--fraud-col` | Rate | Fraud numerator |
| `--dimensions` | Both | Explicit dimension list |
| `--auto` | Both | Auto-detect dimensions |
| `--time-col` | Both | Time-aware consistency |
| `--preset` | Both | Use preset |
| `--config` | Both | Custom YAML config |
| `--debug` | Both | Enable debug sheets |
| `--per-dimension-weights` | Both | Disable global mode |
| `--export-balanced-csv` | Both | Export balanced CSV |

---

## 📈 Output Structure

### Excel Sheets

| Sheet | Content | Condition |
|-------|---------|-----------|
| Summary | Metadata, inputs, findings | Always |
| Per-dimension | Target vs peer comparisons | Always |
| Weight Methods | Method per dimension | Always |
| Rank Changes | Before/after ranking | Always |
| Peer Weights | Multipliers and volumes | `--debug` |
| Privacy Validation | Per-category compliance | `--debug` |
| Structural Diagnostics | Infeasibility analysis | LP failure |
| Subset Search | Search attempts | Subset search |

### Weight Method Labels

| Label | Meaning |
|-------|---------|
| `Global-LP` | All dimensions solved together |
| `Per-Dimension-LP` | Dimension solved independently |
| `Per-Dimension-Bayesian` | Bayesian fallback after LP failure |

### CSV Export Format

```csv
Dimension,Category,year_month,Balanced_Total,Balanced_Approval_Total,Balanced_Fraud_Total
fl_token,Non-tokenized,2024-01,203796570874.8,151927893365.16,185177975.02
```

---

## 🐛 Debugging & Testing

### 🛡️ Mandatory Verification

After **any** code change, you must run the gate test suite. This performs a full system check:
1. Generates 17+ representative scenarios (Share/Rate, Peer-Only/Target, etc.)
2. Executes them to verify runtime stability.
3. **Deeply verifies** outputs: checks Excel sheet structure, value ranges (0-100%), and cross-validates CSV exports against Excel reports (Control 3.2 compliance).

```powershell
# 1. Run Gate Test (System Integration)
python scripts/perform_gate_test.py

# 2. Run Unit Tests
pytest
```

### Validate CSV Output

```powershell
py utils\csv_validator.py report.xlsx report_balanced.csv --verbose
```

### 🧹 CLI Sweep Testing

For comprehensive coverage, use the sweep generator to create and run hundreds of test cases:

```powershell
# Generate core test cases
python scripts/generate_cli_sweep.py --mode core --out-dir test_sweeps

# Run generated commands
test_sweeps/commands.ps1
```

**Modes**:
- `gate`: Minimal set for integrity checks
- `core`: Standard coverage (default)
- `exhaustive`: Large scale parameter sweep

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Entity not found` | Case mismatch | Match exact entity name |
| `No valid dimensions` | All filtered | Use `--dimensions` explicitly |
| `LP Infeasible` | Structural impossibility | Check Structural Diagnostics sheet |
| `Column not found` | Name mismatch | Check normalized column names |
| `Memory error` | High cardinality | Limit dimensions |

### LP Solver Fallback Order

1. `highs` (default)
2. `highs-ds` (dual simplex)
3. `highs-ipm` (interior point)

---

## 🔨 Common Modification Patterns

### Adding a New Preset

```yaml
# presets/my_preset.yaml
version: "3.0"
preset_name: "my_preset"
description: "My custom intent"

optimization:
  linear_programming:
    tolerance: 3.0  # Only override what differs
```

Test: `py benchmark.py config show my_preset`

### Modifying LP Formulation

Key location: `DimensionalAnalyzer._solve_global_weights_lp()`

```python
# Variable layout:
# [m₀...mₚ₋₁, t⁺₀...t⁺ₚ₋₁, t⁻₀...t⁻ₚ₋₁, s_cap₀..., s_rank₀...]
```

### Adding New Column Aliases

1. `utils/config_manager.py` → `DEFAULT_COLUMN_MAPPING`
2. `core/data_loader.py` → `validate_minimal_schema()`
3. `benchmark.py` → `create_parser()` choices

---

## 📚 Dependencies

```
pandas>=1.3.0       # Data manipulation
numpy>=1.21.0       # Numerical operations
openpyxl>=3.0.0     # Excel output
PyYAML>=6.0         # Configuration
scipy>=1.8.0        # LP solver (linprog)
pypyodbc>=1.3.6     # SQL support (optional)
textual>=0.40.0     # TUI framework
python-dateutil>=2.8.0
```

---

## 🎨 Code Style

| Aspect | Standard |
|--------|----------|
| Python | 3.8+ |
| Type hints | Required on public methods |
| Docstrings | NumPy style |
| Logging | `logger = logging.getLogger(__name__)` |
| Config access | Via `ConfigManager.get()` only |

---

## 🚨 Critical Warnings

| Rule | Reason |
|------|--------|
| **NEVER bypass privacy caps** | Legal compliance requirement |
| **NEVER modify `presets/` files** | Create new presets instead |
| **NEVER hardcode config values** | Use `ConfigManager.get()` |
| **NEVER source params from raw CLI args** | Must use merged `opt_config` |
| **Entity names are case-sensitive** | Must match data exactly |
| **Output files are gitignored** | `.xlsx`, `.csv`, `.log` won't commit |
| **TUI and CLI share `core/`** | Changes affect both interfaces |

---

## 📂 Gitignored Patterns

```
*.xlsx, *.csv, *.log      # Output files
__pycache__/, *.pyc       # Python cache
venv/, env/, .venv/       # Virtual environments
.vscode/, .idea/          # IDE configs
data/*.csv                # Input data
/offline_packages/*       # Offline install bundles
```
