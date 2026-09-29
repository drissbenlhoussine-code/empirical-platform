"""Shared fixtures for the MILESTONE-089 Store C integration suite.

Not a test module. Mirrors `_m085_support.py`'s `postgres_enabled`/`config`/`alembic_config`/
`build_engine` shape, but for Store C: a SEPARATE database, migrated through Store C's own
self-contained Alembic chain (`alembic_paper_exit.ini` / `migrations_paper_exit/`), never
through `migrations/`'s chain and never against Store A or Store B.

WHICH DATABASE. `store_c_config()` reads the SAME `EMPIRICAL_PLATFORM_POSTGRES_HOST/PORT/USER/
PASSWORD` env vars `_m085_support.config()` reads (one Postgres server, several databases), but
the database name comes from `EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE`
(default `empirical_platform_paper_exit`) -- mirroring exactly what
`entrypoints._paper_position_exit_composition.resolve_paper_exit_postgres_config` derives in
production, so a test failure here reflects the real composition path.

`build_engine_c` REFUSES to run against a database not named `empirical_platform_paper_exit`
(the default) or a name ending in `_paper_exit_test`/`_paper_exit` when explicitly overridden,
as a defense against a misconfigured environment pointing this suite's `DROP SCHEMA CASCADE` at
a real database. This is stricter than `_m085_support.build_engine`, which has no such guard,
because the M089 mission is explicit that no Paper database may be mutated by engineering.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Engine
from tests.integration._m085_support import postgres_enabled

from empirical_platform.entrypoints._paper_position_exit_composition import (
    PAPER_EXIT_DATABASE_VARIABLE,
)
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The six position_exit_* tables Store C's single migration creates. Identical names to
#: M087's Store-A copy (`test_m087_position_exit_postgres.py`'s `M087_TABLES`) -- same shape,
#: different database.
M089_TABLES = (
    "position_exit_event",
    "position_exit_reconciliation_round",
    "position_exit_acknowledgement",
    "position_exit_attempt",
    "position_exit_authorization",
    "position_exit_preview",
)

_DEFAULT_STORE_C_TEST_DATABASE = "empirical_platform_paper_exit"
_ALLOWED_STORE_C_TEST_SUFFIXES = ("_paper_exit", "_paper_exit_test")


def store_c_config(application_name: str = "empirical-platform-m089") -> PostgreSQLConfigSnapshot:
    database = os.environ.get(PAPER_EXIT_DATABASE_VARIABLE, _DEFAULT_STORE_C_TEST_DATABASE)
    if not database.endswith(_ALLOWED_STORE_C_TEST_SUFFIXES):
        raise AssertionError(
            f"refusing to run the M089 Store C integration suite against database {database!r}: "
            f"it does not end with {_ALLOWED_STORE_C_TEST_SUFFIXES!r}. Set "
            f"{PAPER_EXIT_DATABASE_VARIABLE} to a database name ending in one of those suffixes."
        )
    return PostgreSQLConfigSnapshot(
        host=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_PORT", "5432")),
        database=database,
        user=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_USER", "empirical"),
        password=SecretStr(os.environ["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"]),
        pool_size=8,
        max_overflow=8,
        connection_timeout_seconds=5,
        application_name=application_name,
    )


def store_c_alembic_config() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic_paper_exit.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations_paper_exit"))
    return cfg


def build_engine_c(revision: str = "head") -> Iterator[Engine]:
    """A Store C database at `revision`, rebuilt from `migrations_paper_exit`'s own chain.

    Requires `EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE` to already name the disposable
    test database (see `store_c_config`'s suffix guard): `migrations_paper_exit/env.py` reads
    that variable itself, independent of this `Config` object's own `sqlalchemy.url`.
    """
    if not postgres_enabled():
        pytest.skip("PostgreSQL integration tests require explicit opt-in")
    cfg = store_c_config()
    engine = sa.create_engine(cfg.sqlalchemy_url())
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    alembic_command.upgrade(store_c_alembic_config(), revision)
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
        engine.dispose()


def truncate_all_c(engine: Engine) -> None:
    with engine.begin() as connection:
        present = {
            row[0]
            for row in connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).all()
        }
        existing = [table for table in M089_TABLES if table in present]
        if existing:
            connection.execute(text("TRUNCATE " + ", ".join(existing)))
