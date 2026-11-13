"""Adversarial refusal before destructive SQL or subprocess launch."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import sqlalchemy
from tools import m084_mutation_campaign as tool

from empirical_platform.shared.persistence import database_safety as safety


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMPIRICAL_PLATFORM_DATABASE_MODE", "TEST")
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_HOST", "localhost")
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_PORT", "55436")
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_USER", "empirical")
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_PASSWORD", "test-placeholder")


@pytest.mark.parametrize(
    "database",
    [
        "empirical_platform_paper",
        "empirical_platform_paper_exit",
        '"empirical_platform_paper"',
        "EMPIRICAL_PLATFORM_PAPER",
        "postgresql://localhost:55433/empirical_platform_paper?application_name=x_test",
        "dbname=empirical_platform_paper application_name=x_test",
        "empirical_platform_paper%00_test",
        "empirical_platform_paper/alias_test",
        "alias_test; DROP DATABASE empirical_platform_paper;--_test",
        "x" * 64 + "_test",
        "",
        "ambiguous",
    ],
)
def test_personal_and_connection_string_targets_refused_before_connect(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = MagicMock(side_effect=AssertionError("connection must not be attempted"))
    launch = MagicMock(side_effect=AssertionError("subprocess must not be launched"))
    monkeypatch.setattr(sqlalchemy, "create_engine", engine)
    monkeypatch.setattr(tool.subprocess, "run", launch)
    with pytest.raises(safety.DatabaseSafetyError):
        tool._rebuild_schema(database)
    engine.assert_not_called()
    launch.assert_not_called()


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1", "alias.invalid"])
def test_personal_port_cannot_be_bypassed_by_host_alias(
    host: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_HOST", host)
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_PORT", "55433")
    engine = MagicMock()
    monkeypatch.setattr(sqlalchemy, "create_engine", engine)
    with pytest.raises(safety.DatabaseSafetyError):
        tool._rebuild_schema("alias_test")
    engine.assert_not_called()


@pytest.mark.parametrize(
    "actual,port,marker",
    [
        ("empirical_platform_paper", 55436, safety.TEST_IDENTITY),
        ("empirical_platform_paper_exit", 55436, safety.TEST_IDENTITY),
        ("alias_test", 55433, safety.TEST_IDENTITY),
        ("alias_test", 55436, "PERSONAL_PAPER:B:identity"),
        ("alias_test", 55436, "PERSONAL_PAPER:C:identity"),
        ("alias_test", 55436, None),
        ("alias_test", 55436, ""),
        ("alias_test", 55436, "TEST"),
        ("alias_test", 55436, "EMPIRICAL:TEST "),
        (None, 55436, safety.TEST_IDENTITY),
        ("alias_test", None, safety.TEST_IDENTITY),
        ("different_test", 55436, safety.TEST_IDENTITY),
    ],
)
def test_resolved_identity_refused_before_any_destructive_statement(
    actual: str | None, port: int | None, marker: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value
    connection.engine.url.database = "alias_test"
    connection.engine.url.port = 55436
    connection.exec_driver_sql.return_value.mappings.return_value.one.return_value = {
        "database": actual,
        "server_port": port,
        "identity": marker,
    }
    monkeypatch.setattr(sqlalchemy, "create_engine", lambda *a, **k: engine)
    monkeypatch.setattr(safety, "install_test_connection_guard", lambda: None)
    launch = MagicMock(side_effect=AssertionError("refusal must precede migration"))
    monkeypatch.setattr(tool.subprocess, "run", launch)
    with pytest.raises(safety.DatabaseSafetyError):
        tool._rebuild_schema("alias_test")
    connection.execute.assert_not_called()
    assert all(
        call.args[0] == safety.IDENTITY_QUERY for call in connection.exec_driver_sql.call_args_list
    )
    launch.assert_not_called()
    engine.dispose.assert_called_once()
