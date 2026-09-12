"""Clock bounds and the actual HTTP send boundary, without external sockets."""

from datetime import UTC, datetime, timedelta

import pytest

from empirical_platform.shared.brokerage.alpaca_paper import (
    AlpacaPaperClient,
    AlpacaPaperCredentials,
    BrokerNotSentError,
    PaperEndpoint,
)
from empirical_platform.shared.brokerage.paper_time import (
    PaperTimeReading,
    PaperTimeUncertainError,
    PaperTimeWindow,
)

NOW = datetime(2026, 9, 10, 14, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.utc = NOW
        self.monotonic = 0.0

    def read(self) -> PaperTimeReading:
        return PaperTimeReading(self.utc, self.monotonic)


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


@pytest.mark.parametrize("offset", [-1, 1])
def test_uncertain_absolute_alignment_refuses(offset: int) -> None:
    window = PaperTimeWindow(Clock())
    with pytest.raises(PaperTimeUncertainError, match="alignment"):
        window.verify_broker(NOW + timedelta(seconds=offset), NOW)


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
