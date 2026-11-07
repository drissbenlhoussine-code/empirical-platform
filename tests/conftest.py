"""Install database isolation before collecting any PostgreSQL fixture."""

import os

from empirical_platform.shared.persistence.database_safety import install_test_connection_guard


def pytest_configure() -> None:
    if os.environ.get("EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS") == "1":
        install_test_connection_guard()


# Explicit historical schema compatibility; full-head v1 suites are never redirected.
pytest_plugins = ["tests.historical_schema_plugin", "tests.secondary_database_plugin"]
