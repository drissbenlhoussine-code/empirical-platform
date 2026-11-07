"""Fail-closed identities for personal Paper stores and disposable test databases.

The database comment survives DROP SCHEMA. The independent local manifest survives
database loss. Neither marker is automatically inferred from an empty database.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Connection, Dialect, Engine
from sqlalchemy.pool import ConnectionPoolEntry

from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService

PERSONAL_DATABASES = frozenset({"empirical_platform_paper", "empirical_platform_paper_exit"})
TEST_IDENTITY = "EMPIRICAL:TEST"
IDENTITY_QUERY = (
    "SELECT current_database() AS database, "
    "shobj_description(oid, 'pg_database') AS identity "
    ", inet_server_port() AS server_port "
    "FROM pg_database WHERE datname = current_database()"
)


class DatabaseSafetyError(ValueError):
    """No database mutation or runtime startup is permitted after this refusal."""


def manifest_path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / (
        "EmpiricalPlatform/safety/personal-paper.json"
    )


def read_manifest(path: Path | None = None) -> dict[str, Any]:
    try:
        value = json.loads((path or manifest_path()).read_text(encoding="utf-8"))
        if value["kind"] != "PERSONAL_PAPER" or value["version"] != 1:
            raise ValueError("identity format")
        if set(value["stores"]) != {"B", "C"}:
            raise ValueError("store pair")
        if value["state"] not in {"LOSS_DETECTED", "INITIALIZED"}:
            raise ValueError("initialization state")
        if not isinstance(value["host"], str) or not isinstance(value["port"], int):
            raise ValueError("endpoint")
        for store, entry in value["stores"].items():
            if not all(
                isinstance(entry[key], str) and entry[key]
                for key in ("database", "head", "identity")
            ):
                raise ValueError("store identity")
            if not entry["identity"].startswith(f"PERSONAL_PAPER:{store}:"):
                raise ValueError("store identity namespace")
            if not isinstance(entry["minimum_attempts"], int) or entry["minimum_attempts"] < 0:
                raise ValueError("history baseline")
        return dict(value)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise DatabaseSafetyError("PERSONAL_PAPER identity manifest missing or invalid") from error


def protected_database(database: str) -> bool:
    if database in PERSONAL_DATABASES:
        return True
    path = manifest_path()
    if path.exists():
        manifest = read_manifest(path)
        return any(s["database"] == database for s in manifest["stores"].values())
    return False


def require_test_target(database: str, port: int | None) -> None:
    if port is None or not 1 <= port <= 65535:
        raise DatabaseSafetyError("an explicit PostgreSQL test port is required")
    if protected_database(database):
        raise DatabaseSafetyError("PERSONAL_PAPER database cannot be used by test tooling")
    if port == 55433:
        raise DatabaseSafetyError("personal cluster port 55433 cannot be used by test tooling")
    if os.environ.get("EMPIRICAL_PLATFORM_DATABASE_MODE") != "TEST":
        raise DatabaseSafetyError("explicit EMPIRICAL_PLATFORM_DATABASE_MODE=TEST is required")
    if len(database) > 63 or re.fullmatch(r"[a-z][a-z0-9_]*_test", database) is None:
        raise DatabaseSafetyError(
            "an explicit disposable database name ending in _test is required"
        )


def require_test_connection(connection: Connection) -> None:
    require_test_target(connection.engine.url.database or "", connection.engine.url.port)
    row = connection.exec_driver_sql(IDENTITY_QUERY).mappings().one()
    actual_database = row.get("database")
    actual_port = row.get("server_port")
    if not isinstance(actual_database, str) or not isinstance(actual_port, int):
        raise DatabaseSafetyError("actual database endpoint is missing or ambiguous")
    require_test_target(actual_database, actual_port)
    if actual_database != connection.engine.url.database:
        raise DatabaseSafetyError("actual database differs from the explicit test target")
    if row["identity"] != TEST_IDENTITY:
        raise DatabaseSafetyError("database is not independently marked EMPIRICAL:TEST")


def _before_test_connect(
    dialect: Dialect, record: ConnectionPoolEntry, args: list[object], params: dict[str, Any]
) -> None:
    # Engine's do_connect runs before any network connection or destructive fixture.
    del record, args
    if dialect.name != "postgresql":
        return
    require_test_target(str(params.get("dbname", "")), int(params.get("port", 0)))


def _test_connection(connection: Connection) -> None:
    if connection.dialect.name == "postgresql":
        try:
            require_test_connection(connection)
        except Exception:
            # engine_connect rejection happens before the caller's context manager
            # owns the Connection. Close it here rather than leak a checked-out session.
            connection.close()
            raise
        connection.rollback()  # the identity read must not occupy the fixture transaction


def install_test_connection_guard() -> None:
    """Protect direct engines, fixture teardown, and in-process Alembic alike."""
    if not event.contains(Engine, "engine_connect", _test_connection):
        event.listen(Engine, "engine_connect", _test_connection)
        event.listen(Engine, "do_connect", _before_test_connect)


def require_personal_identity(
    service: PostgresPersistenceService, config: PostgreSQLConfigSnapshot, *, store: str
) -> None:
    """Called before composing a personal Paper runtime; never creates missing state."""
    if os.environ.get("EMPIRICAL_PLATFORM_DATABASE_MODE") == "TEST":
        require_test_target(config.database, config.port)
        with service.unit_of_work() as work:
            rows = work.execute(IDENTITY_QUERY)
            if len(rows) != 1 or rows[0]["identity"] != TEST_IDENTITY:
                raise DatabaseSafetyError("test runtime requires EMPIRICAL:TEST identity")
        return
    manifest = read_manifest()
    expected = manifest["stores"][store]
    if (
        config.host != manifest["host"]
        or config.port != manifest["port"]
        or config.database != expected["database"]
        or manifest["state"] != "INITIALIZED"
    ):
        raise DatabaseSafetyError("PERSONAL_PAPER_LOSS_DETECTED: identity/initialization mismatch")
    try:
        with service.unit_of_work() as work:
            rows = work.execute(IDENTITY_QUERY)
            if len(rows) != 1 or rows[0]["identity"] != expected["identity"]:
                raise DatabaseSafetyError("PERSONAL_PAPER_LOSS_DETECTED: database identity missing")
            heads = work.execute("SELECT version_num FROM public.alembic_version")
            if [r["version_num"] for r in heads] != [expected["head"]]:
                raise DatabaseSafetyError("PERSONAL_PAPER_LOSS_DETECTED: schema revision changed")
            query = (
                "SELECT count(*) AS count FROM public.paper_execution_attempt"
                if store == "B"
                else "SELECT count(*) AS count FROM public.position_exit_attempt"
            )
            count = work.execute(query)[0]["count"]
            if not isinstance(count, int) or count < expected["minimum_attempts"]:
                raise DatabaseSafetyError("PERSONAL_PAPER_LOSS_DETECTED: execution history shrank")
    except DatabaseSafetyError:
        raise
    except Exception as error:
        raise DatabaseSafetyError(
            "PERSONAL_PAPER_LOSS_DETECTED: required state unreadable"
        ) from error


def refuse_unplanned_personal_migration(config: PostgreSQLConfigSnapshot) -> None:
    if protected_database(config.database):
        raise DatabaseSafetyError(
            "PERSONAL_PAPER migration refused; use the reviewed offline initialization/restore plan"
        )
    if os.environ.get("EMPIRICAL_PLATFORM_DATABASE_MODE") == "TEST":
        require_test_target(config.database, config.port)


def require_migration_connection(connection: Connection) -> None:
    """Renaming a personally identified database cannot bypass migration protection."""
    row = connection.exec_driver_sql(IDENTITY_QUERY).mappings().one()
    identity = row["identity"]
    if isinstance(identity, str) and identity.startswith("PERSONAL_PAPER:"):
        raise DatabaseSafetyError("PERSONAL_PAPER online migration refused by database identity")
    if os.environ.get("EMPIRICAL_PLATFORM_DATABASE_MODE") == "TEST":
        require_test_connection(connection)
    connection.rollback()
