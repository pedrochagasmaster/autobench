# Privacy-Compliant Peer Benchmark Tool Instructions

## Project Overview
This is a Python-based dimensional analysis tool designed to compare financial entities against peer groups while strictly enforcing Mastercard privacy compliance rules (Control 3.2). It uses advanced optimization techniques (Linear Programming and Bayesian Optimization) to generate privacy-compliant peer weights.

## Architecture & Core Components
The system follows a configuration-driven architecture with a clear separation of concerns:

- **Entry Point**: `benchmark.py` handles CLI parsing and orchestration.
- **Core Logic** (`core/`):
  - `DataLoader`: Handles CSV/SQL ingestion and schema validation.
  - `DimensionalAnalyzer`: The core engine. Calculates weighted peer averages using a 3-tier optimization strategy.
  - `PrivacyValidator`: Enforces concentration rules (e.g., 5/25, 6/30) based on peer count.
  - `ReportGenerator`: Produces multi-sheet Excel reports.
- **Configuration**: Uses YAML-based configuration and presets (`config/`, `presets/`).

### Optimization Strategy (Critical)
The tool uses a 3-tier fallback mechanism to find privacy-compliant weights:
1.  **Global Linear Programming (HiGHS)**: Solves for one set of weights satisfying constraints across ALL dimensions.
2.  **Per-Dimension LP**: If global fails, solves for each dimension independently.
3.  **Bayesian Optimization (L-BFGS-B)**: Fallback for structural infeasibility; minimizes violations.

## Key Workflows

### Running Analysis
The tool is CLI-driven. Common patterns:

```bash
# Share analysis (distribution of volume/count)
py benchmark.py share --csv data/input.csv --entity "TARGET_BANK" --metric txn_cnt --preset standard

# Rate analysis (approval/fraud rates)
py benchmark.py rate --csv data/input.csv --entity "TARGET_BANK" --total-col txn_cnt --approved-col app_cnt
```

### Configuration
- Prefer using **Presets** (`--preset`) for standard analyses.
- Use `py benchmark.py config list` to see available presets.
- Custom configs can be generated via `py benchmark.py config generate`.

## Coding Conventions & Patterns

- **Privacy First**: All aggregation logic must pass through `PrivacyValidator`. Never bypass concentration checks.
- **Data Frames**:
  - Input data is expected to be "long" format (one row per entity-dimension combination).
  - Column names are normalized internally but CLI flags must match input CSV headers.
- **Optimization**:
  - When modifying `DimensionalAnalyzer`, ensure the 3-tier fallback logic is preserved.
  - Use `scipy.optimize` for solver integration.
- **Logging**: Use the centralized logger (`utils.logger`).

## Project Structure
- `core/`: Business logic and analysis engines.
- `config/`: Configuration templates and validation logic.
- `data/`: Input datasets (CSV/SQL).
- `presets/`: Pre-defined analysis configurations.
- `utils/`: Shared utilities (logging, config management).
