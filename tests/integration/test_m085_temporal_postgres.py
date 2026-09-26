"""M085 time boundaries through real PostgreSQL; all broker I/O is controlled."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from time import monotonic
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from tests.integration._m085_support import (
    EVALUATED_AT,
    a_paper_bound_intent,
    build_engine,
    config,
    truncate_all,
)
from tests.unit._m085_fakes import FakeBroker, FakeView

from empirical_platform.decision_candidate.paper_execution import PaperExecutionState
from empirical_platform.shared.brokerage.paper_time import PaperTimeReading
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.paper_execution_repositories import (  # noqa: E501
    PostgresExecutionAttemptRepository,
    PostgresPaperExecutionRuntime,
)
from empirical_platform.shared.persistence.postgres_repositories.runtime import (
    PostgresRepositoryRuntime,
)
from empirical_platform.usecases.paper_execution import (
    AuthorizePaperSubmissionCommand,
    AuthorizePaperSubmissionHandler,
    PreviewPaperSubmissionCommand,
    PreviewPaperSubmissionHandler,
    ReconcilePaperOrderCommand,
    ReconcilePaperOrderHandler,
    SubmitAuthorizedPaperOrderCommand,
    SubmitAuthorizedPaperOrderHandler,
)

pytestmark = pytest.mark.integration


class Clock:
    def __init__(self) -> None:
        self.utc = EVALUATED_AT + timedelta(seconds=25)
        self.elapsed = 0.0

    def advance(self, seconds: float) -> None:
        self.utc += timedelta(seconds=seconds)
        self.elapsed += seconds

    def read(self) -> PaperTimeReading:
        return PaperTimeReading(self.utc, self.elapsed)


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    yield from build_engine()


@pytest.fixture
def world(engine: Engine) -> Iterator[dict[str, Any]]:
    truncate_all(engine)
    service = PostgresPersistenceService(config("m085-temporal"))
    service.initialize()
    try:
        m084 = PostgresRepositoryRuntime(service)
        paper = PostgresPaperExecutionRuntime(service)
        clock = Clock()

        class Broker(FakeBroker):
            def fetch_clock(self) -> SimpleNamespace:
                return SimpleNamespace(
                    timestamp=clock.utc,
                    is_open=True,
                    next_open=None,
                    next_close=EVALUATED_AT + timedelta(hours=3),
                )

        class MarketData:
            def fetch_quote(self, symbol: str) -> SimpleNamespace:
                return SimpleNamespace(
                    bid="199.95", ask="200", captured_at=clock.utc, source="controlled"
                )

        broker = Broker()
        data = MarketData()
        # Issued through the Paper-bound command, so the intent-time basis is
        # MEASURED against the controlled clock rather than written by the fixture.
        intent = a_paper_bound_intent(m084, paper, broker=broker, time_source=clock)
        preview = PreviewPaperSubmissionHandler(
            intents=m084.approved_order_intents,
            configurations=m084.operator_trading_configurations,
            time_bases=paper.time_bases,
            snapshots=paper.paper_account_snapshots,
            previews=paper.submission_previews,
            events=paper.paper_execution_events,
            broker=broker,
            market_data=data,
            kill_switch=paper.execution_kill_switch,
            time_source=clock,
        ).handle(
            PreviewPaperSubmissionCommand(
                intent_governance_id=intent.intent_governance_id,
                preview_id="PVW-TIME",
                account_snapshot_id="SNP-TIME",
                created_at=clock.utc,
            )
        )
        assert preview.is_authorizable, preview.refusals
        authorization = AuthorizePaperSubmissionHandler(
            previews=paper.submission_previews,
            authorizations=paper.execution_authorizations,
            events=paper.paper_execution_events,
            broker=broker,
            time_source=clock,
        ).handle(
            AuthorizePaperSubmissionCommand(
                authorization_id="AUT-TIME",
                preview_id=preview.preview_id,
                expected_request_fingerprint=preview.request_fingerprint,
                authorized_by="test-fixture",
                authorized_at=clock.utc,
                validity_seconds=5,
            )
        )
        command = SubmitAuthorizedPaperOrderCommand(
            intent_governance_id=intent.intent_governance_id,
            attempt_id="ATT-TIME",
            account_snapshot_id="SNP-SEND",
            at=clock.utc,
        )
        yield dict(
            service=service,
            m084=m084,
            paper=paper,
            clock=clock,
            broker=broker,
            data=data,
            authorization=authorization,
            command=command,
        )
    finally:
        service.close()


def handler(
    world: dict[str, Any], attempts: PostgresExecutionAttemptRepository | None = None
) -> SubmitAuthorizedPaperOrderHandler:
    paper = world["paper"]
    return SubmitAuthorizedPaperOrderHandler(
        intents=world["m084"].approved_order_intents,
        configurations=world["m084"].operator_trading_configurations,
        time_bases=paper.time_bases,
        previews=paper.submission_previews,
        authorizations=paper.execution_authorizations,
        attempts=attempts or paper.execution_attempts,
        acknowledgements=paper.broker_acknowledgements,
        events=paper.paper_execution_events,
        snapshots=paper.paper_account_snapshots,
        broker=world["broker"],
        market_data=world["data"],
        kill_switch=paper.execution_kill_switch,
        time_source=world["clock"],
    )


def test_real_row_lock_wait_cannot_consume_expired_permission(
    world: dict[str, Any], engine: Engine
) -> None:
    reached = Event()

    class Attempts(PostgresExecutionAttemptRepository):
        def claim_dispatch(self, **kwargs: object) -> object:
            reached.set()
            return super().claim_dispatch(**kwargs)

    with engine.connect() as blocker:
        transaction = blocker.begin()
        blocker.execute(
            text(
                "SELECT authorization_id FROM paper_execution_authorization "
                "WHERE authorization_id = 'AUT-TIME' FOR UPDATE"
            )
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                handler(world, Attempts(world["service"])).handle, world["command"]
            )
            try:
                assert reached.wait(5), "worker did not reach claim"
                deadline = monotonic() + 5
                observed_wait = False
                while monotonic() < deadline:
                    with engine.connect() as observer:
                        observed_wait = bool(
                            observer.execute(
                                text(
                                    "SELECT count(*) FROM pg_stat_activity "
                                    "WHERE application_name = 'm085-temporal' "
                                    "AND wait_event_type = 'Lock'"
                                )
                            ).scalar_one()
                        )
                    if observed_wait:
                        break
                    Event().wait(0.01)
                assert observed_wait, "no actual PostgreSQL row-lock wait observed"
                world["clock"].advance(6)
            finally:
                transaction.rollback()
            with pytest.raises(ValueError, match="expired"):
                future.result(timeout=5)
    paper = world["paper"]
    assert not paper.execution_authorizations.get("AUT-TIME").is_consumed
    assert paper.execution_attempts.get("ATT-TIME") is None
    assert world["broker"].submitted == []


def test_post_claim_delay_is_terminal_and_never_resubmits(world: dict[str, Any]) -> None:
    class Attempts(PostgresExecutionAttemptRepository):
        def transition(self, **kwargs: object) -> object:
            result = super().transition(**kwargs)
            if kwargs["target"] is PaperExecutionState.SUBMISSION_IN_PROGRESS:
                world["clock"].advance(6)
            return result

    operation = handler(world, Attempts(world["service"]))
    result = operation.handle(world["command"])
    assert not result.dispatched
    assert result.attempt.state is PaperExecutionState.REJECTED
    assert "expired" in result.attempt.failure_detail
    assert world["paper"].execution_authorizations.get("AUT-TIME").is_consumed
    assert not operation.handle(world["command"]).dispatched
    assert world["broker"].submitted == []


def test_current_permission_dispatches_once_to_controlled_broker(world: dict[str, Any]) -> None:
    operation = handler(world)
    result = operation.handle(world["command"])
    assert result.dispatched
    assert result.attempt.client_order_id == world["authorization"].client_order_id
    assert not operation.handle(world["command"]).dispatched
    assert len(world["broker"].submitted) == 1


# ---------------------------------------------------------------------------
# Corrective pass: uncertain outcomes through the real database edges
# ---------------------------------------------------------------------------


def _reconcile(world: dict[str, Any]) -> object:
    paper = world["paper"]
    return ReconcilePaperOrderHandler(
        attempts=paper.execution_attempts,
        acknowledgements=paper.broker_acknowledgements,
        events=paper.paper_execution_events,
        broker=world["broker"],
        authorizations=paper.execution_authorizations,
        previews=paper.submission_previews,
    ).handle(
        ReconcilePaperOrderCommand(
            intent_governance_id=world["command"].intent_governance_id, at=world["clock"].utc
        )
    )


def _our_order_as_the_broker_reports_it(
    world: dict[str, Any], *, client_order_id: str, **fields: object
) -> FakeView:
    """The AUTHORIZED order, as the broker would echo it.

    IDENTITY-SAFETY CORRECTION (F1): a found order is adopted only when it equals the
    authorized order field by field, so a scripted lookup answer must describe THAT
    order -- the fixture's defaults describe the unit-test intent, not this world's.
    """
    authorization = world["authorization"]
    described: dict[str, object] = {
        "client_order_id": client_order_id,
        "symbol": authorization.symbol,
        "side": authorization.side.lower(),
        "quantity": str(authorization.quantity),
        "order_type": authorization.order_type.value.lower(),
        "limit_price": (
            None if authorization.limit_price is None else str(authorization.limit_price)
        ),
    }
    described.update(fields)
    return FakeView(**described)


def test_a_server_error_is_stored_as_unknown_and_never_resent(world: dict[str, Any]) -> None:
    # D2 AT THE DATABASE. A 503 after the POST is recorded as said, the attempt is
    # SUBMISSION_UNKNOWN in the real table, and neither a repeat nor the database
    # permits a second submission.
    world["broker"].submit_status = 503
    world["broker"].submit_body = '{"message": "service unavailable"}'
    operation = handler(world)
    first = operation.handle(world["command"])
    assert first.attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN
    paper = world["paper"]
    stored = paper.execution_attempts.get("ATT-TIME")
    assert stored is not None and stored.state is PaperExecutionState.SUBMISSION_UNKNOWN
    (acknowledgement,) = paper.broker_acknowledgements.for_attempt("ATT-TIME")
    assert acknowledgement.http_status == 503
    assert not operation.handle(world["command"]).dispatched
    assert len(world["broker"].submitted) == 1


def test_reconciliation_resolves_an_unknown_attempt_through_the_database_edges(
    world: dict[str, Any],
) -> None:
    world["broker"].submit_status = 502
    world["broker"].submit_body = "<html>Bad Gateway</html>"
    unknown = handler(world).handle(world["command"]).attempt
    world["broker"].lookup_view = _our_order_as_the_broker_reports_it(
        world, client_order_id=unknown.client_order_id, status="filled"
    )
    resolved = _reconcile(world)
    assert resolved.state is PaperExecutionState.FILLED  # type: ignore[attr-defined]
    stored = world["paper"].execution_attempts.get("ATT-TIME")
    assert stored is not None and stored.state is PaperExecutionState.FILLED
    assert stored.submitted_at == unknown.submitted_at
    # Terminal now: a further reconciliation neither asks nor writes.
    world["broker"].lookups.clear()
    assert _reconcile(world).state is PaperExecutionState.FILLED  # type: ignore[attr-defined]
    assert world["broker"].lookups == []
    assert len(world["broker"].submitted) == 1


def test_reconciliation_resolves_an_interrupted_dispatch_through_the_database_edges(
    world: dict[str, Any],
) -> None:
    # D3 AT THE DATABASE. A dispatch interrupted AFTER THE REQUEST LEFT stays
    # SUBMISSION_IN_PROGRESS in the real table. Once the not-found window has passed,
    # reconciliation finds the order by client_order_id and records it through
    # PAPER_SUBMITTED, because the trigger refuses SUBMISSION_IN_PROGRESS -> FILLED.
    # CRASH-CONSISTENT LINEAGE (L1): the interruption must come after the send -- the fake
    # broker receives the order and then raises -- because a dispatch interrupted BEFORE
    # the send-capable boundary has no lineage and is never attributed a found order
    # (`test_m085_pre_send_crash_postgres.py`). This test used to replace `submit_order`
    # wholesale, i.e. die before any send, and asserted adoption: that was the L1 gap.
    world["broker"].submit_raises = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        handler(world).handle(world["command"])
    world["broker"].submit_raises = None
    assert len(world["broker"].submitted) == 1
    stuck = world["paper"].execution_attempts.get("ATT-TIME")
    assert stuck is not None and stuck.state is PaperExecutionState.SUBMISSION_IN_PROGRESS
    world["broker"].lookup_view = _our_order_as_the_broker_reports_it(
        world, client_order_id=stuck.client_order_id, status="filled"
    )
    world["clock"].advance(120)
    resolved = _reconcile(world)
    assert resolved.state is PaperExecutionState.FILLED  # type: ignore[attr-defined]
    stored = world["paper"].execution_attempts.get("ATT-TIME")
    assert stored is not None and stored.state is PaperExecutionState.FILLED
    assert world["broker"].lookups[-1] == stuck.client_order_id
    assert len(world["broker"].submitted) == 1, "recovery never resends"


def test_absence_never_resolves_an_interrupted_dispatch_in_the_database(
    world: dict[str, Any],
) -> None:
    # Not-found answers across the whole policy window leave SUBMISSION_IN_PROGRESS
    # stored as it was: the dispatcher may not have sent yet, so nothing is resolved.
    def interrupted(*args: object, **kwargs: object) -> object:
        raise KeyboardInterrupt

    world["broker"].submit_order = interrupted
    with pytest.raises(KeyboardInterrupt):
        handler(world).handle(world["command"])
    world["broker"].lookup_status = 404
    world["broker"].lookup_view = None
    for _ in range(3):
        world["clock"].advance(120)
        assert _reconcile(world).state is PaperExecutionState.SUBMISSION_IN_PROGRESS  # type: ignore[attr-defined]
    stored = world["paper"].execution_attempts.get("ATT-TIME")
    assert stored is not None and stored.state is PaperExecutionState.SUBMISSION_IN_PROGRESS
    assert len(world["broker"].lookups) == 3
    assert world["broker"].submitted == []
