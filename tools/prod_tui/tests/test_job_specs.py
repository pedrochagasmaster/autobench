from __future__ import annotations

from pathlib import Path

import pytest

from dispatch import manifest, sql
from tools.prod_tui import job_specs


def test_matrix_matches_dispatch_legal_cells() -> None:
    """The harness matrix must exactly mirror the app's legal cells."""
    spec_cells = {spec.cell for spec in job_specs.all_specs()}
    assert spec_cells == set(manifest.LEGAL_CELLS)


def test_level4_is_every_legal_cell_except_l3() -> None:
    l4 = {spec.cell for spec in job_specs.level4_specs()}
    assert job_specs.level3_spec().cell not in l4
    assert l4 == set(manifest.LEGAL_CELLS) - {job_specs.level3_spec().cell}
    assert len(job_specs.level4_specs()) == 4


@pytest.mark.parametrize("spec", job_specs.all_specs(), ids=lambda s: s.name)
def test_expected_scripts_match_orchestrator_calls(spec, tmp_path, monkeypatch) -> None:
    """expected_scripts(spec) must equal the scripts the manifest would record."""
    # Force script_argv down its python-interpreter branch (no executable bit).
    monkeypatch.setenv("DISPATCH_SCR_DIR", str(tmp_path / "nonexistent_scr"))
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    schema, table = "aa_enc", "dispatch_smoke_x"
    if spec.source_type == "ExistingTable":
        source = {"type": "ExistingTable", "table_name": f"{schema}.{table}"}
    else:
        source = {"type": spec.source_type, "sql_path_at_launch": "/tmp/x.sql"}
    destination = {"type": spec.dest_type, "schema": schema, "table_name": table, "csv_path": ""}
    params = {"to_email": "", "subject": "s"}
    if spec.is_template:
        params["start_date"] = "01/01/2026"
        params["end_date"] = "01/31/2026"

    calls = manifest.build_orchestrator_calls(
        job_dir, source, destination, params, Path("/tmp"), "tester"
    )
    assert [call["script"] for call in calls] == job_specs.expected_scripts(spec)


def test_template_body_is_a_complete_template() -> None:
    body = job_specs._SQLTEMPLATE_TABLE.sql_body()
    assert sql.template_is_complete(body)
    assert not sql.is_malformed_template(body)
    assert sql.detect_source(body) == "SqlTemplate"


def test_non_template_body_is_the_smoke_select() -> None:
    assert job_specs._SQLFILE_CSV.sql_body() == job_specs.SMOKE_SELECT
    assert sql.detect_source(job_specs._SQLFILE_CSV.sql_body()) == "SqlFile"


def test_prefill_csv_omits_template_dates() -> None:
    pf = job_specs.prefill_for(
        job_specs._SQLFILE_CSV, sql_path="/tmp/x.sql", schema="aa_enc", table_name="dispatch_smoke_x"
    )
    assert pf["source_type"] == "SqlFile"
    assert pf["dest_type"] == "Csv"
    assert "start_date" not in pf and "end_date" not in pf
    assert pf["sql_file"] == "/tmp/x.sql"
    # Csv still needs the table name to derive <table>.csv.
    assert pf["table_name"] == "dispatch_smoke_x"


def test_prefill_template_carries_dates() -> None:
    pf = job_specs.prefill_for(
        job_specs._SQLTEMPLATE_TABLE, sql_path="/tmp/x.sql", schema="aa_enc",
        table_name="dispatch_smoke_x", start_date="01/01/2026", end_date="01/31/2026",
    )
    assert pf["start_date"] == "01/01/2026"
    assert pf["end_date"] == "01/31/2026"
    assert pf["source_type"] == "SqlTemplate"


def test_prefill_existing_table_uses_existing_key_not_sqlfile() -> None:
    pf = job_specs.prefill_for(
        job_specs._EXISTINGTABLE_CSV, sql_path="/tmp/x.sql", schema="aa_enc",
        table_name="dispatch_smoke_x", existing_table="aa_enc.dispatch_smoke_seed",
    )
    assert pf["existing_table"] == "aa_enc.dispatch_smoke_seed"
    assert "sql_file" not in pf
