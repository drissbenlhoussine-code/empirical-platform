"""Opt-in composition of the separately packaged IBKR adapter; no default DB fallback."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.persistence.market_journal import (
    MarketConfigurationRepository,
    PostgresMarketJournal,
    create_market_store,
)
from empirical_platform.usecases.decision_to_approval_io import (
    read_configuration,
    render_configuration_json,
)
from empirical_platform.usecases.market_access import (
    MarketAccessService,
    OperatorTradingConfiguration,
    require_acceptance_policy,
)
from empirical_platform.usecases.market_console import MarketReviewService


@dataclass(frozen=True)
class MarketAccessRuntime:
    service: MarketAccessService
    journal: PostgresMarketJournal
    configurations: MarketConfigurationRepository
    reviews: MarketReviewService


@contextmanager
def market_access_runtime(
    *,
    database: PostgreSQLConfigSnapshot,
    expected_identity: str,
    paper_account: str,
    client_id: int,
    configuration_id: str,
    port: int = 7497,
    enable_approved_paper_dispatch: bool = False,
) -> Iterator[MarketAccessRuntime]:
    """Read-only by default; a deployment flag never substitutes for exact plan approval."""
    if enable_approved_paper_dispatch and not expected_identity.startswith(
        "PERSONAL_PAPER:MARKET_ACCESS:"
    ):
        raise ValueError("real dispatch requires a dedicated protected personal market store")
    from empirical_ibkr.paper import IBKRPaperAdapter
    from empirical_ibkr.session import IBKRSession

    store = create_market_store(database, expected_identity)
    session = IBKRSession(account=paper_account, port=port, client_id=client_id)
    try:
        configurations = MarketConfigurationRepository(
            store, encode=render_configuration_json, decode=read_configuration
        )

        def policy() -> OperatorTradingConfiguration:
            value = configurations.latest(configuration_id)
            if value is None:
                raise ValueError("canonical Owner configuration is required")
            require_acceptance_policy(value)
            return value

        policy()  # Guard database and configuration before contacting any broker.
        session.connect()
        broker = IBKRPaperAdapter(session, allow_approved_writes=enable_approved_paper_dispatch)
        journal = PostgresMarketJournal(store)
        service = MarketAccessService(
            journal=journal, broker=broker, policy=policy, now=lambda: datetime.now(UTC)
        )
        yield MarketAccessRuntime(service, journal, configurations, MarketReviewService(journal))
    finally:
        session.close()
        store.engine.dispose()
