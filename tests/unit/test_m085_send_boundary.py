"""The final safety decision is made AFTER every slow read, immediately before the POST.

Defect A6 (found in the review of candidate `2726f6f`): the pre-send identity lookup ran as the
last step of the in-connection guard, after `final_send_refusal`, so a slow lookup let a POST
leave after the authorization expired, with the kill switch engaged, or with a stale quote.

The guarantee this suite pins is a refusal at the BOUNDED APPLICATION SEND BOUNDARY: every
potentially blocking read (identity lookup, configuration, broker clock, quote) completes
first, the kill switch is read after them, host/monotonic/broker-bounded time is sampled after
all of them, `final_send_refusal` re-validates every rule on that fresh evidence, and no
network operation sits between that decision and the transport's POST attempt. It is not a
claim of atomic control over the broker's receipt time or over events that occur after the
request leaves.

Fakes only. The POST count is the fake broker's `submitted` list, which the fake appends only
after `before_send` returned -- the same contract as the real transport.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import pytest
from freezegun import freeze_time
from freezegun.api import FrozenDateTimeFactory
from tests.unit import test_m085_corrective_pass_handlers as handlers
from tests.unit._m085_fakes import (
    FakeBroker,
    FakeClock,
    FakeConfigurations,
    FakeEvents,
    FakeIntents,
    FakeKillSwitch,
    FakeMarketData,
    FakeQuote,
    a_provenance,
    an_intent,
    time_bases_for,
)

from empirical_platform.decision_candidate.paper_execution import (
    SEND_BOUNDARY_EVENT_TYPE,
    PaperExecutionState,
)

_NOT_FOUND = '{"code": 40410000, "message": "order not found"}'
_LIMIT_SECONDS = 60  # the fixture configuration's quote-freshness limit


@pytest.fixture
def clock() -> Iterator[FrozenDateTimeFactory]:
    with freeze_time(handlers._NOW) as frozen:
        yield frozen


class _Trace:
    """Records the ORDER in which the send boundary read its inputs and sent.

    Hooks fire only once the boundary is armed -- after the dispatch was claimed and
    moved to SUBMISSION_IN_PROGRESS -- so the pre-claim gather, which reads the same
    fakes, is not what a scenario perturbs.
    """

    def __init__(self) -> None:
        self.events: list[str] = []
        self.during: dict[str, Callable[[], None]] = {}
        self.armed: Callable[[], bool] = lambda: True

    def hit(self, name: str) -> None:
        if not self.armed():
            return
        self.events.append(name)
        hook = self.during.get(name)
        if hook is not None:
            hook()


class _TracedBroker(FakeBroker):
    def __init__(self, trace: _Trace) -> None:
        super().__init__()
        self._trace = trace
        self.market_open = True

    def fetch_clock(self) -> FakeClock:
        self._trace.hit("clock")
        clock = super().fetch_clock()
        clock.is_open = self.market_open
        return clock

    def fetch_order_by_client_order_id(
        self, client_order_id: str
    ) -> tuple[int, object | None, str]:
        self._trace.hit("lookup")
        self.lookups.append(client_order_id)
        return 404, None, _NOT_FOUND

    def submit_order(  # type: ignore[override]
        self, order: object, *, before_send: Callable[[], None] | None = None
    ) -> tuple[int, object | None, str]:
        result = super().submit_order(order, before_send=before_send)  # type: ignore[arg-type]
        self._trace.hit("POST")
        return result


class _TracedKillSwitch(FakeKillSwitch):
    def __init__(self, trace: _Trace) -> None:
        super().__init__()
        self._trace = trace

    def is_engaged(self) -> bool:
        self._trace.hit("kill_switch")
        return super().is_engaged()


class _TracedMarketData(FakeMarketData):
    def __init__(self, trace: _Trace) -> None:
        super().__init__()
        self._trace = trace

    def fetch_quote(self, symbol: str) -> object | None:
        self._trace.hit("quote")
        return super().fetch_quote(symbol)


class _TracedConfigurations(FakeConfigurations):
    def __init__(self, trace: _Trace) -> None:
        super().__init__()
        self._trace = trace

    def get(self, configuration_governance_id: str, configuration_version: int) -> object:
        self._trace.hit("configuration")
        return super().get(configuration_governance_id, configuration_version)


class _TracedEvents(FakeEvents):
    """The boundary record's persistence is a step of the boundary too (L1)."""

    def __init__(self, trace: _Trace) -> None:
        super().__init__()
        self._trace = trace

    def append(self, event: object) -> object:
        if getattr(event, "event_type", None) == SEND_BOUNDARY_EVENT_TYPE:
            self._trace.hit("persist_boundary")
        return super().append(event)  # type: ignore[arg-type]


def _world(trace: _Trace) -> dict[str, Any]:
    world = handlers._world(
        broker=_TracedBroker(trace),
        kill_switch=_TracedKillSwitch(trace),
        market_data=_TracedMarketData(trace),
        configurations=_TracedConfigurations(trace),
        events=_TracedEvents(trace),
    )
    trace.armed = lambda: any(
        state is PaperExecutionState.SUBMISSION_IN_PROGRESS
        for _, state in world["attempts"].transitions
    )
    return world


def _boundary_events(trace: _Trace) -> list[str]:
    """The reads made INSIDE the send boundary: after the claim, up to and including the POST."""
    return list(trace.events)


# ---------------------------------------------------------------------------
# Positive control
# ---------------------------------------------------------------------------


def test_while_permitted_exactly_one_post_leaves(clock: FrozenDateTimeFactory) -> None:
    trace = _Trace()
    world = _world(trace)
    handlers._authorize(world)
    result = handlers._submit(world)
    assert result.dispatched is True
    assert len(world["broker"].submitted) == 1
    assert trace.events.count("POST") == 1
    assert result.attempt.state is PaperExecutionState.PAPER_ACCEPTED


def test_the_boundary_reads_everything_before_the_kill_switch_and_samples_time_last(
    clock: FrozenDateTimeFactory,
) -> None:
    trace = _Trace()
    world = _world(trace)
    handlers._authorize(world)
    handlers._submit(world)
    boundary = _boundary_events(trace)
    # Every potentially blocking read precedes the kill switch; nothing but the POST follows it.
    assert boundary[0] == "lookup"
    assert boundary[-1] == "POST"
    assert boundary[-2] == "kill_switch"
    assert {"configuration", "clock", "quote"} <= set(boundary[1:-2]), boundary
    assert "lookup" not in boundary[1:], "the identity lookup ran after the final decision"
    # CRASH-CONSISTENT LINEAGE (L1): the boundary record is written after every
    # preparatory read and BEFORE the kill switch is read -- a write that may block must
    # not sit between the final decision and the POST, nor precede the reads it vouches for.
    assert boundary.count("persist_boundary") == 1
    assert (
        max(boundary.index(read) for read in ("configuration", "clock", "quote"))
        < (boundary.index("persist_boundary"))
        < boundary.index("kill_switch")
    ), boundary


# ---------------------------------------------------------------------------
# The world changes DURING a slow read -- the POST must not leave
# ---------------------------------------------------------------------------


def _slow(seconds: int, clock: FrozenDateTimeFactory) -> Callable[[], None]:
    def hook() -> None:
        clock.tick(timedelta(seconds=seconds))

    return hook


def _engages(world_holder: dict[str, Any]) -> Callable[[], None]:
    def hook() -> None:
        world_holder["world"]["kill_switch"].engaged = True

    return hook


@pytest.mark.parametrize("slow_read", ["lookup", "configuration", "clock", "quote"])
def test_the_authorization_expiring_during_a_slow_read_stops_the_post(
    clock: FrozenDateTimeFactory, slow_read: str
) -> None:
    trace = _Trace()
    world = _world(trace)
    handlers._authorize(world, validity_seconds=300)
    trace.during[slow_read] = _slow(301, clock)
    result = handlers._submit(world)
    assert world["broker"].submitted == [], f"POST left after expiry during {slow_read}"
    assert result.attempt.state is PaperExecutionState.REJECTED
    assert result.attempt.failure_code == "NOT_SENT"


@pytest.mark.parametrize("slow_read", ["lookup", "configuration", "clock", "quote"])
def test_the_kill_switch_engaged_during_a_slow_read_stops_the_post(
    clock: FrozenDateTimeFactory, slow_read: str
) -> None:
    trace = _Trace()
    world = _world(trace)
    holder = {"world": world}
    handlers._authorize(world)
    trace.during[slow_read] = _engages(holder)
    result = handlers._submit(world)
    assert world["broker"].submitted == [], f"POST left with the switch engaged during {slow_read}"
    assert result.attempt.state is PaperExecutionState.REJECTED
    assert "kill switch" in str(result.attempt.failure_detail)


@pytest.mark.parametrize("slow_read", ["lookup", "configuration", "clock", "quote"])
def test_the_quote_going_stale_during_a_slow_read_stops_the_post(
    clock: FrozenDateTimeFactory, slow_read: str
) -> None:
    trace = _Trace()
    world = _world(trace)
    handlers._authorize(world)
    trace.during[slow_read] = _slow(_LIMIT_SECONDS + 30, clock)
    result = handlers._submit(world)
    assert world["broker"].submitted == [], f"POST left with a stale quote after {slow_read}"
    assert result.attempt.state is PaperExecutionState.REJECTED


def _world_with_intent(trace: _Trace, **intent_overrides: object) -> dict[str, Any]:
    """A world whose intent carries the given deadlines, with evidence describing THAT intent."""
    intent = an_intent(**intent_overrides)
    world = _world(trace)
    world["intents"] = FakeIntents(intent)
    world["time_bases"] = time_bases_for(a_provenance(intent))
    return world


def test_the_intent_expiring_during_the_lookup_stops_the_post(clock: FrozenDateTimeFactory) -> None:
    trace = _Trace()
    # The intent expires 30 s from now while the authorization stays valid, so the intent
    # deadline is the one that lapses during the slow lookup.
    world = _world_with_intent(trace, expires_at=handlers._NOW + timedelta(seconds=30))
    handlers._authorize(world, validity_seconds=20)
    trace.during["lookup"] = _slow(31, clock)
    result = handlers._submit(world)
    assert world["broker"].submitted == []
    assert result.attempt.state is PaperExecutionState.REJECTED
    assert "expired" in str(result.attempt.failure_detail)


def test_the_liquidation_deadline_passing_during_the_lookup_stops_the_post(
    clock: FrozenDateTimeFactory,
) -> None:
    trace = _Trace()
    world = _world_with_intent(
        trace, mandatory_liquidation_at=handlers._NOW + timedelta(seconds=30)
    )
    handlers._authorize(world, validity_seconds=20)
    trace.during["lookup"] = _slow(31, clock)
    result = handlers._submit(world)
    assert world["broker"].submitted == []
    assert result.attempt.state is PaperExecutionState.REJECTED


def test_the_market_closing_during_the_lookup_stops_the_post(clock: FrozenDateTimeFactory) -> None:
    trace = _Trace()
    world = _world(trace)
    handlers._authorize(world)

    def closes() -> None:
        world["broker"].market_open = False

    trace.during["lookup"] = closes
    result = handlers._submit(world)
    assert world["broker"].submitted == []
    assert result.attempt.state is PaperExecutionState.REJECTED
    assert "session" in str(result.attempt.failure_detail) or "closed" in str(
        result.attempt.failure_detail
    )


def test_a_quote_that_is_stale_when_read_is_refused_even_if_time_stands_still(
    clock: FrozenDateTimeFactory,
) -> None:
    trace = _Trace()
    world = _world(trace)
    handlers._authorize(world)

    class _Stale(FakeQuote):
        captured_at = handlers._NOW - timedelta(seconds=_LIMIT_SECONDS + 5)

    def stale_feed() -> None:
        world["market_data"]._quote = _Stale()  # noqa: SLF001 - test seam

    trace.during["lookup"] = stale_feed
    result = handlers._submit(world)
    assert world["broker"].submitted == []
    assert result.attempt.state is PaperExecutionState.REJECTED


def test_a_refused_send_is_terminal_not_sent_and_a_repeat_sends_nothing(
    clock: FrozenDateTimeFactory,
) -> None:
    trace = _Trace()
    world = _world(trace)
    holder = {"world": world}
    handlers._authorize(world)
    trace.during["quote"] = _engages(holder)
    first = handlers._submit(world)
    assert first.dispatched is False
    assert world["broker"].submitted == []
    # No reprepared send may reuse the earlier guard result: the attempt is terminal and a
    # repeat is refused before any read.
    events_before = len(trace.events)
    assert handlers._submit(world).dispatched is False
    assert world["broker"].submitted == []
    assert trace.events[events_before:] == []
