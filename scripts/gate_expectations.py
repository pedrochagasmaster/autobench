"""Registry of gate/sweep expectation tokens and their verifiers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set

ExpectationHandler = Callable[..., List[str]]


@dataclass(frozen=True)
class ExpectationSpec:
    """Metadata for a single expectation token."""

    token: str
    status: str  # "enforced" | "informational"
    handler: Optional[ExpectationHandler] = None
    prefix_match: bool = False


# Static tokens (exact match)
STATIC_TOKENS: Dict[str, ExpectationSpec] = {
    "analysis_workbook": ExpectationSpec("analysis_workbook", "enforced"),
    "publication_workbook": ExpectationSpec("publication_workbook", "enforced"),
    "balanced_csv": ExpectationSpec("balanced_csv", "enforced"),
    "share_csv_schema_only": ExpectationSpec("share_csv_schema_only", "informational"),
    "preset_comparison_sheet": ExpectationSpec("preset_comparison_sheet", "enforced"),
    "impact_analysis_sheet": ExpectationSpec("impact_analysis_sheet", "enforced"),
    "data_quality_sheet": ExpectationSpec("data_quality_sheet", "enforced"),
    "no_data_quality_sheet": ExpectationSpec("no_data_quality_sheet", "enforced"),
    "target_columns_present": ExpectationSpec("target_columns_present", "enforced"),
    "peer_only_mode": ExpectationSpec("peer_only_mode", "enforced"),
    "csv_includes_raw_and_impact_columns": ExpectationSpec("csv_includes_raw_and_impact_columns", "enforced"),
    "per_dimension_weight_methods": ExpectationSpec("per_dimension_weight_methods", "enforced"),
    "secondary_metrics_sheet": ExpectationSpec("secondary_metrics_sheet", "enforced"),
    "fraud_in_bps_in_publication": ExpectationSpec("fraud_in_bps_in_publication", "enforced"),
    "fraud_in_percent_in_publication": ExpectationSpec("fraud_in_percent_in_publication", "enforced"),
    "list_presets_output": ExpectationSpec("list_presets_output", "enforced"),
    "preset_details_output": ExpectationSpec("preset_details_output", "enforced"),
    "validate_template_ok": ExpectationSpec("validate_template_ok", "enforced"),
    "template_created": ExpectationSpec("template_created", "enforced"),
    "output_filename_auto_generated": ExpectationSpec("output_filename_auto_generated", "enforced"),
}

PREFIX_TOKENS: Dict[str, ExpectationSpec] = {
    "output_base=": ExpectationSpec("output_base=", "enforced", prefix_match=True),
    "audit_log=": ExpectationSpec("audit_log=", "enforced", prefix_match=True),
}


def resolve_expectation(token: str) -> Optional[ExpectationSpec]:
    if token in STATIC_TOKENS:
        return STATIC_TOKENS[token]
    for prefix, spec in PREFIX_TOKENS.items():
        if token.startswith(prefix):
            return spec
    return None


def all_registered_tokens() -> Set[str]:
    tokens = set(STATIC_TOKENS.keys())
    tokens.update(PREFIX_TOKENS.keys())
    return tokens


def validate_emitted_tokens(tokens: List[str]) -> None:
    """Raise ValueError if any emitted token is not registered."""
    for token in tokens:
        if resolve_expectation(token) is None:
            raise ValueError(f"Unregistered expectation token: {token}")
