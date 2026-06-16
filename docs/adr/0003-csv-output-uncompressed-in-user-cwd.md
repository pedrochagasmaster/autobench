# CSV outputs are uncompressed and land in the user's launch-time CWD

`Csv` and `Table + Csv` **Jobs** write their CSV directly to the directory
the user was in when they ran the `dispatch` command, uncompressed. The
absolute path is recorded in the **Job** manifest's `destination` block. The
`~/.dispatch/` tree never holds CSVs.

To preserve this invariant without modifying the orchestrators in `scr/`, the
runner script **decomposes** a `Table + Csv` Job into two sequential
orchestrator calls instead of using `Query_Impala_Parametrized.py --download`:

1. `Query_Impala_Parametrized.py` (without `--download`) creates the parquet
   table.
2. `download_to_csv.py --table-name <fully.qualified> --output-file <pwd>/<name>.csv`
   exports the table to CSV in the user's CWD.

If step 2 fails, the table from step 1 still exists; the manifest reports
`Failed` and the user can rerun the export step manually or via a future
"resume" feature.

## Considered alternatives

- **Use `Query_Impala_Parametrized.py --download` and `gunzip` the result.**
  Rejected: same gzip cost paid twice (write, then read+rewrite), and the
  `--download` path also forces the CSV under `--session-folder`, requiring
  an additional `mv` to land it in the user's CWD. Decomposing is cleaner.
- **Keep the gzip behaviour for compatibility with the legacy GUI.**
  Rejected: the legacy GUI gzipped because results travelled over `scp` to a
  Windows machine; in the server-only world the file stays on the volume the
  user is already standing on, and downstream tooling (`pandas.read_csv`,
  Excel via samba mount, `awk`) wants plain CSV.

## Consequences

- The `--download` flag of `Query_Impala_Parametrized.py` is effectively
  unused by the new TUI. It is left intact in `scr/` because the legacy GUI
  uses it; once the legacy GUI is hard-deleted at v1.0 (per the migration
  plan), the flag becomes dead code and is a candidate for removal under the
  loosened `scr/` modification policy (ADR-0005).
- `download_to_csv.py` does not gzip on its own (verified in source) — the
  legacy gzip step lived in `Query_Impala_Parametrized.py.export_table_to_csv`.
  The runner therefore needs no extra unzip/cleanup logic.
- A `Csv` Job with a CWD the user lacks write permission on will fail at the
  `download_to_csv.py` step with a filesystem error; the manifest captures
  the failure normally.
