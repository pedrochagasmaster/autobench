"""Declarative job specifications for the controlled production levels.

Level 3 exercises exactly one cell of the Source x Destination matrix
(``SqlFile -> Table``). Levels 4+ widen coverage to the remaining *legal* cells
and to template / existing-table sources. Keeping each cell as a small,
pure-data :class:`JobSpec` lets the controlled-run harness loop over them and
lets us unit-test the matrix, prefill, and expected-orchestrator mapping without
touching the network.

The matrix here mirrors ``dispatch.manifest.LEGAL_CELLS`` /
``build_orchestrator_calls``; ``tests/test_job_specs.py`` asserts it stays in
sync so the two never drift.
"""

from __future__ import annotations

from dataclasses import dataclass

# How a finished job is verified on the edge node.
VERIFY_TABLE = "table"
VERIFY_CSV = "csv"
VERIFY_TABLE_AND_CSV = "table_and_csv"

# The approved smoke SELECT (matches ProdTuiConfig.smoke_query_sql).
SMOKE_SELECT = "SELECT 1 AS smoke_test_value"
# A template smoke body: it must contain BOTH {date_inicio} and {date_fim}
# (dispatch.sql.template_is_complete) and remain a plain SELECT. The
# orchestrator substitutes the dates; the placeholders live in a trailing
# comment so the resulting query stays ``SELECT 1 AS smoke_test_value``.
SMOKE_TEMPLATE_SQL = "SELECT 1 AS smoke_test_value\n-- window {date_inicio} .. {date_fim}\n"

# (source_type, dest_type) -> ordered orchestrator scripts. Mirrors
# dispatch.manifest.build_orchestrator_calls.
_EXPECTED_SCRIPTS: dict[tuple[str, str], list[str]] = {
    ("SqlFile", "Table"): ["Query_Impala_Parametrized.py"],
    ("SqlFile", "Csv"): ["download_to_csv.py"],
    ("SqlFile", "Table+Csv"): ["Query_Impala_Parametrized.py", "download_to_csv.py"],
    ("SqlTemplate", "Table"): ["monthly_query_processor.py"],
    ("ExistingTable", "Csv"): ["download_to_csv.py"],
}


@dataclass(frozen=True)
class JobSpec:
    """One controlled job: a legal Source x Destination cell plus how to verify it."""

    name: str
    source_type: str  # SqlFile | SqlTemplate | ExistingTable
    dest_type: str  # Table | Csv | Table+Csv
    verify: str  # VERIFY_TABLE | VERIFY_CSV | VERIFY_TABLE_AND_CSV
    sql: str | None = None  # SQL file body; None -> SMOKE_SELECT
    is_template: bool = False
    # ExistingTable has no SQL of its own: it reads a table created by a prior
    # Table job in the same batch, so the harness must seed one first.
    needs_existing_table: bool = False

    @property
    def cell(self) -> tuple[str, str]:
        return (self.source_type, self.dest_type)

    @property
    def produces_table(self) -> bool:
        return self.dest_type in ("Table", "Table+Csv")

    @property
    def produces_csv(self) -> bool:
        return self.dest_type in ("Csv", "Table+Csv")

    def sql_body(self) -> str:
        if self.sql is not None:
            return self.sql
        return SMOKE_TEMPLATE_SQL if self.is_template else SMOKE_SELECT


# The full legal matrix. Order matters for L4: the ExistingTable->Csv cell reads
# a table, so a Table-producing cell must run before it within a batch.
_SQLFILE_TABLE = JobSpec("sqlfile_table", "SqlFile", "Table", VERIFY_TABLE)
_SQLFILE_CSV = JobSpec("sqlfile_csv", "SqlFile", "Csv", VERIFY_CSV)
_SQLFILE_TABLE_CSV = JobSpec("sqlfile_table_csv", "SqlFile", "Table+Csv", VERIFY_TABLE_AND_CSV)
_SQLTEMPLATE_TABLE = JobSpec(
    "sqltemplate_table", "SqlTemplate", "Table", VERIFY_TABLE, is_template=True
)
_EXISTINGTABLE_CSV = JobSpec(
    "existingtable_csv", "ExistingTable", "Csv", VERIFY_CSV, needs_existing_table=True
)


def all_specs() -> list[JobSpec]:
    """Every legal Source x Destination cell, including the L3 cell."""
    return [
        _SQLFILE_TABLE,
        _SQLFILE_CSV,
        _SQLFILE_TABLE_CSV,
        _SQLTEMPLATE_TABLE,
        _EXISTINGTABLE_CSV,
    ]


def level3_spec() -> JobSpec:
    """The single cell Level 3 covers (the happy-path baseline)."""
    return _SQLFILE_TABLE


def level4_specs() -> list[JobSpec]:
    """The breadth cells L4 adds on top of L3 (every legal cell except L3's)."""
    return [spec for spec in all_specs() if spec.cell != _SQLFILE_TABLE.cell]


def expected_scripts(spec: JobSpec) -> list[str]:
    """Orchestrator scripts the manifest should record for this cell, in order."""
    return list(_EXPECTED_SCRIPTS[spec.cell])


def ready_marker(spec: JobSpec) -> str:
    """Regex that confirms the prefilled New Job form finished rendering.

    The destination-dependent rows differ per cell (the New Job form hides
    Schema/Table for a pure Csv export, and shows Existing Table for an
    ExistingTable source), so the harness must wait for the row that proves the
    prefill's source/destination actually applied.
    """
    if spec.produces_table or spec.is_template:
        return r"Table Name"
    if spec.source_type == "ExistingTable":
        return r"Existing Table"
    return r"SQL File"


def expected_visible_fields(
    spec: JobSpec,
    *,
    sql_path: str,
    schema: str,
    table_name: str,
    existing_table: str = "",
    start_date: str = "",
    end_date: str = "",
) -> dict[str, str]:
    """Label -> value pairs that must be visible (and correct) on the form.

    Only rows the form actually shows for this cell are included, so a Csv
    export is not asked to prove a (hidden) Table Name row.

    The template Start/End Date rows are intentionally *not* required here: the
    template form is the tallest cell and those two rows fall below a single
    fixed SSH-pane height even with the matrix collapsed and the file picker
    hidden. The dates are instead verified end-to-end in the SQL preview (where
    ``{date_inicio}``/``{date_fim}`` are substituted), which is a stronger check
    than a form-field echo.
    """
    fields: dict[str, str] = {}
    if spec.source_type == "ExistingTable":
        fields["Existing Table"] = existing_table
    else:
        fields["SQL File"] = sql_path
    if spec.produces_table or spec.is_template:
        fields["Schema"] = schema
        fields["Table Name"] = table_name
    return fields


def prefill_for(
    spec: JobSpec,
    *,
    sql_path: str,
    schema: str,
    table_name: str,
    existing_table: str = "",
    email: str = "",
    subject: str = "",
    start_date: str = "",
    end_date: str = "",
) -> dict:
    """Build the DISPATCH_TEST_PREFILL payload for a spec.

    Only the keys the New Job form's ``_apply_prefill`` understands are emitted,
    and only the ones meaningful for the spec's source/destination, so a CSV job
    does not carry stale table fields and a template job carries its dates.
    """
    prefill: dict[str, str] = {
        "source_type": spec.source_type,
        "dest_type": spec.dest_type,
        "email": email,
        "subject": subject or f"Dispatch smoke {table_name}",
    }
    if spec.source_type == "ExistingTable":
        prefill["existing_table"] = existing_table
    else:
        prefill["sql_file"] = sql_path
    if spec.produces_table or spec.is_template:
        prefill["schema"] = schema
        prefill["table_name"] = table_name
    if spec.produces_csv and spec.source_type != "ExistingTable":
        # Csv/Table+Csv still need a table name to derive <table>.csv.
        prefill["schema"] = schema
        prefill["table_name"] = table_name
    if spec.is_template:
        prefill["start_date"] = start_date
        prefill["end_date"] = end_date
    return prefill
