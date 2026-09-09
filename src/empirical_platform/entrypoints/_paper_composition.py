"""MILESTONE-085 composition: the one place a paper credential is read.

WHY A SECOND COMPOSITION HELPER. `_composition.py` yields M084's
`PostgresRepositoryRuntime`, and that file belongs to MILESTONE-053. This one
yields the same thing PLUS M085's own runtime and the two pinned broker clients,
over ONE shared `PostgresPersistenceService`, so M085 does not modify either
`_composition.py` or M084's runtime module to get what it needs.

CREDENTIALS EXIST ONLY HERE AND ONLY IN THE ADAPTER. They are read from the
process environment in this module, handed straight to `AlpacaPaperCredentials`
-- whose `repr` is redacted -- and never returned, logged, stored or passed to a
domain type, a repository or a renderer. No object reachable from an entrypoint
carries one.

THE ENDPOINT IS PROVEN, NOT TRUSTED. `EMPIRICAL_ALPACA_PAPER_BASE_URL` is parsed
by `PaperEndpoint.from_url`, which refuses anything that is not exactly
`https://paper-api.alpaca.markets`. The variable's name contains the word PAPER;
that is not evidence about its value, and this module does not treat it as such.
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass

from empirical_platform.shared.brokerage.alpaca_paper import (
    AlpacaPaperClient,
    AlpacaPaperMarketDataClient,
    PaperEndpoint,
    credentials_from_environment,
)
from empirical_platform.shared.config.settings import (
    PostgreSQLConfigSnapshot,
    resolve_foundation_config,
)
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.paper_execution_repositories import (  # noqa: E501
    PostgresPaperExecutionRuntime,
)
from empirical_platform.shared.persistence.postgres_repositories.runtime import (
    PostgresRepositoryRuntime,
)

__all__ = ["PaperExecutionContext", "paper_execution_runtime", "resolve_paper_endpoint"]

_BASE_URL_VARIABLE = "EMPIRICAL_ALPACA_PAPER_BASE_URL"


def resolve_paper_endpoint(environment: Mapping[str, str] | None = None) -> PaperEndpoint:
    """Parse and PROVE the configured endpoint is the paper endpoint."""
    source = environment if environment is not None else os.environ
    url = source.get(_BASE_URL_VARIABLE)
    if not url:
        raise ValueError(
            f"{_BASE_URL_VARIABLE} is not set; this milestone will not guess an endpoint"
        )
    return PaperEndpoint.from_url(url)


@dataclass(frozen=True, slots=True)
class PaperExecutionContext:
    """Everything an M085 operator command needs, and nothing it does not."""

    m084: PostgresRepositoryRuntime
    paper: PostgresPaperExecutionRuntime
    broker: AlpacaPaperClient
    market_data: AlpacaPaperMarketDataClient


@contextmanager
def paper_execution_runtime(
    config: PostgreSQLConfigSnapshot | None = None,
) -> Iterator[PaperExecutionContext]:
    """Construct, initialize and guarantee cleanup of one paper-execution context.

    The persistence service's entire lifetime is owned by this `try`/`finally`, so
    `close()` is attempted whether initialization, client construction or the
    caller's own body raises -- the same discipline `_composition.py` established.
    """
    resolved = config if config is not None else resolve_foundation_config().postgresql
    endpoint = resolve_paper_endpoint()
    credentials = credentials_from_environment(dict(os.environ))
    service = PostgresPersistenceService(resolved)
    try:
        service.initialize()
        yield PaperExecutionContext(
            m084=PostgresRepositoryRuntime(service),
            paper=PostgresPaperExecutionRuntime(service),
            broker=AlpacaPaperClient(endpoint=endpoint, credentials=credentials),
            market_data=AlpacaPaperMarketDataClient(credentials=credentials),
        )
    finally:
        service.close()
