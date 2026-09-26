"""L1 -- crash-consistent attempt lineage: a death before the send-capable boundary is not lineage.

REVIEW FINDING L1 (HIGH). `SUBMISSION_IN_PROGRESS` is persisted before `before_send` runs, and
`attempt_may_have_transmitted` treated that state as lineage unless an UNSENT marker had been
persisted. A process that dies during the pre-send identity lookup, or after finding an
existing order but before persisting the observation, leaves neither marker -- so reconciliation
could attribute a historical order under the derived identity to an attempt that transmitted
ZERO requests. This is a crash-consistency gap between preparation and possible transmission,
not a duplicate-order claim.

The invariant pinned here: attribution requires a persisted record that THIS attempt reached
the phase in which transmission was possible -- the identity verified absent at the broker and
every preparatory read complete -- bound to the attempt, its authorization, request fingerprint,
account and identity (`SEND_BOUNDARY_ENTERED`). The absence of an unsent marker proves nothing.

Abrupt death is modelled by `_ProcessDied(BaseException)`: no `except Exception` in the handler,
the fake transport or the real transport catches it, so the process state at that instant is
exactly what the persisted rows say. A fresh reconciliation handler stands in for the restarted
process. Positive control: our POST really leaves, the process dies before the acknowledgement
is persisted, and legitimate recovery attributes the order without resending. The same three
boundaries are reproduced with a REAL child-process death against PostgreSQL in
`tests/integration/test_m085_pre_send_crash_postgres.py`.

Fakes only; the POST count is the fake broker's `submitted` list.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from freezegun import freeze_time
from freezegun.api import FrozenDateTimeFactory
from tests.unit import test_m085_corrective_pass_handlers as handlers
from tests.unit._m085_fakes import FakeView

from empirical_platform.decision_candidate.paper_execution import (
    SEND_BOUNDARY_EVENT_TYPE,
    PaperExecutionState,
    attempt_may_have_transmitted,
    send_boundary_binding,
)


class _ProcessDied(BaseException):
    """The process is gone. Nothing after the raise point runs; nothing is persisted."""


@pytest.fixture
def clock() -> Iterator[FrozenDateTimeFactory]:
    with freeze_time(handlers._NOW) as frozen:
        yield frozen


def _identity(world: dict[str, Any]) -> str:
    authorization = world["authorizations"].latest_for_intent("INT-1")
    assert authorization is not None
    return str(authorization.client_order_id)


def _events(world: dict[str, Any]) -> list[str]:
    return [event.event_type for event in world["events"].rows]


def _attempt(world: dict[str, Any]) -> Any:  # noqa: ANN401 - ExecutionAttempt
    attempt = world["attempts"].for_intent("INT-1")
    assert attempt is not None
    return attempt


def _historical_order(world: dict[str, Any]) -> FakeView:
    """An order the broker already holds under OUR derived identity, with the authorized terms."""
    return FakeView(
        client_order_id=_identity(world), broker_order_id="broker-historical", status="filled"
    )


def _die_on_first(repository: Any, method: str) -> None:  # noqa: ANN401 - fake repository
    """The process dies at the first call of `repository.method`; later calls (the restarted
    process) behave normally."""
    original = getattr(repository, method)
    state = {"died": False}

    def once(*args: object, **kwargs: object) -> object:
        if not state["died"]:
            state["died"] = True
            raise _ProcessDied
        return original(*args, **kwargs)

    setattr(repository, method, once)


def _restart_and_reconcile(world: dict[str, Any], *, after_seconds: int = 61) -> Any:  # noqa: ANN401
    return handlers._reconcile(world, at_seconds=after_seconds)


def _assert_observed_not_attributed(world: dict[str, Any], attempt: Any) -> None:  # noqa: ANN401
    assert world["broker"].submitted == [], "a POST left"
    assert world["broker"].cancelled == [], "a cancellation was sent"
    assert attempt.broker_order_id is None, "a historical order was attributed"
    assert attempt.state in {
        PaperExecutionState.SUBMISSION_IN_PROGRESS,
        PaperExecutionState.SUBMISSION_UNKNOWN,
    }, attempt.state
    assert "IDENTITY_OBSERVED_NOT_ATTRIBUTED" in _events(world), _events(world)
    assert "RECONCILED" not in _events(world)


# ---------------------------------------------------------------------------
# A. death DURING the pre-send identity lookup; a historical order exists
# ---------------------------------------------------------------------------


def test_a_death_during_the_pre_send_lookup_leaves_no_lineage(clock: FrozenDateTimeFactory) -> None:
    world = handlers._world()
    handlers._authorize(world)
    broker = world["broker"]
    broker.lookup_view = _historical_order(world)
    broker.lookup_raises = _ProcessDied()  # the process dies inside the lookup
    with pytest.raises(_ProcessDied):
        handlers._submit(world)

    # What the durable record says at the instant of death.
    died = _attempt(world)
    assert died.state is PaperExecutionState.SUBMISSION_IN_PROGRESS
    assert died.failure_code is None
    assert broker.submitted == [], "no POST was ever attempted"
    assert SEND_BOUNDARY_EVENT_TYPE not in _events(world)
    assert not attempt_may_have_transmitted(died, world["events"].rows), (
        "IN_PROGRESS with nothing persisted after it must not count as lineage"
    )

    # The restarted process reconciles; the broker still holds the historical order.
    broker.lookup_raises = None
    recovered = _restart_and_reconcile(world)
    _assert_observed_not_attributed(world, recovered)
    # Still visible and unresolved later; a fresh dispatch sends nothing.
    assert _restart_and_reconcile(world, after_seconds=300).broker_order_id is None
    assert handlers._submit(world).dispatched is False
    assert broker.submitted == []


def test_a_death_before_the_lookup_even_started_leaves_no_lineage(
    clock: FrozenDateTimeFactory,
) -> None:
    # The process dies right after SUBMISSION_IN_PROGRESS is persisted, before any read.
    world = handlers._world()
    handlers._authorize(world)
    broker = world["broker"]
    broker.lookup_view = _historical_order(world)
    original = world["attempts"].transition

    def transition(**kwargs: object) -> object:
        result = original(**kwargs)
        if kwargs.get("target") is PaperExecutionState.SUBMISSION_IN_PROGRESS:
            raise _ProcessDied
        return result

    world["attempts"].transition = transition
    with pytest.raises(_ProcessDied):
        handlers._submit(world)
    world["attempts"].transition = original
    assert broker.lookups == [] and broker.submitted == []
    _assert_observed_not_attributed(world, _restart_and_reconcile(world))


# ---------------------------------------------------------------------------
# B. the historical order is FOUND, the process dies before the observation is persisted
# ---------------------------------------------------------------------------


def test_a_death_after_discovery_before_persistence_leaves_no_lineage(
    clock: FrozenDateTimeFactory,
) -> None:
    world = handlers._world()
    handlers._authorize(world)
    broker = world["broker"]
    broker.lookup_view = _historical_order(world)
    # The first persistence step of `_identity_observed` is the acknowledgement row.
    _die_on_first(world["acknowledgements"], "append")
    with pytest.raises(_ProcessDied):
        handlers._submit(world)

    died = _attempt(world)
    assert died.state is PaperExecutionState.SUBMISSION_IN_PROGRESS
    assert world["acknowledgements"].rows == [] and broker.submitted == []
    assert "IDENTITY_OBSERVED_BEFORE_SEND" not in _events(world)
    assert SEND_BOUNDARY_EVENT_TYPE not in _events(world)
    assert not attempt_may_have_transmitted(died, world["events"].rows)

    _assert_observed_not_attributed(world, _restart_and_reconcile(world))


# ---------------------------------------------------------------------------
# C. POSITIVE CONTROL -- our POST left, the process died before the acknowledgement
# ---------------------------------------------------------------------------


def test_our_own_post_then_death_before_acknowledgement_is_recovered_without_resending(
    clock: FrozenDateTimeFactory,
) -> None:
    world = handlers._world()
    handlers._authorize(world)
    broker = world["broker"]
    # The fake broker answers the lookup with exactly what it RECEIVED, so the order it
    # reports after the crash is the one this attempt sent.
    _die_on_first(world["acknowledgements"], "append")  # first append = the SUBMIT ack
    with pytest.raises(_ProcessDied):
        handlers._submit(world)

    died = _attempt(world)
    assert died.state is PaperExecutionState.SUBMISSION_IN_PROGRESS
    assert len(broker.submitted) == 1, "the POST really left"
    assert SEND_BOUNDARY_EVENT_TYPE in _events(world), "the boundary was recorded before the POST"
    assert attempt_may_have_transmitted(died, world["events"].rows) is True

    recovered = _restart_and_reconcile(world)
    assert recovered.broker_order_id is not None, "legitimate recovery must attribute our order"
    assert recovered.state in {
        PaperExecutionState.PAPER_SUBMITTED,
        PaperExecutionState.PAPER_ACCEPTED,
        PaperExecutionState.FILLED,
    }
    assert "IDENTITY_OBSERVED_NOT_ATTRIBUTED" not in _events(world)
    assert len(broker.submitted) == 1, "recovery never resends"
    # And a repeated submit after the restart sends nothing either.
    repeat = handlers._submit(world)
    assert repeat.dispatched is False and len(broker.submitted) == 1


# ---------------------------------------------------------------------------
# The boundary record itself: bound field by field, never borrowed
# ---------------------------------------------------------------------------

_BOUND: dict[str, object] = {
    "attempt_id": "ATT-1",
    "authorization_id": "AUT-1",
    "request_fingerprint": "a" * 64,
    "account_reference": "ref:account",
    "client_order_id": "m085-0123456789abcdef",
    "identity_lookup_status": 404,
}


def _bare_attempt(
    state: PaperExecutionState = PaperExecutionState.SUBMISSION_IN_PROGRESS,
    failure_code: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        attempt_id="ATT-1",
        authorization_id="AUT-1",
        request_fingerprint="a" * 64,
        client_order_id="m085-0123456789abcdef",
        state=state,
        failure_code=failure_code,
    )


def _boundary_event(**overrides: object) -> SimpleNamespace:
    fields = dict(_BOUND)
    fields.update({key: value for key, value in overrides.items() if key in fields})
    return SimpleNamespace(
        event_type=str(overrides.get("event_type", SEND_BOUNDARY_EVENT_TYPE)),
        attempt_id=overrides.get("event_attempt_id", "ATT-1"),
        detail=send_boundary_binding(**fields),  # type: ignore[arg-type]
    )


def test_the_lineage_predicate_is_the_rule_the_tests_above_depend_on() -> None:
    """The domain rule, stated on a bare record: IN_PROGRESS alone is not lineage."""
    bare = _bare_attempt()
    assert attempt_may_have_transmitted(bare, []) is False
    assert (
        attempt_may_have_transmitted(bare, [SimpleNamespace(event_type="DISPATCH_CLAIMED")])
        is False
    )
    assert attempt_may_have_transmitted(bare, [_boundary_event()]) is True
    assert (
        attempt_may_have_transmitted(bare, [_boundary_event()], account_reference="ref:account")
        is True
    )
    # A legacy UNKNOWN record with a transmitted-looking code but no boundary record stays
    # unresolved rather than being backfilled with lineage.
    legacy = _bare_attempt(PaperExecutionState.SUBMISSION_UNKNOWN, "AMBIGUOUS")
    assert attempt_may_have_transmitted(legacy, []) is False
    assert attempt_may_have_transmitted(legacy, [_boundary_event()]) is True


@pytest.mark.parametrize(
    "tamper",
    [
        {"event_attempt_id": "ATT-2"},
        {"attempt_id": "ATT-2"},
        {"authorization_id": "AUT-2"},
        {"request_fingerprint": "b" * 64},
        {"client_order_id": "m085-fedcba9876543210"},
        {"identity_lookup_status": 200},
        {"account_reference": "ref:other"},
        {"event_type": "DISPATCH_CLAIMED"},
    ],
    ids=lambda tamper: next(iter(tamper)),
)
def test_a_boundary_record_that_does_not_bind_lends_no_lineage(tamper: dict[str, object]) -> None:
    event = _boundary_event(**tamper)
    assert (
        attempt_may_have_transmitted(_bare_attempt(), [event], account_reference="ref:account")
        is False
    )


def test_a_tampered_account_in_the_persisted_boundary_record_blocks_attribution(
    clock: FrozenDateTimeFactory,
) -> None:
    """Even after OUR POST left, a boundary record whose account is not the authorized one
    binds nothing: the account is part of what the phase transition was justified against."""
    world = handlers._world()
    handlers._authorize(world)
    _die_on_first(world["acknowledgements"], "append")
    with pytest.raises(_ProcessDied):
        handlers._submit(world)
    assert len(world["broker"].submitted) == 1
    rows = world["events"].rows
    index = next(i for i, e in enumerate(rows) if e.event_type == SEND_BOUNDARY_EVENT_TYPE)
    rows[index] = replace(rows[index], detail=rows[index].detail.replace("account=", "account=x-"))
    recovered = _restart_and_reconcile(world)
    assert recovered.broker_order_id is None
    assert "IDENTITY_OBSERVED_NOT_ATTRIBUTED" in _events(world)
    assert len(world["broker"].submitted) == 1


# ---------------------------------------------------------------------------
# Deaths and failures AROUND the boundary write
# ---------------------------------------------------------------------------


def test_a_death_during_the_boundary_write_leaves_no_lineage(clock: FrozenDateTimeFactory) -> None:
    world = handlers._world()
    handlers._authorize(world)
    broker = world["broker"]
    _die_on_first(world["events"], "append")  # the first event of the dispatch IS the boundary
    with pytest.raises(_ProcessDied):
        handlers._submit(world)
    died = _attempt(world)
    assert died.state is PaperExecutionState.SUBMISSION_IN_PROGRESS
    assert SEND_BOUNDARY_EVENT_TYPE not in _events(world) and broker.submitted == []
    # A historical order appears under the identity afterwards: observed, never attributed.
    broker.lookup_view = _historical_order(world)
    _assert_observed_not_attributed(world, _restart_and_reconcile(world))


def test_a_death_right_after_the_boundary_write_is_lineage_by_design(
    clock: FrozenDateTimeFactory,
) -> None:
    """The accepted window. The boundary record says: identity verified absent (404), every
    preparatory read complete, nothing left but the final checks and the POST. A death here
    leaves lineage even though no POST left -- and that is what the record is FOR: an order
    found later under this identity may be ours. What bounds it is the 404 the record carries:
    a historical order did not exist at the boundary."""
    world = handlers._world()
    handlers._authorize(world)
    broker = world["broker"]
    original = world["events"].append

    def append_then_die(event: object) -> object:
        result = original(event)
        if getattr(event, "event_type", None) == SEND_BOUNDARY_EVENT_TYPE:
            raise _ProcessDied
        return result

    world["events"].append = append_then_die
    with pytest.raises(_ProcessDied):
        handlers._submit(world)
    world["events"].append = original
    died = _attempt(world)
    assert died.state is PaperExecutionState.SUBMISSION_IN_PROGRESS and broker.submitted == []
    assert SEND_BOUNDARY_EVENT_TYPE in _events(world)
    assert attempt_may_have_transmitted(died, world["events"].rows) is True
    # Nothing at the broker: absence never resolves an in-progress attempt, nothing is sent.
    for seconds in (61, 300):
        assert handlers._reconcile(world, at_seconds=seconds).state is (
            PaperExecutionState.SUBMISSION_IN_PROGRESS
        )
    assert broker.submitted == []


def test_a_database_failure_at_the_boundary_write_is_a_definite_not_sent(
    clock: FrozenDateTimeFactory,
) -> None:
    world = handlers._world()
    handlers._authorize(world)
    original = world["events"].append
    calls = {"n": 0}

    def failing_once(event: object) -> object:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("database unavailable")
        return original(event)

    world["events"].append = failing_once
    result = handlers._submit(world)
    assert result.dispatched is False and world["broker"].submitted == []
    assert result.attempt.state is PaperExecutionState.REJECTED
    assert result.attempt.failure_code == "NOT_SENT"
    assert SEND_BOUNDARY_EVENT_TYPE not in _events(world)
    assert "DISPATCH_NOT_SENT" in _events(world)
    assert not attempt_may_have_transmitted(result.attempt, world["events"].rows)


def test_database_failures_at_the_boundary_and_at_the_refusal_leave_no_lineage(
    clock: FrozenDateTimeFactory,
) -> None:
    """The database is down for the boundary write AND for the not-sent transition: the
    handler cannot record anything, the process ends with an error, and the durable record
    is SUBMISSION_IN_PROGRESS with no boundary event -- which lends no lineage."""
    world = handlers._world()
    handlers._authorize(world)
    broker = world["broker"]
    original_append = world["events"].append
    original_transition = world["attempts"].transition

    def failing_append(event: object) -> object:
        if getattr(event, "event_type", None) == SEND_BOUNDARY_EVENT_TYPE:
            raise RuntimeError("database unavailable")
        return original_append(event)

    def failing_transition(**kwargs: object) -> object:
        if kwargs.get("target") is PaperExecutionState.REJECTED:
            raise RuntimeError("database unavailable")
        return original_transition(**kwargs)

    world["events"].append = failing_append
    world["attempts"].transition = failing_transition
    with pytest.raises(RuntimeError, match="database unavailable"):
        handlers._submit(world)
    world["events"].append = original_append
    world["attempts"].transition = original_transition
    died = _attempt(world)
    assert died.state is PaperExecutionState.SUBMISSION_IN_PROGRESS and broker.submitted == []
    broker.lookup_view = _historical_order(world)
    _assert_observed_not_attributed(world, _restart_and_reconcile(world))


# ---------------------------------------------------------------------------
# A6 is not reintroduced: the write may block; the final checks follow it
# ---------------------------------------------------------------------------


def _slow_boundary_write(world: dict[str, Any], during: Callable[[], None]) -> None:
    original = world["events"].append

    def slow(event: object) -> object:
        if getattr(event, "event_type", None) == SEND_BOUNDARY_EVENT_TYPE:
            during()
        return original(event)

    world["events"].append = slow


def test_an_authorization_expiring_during_the_boundary_write_stops_the_post(
    clock: FrozenDateTimeFactory,
) -> None:
    world = handlers._world()
    handlers._authorize(world, validity_seconds=300)
    _slow_boundary_write(world, lambda: clock.tick(timedelta(seconds=301)))
    result = handlers._submit(world)
    assert world["broker"].submitted == [], "POST left after the authorization expired"
    assert result.attempt.state is PaperExecutionState.REJECTED
    assert result.attempt.failure_code == "NOT_SENT"
    # The boundary record exists, but the unsent record outranks it.
    assert SEND_BOUNDARY_EVENT_TYPE in _events(world)
    assert not attempt_may_have_transmitted(result.attempt, world["events"].rows)


def test_the_kill_switch_engaged_during_the_boundary_write_stops_the_post(
    clock: FrozenDateTimeFactory,
) -> None:
    world = handlers._world()
    handlers._authorize(world)
    _slow_boundary_write(world, lambda: setattr(world["kill_switch"], "engaged", True))
    result = handlers._submit(world)
    assert world["broker"].submitted == [], "POST left with the kill switch engaged"
    assert result.attempt.state is PaperExecutionState.REJECTED
    assert "kill switch" in str(result.attempt.failure_detail)


# ---------------------------------------------------------------------------
# Concurrency: a reconciler looks while the dispatcher is still preparing
# ---------------------------------------------------------------------------


def test_a_concurrent_reconciliation_during_preparation_attributes_nothing(
    clock: FrozenDateTimeFactory,
) -> None:
    """While the dispatcher is inside its pre-send lookup, a reconciler (past the not-found
    window) finds the historical order: no lineage yet, so it is observed and not attributed.
    The dispatcher then sees the order itself and sends nothing."""
    world = handlers._world()
    handlers._authorize(world)
    broker = world["broker"]
    broker.lookup_view = _historical_order(world)
    original = broker.fetch_order_by_client_order_id
    seen: list[Any] = []
    entered = {"reconciler": False}

    def lookup_with_a_concurrent_reconciler(
        client_order_id: str,
    ) -> tuple[int, object | None, str]:
        # The reconciler's own lookup comes through here too: run it exactly once.
        if not entered["reconciler"]:
            entered["reconciler"] = True
            seen.append(handlers._reconcile(world, at_seconds=61))
        return original(client_order_id)

    broker.fetch_order_by_client_order_id = lookup_with_a_concurrent_reconciler
    result = handlers._submit(world)
    (concurrent,) = seen
    assert concurrent.broker_order_id is None
    assert concurrent.state is PaperExecutionState.SUBMISSION_IN_PROGRESS
    assert "IDENTITY_OBSERVED_NOT_ATTRIBUTED" in _events(world)
    assert result.dispatched is False and broker.submitted == []
    assert result.attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN
    assert result.attempt.failure_code == "IDENTITY_EXISTS_UNSENT"
    assert result.attempt.broker_order_id is None
