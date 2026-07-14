"""Multi-axis foundation health model."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from empirical_platform.shared.errors import FoundationError, FoundationErrorCategory


class HealthState(StrEnum):
    """Allowed health dimension states."""

    PASS = "PASS"  # noqa: S105 - health state, not a password.
    FAIL = "FAIL"
    DEGRADED = "DEGRADED"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ProcessHealth(StrEnum):
    """Aggregated process-level health."""

    PASS = "PASS"  # noqa: S105 - health state, not a password.
    FAIL = "FAIL"
    DEGRADED = "DEGRADED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class LayerHealth:
    """Independent health dimensions for one observed layer."""

    layer: str
    liveness: HealthState
    readiness: HealthState
    dependency_health: HealthState

    def __post_init__(self) -> None:
        if HealthState.NOT_APPLICABLE in {self.liveness, self.readiness}:
            raise ValueError("NOT_APPLICABLE is valid only for dependency health")
        if self.dependency_health is HealthState.NOT_APPLICABLE:
            return
        if self.dependency_health not in {
            HealthState.PASS,
            HealthState.FAIL,
            HealthState.DEGRADED,
            HealthState.UNKNOWN,
        }:
            raise ValueError("invalid dependency health state")

    @classmethod
    def internal(
        cls,
        layer: str,
        *,
        liveness: HealthState = HealthState.UNKNOWN,
        readiness: HealthState = HealthState.UNKNOWN,
    ) -> LayerHealth:
        """Create health for a layer without an external dependency."""
        return cls(
            layer=layer,
            liveness=liveness,
            readiness=readiness,
            dependency_health=HealthState.NOT_APPLICABLE,
        )

    def as_dict(self) -> dict[str, str]:
        """Return a serializable health signal."""
        return {
            "layer": self.layer,
            "liveness": self.liveness.value,
            "readiness": self.readiness.value,
            "dependency_health": self.dependency_health.value,
        }


def aggregate_health(layers: list[LayerHealth]) -> ProcessHealth:
    """Aggregate per-layer dimensions using an explicit conservative policy."""
    if not layers:
        return ProcessHealth.UNKNOWN

    states = [
        state
        for layer in layers
        for state in (layer.liveness, layer.readiness, layer.dependency_health)
        if state is not HealthState.NOT_APPLICABLE
    ]
    if any(state is HealthState.FAIL for state in states):
        return ProcessHealth.FAIL
    if any(state is HealthState.DEGRADED for state in states):
        return ProcessHealth.DEGRADED
    if any(state is HealthState.UNKNOWN for state in states):
        return ProcessHealth.UNKNOWN
    return ProcessHealth.PASS


@dataclass(frozen=True, slots=True)
class HealthReport:
    """Aggregated foundation health report."""

    layers: tuple[LayerHealth, ...]
    status: ProcessHealth

    @classmethod
    def from_layers(cls, layers: list[LayerHealth]) -> HealthReport:
        """Create an aggregate report."""
        try:
            return cls(layers=tuple(layers), status=aggregate_health(layers))
        except Exception as exc:
            raise FoundationError.wrap(
                exc,
                category=FoundationErrorCategory.FOUNDATION,
                message="Foundation health aggregation failed",
                layer="health",
                operation="aggregate",
            ) from exc

    def as_dict(self) -> dict[str, object]:
        """Return a serializable report."""
        return {
            "status": self.status.value,
            "layers": [layer.as_dict() for layer in self.layers],
        }
