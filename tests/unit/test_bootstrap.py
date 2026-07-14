from __future__ import annotations

import uuid

import pytest

from empirical_platform.shared.bootstrap import initialize_foundation_runtime
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.health import ProcessHealth
from empirical_platform.shared.identifiers import DeterministicRuntimeIdentifierGenerator
from empirical_platform.shared.interfaces.clock import FixedWallClock, ManualMonotonicClock


def test_initialize_foundation_runtime_composes_process_local_foundations() -> None:
    value = str(uuid.uuid4())
    runtime = initialize_foundation_runtime(
        {"EMPIRICAL_PLATFORM_ENVIRONMENT": "test"},
        identifiers=DeterministicRuntimeIdentifierGenerator([value]),
        wall_clock=FixedWallClock(
            __import__("datetime").datetime.now(tz=__import__("datetime").UTC)
        ),
        monotonic_clock=ManualMonotonicClock(),
    )

    assert runtime.config.app.environment == "test"
    assert str(runtime.identifiers.generate()) == value
    assert runtime.health.status is ProcessHealth.PASS


def test_invalid_config_prevents_ready_runtime() -> None:
    with pytest.raises(FoundationError):
        initialize_foundation_runtime({"EMPIRICAL_PLATFORM_LOG_LEVEL": "NOPE"})
