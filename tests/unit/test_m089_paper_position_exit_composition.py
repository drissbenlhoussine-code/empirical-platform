"""MILESTONE-089 -- Store C's connectivity derivation. No real database is touched here.

`resolve_paper_exit_postgres_config` is a pure function: same host/port/user/password/pool
settings as Store B, a database name taken from `EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE`
or defaulting to `empirical_platform_paper_exit`. These tests prove the derivation itself,
never a connection.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from pydantic import SecretStr

from empirical_platform.entrypoints._paper_position_exit_composition import (
    PAPER_EXIT_DATABASE_VARIABLE,
    resolve_paper_exit_postgres_config,
)
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot

_STORE_B = PostgreSQLConfigSnapshot(
    host="db.internal",
    port=6543,
    database="empirical_platform_paper",
    user="paper_owner",
    password=SecretStr("s3cret"),
    pool_size=3,
    max_overflow=1,
    connection_timeout_seconds=9,
    application_name="m089-test",
)


@pytest.fixture(autouse=True)
def _clean_environment() -> Iterator[None]:
    previous = os.environ.pop(PAPER_EXIT_DATABASE_VARIABLE, None)
    try:
        yield
    finally:
        if previous is not None:
            os.environ[PAPER_EXIT_DATABASE_VARIABLE] = previous
        else:
            os.environ.pop(PAPER_EXIT_DATABASE_VARIABLE, None)


def test_store_c_defaults_to_its_own_database_name_with_store_bs_server_and_credentials() -> None:
    store_c = resolve_paper_exit_postgres_config(_STORE_B)
    assert store_c.database == "empirical_platform_paper_exit"
    assert store_c.host == _STORE_B.host
    assert store_c.port == _STORE_B.port
    assert store_c.user == _STORE_B.user
    assert store_c.password == _STORE_B.password
    assert store_c.pool_size == _STORE_B.pool_size
    assert store_c.max_overflow == _STORE_B.max_overflow
    assert store_c.connection_timeout_seconds == _STORE_B.connection_timeout_seconds


def test_store_c_never_reuses_store_bs_database_name() -> None:
    store_c = resolve_paper_exit_postgres_config(_STORE_B)
    assert store_c.database != _STORE_B.database


def test_the_override_variable_is_honored_and_is_never_the_store_b_database_variable() -> None:
    os.environ[PAPER_EXIT_DATABASE_VARIABLE] = "empirical_platform_paper_exit_custom"
    store_c = resolve_paper_exit_postgres_config(_STORE_B)
    assert store_c.database == "empirical_platform_paper_exit_custom"
    assert PAPER_EXIT_DATABASE_VARIABLE != "EMPIRICAL_PLATFORM_POSTGRES_DATABASE"


def test_an_unset_override_falls_back_to_the_documented_default_every_time() -> None:
    assert PAPER_EXIT_DATABASE_VARIABLE not in os.environ
    first = resolve_paper_exit_postgres_config(_STORE_B)
    second = resolve_paper_exit_postgres_config(_STORE_B)
    assert first.database == second.database == "empirical_platform_paper_exit"
