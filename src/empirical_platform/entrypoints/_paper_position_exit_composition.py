"""MILESTONE-089 -- the Operator Console composed for PAPER WITH the exit path: Store B + Store C.

THE DUAL-STORE BOUNDARY, EXPLICIT. Store B is `paper_execution_runtime()`
(`entrypoints._paper_composition`) -- the SAME real Alpaca-credentialed, exact-M085-schema-
head-verified context `tools/m085_paper_acceptance.py` and MILESTONE-088's console use,
UNCHANGED. Store C is a SECOND, independent `PostgresPersistenceService`, over a database this
module opens itself, exact-M089-schema-head-verified
(`require_exact_m089_schema_head`) before anything built over it is handed out. There is no
shared connection, no shared transaction and no cross-database foreign key between the two: a
preview built for Store C reads Store B's own M085 entry-attempt repository directly (the SAME
usecase code M087 already runs, `usecases.position_exit.PreviewPositionExitHandler`, composed
here over Store B's `intents`/`entry_attempts` instead of Store A's) and then writes to Store C
in a separate operation. See `external-review/MILESTONE-089/scope-and-design.md`: "No shared
cross-database transaction may be assumed atomic. Use durable reconciliation instead."

WHY THIS IS A NEW FILE, NOT AN EDIT TO `_paper_operator_console_composition.py`. That module is
MILESTONE-088's own composition root, stable and already deployed; MILESTONE-089's mission is
explicit that M088's "no exit path" behavior must remain correct on M088 itself, and that this
milestone must not replace M088's console. This module duplicates the small amount of Store-B
wiring `paper_operator_console_runtime()` already does (opening `paper_execution_runtime()`,
building `ConsoleRepositories`, one `HmacSigner`) rather than importing or modifying that
function, so a change here can never alter M088's own composition, and a change there can never
silently add an exit path to M088's console. `PAPER_CAPABILITY` and `PaperConsoleBackend` ARE
imported from that module: they are M088's own already-reviewed capability declaration and
result type, reused unchanged, not duplicated.

ONE SIGNER, SHARED. As in M086/M087's `_compose_verified_console`, the entry-order
`OperatorConsoleService` and the exit `PositionExitConsole` share ONE `HmacSigner` instance for
this process's lifetime: `ConfirmationTicket.action` (`"EXECUTE"` vs `"EXIT"`) is what tells the
two kinds of ticket apart, not the key.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from empirical_platform.entrypoints._paper_composition import paper_execution_runtime
from empirical_platform.entrypoints._paper_operator_console_composition import (
    PAPER_CAPABILITY,
    PaperConsoleBackend,
)
from empirical_platform.shared.config.settings import (
    PostgreSQLConfigSnapshot,
    resolve_foundation_config,
)
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.approved_plan_repositories import (  # noqa: E501
    PostgresApprovedPlanRepository,
    require_exact_v1_approved_plan_schema_head,
)
from empirical_platform.shared.persistence.postgres_repositories.paper_position_exit_schema import (
    require_exact_m089_schema_head,
)
from empirical_platform.shared.persistence.postgres_repositories.position_exit_repositories import (  # noqa: E501
    PostgresPositionExitRuntime,
)
from empirical_platform.usecases.operator_console import (
    ConsoleRepositories,
    HmacSigner,
    OperatorConsoleService,
)
from empirical_platform.usecases.operator_console_exits import ExitRepositories, PositionExitConsole
from empirical_platform.usecases.position_plan_manager import PositionPlanManager

__all__ = [
    "PAPER_EXIT_DATABASE_VARIABLE",
    "resolve_paper_exit_postgres_config",
    "paper_operator_console_with_exit_runtime",
]

#: Names Store C's database. Never `EMPIRICAL_PLATFORM_POSTGRES_DATABASE` -- that variable,
#: read by `resolve_foundation_config()`, names Store B in this process. The same host, port,
#: user and password as Store B are reused (one Postgres server, two databases); only the
#: database name differs.
PAPER_EXIT_DATABASE_VARIABLE = "EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE"
_DEFAULT_STORE_C_DATABASE = "empirical_platform_paper_exit"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def resolve_paper_exit_postgres_config(
    store_b_config: PostgreSQLConfigSnapshot,
) -> PostgreSQLConfigSnapshot:
    """Store C's connectivity: Store B's server and credentials, a distinct database name."""
    database = os.environ.get(PAPER_EXIT_DATABASE_VARIABLE, _DEFAULT_STORE_C_DATABASE)
    return store_b_config.model_copy(update={"database": database})


@contextmanager
def paper_operator_console_with_exit_runtime() -> Iterator[PaperConsoleBackend]:
    """Own Store B's AND Store C's persistence services for the console's lifetime.

    Requires the EXACT M085 schema head on Store B (via `paper_execution_runtime()`,
    unweakened) and the EXACT M089 schema head on Store C (via
    `require_exact_m089_schema_head`, unweakened) before either database is read for anything
    but the schema check itself, and before any credential is used to build the broker
    clients. Store C is opened INSIDE Store B's context and closed before it, so a Store-C
    failure never leaves Store B's connection dangling and Store B's guard always runs first.
    """
    with paper_execution_runtime() as store_b:
        store_a_config = resolve_foundation_config().postgresql
        store_c_config = resolve_paper_exit_postgres_config(store_a_config)
        store_a_plans = PostgresPersistenceService(store_a_config)
        store_c = PostgresPersistenceService(store_c_config)
        try:
            store_a_plans.initialize()
            require_exact_v1_approved_plan_schema_head(store_a_plans)
            plans = PostgresApprovedPlanRepository(store_a_plans)
            store_c.initialize()
            require_exact_m089_schema_head(store_c)
            exit_runtime = PostgresPositionExitRuntime(store_c)
            exits = ExitRepositories(
                previews=exit_runtime.previews,
                authorizations=exit_runtime.authorizations,
                attempts=exit_runtime.attempts,
                acknowledgements=exit_runtime.acknowledgements,
                rounds=exit_runtime.rounds,
                events=exit_runtime.events,
            )
            signer = HmacSigner(secrets.token_bytes(32))
            repositories = ConsoleRepositories(
                configurations=store_b.m084.operator_trading_configurations,
                contexts=store_b.m084.evaluation_contexts,
                proposals=store_b.m084.trade_proposals,
                decisions=store_b.m084.approval_decisions,
                intents=store_b.m084.approved_order_intents,
                time_bases=store_b.paper.time_bases,
                snapshots=store_b.paper.paper_account_snapshots,
                previews=store_b.paper.submission_previews,
                authorizations=store_b.paper.execution_authorizations,
                attempts=store_b.paper.execution_attempts,
                acknowledgements=store_b.paper.broker_acknowledgements,
                events=store_b.paper.paper_execution_events,
                rounds=store_b.paper.reconciliation_rounds,
                kill_switch=store_b.paper.execution_kill_switch,
            )
            exit_console = PositionExitConsole(
                exits=exits,
                intents=repositories.intents,
                entry_attempts=repositories.attempts,
                configurations=repositories.configurations,
                kill_switch=repositories.kill_switch,
                broker=store_b.broker,
                market_data=store_b.market_data,
                signer=signer,
                time_source=store_b.time_source,
                clock=_utc_now,
                environment=PAPER_CAPABILITY.capability.value,
            )
            service = OperatorConsoleService(
                repositories=repositories,
                broker=store_b.broker,
                market_data=store_b.market_data,
                signer=signer,
                capability=PAPER_CAPABILITY,
                time_source=store_b.time_source,
                exits=exit_console,
            )
            # RELEASE v1: the automatic position-plan manager, over the SAME Store B/Store C
            # repositories the Owner's own manual exit already uses -- never a parallel
            # broker-submission path (see `usecases.position_plan_manager`'s own docstring).
            plan_manager = PositionPlanManager(
                plans=plans,
                intents=repositories.intents,
                entry_attempts=repositories.attempts,
                exit_attempts=exits.attempts,
                previews=exits.previews,
                authorizations=exits.authorizations,
                acknowledgements=exits.acknowledgements,
                events=exits.events,
                rounds=exits.rounds,
                broker=store_b.broker,
                market_data=store_b.market_data,
                configurations=repositories.configurations,
                environment=PAPER_CAPABILITY.capability.value,
                time_source=store_b.time_source,
            )
            yield PaperConsoleBackend(
                service=service,
                configuration_id="CFG-089-PAPER",
                _repositories=repositories,
                _watermarks=store_b.m084.evaluation_evidence_watermarks,
                _broker=store_b.broker,
                _market_data=store_b.market_data,
                _time_source=store_b.time_source,
                _plans=plans,
                _plan_manager=plan_manager,
            )
        finally:
            store_c.close()
            store_a_plans.close()
