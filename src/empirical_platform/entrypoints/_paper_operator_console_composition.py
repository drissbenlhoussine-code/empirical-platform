"""MILESTONE-088 -- the Operator Console composed for PAPER: Store B.

THE DUAL-STORE BOUNDARY, EXPLICIT. This module builds the console entirely over
`paper_execution_runtime()` (`entrypoints._paper_composition`) -- Store B, the SAME real
Alpaca-credentialed context `tools/m085_paper_acceptance.py` uses, UNCHANGED. There is no
second `PostgresPersistenceService`, no console-specific database, and no read from
`empirical_platform` (the M087/SIMULATION database, Store A) in this module at all: PAPER has
nothing to put there for this mission (opportunity scanning, position/exit UI state) --
`today()`, `active_trades()`, `history()` and `safety()` all project directly from Store B's
own M085 tables via `OperatorConsoleService`, reused unchanged. RELEASE v1 schema-blocker
fix: `paper_execution_runtime()` itself now proves Store B compatible via
`require_v1_integrated_schema_compatibility` (see that function's own docstring in
`paper_execution_repositories.py`), not the historical `require_exact_m085_schema_head` --
this module still reads NOTHING until `paper_execution_runtime()`'s own guard has passed;
only which guard that is changed, not the discipline.

WHY `OperatorConsoleService` ITSELF, NOT A PARALLEL CLASS. It was already written against
the `PaperBrokerPort`/`PaperMarketDataPort` protocols, never against a concrete simulated
type; its one PAPER-specific gate (composing it at all) is `__init__`'s capability check,
widened in this milestone to accept `PAPER` and `SIMULATION` -- never `LIVE`, which this
module's `PAPER_CAPABILITY` cannot express (`ExecutionCapability` has no LIVE member this
constant could carry with `enabled=True`, and no composition function here builds one).
Every other line of that service -- the two-stage ticket-bound approve/confirm, the M085
dispatch chain, exactly-once identity, the human-language failure translation -- runs
unchanged over Store B's repositories and the real `AlpacaPaperClient`.

TESTING THE WRITE PATH WITHOUT A REAL BROKER CALL. `compose_paper_operator_console` always
builds the real `AlpacaPaperClient`/`AlpacaPaperMarketDataClient` (Store B's own, exactly as
`_paper_composition.py` builds them). Tests that must never touch the network construct
`OperatorConsoleService` directly with `tests.unit._m085_fakes.FakeBroker`/`FakeMarketData`
instead of calling this composition function -- the SAME dependency-injection seam M085's
own unit tests already use. Nothing in this module, or in `OperatorConsoleService`, can
express a write to any endpoint other than the one `AlpacaPaperClient` was constructed
against; there is no URL parameter, no header mapping and no raw-body method here or in the
adapter it wraps (see `shared.brokerage.alpaca_paper`'s own module docstring).
"""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from empirical_platform.entrypoints._paper_composition import paper_execution_runtime
from empirical_platform.shared.brokerage.alpaca_paper import (
    AlpacaPaperClient,
    AlpacaPaperMarketDataClient,
)
from empirical_platform.shared.brokerage.paper_time import PaperTimeSource
from empirical_platform.shared.persistence.postgres_repositories.evaluation_evidence_watermark_repository import (  # noqa: E501
    PostgresEvaluationEvidenceWatermarkRepository,
)
from empirical_platform.usecases.operator_console import (
    CapabilityStatus,
    ConsoleRefusalError,
    ConsoleRepositories,
    ExecutionCapability,
    HmacSigner,
    OperatorConsoleService,
)
from empirical_platform.usecases.operator_console_exits import ExitRepositories
from empirical_platform.usecases.operator_console_fixtures import SimulationDayReport
from empirical_platform.usecases.paper_operator_console import prepare_paper_candidate
from empirical_platform.usecases.position_plan_manager import (
    ApprovedPlanRepository,
    PositionPlanManager,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


__all__ = ["PAPER_CAPABILITY", "PaperConsoleBackend", "paper_operator_console_runtime"]

#: MILESTONE-088. The real PAPER capability, declared here and ONLY here, after Store B's
#: schema has actually been proven compatible by `paper_execution_runtime()` below.
#: `usecases.operator_console.CAPABILITIES` -- M086's own displayed table -- is untouched:
#: a test pins it to `[True, False, False]` (SIMULATION enabled, PAPER and LIVE locked), and
#: that remains correct on the M086/M087 branches, where PAPER genuinely is not composed.
PAPER_CAPABILITY = CapabilityStatus(
    ExecutionCapability.PAPER,
    True,
    "Paper",
    "Real Alpaca PAPER endpoint (paper-api.alpaca.markets). Not real money and not a "
    "real-market execution. Every submission requires explicit Owner approval; nothing is "
    "scheduled or automatic.",
)


@dataclass(frozen=True, slots=True)
class PaperConsoleBackend:
    """Satisfies `entrypoints.operator_console_app.ConsoleBackend` for PAPER over Store B."""

    service: OperatorConsoleService
    configuration_id: str

    def load_day(self) -> SimulationDayReport:
        """PAPER has no simulated day: the route exists on the shared router but refuses."""
        raise ConsoleRefusalError(
            "Not applicable", "PAPER has no simulated day to load. Nothing was done."
        )

    def prepare_candidate(self) -> None:
        """The one Owner-triggered action that originates a new PAPER candidate.

        See `usecases.paper_operator_console.prepare_paper_candidate`: bounded to the same
        symbol, notional and limit-price safety envelope M085's own Paper Acceptance used,
        idempotent per calendar day, and refuses (never relaxes) when the market is shut or
        the quote is not fresh and safe. Writes a PREPARED proposal only -- nothing is
        decided, previewed, authorized or dispatched here.
        """
        prepare_paper_candidate(
            configurations=self._repositories.configurations,
            contexts=self._repositories.contexts,
            proposals=self._repositories.proposals,
            watermarks=self._watermarks,
            time_bases=self._repositories.time_bases,
            broker=self._broker,
            market_data=self._market_data,
            time_source=self._time_source,
            now=_utc_now(),
        )

    # MILESTONE-088: the fields `prepare_candidate` needs but `ConsoleBackend` does not
    # declare. Private, set once by the composition function below; never read by the
    # shared routes, which only ever call `service`, `configuration_id` and `load_day()`.
    _repositories: ConsoleRepositories
    _watermarks: PostgresEvaluationEvidenceWatermarkRepository
    _broker: AlpacaPaperClient
    _market_data: AlpacaPaperMarketDataClient
    _time_source: PaperTimeSource
    #: RELEASE v1. `None` for M088's own plain PAPER composition (`paper_operator_console_
    #: runtime`, unchanged below) -- only the SEPARATE exit-capable composition module (the
    #: capability that can actually close a position) builds these. When set,
    #: `paper_operator_console_app.py` wires /confirm-approval through `approve_full_plan`
    #: instead of `service.confirm_approval` directly, and starts `_plan_manager` as a
    #: background thread for the console process's lifetime.
    _plans: ApprovedPlanRepository | None = None
    _plan_manager: PositionPlanManager | None = None
    #: RELEASE v1. Set alongside `_plans`/`_plan_manager` so the Active/History routes can
    #: read the SAME exit-attempt records the manual exit flow and the automatic manager
    #: both already use -- never a second, parallel read of exit state.
    _exits: ExitRepositories | None = None


@contextmanager
def paper_operator_console_runtime() -> Iterator[PaperConsoleBackend]:
    """Own Store B's persistence service for the console's lifetime. PAPER only.

    Requires Store B's schema proven compatible (via `paper_execution_runtime`'s own
    `require_v1_integrated_schema_compatibility` guard -- RELEASE v1 schema-blocker fix;
    see that function's docstring in `paper_execution_repositories.py`) before anything is
    built or any credential is read. `exits` is always `None`: PAPER exit stays locked
    (MILESTONE-088 Phase 11) until M087 SELL_TO_CLOSE has its own Paper acceptance.
    """
    with paper_execution_runtime() as context:
        signer = HmacSigner(_signing_secret())
        repositories = ConsoleRepositories(
            configurations=context.m084.operator_trading_configurations,
            contexts=context.m084.evaluation_contexts,
            proposals=context.m084.trade_proposals,
            decisions=context.m084.approval_decisions,
            intents=context.m084.approved_order_intents,
            time_bases=context.paper.time_bases,
            snapshots=context.paper.paper_account_snapshots,
            previews=context.paper.submission_previews,
            authorizations=context.paper.execution_authorizations,
            attempts=context.paper.execution_attempts,
            acknowledgements=context.paper.broker_acknowledgements,
            events=context.paper.paper_execution_events,
            rounds=context.paper.reconciliation_rounds,
            kill_switch=context.paper.execution_kill_switch,
        )
        service = OperatorConsoleService(
            repositories=repositories,
            broker=context.broker,
            market_data=context.market_data,
            signer=signer,
            capability=PAPER_CAPABILITY,
            time_source=context.time_source,
            exits=None,
        )
        yield PaperConsoleBackend(
            service=service,
            configuration_id="CFG-088-PAPER",
            _repositories=repositories,
            _watermarks=context.m084.evaluation_evidence_watermarks,
            _broker=context.broker,
            _market_data=context.market_data,
            _time_source=context.time_source,
        )


def _signing_secret() -> bytes:
    return secrets.token_bytes(32)
