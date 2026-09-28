"""MILESTONE-087 -- the Operator Console composition root WITH the position-exit path.

SCHEMA AUTHORITY, M087's OWN. `compose_operator_console_with_exits` requires the EXACT M087
schema head (`require_exact_m087_schema_head`: refuses the M085 head, any older revision, an
unknown newer revision, multiple heads and a missing version) and only then builds the console
through the M086 composition module's private, already-verified helper, adding the M087 exit
runtime and the exit console. The M086 public composition is untouched and still requires the
exact M085 head; neither guard can be swapped by a caller, an entrypoint or a request.

SIMULATION ONLY. The capability firewall is the M086 one; the exit console is composed for
`ExecutionCapability.SIMULATION` and nothing else.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from empirical_platform.entrypoints._operator_console_composition import (
    ConsoleRuntime,
    _compose_verified_console,
    _refuse_unless_simulation,
)
from empirical_platform.shared.brokerage.paper_time import PaperTimeSource
from empirical_platform.shared.brokerage.simulation_paper import SimulationStateLock
from empirical_platform.shared.config.settings import (
    PostgreSQLConfigSnapshot,
    resolve_foundation_config,
)
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.position_exit_repositories import (  # noqa: E501
    PostgresPositionExitRuntime,
    require_exact_m087_schema_head,
)
from empirical_platform.usecases.operator_console import ExecutionCapability
from empirical_platform.usecases.operator_console_exits import ExitRepositories

__all__ = ["compose_operator_console_with_exits", "simulation_exit_console_runtime"]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def compose_operator_console_with_exits(
    capability: ExecutionCapability,
    *,
    service: PostgresPersistenceService,
    state_dir: Path,
    clock: Callable[[], datetime] = _utc_now,
    time_source: PaperTimeSource | None = None,
    state_lock: SimulationStateLock | None = None,
) -> ConsoleRuntime:
    """Build the MILESTONE-087 console (M086 console + exit path). SIMULATION only.

    Requires the EXACT M087 schema head. A database at the M085 head -- which has no exit
    tables -- or at any other revision is refused before anything is built.
    """
    _refuse_unless_simulation(capability)
    verified = require_exact_m087_schema_head(service)
    exit_runtime = PostgresPositionExitRuntime(service)
    exits = ExitRepositories(
        previews=exit_runtime.previews,
        authorizations=exit_runtime.authorizations,
        attempts=exit_runtime.attempts,
        acknowledgements=exit_runtime.acknowledgements,
        rounds=exit_runtime.rounds,
        events=exit_runtime.events,
    )
    return _compose_verified_console(
        service=service,
        state_dir=state_dir,
        clock=clock,
        time_source=time_source,
        state_lock=state_lock,
        exits=exits,
        verified_schema_head=verified,
    )


@contextmanager
def simulation_exit_console_runtime(
    config: PostgreSQLConfigSnapshot | None = None,
    *,
    state_dir: Path,
    clock: Callable[[], datetime] = _utc_now,
    time_source: PaperTimeSource | None = None,
) -> Iterator[ConsoleRuntime]:
    """Own the state lock and the persistence service for the M087 console's lifetime.

    Same order as the M086 runtime: the lock FIRST, before any database connection; released
    LAST, after the service is closed.
    """
    lock = SimulationStateLock(Path(state_dir))
    lock.acquire()
    try:
        resolved = config if config is not None else resolve_foundation_config().postgresql
        service = PostgresPersistenceService(resolved)
        try:
            service.initialize()
            yield compose_operator_console_with_exits(
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
