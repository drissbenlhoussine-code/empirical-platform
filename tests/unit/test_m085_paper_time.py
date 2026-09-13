"""The temporal model: bounded uncertainty, and the actual HTTP send boundary.

Every case here is deterministic -- a scripted clock, no sockets, no sleeping and
no real broker -- so a failure means the model changed, never that a machine was
busy or a network was slow.

WHAT THE REPLACED MODEL ASSERTED, AND WHY THOSE ASSERTIONS ARE GONE. It required
the broker's clock reading to fall inside the local request interval, and a test
asserted that a one-second host/broker difference refused. That encoded the
defect: the product then refused every dispatch on a host whose wall clock was
0.086 s slow, which is well inside what ordinary Windows time synchronisation
leaves. The replacement bounds the offset instead of demanding it be zero, so the
one-second case is now REQUIRED to be usable and the refusals below are the ones
that actually protect an order.
"""

from datetime import UTC, datetime, timedelta

import pytest

from empirical_platform.shared.brokerage.alpaca_paper import (
    AlpacaPaperClient,
    AlpacaPaperCredentials,
    BrokerNotSentError,
    PaperEndpoint,
)
from empirical_platform.shared.brokerage.paper_time import (
    BoundedInstant,
    PaperTimeReading,
    PaperTimeUncertainError,
    PaperTimeWindow,
)

NOW = datetime(2026, 9, 10, 14, tzinfo=UTC)


class Clock:
    """A scripted host clock. `utc` and `monotonic` are moved by the test."""

    def __init__(self) -> None:
        self.utc = NOW
        self.monotonic = 0.0

    def read(self) -> PaperTimeReading:
        return PaperTimeReading(self.utc, self.monotonic)


# ---------------------------------------------------------------------------
# The host timeline. Elapsed time is monotonic, and it cannot be wished away.
# ---------------------------------------------------------------------------


def test_stalled_wall_clock_does_not_stop_expiry() -> None:
    clock = Clock()
    window = PaperTimeWindow(clock)
    clock.monotonic += 61
    assert window.now() == NOW + timedelta(seconds=61)


@pytest.mark.parametrize("field", ["utc", "monotonic"])
def test_rollback_refuses(field: str) -> None:
    clock = Clock()
    window = PaperTimeWindow(clock)
    if field == "utc":
        clock.utc -= timedelta(microseconds=1)
    else:
        clock.monotonic -= 0.001
    with pytest.raises(PaperTimeUncertainError, match="rollback"):
        window.now()


def test_forward_wall_step_does_not_extend_validity() -> None:
    clock = Clock()
    window = PaperTimeWindow(clock)
    clock.utc += timedelta(seconds=120)
    assert window.now() == NOW + timedelta(seconds=120)


def test_aware_finite_time_is_required() -> None:
    clock = Clock()
    clock.monotonic = float("nan")
    with pytest.raises(PaperTimeUncertainError, match="finite"):
        PaperTimeWindow(clock)
    clock.monotonic = 0
    clock.utc = datetime(2026, 9, 10)
    with pytest.raises(PaperTimeUncertainError, match="aware"):
        PaperTimeWindow(clock)


# ---------------------------------------------------------------------------
# The broker timeline. Bounded from one round trip, never assumed to agree.
# ---------------------------------------------------------------------------


def _observe(clock: Clock, window: PaperTimeWindow, *, broker: datetime, trip: float) -> None:
    sent = clock.monotonic
    clock.monotonic += trip
    window.observe_broker_clock(broker, sent, clock.monotonic)


@pytest.mark.parametrize("host_offset", [-5.0, -1.0, -0.086, 0.0, 0.086, 1.0, 5.0])
def test_a_host_offset_in_either_direction_is_bounded_not_refused(host_offset: float) -> None:
    # The measured failure was a host 0.086 s SLOW. Both directions, and both
    # far larger magnitudes, must be usable: the offset is unknown, so it is
    # bounded and carried, never required to be zero.
    clock = Clock()
    clock.utc = NOW + timedelta(seconds=host_offset)
    window = PaperTimeWindow(clock)
    _observe(clock, window, broker=NOW, trip=0.45)
    instant = window.broker_now()
    assert instant.earliest <= instant.latest
    assert instant.uncertainty_seconds == pytest.approx(0.45)


@pytest.mark.parametrize("trip", [0.001, 0.45, 2.4, 30.0])
def test_the_uncertainty_width_is_exactly_the_measured_round_trip(trip: float) -> None:
    clock = Clock()
    window = PaperTimeWindow(clock)
    _observe(clock, window, broker=NOW, trip=trip)
    assert window.broker_now().uncertainty_seconds == pytest.approx(trip)


@pytest.mark.parametrize("trip", [0.45, 2.4])
def test_the_broker_reading_is_contained_by_its_own_bound(trip: float) -> None:
    # Whatever point of the round trip the broker sampled, its reading at the
    # moment the response was read lies inside the interval. Nothing here
    # assumes the two legs are equal.
    clock = Clock()
    window = PaperTimeWindow(clock)
    _observe(clock, window, broker=NOW, trip=trip)
    instant = window.broker_now()
    assert instant.earliest == NOW
    assert instant.latest == NOW + timedelta(seconds=trip)


@pytest.mark.parametrize("request_leg", [0.0, 0.1, 0.44, 0.45])
def test_an_asymmetric_round_trip_does_not_move_the_bound(request_leg: float) -> None:
    # The bound depends only on the TOTAL round trip. Two runs whose legs split
    # differently but total the same produce the same interval, because the
    # split is not observable and is therefore not assumed.
    clock = Clock()
    window = PaperTimeWindow(clock)
    sent = clock.monotonic
    clock.monotonic += request_leg
    stamped = NOW
    clock.monotonic += 0.45 - request_leg
    window.observe_broker_clock(stamped, sent, clock.monotonic)
    instant = window.broker_now()
    assert instant.earliest == NOW
    assert instant.latest == NOW + timedelta(seconds=0.45)


def test_elapsed_processing_ages_the_broker_instant() -> None:
    # Time spent after the fetch -- database waits, lock contention, connecting --
    # moves both ends forward by exactly the elapsed monotonic time and does not
    # widen the interval.
    clock = Clock()
    window = PaperTimeWindow(clock)
    _observe(clock, window, broker=NOW, trip=0.4)
    clock.monotonic += 30
    clock.utc += timedelta(seconds=30)
    instant = window.broker_now()
    assert instant.earliest == NOW + timedelta(seconds=30)
    assert instant.latest == NOW + timedelta(seconds=30.4)
    assert instant.uncertainty_seconds == pytest.approx(0.4)


def test_a_stalled_host_wall_clock_still_ages_the_broker_instant() -> None:
    # The wall clock does not move; monotonic does. Elapsed work must still age
    # the evidence, or a stopped clock would hold a permission open.
    clock = Clock()
    window = PaperTimeWindow(clock)
    _observe(clock, window, broker=NOW, trip=0.2)
    clock.monotonic += 120
    assert window.broker_now().earliest == NOW + timedelta(seconds=120)


def test_broker_time_is_unavailable_until_it_has_been_observed() -> None:
    window = PaperTimeWindow(Clock())
    with pytest.raises(PaperTimeUncertainError, match="not been observed"):
        window.broker_now()


def test_a_naive_broker_timestamp_is_refused() -> None:
    window = PaperTimeWindow(Clock())
    with pytest.raises(PaperTimeUncertainError, match="timezone-aware"):
        window.observe_broker_clock(datetime(2026, 9, 10, 14), 0.0, 0.1)


def test_a_response_read_before_it_was_sent_is_refused() -> None:
    window = PaperTimeWindow(Clock())
    with pytest.raises(PaperTimeUncertainError, match="before the request was sent"):
        window.observe_broker_clock(NOW, 5.0, 1.0)


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_a_round_trip_measured_on_a_broken_clock_is_refused(bad: float) -> None:
    window = PaperTimeWindow(Clock())
    with pytest.raises(PaperTimeUncertainError, match="finite"):
        window.observe_broker_clock(NOW, 0.0, bad)


def test_a_broker_clock_that_moves_backwards_is_refused() -> None:
    # Replayed or inconsistent evidence. The second reading is older than the
    # first one's own lower bound, which no real clock can do.
    clock = Clock()
    window = PaperTimeWindow(clock)
    _observe(clock, window, broker=NOW, trip=0.2)
    clock.monotonic += 10
    with pytest.raises(PaperTimeUncertainError, match="moved backwards"):
        _observe(clock, window, broker=NOW - timedelta(seconds=60), trip=0.2)


def test_a_replayed_identical_broker_reading_is_refused_after_real_elapsed_time() -> None:
    clock = Clock()
    window = PaperTimeWindow(clock)
    _observe(clock, window, broker=NOW, trip=0.2)
    clock.monotonic += 300
    with pytest.raises(PaperTimeUncertainError, match="moved backwards"):
        _observe(clock, window, broker=NOW, trip=0.2)


def test_a_broker_clock_that_advances_normally_is_accepted() -> None:
    clock = Clock()
    window = PaperTimeWindow(clock)
    _observe(clock, window, broker=NOW, trip=0.2)
    clock.monotonic += 10
    _observe(clock, window, broker=NOW + timedelta(seconds=10), trip=0.2)
    assert window.broker_now().earliest == NOW + timedelta(seconds=10)


# ---------------------------------------------------------------------------
# Refusing evidence too uncertain to decide the question it is asked.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("trip", [60.0, 120.0])
def test_uncertainty_at_or_beyond_the_margin_is_refused(trip: float) -> None:
    clock = Clock()
    window = PaperTimeWindow(clock)
    _observe(clock, window, broker=NOW, trip=trip)
    with pytest.raises(PaperTimeUncertainError, match="uncertain"):
        window.require_broker_certainty_within(60)


@pytest.mark.parametrize("trip", [0.45, 59.9])
def test_uncertainty_inside_the_margin_is_accepted(trip: float) -> None:
    clock = Clock()
    window = PaperTimeWindow(clock)
    _observe(clock, window, broker=NOW, trip=trip)
    window.require_broker_certainty_within(60)


def test_a_non_positive_margin_is_refused() -> None:
    clock = Clock()
    window = PaperTimeWindow(clock)
    _observe(clock, window, broker=NOW, trip=0.2)
    with pytest.raises(PaperTimeUncertainError, match="must be positive"):
        window.require_broker_certainty_within(0)


# ---------------------------------------------------------------------------
# Deadlines: "might already have passed" counts as passed.
# ---------------------------------------------------------------------------


def test_a_deadline_inside_the_interval_counts_as_passed() -> None:
    instant = BoundedInstant(earliest=NOW, latest=NOW + timedelta(seconds=1))
    inside = NOW + timedelta(milliseconds=500)
    assert instant.possibly_at_or_after(inside) is True
    assert instant.definitely_at_or_after(inside) is False


def test_a_deadline_beyond_the_interval_has_not_passed() -> None:
    instant = BoundedInstant(earliest=NOW, latest=NOW + timedelta(seconds=1))
    assert instant.possibly_at_or_after(NOW + timedelta(seconds=5)) is False


def test_age_bounds_are_returned_smallest_first() -> None:
    instant = BoundedInstant(earliest=NOW, latest=NOW + timedelta(seconds=2))
    youngest, oldest = instant.age_of(NOW - timedelta(seconds=10))
    assert youngest == pytest.approx(10.0)
    assert oldest == pytest.approx(12.0)


def test_an_inverted_interval_cannot_be_constructed() -> None:
    with pytest.raises(PaperTimeUncertainError, match="cannot end before it starts"):
        BoundedInstant(earliest=NOW + timedelta(seconds=1), latest=NOW)


# ---------------------------------------------------------------------------
# The real send boundary.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("unexpected", [False, True])
def test_final_guard_runs_after_connect_and_before_http_request(
    monkeypatch: pytest.MonkeyPatch, unexpected: bool
) -> None:
    from tests.unit._m085_fakes import a_preview

    events = []

    class Connection:
        sock = None

        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def connect(self) -> None:
            events.append("connected")

        def request(self, *args: object, **kwargs: object) -> None:
            events.append("sent")

        def getresponse(self) -> None:
            raise AssertionError("order bytes sent without pre-send guard")

        def close(self) -> None:
            events.append("closed")

    monkeypatch.setattr("http.client.HTTPSConnection", Connection)
    client = AlpacaPaperClient(
        endpoint=PaperEndpoint.from_url("https://paper-api.alpaca.markets"),
        credentials=AlpacaPaperCredentials("test-key-" * 4, "test-secret-" * 4),
    )

    def guard() -> None:
        assert events == ["connected"]
        events.append("guard")
        if unexpected:
            raise RuntimeError("controlled failure")
        raise BrokerNotSentError("authorization expired during connection")

    with pytest.raises(BrokerNotSentError):
        client.submit_order(a_preview().order, before_send=guard)
    assert events == ["connected", "guard", "closed"]
