"""Run the actual corrected reset plus migrations only on a disposable database."""

from __future__ import annotations

import os
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from tools import m084_mutation_campaign as tool

from empirical_platform.shared.config.settings import resolve_foundation_config
from empirical_platform.shared.persistence.database_safety import (
    IDENTITY_QUERY,
    TEST_IDENTITY,
    DatabaseSafetyError,
    require_test_target,
)
from empirical_platform.shared.persistence.postgres_repositories import (
    paper_execution_repositories as paper_schema,
)


@pytest.mark.integration
def test_actual_tool_preserves_personal_markers_and_resets_explicit_test(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.environ.get("EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS") != "1":
        pytest.skip("explicit isolated PostgreSQL opt-in required")
    cfg = resolve_foundation_config().postgresql
    require_test_target(cfg.database, cfg.port)
    name = f"safety_reset_{uuid4().hex[:12]}_test"
    parameters = dict(
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password.get_secret_value(),
        autocommit=True,
    )
    statements: list[str] = []

    def record_sql(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    monkeypatch.setattr(tool, "_purge_bytecode", lambda: None)
    with psycopg.connect(dbname=cfg.database, **parameters) as admin:
        assert admin.execute(IDENTITY_QUERY).fetchone()[1] == TEST_IDENTITY
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            with psycopg.connect(dbname=name, **parameters) as check:
                check.execute("CREATE TABLE durable_canary(id integer)")
                check.execute("INSERT INTO durable_canary VALUES (7)")
                event.listen(Engine, "before_cursor_execute", record_sql)
                try:
                    for marker in (
                        None,
                        "",
                        "TEST",
                        "PERSONAL_PAPER:B:fixture",
                        "PERSONAL_PAPER:C:fixture",
                    ):
                        check.execute(
                            sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                                sql.Identifier(name), sql.Literal(marker)
                            )
                        )
                        statements.clear()
                        with pytest.raises(DatabaseSafetyError):
                            tool._rebuild_schema(name)
                        assert statements and all(s == IDENTITY_QUERY for s in statements)
                        assert check.execute("SELECT id FROM durable_canary").fetchone() == (7,)
                    # libpq/SQLAlchemy query-parameter override: actual dbname must be checked.
                    for host in ("localhost", "127.0.0.1"):
                        url = cfg.model_copy(update={"database": "innocent_test", "host": host})
                        engine = create_engine(
                            url.sqlalchemy_url().update_query_dict({"dbname": name})
                        )
                        try:
                            statements.clear()
                            with pytest.raises(DatabaseSafetyError):
                                with engine.begin() as conn:
                                    conn.exec_driver_sql("TRUNCATE durable_canary")
                            assert all(s == IDENTITY_QUERY for s in statements)
                        finally:
                            engine.dispose()
                    check.execute(
                        sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                            sql.Identifier(name), sql.Literal(TEST_IDENTITY)
                        )
                    )
                    statements.clear()
                    tool._rebuild_schema(name)
                    assert "DROP SCHEMA public CASCADE" in statements
                    assert not any("DROP DATABASE" in s for s in statements)
                    assert check.execute(
                        "SELECT to_regclass('public.durable_canary')"
                    ).fetchone() == (None,)
                    assert check.execute("SELECT version_num FROM alembic_version").fetchone() == (
                        paper_schema.V1_INTEGRATED_SCHEMA_HEAD,
                    )
                    assert check.execute(IDENTITY_QUERY).fetchone()[1] == TEST_IDENTITY
                finally:
                    event.remove(Engine, "before_cursor_execute", record_sql)
        finally:
            require_test_target(name, cfg.port)
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
