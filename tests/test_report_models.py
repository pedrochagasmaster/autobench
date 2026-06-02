import pytest
import pandas as pd

from core.contracts import (
    AnalysisPlan,
    AnalysisResult,
    AnalysisRunRequest,
    OutputSettings,
    RunSummary,
    WeightingResult,
)
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


def test_report_model_to_metadata_renders_optional_frames() -> None:
    model = ReportModel(
        summary=RunSummary(
            entity="Target",
            entity_column="issuer_name",
            dimensions_analyzed=1,
            dimension_names=["card_type"],
        ),
        compliance_summary={"compliance_verdict": "fully_compliant"},
        results={"card_type": pd.DataFrame({"Category": ["A"]})},
        weights_df=pd.DataFrame({"Peer": ["P1"]}),
        method_breakdown_df=pd.DataFrame({"Dimension": ["card_type"]}),
        secondary_results_df=pd.DataFrame({"Dimension": ["card_type"]}),
        validation_issues=[],
    )

    metadata = model.to_metadata({"custom": "value"})

    assert metadata["custom"] == "value"
    assert metadata["entity"] == "Target"
    assert metadata["compliance_summary"] == {"compliance_verdict": "fully_compliant"}
    assert metadata["weights_df"].equals(model.weights_df)
    assert metadata["method_breakdown_df"].equals(model.method_breakdown_df)
    assert metadata["secondary_results"].equals(model.secondary_results_df)
    assert metadata["validation_issues"] == []
