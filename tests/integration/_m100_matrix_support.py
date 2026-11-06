"""Shared harness for the M100 24-step acceptance matrix (not a test module).

REAL: PostgreSQL Store B at the current head (v2 entry-risk triggers active), PostgreSQL Store C
at its own head, the approved-plan table, every M084/M085/M087/M089 handler, the D1 limit gate
and the D3 exit state machine.

SIMULATED: only the broker (``SimulatedPaperBroker`` / ``SimulatedMarketData`` over a
``SimulationStore``) and the clock. No network is opened; no real order can exist.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine
from tests.integration._m085_support import (
    EVALUATED_AT,
    a_configuration,
    a_context,
    config,
    paper_bound_market_inputs,
)
from tests.integration._m089_support import store_c_config

from empirical_platform.decision_candidate.approved_plan import (
    ApprovedPlan,
    derive_system_identity,
)
from empirical_platform.decision_candidate.paper_execution import PaperExecutionState
from empirical_platform.shared.brokerage.paper_time import PaperTimeReading
from empirical_platform.shared.brokerage.simulation_paper import (
    SimulatedMarketData,
    SimulatedPaperBroker,
    SimulationExitScenario,
    SimulationScenario,
    SimulationStore,
)
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.approved_plan_repositories import (  # noqa: E501
    PostgresApprovedPlanRepository,
)
from empirical_platform.shared.persistence.postgres_repositories.external_position_closure_repositories import (  # noqa: E501
    PostgresExternalPositionClosureRepository,
)
from empirical_platform.shared.persistence.postgres_repositories.paper_execution_repositories import (  # noqa: E501
    PostgresPaperExecutionRuntime,
)
from empirical_platform.shared.persistence.postgres_repositories.position_exit_repositories import (  # noqa: E501
    PostgresPositionExitRuntime,
)
from empirical_platform.shared.persistence.postgres_repositories.runtime import (
    PostgresRepositoryRuntime,
)
from empirical_platform.usecases.decision_to_approval import (
    SaveOperatorTradingConfigurationCommand,
    SaveOperatorTradingConfigurationHandler,
)
from empirical_platform.usecases.paper_execution import (
    AuthorizePaperSubmissionCommand,
    AuthorizePaperSubmissionHandler,
    DecidePaperBoundTradeProposalCommand,
    DecidePaperBoundTradeProposalHandler,
    IssuePaperBoundOrderIntentCommand,
    IssuePaperBoundOrderIntentHandler,
    PreparePaperBoundTradeProposalCommand,
    PreparePaperBoundTradeProposalHandler,
    PreviewPaperSubmissionCommand,
    PreviewPaperSubmissionHandler,
    ReconcilePaperOrderCommand,
    ReconcilePaperOrderHandler,
    SubmitAuthorizedPaperOrderCommand,
    SubmitAuthorizedPaperOrderHandler,
)
from empirical_platform.usecases.position_plan_manager import PositionPlanManager

#: Everything in Store A/B this matrix writes that ``truncate_all`` does not already clear.
EXTRA_B_TABLES = ("approved_plan",)

QUOTE = ("199.95", "200.10")


class MatrixClock:
    """One controllable clock for the host, the simulated broker and every handler."""

    def __init__(self) -> None:
        self.utc = EVALUATED_AT + timedelta(seconds=25)
        self.elapsed = 1000.0

    def __call__(self) -> datetime:
        return self.utc

    def read(self) -> PaperTimeReading:
        return PaperTimeReading(self.utc, self.elapsed)

    def advance(self, seconds: float) -> None:
        self.utc += timedelta(seconds=seconds)
        self.elapsed += seconds


@dataclass(slots=True)
class Entry:
    """One entry order that has been prepared, approved, issued, previewed and authorized."""

    intent_id: str
    proposal_id: str
    symbol: str
    attempt_id: str
    snapshot_id: str


class Matrix:
    """The whole stack, rebuilt from durable state on demand (`restart`)."""

    def __init__(self, engine_b: Engine, engine_c: Engine, tmp_path: Path) -> None:
        from tests.integration._m085_support import truncate_all
        from tests.integration._m089_support import truncate_all_c

        truncate_all(engine_b)
        truncate_all_c(engine_c)
        with engine_b.begin() as connection:
            for table in EXTRA_B_TABLES:
                connection.execute(text(f"TRUNCATE public.{table}"))  # noqa: S608 - fixed names
        self.engine_b = engine_b
        self.engine_c = engine_c
        self.clock = MatrixClock()
        self.store = SimulationStore(tmp_path / "broker.json")
        self.broker = SimulatedPaperBroker(self.store, clock=self.clock)
        self.market = SimulatedMarketData(self.store, clock=self.clock)
        self._counter = 0
        self._extra_quotes: dict[str, tuple[str, str]] = {}
        self._configuration_saved = False
        self._open_services()

    # -- lifecycle -------------------------------------------------------------------------
    def _open_services(self) -> None:
        self.service_b = PostgresPersistenceService(config("m100-matrix-b"))
        self.service_b.initialize()
        self.service_c = PostgresPersistenceService(store_c_config("m100-matrix-c"))
        self.service_c.initialize()
        self.m084 = PostgresRepositoryRuntime(self.service_b)
        self.paper = PostgresPaperExecutionRuntime(self.service_b)
        self.exit_rt = PostgresPositionExitRuntime(self.service_c)
        self.plans = PostgresApprovedPlanRepository(self.service_b)
        self.closures = PostgresExternalPositionClosureRepository(self.service_c)

    def close(self) -> None:
        self.service_c.close()
        self.service_b.close()

    def restart(self) -> None:
        """A brand-new process: every connection, repository and handler is rebuilt. Only the
        databases and the (durable) simulated broker survive."""
        self.close()
        self._open_services()

    # -- broker staging ----------------------------------------------------------------------
    def stage(
        self,
        symbol: str = "AAPL",
        *,
        entry: SimulationScenario = SimulationScenario.ACCEPTED_THEN_FILLED,
        exit_: SimulationExitScenario = SimulationExitScenario.EXIT_FILLED,
        quote: tuple[str, str] = QUOTE,
        extra_quotes: dict[str, tuple[str, str]] | None = None,
    ) -> None:
        scenarios = dict(self.store.scenarios())
        exits = dict(self.store.exit_scenarios())
        quotes = {s: self.store.quote_for(s) for s in scenarios if self.store.quote_for(s)}
        scenarios[symbol] = entry
        exits[symbol] = exit_
        quotes[symbol] = quote
        self._extra_quotes.update(extra_quotes or {})
        quotes.update(self._extra_quotes)
        self.store.stage(
            scenarios={k: SimulationScenario(v) for k, v in scenarios.items()},
            quotes={k: v for k, v in quotes.items() if v is not None},
            exit_scenarios={k: SimulationExitScenario(v) for k, v in exits.items()},
        )

    # -- the entry chain -----------------------------------------------------------------------
    def governed_configuration(self, **overrides: object) -> object:
        configuration = replace(
            a_configuration(
                configuration_governance_id="CFG-100-0001",
                permitted_order_types=(a_configuration().default_order_type,),
                **overrides,
            ),
            risk_contract_version=2,
            maximum_position_quantity_shares=5,
            maximum_planned_loss_per_trade=Decimal("200"),
        )
        return configuration

    def entry(self, symbol: str = "AAPL") -> Entry:
        """prepare -> approve -> issue -> preview -> authorize, every step through its real
        Paper-bound command at the current schema head, ending with an authorization ready to
        submit. Nothing has been sent to the broker."""
        self._counter += 1
        n = self._counter
        proposal_id, intent_id = f"PRP-100-{n:04d}", f"INT-100-{n:04d}"
        context_id, watermark_id = f"ECX-100-{n:04d}", f"WM-100-{n:04d}"
        if not self._configuration_saved:
            SaveOperatorTradingConfigurationHandler(
                configuration_repository=self.m084.operator_trading_configurations
            ).handle(SaveOperatorTradingConfigurationCommand(self.governed_configuration()))  # type: ignore[arg-type]
            self._configuration_saved = True
        configuration = self.m084.operator_trading_configurations.latest("CFG-100-0001")
        assert configuration is not None
        context = a_context(
            self.m084, configuration, context_id=context_id, watermark_id=watermark_id
        )
        self.m084.evaluation_contexts.save(context)
        observed_at = self.clock.read().utc - timedelta(seconds=5)
        prepared = PreparePaperBoundTradeProposalHandler(
            configurations=self.m084.operator_trading_configurations,
            contexts=self.m084.evaluation_contexts,
            proposals=self.m084.trade_proposals,
            time_bases=self.paper.time_bases,
            broker=self.broker,
            time_source=self.clock,
        ).handle(
            PreparePaperBoundTradeProposalCommand(
                proposal_governance_id=proposal_id,
                evaluation_context_id=context.evaluation_context_id,
                symbol=symbol,
                **paper_bound_market_inputs(symbol=symbol, observed_at=observed_at),  # type: ignore[arg-type]
            )
        )
        assert prepared.outcome.proposal is not None, prepared.outcome.no_trade_reason
        from empirical_platform.decision_candidate.trade_approval import OperatorAction

        DecidePaperBoundTradeProposalHandler(
            configurations=self.m084.operator_trading_configurations,
            decisions=self.m084.approval_decisions,
            proposals=self.m084.trade_proposals,
            time_bases=self.paper.time_bases,
            broker=self.broker,
            time_source=self.clock,
        ).handle(
            DecidePaperBoundTradeProposalCommand(
                proposal_governance_id=proposal_id,
                decision_governance_id=f"DEC-{proposal_id}",
                action=OperatorAction.APPROVE,
                operator_identity="owner",
            )
        )
        IssuePaperBoundOrderIntentHandler(
            approval_decisions=self.m084.approval_decisions,
            intents=self.m084.approved_order_intents,
            proposals=self.m084.trade_proposals,
            time_bases=self.paper.time_bases,
            broker=self.broker,
            time_source=self.clock,
        ).handle(
            IssuePaperBoundOrderIntentCommand(
                intent_governance_id=intent_id,
                proposal_governance_id=proposal_id,
                idempotency_key=f"IDEM-{intent_id}",
            )
        )
        preview = PreviewPaperSubmissionHandler(
            intents=self.m084.approved_order_intents,
            configurations=self.m084.operator_trading_configurations,
            time_bases=self.paper.time_bases,
            snapshots=self.paper.paper_account_snapshots,
            previews=self.paper.submission_previews,
            events=self.paper.paper_execution_events,
            broker=self.broker,
            market_data=self.market,
            kill_switch=self.paper.execution_kill_switch,
            time_source=self.clock,
        ).handle(
            PreviewPaperSubmissionCommand(
                intent_governance_id=intent_id,
                preview_id=f"PVW-100-{n:04d}",
                account_snapshot_id=f"SNP-PRE-{n:04d}",
                created_at=self.clock.utc,
            )
        )
        assert preview.is_authorizable, preview.refusals
        AuthorizePaperSubmissionHandler(
            previews=self.paper.submission_previews,
            authorizations=self.paper.execution_authorizations,
            events=self.paper.paper_execution_events,
            broker=self.broker,
            time_source=self.clock,
        ).handle(
            AuthorizePaperSubmissionCommand(
                authorization_id=f"AUT-100-{n:04d}",
                preview_id=preview.preview_id,
                expected_request_fingerprint=preview.request_fingerprint,
                authorized_by="owner",
                authorized_at=self.clock.utc,
                validity_seconds=60,
            )
        )
        return Entry(intent_id, proposal_id, symbol, f"ATT-100-{n:04d}", f"SNP-SND-{n:04d}")

    def submit_handler(self) -> SubmitAuthorizedPaperOrderHandler:
        return SubmitAuthorizedPaperOrderHandler(
            intents=self.m084.approved_order_intents,
            configurations=self.m084.operator_trading_configurations,
            time_bases=self.paper.time_bases,
            previews=self.paper.submission_previews,
            authorizations=self.paper.execution_authorizations,
            attempts=self.paper.execution_attempts,
            acknowledgements=self.paper.broker_acknowledgements,
            events=self.paper.paper_execution_events,
            snapshots=self.paper.paper_account_snapshots,
            broker=self.broker,
            market_data=self.market,
            kill_switch=self.paper.execution_kill_switch,
            time_source=self.clock,
        )

    def submit(self, entry: Entry, *, snapshot_id: str | None = None) -> object:
        return self.submit_handler().handle(
            SubmitAuthorizedPaperOrderCommand(
                intent_governance_id=entry.intent_id,
                attempt_id=entry.attempt_id,
                account_snapshot_id=snapshot_id or entry.snapshot_id,
                at=self.clock.utc,
            )
        )

    def reconcile(self, entry: Entry) -> object:
        return ReconcilePaperOrderHandler(
            attempts=self.paper.execution_attempts,
            acknowledgements=self.paper.broker_acknowledgements,
            events=self.paper.paper_execution_events,
            broker=self.broker,
            authorizations=self.paper.execution_authorizations,
            previews=self.paper.submission_previews,
            rounds=self.paper.reconciliation_rounds,
            time_source=self.clock,
        ).handle(
            ReconcilePaperOrderCommand(intent_governance_id=entry.intent_id, at=self.clock.utc)
        )

    def open_position(self, symbol: str = "AAPL") -> Entry:
        """A fully filled entry, reached through submit + reconcile on PostgreSQL."""
        self.stage(symbol)
        entry = self.entry(symbol)
        self.submit(entry)
        for _ in range(3):
            self.clock.advance(5)
            self.reconcile(entry)
            attempt = self.paper.execution_attempts.for_intent(entry.intent_id)
            if attempt is not None and attempt.state is PaperExecutionState.FILLED:
                return entry
        raise AssertionError("the entry did not fill")

    # -- exits ---------------------------------------------------------------------------------
    def plan(self, entry: Entry, *, stop: str = "230", target: str = "260") -> ApprovedPlan:
        plan_id = f"PLAN-{entry.intent_id}"
        owner = f"OWN-{entry.intent_id}"
        return self.plans.save(
            ApprovedPlan(
                plan_id=plan_id,
                candidate_id="CAND-100",
                entry_intent_governance_id=entry.intent_id,
                symbol=entry.symbol,
                approved_quantity=Decimal(self.store.position(entry.symbol)),
                stop_price=Decimal(stop),
                target_price=Decimal(target),
                mandatory_liquidation_at=self.clock.utc + timedelta(hours=2),
                owner_approval_id=owner,
                system_identity=derive_system_identity(plan_id=plan_id, owner_approval_id=owner),
                created_at=self.clock.utc,
            )
        )

    def manager(self) -> PositionPlanManager:
        return PositionPlanManager(
            plans=self.plans,
            external_closures=self.closures,
            intents=self.m084.approved_order_intents,
            entry_attempts=self.paper.execution_attempts,
            exit_attempts=self.exit_rt.attempts,
            previews=self.exit_rt.previews,
            authorizations=self.exit_rt.authorizations,
            acknowledgements=self.exit_rt.acknowledgements,
            events=self.exit_rt.events,
            rounds=self.exit_rt.rounds,
            broker=self.broker,
            market_data=self.market,
            configurations=self.m084.operator_trading_configurations,
            environment="PAPER",
            time_source=self.clock,
            entry_kill_switch=self.paper.execution_kill_switch,
        )

    def breach_stop(self, symbol: str = "AAPL", bid: str = "229.00") -> None:
        self.stage(
            symbol,
            entry=SimulationScenario(self.store.scenarios().get(symbol, "ACCEPTED_THEN_FILLED")),
            exit_=SimulationExitScenario(self.store.exit_scenarios().get(symbol, "EXIT_FILLED")),
            quote=(bid, f"{float(bid) + 0.10:.2f}"),
        )

    def set_exit(self, scenario: SimulationExitScenario, symbol: str = "AAPL") -> None:
        quote = self.store.quote_for(symbol) or QUOTE
        self.stage(
            symbol,
            entry=SimulationScenario(self.store.scenarios().get(symbol, "ACCEPTED_THEN_FILLED")),
            exit_=scenario,
            quote=quote,
        )

    # -- observation -----------------------------------------------------------------------------
    def sells(self) -> list[object]:
        return [o for o in self.store.orders() if o.side == "sell"]

    def buys(self) -> list[object]:
        return [o for o in self.store.orders() if o.side == "buy"]

    def count(self, table: str, engine: Engine | None = None) -> int:
        with (engine or self.engine_b).connect() as connection:
            return int(
                connection.execute(text(f"SELECT count(*) FROM public.{table}")).scalar_one()  # noqa: S608 - fixed names
            )


def iterate(items: Iterator[object]) -> list[object]:
    return list(items)
