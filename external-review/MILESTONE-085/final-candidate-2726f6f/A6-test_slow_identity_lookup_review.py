"""Review item A (scratch, not committed): a slow identity lookup before the send.

Sequence: the final guard passes -> the pre-send identity lookup starts while permitted ->
the lookup is delayed -> DURING the delay the permission expires (authorization expiry) or the
kill switch is engaged -> the lookup returns "no order" (404) -> is the POST still sent?
Expected safe behaviour: zero submissions. A submission here is a demonstrated defect.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import pytest
from freezegun import freeze_time
from freezegun.api import FrozenDateTimeFactory
from tests.unit import test_m085_corrective_pass_handlers as handlers
from tests.unit._m085_fakes import FakeBroker

from empirical_platform.decision_candidate.paper_execution import PaperExecutionState

_NOT_FOUND = '{"code": 40410000, "message": "order not found"}'


@pytest.fixture
def clock() -> Iterator[FrozenDateTimeFactory]:
    with freeze_time(handlers._NOW) as frozen:
        yield frozen


class _SlowLookupBroker(FakeBroker):
    """The identity lookup takes long enough for the world to change under it."""

    def __init__(self, *, during_lookup: Callable[[], None]) -> None:
        super().__init__()
        self._during_lookup = during_lookup

    def fetch_order_by_client_order_id(
        self, client_order_id: str
    ) -> tuple[int, object | None, str]:
        self.lookups.append(client_order_id)
        self._during_lookup()  # time passes / the switch is thrown while we wait
        return 404, None, _NOT_FOUND


def _world_with(clock: FrozenDateTimeFactory, during_lookup: Callable[[], None]) -> dict[str, Any]:
    broker = _SlowLookupBroker(during_lookup=during_lookup)
    world = handlers._world(broker=broker)
    return world


def test_authorization_expires_during_the_identity_lookup(clock: FrozenDateTimeFactory) -> None:
    holder: dict[str, Any] = {}

    def during_lookup() -> None:
        # 301 s pass inside the lookup; the authorization was valid for 300 s.
        clock.tick(timedelta(seconds=301))

    world = _world_with(clock, during_lookup)
    holder["world"] = world
    handlers._authorize(world, validity_seconds=300)
    result = handlers._submit(world)
    assert world["broker"].submitted == [], (
        f"POST was transmitted after the authorization expired during the lookup: "
        f"state={result.attempt.state} note={result.note}"
    )
    assert result.attempt.state is PaperExecutionState.REJECTED


def test_kill_switch_engaged_during_the_identity_lookup(clock: FrozenDateTimeFactory) -> None:
    holder: dict[str, Any] = {}

    def during_lookup() -> None:
        holder["world"]["kill_switch"].engaged = True

    world = _world_with(clock, during_lookup)
    holder["world"] = world
    handlers._authorize(world)
    result = handlers._submit(world)
    assert world["broker"].submitted == [], (
        f"POST was transmitted although the kill switch was engaged during the lookup: "
        f"state={result.attempt.state} note={result.note}"
    )


def test_quote_goes_stale_during_the_identity_lookup(clock: FrozenDateTimeFactory) -> None:
    holder: dict[str, Any] = {}

    def during_lookup() -> None:
        # Quote freshness limit is 60 s in the fixture configuration; 90 s pass.
        clock.tick(timedelta(seconds=90))

    world = _world_with(clock, during_lookup)
    holder["world"] = world
    handlers._authorize(world)
    result = handlers._submit(world)
    assert world["broker"].submitted == [], (
        f"POST was transmitted with a quote that went stale during the lookup: "
        f"state={result.attempt.state} note={result.note}"
    )
