"""IDENTITY-SAFETY CORRECTION (F1) and crash/restart recovery, against real PostgreSQL.

Production handlers over the real repositories, a controlled broker fake, and a real
database that is rebuilt from the complete migration history. Two sequences are proved
end to end:

  1. the broker may have accepted the order -> the local answer is missing or ambiguous
     -> the process terminates -> a NEW process starts over the same database
     -> SUBMISSION_UNKNOWN / SUBMISSION_IN_PROGRESS is recovered by a broker lookup on
     the same client_order_id -> nothing is resent;

  2. the local database is lost and rebuilt (the same intent, preview and authorization
     derive the same client_order_id) -> the broker still holds the earlier order
     -> a new dispatch attempt -> no second broker order -> an exact match is adopted by
     identity reconciliation; a different order under the identity is a recorded
     collision that an operator must resolve.

No external Alpaca order is placed; the broker is `FakeBroker`, which receives orders
and answers lookups about exactly what it received.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.engine import Engine
from tests.integration._m085_support import (
    EVALUATED_AT,
    a_paper_bound_intent,
    build_engine,
    config,
    truncate_all,
)
from tests.integration.test_m085_temporal_postgres import Clock
from tests.unit._m085_fakes import FakeBroker, FakeView

from empirical_platform.decision_candidate.paper_execution import (
    ExecutionAuthorization,
    PaperExecutionState,
)
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.paper_execution_repositories import (  # noqa: E501
    PostgresPaperExecutionRuntime,
)
from empirical_platform.shared.persistence.postgres_repositories.runtime import (
    PostgresRepositoryRuntime,
)
from empirical_platform.usecases.paper_execution import (
    AuthorizePaperSubmissionCommand,
    AuthorizePaperSubmissionHandler,
    ExecutionAttempt,
    PaperSubmissionResult,
    PreviewPaperSubmissionCommand,
    PreviewPaperSubmissionHandler,
    ReconcilePaperOrderCommand,
    ReconcilePaperOrderHandler,
    SubmitAuthorizedPaperOrderCommand,
    SubmitAuthorizedPaperOrderHandler,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    yield from build_engine()


class _Crash(BaseException):
    """The process dies after the request left and before anything was recorded."""


def _authorized_order_as_the_broker_reports_it(
    authorization: ExecutionAuthorization, **fields: object
) -> FakeView:
    """The authorized order, as the broker would echo it (every term), for scripted lookups."""
    described: dict[str, object] = {
        "client_order_id": authorization.client_order_id,
        "symbol": authorization.symbol,
        "side": authorization.side.lower(),
        "quantity": str(authorization.quantity),
        "order_type": authorization.order_type.value.lower(),
        "limit_price": None
        if authorization.limit_price is None
        else str(authorization.limit_price),
        "time_in_force": "day",
        "extended_hours": False,
    }
    described.update(fields)
    return FakeView(**described)


class _Broker(FakeBroker):
    def __init__(self, clock: Clock) -> None:
        super().__init__()
        self._clock = clock

    def fetch_clock(self) -> SimpleNamespace:
        return SimpleNamespace(
            timestamp=self._clock.utc,
            is_open=True,
            next_open=None,
            next_close=EVALUATED_AT + timedelta(hours=3),
        )


class _MarketData:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    def fetch_quote(self, symbol: str) -> SimpleNamespace:
        del symbol
        return SimpleNamespace(
            bid="199.95", ask="200", captured_at=self._clock.utc, source="controlled"
        )


class _Process:
    """One process: its own persistence service and handler instances over the shared database."""

    def __init__(self, name: str, clock: Clock, broker: _Broker, data: _MarketData) -> None:
        self.service = PostgresPersistenceService(config(f"m085-identity-{name}"))
        self.service.initialize()
        self.m084 = PostgresRepositoryRuntime(self.service)
        self.paper = PostgresPaperExecutionRuntime(self.service)
        self.clock = clock
        self.broker = broker
        self.data = data

    def close(self) -> None:
        self.service.close()

    def authorize(self, *, suffix: str) -> tuple[str, Any]:
        intent = a_paper_bound_intent(
            self.m084, self.paper, broker=self.broker, time_source=self.clock
        )
        preview = PreviewPaperSubmissionHandler(
            intents=self.m084.approved_order_intents,
            configurations=self.m084.operator_trading_configurations,
            time_bases=self.paper.time_bases,
            snapshots=self.paper.paper_account_snapshots,
            previews=self.paper.submission_previews,
            events=self.paper.paper_execution_events,
            broker=self.broker,
            market_data=self.data,
            kill_switch=self.paper.execution_kill_switch,
            time_source=self.clock,
        ).handle(
            PreviewPaperSubmissionCommand(
                intent_governance_id=intent.intent_governance_id,
                preview_id=f"PVW-ID-{suffix}",
                account_snapshot_id=f"SNP-ID-{suffix}",
                created_at=self.clock.utc,
            )
        )
        assert preview.is_authorizable, preview.refusals
        authorization = AuthorizePaperSubmissionHandler(
            previews=self.paper.submission_previews,
            authorizations=self.paper.execution_authorizations,
            events=self.paper.paper_execution_events,
            broker=self.broker,
            time_source=self.clock,
        ).handle(
            AuthorizePaperSubmissionCommand(
                authorization_id=f"AUT-ID-{suffix}",
                preview_id=preview.preview_id,
                expected_request_fingerprint=preview.request_fingerprint,
                authorized_by="test-fixture",
                authorized_at=self.clock.utc,
                validity_seconds=300,
            )
        )
        return intent.intent_governance_id, authorization

    def submit(self, intent_id: str, *, attempt_id: str) -> PaperSubmissionResult:
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
            market_data=self.data,
            kill_switch=self.paper.execution_kill_switch,
            time_source=self.clock,
        ).handle(
            SubmitAuthorizedPaperOrderCommand(
                intent_governance_id=intent_id,
                attempt_id=attempt_id,
                account_snapshot_id=f"SNP-SEND-{attempt_id}",
                at=self.clock.utc,
            )
        )

    def reconcile(self, intent_id: str) -> ExecutionAttempt:
        return ReconcilePaperOrderHandler(
            attempts=self.paper.execution_attempts,
            acknowledgements=self.paper.broker_acknowledgements,
            events=self.paper.paper_execution_events,
            broker=self.broker,
            authorizations=self.paper.execution_authorizations,
            previews=self.paper.submission_previews,
            rounds=self.paper.reconciliation_rounds,
            time_source=self.clock,
        ).handle(ReconcilePaperOrderCommand(intent_governance_id=intent_id, at=self.clock.utc))

    def events(self, intent_id: str) -> list[str]:
        return [e.event_type for e in self.paper.paper_execution_events.for_intent(intent_id)]


@pytest.fixture
def world(engine: Engine) -> Iterator[dict[str, Any]]:
    truncate_all(engine)
    clock = Clock()
    broker = _Broker(clock)
    data = _MarketData(clock)
    processes: list[_Process] = []

    def spawn(name: str) -> _Process:
        process = _Process(name, clock, broker, data)
        processes.append(process)
        return process

    try:
        yield {"engine": engine, "clock": clock, "broker": broker, "spawn": spawn}
    finally:
        for process in processes:
            process.close()


# ---------------------------------------------------------------------------
# 1. crash / ambiguity, then a new process recovers through the same identity
# ---------------------------------------------------------------------------


def test_an_ambiguous_answer_then_a_new_process_recovers_the_order_without_resending(
    world: dict[str, Any],
) -> None:
    a = world["spawn"]("a")
    intent_id, authorization = a.authorize(suffix="1")
    broker = world["broker"]
    broker.submit_status = 503
    broker.submit_body = '{"code": 50310000, "message": "unavailable"}'
    first = a.submit(intent_id, attempt_id="ATT-ID-1")
    assert first.attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN
    assert len(broker.submitted) == 1
    a.close()  # the process terminates

    b = world["spawn"]("b")
    stored = b.paper.execution_attempts.for_intent(intent_id)
    assert stored is not None and stored.state is PaperExecutionState.SUBMISSION_UNKNOWN
    broker.submit_status = 200
    assert b.submit(intent_id, attempt_id="ATT-ID-2").dispatched is False
    world["clock"].advance(seconds=5)
    recovered = b.reconcile(intent_id)
    assert recovered.state is PaperExecutionState.PAPER_ACCEPTED
    assert recovered.client_order_id == authorization.client_order_id
    assert broker.lookups[-1] == authorization.client_order_id
    assert len(broker.submitted) == 1


def test_a_crash_after_the_send_then_a_new_process_recovers_in_progress_without_resending(
    world: dict[str, Any],
) -> None:
    a = world["spawn"]("a")
    intent_id, authorization = a.authorize(suffix="1")
    broker = world["broker"]
    broker.submit_raises = _Crash()
    with pytest.raises(_Crash):
        a.submit(intent_id, attempt_id="ATT-ID-1")
    assert len(broker.submitted) == 1
    a.close()

    b = world["spawn"]("b")
    stranded = b.paper.execution_attempts.for_intent(intent_id)
    assert stranded is not None and stranded.state is PaperExecutionState.SUBMISSION_IN_PROGRESS
    broker.submit_raises = None
    assert b.submit(intent_id, attempt_id="ATT-ID-2").dispatched is False
    # Inside the not-found window the live dispatch is left alone; after it, the broker
    # is asked about the SAME identity and the order it holds is adopted.
    world["clock"].advance(seconds=30)
    assert b.reconcile(intent_id).state is PaperExecutionState.SUBMISSION_IN_PROGRESS
    world["clock"].advance(seconds=31)
    recovered = b.reconcile(intent_id)
    assert recovered.state is PaperExecutionState.PAPER_ACCEPTED
    assert recovered.client_order_id == authorization.client_order_id
    assert len(broker.submitted) == 1
    with world["engine"].connect() as connection:
        row = connection.execute(
            text(
                "SELECT state, broker_order_id FROM public.paper_execution_attempt "
                "WHERE intent_governance_id = :i"
            ),
            {"i": intent_id},
        ).one()
    assert (row.state, row.broker_order_id) == ("PAPER_ACCEPTED", "broker-1")


def test_recovery_refuses_a_different_order_found_under_the_identity(world: dict[str, Any]) -> None:
    a = world["spawn"]("a")
    intent_id, authorization = a.authorize(suffix="1")
    broker = world["broker"]
    broker.submit_raises = _Crash()
    with pytest.raises(_Crash):
        a.submit(intent_id, attempt_id="ATT-ID-1")
    a.close()

    b = world["spawn"]("b")
    broker.submit_raises = None
    broker.lookup_view = FakeView(client_order_id=authorization.client_order_id, symbol="TSLA")
    world["clock"].advance(seconds=61)
    result = b.reconcile(intent_id)
    assert result.state is PaperExecutionState.SUBMISSION_IN_PROGRESS
    assert result.broker_order_id is None
    assert "IDENTITY_COLLISION_MISMATCH" in b.events(intent_id)
    assert b.submit(intent_id, attempt_id="ATT-ID-2").dispatched is False
    assert len(broker.submitted) == 1


# ---------------------------------------------------------------------------
# 2. the database is lost; the broker still holds the order under the same identity
# ---------------------------------------------------------------------------


def test_a_rebuilt_database_observes_the_brokers_order_without_attributing_or_sending(
    world: dict[str, Any],
) -> None:
    # Observing is not attributing. Process A dispatched; its database is lost; process B
    # rebuilds the same identity. The broker still holds A's order: B sends nothing, records
    # the order it sees, and does NOT adopt it -- B's attempt did not create it, and nothing
    # in B's database carries A's lineage.
    a = world["spawn"]("a")
    intent_id, authorization = a.authorize(suffix="1")
    first = a.submit(intent_id, attempt_id="ATT-ID-1")
    assert first.dispatched is True
    assert first.attempt.state is PaperExecutionState.PAPER_ACCEPTED
    broker = world["broker"]
    assert len(broker.submitted) == 1
    a.close()

    truncate_all(world["engine"])  # the database is lost; the broker is not
    b = world["spawn"]("b")
    assert b.paper.execution_attempts.for_intent(intent_id) is None
    rebuilt_intent_id, rebuilt_authorization = b.authorize(suffix="1")
    assert rebuilt_intent_id == intent_id
    assert rebuilt_authorization.client_order_id == authorization.client_order_id

    second = b.submit(intent_id, attempt_id="ATT-ID-REBUILT")
    assert len(broker.submitted) == 1, "a second broker order was created"
    assert second.dispatched is False
    assert second.attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN
    assert second.attempt.failure_code == "IDENTITY_EXISTS_UNSENT"
    assert second.attempt.broker_order_id is None, "a historical order was adopted"
    events = b.events(intent_id)
    assert "IDENTITY_OBSERVED_BEFORE_SEND" in events
    assert "IDENTITY_OBSERVED_NOT_ATTRIBUTED" in events
    assert "IDENTITY_RECONCILED_EXACT_MATCH" not in events
    # The broker's order is visible in the acknowledgement the observation recorded.
    acknowledgements = b.paper.broker_acknowledgements.for_attempt("ATT-ID-REBUILT")
    assert any(ack.broker_order_id == first.attempt.broker_order_id for ack in acknowledgements)
    # Reconciliation keeps observing and still does not attribute; nothing is ever resent.
    world["clock"].advance(seconds=120)
    reconciled = b.reconcile(intent_id)
    assert reconciled.state is PaperExecutionState.SUBMISSION_UNKNOWN
    assert reconciled.broker_order_id is None
    assert b.submit(intent_id, attempt_id="ATT-ID-AGAIN").dispatched is False
    assert len(broker.submitted) == 1


def test_a_rebuilt_database_surfaces_a_different_order_under_its_identity_as_a_collision(
    world: dict[str, Any],
) -> None:
    a = world["spawn"]("a")
    intent_id, authorization = a.authorize(suffix="1")
    a.submit(intent_id, attempt_id="ATT-ID-1")
    broker = world["broker"]
    a.close()

    truncate_all(world["engine"])
    broker.lookup_fields = {"quantity": "5"}  # what the broker holds is NOT this order
    b = world["spawn"]("b")
    b.authorize(suffix="1")
    second = b.submit(intent_id, attempt_id="ATT-ID-REBUILT")
    assert len(broker.submitted) == 1
    assert second.dispatched is False
    assert second.attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN
    assert second.attempt.failure_code == "IDENTITY_EXISTS_UNSENT"
    assert second.attempt.broker_order_id is None
    events = b.events(intent_id)
    assert "IDENTITY_OBSERVED_BEFORE_SEND" in events
    assert "IDENTITY_COLLISION_MISMATCH" in events
    assert "IDENTITY_RECONCILED_EXACT_MATCH" not in events
    assert b.submit(intent_id, attempt_id="ATT-ID-AGAIN").dispatched is False
    # The database itself refuses a second attempt for the intent or the identity.
    with pytest.raises(sa.exc.DatabaseError), world["engine"].begin() as connection:
        connection.execute(
            text(
                "INSERT INTO public.paper_execution_attempt (attempt_id, intent_governance_id, "
                "authorization_id, client_order_id, request_fingerprint, state, claimed_at) "
                "VALUES ('ATT-FORGED', :intent, 'AUT-ID-1', :cid, 'fp', 'DISPATCH_CLAIMED', now())"
            ),
            {"intent": intent_id, "cid": authorization.client_order_id},
        )
    assert len(broker.submitted) == 1


def test_a_duplicate_answer_after_the_send_is_observed_and_not_attributed(
    world: dict[str, Any],
) -> None:
    # The broker says the identity already existed when our POST arrived: the order predates
    # our request, so it is not ours. Stored as UNKNOWN with the answer, observed, not adopted.
    a = world["spawn"]("a")
    intent_id, authorization = a.authorize(suffix="1")
    broker = world["broker"]
    broker.lookup_sequence = [(404, None, '{"code": 40410000, "message": "order not found"}')]
    broker.submit_status = 422
    broker.submit_body = '{"code": 40010001, "message": "client_order_id must be unique"}'
    result = a.submit(intent_id, attempt_id="ATT-ID-1")
    assert len(broker.submitted) == 1
    assert result.dispatched is True
    assert result.attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN
    assert result.attempt.failure_code == "IDENTITY_EXISTS_SENT"
    assert result.attempt.broker_order_id is None
    events = a.events(intent_id)
    assert "CLIENT_ORDER_ID_COLLISION" in events
    assert "IDENTITY_OBSERVED_NOT_ATTRIBUTED" in events
    acknowledgements = a.paper.broker_acknowledgements.for_attempt("ATT-ID-1")
    assert [(ack.kind, ack.http_status) for ack in acknowledgements][:2] == [
        ("SUBMIT", 422),
        ("RECONCILE", 200),
    ]
    assert authorization.client_order_id == result.attempt.client_order_id
    # New process: nothing is resent; reconciliation still does not attribute.
    a.close()
    b = world["spawn"]("b")
    assert b.submit(intent_id, attempt_id="ATT-ID-2").dispatched is False
    world["clock"].advance(seconds=120)
    assert b.reconcile(intent_id).state is PaperExecutionState.SUBMISSION_UNKNOWN
    assert len(broker.submitted) == 1


# ---------------------------------------------------------------------------
# 3. an inconclusive identity lookup before the send is recoverable uncertainty
# ---------------------------------------------------------------------------


def test_an_inconclusive_lookup_then_a_restart_surfaces_the_order_without_attribution(
    world: dict[str, Any],
) -> None:
    # The broker already holds an order under the identity, but the first lookup fails.
    # Zero POSTs. A new process asks again, the lookup succeeds, the order is surfaced and
    # recorded, attribution follows the lineage rule (this attempt never sent), no resend.
    a = world["spawn"]("a")
    intent_id, authorization = a.authorize(suffix="1")
    broker = world["broker"]
    broker.lookup_status = 500
    broker.lookup_view = None
    broker.lookup_body = '{"code": 50010000, "message": "internal"}'
    first = a.submit(intent_id, attempt_id="ATT-ID-1")
    assert broker.submitted == [], "a POST left after an inconclusive identity lookup"
    assert first.dispatched is False
    assert first.attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN
    assert first.attempt.failure_code == "IDENTITY_UNRESOLVED_UNSENT"
    assert "IDENTITY_LOOKUP_INCONCLUSIVE" in a.events(intent_id)
    stored = a.paper.execution_attempts.for_intent(intent_id)
    assert stored is not None and stored.state is PaperExecutionState.SUBMISSION_UNKNOWN
    a.close()

    b = world["spawn"]("b")
    broker.lookup_status = 200
    broker.lookup_view = _authorized_order_as_the_broker_reports_it(
        authorization, broker_order_id="broker-old", status="accepted"
    )
    assert b.submit(intent_id, attempt_id="ATT-ID-2").dispatched is False
    world["clock"].advance(seconds=5)
    surfaced = b.reconcile(intent_id)
    assert surfaced.state is PaperExecutionState.SUBMISSION_UNKNOWN
    assert surfaced.broker_order_id is None
    assert "IDENTITY_OBSERVED_NOT_ATTRIBUTED" in b.events(intent_id)
    observed = [
        e
        for e in b.paper.paper_execution_events.for_intent(intent_id)
        if e.event_type == "IDENTITY_OBSERVED_NOT_ATTRIBUTED"
    ]
    assert observed and "broker-old" in observed[-1].detail
    assert broker.submitted == []
    with world["engine"].connect() as connection:
        row = connection.execute(
            text(
                "SELECT state, failure_code, broker_order_id FROM public.paper_execution_attempt "
                "WHERE intent_governance_id = :i"
            ),
            {"i": intent_id},
        ).one()
    assert (row.state, row.failure_code, row.broker_order_id) == (
        "SUBMISSION_UNKNOWN",
        "IDENTITY_UNRESOLVED_UNSENT",
        None,
    )
