"""Q-2 / Q-4 -- durable reconciliation rounds and a waiting interval on the broker's clock.

Every reconciliation round is begun DURABLY before its network work, completed exactly once
against its own identity, and ordered by an allocated per-attempt sequence. The bounded
not-found policy reads rounds: a trailing run of completed NOT_FOUND rounds (an incomplete,
FAILED, UNUSABLE or FOUND round ends it), and a waiting interval measured on the BROKER clock
as `current_round.broker_earliest - anchor_round.broker_latest`, the anchor being the first
completed round with a broker interval (established after the uncertain dispatch, so
conservative). The terminal transition is re-validated atomically on fresh rows.

Unit simulations over the fakes (`FakeReconciliationRounds` implements the repository
contract in memory). Two reconcilers are two handler instances with their own wall-clock
sources; the broker clock is the fake broker's and is independent of both. The same matrix
runs against PostgreSQL with fresh services and a real child death in
`tests/integration/test_m085_reconciliation_rounds_postgres.py`.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from freezegun import freeze_time
from freezegun.api import FrozenDateTimeFactory
from tests.unit import test_m085_corrective_pass_handlers as handlers
from tests.unit._m085_fakes import FakeBroker, FakeReconciliationRounds, FakeView

from empirical_platform.decision_candidate.paper_execution import (
    MINIMUM_CONSECUTIVE_NOT_FOUND_OBSERVATIONS,
    MINIMUM_SECONDS_BEFORE_NOT_FOUND_COUNTS,
    PaperExecutionState,
    ReconciliationRoundOutcome,
    absence_evaluation,
    consecutive_not_found_rounds,
    waiting_lower_bound_seconds,
)
from empirical_platform.shared.brokerage.paper_time import PaperTimeReading
from empirical_platform.usecases.paper_execution import (
    ReconcilePaperOrderCommand,
    ReconcilePaperOrderHandler,
)

_NOT_FOUND = (404, None, '{"code": 40410000, "message": "order not found"}')
_SERVER_ERROR = (500, None, '{"code": 50010000, "message": "internal server error"}')


@pytest.fixture(autouse=True)
def frozen() -> Iterator[FrozenDateTimeFactory]:
    with freeze_time(handlers._NOW) as clock:
        yield clock


class _BrokerWithItsOwnClock(FakeBroker):
    """The broker's clock is set by the test; it is NOT any reconciler's wall clock."""

    def __init__(self) -> None:
        super().__init__()
        self.broker_utc: datetime = handlers._NOW
        self.clock_round_trip_seconds = 0.0
        self.clock_raises: BaseException | None = None

    def fetch_clock(self) -> Any:  # noqa: ANN401 - FakeClock
        if self.clock_raises is not None:
            raise self.clock_raises
        clock = super().fetch_clock()
        clock.timestamp = self.broker_utc
        return clock


class _Wall:
    """One reconciler's wall clock: the broker clock plus a fixed offset, with a monotonic
    clock that can be made to advance during the broker-clock fetch (a round trip)."""

    def __init__(self, broker: _BrokerWithItsOwnClock, offset_seconds: float) -> None:
        self._broker = broker
        self._offset = timedelta(seconds=offset_seconds)
        self._monotonic = 1000.0

    @property
    def utc(self) -> datetime:
        return self._broker.broker_utc + self._offset

    def read(self) -> PaperTimeReading:
        # Monotonic time advances only when a test makes a round trip take time; an
        # instantaneous fake trip yields a zero-width broker interval.
        return PaperTimeReading(self.utc, self._monotonic)


def _world() -> dict[str, Any]:
    world = handlers._world(broker=_BrokerWithItsOwnClock())
    handlers._authorize(world)
    return world


def _ambiguous_dispatch(world: dict[str, Any]) -> None:
    broker = world["broker"]
    broker.submit_status = 503
    broker.submit_body = '{"code": 50310000, "message": "unavailable"}'
    result = handlers._submit(world)
    assert result.attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN
    assert len(broker.submitted) == 1
    broker.submit_status = 200


def _reconciler(
    world: dict[str, Any], wall: _Wall, rounds: object | None = None
) -> ReconcilePaperOrderHandler:
    return ReconcilePaperOrderHandler(
        attempts=world["attempts"],
        acknowledgements=world["acknowledgements"],
        events=world["events"],
        broker=world["broker"],
        authorizations=world["authorizations"],
        previews=world["previews"],
        rounds=rounds if rounds is not None else world["rounds"],  # type: ignore[arg-type]
        time_source=wall,
    )


def _round(
    world: dict[str, Any],
    *,
    broker_seconds: float,
    answer: tuple[int, object | None, str] | BaseException,
    wall_offset: float = 0.0,
    rounds: object | None = None,
    round_trip_seconds: float = 0.0,
) -> Any:  # noqa: ANN401 - ExecutionAttempt or the raised exception
    """One reconciliation round: the broker clock reads `_NOW + broker_seconds`; the reconciler's
    wall clock reads that plus `wall_offset`. Returns the attempt, or the exception raised."""
    broker: _BrokerWithItsOwnClock = world["broker"]
    broker.broker_utc = handlers._NOW + timedelta(seconds=broker_seconds)
    wall = _Wall(broker, wall_offset)
    if round_trip_seconds:
        original_fetch = broker.fetch_clock

        def slow_fetch() -> Any:  # noqa: ANN401
            wall._monotonic += round_trip_seconds  # the trip takes this long on the host
            return original_fetch()

        broker.fetch_clock = slow_fetch  # type: ignore[method-assign]
    if isinstance(answer, BaseException):
        broker.lookup_raises = answer
    else:
        broker.lookup_sequence = [answer]
    try:
        return _reconciler(world, wall, rounds).handle(
            ReconcilePaperOrderCommand(intent_governance_id="INT-1", at=wall.utc)
        )
    except Exception as error:  # noqa: BLE001 - returned for inspection
        return error
    finally:
        broker.lookup_raises = None
        if round_trip_seconds:
            broker.fetch_clock = original_fetch  # type: ignore[method-assign]


def _attempt(world: dict[str, Any]) -> Any:  # noqa: ANN401
    return world["attempts"].for_intent("INT-1")


def _rounds(world: dict[str, Any]) -> list[tuple[int, str | None]]:
    return [
        (r.sequence, None if r.outcome is None else r.outcome.value)
        for r in world["rounds"].for_attempt("ATT-1")
    ]


def _events(world: dict[str, Any]) -> list[str]:
    return [e.event_type for e in world["events"].rows if e.attempt_id is not None]


# ---------------------------------------------------------------------------
# Positive control: genuine consecutive negatives with justified time still resolve
# ---------------------------------------------------------------------------


def test_two_consecutive_not_found_rounds_sixty_broker_seconds_apart_resolve() -> None:
    world = _world()
    _ambiguous_dispatch(world)
    assert (
        _round(world, broker_seconds=61, answer=_NOT_FOUND).state
        is PaperExecutionState.SUBMISSION_UNKNOWN
    )
    resolved = _round(world, broker_seconds=121, answer=_NOT_FOUND)
    assert resolved.state is PaperExecutionState.REJECTED
    assert resolved.failure_code == "NOT_FOUND_AT_BROKER"
    assert _rounds(world) == [(1, "NOT_FOUND"), (2, "NOT_FOUND")]
    assert "RECONCILE_RESOLVED_NOT_FOUND" in _events(world)
    assert len(world["broker"].submitted) == 1 and world["broker"].cancelled == []


def test_the_policy_thresholds_are_unchanged() -> None:
    assert MINIMUM_CONSECUTIVE_NOT_FOUND_OBSERVATIONS == 2
    assert MINIMUM_SECONDS_BEFORE_NOT_FOUND_COUNTS == 60


# ---------------------------------------------------------------------------
# Q-2: a failed lookup whose failure could not be persisted no longer disappears
# ---------------------------------------------------------------------------


def test_q2_a_failed_round_whose_outcome_write_fails_stays_incomplete_and_blocks_resolution() -> (
    None
):
    world = _world()
    _ambiguous_dispatch(world)
    broker = world["broker"]
    assert (
        _round(world, broker_seconds=61, answer=_NOT_FOUND).state
        is PaperExecutionState.SUBMISSION_UNKNOWN
    )
    # Round 2: the lookup raises AND the completion write raises.
    world["rounds"].complete_raises = RuntimeError("database unavailable")
    error = _round(world, broker_seconds=121, answer=RuntimeError("connection reset"))
    assert isinstance(error, RuntimeError)
    world["rounds"].complete_raises = None
    assert _rounds(world) == [(1, "NOT_FOUND"), (2, None)], "the STARTED round is the durable trace"
    # A "restarted process" (a fresh handler over the same persisted fakes) sees 404 again.
    third = _round(world, broker_seconds=181, answer=_NOT_FOUND)
    assert third.state is PaperExecutionState.SUBMISSION_UNKNOWN, "an incomplete round was ignored"
    assert _rounds(world) == [(1, "NOT_FOUND"), (2, None), (3, "NOT_FOUND")]
    assert "RECONCILE_ROUND_INCOMPLETE" in _events(world)
    assert consecutive_not_found_rounds(world["rounds"].for_attempt("ATT-1")) == 1
    assert not _attempt(world).is_terminal and len(broker.submitted) == 1
    # It stays that way however many 404s follow: unfinished work is never assumed absent.
    for seconds in (300, 400):
        assert _round(world, broker_seconds=seconds, answer=_NOT_FOUND).state is (
            PaperExecutionState.SUBMISSION_UNKNOWN
        )


def test_q2_when_beginning_the_round_fails_no_lookup_is_made() -> None:
    world = _world()
    _ambiguous_dispatch(world)
    broker = world["broker"]
    lookups_before = list(broker.lookups)
    world["rounds"].begin_raises = RuntimeError("database unavailable")
    error = _round(world, broker_seconds=61, answer=_NOT_FOUND)
    assert isinstance(error, RuntimeError)
    assert broker.lookups == lookups_before, "a lookup ran under an unproven round"
    assert _rounds(world) == []
    assert world["acknowledgements"].for_attempt("ATT-1")[-1].kind == "SUBMIT"


def test_q2_a_response_whose_completion_write_fails_leaves_the_round_incomplete() -> None:
    world = _world()
    _ambiguous_dispatch(world)
    assert (
        _round(world, broker_seconds=61, answer=_NOT_FOUND).state
        is PaperExecutionState.SUBMISSION_UNKNOWN
    )
    world["rounds"].complete_raises = RuntimeError("database unavailable")
    error = _round(world, broker_seconds=121, answer=_NOT_FOUND)
    assert isinstance(error, RuntimeError)
    world["rounds"].complete_raises = None
    # The acknowledgement was recorded (the broker did answer) but the round is not complete.
    acks = [a for a in world["acknowledgements"].for_attempt("ATT-1") if a.kind == "RECONCILE"]
    assert len(acks) == 2
    assert _rounds(world) == [(1, "NOT_FOUND"), (2, None)]
    assert (
        _round(world, broker_seconds=181, answer=_NOT_FOUND).state
        is PaperExecutionState.SUBMISSION_UNKNOWN
    )
    assert "RECONCILE_ROUND_INCOMPLETE" in _events(world)


def test_q2_completion_cannot_be_repeated_or_rewritten() -> None:
    world = _world()
    _ambiguous_dispatch(world)
    _round(world, broker_seconds=61, answer=_NOT_FOUND)
    (round_,) = world["rounds"].for_attempt("ATT-1")
    with pytest.raises(ValueError, match="already complete"):
        world["rounds"].complete(
            round_.round_id, outcome=ReconciliationRoundOutcome.FOUND, completed_at=handlers._NOW
        )
    assert _rounds(world) == [(1, "NOT_FOUND")]
    with pytest.raises(ValueError, match="no reconciliation round"):
        world["rounds"].complete(
            "RND-ATT-1-99", outcome=ReconciliationRoundOutcome.FOUND, completed_at=handlers._NOW
        )


# ---------------------------------------------------------------------------
# Q-4: two reconcilers with skewed wall clocks; the broker clock is the time domain
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("skew", [-120.0, 120.0], ids=["reconciler-B-lags", "reconciler-B-leads"])
def test_q4_a_failure_recorded_by_a_skewed_reconciler_still_breaks_the_run(skew: float) -> None:
    world = _world()
    _ambiguous_dispatch(world)
    assert (
        _round(world, broker_seconds=61, answer=_NOT_FOUND).state
        is PaperExecutionState.SUBMISSION_UNKNOWN
    )
    error = _round(
        world, broker_seconds=121, answer=RuntimeError("connection reset"), wall_offset=skew
    )
    assert isinstance(error, RuntimeError)
    third = _round(world, broker_seconds=181, answer=_NOT_FOUND)
    assert third.state is PaperExecutionState.SUBMISSION_UNKNOWN, (
        f"skew {skew:+.0f}s resolved early"
    )
    assert _rounds(world) == [(1, "NOT_FOUND"), (2, "FAILED"), (3, "NOT_FOUND")]
    assert consecutive_not_found_rounds(world["rounds"].for_attempt("ATT-1")) == 1


@pytest.mark.parametrize("skew", [-120.0, 120.0], ids=["reconciler-B-lags", "reconciler-B-leads"])
def test_q4_a_positive_observation_by_a_skewed_reconciler_is_never_undone_by_absence(
    skew: float,
) -> None:
    world = _world()
    _ambiguous_dispatch(world)
    identity = world["authorizations"].latest_for_intent("INT-1").client_order_id
    assert (
        _round(world, broker_seconds=61, answer=_NOT_FOUND).state
        is PaperExecutionState.SUBMISSION_UNKNOWN
    )
    found = (
        200,
        FakeView(client_order_id=identity, broker_order_id="broker-1", status="new"),
        "{}",
    )
    observed = _round(world, broker_seconds=121, answer=found, wall_offset=skew)
    # This attempt has lineage (its POST left) and the terms match: legitimate recovery.
    assert observed.broker_order_id == "broker-1" and not observed.is_terminal
    later = _round(world, broker_seconds=181, answer=_NOT_FOUND)
    assert later.state is observed.state and later.broker_order_id == "broker-1"
    assert "RECONCILE_NOT_FOUND_KNOWN_ORDER" in _events(world)
    assert _rounds(world) == [(1, "NOT_FOUND"), (2, "FOUND"), (3, "NOT_FOUND")]


def test_q4_a_leading_host_clock_cannot_manufacture_the_waiting_interval() -> None:
    """Round 1 by reconciler A (wall clock = broker clock); round 2, ten broker-seconds
    later, by reconciler B whose wall clock leads by 120 s. B's wall clock says 130 s passed
    since round 1; the broker clock says 10 s. Only the broker clock may be believed."""
    world = _world()
    _ambiguous_dispatch(world)
    assert _round(world, broker_seconds=5, answer=_NOT_FOUND, wall_offset=0).state is (
        PaperExecutionState.SUBMISSION_UNKNOWN
    )
    second = _round(world, broker_seconds=15, answer=_NOT_FOUND, wall_offset=120)
    assert second.state is PaperExecutionState.SUBMISSION_UNKNOWN, (
        "host wall time counted as waiting"
    )
    assert waiting_lower_bound_seconds(world["rounds"].for_attempt("ATT-1")) == 10.0
    assert "RECONCILE_NOT_FOUND_INSUFFICIENT" in _events(world)
    # Sixty broker seconds after the anchor, it resolves -- whatever the host clock says.
    resolved = _round(world, broker_seconds=65, answer=_NOT_FOUND, wall_offset=-3600)
    assert resolved.state is PaperExecutionState.REJECTED


def test_q4_interval_uncertainty_straddling_the_threshold_waits_for_the_lower_bound() -> None:
    """The anchor round's clock fetch took 10 s, so its broker interval is [t, t+10]. The
    conservative bound subtracts the anchor's LATEST reading."""
    world = _world()
    _ambiguous_dispatch(world)
    assert _round(world, broker_seconds=0, answer=_NOT_FOUND, round_trip_seconds=10).state is (
        PaperExecutionState.SUBMISSION_UNKNOWN
    )
    rounds = world["rounds"].for_attempt("ATT-1")
    assert (rounds[0].broker_latest_at - rounds[0].broker_earliest_at).total_seconds() == 10.0
    # 65 s after the anchor's timestamp, but only 55 s after its latest possible reading.
    straddling = _round(world, broker_seconds=65, answer=_NOT_FOUND)
    assert straddling.state is PaperExecutionState.SUBMISSION_UNKNOWN
    assert waiting_lower_bound_seconds(world["rounds"].for_attempt("ATT-1")) == 55.0
    resolved = _round(world, broker_seconds=70, answer=_NOT_FOUND)
    assert resolved.state is PaperExecutionState.REJECTED
    assert waiting_lower_bound_seconds(world["rounds"].for_attempt("ATT-1")) == 60.0


def test_q4_a_broker_clock_that_reads_backwards_is_not_trusted_for_the_interval() -> None:
    world = _world()
    _ambiguous_dispatch(world)
    _round(world, broker_seconds=200, answer=_NOT_FOUND)
    second = _round(world, broker_seconds=100, answer=_NOT_FOUND)  # earlier than the anchor
    assert second.state is PaperExecutionState.SUBMISSION_UNKNOWN
    assert waiting_lower_bound_seconds(world["rounds"].for_attempt("ATT-1")) is None
    assert "RECONCILE_TIME_EVIDENCE_INSUFFICIENT" in _events(world)


def test_legacy_acknowledgements_without_rounds_never_count_toward_resolution() -> None:
    """An attempt reconciled before the round journal existed: two 404 acknowledgements are on
    record but no rounds. They are evidence for operators, not rounds; resolution needs two new
    completed rounds with justified broker time."""
    world = _world()
    _ambiguous_dispatch(world)
    from empirical_platform.decision_candidate.paper_execution import BrokerAcknowledgement

    for sequence in (2, 3):
        world["acknowledgements"].append(
            BrokerAcknowledgement(
                acknowledgement_id=f"ACK-ATT-1-{sequence}",
                attempt_id="ATT-1",
                sequence=sequence,
                kind="RECONCILE",
                observed_at=handlers._NOW,
                http_status=404,
                broker_order_id=None,
                broker_status=None,
                client_order_id_echo=None,
                payload_digest="a" * 64,
                sanitized_payload="{}",
            )
        )
    first = _round(world, broker_seconds=61, answer=_NOT_FOUND)
    assert first.state is PaperExecutionState.SUBMISSION_UNKNOWN
    assert _rounds(world) == [(1, "NOT_FOUND")]
    assert (
        _round(world, broker_seconds=121, answer=_NOT_FOUND).state is PaperExecutionState.REJECTED
    )


def test_a_failed_broker_clock_fetch_makes_the_round_failed_without_time_evidence() -> None:
    world = _world()
    _ambiguous_dispatch(world)
    world["broker"].clock_raises = RuntimeError("clock unavailable")
    error = _round(world, broker_seconds=61, answer=_NOT_FOUND)
    assert isinstance(error, RuntimeError)
    world["broker"].clock_raises = None
    assert _rounds(world) == [(1, "FAILED")]
    (failed,) = world["rounds"].for_attempt("ATT-1")
    assert not failed.has_broker_interval
    # Two clean rounds afterwards still resolve, anchored on the first with an interval.
    assert (
        _round(world, broker_seconds=121, answer=_NOT_FOUND).state
        is PaperExecutionState.SUBMISSION_UNKNOWN
    )
    assert (
        _round(world, broker_seconds=181, answer=_NOT_FOUND).state is PaperExecutionState.REJECTED
    )


# ---------------------------------------------------------------------------
# Concurrency and finalisation
# ---------------------------------------------------------------------------


class _RoundsWithAnInterloper:
    """The rounds repository, except that just before the finalising re-validation another
    process acts: it completes an earlier in-flight round, or adds a round of its own."""

    def __init__(self, inner: FakeReconciliationRounds, interlope: Callable[[], None]) -> None:
        self._inner = inner
        self._interlope = interlope
        self.interloped = False

    def resolve_not_found(self, **kwargs: Any) -> Any:  # noqa: ANN401
        if not self.interloped:
            self.interloped = True
            self._interlope()
        return self._inner.resolve_not_found(**kwargs)

    def __getattr__(self, name: str) -> Any:  # noqa: ANN401
        return getattr(self._inner, name)


def test_a_delayed_earlier_round_blocks_later_negatives_until_it_completes() -> None:
    world = _world()
    _ambiguous_dispatch(world)
    attempt = _attempt(world)
    # Process B begins round 1 and stalls (its answer is delayed).
    stalled = world["rounds"].begin(
        attempt=attempt, account_reference="ref:x", started_at=handlers._NOW
    )
    assert stalled.sequence == 1
    # Process A runs two clean 404 rounds sixty broker-seconds apart.
    assert (
        _round(world, broker_seconds=61, answer=_NOT_FOUND).state
        is PaperExecutionState.SUBMISSION_UNKNOWN
    )
    third = _round(world, broker_seconds=121, answer=_NOT_FOUND)
    assert third.state is PaperExecutionState.SUBMISSION_UNKNOWN, "an in-flight round was ignored"
    assert "RECONCILE_ROUND_INCOMPLETE" in _events(world)
    # B's delayed answer arrives: the order EXISTS. It is recorded against B's own round.
    world["rounds"].complete(
        stalled.round_id,
        outcome=ReconciliationRoundOutcome.FOUND,
        completed_at=handlers._NOW,
        acknowledgement_sequence=None,
    )
    assert _rounds(world) == [(1, "FOUND"), (2, "NOT_FOUND"), (3, "NOT_FOUND")]
    # The FOUND round breaks the run by SEQUENCE even though it completed last ...
    assert consecutive_not_found_rounds(world["rounds"].for_attempt("ATT-1")) == 2
    # ... and, being positive evidence, it forbids absence resolution for good: however
    # many completed 404 rounds follow, a FOUND round on record is never overridden.
    for seconds in (181, 400):
        assert (
            _round(world, broker_seconds=seconds, answer=_NOT_FOUND).state
            is PaperExecutionState.SUBMISSION_UNKNOWN
        )
    assert "RECONCILE_FOUND_ROUND_WITHOUT_OBSERVATION" in _events(world)
    assert "RECONCILE_RESOLVED_NOT_FOUND" not in _events(world)
    assert len(world["broker"].submitted) == 1 and world["broker"].cancelled == []


def test_positive_evidence_arriving_during_finalisation_prevents_the_rejection() -> None:
    world = _world()
    _ambiguous_dispatch(world)
    identity = world["authorizations"].latest_for_intent("INT-1").client_order_id
    assert (
        _round(world, broker_seconds=61, answer=_NOT_FOUND).state
        is PaperExecutionState.SUBMISSION_UNKNOWN
    )

    def another_process_observes_the_order() -> None:
        world["broker"].lookup_sequence = [
            (
                200,
                FakeView(client_order_id=identity, broker_order_id="broker-late", status="new"),
                "{}",
            )
        ]
        _reconciler(world, _Wall(world["broker"], 0.0)).handle(
            ReconcilePaperOrderCommand(intent_governance_id="INT-1", at=world["broker"].broker_utc)
        )

    interloper = _RoundsWithAnInterloper(world["rounds"], another_process_observes_the_order)
    result = _round(world, broker_seconds=121, answer=_NOT_FOUND, rounds=interloper)
    assert result.state is not PaperExecutionState.REJECTED
    assert result.broker_order_id == "broker-late", "the late positive evidence was honoured"
    assert "RECONCILE_RESOLUTION_REVALIDATION_FAILED" in _events(world)
    assert "RECONCILE_RESOLVED_NOT_FOUND" not in _events(world)
    assert len(world["broker"].submitted) == 1


def test_a_round_added_after_the_snapshot_makes_the_snapshot_stale() -> None:
    world = _world()
    _ambiguous_dispatch(world)
    assert (
        _round(world, broker_seconds=61, answer=_NOT_FOUND).state
        is PaperExecutionState.SUBMISSION_UNKNOWN
    )

    def another_process_begins_a_round() -> None:
        world["rounds"].begin(
            attempt=_attempt(world), account_reference="ref:x", started_at=handlers._NOW
        )

    interloper = _RoundsWithAnInterloper(world["rounds"], another_process_begins_a_round)
    result = _round(world, broker_seconds=121, answer=_NOT_FOUND, rounds=interloper)
    assert result.state is PaperExecutionState.SUBMISSION_UNKNOWN, "finalised from a stale snapshot"
    assert "RECONCILE_RESOLUTION_REVALIDATION_FAILED" in _events(world)
    assert _rounds(world)[-1] == (3, None)


def test_concurrent_round_starts_obtain_distinct_sequences() -> None:
    world = _world()
    _ambiguous_dispatch(world)
    attempt = _attempt(world)
    begun = [
        world["rounds"].begin(attempt=attempt, account_reference="ref:x", started_at=handlers._NOW)
        for _ in range(5)
    ]
    assert sorted(r.sequence for r in begun) == [1, 2, 3, 4, 5]
    assert len({r.round_id for r in begun}) == 5


# ---------------------------------------------------------------------------
# The pure evaluation, on bare records
# ---------------------------------------------------------------------------


def test_the_evaluation_protects_bound_and_observed_orders_before_counting_anything() -> None:
    from types import SimpleNamespace

    assert not absence_evaluation(
        state=PaperExecutionState.PAPER_ACCEPTED,
        broker_order_id="b",
        acknowledgements=[],
        events=[],
        rounds=[],
    ).resolvable
    assert not absence_evaluation(
        state=PaperExecutionState.SUBMISSION_UNKNOWN,
        broker_order_id=None,
        acknowledgements=[],
        events=[SimpleNamespace(event_type="IDENTITY_OBSERVED_NOT_ATTRIBUTED")],
        rounds=[],
    ).resolvable
    empty = absence_evaluation(
        state=PaperExecutionState.SUBMISSION_UNKNOWN,
        broker_order_id=None,
        acknowledgements=[],
        events=[],
        rounds=[],
    )
    assert not empty.resolvable and empty.rounds_version == (0, 0)


def test_completed_rounds_without_broker_time_evidence_never_satisfy_the_interval() -> None:
    """Two completed NOT_FOUND rounds whose broker clock interval is absent (rows completed
    by a process that could not sample the broker clock, or legacy rows) carry no waiting
    evidence. Nothing is invented for them; the outcome stays unresolved."""
    world = _world()
    _ambiguous_dispatch(world)
    attempt = _attempt(world)
    for seconds in (61, 121):
        begun = world["rounds"].begin(
            attempt=attempt, account_reference="ref:x", started_at=handlers._NOW
        )
        world["rounds"].complete(
            begun.round_id,
            outcome=ReconciliationRoundOutcome.NOT_FOUND,
            completed_at=handlers._NOW + timedelta(seconds=seconds),
        )
    without_time = absence_evaluation(
        state=attempt.state,
        broker_order_id=None,
        acknowledgements=[],
        events=[],
        rounds=world["rounds"].for_attempt("ATT-1"),
    )
    assert not without_time.resolvable, "missing broker-time evidence was read as sufficient"
    assert without_time.consecutive_not_found == 2
    assert without_time.waiting_lower_bound_seconds is None
    assert "no compatible broker-time evidence" in without_time.reason
    # The same two rounds WITH broker-clock intervals sixty seconds apart resolve.
    from dataclasses import replace

    timed = tuple(
        replace(
            round_,
            broker_earliest_at=round_.completed_at,
            broker_latest_at=round_.completed_at,
        )
        for round_ in world["rounds"].for_attempt("ATT-1")
    )
    with_time = absence_evaluation(
        state=attempt.state, broker_order_id=None, acknowledgements=[], events=[], rounds=timed
    )
    assert with_time.waiting_lower_bound_seconds == 60.0 and with_time.resolvable


def test_time_moves_only_when_the_test_moves_it() -> None:
    # Guard for this module's own assumption: the frozen wall clock does not drift.
    before = datetime.now(UTC)
    time.sleep(0.01)
    assert datetime.now(UTC) == before
