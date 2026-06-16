from __future__ import annotations

from tools.prod_tui import safety


def test_classify_known_safe_and_blocked_actions() -> None:
    assert safety.classify("navigate") is safety.ActionTier.SAFE
    assert safety.classify("drop_table") is safety.ActionTier.BLOCKED
    assert safety.classify("unknown_thing") is safety.ActionTier.BLOCKED


def test_classify_controlled_action() -> None:
    assert safety.classify("launch_smoke_query") is safety.ActionTier.CONTROLLED


def test_safe_table_name_requires_prefix_and_identifier_chars() -> None:
    assert safety.is_safe_table_name("dispatch_smoke_user_20260519_023000")
    assert not safety.is_safe_table_name("")
    assert not safety.is_safe_table_name("prod_table")
    assert not safety.is_safe_table_name("dispatch_smoke_user;drop")


def test_safe_sql_accepts_exact_configured_smoke_query() -> None:
    assert safety.is_safe_sql("SELECT 1 AS smoke_test_value")
    assert safety.is_safe_sql("select cast(1 as int) as smoke_test_value;")


def test_safe_sql_rejects_ddl_dml_and_comments() -> None:
    assert not safety.is_safe_sql("DROP TABLE x")
    assert not safety.is_safe_sql("SELECT 1 AS smoke_test_value; -- DROP TABLE x")
    assert not safety.is_safe_sql("/* CREATE TABLE x */ SELECT 1 AS smoke_test_value")
    assert not safety.is_safe_sql("INSERT INTO x SELECT 1 AS smoke_test_value")


def test_preconditions_reject_missing_and_low_kerberos() -> None:
    missing = safety.check_launch_preconditions(None, 0, "dispatch_smoke_user", "SELECT 1 AS smoke_test_value")
    low = safety.check_launch_preconditions(299, 0, "dispatch_smoke_user", "SELECT 1 AS smoke_test_value")
    assert any("missing" in message.lower() for message in missing)
    assert any("less than five" in message.lower() for message in low)


def test_preconditions_reject_job_cap_table_and_sql() -> None:
    violations = safety.check_launch_preconditions(300, 2, "unsafe", "DROP TABLE x")
    assert any("running" in message.lower() for message in violations)
    assert any("table name" in message.lower() for message in violations)
    assert any("sql" in message.lower() for message in violations)


def test_preconditions_happy_path() -> None:
    assert safety.check_launch_preconditions(
        300,
        1,
        "dispatch_smoke_user_20260519_023000",
        "SELECT 1 AS smoke_test_value",
    ) == []
