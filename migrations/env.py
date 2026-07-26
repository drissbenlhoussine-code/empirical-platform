"""Alembic environment for the MILESTONE-022 PostgreSQL schema migration.

No ORM models are declared here; ``target_metadata`` stays ``None`` and every
table is defined explicitly in the revision scripts under
``migrations/versions``.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


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
    """Run migrations in online mode against a real PostgreSQL connection."""
    from sqlalchemy import create_engine

    from empirical_platform.shared.config.settings import resolve_foundation_config

    postgres_config = resolve_foundation_config().postgresql
    connectable = create_engine(postgres_config.sqlalchemy_url())

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
