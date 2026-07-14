"""Alembic environment for infrastructure-only migration bootstrap.

No business schemas or domain metadata are defined in this milestone.
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
    """Online migrations are intentionally not configured in the scaffold."""
    msg = "Online database migrations are deferred until schema implementation is authorized."
    raise RuntimeError(msg)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
