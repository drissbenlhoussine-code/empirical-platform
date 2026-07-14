"""Startup-safe composition for process-local foundations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from empirical_platform.shared.config.settings import (
    FoundationConfigSnapshot,
    LoggingSettings,
    resolve_foundation_config,
)
from empirical_platform.shared.health import HealthReport, HealthState, LayerHealth
from empirical_platform.shared.identifiers import (
    RuntimeIdentifierGenerator,
    UuidRuntimeIdentifierGenerator,
)
from empirical_platform.shared.interfaces.clock import (
    MonotonicClock,
    SystemMonotonicClock,
    SystemWallClock,
    WallClock,
)
from empirical_platform.shared.logging.configure import FoundationLogger, configure_logging


@dataclass(frozen=True, slots=True)
class FoundationRuntime:
    """Composed process-local foundation runtime."""

    config: FoundationConfigSnapshot
    wall_clock: WallClock
    monotonic_clock: MonotonicClock
    identifiers: RuntimeIdentifierGenerator
    logger: FoundationLogger
    health: HealthReport


def initialize_foundation_runtime(
    environ: Mapping[str, str] | None = None,
    *,
    wall_clock: WallClock | None = None,
    monotonic_clock: MonotonicClock | None = None,
    identifiers: RuntimeIdentifierGenerator | None = None,
    logger: FoundationLogger | None = None,
) -> FoundationRuntime:
    """Initialize process-local foundations in a fixed startup order."""
    config = resolve_foundation_config(environ)
    configure_logging(LoggingSettings(log_level=config.logging.log_level))
    runtime = FoundationRuntime(
        config=config,
        wall_clock=wall_clock or SystemWallClock(),
        monotonic_clock=monotonic_clock or SystemMonotonicClock(),
        identifiers=identifiers or UuidRuntimeIdentifierGenerator(),
        logger=logger or FoundationLogger(),
        health=HealthReport.from_layers(
            [
                LayerHealth.internal(
                    "configuration",
                    liveness=HealthState.PASS,
                    readiness=HealthState.PASS,
                ),
                LayerHealth.internal(
                    "wall_clock",
                    liveness=HealthState.PASS,
                    readiness=HealthState.PASS,
                ),
                LayerHealth.internal(
                    "monotonic_clock",
                    liveness=HealthState.PASS,
                    readiness=HealthState.PASS,
                ),
                LayerHealth.internal(
                    "identifier",
                    liveness=HealthState.PASS,
                    readiness=HealthState.PASS,
                ),
                LayerHealth.internal(
                    "logging",
                    liveness=HealthState.PASS,
                    readiness=HealthState.PASS,
                ),
            ]
        ),
    )
    runtime.logger.info("foundation_runtime_initialized")
    return runtime
