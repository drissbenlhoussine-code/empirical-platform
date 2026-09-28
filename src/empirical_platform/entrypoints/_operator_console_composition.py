"""MILESTONE-086 -- the Operator Console composition root.

THE ONLY PLACE THE CONSOLE'S BROKER IS CHOSEN, AND IT CAN ONLY CHOOSE THE SIMULATION.
`compose_operator_console` takes an `ExecutionCapability` and refuses -- before any database
connection, before any adapter is built -- everything except SIMULATION. There is no branch
here that imports or constructs `AlpacaPaperClient`; the module does not import it. PAPER
stays "locked pending M085 Paper Acceptance" and LIVE "not authorized": enabling either is a
separate, Owner-gated change to THIS file, not a setting, a flag or a request parameter.

SCHEMA AUTHORITY BELONGS TO THE COMPOSITION ROOT. The public M086 composition requires the
EXACT M085 schema head (`require_exact_m085_schema_head`) and then builds the console through
`_compose_verified_console`, a private helper that assumes the schema was already verified by
its caller. MILESTONE-087's composition (`_position_exit_composition.py`) verifies ITS exact
head and calls the same private helper with the exit runtime. Neither guard can be replaced by
a caller-supplied function: there is no parameter for one, and the helper is not exported.
M086 semantics stay "schema = M085 head"; M087 semantics are "schema = M087 head".

Like `_paper_composition.py`, this owns one `PostgresPersistenceService` for the whole
console process and hands the presentation layer a service object -- never a repository or a
connection.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from empirical_platform.shared.brokerage.paper_time import PaperTimeSource, SystemPaperTimeSource
from empirical_platform.shared.brokerage.simulation_paper import (
    SimulatedMarketData,
    SimulatedPaperBroker,
    SimulationStateLock,
    SimulationStore,
    default_exit_scenario_table,
    default_scenario_table,
)
from empirical_platform.shared.config.settings import (
    PostgreSQLConfigSnapshot,
    resolve_foundation_config,
)
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.paper_execution_repositories import (  # noqa: E501
    PostgresPaperExecutionRuntime,
    require_exact_m085_schema_head,
)
from empirical_platform.shared.persistence.postgres_repositories.runtime import (
    PostgresRepositoryRuntime,
)
from empirical_platform.usecases.operator_console import (
    CAPABILITIES,
    CapabilityRefusedError,
    ConsoleRepositories,
    ExecutionCapability,
    HmacSigner,
    OperatorConsoleService,
)
from empirical_platform.usecases.operator_console_exits import (
    ExitRepositories,
    PositionExitConsole,
)
from empirical_platform.usecases.operator_console_fixtures import (
    SIMULATION_CONFIGURATION_ID,
    SIMULATION_QUOTES,
    EvaluationEvidenceWatermarkRepository,
    SimulationDayReport,
    load_simulation_day,
)

__all__ = ["ConsoleRuntime", "compose_operator_console", "simulation_console_runtime"]

SIMULATION_STORE_FILE = "simulation-broker.json"


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ConsoleRuntime:
    """What the routes and the launcher receive. Nothing here reaches a network."""

    service: OperatorConsoleService
    repositories: ConsoleRepositories
    store: SimulationStore
    broker: SimulatedPaperBroker
    market_data: SimulatedMarketData
    time_source: PaperTimeSource
    clock: Callable[[], datetime]
    watermarks: EvaluationEvidenceWatermarkRepository
    configuration_id: str = SIMULATION_CONFIGURATION_ID
    #: The exclusive lock on the state directory; released by `close()`.
    state_lock: SimulationStateLock | None = None
    #: MILESTONE-087: the exit repositories when the M087 composition built this runtime; None
    #: for the M086 composition. Tests inspect them; routes never do.
    exits: ExitRepositories | None = None
    #: The schema revision the composition root verified before building this runtime.
    verified_schema_head: str = ""

    def close(self) -> None:
        """Release the state-directory lock. The persistence service is closed by its owner."""
        if self.state_lock is not None:
            self.state_lock.release()

    def load_day(self) -> SimulationDayReport:
        """Stage the deterministic day: broker behaviours, quotes, and the real M084 proposals."""
        scenarios = default_scenario_table()
        self.store.stage(
            scenarios=scenarios,
            quotes=dict(SIMULATION_QUOTES),
            exit_scenarios=default_exit_scenario_table(),
        )
        return load_simulation_day(
            repositories=self.repositories,
            watermarks=self.watermarks,
            broker=self.broker,
            time_source=self.time_source,
            clock=self.clock,
            symbols=tuple(scenarios),
        )


def _refuse_unless_simulation(capability: ExecutionCapability) -> None:
    if capability is not ExecutionCapability.SIMULATION:
        raise CapabilityRefusedError(
            f"the Operator Console cannot be composed for {capability.value}: PAPER is locked "
            "pending M085 Paper Acceptance and LIVE is not authorized. Nothing was built."
        )


def compose_operator_console(
    capability: ExecutionCapability,
    *,
    service: PostgresPersistenceService,
    state_dir: Path,
    clock: Callable[[], datetime] = _utc_now,
    time_source: PaperTimeSource | None = None,
    state_lock: SimulationStateLock | None = None,
) -> ConsoleRuntime:
    """Build the MILESTONE-086 console over an initialized persistence service. SIMULATION only.

    Requires the EXACT M085 schema head: this is the M086 console, and a database at any
    other revision -- including a later milestone's -- is refused before anything is built.
    Takes the state-directory lock (unless the caller already holds one and passes it) BEFORE
    the simulation store is opened, so a second console on the same directory is refused
    before it can read or mutate simulation state.
    """
    _refuse_unless_simulation(capability)
    verified = require_exact_m085_schema_head(service)
    return _compose_verified_console(
        service=service,
        state_dir=state_dir,
        clock=clock,
        time_source=time_source,
        state_lock=state_lock,
        exits=None,
        verified_schema_head=verified,
    )


def _compose_verified_console(
    *,
    service: PostgresPersistenceService,
    state_dir: Path,
    clock: Callable[[], datetime],
    time_source: PaperTimeSource | None,
    state_lock: SimulationStateLock | None,
    exits: ExitRepositories | None,
    verified_schema_head: str,
) -> ConsoleRuntime:
    """Build the console over a service whose schema THE CALLER ALREADY VERIFIED.

    Private on purpose: every public composition function verifies its own exact schema head
    and then calls this. It takes no verifier, so no entrypoint or request can substitute one.
    """
    lock = state_lock
    if lock is None:
        lock = SimulationStateLock(Path(state_dir))
        lock.acquire()
    m084 = PostgresRepositoryRuntime(service)
    paper = PostgresPaperExecutionRuntime(service)
    store = SimulationStore(Path(state_dir) / SIMULATION_STORE_FILE)
    broker = SimulatedPaperBroker(store, clock=clock)
    market_data = SimulatedMarketData(store, clock=clock)
    source: PaperTimeSource = time_source or SystemPaperTimeSource()
    signer = HmacSigner(secrets.token_bytes(32))
    repositories = ConsoleRepositories(
        configurations=m084.operator_trading_configurations,
        contexts=m084.evaluation_contexts,
        proposals=m084.trade_proposals,
        decisions=m084.approval_decisions,
        intents=m084.approved_order_intents,
        time_bases=paper.time_bases,
        snapshots=paper.paper_account_snapshots,
        previews=paper.submission_previews,
        authorizations=paper.execution_authorizations,
        attempts=paper.execution_attempts,
        acknowledgements=paper.broker_acknowledgements,
        events=paper.paper_execution_events,
        rounds=paper.reconciliation_rounds,
        kill_switch=paper.execution_kill_switch,
    )
    exit_console = (
        None
        if exits is None
        else PositionExitConsole(
            exits=exits,
            intents=repositories.intents,
            entry_attempts=repositories.attempts,
            kill_switch=repositories.kill_switch,
            broker=broker,
            market_data=market_data,
            signer=signer,
            time_source=source,
            clock=clock,
            environment=ExecutionCapability.SIMULATION.value,
        )
    )
    console = OperatorConsoleService(
        repositories=repositories,
        broker=broker,
        market_data=market_data,
        signer=signer,
        capability=CAPABILITIES[0],
        time_source=source,
        clock=clock,
        staged_scenarios=lambda: {s: v.value for s, v in store.scenarios().items()},
        exits=exit_console,
    )
    return ConsoleRuntime(
        service=console,
        repositories=repositories,
        store=store,
        broker=broker,
        market_data=market_data,
        time_source=source,
        clock=clock,
        watermarks=m084.evaluation_evidence_watermarks,
        state_lock=lock,
        exits=exits,
        verified_schema_head=verified_schema_head,
    )


@contextmanager
def simulation_console_runtime(
    config: PostgreSQLConfigSnapshot | None = None,
    *,
    state_dir: Path,
    clock: Callable[[], datetime] = _utc_now,
    time_source: PaperTimeSource | None = None,
) -> Iterator[ConsoleRuntime]:
    """Own the state lock and the persistence service for the M086 console's lifetime.

    The lock is taken FIRST -- before any database connection -- so a second process is
    refused before it touches anything; it is released LAST, after the service is closed.
    """
    lock = SimulationStateLock(Path(state_dir))
    lock.acquire()
    try:
        resolved = config if config is not None else resolve_foundation_config().postgresql
        service = PostgresPersistenceService(resolved)
        try:
            service.initialize()
            yield compose_operator_console(
                ExecutionCapability.SIMULATION,
                service=service,
                state_dir=state_dir,
                clock=clock,
                time_source=time_source,
                state_lock=lock,
            )
        finally:
            service.close()
    finally:
        lock.release()
