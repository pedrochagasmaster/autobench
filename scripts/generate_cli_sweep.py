#!/usr/bin/env python
"""
Generate CLI sweep cases for benchmark.py (share/rate/config).

The script inspects the CSV header to pick reasonable columns and writes
case files plus runnable commands into a dedicated folder.
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd


PREFERRED_ENTITY_COLS = [
    "issuer_name",
    "entity_name",
    "bank_name",
    "entity",
    "issuer",
]

PREFERRED_TIME_COLS = [
    "ano_mes",
    "year_month",
    "time_period",
    "period",
    "month",
    "date",
]

PREFERRED_SHARE_METRICS = [
    "volume_brl",
    "transaction_amount",
    "tpv",
    "txn_count",
    "transaction_count",
    "amount",
    "volume",
]

PREFERRED_TOTAL_COLS = [
    "total_txn",
    "total",
    "txn_count",
    "transaction_count",
    "total_volume",
]

PREFERRED_APPROVAL_COLS = [
    "txn_count",
    "approved_count",
    "approved_txn",
    "approved",
    "approval_count",
]

PREFERRED_FRAUD_COLS = [
    "fraud_count",
    "fraud_txn",
    "fraud",
    "fraud_amount",
]


def quote_arg(value: str) -> str:
    if value is None:
        return ""
    value = str(value)
    if any(ch in value for ch in [" ", "\t", "\""]):
        return f'"{value.replace("\"", "\\\"")}"'
    return value


def _score_columns(columns: List[str]) -> int:
    score = 0
    if pick_first(columns, PREFERRED_ENTITY_COLS):
        score += 3
    if pick_first(columns, PREFERRED_TIME_COLS):
        score += 2
    if pick_first(columns, PREFERRED_SHARE_METRICS):
        score += 2
    if pick_first(columns, PREFERRED_TOTAL_COLS):
        score += 2
    if pick_first(columns, PREFERRED_APPROVAL_COLS):
        score += 2
    if pick_first(columns, PREFERRED_FRAUD_COLS):
        score += 1
    return score


def _read_columns(csv_path: Path) -> List[str]:
    try:
        return list(pd.read_csv(csv_path, nrows=0).columns)
    except Exception:
        return []


def find_default_csv() -> Path:
    data_candidates = sorted(Path("data").glob("*.csv"))
    candidates = [c for c in data_candidates if not c.name.endswith("_balanced.csv")]
    if not candidates:
        candidates = [c for c in sorted(Path(".").glob("*.csv")) if not c.name.endswith("_balanced.csv")]
    if not candidates:
        raise FileNotFoundError("No CSV files found in data/ or project root.")

    scored = []
    for candidate in candidates:
        cols = _read_columns(candidate)
        score = _score_columns(cols)
        scored.append((score, candidate))
    scored.sort(key=lambda x: (-x[0], x[1].name))
    return scored[0][1]


def read_sample(csv_path: Path) -> pd.DataFrame:
    return pd.read_csv(csv_path, nrows=200)


def pick_first(columns: Iterable[str], preferred: List[str]) -> Optional[str]:
    for name in preferred:
        if name in columns:
            return name
    return None


def choose_entity_col(columns: List[str]) -> str:
    return pick_first(columns, PREFERRED_ENTITY_COLS) or columns[0]


def choose_time_col(columns: List[str]) -> Optional[str]:
    return pick_first(columns, PREFERRED_TIME_COLS)


def choose_metric(columns: List[str], numeric_cols: List[str]) -> Optional[str]:
    metric = pick_first(columns, PREFERRED_SHARE_METRICS)
    if metric:
        return metric
    for col in numeric_cols:
        if col not in columns:
            continue
        return col
    return None


def choose_total_col(columns: List[str], numeric_cols: List[str]) -> Optional[str]:
    total = pick_first(columns, PREFERRED_TOTAL_COLS)
    if total:
        return total
    for col in numeric_cols:
        return col
    return None


def choose_approved_col(
    columns: List[str],
    numeric_cols: List[str],
    total_col: Optional[str],
) -> Optional[str]:
    approved = pick_first(columns, PREFERRED_APPROVAL_COLS)
    if approved:
        return approved
    for col in numeric_cols:
        if col != total_col:
            return col
    return total_col


def choose_fraud_col(columns: List[str]) -> Optional[str]:
    return pick_first(columns, PREFERRED_FRAUD_COLS)


def choose_dimensions(df: pd.DataFrame, reserved: List[str], count: int = 2) -> List[str]:
    dim_candidates = [
        c for c in df.columns
        if c not in reserved and not pd.api.types.is_numeric_dtype(df[c])
    ]
    if len(dim_candidates) < count:
        dim_candidates = [c for c in df.columns if c not in reserved]
    return dim_candidates[:count]


def choose_secondary_metrics(df: pd.DataFrame, reserved: List[str], count: int = 2) -> List[str]:
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    candidates = [c for c in numeric_cols if c not in reserved]
    return candidates[:count]


def pick_sample_entity(df: pd.DataFrame, entity_col: str) -> Optional[str]:
    if entity_col not in df.columns:
        return None
    series = df[entity_col].dropna()
    if series.empty:
        return None
    return str(series.iloc[0])


def list_presets() -> List[str]:
    return sorted([p.stem for p in Path("presets").glob("*.yaml")])


def build_command(base: List[str], flags: List[str]) -> str:
    parts = base + flags
    return " ".join(quote_arg(p) for p in parts if p)


def add_flag(args: List[str], flag: str, value) -> None:
    if value is None:
        return
    if isinstance(value, bool):
        if value:
            args.append(flag)
        return
    if isinstance(value, list):
        if not value:
            return
        args.append(flag)
        args.extend(str(v) for v in value)
        return
    args.extend([flag, str(value)])


def make_case(case_id: str, command: str, params: Dict, expectations: List[str]) -> Dict:
    return {
        "id": case_id,
        "command": command,
        "params": params,
        "expectations": expectations,
    }


def expectations_for_case(params: Dict, analysis_type: str, output_path: Optional[Path]) -> List[str]:
    expectations: List[str] = []

    output_format = params.get("output_format")
    publication_format = params.get("publication_format")
    if publication_format:
        output_format = "publication"

    if output_format in (None, "analysis", "both"):
        expectations.append("analysis_workbook")
    if output_format in ("publication", "both"):
        expectations.append("publication_workbook")

    if params.get("export_balanced_csv"):
        expectations.append("balanced_csv")
        if params.get("include_calculated"):
            expectations.append("csv_includes_raw_and_impact_columns")

    if params.get("compare_presets"):
        expectations.append("preset_comparison_sheet")

    if params.get("analyze_distortion"):
        expectations.append("impact_analysis_sheet")

    if params.get("secondary_metrics"):
        expectations.append("secondary_metrics_sheet")

    if params.get("validate_input") is False:
        expectations.append("no_data_quality_sheet")
    else:
        expectations.append("data_quality_sheet")

    if params.get("per_dimension_weights"):
        expectations.append("per_dimension_weight_methods")

    if analysis_type == "rate":
        if params.get("fraud_col") and params.get("fraud_in_bps") is True and output_format in ("publication", "both"):
            expectations.append("fraud_in_bps_in_publication")
        if params.get("fraud_col") and params.get("fraud_in_bps") is False and output_format in ("publication", "both"):
            expectations.append("fraud_in_percent_in_publication")

    if params.get("entity"):
        expectations.append("target_columns_present")
    else:
        expectations.append("peer_only_mode")

    if output_path is None:
        expectations.append("output_filename_auto_generated")
    else:
        expectations.append(f"output_base={output_path}")
        expectations.append(f"audit_log={output_path.with_suffix('').name}_audit.log")

    return expectations


def write_cases(out_dir: Path, cases: List[Dict], commands: List[str]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    cases_path = out_dir / "cases.jsonl"
    commands_path = out_dir / "commands.ps1"

    with cases_path.open("w", encoding="utf-8") as f:
        for case in cases:
            f.write(json.dumps(case, ensure_ascii=True) + "\n")

    with commands_path.open("w", encoding="utf-8") as f:
        for cmd in commands:
            f.write(cmd + "\n")


def generate_gate_cases(
    analysis_type: str,
    base_args: List[str],
    output_dir: Path,
    csv_path: Path,
    entity: Optional[str],
    entity_col: str,
    dimensions: List[str],
    time_col: Optional[str],
    presets: List[str],
    config_path: Optional[Path],
    secondary_metrics: List[str] = None,
    fraud_col: Optional[str] = None,
) -> Tuple[List[Dict], List[str]]:
    """
    Generate a minimal set of "gate" cases that cover most code paths
    without combinatorial explosion.
    """
    cases: List[Dict] = []
    commands: List[str] = []

    # Helper to clean up flag building
    def make_gate_case(cid_suffix: str, extra_params: Dict, extra_flags: List[str]):
        case_id = f"{analysis_type}_gate_{cid_suffix}"
        output_path = output_dir / f"{case_id}.xlsx"
        
        # Base params (defaults)
        params = {
            "csv": str(csv_path),
            "entity": entity,
            "entity_col": entity_col,
            "dimensions": dimensions,
            "output_format": "analysis",
            "validate_input": True,
            "output": str(output_path),
            **extra_params
        }
        
        # Base flags
        flags = ["--csv", str(csv_path), "--entity-col", entity_col]
        
        # Handle Entity (allow override in extra_params, else default to entity if present)
        if "entity" in extra_params:
            if extra_params["entity"] is not None:
                flags.extend(["--entity", extra_params["entity"]])
        elif entity:
            flags.extend(["--entity", entity])
            
        # Handle Dimensions (allow override)
        if "dimensions" in extra_params:
            if extra_params["dimensions"]:
                flags.extend(["--dimensions", *extra_params["dimensions"]])
        elif "auto" in extra_params and extra_params["auto"]:
            flags.append("--auto")
        else:
             flags.extend(["--dimensions", *dimensions])

        if time_col:
            flags.extend(["--time-col", time_col])
            
        flags.extend(["--output", str(output_path)])
        flags.extend(extra_flags)
        
        cmd = build_command(base_args, flags)
        expectations = expectations_for_case(params, analysis_type, output_path)
        cases.append(make_case(case_id, cmd, params, expectations))
        commands.append(cmd)

    # Case 1: Baseline (Target + Manual Dims + Analysis + Validate)
    make_gate_case("baseline", {}, ["--output-format", "analysis", "--validate-input"])

    # Case 2: Peer + Auto Dims + Publication + No Validate
    # Note: entity=None implies peer-only
    make_gate_case(
        "peer_auto_pub", 
        {"entity": None, "dimensions": None, "auto": True, "output_format": "publication", "validate_input": False}, 
        ["--auto", "--output-format", "publication", "--no-validate-input"]
    )

    # Case 3: Preset + Impact/Distortion (if available)
    if presets:
        preset = presets[0]
        make_gate_case(
            "preset_impact",
            {"preset": preset, "analyze_distortion": True},
            ["--preset", preset, "--analyze-distortion"]
        )

    # Case 4: Config + Balanced CSV (with calc)
    if config_path:
        make_gate_case(
            "config_csv",
            {"config": str(config_path), "export_balanced_csv": True, "include_calculated": True},
            ["--config", str(config_path), "--export-balanced-csv", "--include-calculated"]
        )
        
    # Case 5: Rate Specific - Fraud (if applicable)
    if analysis_type == "rate" and fraud_col:
        make_gate_case(
            "fraud_bps",
            {"fraud_col": fraud_col, "fraud_in_bps": True, "output_format": "publication"},
            ["--fraud-col", fraud_col, "--fraud-in-bps", "--output-format", "publication"]
        )

    return cases, commands


def generate_core_cases(
    analysis_type: str,
    base_args: List[str],
    output_dir: Path,
    csv_path: Path,
    entity: Optional[str],
    entity_col: str,
    dimensions: List[str],
    time_col: Optional[str],
    presets: List[str],
    config_path: Optional[Path],
) -> Tuple[List[Dict], List[str]]:
    cases: List[Dict] = []
    commands: List[str] = []

    entity_modes = [
        ("target", {"entity": entity}),
        ("peer_only", {"entity": None}),
    ]

    dim_modes = [
        ("manual", {"dimensions": dimensions, "auto": False}),
        ("auto", {"dimensions": None, "auto": True}),
    ]

    preset_modes: List[Tuple[str, Dict]] = [("none", {})]
    for preset in presets:
        preset_modes.append((f"preset_{preset}", {"preset": preset}))
    if config_path:
        preset_modes.append(("config", {"config": str(config_path)}))
        for preset in presets:
            preset_modes.append((f"config_preset_{preset}", {"config": str(config_path), "preset": preset}))

    output_formats = [
        ("analysis", {"output_format": "analysis"}),
        ("publication", {"output_format": "publication"}),
        ("both", {"output_format": "both"}),
    ]

    validate_modes = [
        ("validate_default", {}),
        ("validate_on", {"validate_input": True}),
        ("validate_off", {"validate_input": False}),
    ]

    for (entity_label, entity_params), (dim_label, dim_params), (preset_label, preset_params), (
        fmt_label,
        fmt_params,
    ), (val_label, val_params) in itertools.product(
        entity_modes, dim_modes, preset_modes, output_formats, validate_modes
    ):
        case_id = f"{analysis_type}_core_{entity_label}_{dim_label}_{preset_label}_{fmt_label}_{val_label}"
        output_path = output_dir / f"{case_id}.xlsx"

        params: Dict = {
            "csv": str(csv_path),
            "entity": entity_params.get("entity"),
            "entity_col": entity_col,
            **dim_params,
            **preset_params,
            **fmt_params,
            **val_params,
        }

        flags: List[str] = []
        add_flag(flags, "--csv", params["csv"])
        if params.get("entity"):
            add_flag(flags, "--entity", params["entity"])
        add_flag(flags, "--entity-col", entity_col)
        if params.get("dimensions"):
            add_flag(flags, "--dimensions", params["dimensions"])
        elif params.get("auto"):
            add_flag(flags, "--auto", True)
        if time_col:
            add_flag(flags, "--time-col", time_col)
        if params.get("preset"):
            add_flag(flags, "--preset", params["preset"])
        if params.get("config"):
            add_flag(flags, "--config", params["config"])
        add_flag(flags, "--output-format", params.get("output_format"))
        if params.get("validate_input") is True:
            add_flag(flags, "--validate-input", True)
        if params.get("validate_input") is False:
            add_flag(flags, "--no-validate-input", True)
        add_flag(flags, "--output", str(output_path))

        command = build_command(base_args, flags)
        expectations = expectations_for_case(params, analysis_type, output_path)

        cases.append(make_case(case_id, command, params, expectations))
        commands.append(command)

    return cases, commands


def generate_feature_cases(
    analysis_type: str,
    base_args: List[str],
    output_dir: Path,
    csv_path: Path,
    entity: Optional[str],
    entity_col: str,
    dimensions: List[str],
    time_col: Optional[str],
    presets: List[str],
    config_path: Optional[Path],
    secondary_metrics: List[str],
    fraud_col: Optional[str] = None,
) -> Tuple[List[Dict], List[str]]:
    cases: List[Dict] = []
    commands: List[str] = []

    baseline_id = f"{analysis_type}_feature_baseline"
    baseline_output = output_dir / f"{baseline_id}.xlsx"

    baseline_params: Dict = {
        "csv": str(csv_path),
        "entity": entity,
        "entity_col": entity_col,
        "dimensions": dimensions,
        "auto": False,
        "output_format": "analysis",
        "validate_input": True,
    }

    def build_base_flags(output_path: Path) -> List[str]:
        flags: List[str] = []
        add_flag(flags, "--csv", str(csv_path))
        if entity:
            add_flag(flags, "--entity", entity)
        add_flag(flags, "--entity-col", entity_col)
        add_flag(flags, "--dimensions", dimensions)
        if time_col:
            add_flag(flags, "--time-col", time_col)
        add_flag(flags, "--output", str(output_path))
        add_flag(flags, "--output-format", "analysis")
        add_flag(flags, "--validate-input", True)
        return flags

    baseline_flags = build_base_flags(baseline_output)
    baseline_command = build_command(base_args, baseline_flags)
    baseline_expectations = expectations_for_case(baseline_params, analysis_type, baseline_output)
    cases.append(make_case(baseline_id, baseline_command, baseline_params, baseline_expectations))
    commands.append(baseline_command)

    feature_defs = [
        ("debug", {"debug": True}, ["--debug"]),
        ("per_dimension_weights", {"per_dimension_weights": True}, ["--per-dimension-weights"]),
        ("export_balanced_csv", {"export_balanced_csv": True}, ["--export-balanced-csv"]),
        (
            "export_balanced_csv_with_calc",
            {"export_balanced_csv": True, "include_calculated": True},
            ["--export-balanced-csv", "--include-calculated"],
        ),
        ("compare_presets", {"compare_presets": True}, ["--compare-presets"]),
        ("analyze_distortion", {"analyze_distortion": True}, ["--analyze-distortion"]),
        ("auto_subset_search", {"auto_subset_search": True}, ["--auto-subset-search"]),
        ("subset_search_max_tests", {"subset_search_max_tests": 50}, ["--subset-search-max-tests", "50"]),
        ("trigger_subset_on_slack", {"trigger_subset_on_slack": True}, ["--trigger-subset-on-slack"]),
        ("max_cap_slack", {"max_cap_slack": 0.5}, ["--max-cap-slack", "0.5"]),
        ("publication_format_alias", {"publication_format": True}, ["--publication-format"]),
        ("output_format_both", {"output_format": "both"}, ["--output-format", "both"]),
        ("log_level_debug", {"log_level": "DEBUG"}, ["--log-level", "DEBUG"]),
        ("log_level_info", {"log_level": "INFO"}, ["--log-level", "INFO"]),
        ("log_level_warning", {"log_level": "WARNING"}, ["--log-level", "WARNING"]),
        ("log_level_error", {"log_level": "ERROR"}, ["--log-level", "ERROR"]),
        (
            "secondary_metrics",
            {"secondary_metrics": secondary_metrics},
            ["--secondary-metrics"] + secondary_metrics if secondary_metrics else [],
        ),
    ]

    if presets:
        feature_defs.append(("preset_only", {"preset": presets[0]}, ["--preset", presets[0]]))
    if config_path:
        feature_defs.append(("config_only", {"config": str(config_path)}, ["--config", str(config_path)]))
        if presets:
            feature_defs.append(
                (
                    "config_and_preset",
                    {"config": str(config_path), "preset": presets[0]},
                    ["--config", str(config_path), "--preset", presets[0]],
                )
            )

    if analysis_type == "rate" and fraud_col:
        feature_defs.append(("fraud_in_bps", {"fraud_in_bps": True}, ["--fraud-in-bps"]))
        feature_defs.append(("fraud_in_percent", {"fraud_in_bps": False}, ["--no-fraud-in-bps"]))

    for feature_name, param_updates, extra_flags in feature_defs:
        case_id = f"{analysis_type}_feature_{feature_name}"
        output_path = output_dir / f"{case_id}.xlsx"
        flags = build_base_flags(output_path)
        flags.extend(extra_flags)
        params = {**baseline_params, **param_updates}

        command = build_command(base_args, flags)
        expectations = expectations_for_case(params, analysis_type, output_path)
        cases.append(make_case(case_id, command, params, expectations))
        commands.append(command)

    # Output without explicit --output to test auto naming
    case_id = f"{analysis_type}_feature_output_default"
    flags = build_base_flags(output_dir / f"{case_id}.xlsx")
    if "--output" in flags:
        idx = flags.index("--output")
        del flags[idx : idx + 2]
    params = dict(baseline_params)
    params["output_format"] = "analysis"
    command = build_command(base_args, flags)
    expectations = expectations_for_case(params, analysis_type, None)
    cases.append(make_case(case_id, command, params, expectations))
    commands.append(command)

    return cases, commands


def generate_config_cases(out_dir: Path, presets: List[str]) -> Tuple[List[Dict], List[str]]:
    cases: List[Dict] = []
    commands: List[str] = []

    list_cmd = "py benchmark.py config list"
    cases.append(make_case("config_list", list_cmd, {}, ["list_presets_output"]))
    commands.append(list_cmd)

    for preset in presets:
        cmd = f"py benchmark.py config show {quote_arg(preset)}"
        cases.append(make_case(f"config_show_{preset}", cmd, {"preset": preset}, ["preset_details_output"]))
        commands.append(cmd)

    template_path = Path("config") / "template.yaml"
    if template_path.exists():
        cmd = f"py benchmark.py config validate {quote_arg(str(template_path))}"
        cases.append(make_case("config_validate_template", cmd, {"config": str(template_path)}, ["validate_template_ok"]))
        commands.append(cmd)

        output_template = out_dir / "generated_template.yaml"
        cmd = f"py benchmark.py config generate {quote_arg(str(output_template))}"
        cases.append(make_case("config_generate_template", cmd, {"output": str(output_template)}, ["template_created"]))
        commands.append(cmd)

    return cases, commands


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate CLI sweep cases for benchmark.py")
    parser.add_argument("--csv", help="Path to input CSV. Defaults to first CSV in data/.")
    parser.add_argument("--out-dir", default="test_sweeps", help="Output directory for sweep cases")
    parser.add_argument("--mode", choices=["core", "exhaustive", "gate"], default="core", help="Sweep mode")
    parser.add_argument("--max-cases", type=int, default=5000, help="Safety cap for exhaustive mode")
    parser.add_argument("--allow-large", action="store_true", help="Allow case count to exceed max-cases")
    parser.add_argument("--entity-col", help="Override entity column name")
    parser.add_argument("--entity", help="Override entity value for target cases")
    parser.add_argument("--time-col", help="Override time column name")
    parser.add_argument("--metric-col", help="Override share metric column name")
    parser.add_argument("--total-col", help="Override rate total column name")
    parser.add_argument("--approved-col", help="Override rate approval column name")
    parser.add_argument("--fraud-col", help="Override rate fraud column name")
    parser.add_argument("--dimensions", nargs="+", help="Override dimension columns (space-separated)")
    parser.add_argument("--secondary-metrics", nargs="+", help="Override secondary metrics (space-separated)")
    args = parser.parse_args()

    csv_path = Path(args.csv) if args.csv else find_default_csv()
    df = read_sample(csv_path)
    columns = list(df.columns)
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]

    entity_col = args.entity_col or choose_entity_col(columns)
    time_col = args.time_col or choose_time_col(columns)
    entity_value = args.entity or pick_sample_entity(df, entity_col)

    metric_col = args.metric_col or choose_metric(columns, numeric_cols)
    total_col = args.total_col or choose_total_col(columns, numeric_cols)
    approved_col = args.approved_col or choose_approved_col(columns, numeric_cols, total_col)
    fraud_col = args.fraud_col or choose_fraud_col(columns)

    if metric_col is None:
        print("ERROR: Could not infer share metric column.")
        return 1
    if total_col is None or approved_col is None:
        print("ERROR: Could not infer rate columns (total or approval).")
        print(f"Numeric columns detected: {numeric_cols}")
        return 1
    if approved_col == total_col and args.approved_col is None:
        print(
            "WARNING: Approval column not found; using total_col as approval_col. "
            "Rates will be 100% in these sweeps. Override with --approved-col to avoid this."
        )

    reserved = [entity_col, time_col, metric_col, total_col, approved_col, fraud_col]
    dimensions = args.dimensions or choose_dimensions(df, [c for c in reserved if c])
    if not dimensions:
        print("ERROR: Could not infer dimension columns.")
        return 1

    secondary_metrics = args.secondary_metrics or choose_secondary_metrics(df, [c for c in reserved if c])

    presets = list_presets()
    config_path = Path("config") / "template.yaml"
    if not config_path.exists():
        config_path = None

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    meta = {
        "csv": str(csv_path),
        "entity_col": entity_col,
        "entity_value": entity_value,
        "time_col": time_col,
        "metric_col": metric_col,
        "total_col": total_col,
        "approved_col": approved_col,
        "fraud_col": fraud_col,
        "dimensions": dimensions,
        "secondary_metrics": secondary_metrics,
        "presets": presets,
        "config_template": str(config_path) if config_path else None,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # Share cases
    share_base = ["py", "benchmark.py", "share", "--metric", metric_col]
    share_output_dir = out_dir / "share"
    share_output_dir.mkdir(parents=True, exist_ok=True)
    share_outputs = out_dir / "outputs" / "share"
    share_outputs.mkdir(parents=True, exist_ok=True)

    share_cases: List[Dict] = []
    share_commands: List[str] = []

    if args.mode == "gate":
        cases, commands = generate_gate_cases(
            "share",
            share_base,
            share_outputs,
            csv_path,
            entity_value,
            entity_col,
            dimensions,
            time_col,
            presets,
            config_path,
            secondary_metrics,
        )
        share_cases.extend(cases)
        share_commands.extend(commands)
    elif args.mode == "core":
        cases, commands = generate_core_cases(
            "share",
            share_base,
            share_outputs,
            csv_path,
            entity_value,
            entity_col,
            dimensions,
            time_col,
            presets,
            config_path,
        )
        share_cases.extend(cases)
        share_commands.extend(commands)

        feat_cases, feat_commands = generate_feature_cases(
            "share",
            share_base,
            share_outputs,
            csv_path,
            entity_value,
            entity_col,
            dimensions,
            time_col,
            presets,
            config_path,
            secondary_metrics,
        )
        share_cases.extend(feat_cases)
        share_commands.extend(feat_commands)
    else:
        base_cases, base_commands = generate_core_cases(
            "share",
            share_base,
            share_outputs,
            csv_path,
            entity_value,
            entity_col,
            dimensions,
            time_col,
            presets,
            config_path,
        )
        share_cases.extend(base_cases)
        share_commands.extend(base_commands)

        total_cases = len(share_cases)
        if total_cases > args.max_cases and not args.allow_large:
            print(f"ERROR: Exhaustive mode would generate {total_cases} cases. Use --allow-large or --mode core.")
            return 1

    write_cases(share_output_dir, share_cases, share_commands)

    # Rate cases
    rate_base = ["py", "benchmark.py", "rate", "--total-col", total_col, "--approved-col", approved_col]
    rate_output_dir = out_dir / "rate"
    rate_output_dir.mkdir(parents=True, exist_ok=True)
    rate_outputs = out_dir / "outputs" / "rate"
    rate_outputs.mkdir(parents=True, exist_ok=True)

    rate_cases: List[Dict] = []
    rate_commands: List[str] = []

    if args.mode == "gate":
        cases, commands = generate_gate_cases(
            "rate",
            rate_base,
            rate_outputs,
            csv_path,
            entity_value,
            entity_col,
            dimensions,
            time_col,
            presets,
            config_path,
            secondary_metrics,
            fraud_col=fraud_col,
        )
        rate_cases.extend(cases)
        rate_commands.extend(commands)
    elif args.mode == "core":
        cases, commands = generate_core_cases(
            "rate",
            rate_base,
            rate_outputs,
            csv_path,
            entity_value,
            entity_col,
            dimensions,
            time_col,
            presets,
            config_path,
        )
        rate_cases.extend(cases)
        rate_commands.extend(commands)

        feat_cases, feat_commands = generate_feature_cases(
            "rate",
            rate_base,
            rate_outputs,
            csv_path,
            entity_value,
            entity_col,
            dimensions,
            time_col,
            presets,
            config_path,
            secondary_metrics,
            fraud_col=fraud_col,
        )
        rate_cases.extend(feat_cases)
        rate_commands.extend(feat_commands)
    else:
        base_cases, base_commands = generate_core_cases(
            "rate",
            rate_base,
            rate_outputs,
            csv_path,
            entity_value,
            entity_col,
            dimensions,
            time_col,
            presets,
            config_path,
        )
        rate_cases.extend(base_cases)
        rate_commands.extend(base_commands)

        total_cases = len(rate_cases)
        if total_cases > args.max_cases and not args.allow_large:
            print(f"ERROR: Exhaustive mode would generate {total_cases} cases. Use --allow-large or --mode core.")
            return 1

    write_cases(rate_output_dir, rate_cases, rate_commands)

    # Config cases
    config_out_dir = out_dir / "config"
    config_out_dir.mkdir(parents=True, exist_ok=True)
    config_cases, config_commands = generate_config_cases(config_out_dir, presets)
    write_cases(config_out_dir, config_cases, config_commands)

    print(f"Sweep cases generated under: {out_dir}")
    print("Check meta.json for inferred columns and entity value.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
