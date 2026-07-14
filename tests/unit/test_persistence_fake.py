from __future__ import annotations

import pytest

from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.health import HealthState
from empirical_platform.shared.persistence.fake import FakePersistenceService


def test_fake_persistence_commits_successful_unit_of_work() -> None:
    service = FakePersistenceService()
    service.initialize()

    with service.unit_of_work() as work:
        work.execute("SELECT 1")

    assert service.committed == ["SELECT 1"]
    assert service.rollback_count == 0


def test_fake_persistence_rolls_back_on_exception() -> None:
    service = FakePersistenceService()
    service.initialize()

    with pytest.raises(RuntimeError, match="boom"):
        with service.unit_of_work() as work:
            work.execute("SELECT 1")
            raise RuntimeError("boom")

    assert service.committed == []
    assert service.rollback_count == 1


def test_fake_persistence_explicit_rollback_and_double_completion() -> None:
    service = FakePersistenceService()
    service.initialize()

    with service.unit_of_work() as work:
        work.execute("SELECT 1")
        work.rollback()
        with pytest.raises(FoundationError):
            work.commit()

    assert service.committed == []
    assert service.rollback_count == 1


def test_fake_persistence_rejects_nested_unit_of_work() -> None:
    service = FakePersistenceService()
    service.initialize()

    with service.unit_of_work():
        with pytest.raises(FoundationError):
            with service.unit_of_work():
                pass


def test_fake_persistence_health_and_use_after_close() -> None:
    service = FakePersistenceService()

    assert service.health().readiness is HealthState.UNKNOWN
    service.initialize()
    assert service.health().dependency_health is HealthState.PASS
    service.close()
    assert service.health().readiness is HealthState.UNKNOWN
    with pytest.raises(FoundationError):
        service.unit_of_work()
