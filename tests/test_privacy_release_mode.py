"""Contracts and configuration for PrivacyReleaseMode (Plan 002 Commit 2)."""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, Mapping, Optional, Tuple

import pytest
import yaml

from core.analysis_run import (
    RunAborted,
    check_privacy_release_mode_compatibility,
    resolve_privacy_release_mode,
)
from core.contracts import (
    COVERAGE_CERTIFICATE_ARTIFACT_TYPE,
    AnalysisArtifacts,
    AnalysisRunRequest,
    CoverageCertificate,
    PrivacyReleaseMode,
    PrivacyRuleStrategy,
    PublicationUnit,
    SafeCoverageResult,
)
from utils.config_manager import ConfigManager
from utils.validators import ConfigValidationError, ConfigValidator


def _unit(
    key: str,
    *,
    dimension: str = "region",
    category: str = "North",
    time_period: Optional[str] = "2025Q1",
) -> PublicationUnit:
    return PublicationUnit(
        internal_key=key,
        dimension=dimension,
        category=category,
        time_period=time_period,
        output_scope=None,
        metric_records=({"metric": "transaction_amount", "value": 1.0},),
        applicable_rules=("5/25", "6/30"),
        mandatory_overlays=(),
    )


def _safe_coverage_result(
    *,
    release_keys: Tuple[str, ...] = ("u1",),
    suppression_keys: Tuple[str, ...] = ("u2",),
    primary_objective_value: Optional[int] = None,
    authorizing_rules: Optional[Mapping[str, str]] = None,
    **overrides: Any,
) -> SafeCoverageResult:
    units = tuple(_unit(key) for key in (*release_keys, *suppression_keys))
    kwargs: Dict[str, Any] = {
        "release_mode": PrivacyReleaseMode.MAXIMIZE_SAFE_COVERAGE,
        "global_weights": {"P1": 1.0, "P2": 1.0},
        "candidate_universe": units,
        "release_set": release_keys,
        "suppression_set": suppression_keys,
        "authorizing_rules": authorizing_rules
        or {key: "5/25" for key in release_keys},
        "primary_objective_value": (
            len(release_keys)
            if primary_objective_value is None
            else primary_objective_value
        ),
        "later_objective_values": (0.0, 0.0),
        "solver_state": "optimal",
        "mip_dual_bound": float(len(release_keys)),
        "mip_gap": 0.0,
        "solver_name": "scipy.optimize.milp",
        "solver_version": "1.18.0",
        "input_digest": "input",
        "configuration_digest": "config",
        "policy_version": "v5",
        "policy_source": "docs",
        "rule_set_digest": "rules",
        "candidate_universe_digest": "universe",
        "release_mask_digest": "mask",
        "verifier_result": "accepted",
    }
    kwargs.update(overrides)
    return SafeCoverageResult(**kwargs)


def test_privacy_release_mode_has_exactly_two_values() -> None:
    assert tuple(mode.value for mode in PrivacyReleaseMode) == (
        "complete-output",
        "maximize-safe-coverage",
    )


def test_request_defaults_privacy_release_mode_to_none() -> None:
    request = AnalysisRunRequest(mode="share", metric="amount")
    assert request.privacy_release_mode is None


def test_request_rejects_string_privacy_release_mode() -> None:
    with pytest.raises(TypeError, match="PrivacyReleaseMode"):
        AnalysisRunRequest(
            mode="share",
            metric="amount",
            privacy_release_mode="maximize-safe-coverage",  # type: ignore[arg-type]
        )


def test_resolve_defaults_to_complete_output() -> None:
    request = AnalysisRunRequest(mode="share", metric="amount")
    resolved = ConfigManager().resolve()
    effective = resolve_privacy_release_mode(request, resolved)
    assert effective.privacy_release_mode is PrivacyReleaseMode.COMPLETE_OUTPUT
    assert request.privacy_release_mode is None


def test_resolve_uses_yaml_when_request_is_none(tmp_path) -> None:
    path = tmp_path / "release.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": "3.0",
                "compliance_posture": "strict",
                "privacy_release_mode": "maximize-safe-coverage",
            }
        ),
        encoding="utf-8",
    )
    request = AnalysisRunRequest(mode="share", metric="amount")
    resolved = ConfigManager(config_file=str(path)).resolve()
    effective = resolve_privacy_release_mode(request, resolved)
    assert effective.privacy_release_mode is PrivacyReleaseMode.MAXIMIZE_SAFE_COVERAGE


def test_explicit_enum_overrides_yaml(tmp_path) -> None:
    path = tmp_path / "release.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": "3.0",
                "compliance_posture": "strict",
                "privacy_release_mode": "maximize-safe-coverage",
            }
        ),
        encoding="utf-8",
    )
    request = AnalysisRunRequest(
        mode="share",
        metric="amount",
        privacy_release_mode=PrivacyReleaseMode.COMPLETE_OUTPUT,
        privacy_rule_strategy=PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE,
    )
    resolved = ConfigManager(config_file=str(path)).resolve()
    effective = resolve_privacy_release_mode(request, resolved)
    assert effective.privacy_release_mode is PrivacyReleaseMode.COMPLETE_OUTPUT


def test_cli_none_does_not_override_yaml_privacy_release_mode(tmp_path) -> None:
    path = tmp_path / "release.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": "3.0",
                "compliance_posture": "strict",
                "privacy_release_mode": "maximize-safe-coverage",
            }
        ),
        encoding="utf-8",
    )
    config = ConfigManager(
        config_file=str(path),
        cli_overrides={"privacy_release_mode": None},
    )
    assert config.get("privacy_release_mode") == "maximize-safe-coverage"
    assert (
        config.resolve().privacy_release_mode
        is PrivacyReleaseMode.MAXIMIZE_SAFE_COVERAGE
    )


def test_cli_enum_override_writes_string_value(tmp_path) -> None:
    path = tmp_path / "release.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": "3.0",
                "compliance_posture": "strict",
                "privacy_release_mode": "complete-output",
            }
        ),
        encoding="utf-8",
    )
    config = ConfigManager(
        config_file=str(path),
        cli_overrides={
            "privacy_release_mode": PrivacyReleaseMode.MAXIMIZE_SAFE_COVERAGE
        },
    )
    assert config.get("privacy_release_mode") == "maximize-safe-coverage"


def test_unknown_yaml_privacy_release_mode_rejected(tmp_path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": "3.0",
                "compliance_posture": "strict",
                "privacy_release_mode": "weaken-privacy",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigValidationError, match="privacy_release_mode"):
        ConfigManager(config_file=str(path))


def test_config_validator_rejects_unknown_privacy_release_mode() -> None:
    errors = ConfigValidator.validate(
        {
            "version": "3.0",
            "compliance_posture": "strict",
            "privacy_release_mode": "not-a-mode",
        }
    )
    assert any("privacy_release_mode" in error for error in errors)


def test_maximize_rejects_rate_analysis() -> None:
    request = AnalysisRunRequest(
        mode="rate",
        total_col="total",
        privacy_release_mode=PrivacyReleaseMode.MAXIMIZE_SAFE_COVERAGE,
        privacy_rule_strategy=PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE,
    )
    with pytest.raises(RunAborted, match="rate analysis"):
        check_privacy_release_mode_compatibility(request)


def test_maximize_rejects_per_dimension_weights() -> None:
    request = AnalysisRunRequest(
        mode="share",
        metric="amount",
        per_dimension_weights=True,
        privacy_release_mode=PrivacyReleaseMode.MAXIMIZE_SAFE_COVERAGE,
        privacy_rule_strategy=PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE,
    )
    with pytest.raises(RunAborted, match="global weight vector"):
        check_privacy_release_mode_compatibility(request)


def test_maximize_rejects_incompatible_rule_strategy() -> None:
    request = AnalysisRunRequest(
        mode="share",
        metric="amount",
        privacy_release_mode=PrivacyReleaseMode.MAXIMIZE_SAFE_COVERAGE,
        privacy_rule_strategy=PrivacyRuleStrategy.SELECT_BY_PEER_COUNT,
    )
    with pytest.raises(RunAborted, match="SWEEP_ANY_APPLICABLE"):
        check_privacy_release_mode_compatibility(request)


def test_maximize_accepts_compatible_share_request() -> None:
    request = AnalysisRunRequest(
        mode="share",
        metric="amount",
        privacy_release_mode=PrivacyReleaseMode.MAXIMIZE_SAFE_COVERAGE,
        privacy_rule_strategy=PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE,
    )
    check_privacy_release_mode_compatibility(request)


def test_complete_output_accepts_both_rule_strategies() -> None:
    for strategy in PrivacyRuleStrategy:
        request = AnalysisRunRequest(
            mode="share",
            metric="amount",
            privacy_release_mode=PrivacyReleaseMode.COMPLETE_OUTPUT,
            privacy_rule_strategy=strategy,
        )
        check_privacy_release_mode_compatibility(request)


def test_safe_coverage_result_rejects_overlapping_sets() -> None:
    with pytest.raises(ValueError, match="must not overlap"):
        _safe_coverage_result(
            release_keys=("u1",),
            suppression_keys=("u1",),
            authorizing_rules={"u1": "5/25"},
            candidate_universe=(_unit("u1"),),
        )


def test_safe_coverage_result_rejects_primary_objective_mismatch() -> None:
    with pytest.raises(ValueError, match="primary_objective_value"):
        _safe_coverage_result(primary_objective_value=99)


def test_coverage_certificate_rejects_wrong_artifact_type() -> None:
    with pytest.raises(ValueError, match="artifact_type"):
        CoverageCertificate(
            privacy_release_mode=PrivacyReleaseMode.MAXIMIZE_SAFE_COVERAGE,
            candidate_unit_count=1,
            released_unit_count=1,
            suppressed_unit_count=0,
            coverage_percentage=100.0,
            visible_publication_unit_keys=("u1",),
            authorizing_rules={"u1": "5/25"},
            global_weights={"P1": 1.0},
            policy_version="v5",
            policy_source="docs",
            rule_set_digest="rules",
            solver_name="scipy.optimize.milp",
            solver_version="1.18.0",
            primary_objective_value=1,
            mip_dual_bound=1.0,
            mip_gap=0.0,
            solver_state="optimal",
            artifact_hashes={"analysis": "abc"},
            certificate_digest="digest",
            artifact_type="coverage_certificate.v0",
        )


def test_coverage_certificate_accepts_valid_payload() -> None:
    certificate = CoverageCertificate(
        privacy_release_mode=PrivacyReleaseMode.MAXIMIZE_SAFE_COVERAGE,
        candidate_unit_count=2,
        released_unit_count=1,
        suppressed_unit_count=1,
        coverage_percentage=50.0,
        visible_publication_unit_keys=("u1",),
        authorizing_rules={"u1": "5/25"},
        global_weights={"P1": 1.0},
        policy_version="v5",
        policy_source="docs",
        rule_set_digest="rules",
        solver_name="scipy.optimize.milp",
        solver_version="1.18.0",
        primary_objective_value=1,
        mip_dual_bound=1.0,
        mip_gap=0.0,
        solver_state="optimal",
        artifact_hashes={"analysis": "abc"},
        certificate_digest="digest",
    )
    assert certificate.artifact_type == COVERAGE_CERTIFICATE_ARTIFACT_TYPE


def test_analysis_artifacts_expose_coverage_fields() -> None:
    names = {f.name for f in dataclasses.fields(AnalysisArtifacts)}
    assert {
        "safe_coverage_result",
        "coverage_certificate",
        "coverage_certificate_output",
    } <= names


def test_resolved_config_default_is_complete_output() -> None:
    assert (
        ConfigManager().resolve().privacy_release_mode
        is PrivacyReleaseMode.COMPLETE_OUTPUT
    )
