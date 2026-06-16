"""Safety policy for production Dispatch TUI automation."""

from __future__ import annotations

import re
from enum import Enum


class ActionTier(Enum):
    SAFE = "safe"
    CONTROLLED = "controlled"
    BLOCKED = "blocked"


SAFE_ACTIONS: set[str] = {
    "navigate",
    "preview",
    "capture",
    "inspect_logs",
    "inspect_history",
    "run_help",
    "compileall",
    "quit",
    "kinit",
    "klist",
    "show_tables",
    "describe_table",
}

CONTROLLED_ACTIONS: set[str] = {
    "launch_smoke_query",
}

BLOCKED_ACTIONS: set[str] = {
    "drop_table",
    "run_arbitrary_sql",
    "modify_scr",
    "delete_files",
    "launch_unknown_sql",
}

_DDL_DML_RE = re.compile(
    r"\b(drop|create|alter|insert|delete|update|truncate)\b",
    flags=re.IGNORECASE,
)
_SMOKE_SELECT_RE = re.compile(
    r"^\s*select\s+.+\s+as\s+smoke_test_value\s*;?\s*$",
    flags=re.IGNORECASE | re.DOTALL,
)
_COMMENT_RE = re.compile(r"(--[^\n]*(?:\n|$))|(/\*.*?\*/)", flags=re.DOTALL)


def classify(action: str) -> ActionTier:
    normalized = action.strip().lower()
    if normalized in SAFE_ACTIONS:
        return ActionTier.SAFE
    if normalized in CONTROLLED_ACTIONS:
        return ActionTier.CONTROLLED
    return ActionTier.BLOCKED


def is_safe_table_name(name: str, table_prefix: str = "dispatch_smoke") -> bool:
    normalized = name.strip()
    prefix = table_prefix.strip().rstrip("_") + "_"
    if not normalized.startswith(prefix):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_]+", normalized))


def _normalize_sql(sql_text: str) -> str:
    return " ".join(sql_text.strip().rstrip(";").split()).lower()


def is_safe_sql(sql_text: str, smoke_query_sql: str = "SELECT 1 AS smoke_test_value") -> bool:
    if not sql_text or _COMMENT_RE.search(sql_text):
        return False
    if _DDL_DML_RE.search(sql_text):
        return False
    if _normalize_sql(sql_text) == _normalize_sql(smoke_query_sql):
        return True
    return bool(_SMOKE_SELECT_RE.fullmatch(sql_text))


def check_launch_preconditions(
    kerberos_ttl: int | None,
    running_jobs: int,
    table_name: str,
    sql_text: str,
    *,
    table_prefix: str = "dispatch_smoke",
    smoke_query_sql: str = "SELECT 1 AS smoke_test_value",
) -> list[str]:
    violations: list[str] = []
    if kerberos_ttl is None:
        violations.append("Kerberos ticket is missing")
    elif kerberos_ttl < 300:
        violations.append("Kerberos ticket has less than five minutes remaining")

    if running_jobs >= 2:
        violations.append("Two or more Dispatch jobs are already running")

    if not is_safe_table_name(table_name, table_prefix=table_prefix):
        violations.append(f"Table name must start with {table_prefix.rstrip('_')}_ and contain only letters, numbers, and underscores")

    if not is_safe_sql(sql_text, smoke_query_sql=smoke_query_sql):
        violations.append("SQL is not an approved smoke-test SELECT")

    return violations
