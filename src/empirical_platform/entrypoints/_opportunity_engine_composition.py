"""MILESTONE-090 -- the Opportunity Engine's composition root.

READ-ONLY, BY WHAT IT NEVER CONSTRUCTS. This module builds `AlpacaPaperClient` (for
`fetch_clock`/`fetch_asset`/`fetch_account`) and `AlpacaPaperMarketDataClient` (for
`fetch_quote`/`fetch_minute_bars`) using the SAME credential/endpoint convention
`entrypoints._paper_composition.paper_execution_runtime` already established
(`resolve_paper_endpoint`, `credentials_from_environment` -- reused, not reimplemented). The
order-dispatch method remains reachable on `AlpacaPaperClient` (the same object
`PaperBrokerPort` fakes model, dispatch included, precisely so a handler that never invokes it
is the proof, not a structurally narrower type -- see `tests/unit/_m090_fakes.py`'s own
`FakeOpportunityBroker`), but no M090 code path anywhere invokes it (see
`tests/architecture/test_m090_environment_isolation.py`).

NOT STORE B, NOT STORE C. M090's own two tables live in the SAME default database
`entrypoints._operator_console_composition.py`'s `PostgresRepositoryRuntime` already reads M084's
`operator_trading_configuration` table from (`resolve_foundation_config().postgresql`) -- this
module opens ONE `PostgresPersistenceService` against that default config, never Store B's
Paper-execution database and never Store C's exit database, and requires no schema-head guard
(see `external-review/MILESTONE-090/scope-and-design.md` Section 4: research/read data, no
broker-write path in this milestone).

THE CONFIGURATION IS READ, NEVER GENERATED. Like every other milestone's composition root, this
one reads the latest `OperatorTradingConfiguration` version already staged under its OWN
governance id (`CFG-090-PAPER`) -- it does not invent, default or fabricate one. If none has been
staged yet, every backend method refuses clearly rather than guessing.

GENERATION IS A SEPARATE, EXPLICIT ACTION, NOT A SIDE EFFECT OF A PAGE VIEW. `today()` only
reads opportunities already persisted for the current session date
(`OpportunityRepository.list_for_session`) -- it never calls `GenerateOpportunitiesHandler`
itself, so loading the Today page can never trigger a real broker call. `generate_today` is
exposed separately on `OpportunityEngineRuntime` for whatever explicit trigger (a CLI, a staged
fixture run) a later step wires up; nothing in this file calls it automatically, on a timer or on
any request.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from empirical_platform.entrypoints._paper_composition import (
    resolve_paper_endpoint,
)
from empirical_platform.shared.brokerage.alpaca_paper import (
    AlpacaPaperClient,
    AlpacaPaperMarketDataClient,
    credentials_from_environment,
)
from empirical_platform.shared.config.settings import (
    PostgreSQLConfigSnapshot,
    resolve_foundation_config,
)
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.opportunity_engine_repositories import (  # noqa: E501
    PostgresOpportunityEngineRuntime,
)
from empirical_platform.shared.persistence.postgres_repositories.runtime import (
    PostgresRepositoryRuntime,
)
from empirical_platform.usecases.opportunity_engine import (
    ApproveOpportunityCommand,
    ApproveOpportunityHandler,
    GenerateOpportunitiesCommand,
    GenerateOpportunitiesHandler,
    IgnoreOpportunityCommand,
    IgnoreOpportunityHandler,
    OperatorTradingConfiguration,
    OperatorTradingConfigurationRepository,
    OpportunityEnginePolicy,
    OpportunityEngineRefusedError,
    TradingOpportunity,
)

__all__ = [
    "CONFIGURATION_GOVERNANCE_ID",
    "DEFAULT_OPPORTUNITY_ENGINE_POLICY",
    "OpportunityEngineRuntime",
    "opportunity_engine_runtime",
]

#: This milestone's OWN configuration identity, matching M088/M089's per-milestone convention
#: (`CFG-088-PAPER`, `CFG-089-PAPER`) rather than reusing another milestone's literal row --
#: staging it (Phase 22) is a separate, later step; this module only ever READS it.
CONFIGURATION_GOVERNANCE_ID = "CFG-090-PAPER"

#: The first versioned policy this engine ships with (see
#: `decision_candidate.opportunity_engine.OPPORTUNITY_ENGINE_POLICY_VERSION`). Every threshold
#: documented at its own field in `OpportunityEnginePolicy`; the values below are this
#: composition root's own choice of defaults for a REAL, liquid-equity intraday universe --
#: deliberately more conservative than the small toy fixtures the unit-test suites use to
#: isolate one gate at a time.
DEFAULT_OPPORTUNITY_ENGINE_POLICY = OpportunityEnginePolicy(
    policy_version="M090-V1",
    structure_lookback_bars=5,
    #: A real liquid-equity floor (Alpaca IEX 1-minute bar volume), well above the toy 1,000
    #: unit-test fixtures use to isolate the liquidity gate from the structure gate.
    minimum_recent_share_volume=20_000,
    minimum_reward_risk_ratio=Decimal("2"),
    maximum_loss_per_trade=Decimal("100"),
    top_n=5,
    entry_tolerance_percent=Decimal("0.5"),
    #: 5 minutes: long enough for the Owner to reach Review, short enough that a CANDIDATE row
    #: never lingers past the intraday moment it described.
    opportunity_validity_seconds=300,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _decision_id() -> str:
    return "DEC-" + secrets.token_hex(16)


class OpportunityEngineRuntime:
    """What `entrypoints.opportunity_engine_app.OpportunityEngineBackend` needs, and a separate,
    explicitly-named `generate_today` hook for whatever later, explicit trigger runs the engine.
    Implements the Protocol structurally (duck typing); no inheritance needed."""

    __slots__ = ("_broker", "_configurations", "_market_data", "_policy", "_service")

    def __init__(
        self,
        *,
        configurations: OperatorTradingConfigurationRepository,
        policy: OpportunityEnginePolicy,
        broker: AlpacaPaperClient,
        market_data: AlpacaPaperMarketDataClient,
        service: PostgresOpportunityEngineRuntime,
    ) -> None:
        self._configurations = configurations
        self._policy = policy
        self._broker = broker
        self._market_data = market_data
        self._service = service

    def _configuration(self) -> OperatorTradingConfiguration:
        configuration = self._configurations.latest(CONFIGURATION_GOVERNANCE_ID)
        if configuration is None:
            raise OpportunityEngineRefusedError(
                f"no OperatorTradingConfiguration is staged under {CONFIGURATION_GOVERNANCE_ID!r}; "
                "nothing can be generated, reviewed or approved yet"
            )
        return configuration

    @staticmethod
    def _session_date(configuration: OperatorTradingConfiguration, *, now: datetime) -> str:
        return now.astimezone(ZoneInfo(configuration.operator_timezone)).date().isoformat()

    def top_n(self) -> int:
        return self._policy.top_n

    def today(self) -> tuple[TradingOpportunity, ...]:
        """Reads only. Never calls the broker, never generates -- see the module docstring."""
        configuration = self._configuration()
        session_date = self._session_date(configuration, now=_utc_now())
        return self._service.opportunities.list_for_session(session_date)

    def get(self, opportunity_id: str) -> TradingOpportunity | None:
        return self._service.opportunities.get(opportunity_id)

    def approve(self, opportunity_id: str, *, approved_by: str) -> TradingOpportunity:
        configuration = self._configuration()
        handler = ApproveOpportunityHandler(
            configuration=configuration,
            policy=self._policy,
            broker=self._broker,
            market_data=self._market_data,
            bars=self._market_data,
            opportunities=self._service.opportunities,
            decisions=self._service.decisions,
        )
        return handler.handle(
            ApproveOpportunityCommand(
                opportunity_id=opportunity_id,
                decision_id=_decision_id(),
                approved_by=approved_by,
                at=_utc_now(),
            )
        )

    def ignore(self, opportunity_id: str, *, ignored_by: str) -> TradingOpportunity:
        handler = IgnoreOpportunityHandler(
            opportunities=self._service.opportunities, decisions=self._service.decisions
        )
        return handler.handle(
            IgnoreOpportunityCommand(
                opportunity_id=opportunity_id,
                decision_id=_decision_id(),
                ignored_by=ignored_by,
                at=_utc_now(),
            )
        )

    def generate_today(self) -> tuple[TradingOpportunity, ...]:
        """NOT part of `OpportunityEngineBackend` -- a separate, explicitly-named hook for
        whatever later, explicit trigger (a CLI, a staged fixture run) runs the engine for
        real. Nothing in this composition module calls this on its own; see the module
        docstring."""
        configuration = self._configuration()
        now = _utc_now()
        session_date = self._session_date(configuration, now=now)
        handler = GenerateOpportunitiesHandler(
            configuration=configuration,
            policy=self._policy,
            broker=self._broker,
            market_data=self._market_data,
            bars=self._market_data,
            opportunities=self._service.opportunities,
        )
        return handler.handle(
            GenerateOpportunitiesCommand(session_date=session_date, generated_at=now)
        )


@contextmanager
def opportunity_engine_runtime(
    config: PostgreSQLConfigSnapshot | None = None,
    *,
    policy: OpportunityEnginePolicy = DEFAULT_OPPORTUNITY_ENGINE_POLICY,
) -> Iterator[OpportunityEngineRuntime]:
    """Own the persistence service for the runtime's lifetime.

    Credentials are read from the process environment exactly once, here, via the SAME
    `resolve_paper_endpoint`/`credentials_from_environment` pair `paper_execution_runtime`
    already uses -- no second credential path. No `require_exact_m09X_schema_head` guard: see
    the module docstring for why M090's tables carry none.
    """
    endpoint = resolve_paper_endpoint()
    credentials = credentials_from_environment(dict(os.environ))
    broker = AlpacaPaperClient(endpoint=endpoint, credentials=credentials)
    market_data = AlpacaPaperMarketDataClient(credentials=credentials)
    resolved = config if config is not None else resolve_foundation_config().postgresql
    service = PostgresPersistenceService(resolved)
    try:
        service.initialize()
        m084 = PostgresRepositoryRuntime(service)
        opportunity_service = PostgresOpportunityEngineRuntime(service)
        yield OpportunityEngineRuntime(
            configurations=m084.operator_trading_configurations,
            policy=policy,
            broker=broker,
            market_data=market_data,
            service=opportunity_service,
        )
    finally:
        service.close()
