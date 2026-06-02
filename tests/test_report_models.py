import pytest

from core.contracts import AnalysisPlan, AnalysisResult, AnalysisRunRequest, OutputSettings, WeightingResult
from core.report_models import ReportModel
from utils.config_manager import ConfigManager


def test_report_model_requires_compliance_summary() -> None:
    request = AnalysisRunRequest(mode="share", metric="txn_cnt", dimensions=["card_type"])
    plan = AnalysisPlan(
        request=request,
        resolved_config=ConfigManager().resolve(),
        entity="Target",
        entity_column="issuer_name",
        dimensions=["card_type"],
        metric_columns={"metric": "txn_cnt"},
        output_settings=OutputSettings(),
    )
    result = AnalysisResult(
        plan=plan,
        weighting=WeightingResult(),
        privacy_validation=None,
        data_quality=None,
        results={},
        compliance_summary={},
    )

    with pytest.raises(ValueError, match="compliance_summary"):
        ReportModel.from_analysis_result(result)
