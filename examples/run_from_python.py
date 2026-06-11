"""Minimal programmatic usage of the benchmark engine.

The public API surface is:
    core.contracts.AnalysisRunRequest   (input contract)
    core.analysis_run.execute_share_run (share analysis)
    core.analysis_run.execute_rate_run  (rate analysis)
    -> both return core.contracts.AnalysisArtifacts

Generated .xlsx files are gitignored; safe to write to the repo root for ad-hoc runs.

Run from the repository root: ``py examples/run_from_python.py``
"""
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.analysis_run import execute_share_run
from core.contracts import AnalysisRunRequest

logging.basicConfig(level=logging.INFO)

request = AnalysisRunRequest(
    csv="tests/fixtures/gate_demo.csv",
    entity="Target",
    metric="txn_cnt",
    dimensions=["card_type", "channel"],
    time_col="year_month",
    preset="balanced_default",
    compliance_posture="strict",
    output="example_share.xlsx",
)
artifacts = execute_share_run(request, logging.getLogger("example"))
print("Report:", artifacts.analysis_output_file)
