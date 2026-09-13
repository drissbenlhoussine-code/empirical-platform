"""M085 time boundaries through real PostgreSQL; all broker I/O is controlled."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Event
from time import monotonic
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from tests.integration._m085_support import (
    EVALUATED_AT,
    an_approved_intent,
    build_engine,
    config,
    truncate_all,
)
from tests.unit._m085_fakes import FakeBroker

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
        intent = an_approved_intent(m084)
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
        preview = PreviewPaperSubmissionHandler(
            intents=m084.approved_order_intents,
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
                approved_watchlist=frozenset({"AAPL"}),
                maximum_notional=Decimal("100000"),
                quote_maximum_age_seconds=60,
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
            approved_watchlist=frozenset({"AAPL"}),
            maximum_notional=Decimal("100000"),
            quote_maximum_age_seconds=60,
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
