"""REV-R1 against real PostgreSQL and process restarts: absence never revokes what was observed.

Production handlers over the real repositories on a disposable database; every "process" is a
fresh `PostgresPersistenceService`, so each reconciliation reads exactly what the database holds.
The broker is the controlled fake of the identity-collision suite.

  A  ambiguous POST (1 request left) -> new process: 404 -> 500 -> 404: NOT two consecutive
     not-found observations; the outcome stays SUBMISSION_UNKNOWN and a later consecutive pair
     still resolves it (positive control of the bounded policy);
  B  accepted order with a persisted broker_order_id -> new process: 404 -> 404: absence records
     an event, the order stays PAPER_ACCEPTED with its broker id and remains reconcilable;
  C  inconclusive pre-send lookup (0 requests) -> new process: 404 -> 200 (existing order,
     observed, not attributed) -> 404: the positive observation is not discarded.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy.engine import Engine
from tests.integration._m085_support import build_engine, truncate_all
from tests.integration.test_m085_identity_collision_postgres import (
    _authorized_order_as_the_broker_reports_it,
    _Broker,
    _MarketData,
    _Process,
)
from tests.integration.test_m085_temporal_postgres import Clock

from empirical_platform.decision_candidate.paper_execution import (
    ExecutionAttempt,
    PaperExecutionState,
)

pytestmark = pytest.mark.integration

_NOT_FOUND = (404, None, '{"code": 40410000, "message": "order not found"}')
_SERVER_ERROR = (500, None, '{"code": 50010000, "message": "internal server error"}')


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    yield from build_engine()


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
        yield {"clock": clock, "broker": broker, "spawn": spawn}
    finally:
        for process in processes:
            process.close()


def _reconcile_after(
    process: _Process,
    world: dict[str, Any],
    intent_id: str,
    seconds: int,
    answer: tuple[int, object | None, str],
) -> ExecutionAttempt:
    world["broker"].lookup_sequence = [answer]
    world["clock"].advance(seconds)
    return process.reconcile(intent_id)


def _acks(process: _Process, attempt_id: str) -> list[tuple[str, int, str | None]]:
    return [
        (a.kind, a.http_status, a.broker_order_id)
        for a in process.paper.broker_acknowledgements.for_attempt(attempt_id)
    ]


def test_an_unusable_answer_between_two_not_found_answers_does_not_resolve_the_unknown(
    world: dict[str, Any],
) -> None:
    a = world["spawn"]("a")
    intent_id, _ = a.authorize(suffix="A")
    broker = world["broker"]
    broker.submit_status = 503
    broker.submit_body = '{"code": 50310000, "message": "unavailable"}'
    first = a.submit(intent_id, attempt_id="ATT-ABS-A")
    assert first.attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN
    assert len(broker.submitted) == 1
    a.close()

    b = world["spawn"]("b")
    assert _reconcile_after(b, world, intent_id, 61, _NOT_FOUND).state is (
        PaperExecutionState.SUBMISSION_UNKNOWN
    )
    assert _reconcile_after(b, world, intent_id, 60, _SERVER_ERROR).state is (
        PaperExecutionState.SUBMISSION_UNKNOWN
    )
    third = _reconcile_after(b, world, intent_id, 60, _NOT_FOUND)
    assert third.state is PaperExecutionState.SUBMISSION_UNKNOWN, (
        f"404 -> 500 -> 404 resolved the unknown: {third.state.value} {third.failure_code}"
    )
    assert _acks(b, "ATT-ABS-A")[1:] == [
        ("RECONCILE", 404, None),
        ("RECONCILE", 500, None),
        ("RECONCILE", 404, None),
    ]
    b.close()
    # Positive control, in a third process: a consecutive second 404 resolves it.
    c = world["spawn"]("c")
    resolved = _reconcile_after(c, world, intent_id, 60, _NOT_FOUND)
    assert resolved.state is PaperExecutionState.REJECTED
    assert resolved.failure_code == "NOT_FOUND_AT_BROKER"
    assert len(broker.submitted) == 1


def test_absence_never_rejects_an_accepted_order_with_a_persisted_broker_id(
    world: dict[str, Any],
) -> None:
    a = world["spawn"]("a")
    intent_id, authorization = a.authorize(suffix="B")
    accepted = a.submit(intent_id, attempt_id="ATT-ABS-B")
    assert accepted.attempt.state is PaperExecutionState.PAPER_ACCEPTED
    assert accepted.attempt.broker_order_id is not None
    a.close()

    b = world["spawn"]("b")
    stored = b.paper.execution_attempts.for_intent(intent_id)
    assert stored is not None and stored.broker_order_id == accepted.attempt.broker_order_id
    for seconds in (61, 60):
        later = _reconcile_after(b, world, intent_id, seconds, _NOT_FOUND)
        assert later.state is PaperExecutionState.PAPER_ACCEPTED, (
            f"absence changed a known accepted order to {later.state.value} {later.failure_code}"
        )
        assert later.broker_order_id == accepted.attempt.broker_order_id
    assert "RECONCILE_NOT_FOUND_KNOWN_ORDER" in b.events(intent_id)
    assert "RECONCILE_RESOLVED_NOT_FOUND" not in b.events(intent_id)
    b.close()
    # Still reconcilable from yet another process when the broker answers again.
    c = world["spawn"]("c")
    filled = _reconcile_after(
        c,
        world,
        intent_id,
        60,
        (
            200,
            _authorized_order_as_the_broker_reports_it(
                authorization, broker_order_id=accepted.attempt.broker_order_id, status="filled"
            ),
            "{}",
        ),
    )
    assert filled.state is PaperExecutionState.FILLED
    assert len(world["broker"].submitted) == 1


def test_absence_never_discards_a_positive_observation_across_processes(
    world: dict[str, Any],
) -> None:
    a = world["spawn"]("a")
    intent_id, authorization = a.authorize(suffix="C")
    broker = world["broker"]
    broker.lookup_sequence = [_SERVER_ERROR]  # the pre-send lookup is inconclusive
    first = a.submit(intent_id, attempt_id="ATT-ABS-C")
    assert first.attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN
    assert first.attempt.failure_code == "IDENTITY_UNRESOLVED_UNSENT"
    assert broker.submitted == []
    a.close()

    b = world["spawn"]("b")
    assert _reconcile_after(b, world, intent_id, 61, _NOT_FOUND).state is (
        PaperExecutionState.SUBMISSION_UNKNOWN
    )
    historical = (
        200,
        _authorized_order_as_the_broker_reports_it(
            authorization, broker_order_id="broker-historical", status="new"
        ),
        "{}",
    )
    observed = _reconcile_after(b, world, intent_id, 60, historical)
    assert observed.state is PaperExecutionState.SUBMISSION_UNKNOWN
    assert observed.broker_order_id is None
    assert "IDENTITY_OBSERVED_NOT_ATTRIBUTED" in b.events(intent_id)
    b.close()

    c = world["spawn"]("c")
    third = _reconcile_after(c, world, intent_id, 60, _NOT_FOUND)
    assert third.state is PaperExecutionState.SUBMISSION_UNKNOWN, (
        f"a later 404 discarded the observation: {third.state.value} {third.failure_code}"
    )
    assert "RECONCILE_NOT_FOUND_AFTER_OBSERVATION" in c.events(intent_id)
    assert "RECONCILE_RESOLVED_NOT_FOUND" not in c.events(intent_id)
    assert c.submit(intent_id, attempt_id="ATT-ABS-C2").dispatched is False
    assert broker.submitted == []
