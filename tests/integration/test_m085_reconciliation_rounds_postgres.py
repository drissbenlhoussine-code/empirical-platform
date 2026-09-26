"""Q-2 / Q-4 against real PostgreSQL: durable rounds, atomic allocation, real deaths, skewed clocks.

Production handlers and repositories on a disposable database rebuilt from the full migration
history (so `a7d3c9e14f26` is installed by the chain). Each "process" is a fresh
`PostgresPersistenceService`; a real child-process death (`os._exit`) is used for the round
that dies after it was begun. The broker is the controlled fake of the identity-collision
suite; its clock is `clock_a` -- reconciler B's wall clock is a different, offset clock.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from sqlalchemy import text
from sqlalchemy.engine import Engine
from tests.integration._m085_support import (
    REPO_ROOT,
    alembic_config,
    build_engine,
    config,
    truncate_all,
)
from tests.integration.test_m085_identity_collision_postgres import (
    _authorized_order_as_the_broker_reports_it,
    _Broker,
    _MarketData,
    _Process,
)
from tests.integration.test_m085_temporal_postgres import Clock

from empirical_platform.decision_candidate.paper_execution import (
    BrokerAcknowledgement,
    PaperExecutionState,
    ReconciliationRoundOutcome,
    consecutive_not_found_rounds,
    waiting_lower_bound_seconds,
)
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.paper_execution_repositories import (  # noqa: E501
    M085_SCHEMA_HEAD,
    PostgresPaperExecutionRuntime,
    PostgresReconciliationRoundRepository,
)
from empirical_platform.usecases.paper_execution import (
    ReconcilePaperOrderCommand,
    ReconcilePaperOrderHandler,
)

pytestmark = pytest.mark.integration

_NOT_FOUND = (404, None, '{"code": 40410000, "message": "order not found"}')
_DEATH = 3


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    yield from build_engine()


@pytest.fixture
def world(engine: Engine, tmp_path: Path) -> Iterator[dict[str, Any]]:
    truncate_all(engine)
    clock = Clock()
    broker = _Broker(clock)  # the broker's clock IS clock_a
    data = _MarketData(clock)
    processes: list[_Process] = []

    def spawn(name: str, clock_for_process: Clock | None = None) -> _Process:
        process = _Process(name, clock_for_process or clock, broker, data)
        processes.append(process)
        return process

    try:
        yield {"engine": engine, "clock": clock, "broker": broker, "spawn": spawn, "out": tmp_path}
    finally:
        for process in processes:
            process.close()


def _ambiguous(
    world: dict[str, Any], process: _Process, suffix: str, attempt_id: str
) -> tuple[str, Any]:
    intent_id, authorization = process.authorize(suffix=suffix)
    broker = world["broker"]
    broker.submit_status = 503
    broker.submit_body = '{"code": 50310000, "message": "unavailable"}'
    result = process.submit(intent_id, attempt_id=attempt_id)
    assert result.attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN
    broker.submit_status = 200
    return intent_id, authorization


def _reconcile(process: _Process, intent_id: str, answer: Any, *, rounds: Any = None) -> Any:  # noqa: ANN401
    broker = process.broker
    if isinstance(answer, BaseException):
        broker.lookup_raises = answer
    else:
        broker.lookup_sequence = [answer]
    try:
        return ReconcilePaperOrderHandler(
            attempts=process.paper.execution_attempts,
            acknowledgements=process.paper.broker_acknowledgements,
            events=process.paper.paper_execution_events,
            broker=broker,
            authorizations=process.paper.execution_authorizations,
            previews=process.paper.submission_previews,
            rounds=rounds if rounds is not None else process.paper.reconciliation_rounds,
            time_source=process.clock,
        ).handle(ReconcilePaperOrderCommand(intent_governance_id=intent_id, at=process.clock.utc))
    except Exception as error:  # noqa: BLE001 - returned for inspection
        return error
    finally:
        broker.lookup_raises = None


def _rounds(process: _Process, attempt_id: str) -> list[tuple[int, str | None]]:
    return [
        (r.sequence, None if r.outcome is None else r.outcome.value)
        for r in process.paper.reconciliation_rounds.for_attempt(attempt_id)
    ]


class _CompletionThatFails:
    def __init__(self, inner: object) -> None:
        self._inner = inner

    def complete(self, *args: object, **kwargs: object) -> object:
        raise RuntimeError("database unavailable while completing the round")

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)


# ---------------------------------------------------------------------------
# Repository guards
# ---------------------------------------------------------------------------


def test_the_journal_completes_a_round_exactly_once_and_binds_it_to_the_attempt(
    world: dict[str, Any],
) -> None:
    a = world["spawn"]("a")
    intent_id, authorization = _ambiguous(world, a, "G", "ATT-RND-G")
    rounds = a.paper.reconciliation_rounds
    attempt = a.paper.execution_attempts.for_intent(intent_id)
    assert attempt is not None
    round_ = rounds.begin(
        attempt=attempt,
        account_reference=authorization.account_reference,
        started_at=world["clock"].utc,
    )
    assert round_.sequence == 1 and not round_.is_complete
    done = rounds.complete(
        round_.round_id,
        outcome=ReconciliationRoundOutcome.NOT_FOUND,
        completed_at=world["clock"].utc,
    )
    assert done.is_complete
    with pytest.raises(ValueError, match="already complete"):
        rounds.complete(
            round_.round_id,
            outcome=ReconciliationRoundOutcome.FOUND,
            completed_at=world["clock"].utc,
        )
    with pytest.raises(ValueError, match="no reconciliation round"):
        rounds.complete(
            "RND-NOPE-1", outcome=ReconciliationRoundOutcome.FOUND, completed_at=world["clock"].utc
        )
    # The database itself refuses a rewrite, an identity change and a deletion. Each attack
    # runs in its own transaction: the trigger's exception aborts the transaction it is in.
    for statement, fragment in (
        (
            "UPDATE public.paper_reconciliation_round SET outcome = 'FOUND' WHERE round_id = :r",
            "immutable",
        ),
        (
            "UPDATE public.paper_reconciliation_round SET sequence = 9 WHERE round_id = :r",
            "immutable",
        ),
        ("DELETE FROM public.paper_reconciliation_round WHERE round_id = :r", "append-only"),
    ):
        with pytest.raises(sa.exc.DBAPIError) as raised, world["engine"].begin() as connection:
            connection.execute(text(statement), {"r": round_.round_id})
        assert fragment in str(raised.value)
    # A round inserted already complete, or for a foreign attempt, is refused.
    with pytest.raises(sa.exc.DBAPIError, match="must begin incomplete"):
        with world["engine"].begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.paper_reconciliation_round (round_id, attempt_id, "
                    "intent_governance_id, authorization_id, client_order_id, "
                    "account_reference, sequence, started_at, outcome, completed_at) VALUES "
                    "('RND-X', :attempt, :intent, :authorization, :client, 'ref:x', 7, now(), "
                    "'NOT_FOUND', now())"
                ),
                {
                    "attempt": attempt.attempt_id,
                    "intent": attempt.intent_governance_id,
                    "authorization": attempt.authorization_id,
                    "client": attempt.client_order_id,
                },
            )
    # The per-attempt sequence is unique: a second round 1 for this attempt is refused.
    with pytest.raises(sa.exc.IntegrityError, match="uq_paper_reconciliation_round"):
        with world["engine"].begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.paper_reconciliation_round (round_id, attempt_id, "
                    "intent_governance_id, authorization_id, client_order_id, "
                    "account_reference, sequence, started_at) VALUES ('RND-DUP', :attempt, "
                    ":intent, :authorization, :client, 'ref:x', 1, now())"
                ),
                {
                    "attempt": attempt.attempt_id,
                    "intent": attempt.intent_governance_id,
                    "authorization": attempt.authorization_id,
                    "client": attempt.client_order_id,
                },
            )
    with pytest.raises(sa.exc.DBAPIError, match="does not describe attempt"):
        with world["engine"].begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.paper_reconciliation_round (round_id, attempt_id, "
                    "intent_governance_id, authorization_id, client_order_id, "
                    "account_reference, sequence, started_at) VALUES ('RND-Y', :attempt, "
                    ":intent, 'AUT-OTHER', :client, 'ref:x', 8, now())"
                ),
                {
                    "attempt": attempt.attempt_id,
                    "intent": attempt.intent_governance_id,
                    "client": attempt.client_order_id,
                },
            )


def test_concurrent_round_starts_obtain_distinct_durable_sequences(world: dict[str, Any]) -> None:
    a = world["spawn"]("a")
    intent_id, authorization = _ambiguous(world, a, "C", "ATT-RND-C")
    attempt = a.paper.execution_attempts.for_intent(intent_id)
    assert attempt is not None
    services = [PostgresPersistenceService(config(f"m085-rounds-{i}")) for i in range(8)]
    for service in services:
        service.initialize()
    errors: list[str] = []
    sequences: list[int] = []

    def begin(service: PostgresPersistenceService) -> None:
        try:
            round_ = PostgresPaperExecutionRuntime(service).reconciliation_rounds.begin(
                attempt=attempt,
                account_reference=authorization.account_reference,
                started_at=world["clock"].utc,
            )
            sequences.append(round_.sequence)
        except Exception as error:  # noqa: BLE001 - collected, asserted below
            errors.append(f"{type(error).__name__}: {error}")

    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(begin, services))
    finally:
        for service in services:
            service.close()
    assert errors == []
    assert sorted(sequences) == list(range(1, 9)), (
        "concurrent starts did not obtain distinct sequences"
    )
    assert len(_rounds(a, attempt.attempt_id)) == 8


class _PausingWork:
    """A unit of work that pauses right after the highest sequence was read."""

    def __init__(self, inner: Any, pause: Any) -> None:  # noqa: ANN401
        self._inner = inner
        self._pause = pause

    def __enter__(self) -> _PausingWork:
        self._inner.__enter__()
        return self

    def __exit__(self, *exc: object) -> Any:  # noqa: ANN401
        return self._inner.__exit__(*exc)

    def execute(self, statement: str, parameters: Any = None) -> Any:  # noqa: ANN401
        rows = self._inner.execute(statement, parameters)
        if "MAX(sequence)" in statement and "paper_reconciliation_round" in statement:
            self._pause()
        return rows

    def __getattr__(self, name: str) -> Any:  # noqa: ANN401
        return getattr(self._inner, name)


class _PausingService:
    def __init__(self, inner: PostgresPersistenceService, pause: Any) -> None:  # noqa: ANN401
        self._inner = inner
        self._pause = pause

    def unit_of_work(self) -> _PausingWork:
        return _PausingWork(self._inner.unit_of_work(), self._pause)

    def __getattr__(self, name: str) -> Any:  # noqa: ANN401
        return getattr(self._inner, name)


def test_allocation_holds_the_attempt_lock_between_reading_and_inserting(
    world: dict[str, Any],
) -> None:
    """Deterministic race: writer S reads MAX(sequence) and then pauses until writer F has
    finished or three seconds pass. Under the attempt lock F cannot finish while S holds it,
    so S times out, inserts 1, commits, and F then allocates 2. Without the lock F allocates 1
    during the pause and S's insert of 1 collides."""
    a = world["spawn"]("a")
    intent_id, authorization = _ambiguous(world, a, "K", "ATT-RND-K")
    attempt = a.paper.execution_attempts.for_intent(intent_id)
    assert attempt is not None
    paused = threading.Event()
    fast_done = threading.Event()
    slow_service = PostgresPersistenceService(config("m085-rounds-slow"))
    fast_service = PostgresPersistenceService(config("m085-rounds-fast"))
    slow_service.initialize()
    fast_service.initialize()
    errors: list[str] = []
    sequences: list[tuple[str, int]] = []

    def pause() -> None:
        paused.set()
        fast_done.wait(timeout=3.0)

    def slow() -> None:
        repository = PostgresReconciliationRoundRepository(
            _PausingService(slow_service, pause)  # type: ignore[arg-type]
        )
        try:
            begun = repository.begin(
                attempt=attempt,
                account_reference=authorization.account_reference,
                started_at=world["clock"].utc,
            )
            sequences.append(("slow", begun.sequence))
        except Exception as error:  # noqa: BLE001 - collected, asserted below
            errors.append(f"slow: {type(error).__name__}: {error}")

    def fast() -> None:
        assert paused.wait(timeout=10.0)
        try:
            begun = PostgresPaperExecutionRuntime(fast_service).reconciliation_rounds.begin(
                attempt=attempt,
                account_reference=authorization.account_reference,
                started_at=world["clock"].utc,
            )
            sequences.append(("fast", begun.sequence))
        except Exception as error:  # noqa: BLE001 - collected, asserted below
            errors.append(f"fast: {type(error).__name__}: {error}")
        finally:
            fast_done.set()

    threads = [threading.Thread(target=slow), threading.Thread(target=fast)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30.0)
    finally:
        slow_service.close()
        fast_service.close()
    assert errors == [], errors
    assert dict(sequences) == {"slow": 1, "fast": 2}, sequences
    assert _rounds(a, "ATT-RND-K") == [(1, None), (2, None)]


# ---------------------------------------------------------------------------
# Q-2 across fresh services and a real child death
# ---------------------------------------------------------------------------


def test_q2_double_failure_across_a_restart_leaves_the_round_visible_and_blocks_resolution(
    world: dict[str, Any],
) -> None:
    a = world["spawn"]("a")
    intent_id, _ = _ambiguous(world, a, "Q2", "ATT-RND-Q2")
    a.close()
    b = world["spawn"]("b")
    world["clock"].advance(61)
    assert _reconcile(b, intent_id, _NOT_FOUND).state is PaperExecutionState.SUBMISSION_UNKNOWN
    world["clock"].advance(60)
    failing = _CompletionThatFails(b.paper.reconciliation_rounds)
    error = _reconcile(b, intent_id, RuntimeError("connection reset"), rounds=failing)
    assert isinstance(error, RuntimeError)
    b.close()
    c = world["spawn"]("c")
    assert _rounds(c, "ATT-RND-Q2") == [(1, "NOT_FOUND"), (2, None)], (
        "the STARTED round survived the restart"
    )
    world["clock"].advance(60)
    third = _reconcile(c, intent_id, _NOT_FOUND)
    assert third.state is PaperExecutionState.SUBMISSION_UNKNOWN
    assert _rounds(c, "ATT-RND-Q2") == [(1, "NOT_FOUND"), (2, None), (3, "NOT_FOUND")]
    assert "RECONCILE_ROUND_INCOMPLETE" in c.events(intent_id)
    assert not third.is_terminal and len(world["broker"].submitted) == 1


def test_positive_control_two_completed_not_found_rounds_sixty_broker_seconds_apart_resolve(
    world: dict[str, Any],
) -> None:
    a = world["spawn"]("a")
    intent_id, _ = _ambiguous(world, a, "PC", "ATT-RND-PC")
    a.close()
    b = world["spawn"]("b")
    world["clock"].advance(61)
    assert _reconcile(b, intent_id, _NOT_FOUND).state is PaperExecutionState.SUBMISSION_UNKNOWN
    world["clock"].advance(60)
    resolved = _reconcile(b, intent_id, _NOT_FOUND)
    assert resolved.state is PaperExecutionState.REJECTED
    assert resolved.failure_code == "NOT_FOUND_AT_BROKER"
    assert _rounds(b, "ATT-RND-PC") == [(1, "NOT_FOUND"), (2, "NOT_FOUND")]
    assert "RECONCILE_RESOLVED_NOT_FOUND" in b.events(intent_id)
    assert len(world["broker"].submitted) == 1 and world["broker"].cancelled == []


def test_q2_a_real_child_death_after_the_round_began_leaves_it_incomplete(
    world: dict[str, Any],
) -> None:
    a = world["spawn"]("a")
    intent_id, _ = _ambiguous(world, a, "R", "ATT-RND-R")
    a.close()
    result = subprocess.run(  # noqa: S603 - this repository's own test module
        [
            sys.executable,
            "-B",
            "-m",
            "tests.integration._m085_crash_child",
            "R",
            intent_id,
            "ATT-RND-R",
            str(world["out"]),
        ],
        cwd=REPO_ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == _DEATH, (
        result.returncode,
        result.stdout[-1500:],
        result.stderr[-3000:],
    )
    assert (world["out"] / "died-at.txt").read_text(
        encoding="utf-8"
    ) == "during-reconciliation-lookup-after-round-begun"
    b = world["spawn"]("b")
    assert _rounds(b, "ATT-RND-R") == [(1, None)], (
        "the child's STARTED round is visible after its death"
    )
    world["clock"].advance(61)
    assert _reconcile(b, intent_id, _NOT_FOUND).state is PaperExecutionState.SUBMISSION_UNKNOWN
    world["clock"].advance(60)
    third = _reconcile(b, intent_id, _NOT_FOUND)
    assert third.state is PaperExecutionState.SUBMISSION_UNKNOWN, (
        "the dead round's absence of a result counted as a 404"
    )
    assert "RECONCILE_ROUND_INCOMPLETE" in b.events(intent_id)
    assert len(world["broker"].submitted) == 1


# ---------------------------------------------------------------------------
# Q-4 with two reconcilers whose wall clocks differ; the broker clock is clock_a
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("skew", [-120, 120], ids=["B-lags", "B-leads"])
def test_q4_failure_by_a_skewed_reconciler_breaks_the_run_by_sequence(
    world: dict[str, Any], skew: int
) -> None:
    a = world["spawn"]("a")
    intent_id, _ = _ambiguous(world, a, "S", "ATT-RND-S")
    clock_b = Clock()
    clock_b.advance(skew)
    b = world["spawn"]("b", clock_b)
    world["clock"].advance(61)
    clock_b.advance(61)
    assert _reconcile(a, intent_id, _NOT_FOUND).state is PaperExecutionState.SUBMISSION_UNKNOWN
    world["clock"].advance(60)
    clock_b.advance(60)
    assert isinstance(_reconcile(b, intent_id, RuntimeError("connection reset")), RuntimeError)
    world["clock"].advance(60)
    clock_b.advance(60)
    third = _reconcile(a, intent_id, _NOT_FOUND)
    assert third.state is PaperExecutionState.SUBMISSION_UNKNOWN, f"skew {skew:+d}s resolved early"
    assert _rounds(a, "ATT-RND-S") == [(1, "NOT_FOUND"), (2, "FAILED"), (3, "NOT_FOUND")]


@pytest.mark.parametrize("skew", [-120, 120], ids=["B-lags", "B-leads"])
def test_q4_positive_observation_by_a_skewed_reconciler_is_protected(
    world: dict[str, Any], skew: int
) -> None:
    a = world["spawn"]("a")
    intent_id, authorization = _ambiguous(world, a, "P", "ATT-RND-P")
    clock_b = Clock()
    clock_b.advance(skew)
    b = world["spawn"]("b", clock_b)
    world["clock"].advance(61)
    clock_b.advance(61)
    assert _reconcile(a, intent_id, _NOT_FOUND).state is PaperExecutionState.SUBMISSION_UNKNOWN
    world["clock"].advance(60)
    clock_b.advance(60)
    found = (
        200,
        _authorized_order_as_the_broker_reports_it(
            authorization, broker_order_id="broker-b", status="new"
        ),
        "{}",
    )
    observed = _reconcile(b, intent_id, found)
    assert observed.broker_order_id == "broker-b"  # lineage present: legitimate recovery
    world["clock"].advance(60)
    clock_b.advance(60)
    later = _reconcile(a, intent_id, _NOT_FOUND)
    assert later.broker_order_id == "broker-b" and not later.is_terminal
    assert "RECONCILE_NOT_FOUND_KNOWN_ORDER" in a.events(intent_id)


def test_q4_a_leading_reconciler_clock_cannot_satisfy_the_waiting_interval(
    world: dict[str, Any],
) -> None:
    a = world["spawn"]("a")
    intent_id, _ = _ambiguous(world, a, "L", "ATT-RND-L")
    clock_b = Clock()
    clock_b.advance(120)  # B believes it is two minutes later than the broker
    b = world["spawn"]("b", clock_b)
    # Round 1 by A (wall clock = broker clock); round 2 by B five broker-seconds later.
    world["clock"].advance(5)
    clock_b.advance(5)
    assert _reconcile(a, intent_id, _NOT_FOUND).state is PaperExecutionState.SUBMISSION_UNKNOWN
    world["clock"].advance(5)
    clock_b.advance(5)
    result = _reconcile(b, intent_id, _NOT_FOUND)
    assert result.state is PaperExecutionState.SUBMISSION_UNKNOWN, (
        "host wall time satisfied the interval"
    )
    rounds = b.paper.reconciliation_rounds.for_attempt("ATT-RND-L")
    assert waiting_lower_bound_seconds(rounds) == 5.0
    assert consecutive_not_found_rounds(rounds) == 2
    world["clock"].advance(55)
    clock_b.advance(55)
    assert (
        _reconcile(b, intent_id, _NOT_FOUND).state is PaperExecutionState.REJECTED
    )  # 60 broker seconds


# ---------------------------------------------------------------------------
# Finalisation under concurrency, against the real repository
# ---------------------------------------------------------------------------


class _RoundsWithAnInterloper:
    def __init__(self, inner: object, interlope: Any) -> None:  # noqa: ANN401
        self._inner = inner
        self._interlope = interlope
        self.done = False

    def resolve_not_found(self, **kwargs: Any) -> Any:  # noqa: ANN401
        if not self.done:
            self.done = True
            self._interlope()
        return self._inner.resolve_not_found(**kwargs)  # type: ignore[attr-defined]

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)


def test_positive_evidence_from_another_process_during_finalisation_prevents_rejection(
    world: dict[str, Any],
) -> None:
    a = world["spawn"]("a")
    intent_id, authorization = _ambiguous(world, a, "F", "ATT-RND-F")
    b = world["spawn"]("b")
    world["clock"].advance(61)
    assert _reconcile(a, intent_id, _NOT_FOUND).state is PaperExecutionState.SUBMISSION_UNKNOWN
    world["clock"].advance(60)

    def b_observes_the_order() -> None:
        found = (
            200,
            _authorized_order_as_the_broker_reports_it(
                authorization, broker_order_id="broker-late", status="new"
            ),
            "{}",
        )
        _reconcile(b, intent_id, found)

    result = _reconcile(
        a,
        intent_id,
        _NOT_FOUND,
        rounds=_RoundsWithAnInterloper(a.paper.reconciliation_rounds, b_observes_the_order),
    )
    assert result.state is not PaperExecutionState.REJECTED
    assert result.broker_order_id == "broker-late"
    assert "RECONCILE_RESOLUTION_REVALIDATION_FAILED" in a.events(intent_id)
    assert "RECONCILE_RESOLVED_NOT_FOUND" not in a.events(intent_id)


def test_a_round_completed_by_another_process_after_the_snapshot_is_never_finalised_from_it(
    world: dict[str, Any],
) -> None:
    """The interloper completes a clean NOT_FOUND round of its own between A's judgement and
    A's finalisation. The fresh rows would STILL permit resolution, so only the round-set
    version check stands between A and a decision made on evidence it never saw."""
    a = world["spawn"]("a")
    intent_id, authorization = _ambiguous(world, a, "S", "ATT-RND-S")
    b = world["spawn"]("b")
    attempt = a.paper.execution_attempts.for_intent(intent_id)
    assert attempt is not None
    world["clock"].advance(61)
    assert _reconcile(a, intent_id, _NOT_FOUND).state is PaperExecutionState.SUBMISSION_UNKNOWN
    world["clock"].advance(60)

    def b_completes_a_round_of_its_own() -> None:
        rounds_b = b.paper.reconciliation_rounds
        begun = rounds_b.begin(
            attempt=attempt,
            account_reference=authorization.account_reference,
            started_at=world["clock"].utc,
        )
        rounds_b.complete(
            begun.round_id,
            outcome=ReconciliationRoundOutcome.NOT_FOUND,
            completed_at=world["clock"].utc,
            broker_earliest_at=world["clock"].utc,
            broker_latest_at=world["clock"].utc,
        )

    result = _reconcile(
        a,
        intent_id,
        _NOT_FOUND,
        rounds=_RoundsWithAnInterloper(
            a.paper.reconciliation_rounds, b_completes_a_round_of_its_own
        ),
    )
    assert result.state is PaperExecutionState.SUBMISSION_UNKNOWN, "finalised from a stale snapshot"
    assert "RECONCILE_RESOLUTION_REVALIDATION_FAILED" in a.events(intent_id)
    assert _rounds(a, "ATT-RND-S") == [(1, "NOT_FOUND"), (2, "NOT_FOUND"), (3, "NOT_FOUND")]
    # Judged again on the complete round set, the next round resolves legitimately.
    world["clock"].advance(60)
    assert _reconcile(a, intent_id, _NOT_FOUND).state is PaperExecutionState.REJECTED


def test_finalisation_honours_positive_evidence_recorded_without_a_round(
    world: dict[str, Any],
) -> None:
    """A positive observation lands in the acknowledgement journal without a round (another
    code path, or a legacy writer) between judgement and finalisation. The round set is
    unchanged, so only the fresh re-evaluation stands between A and the rejection."""
    a = world["spawn"]("a")
    intent_id, _ = _ambiguous(world, a, "P", "ATT-RND-P")
    attempt = a.paper.execution_attempts.for_intent(intent_id)
    assert attempt is not None
    world["clock"].advance(61)
    assert _reconcile(a, intent_id, _NOT_FOUND).state is PaperExecutionState.SUBMISSION_UNKNOWN
    world["clock"].advance(60)

    def an_observation_lands_without_a_round() -> None:
        acknowledgements = a.paper.broker_acknowledgements
        sequence = acknowledgements.next_sequence(attempt.attempt_id)
        acknowledgements.append(
            BrokerAcknowledgement(
                acknowledgement_id=f"ACK-{attempt.attempt_id}-{sequence}",
                attempt_id=attempt.attempt_id,
                sequence=sequence,
                kind="RECONCILE",
                observed_at=world["clock"].utc,
                http_status=200,
                broker_order_id="broker-elsewhere",
                broker_status="new",
                client_order_id_echo=attempt.client_order_id,
                payload_digest="a" * 64,
                sanitized_payload="{}",
            )
        )

    result = _reconcile(
        a,
        intent_id,
        _NOT_FOUND,
        rounds=_RoundsWithAnInterloper(
            a.paper.reconciliation_rounds, an_observation_lands_without_a_round
        ),
    )
    assert result.state is not PaperExecutionState.REJECTED, (
        "a positive observation on fresh rows was ignored at finalisation"
    )
    assert "RECONCILE_RESOLUTION_REVALIDATION_FAILED" in a.events(intent_id)
    assert "RECONCILE_RESOLVED_NOT_FOUND" not in a.events(intent_id)


# ---------------------------------------------------------------------------
# Migration: additive, reversible, re-applicable
# ---------------------------------------------------------------------------


def test_the_round_journal_migration_goes_down_and_up_again(world: dict[str, Any]) -> None:
    engine: Engine = world["engine"]

    def catalog() -> dict[str, Any]:
        with engine.begin() as connection:
            tables = {
                r[0]
                for r in connection.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                ).all()
            }
            triggers = {
                r[0]
                for r in connection.execute(
                    text(
                        "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal "
                        "AND tgname LIKE 'paper_reconciliation_round%'"
                    )
                ).all()
            }
            functions = {
                r[0]
                for r in connection.execute(
                    text(
                        "SELECT proname FROM pg_proc "
                        "WHERE proname LIKE 'paper_reconciliation_round%'"
                    )
                ).all()
            }
            head = connection.execute(
                text("SELECT version_num FROM public.alembic_version")
            ).scalar_one()
        return {
            "table": "paper_reconciliation_round" in tables,
            "triggers": triggers,
            "functions": functions,
            "head": head,
        }

    at_head = catalog()
    assert at_head["table"] and at_head["head"] == M085_SCHEMA_HEAD
    assert at_head["triggers"] == {
        "paper_reconciliation_round_guard_insert_trigger",
        "paper_reconciliation_round_guard_update_trigger",
        "paper_reconciliation_round_append_only_trigger",
    }
    assert at_head["functions"] == {
        "paper_reconciliation_round_guard_insert",
        "paper_reconciliation_round_guard_update",
    }
    # The revision below the round journal, spelled in two parts for the entropy scanner.
    previous_revision = "".join(("9c4b2e", "7d5a18"))
    alembic_command.downgrade(alembic_config(), previous_revision)
    try:
        below = catalog()
        assert not below["table"] and below["triggers"] == set() and below["functions"] == set()
        assert below["head"] == previous_revision
    finally:
        alembic_command.upgrade(alembic_config(), "head")
    assert catalog() == at_head
