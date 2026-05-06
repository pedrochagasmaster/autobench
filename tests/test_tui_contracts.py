from types import SimpleNamespace

import pandas as pd

from core.analysis_run import build_run_config
from core.contracts import AnalysisRunRequest


def test_analysis_run_request_preserves_preloaded_dataframe() -> None:
    df = pd.DataFrame({"issuer_name": ["Target", "P1"], "metric": [1, 2]})
    request = AnalysisRunRequest(mode="share", csv="", metric="metric")
    request.df = df

    namespace = request.to_namespace()

    assert namespace.df is df


def test_analysis_run_request_from_namespace_copies_dataframe() -> None:
    df = pd.DataFrame({"issuer_name": ["Target"], "metric": [1]})
    namespace = SimpleNamespace(mode="share", csv="", df=df, metric="metric", ignored_flag=True)

    request = AnalysisRunRequest.from_namespace("share", namespace)

    assert request.df is df
    assert not hasattr(request, "ignored_flag")


def test_build_run_config_accepts_request_namespace_after_dataframe_fix() -> None:
    request = AnalysisRunRequest(mode="share", csv="", df=object(), metric="metric", validate_input=False)

    config = build_run_config(request.to_namespace())

    assert config.get("input", "validate_input") is False
