# Analytics Benchmark Tool

## Overview

The `benchmark_tool.py` is a flexible analytics engine for benchmarking financial institutions or other entities using peer group analysis. It supports both **rate** and **share** analyses, allowing you to compare your institution's performance against dynamically selected peer groups, with robust privacy and balancing rules.

## Features
- **Rate Analysis**: Find peer groups and calculate approval/fraud rates using configurable privacy rules.
- **Share Analysis**: Calculate the average market share for your peer group in any category.
- **Dynamic Peer Group Selection**: Automatically finds valid peer combinations based on your rules.
- **Flexible Breaks**: Analyze by any column or combination of columns (e.g., `wallet_flag:super_industry_name_grouped`).
- **Presets**: Use or define custom analysis presets for common scenarios.
- **Excel Output**: Results are saved to Excel with clear sheet names and headers.
- **Logging**: Each run generates a detailed log file of the analysis process.

## Requirements
- Python 3.8+
- pandas
- numpy
- openpyxl
- scikit-learn

Install requirements with:
```sh
pip install -r requirements.txt
```

## Usage

### CLI Structure
The tool uses subcommands for different analysis types:
- `rate` — Approval/fraud rate analysis
- `share` — Market share analysis
- `legacy` — (For compatibility with old scripts)

### Example: Rate Analysis
```sh
python benchmark_tool.py rate \
  --csv query-impala-7310928.csv \
  --issuer "BANCO SANTANDER (BRASIL) S.A." \
  --issuer-col issuer_name \
  --participants 4 \
  --max-percent 35 \
  --break month_year super_industry_name_grouped wallet_flag wallet_flag:super_industry_name_grouped \
  --combinations 5 1 2
```

### Example: Share Analysis
```sh
python benchmark_tool.py share \
  --csv query-impala-7310928.csv \
  --issuer "BANCO SANTANDER (BRASIL) S.A." \
  --issuer-col issuer_name \
  --participants 4 \
  --max-percent 35 \
  --break wallet_flag \
  --combinations 5 1 2
```

### CLI Options
- `--csv`           : Path to the CSV file
- `--issuer`        : Name of the institution to analyze
- `--issuer-col`    : Column name for issuer/institution
- `--participants`  : Number of peers in each group
- `--max-percent`   : Maximum allowed share per peer (privacy rule)
- `--break`         : One or more columns (or combined columns with `:`) to break analysis by
- `--combinations`  : Priority order of combinations to try (e.g., `5 1 2`)
- `--preset`        : (Optional) Use a named preset from `presets.json`

### Presets
You can define custom analysis presets in `presets.json`:
```json
{
  "conservative": { "participants": 5, "max_percent": 25, "combinations": [1,2,3,4,5] },
  "aggressive":   { "participants": 4, "max_percent": 40, "combinations": [5,1,2] },
  "my_custom":    { "participants": 6, "max_percent": 30, "combinations": [2,3,1] }
}
```
List available presets:
```sh
python benchmark_tool.py presets
```
Use a preset:
```sh
python benchmark_tool.py rate --csv ... --issuer ... --preset my_custom --break ...
```

### Output Interpretation
- **Excel File**: Results are saved as `benchmark_output_<date>_<type>.xlsx` with one sheet per break.
- **Sheet Headers**: Each sheet includes a header describing the analysis, peer group, and status.
- **Rate Analysis**: Sheets show KPIs like approval rate, BIC rate, fraud BPS, etc.
- **Share Analysis**: Sheets show the peer group's average share for each category.
- **Log File**: A log file is generated for each run, detailing parameters and peer group selection.

## Support
For questions or issues, please contact the project maintainer or open an issue in your repository. 