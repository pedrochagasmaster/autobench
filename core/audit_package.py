"""Audit package bundle creation."""

from __future__ import annotations

import json
import logging
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

logger = logging.getLogger(__name__)


def _json_default(value: Any) -> str:
    return str(value)


def _add_existing_file(zf: zipfile.ZipFile, path: Optional[str], *, added: set[str]) -> None:
    if not path:
        return
    file_path = Path(path)
    if not file_path.exists():
        logger.warning("Audit package artifact missing: %s", file_path)
        return
    arcname = file_path.name
    if arcname in added:
        return
    zf.write(file_path, arcname)
    added.add(arcname)


def build_validation_summary(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Extract a compact validation/compliance summary for audit packages."""
    return {
        "run_status": metadata.get("run_status"),
        "compliance_verdict": metadata.get("compliance_verdict"),
        "acknowledgement_state": metadata.get("acknowledgement_state"),
        "posture_consistent": metadata.get("posture_consistent"),
        "data_quality_checked": metadata.get("data_quality_checked"),
        "data_quality_publishable": metadata.get("data_quality_publishable"),
        "validation_errors": metadata.get("validation_errors", 0),
        "validation_warnings": metadata.get("validation_warnings", 0),
        "compliance_summary": metadata.get("compliance_summary", {}),
    }


def write_audit_package(
    *,
    analysis_output_file: str,
    report_paths: Iterable[str],
    csv_output: Optional[str],
    audit_log_output: Optional[str],
    config_snapshot: Dict[str, Any],
    metadata: Dict[str, Any],
) -> str:
    """Create a zip archive containing the run's audit evidence."""
    package_path = Path(analysis_output_file).with_name(
        f"{Path(analysis_output_file).stem}_audit_package.zip"
    )
    package_path.parent.mkdir(parents=True, exist_ok=True)

    added: set[str] = set()
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for report_path in report_paths:
            _add_existing_file(zf, report_path, added=added)
        _add_existing_file(zf, csv_output, added=added)
        _add_existing_file(zf, audit_log_output, added=added)
        zf.writestr(
            "config_snapshot.json",
            json.dumps(config_snapshot, indent=2, sort_keys=True, default=_json_default),
        )
        zf.writestr(
            "validation_summary.json",
            json.dumps(build_validation_summary(metadata), indent=2, sort_keys=True, default=_json_default),
        )

    logger.info("Audit package written to %s", package_path)
    return str(package_path)
