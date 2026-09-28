"""In-memory world for the MILESTONE-086 Operator Console tests.

The M085 repositories are the proven fakes from `_m085_fakes.py`; the M084 repositories
are small dictionaries with the PostgreSQL uniqueness refusals mirrored, so an idempotency
bug in the console (a second decision, intent, authorization or attempt) fails here the way
it would fail against the database. The broker is the REAL simulation adapter over a
temporary store file; the clock is controllable so tests can expire proposals, age
authorizations and satisfy the 60 s absence policy without sleeping.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tests.unit._m085_fakes import (
    FakeAcknowledgements,
    FakeAttempts,
    FakeAuthorizations,
    FakeEvents,
    FakeKillSwitch,
    FakePreviews,
    FakeReconciliationRounds,
    FakeSnapshots,
    FakeTimeBases,
)
from tests.unit._m087_fakes import (
    FakeExitAcknowledgements,
    FakeExitAttempts,
    FakeExitAuthorizations,
    FakeExitEvents,
    FakeExitPreviews,
    FakeExitRounds,
)

from empirical_platform.decision_candidate.evaluation_context import EvaluationContext
from empirical_platform.decision_candidate.evaluation_evidence_watermark import (
    EvaluationEvidenceWatermark,
)
from empirical_platform.decision_candidate.operator_trading_configuration import (
    OperatorTradingConfiguration,
)
from empirical_platform.decision_candidate.trade_approval import (
    ApprovalDecision,
    ApprovedOrderIntent,
)
from empirical_platform.decision_candidate.trade_proposal import ProposalStatus, TradeProposal
from empirical_platform.shared.brokerage.paper_time import PaperTimeReading
from empirical_platform.shared.brokerage.simulation_paper import (
    SimulatedMarketData,
    SimulatedPaperBroker,
    SimulationExitScenario,
    SimulationStore,
    default_exit_scenario_table,
    default_scenario_table,
)
from empirical_platform.usecases.operator_console import (
    CAPABILITIES,
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
    SIMULATION_QUOTES,
    SimulationDayReport,
    load_simulation_day,
)

START = datetime(2026, 9, 28, 14, 0, tzinfo=UTC)


class TestClock:
    """One controllable clock for the host, the broker and the console."""

    __test__ = False

    def __init__(self, start: datetime = START) -> None:
        self.utc = start
        self.monotonic = 1000.0

    def advance(self, seconds: float) -> None:
        self.utc += timedelta(seconds=seconds)
        self.monotonic += seconds

    def read(self) -> PaperTimeReading:
        return PaperTimeReading(self.utc, self.monotonic)

    def __call__(self) -> datetime:
        return self.utc


class MemoryConfigurations:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, int], OperatorTradingConfiguration] = {}

    def save(self, configuration: OperatorTradingConfiguration) -> OperatorTradingConfiguration:
        key = (configuration.configuration_governance_id, configuration.configuration_version)
        if key in self.rows:
            raise ValueError(f"configuration {key} already exists")
        self.rows[key] = configuration
        return configuration

    def get(self, gid: str, version: int) -> OperatorTradingConfiguration | None:
        return self.rows.get((gid, version))

    def latest(self, gid: str) -> OperatorTradingConfiguration | None:
        matches = [c for (g, _), c in self.rows.items() if g == gid]
        return max(matches, key=lambda c: c.configuration_version) if matches else None


class MemoryContexts:
    def __init__(self) -> None:
        self.rows: dict[str, EvaluationContext] = {}

    def save(self, context: EvaluationContext) -> EvaluationContext:
        self.rows[context.evaluation_context_id] = context
        return context

    def get(self, context_id: str) -> EvaluationContext | None:
        return self.rows.get(context_id)


class MemoryWatermarks:
    def capture(self, *, watermark_governance_id: str) -> EvaluationEvidenceWatermark:
        return EvaluationEvidenceWatermark(
            watermark_governance_id=watermark_governance_id, receipt_governance_ids=()
        )

    def get(self, watermark_governance_id: str) -> EvaluationEvidenceWatermark | None:
        return None


class MemoryProposals:
    def __init__(self) -> None:
        self.rows: dict[str, TradeProposal] = {}

    def save(self, proposal: TradeProposal) -> TradeProposal:
        if proposal.proposal_governance_id in self.rows:
            raise ValueError(f"proposal {proposal.proposal_governance_id} already exists")
        self.rows[proposal.proposal_governance_id] = proposal
        return proposal

    def get(self, proposal_id: str) -> TradeProposal | None:
        return self.rows.get(proposal_id)

    def list_by_status(self, status: ProposalStatus) -> tuple[TradeProposal, ...]:
        return tuple(p for p in self.rows.values() if p.status is status)

    def counts_by_status(self) -> dict[ProposalStatus, int]:
        counts = dict.fromkeys(ProposalStatus, 0)
        for proposal in self.rows.values():
            counts[proposal.status] += 1
        return counts

    def set_status(self, proposal_id: str, status: ProposalStatus) -> TradeProposal:
        moved = replace(self.rows[proposal_id], status=status)
        self.rows[proposal_id] = moved
        return moved

    def replace_row(self, proposal: TradeProposal) -> None:
        """Test hook: a proposal 'changed under' an open page (a new version)."""
        self.rows[proposal.proposal_governance_id] = proposal


class MemoryDecisions:
    def __init__(self) -> None:
        self.rows: dict[str, ApprovalDecision] = {}

    def record(self, decision: ApprovalDecision) -> ApprovalDecision:
        if decision.decision_governance_id in self.rows:
            raise ValueError(f"decision {decision.decision_governance_id} already exists")
        if self.for_proposal(decision.proposal_governance_id) is not None:
            raise ValueError("this proposal already has a decision")
        self.rows[decision.decision_governance_id] = decision
        return decision

    def get(self, decision_id: str) -> ApprovalDecision | None:
        return self.rows.get(decision_id)

    def for_proposal(self, proposal_id: str) -> ApprovalDecision | None:
        return next(
            (d for d in self.rows.values() if d.proposal_governance_id == proposal_id), None
        )


class MemoryIntents:
    def __init__(self) -> None:
        self.rows: dict[str, ApprovedOrderIntent] = {}

    def issue(self, intent: ApprovedOrderIntent) -> ApprovedOrderIntent:
        if intent.intent_governance_id in self.rows:
            raise ValueError(f"intent {intent.intent_governance_id} already exists")
        if self.for_proposal(intent.proposal_governance_id) is not None:
            raise ValueError("this proposal already has an intent")
        self.rows[intent.intent_governance_id] = intent
        return intent

    def get(self, intent_id: str) -> ApprovedOrderIntent | None:
        return self.rows.get(intent_id)

    def for_proposal(self, proposal_id: str) -> ApprovedOrderIntent | None:
        return next(
            (i for i in self.rows.values() if i.proposal_governance_id == proposal_id), None
        )


@dataclass
class World:
    clock: TestClock
    repositories: ConsoleRepositories
    watermarks: MemoryWatermarks
    store: SimulationStore
    broker: SimulatedPaperBroker
    market_data: SimulatedMarketData
    signer: HmacSigner
    service: OperatorConsoleService
    kill_switch: FakeKillSwitch
    exits: ExitRepositories

    def load_day(
        self,
        symbols: tuple[str, ...] | None = None,
        *,
        exit_scenarios: dict[str, SimulationExitScenario] | None = None,
    ) -> SimulationDayReport:
        scenarios = default_scenario_table()
        chosen = symbols or tuple(scenarios)
        exits = default_exit_scenario_table()
        exits.update(exit_scenarios or {})
        self.store.stage(
            scenarios={s: scenarios[s] for s in chosen},
            quotes={s: SIMULATION_QUOTES[s] for s in chosen},
            exit_scenarios={s: exits[s] for s in chosen},
        )
        return load_simulation_day(
            repositories=self.repositories,
            watermarks=self.watermarks,
            broker=self.broker,
            time_source=self.clock,
            clock=self.clock,
            symbols=chosen,
        )

    def proposal_id(self, symbol: str) -> str:
        return f"PRP-086-{self.clock.utc.strftime('%Y%m%d')}-{symbol}"

    def restart(self, *, new_secret: bool = True) -> World:
        """A fresh process over the SAME durable state: repositories, store file, clock."""
        store = SimulationStore(self.store.path)
        broker = SimulatedPaperBroker(store, clock=self.clock)
        market = SimulatedMarketData(store, clock=self.clock)
        signer = HmacSigner(b"another-process-secret") if new_secret else self.signer
        service = _service(
            self.repositories,
            self.exits if self.service.exits is not None else None,
            broker,
            market,
            signer,
            self.clock,
            store,
        )
        return World(
            clock=self.clock,
            repositories=self.repositories,
            watermarks=self.watermarks,
            store=store,
            broker=broker,
            market_data=market,
            signer=signer,
            service=service,
            kill_switch=self.kill_switch,
            exits=self.exits,
        )


def _service(
    repositories: ConsoleRepositories,
    exits: ExitRepositories | None,
    broker: SimulatedPaperBroker,
    market: SimulatedMarketData,
    signer: HmacSigner,
    clock: TestClock,
    store: SimulationStore,
) -> OperatorConsoleService:
    exit_console = (
        None
        if exits is None
        else PositionExitConsole(
            exits=exits,
            intents=repositories.intents,
            entry_attempts=repositories.attempts,
            kill_switch=repositories.kill_switch,
            broker=broker,
            market_data=market,
            signer=signer,
            time_source=clock,
            clock=clock,
            environment=ExecutionCapability.SIMULATION.value,
        )
    )
    return OperatorConsoleService(
        repositories=repositories,
        broker=broker,
        market_data=market,
        signer=signer,
        capability=CAPABILITIES[0],
        time_source=clock,
        clock=clock,
        staged_scenarios=lambda: {s: v.value for s, v in store.scenarios().items()},
        exits=exit_console,
    )


def simulation_world(tmp_path: Path, *, start: datetime = START, exits: bool = False) -> World:
    """The M086 world. `exits=False` is the M086 console exactly (open positions shown with their
    exit locked); `exits=True` composes the MILESTONE-087 exit console over the same records."""
    exits_enabled = exits
    clock = TestClock(start)
    attempts = FakeAttempts()
    acknowledgements = FakeAcknowledgements()
    events = FakeEvents()
    kill_switch = FakeKillSwitch()
    repositories = ConsoleRepositories(
        configurations=MemoryConfigurations(),
        contexts=MemoryContexts(),
        proposals=MemoryProposals(),
        decisions=MemoryDecisions(),
        intents=MemoryIntents(),
        time_bases=FakeTimeBases(),
        snapshots=FakeSnapshots(),
        previews=FakePreviews(),
        authorizations=FakeAuthorizations(),
        attempts=attempts,
        acknowledgements=acknowledgements,
        events=events,
        rounds=FakeReconciliationRounds(attempts, acknowledgements, events),
        kill_switch=kill_switch,
    )
    exit_authorizations = FakeExitAuthorizations()
    exit_attempts = FakeExitAttempts(exit_authorizations)
    exit_acknowledgements = FakeExitAcknowledgements()
    exit_events = FakeExitEvents()
    exits = ExitRepositories(
        previews=FakeExitPreviews(),
        authorizations=exit_authorizations,
        attempts=exit_attempts,
        acknowledgements=exit_acknowledgements,
        rounds=FakeExitRounds(exit_attempts, exit_acknowledgements, exit_events),
        events=exit_events,
    )
    store = SimulationStore(tmp_path / "simulation-broker.json")
    broker = SimulatedPaperBroker(store, clock=clock)
    market = SimulatedMarketData(store, clock=clock)
    signer = HmacSigner(b"test-process-secret")
    service = _service(
        repositories, exits if exits_enabled else None, broker, market, signer, clock, store
    )
    return World(
        clock=clock,
        repositories=repositories,
        watermarks=MemoryWatermarks(),
        store=store,
        broker=broker,
        market_data=market,
        signer=signer,
        service=service,
        kill_switch=kill_switch,
        exits=exits,
    )
