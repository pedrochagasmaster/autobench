#!/usr/bin/env python
"""Dump additional-constraint violations for a share analysis run."""

import argparse
import json
from datetime import datetime

from core.data_loader import DataLoader
from core.dimensional_analyzer import DimensionalAnalyzer
from utils.config_manager import ConfigManager


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dump additional-constraint violations")
    parser.add_argument("--csv", required=True, help="Path to CSV input file")
    parser.add_argument("--metric", required=True, help="Metric column name")
    parser.add_argument("--time-col", required=True, help="Time column name")
    parser.add_argument("--config", required=True, help="YAML config file")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = ConfigManager(
        config_file=args.config,
        cli_overrides={
            "time_col": args.time_col,
            "auto": True,
        },
    )

    data_loader = DataLoader(config)
    df = data_loader.load_from_csv(args.csv)

    entity_col = config.get("input", "entity_col")
    metric_col = args.metric
    dimensions = data_loader.get_available_dimensions(df)

    opt_config = config.config["optimization"]
    analysis_config = config.config["analysis"]
    dyn_constraints = opt_config.get("constraints", {}).get("dynamic_constraints", {})

    analyzer = DimensionalAnalyzer(
        target_entity=None,
        entity_column=entity_col,
        bic_percentile=analysis_config.get("best_in_class_percentile", 0.85),
        debug_mode=True,
        consistent_weights=True,
        max_iterations=opt_config["linear_programming"]["max_iterations"],
        tolerance=opt_config["linear_programming"]["tolerance"],
        max_weight=opt_config["bounds"]["max_weight"],
        min_weight=opt_config["bounds"]["min_weight"],
        volume_preservation_strength=opt_config["constraints"]["volume_preservation"],
        prefer_slacks_first=opt_config["subset_search"].get("prefer_slacks_first", False),
        auto_subset_search=opt_config["subset_search"].get("enabled", True),
        subset_search_max_tests=opt_config["subset_search"].get("max_attempts", 200),
        greedy_subset_search=(opt_config["subset_search"].get("strategy", "greedy") == "greedy"),
        trigger_subset_on_slack=opt_config["subset_search"].get("trigger_on_slack", True),
        max_cap_slack=opt_config["subset_search"].get("max_slack_threshold", 0.0),
        time_column=args.time_col,
        volume_weighted_penalties=opt_config["linear_programming"].get("volume_weighted_penalties", False),
        volume_weighting_exponent=opt_config["linear_programming"].get("volume_weighting_exponent", 1.0),
        enforce_additional_constraints=opt_config.get("constraints", {}).get("enforce_additional_constraints", True),
        dynamic_constraints_enabled=dyn_constraints.get("enabled", True),
        min_peer_count_for_constraints=dyn_constraints.get("min_peer_count", 4),
        min_effective_peer_count=dyn_constraints.get("min_effective_peer_count", 3.0),
        min_category_volume_share=dyn_constraints.get("min_category_volume_share", 0.001),
        min_overall_volume_share=dyn_constraints.get("min_overall_volume_share", 0.0005),
        min_representativeness=dyn_constraints.get("min_representativeness", 0.1),
        dynamic_threshold_scale_floor=dyn_constraints.get("threshold_scale_floor", 0.6),
        dynamic_count_scale_floor=dyn_constraints.get("count_scale_floor", 0.5),
        representativeness_penalty_floor=dyn_constraints.get("penalty_floor", 0.25),
        representativeness_penalty_power=dyn_constraints.get("penalty_power", 1.0),
    )

    analyzer.calculate_global_privacy_weights(df, metric_col, dimensions)

    violations = getattr(analyzer, "additional_constraint_violations", []) or []
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "violations_count": len(violations),
        "violations": violations,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(json.dumps({"violations_count": len(violations), "output": args.output}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
