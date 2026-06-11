"""Shared advanced configuration override mapping for adapters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import yaml


@dataclass(frozen=True)
class ConfigFieldSpec:
    widget_id: str
    path: Tuple[str, ...]
    kind: str
    default: Any = None
    always_write: bool = False
    read_paths: Tuple[Tuple[str, ...], ...] = ()

    def as_legacy_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "widget_id": self.widget_id,
            "keys": self.path,
            "kind": self.kind,
        }
        if self.always_write:
            data["always_write"] = True
        if self.read_paths:
            data["read_keys"] = list(self.read_paths)
        return data


ADVANCED_FIELD_SPECS: List[ConfigFieldSpec] = [
    ConfigFieldSpec("adv_lp_tolerance", ("optimization", "linear_programming", "tolerance"), "input"),
    ConfigFieldSpec("adv_lp_max_iterations", ("optimization", "linear_programming", "max_iterations"), "input"),
    ConfigFieldSpec("adv_lp_lambda_penalty", ("optimization", "linear_programming", "lambda_penalty"), "input"),
    ConfigFieldSpec("adv_lp_volume_weighting_exponent", ("optimization", "linear_programming", "volume_weighting_exponent"), "input"),
    ConfigFieldSpec("adv_lp_volume_weighted_penalties", ("optimization", "linear_programming", "volume_weighted_penalties"), "checkbox", always_write=True),
    ConfigFieldSpec("adv_constraints_volume_preservation", ("optimization", "constraints", "volume_preservation"), "input"),
    ConfigFieldSpec("adv_bounds_min_weight", ("optimization", "bounds", "min_weight"), "input"),
    ConfigFieldSpec("adv_bounds_max_weight", ("optimization", "bounds", "max_weight"), "input"),
    ConfigFieldSpec("adv_subset_enabled", ("optimization", "subset_search", "enabled"), "checkbox", always_write=True),
    ConfigFieldSpec("adv_subset_strategy", ("optimization", "subset_search", "strategy"), "input"),
    ConfigFieldSpec(
        "adv_subset_max_attempts",
        ("optimization", "subset_search", "max_attempts"),
        "input",
        read_paths=(("optimization", "subset_search", "max_tests"),),
    ),
    ConfigFieldSpec("adv_subset_max_slack_threshold", ("optimization", "subset_search", "max_slack_threshold"), "input"),
    ConfigFieldSpec("adv_subset_trigger_on_slack", ("optimization", "subset_search", "trigger_on_slack"), "checkbox", always_write=True),
    ConfigFieldSpec("adv_subset_prefer_slacks_first", ("optimization", "subset_search", "prefer_slacks_first"), "checkbox", always_write=True),
    ConfigFieldSpec("adv_bayes_max_iterations", ("optimization", "bayesian", "max_iterations"), "input"),
    ConfigFieldSpec("adv_bayes_learning_rate", ("optimization", "bayesian", "learning_rate"), "input"),
    ConfigFieldSpec("adv_analysis_bic_percentile", ("analysis", "best_in_class_percentile"), "input"),
    ConfigFieldSpec("adv_output_debug_sheets", ("output", "include_debug_sheets"), "checkbox", always_write=True),
    ConfigFieldSpec("adv_output_privacy_validation", ("output", "include_privacy_validation"), "checkbox", always_write=True),
]


def nested_get(data: Mapping[str, Any], keys: Iterable[str]) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current


def nested_set(data: Dict[str, Any], keys: Iterable[str], value: Any) -> None:
    key_list = list(keys)
    current = data
    for key in key_list[:-1]:
        current = current.setdefault(key, {})
    current[key_list[-1]] = value


def try_parse_number(value: str) -> Any:
    if value == "":
        return None
    try:
        return float(value) if "." in value else int(value)
    except ValueError:
        return value


class ConfigOverrideBuilder:
    def __init__(self, specs: Optional[List[ConfigFieldSpec]] = None) -> None:
        self.specs = specs or ADVANCED_FIELD_SPECS

    def read_field(self, data: Mapping[str, Any], spec: ConfigFieldSpec) -> Any:
        value = nested_get(data, spec.path)
        if value is None:
            for alt_path in spec.read_paths:
                value = nested_get(data, alt_path)
                if value is not None:
                    break
        return value

    def read_from_mapping(self, values: Mapping[str, Any]) -> Dict[str, Any]:
        yaml_data: Dict[str, Any] = {}
        for spec in self.specs:
            if spec.widget_id not in values:
                continue
            value = values[spec.widget_id]
            if spec.kind == "input":
                if value in ("", None):
                    continue
                value = try_parse_number(str(value))
            nested_set(yaml_data, spec.path, value)
        return yaml_data

    def write_yaml(self, values: Dict[str, Any], path: Path) -> None:
        with open(path, "w", encoding="utf-8") as handle:
            yaml.safe_dump(values, handle, sort_keys=False)


ADVANCED_FIELD_MAP: List[Dict[str, Any]] = [
    spec.as_legacy_dict() for spec in ADVANCED_FIELD_SPECS
]
