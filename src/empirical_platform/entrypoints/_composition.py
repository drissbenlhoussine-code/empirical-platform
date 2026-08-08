"""Shared resource-lifecycle composition helper for entrypoints (MILESTONE-053).

Owns exactly the `PostgresPersistenceService`/`PostgresRepositoryRuntime`
construction-and-cleanup boundary already proven three times, identically,
by M050/M051/M052's own hand-rolled entrypoints -- extracted here only
because eight new entrypoints in this one milestone would otherwise repeat
the identical M050-Y-1-class resource-lifecycle risk eight times over
(see MILESTONE_053 scope Section 4). Contains no handler/command awareness,
no dispatch, and is not a registry or service locator: every caller still
constructs its own specific handler and command explicitly.

`get_campaign.py`/`cancel_campaign.py`/`create_campaign.py` (M050-M052) are
deliberately not retrofitted to use this -- they remain exactly as
independently reviewed and frozen.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from empirical_platform.shared.config.settings import (
    PostgreSQLConfigSnapshot,
    resolve_foundation_config,
)
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.runtime import (
    PostgresRepositoryRuntime,
)


@contextmanager
def postgres_repository_runtime(
    config: PostgreSQLConfigSnapshot | None = None,
) -> Iterator[PostgresRepositoryRuntime]:
    """Construct, initialize, and guarantee cleanup of one real PostgreSQL
    repository runtime for the duration of one composition call.

    `config` defaults to the real environment-resolved configuration. The
    service's entire lifetime, including `.initialize()`, is owned by this
    context manager's own `try`/`finally` boundary -- `.close()` is
    attempted whether initialization, repository construction, or the
    caller's own body succeeds or fails.
    """
    resolved_config = config if config is not None else resolve_foundation_config().postgresql
    service = PostgresPersistenceService(resolved_config)
    try:
        service.initialize()
        yield PostgresRepositoryRuntime(service)
    finally:
        service.close()
