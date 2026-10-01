"""MILESTONE-089 -- Alembic environment for Store C, the PAPER exit-lifecycle database.

A SEPARATE, SELF-CONTAINED CHAIN. `migrations/` (the M082-M087 chain, `alembic.ini`) is never
imported, referenced or extended by this environment. This chain has exactly one revision,
with `down_revision = None`: pointed at a fresh database, `alembic upgrade head` here creates
ONLY the M089 exit-lifecycle tables, never the M082-M085 apparatus the other chain would drag
in. This is deliberate: Store C never holds the M085 entry tables (`paper_execution_attempt`
stays in Store B, `empirical_platform_paper`, unmodified at its exact M085 head), so a chain
that could ever reapply the M085/M087 migrations against Store C would be a standing hazard,
not a convenience.

THE DATABASE THIS POINTS AT. `EMPIRICAL_PLATFORM_POSTGRES_*` (host/port/user/password/pool)
are read exactly as `migrations/env.py` reads them -- the same server, the same credentials --
but the database name is `EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE`
(default `empirical_platform_paper_exit`), never `EMPIRICAL_PLATFORM_POSTGRES_DATABASE`. A
process that forgets to set the override and runs this chain still lands on the Store-C-named
default, never on Store A or Store B by accident.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None

_DATABASE_VARIABLE = "EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE"
_DEFAULT_DATABASE = "empirical_platform_paper_exit"


def run_migrations_offline() -> None:
    """Run migrations in offline mode."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url", "postgresql://localhost/placeholder"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in online mode against a real PostgreSQL connection: Store C only."""
    import os

    from sqlalchemy import create_engine

    from empirical_platform.shared.config.settings import resolve_foundation_config

    postgres_config = resolve_foundation_config().postgresql
    store_c = postgres_config.model_copy(
        update={"database": os.environ.get(_DATABASE_VARIABLE, _DEFAULT_DATABASE)}
    )
    from empirical_platform.shared.persistence.database_safety import (
        refuse_unplanned_personal_migration,
        require_migration_connection,
    )

    refuse_unplanned_personal_migration(store_c)
    connectable = create_engine(store_c.sqlalchemy_url())

    with connectable.connect() as connection:
        require_migration_connection(connection)
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
