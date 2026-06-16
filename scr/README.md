# Orchestrator scripts

These scripts are Dispatch's stable Orchestrator script API. They are reused by
the TUI runner as black boxes and are modified only under ADR-0005.

`_common.py` holds the shared helpers allowed by ADR-0005: email sending,
Impala error classification, and Resource Pool cycling.
