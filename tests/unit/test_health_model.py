from __future__ import annotations

import pytest

from empirical_platform.shared.health import (
    HealthReport,
    HealthState,
    LayerHealth,
    ProcessHealth,
    aggregate_health,
)


def test_internal_layer_uses_not_applicable_dependency_health() -> None:
    health = LayerHealth.internal(
        "configuration",
        liveness=HealthState.PASS,
        readiness=HealthState.PASS,
    )

    assert health.dependency_health is HealthState.NOT_APPLICABLE
    assert health.as_dict()["dependency_health"] == "NOT_APPLICABLE"


def test_not_applicable_is_invalid_for_liveness_or_readiness() -> None:
    with pytest.raises(ValueError):
        LayerHealth(
            "logging",
            liveness=HealthState.NOT_APPLICABLE,
            readiness=HealthState.PASS,
            dependency_health=HealthState.NOT_APPLICABLE,
        )


def test_aggregation_policy_is_conservative_and_explicit() -> None:
    assert aggregate_health([]) is ProcessHealth.UNKNOWN
    assert (
        aggregate_health([LayerHealth.internal("configuration", liveness=HealthState.PASS)])
        is ProcessHealth.UNKNOWN
    )
    assert (
        aggregate_health(
            [
                LayerHealth.internal(
                    "configuration",
                    liveness=HealthState.PASS,
                    readiness=HealthState.DEGRADED,
                )
            ]
        )
        is ProcessHealth.DEGRADED
    )
    assert (
        aggregate_health(
            [
                LayerHealth(
                    "persistence",
                    liveness=HealthState.PASS,
                    readiness=HealthState.FAIL,
                    dependency_health=HealthState.FAIL,
                )
            ]
        )
        is ProcessHealth.FAIL
    )


def test_health_report_is_distinct_from_error_or_log_record() -> None:
    report = HealthReport.from_layers(
        [LayerHealth.internal("error", liveness=HealthState.PASS, readiness=HealthState.PASS)]
    )

    payload = report.as_dict()
    assert payload["status"] == "PASS"
    assert "category" not in payload
    assert "event" not in payload
