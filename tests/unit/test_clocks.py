from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from empirical_platform.shared.interfaces.clock import (
    FixedWallClock,
    ManualMonotonicClock,
    SystemWallClock,
)


def test_system_wall_clock_returns_timezone_aware_timestamp() -> None:
    assert SystemWallClock().now().tzinfo is not None


def test_fixed_wall_clock_allows_backward_adjustment() -> None:
    first = datetime(2026, 1, 2, tzinfo=UTC)
    second = first - timedelta(days=1)
    clock = FixedWallClock(first)

    clock.set(second)

    assert clock.now() == second


def test_fixed_wall_clock_rejects_naive_time() -> None:
    with pytest.raises(ValueError):
        FixedWallClock(datetime(2026, 1, 1))


def test_manual_monotonic_clock_is_elapsed_only_and_non_decreasing() -> None:
    clock = ManualMonotonicClock(initial=4.0)
    started = clock.tick()

    clock.advance(2.5)

    assert clock.tick() == 6.5
    assert clock.elapsed_since(started) == 2.5
    with pytest.raises(ValueError):
        clock.advance(-1)
