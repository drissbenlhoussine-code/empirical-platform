from __future__ import annotations

import pytest

from empirical_platform.shared.bootstrap import initialize_foundation_runtime_with_postgresql
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.health import ProcessHealth
from empirical_platform.shared.persistence.fake import FakePersistenceService


def test_bootstrap_with_persistence_initializes_or_exposes_no_ready_runtime() -> None:
    persistence = FakePersistenceService()

    runtime = initialize_foundation_runtime_with_postgresql(
        {"EMPIRICAL_PLATFORM_ENVIRONMENT": "test"},
        persistence=persistence,
    )

    assert runtime.persistence is persistence
    assert runtime.health.status is ProcessHealth.PASS


def test_bootstrap_with_unreachable_persistence_fails_before_ready_runtime() -> None:
    with pytest.raises(FoundationError):
        initialize_foundation_runtime_with_postgresql(
            {"EMPIRICAL_PLATFORM_ENVIRONMENT": "test"},
            persistence=FakePersistenceService(reachable=False),
        )
