# Privacy-Compliant Peer Benchmark Tool Instructions

## Project Overview
This is a Python-based dimensional analysis tool designed to compare financial entities against peer groups while strictly enforcing Mastercard privacy compliance rules (Control 3.2). It uses advanced optimization techniques (Linear Programming and Bayesian Optimization) to generate privacy-compliant peer weights.

## Architecture & Core Components
The system follows a configuration-driven architecture with a clear separation of concerns:

- **Entry Points**:
  - `benchmark.py`: CLI parsing and orchestration.
  - `tui_app.py`: Textual-based Terminal User Interface (TUI) for interactive workflows.
    - Uses `ListView` for filtered CSV file selection (current dir + `data/`).
    - Uses dynamic `Select` widgets for column and entity selection, populated by reading CSV headers and unique values via `pandas`.
    - Implements `FileListItem` to handle file paths safely.
- **Core Logic** (`core/`):
  - `DataLoader`: Handles CSV/SQL ingestion and schema validation. Normalizes column names.
  - `DimensionalAnalyzer`: The core engine. Calculates weighted peer averages using a multi-tier optimization strategy.
  - `PrivacyValidator`: Enforces concentration rules (e.g., 5/25, 6/30) based on peer count.
  - `ReportGenerator`: Produces multi-sheet Excel reports with debug and audit trails.
- **Configuration**: Uses YAML-based configuration and presets (`config/`, `presets/`).
  - **Hierarchy**: Defaults -> Preset -> Config File -> CLI Args.
  - **Integrity**: All analysis logic must source parameters from the merged `opt_config` object, NOT raw CLI args, to ensure presets are respected.

### Optimization Strategy (Critical)
The tool uses a sophisticated fallback mechanism to find privacy-compliant weights:
1.  **Global Linear Programming (HiGHS)**: Attempts to solve for one set of weights satisfying constraints across ALL dimensions.
    - Supports **Volume-Weighted Penalties** to prioritize compliance in high-volume categories.
    - Uses **Slack Variables** to allow controlled violations if configured.
2.  **Subset Search**: If Global LP fails, identifies the largest subset of dimensions that can be solved globally.
3.  **Per-Dimension LP**: Solves for dropped dimensions independently.
4.  **Bayesian Optimization (L-BFGS-B)**: Fallback for structural infeasibility; minimizes violations when LP fails.

## Key Workflows

### Running Analysis
The tool is CLI-driven but often used via the TUI.

**CLI Patterns:**
```bash
# Share analysis (distribution of volume/count)
py benchmark.py share --csv data/input.csv --entity "TARGET_BANK" --metric txn_cnt --preset standard

# Rate analysis (approval/fraud rates)
py benchmark.py rate --csv data/input.csv --entity "TARGET_BANK" --total-col txn_cnt --approved-col app_cnt
```

**TUI Workflow:**
- **File Selection**: Select CSV from the filtered list (`ListView`).
- **Entity Configuration**:
  - Select "Entity Column" (left dropdown).
  - Select "Target Entity" (right dropdown, auto-populated based on column selection).
- **Preset Selection**: Choose a Preset from the dropdown.
- **Analysis Configuration**:
  - **Share Tab**: Select Primary Metric.
  - **Rate Tab**: Select Total, Approved, and Fraud columns.
  - **Secondary Metrics/Dimensions**: Text inputs for space-separated values.

### Configuration
- **Presets** (`presets/`):
  - `compliance_strict`: Zero tolerance for violations. May drop dimensions.
  - `strategic_consistency`: Prioritizes global weights. Uses volume-weighted penalties to minimize business impact of violations.
  - `balanced_default`: Good balance for day-to-day analysis. Allows small violations (2%).
  - `research_exploratory`: For difficult datasets. Lower rank preservation, higher weight bounds.
- Use `py benchmark.py config list` to see available presets.

## Coding Conventions & Patterns

- **Privacy First**: All aggregation logic must pass through `PrivacyValidator`. Never bypass concentration checks.
- **Data Frames**:
  - Input data is expected to be "long" format (one row per entity-dimension combination).
  - Column names are normalized internally but CLI flags must match input CSV headers.
- **TUI Development**:
  - Use `FileListItem` for file lists to avoid ID collision issues with paths.
  - Populate `Select` widgets dynamically using `pd.read_csv(..., nrows=0)` for efficiency.
  - Use `Select` widgets for single-choice fields (columns, entities).
  - Use `Input` widgets for multi-value fields (secondary metrics, dimensions).
- **Optimization**:
  - When modifying `DimensionalAnalyzer`, ensure the fallback logic (Global -> Subset -> Per-Dim -> Bayesian) is preserved.
  - Use `scipy.optimize` for solver integration.
- **Logging**: Use the centralized logger (`utils.logger`).
- **Reporting**: Excel reports must include a full dump of "Optimization Parameters" sourced from `opt_config` for auditability.

## Project Structure
- `benchmark.py`: Main CLI entry point.
- `tui_app.py`: Terminal User Interface application.
- `core/`: Business logic and analysis engines.
- `config/`: Configuration templates and validation logic.
- `data/`: Input datasets (CSV/SQL).
- `presets/`: Pre-defined analysis configurations.
- `utils/`: Shared utilities (logging, config management).
