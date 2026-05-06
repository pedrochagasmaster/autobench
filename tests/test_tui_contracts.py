"""Tests for TUI/CLI orchestration contracts — preloaded DataFrame preservation."""

from types import SimpleNamespace

import pandas as pd

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


def test_analysis_run_request_namespace_round_trip() -> None:
    df = pd.DataFrame({"issuer_name": ["Target"], "metric": [1]})
    request = AnalysisRunRequest(mode="share", csv="test.csv", metric="metric")
    request.df = df

    namespace = request.to_namespace()
    restored = AnalysisRunRequest.from_namespace("share", namespace)

    assert restored.df is df
    assert restored.csv == "test.csv"
