from pathlib import Path

import pandas as pd

from core.contracts import (
    AnalysisPlan,
    AnalysisResult,
    AnalysisRunRequest,
    DataQualityResult,
    OutputSettings,
    WeightingResult,
)
from core.report_artifact_builder import build_analysis_artifacts
from utils.config_manager import ConfigManager


def test_build_analysis_artifacts_assembles_report_model_frames(tmp_path: Path) -> None:
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
    analysis_result = AnalysisResult(
        plan=plan,
        weighting=WeightingResult(privacy_rule_name="5/25"),
        privacy_validation=None,
        data_quality=DataQualityResult(checked=True),
        results={"card_type": pd.DataFrame({"Category": ["A"]})},
        compliance_summary={"compliance_verdict": "fully_compliant"},
    )
    weights_df = pd.DataFrame({"Peer": ["P1"]})
    privacy_validation_df = pd.DataFrame({"Dimension": ["card_type"]})
    diagnostics = {
        "weights_df": weights_df,
        "method_breakdown_df": pd.DataFrame({"Method": ["Global-LP"]}),
        "privacy_validation_df": privacy_validation_df,
    }
    output = tmp_path / "analysis.xlsx"

    artifacts = build_analysis_artifacts(
        analysis_result=analysis_result,
        metadata={"entity": "Target"},
        diagnostics=diagnostics,
        secondary_results_df=pd.DataFrame({"Metric": ["secondary"]}),
        preset_comparison_df=None,
        impact_df=pd.DataFrame({"Impact_PP": [0.1]}),
        impact_summary_df=pd.DataFrame({"Mean_Abs_Impact_PP": [0.1]}),
        validation_issues=[],
        analysis_output_file=str(output),
        analyzer=object(),
        compliance_summary=analysis_result.compliance_summary,
    )

    assert artifacts.analysis_output_file == str(output)
    assert artifacts.publication_output == str(tmp_path / "analysis_publication.xlsx")
    assert artifacts.weights_df.equals(weights_df)
    assert artifacts.report_model is not None
    assert artifacts.report_model.weights_df.equals(weights_df)
    assert artifacts.report_model.privacy_validation_df.equals(privacy_validation_df)
    assert artifacts.report_model.impact_summary_df.equals(artifacts.impact_summary_df)
