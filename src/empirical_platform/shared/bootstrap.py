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
from empirical_platform.shared.interfaces.object_storage import ObjectStorageService
from empirical_platform.shared.interfaces.persistence import PersistenceService
from empirical_platform.shared.logging.configure import FoundationLogger, configure_logging
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService


@dataclass(frozen=True, slots=True)
class FoundationRuntime:
    """Composed process-local foundation runtime."""

    config: FoundationConfigSnapshot
    wall_clock: WallClock
    monotonic_clock: MonotonicClock
    identifiers: RuntimeIdentifierGenerator
    logger: FoundationLogger
    health: HealthReport
    persistence: PersistenceService | None = None
    object_storage: ObjectStorageService | None = None


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


def initialize_foundation_runtime_with_postgresql(
    environ: Mapping[str, str] | None = None,
    *,
    wall_clock: WallClock | None = None,
    monotonic_clock: MonotonicClock | None = None,
    identifiers: RuntimeIdentifierGenerator | None = None,
    logger: FoundationLogger | None = None,
    persistence: PersistenceService | None = None,
) -> FoundationRuntime:
    """Initialize process-local foundations and mandatory PostgreSQL persistence."""
    config = resolve_foundation_config(environ)
    configure_logging(LoggingSettings(log_level=config.logging.log_level))
    persistence_service = persistence or PostgresPersistenceService(config.postgresql)
    persistence_service.initialize()
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
                persistence_service.health(),
            ]
        ),
        persistence=persistence_service,
    )
    runtime.logger.info("foundation_runtime_initialized_with_postgresql")
    return runtime


def initialize_foundation_runtime_with_object_storage(
    environ: Mapping[str, str] | None = None,
    *,
    wall_clock: WallClock | None = None,
    monotonic_clock: MonotonicClock | None = None,
    identifiers: RuntimeIdentifierGenerator | None = None,
    logger: FoundationLogger | None = None,
    object_storage: ObjectStorageService | None = None,
) -> FoundationRuntime:
    """Initialize process-local foundations and mandatory object storage."""
    from empirical_platform.shared.object_storage.s3 import S3ObjectStorageService

    config = resolve_foundation_config(environ)
    configure_logging(LoggingSettings(log_level=config.logging.log_level))
    object_storage_service = object_storage or S3ObjectStorageService(config.object_storage)
    object_storage_service.initialize()
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
                object_storage_service.health(),
            ]
        ),
        object_storage=object_storage_service,
    )
    runtime.logger.info("foundation_runtime_initialized_with_object_storage")
    return runtime
