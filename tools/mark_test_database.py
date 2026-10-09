"""Explicitly mark an EMPTY disposable database; never bless personal data as test data."""

from __future__ import annotations

import os

from sqlalchemy import create_engine, text

from empirical_platform.shared.config.settings import resolve_foundation_config
from empirical_platform.shared.persistence.database_safety import (
    IDENTITY_QUERY,
    TEST_IDENTITY,
    DatabaseSafetyError,
    require_test_target,
)


def main() -> None:
    config = resolve_foundation_config().postgresql
    names = [config.database]
    store_c = os.environ.get("EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE")
    if store_c:
        names.append(store_c)
    for name in names:
        require_test_target(name, config.port)
        engine = create_engine(config.model_copy(update={"database": name}).sqlalchemy_url())
        try:
            with engine.begin() as connection:
                identity = connection.execute(text(IDENTITY_QUERY)).mappings().one()["identity"]
                tables = connection.execute(
                    text("SELECT count(*) FROM pg_tables WHERE schemaname='public'")
                ).scalar_one()
                if identity == TEST_IDENTITY:
                    continue
                if identity is not None or tables:
                    raise DatabaseSafetyError("only an unmarked EMPTY test database can be marked")
                quoted = connection.dialect.identifier_preparer.quote_identifier(name)
                connection.exec_driver_sql(f"COMMENT ON DATABASE {quoted} IS 'EMPIRICAL:TEST'")
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
