"""FIX D1 against a real PostgreSQL: the entry-limit ledger and its atomic count-and-admit.

Opt-in (`EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1`) like every other database test here; it
self-skips otherwise. Real threads and a `threading.Barrier` prove the submitters overlap, so
"exactly K of N admitted" is a measured outcome of the transaction-scoped advisory lock on the
trading day, not luck of scheduling.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.engine import Engine
from tests.integration._m085_support import (
    CHAIN_AT,
    alembic_config,
    config,
    postgres_enabled,
)
from tests.integration.test_m085_concurrency import _broker_clock, a_chain, an_account

from empirical_platform.decision_candidate.paper_execution import (
    PaperExecutionEvent,
    PaperExecutionState,
)
from empirical_platform.decision_candidate.paper_portfolio_limits import (
    ENTRY_ADMITTED_EVENT_TYPE,
    EntryLedgerRow,
    PortfolioEvidence,
    PortfolioEvidenceError,
    PortfolioLimits,
    ledger_counts_order,
    portfolio_limit_refusal,
    trading_day_bounds,
)
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.paper_execution_repositories import (  # noqa: E501
    M085_SCHEMA_HEAD,
    PostgresPaperExecutionRuntime,
)

pytestmark = pytest.mark.integration

DAY_START, DAY_END = trading_day_bounds(CHAIN_AT)


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    if not postgres_enabled():
        pytest.skip("PostgreSQL integration tests require explicit opt-in")
    built = sa.create_engine(config("d1-admission").sqlalchemy_url())
    try:
        yield built
    finally:
        with built.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
        built.dispose()


@pytest.fixture
def paper(engine: Engine) -> Iterator[PostgresPaperExecutionRuntime]:
    from alembic import command as alembic_command

    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    alembic_command.upgrade(alembic_config(), M085_SCHEMA_HEAD)
    service = PostgresPersistenceService(config("d1-admission-service"))
    service.initialize()
    try:
        yield PostgresPaperExecutionRuntime(service)
    finally:
        service.close()


def _claimed_attempts(paper: PostgresPaperExecutionRuntime, count: int) -> list[str]:
    """`count` independent intents, each authorized and CLAIMED (as the handler does before
    `before_send`), so each has a real attempt row to admit."""
    attempt_ids: list[str] = []
    for number in range(count):
        _, authorization = a_chain(
            paper,
            intent_id=f"INT-D1-{number}",
            preview_id=f"PVW-D1-{number}",
            authorization_id=f"AUT-D1-{number}",
            account=an_account(snapshot_id=f"SNP-D1-{number}"),
        )
        claim = paper.execution_attempts.claim_dispatch(
            attempt_id=f"ATT-D1-{number}",
            authorization=authorization,
            request_fingerprint_now=authorization.request_fingerprint,
            account_reference_now=authorization.account_reference,
            broker_clock=_broker_clock,
            claimed_at=CHAIN_AT,
        )
        assert claim.won
        attempt_ids.append(claim.attempt.attempt_id)
    return attempt_ids


def _limits(**overrides: object) -> PortfolioLimits:
    fields: dict[str, object] = {
        "maximum_daily_loss": Decimal("1000"),
        "maximum_daily_order_count": 3,
        "maximum_simultaneous_positions": 50,
        "maximum_deployable_capital": Decimal("1000000"),
    }
    fields.update(overrides)
    return PortfolioLimits(**fields)  # type: ignore[arg-type]


_FLAT = PortfolioEvidence(
    equity=Decimal("100000"),
    last_equity=Decimal("100000"),
    positions=(),
    working_buys=(),
)


def _admit(
    paper: PostgresPaperExecutionRuntime,
    attempt_id: str,
    limits: PortfolioLimits,
    *,
    symbol: str = "AAPL",
    notional: Decimal = Decimal("4"),
) -> str | None:
    def decide(ledger: tuple[EntryLedgerRow, ...]) -> str | None:
        return portfolio_limit_refusal(
            limits=limits,
            portfolio=_FLAT,
            ledger=ledger,
            attempt_id=attempt_id,
            client_order_id=f"coid-{attempt_id}",
            symbol=symbol,
            order_notional=notional,
        )

    return paper.execution_attempts.admit_entry(
        attempt_id=attempt_id,
        day_start=DAY_START,
        day_end=DAY_END,
        at=CHAIN_AT,
        symbol=symbol,
        notional=notional,
        client_order_id=f"coid-{attempt_id}",
        decide=decide,
    )


class TestTheAtomicAdmission:
    def test_n_parallel_submits_against_a_cap_of_k_admit_exactly_k(
        self, paper: PostgresPaperExecutionRuntime
    ) -> None:
        count, cap = 8, 3
        attempt_ids = _claimed_attempts(paper, count)
        # Every claimed-but-unadmitted attempt exists in the ledger while the others decide:
        # they must NOT count each other, or all eight would refuse.
        barrier = threading.Barrier(count, timeout=30)
        limits = _limits(maximum_daily_order_count=cap)

        def worker(attempt_id: str) -> str | None:
            barrier.wait()
            return _admit(paper, attempt_id, limits)

        with ThreadPoolExecutor(max_workers=count) as pool:
            results = list(pool.map(worker, attempt_ids, timeout=120))

        admitted = [r for r in results if r is None]
        refused = [r for r in results if r is not None]
        assert len(admitted) == cap, results
        assert len(refused) == count - cap
        assert all("daily order count limit reached" in message for message in refused)
        ledger = paper.execution_attempts.entry_ledger(day_start=DAY_START, day_end=DAY_END)
        assert len(ledger) == count
        assert sum(1 for row in ledger if row.admitted) == cap
        assert sum(1 for row in ledger if ledger_counts_order(row)) == cap

    def test_a_cap_of_one_admits_exactly_one_of_many(
        self, paper: PostgresPaperExecutionRuntime
    ) -> None:
        count = 6
        attempt_ids = _claimed_attempts(paper, count)
        barrier = threading.Barrier(count, timeout=30)
        limits = _limits(maximum_daily_order_count=1)

        def worker(attempt_id: str) -> str | None:
            barrier.wait()
            return _admit(paper, attempt_id, limits)

        with ThreadPoolExecutor(max_workers=count) as pool:
            results = list(pool.map(worker, attempt_ids, timeout=120))
        assert results.count(None) == 1, results

    def test_exposure_is_serialized_too(self, paper: PostgresPaperExecutionRuntime) -> None:
        # 100 USD ceiling, 40 USD each: exactly two fit, however many race.
        count = 6
        attempt_ids = _claimed_attempts(paper, count)
        barrier = threading.Barrier(count, timeout=30)
        limits = _limits(maximum_deployable_capital=Decimal("100"), maximum_daily_order_count=50)

        def worker(attempt_id: str) -> str | None:
            barrier.wait()
            return _admit(paper, attempt_id, limits, notional=Decimal("40"))

        with ThreadPoolExecutor(max_workers=count) as pool:
            results = list(pool.map(worker, attempt_ids, timeout=120))
        assert results.count(None) == 2, results
        assert all("total exposure limit reached" in r for r in results if r is not None)

    def test_admitting_the_same_attempt_twice_is_idempotent(
        self, paper: PostgresPaperExecutionRuntime
    ) -> None:
        (attempt_id,) = _claimed_attempts(paper, 1)
        limits = _limits(maximum_daily_order_count=1)
        assert _admit(paper, attempt_id, limits) is None
        assert _admit(paper, attempt_id, limits) is None  # its own row is never double counted
        ledger = paper.execution_attempts.entry_ledger(day_start=DAY_START, day_end=DAY_END)
        assert [row.admitted for row in ledger] == [True]

    def test_a_refusal_records_nothing(self, paper: PostgresPaperExecutionRuntime) -> None:
        (attempt_id,) = _claimed_attempts(paper, 1)
        refusal = _admit(paper, attempt_id, _limits(maximum_deployable_capital=Decimal("1")))
        assert refusal is not None and "total exposure limit reached" in refusal
        (row,) = paper.execution_attempts.entry_ledger(day_start=DAY_START, day_end=DAY_END)
        assert row.admitted is False


class TestTheLedgerIsDurableLocalTruth:
    def test_an_attempt_closed_not_sent_stops_counting(
        self, paper: PostgresPaperExecutionRuntime
    ) -> None:
        first, second = _claimed_attempts(paper, 2)
        limits = _limits(maximum_daily_order_count=1)
        assert _admit(paper, first, limits) is None
        assert _admit(paper, second, limits) is not None  # the cap is spent

        # The first attempt is then refused at the last guard: nothing left the process.
        attempts = paper.execution_attempts
        attempts.transition(
            attempt_id=first, target=PaperExecutionState.SUBMISSION_IN_PROGRESS, at=CHAIN_AT
        )
        attempts.transition(
            attempt_id=first,
            target=PaperExecutionState.REJECTED,
            at=CHAIN_AT,
            failure_code="NOT_SENT",
            failure_detail="refused at the boundary",
        )
        rows = {
            row.attempt_id: row
            for row in attempts.entry_ledger(day_start=DAY_START, day_end=DAY_END)
        }
        assert not ledger_counts_order(rows[first])
        assert _admit(paper, second, limits) is None  # the slot was freed

    def test_the_ledger_is_scoped_to_the_trading_day(
        self, paper: PostgresPaperExecutionRuntime
    ) -> None:
        (attempt_id,) = _claimed_attempts(paper, 1)
        assert _admit(paper, attempt_id, _limits()) is None
        next_start, next_end = trading_day_bounds(DAY_END)
        assert paper.execution_attempts.entry_ledger(day_start=next_start, day_end=next_end) == ()

    def test_an_unreadable_admission_record_fails_closed(
        self, paper: PostgresPaperExecutionRuntime
    ) -> None:
        (attempt_id,) = _claimed_attempts(paper, 1)
        attempt = paper.execution_attempts.get(attempt_id)
        assert attempt is not None
        paper.paper_execution_events.append(
            PaperExecutionEvent(
                event_id="EVT-D1-GARBAGE",
                intent_governance_id=attempt.intent_governance_id,
                attempt_id=attempt_id,
                event_type=ENTRY_ADMITTED_EVENT_TYPE,
                occurred_at=CHAIN_AT,
                detail="this is not an admission record",
            )
        )
        with pytest.raises(PortfolioEvidenceError):
            paper.execution_attempts.entry_ledger(day_start=DAY_START, day_end=DAY_END)
        with pytest.raises(PortfolioEvidenceError):
            _admit(paper, attempt_id, _limits())
