"""REV-R1 -- a later lookup absence cannot, by itself, revoke what was positively observed.

The bounded not-found policy (`RECONCILIATION_UNKNOWN_POLICY`: at least two CONSECUTIVE
not-found observations, at least 60 s after the dispatch) exists to resolve an outcome that was
never observed. The reviewed code counted every historical 404 acknowledgement rather than the
trailing consecutive run, and applied the policy to any non-terminal state -- so it could
terminally reject a previously ACCEPTED order with a bound broker id, or an order that had been
positively observed under our identity, solely because two later lookups said 404; and a lookup
that raised left no record at all, so the 404s on either side of it read as consecutive.

Distinctions preserved here, through the production handlers over fakes:
  - never positively observed (an UNKNOWN whose broker answers were 404 only) -> the bounded
    policy applies, over the CONSECUTIVE trailing run; a 500 or a raised lookup breaks the run;
  - previously observed but not attributable -> absence records an event; state unchanged;
  - positively acknowledged and bound to this attempt -> absence records an event; state
    unchanged; the order stays visible and reconcilable;
  - a dispatcher that may still be live (SUBMISSION_IN_PROGRESS) -> never resolved by absence.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from freezegun import freeze_time
from freezegun.api import FrozenDateTimeFactory
from tests.unit import test_m085_corrective_pass_handlers as handlers
from tests.unit._m085_fakes import FakeView

from empirical_platform.decision_candidate.paper_execution import PaperExecutionState

_NOT_FOUND = (404, None, '{"code": 40410000, "message": "order not found"}')
_SERVER_ERROR = (500, None, '{"code": 50010000, "message": "internal server error"}')


@pytest.fixture(autouse=True)
def clock() -> Iterator[FrozenDateTimeFactory]:
    with freeze_time(handlers._NOW) as frozen:
        yield frozen


def _identity(world: dict[str, Any]) -> str:
    authorization = world["authorizations"].latest_for_intent("INT-1")
    assert authorization is not None
    return str(authorization.client_order_id)


def _events(world: dict[str, Any]) -> list[str]:
    return [e.event_type for e in world["events"].rows if e.attempt_id is not None]


def _acks(world: dict[str, Any]) -> list[tuple[str, int, str | None]]:
    return [(a.kind, a.http_status, a.broker_order_id) for a in world["acknowledgements"].rows]


def _historical(world: dict[str, Any]) -> tuple[int, FakeView, str]:
    return (
        200,
        FakeView(
            client_order_id=_identity(world), broker_order_id="broker-historical", status="new"
        ),
        "{}",
    )


def _unknown_after_an_ambiguous_post(world: dict[str, Any]) -> None:
    world["broker"].submit_status = 503
    world["broker"].submit_body = '{"code": 50310000, "message": "unavailable"}'
    result = handlers._submit(world)
    assert result.attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN
    assert len(world["broker"].submitted) == 1


# ---------------------------------------------------------------------------
# A. 404 -> 500 -> 404 is not two consecutive not-found observations
# ---------------------------------------------------------------------------


def test_an_unusable_answer_breaks_the_consecutive_not_found_run() -> None:
    world = handlers._world()
    handlers._authorize(world)
    _unknown_after_an_ambiguous_post(world)
    broker = world["broker"]
    code_after_dispatch = world["attempts"].for_intent("INT-1").failure_code
    broker.lookup_sequence = [_NOT_FOUND, _SERVER_ERROR, _NOT_FOUND]
    assert handlers._reconcile(world, at_seconds=61).state is PaperExecutionState.SUBMISSION_UNKNOWN
    assert (
        handlers._reconcile(world, at_seconds=120).state is PaperExecutionState.SUBMISSION_UNKNOWN
    )
    third = handlers._reconcile(world, at_seconds=180)
    assert third.state is PaperExecutionState.SUBMISSION_UNKNOWN, (
        "404 -> 500 -> 404 was counted as two consecutive not-found observations"
    )
    assert third.failure_code == code_after_dispatch, "the recorded cause was rewritten"
    assert _events(world).count("RECONCILE_NOT_FOUND_INSUFFICIENT") == 2
    assert "RECONCILE_UNUSABLE_ANSWER" in _events(world)
    assert len(broker.submitted) == 1
    # Positive control of the policy itself: a SECOND consecutive 404 now satisfies it.
    broker.lookup_sequence = [_NOT_FOUND]
    resolved = handlers._reconcile(world, at_seconds=240)
    assert resolved.state is PaperExecutionState.REJECTED
    assert resolved.failure_code == "NOT_FOUND_AT_BROKER"
    assert len(broker.submitted) == 1


def test_a_lookup_that_raises_is_recorded_and_breaks_the_run() -> None:
    world = handlers._world()
    handlers._authorize(world)
    _unknown_after_an_ambiguous_post(world)
    broker = world["broker"]
    broker.lookup_sequence = [_NOT_FOUND]
    assert handlers._reconcile(world, at_seconds=61).state is PaperExecutionState.SUBMISSION_UNKNOWN
    broker.lookup_raises = RuntimeError("connection reset")
    with pytest.raises(RuntimeError):
        handlers._reconcile(world, at_seconds=120)
    broker.lookup_raises = None
    assert "RECONCILE_LOOKUP_FAILED" in _events(world), "the failed lookup left no record"
    broker.lookup_sequence = [_NOT_FOUND]
    third = handlers._reconcile(world, at_seconds=180)
    assert third.state is PaperExecutionState.SUBMISSION_UNKNOWN, (
        "the 404s on either side of a failed lookup were counted as consecutive"
    )
    assert len(broker.submitted) == 1


# ---------------------------------------------------------------------------
# B. a previously ACCEPTED order with a bound broker id is not rejected by absence
# ---------------------------------------------------------------------------


def test_absence_never_rejects_a_previously_accepted_order() -> None:
    world = handlers._world()
    handlers._authorize(world)
    accepted = handlers._submit(world)
    assert accepted.attempt.state is PaperExecutionState.PAPER_ACCEPTED
    assert accepted.attempt.broker_order_id == "broker-1"
    broker = world["broker"]
    broker.lookup_sequence = [_NOT_FOUND, _NOT_FOUND]
    for seconds in (61, 120):
        later = handlers._reconcile(world, at_seconds=seconds)
        assert later.state is PaperExecutionState.PAPER_ACCEPTED, (
            f"absence at +{seconds}s changed a known accepted order to {later.state.value}"
        )
        assert later.broker_order_id == "broker-1", "the broker identity was erased"
    assert _events(world).count("RECONCILE_NOT_FOUND_KNOWN_ORDER") == 2
    assert "RECONCILE_RESOLVED_NOT_FOUND" not in _events(world)
    # Still reconcilable: when the broker answers again, the lifecycle continues.
    broker.lookup_sequence = [
        (
            200,
            FakeView(client_order_id=_identity(world), broker_order_id="broker-1", status="filled"),
            "{}",
        )
    ]
    assert handlers._reconcile(world, at_seconds=180).state is PaperExecutionState.FILLED
    assert len(broker.submitted) == 1


# ---------------------------------------------------------------------------
# C. a positive observation (not attributed) is not discarded by later absence
# ---------------------------------------------------------------------------


def test_absence_never_discards_a_prior_positive_observation() -> None:
    world = handlers._world()
    handlers._authorize(world)
    broker = world["broker"]
    # An inconclusive pre-send lookup: UNKNOWN, nothing sent, no send-boundary record.
    broker.lookup_sequence = [_SERVER_ERROR]
    first = handlers._submit(world)
    assert first.attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN
    assert first.attempt.failure_code == "IDENTITY_UNRESOLVED_UNSENT"
    assert broker.submitted == []
    broker.lookup_sequence = [_NOT_FOUND, _historical(world), _NOT_FOUND]
    assert handlers._reconcile(world, at_seconds=61).state is PaperExecutionState.SUBMISSION_UNKNOWN
    observed = handlers._reconcile(world, at_seconds=120)
    assert observed.state is PaperExecutionState.SUBMISSION_UNKNOWN
    assert observed.broker_order_id is None
    assert "IDENTITY_OBSERVED_NOT_ATTRIBUTED" in _events(world)
    third = handlers._reconcile(world, at_seconds=180)
    assert third.state is PaperExecutionState.SUBMISSION_UNKNOWN, (
        "a later 404 terminally rejected an attempt whose identity was positively observed"
    )
    assert "RECONCILE_NOT_FOUND_AFTER_OBSERVATION" in _events(world)
    assert "RECONCILE_RESOLVED_NOT_FOUND" not in _events(world)
    # Still visible and reconcilable, still never attributed, never resent.
    broker.lookup_sequence = [_NOT_FOUND, _NOT_FOUND]
    for seconds in (300, 600):
        assert handlers._reconcile(world, at_seconds=seconds).state is (
            PaperExecutionState.SUBMISSION_UNKNOWN
        )
    assert handlers._submit(world).dispatched is False
    assert broker.submitted == []


# ---------------------------------------------------------------------------
# Positive controls: the policy still resolves what was NEVER observed
# ---------------------------------------------------------------------------


def test_two_consecutive_not_found_answers_still_resolve_a_never_observed_unknown() -> None:
    world = handlers._world()
    handlers._authorize(world)
    _unknown_after_an_ambiguous_post(world)
    world["broker"].lookup_sequence = [_NOT_FOUND, _NOT_FOUND]
    assert handlers._reconcile(world, at_seconds=61).state is PaperExecutionState.SUBMISSION_UNKNOWN
    # Q-4: 60 s on the broker clock after the FIRST round (the anchor), not after dispatch.
    resolved = handlers._reconcile(world, at_seconds=121)
    assert resolved.state is PaperExecutionState.REJECTED
    assert resolved.failure_code == "NOT_FOUND_AT_BROKER"
    assert "RECONCILE_RESOLVED_NOT_FOUND" in _events(world)
    assert len(world["broker"].submitted) == 1


def test_a_possibly_live_dispatcher_is_still_never_resolved_by_absence() -> None:
    world = handlers._world()
    handlers._authorize(world)
    world["broker"].submit_raises = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        handlers._submit(world)
    world["broker"].submit_raises = None
    world["broker"].lookup_sequence = [_NOT_FOUND] * 3
    for seconds in (61, 120, 900):
        assert handlers._reconcile(world, at_seconds=seconds).state is (
            PaperExecutionState.SUBMISSION_IN_PROGRESS
        )
    assert _events(world).count("RECONCILE_NOT_FOUND_DISPATCH_MAY_BE_LIVE") == 3
