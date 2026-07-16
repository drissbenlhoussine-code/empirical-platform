"""Startup-safe composition for process-local foundations and dependencies."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from empirical_platform.shared.config.settings import (
    FoundationConfigSnapshot,
    LoggingSettings,
    resolve_foundation_config,
)
from empirical_platform.shared.errors import FoundationError, FoundationErrorCategory
from empirical_platform.shared.health import HealthReport, HealthState, LayerHealth, ProcessHealth
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


class RuntimeLifecycleState(StrEnum):
    """Explicit lifecycle states for a composed runtime."""

    NEW = "NEW"
    STARTING = "STARTING"
    READY = "READY"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


HealthReportFactory = Callable[[list[LayerHealth]], HealthReport]


@dataclass(slots=True)
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
    _state: RuntimeLifecycleState = RuntimeLifecycleState.READY
    _lifecycle_events: list[RuntimeLifecycleState] = field(
        default_factory=lambda: [
            RuntimeLifecycleState.NEW,
            RuntimeLifecycleState.STARTING,
            RuntimeLifecycleState.READY,
        ]
    )

    @property
    def lifecycle_state(self) -> RuntimeLifecycleState:
        """Return the current runtime lifecycle state."""
        return self._state

    @property
    def lifecycle_events(self) -> tuple[RuntimeLifecycleState, ...]:
        """Return observed lifecycle states in transition order."""
        return tuple(self._lifecycle_events)

    def ensure_ready(self, operation: str = "runtime_operation") -> None:
        """Fail safely when runtime-owned work is attempted outside READY state."""
        if self._state is not RuntimeLifecycleState.READY:
            raise FoundationError(
                category=FoundationErrorCategory.FOUNDATION,
                message="Infrastructure runtime is not ready",
                layer="runtime",
                operation=operation,
                context={"lifecycle_state": self._state.value},
            )

    def refresh_health(
        self,
        *,
        health_report_factory: HealthReportFactory = HealthReport.from_layers,
    ) -> HealthReport:
        """Refresh and return combined runtime health."""
        layers = _base_health_layers()
        if self.persistence is not None:
            self.persistence.check()
            layers.append(self.persistence.health())
        if self.object_storage is not None:
            self.object_storage.check()
            layers.append(self.object_storage.health())
        if self._state is RuntimeLifecycleState.STOPPED:
            layers.append(
                LayerHealth.internal(
                    "runtime",
                    liveness=HealthState.PASS,
                    readiness=HealthState.FAIL,
                )
            )
        elif self._state is RuntimeLifecycleState.FAILED:
            layers.append(
                LayerHealth.internal(
                    "runtime",
                    liveness=HealthState.PASS,
                    readiness=HealthState.FAIL,
                )
            )
        self.health = health_report_factory(layers)
        return self.health

    def close(self) -> None:
        """Close runtime-owned resources in reverse initialization order."""
        if self._state is RuntimeLifecycleState.STOPPED:
            return
        if self._state is RuntimeLifecycleState.FAILED:
            self._transition(RuntimeLifecycleState.STOPPED)
            return
        if self._state is not RuntimeLifecycleState.READY:
            raise FoundationError(
                category=FoundationErrorCategory.FOUNDATION,
                message="Infrastructure runtime cannot shut down from current state",
                layer="runtime",
                operation="shutdown",
                context={"lifecycle_state": self._state.value},
            )

        self._transition(RuntimeLifecycleState.STOPPING)
        cleanup_failures = _cleanup_initialized(
            [
                ("object_storage", self.object_storage),
                ("persistence", self.persistence),
            ]
        )
        self._transition(RuntimeLifecycleState.STOPPED)
        self.refresh_health()
        if cleanup_failures:
            raise FoundationError(
                category=FoundationErrorCategory.FOUNDATION,
                message="Infrastructure runtime shutdown completed with cleanup failures",
                layer="runtime",
                operation="shutdown",
                context={"cleanup_failures": cleanup_failures},
            )

    def _transition(self, state: RuntimeLifecycleState) -> None:
        self._state = state
        self._lifecycle_events.append(state)


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


def initialize_infrastructure_runtime(
    environ: Mapping[str, str] | None = None,
    *,
    wall_clock: WallClock | None = None,
    monotonic_clock: MonotonicClock | None = None,
    identifiers: RuntimeIdentifierGenerator | None = None,
    logger: FoundationLogger | None = None,
    persistence: PersistenceService | None = None,
    object_storage: ObjectStorageService | None = None,
    health_report_factory: HealthReportFactory = HealthReport.from_layers,
) -> FoundationRuntime:
    """Initialize the canonical infrastructure runtime with mandatory dependencies."""
    from empirical_platform.shared.object_storage.s3 import S3ObjectStorageService

    lifecycle_events = [RuntimeLifecycleState.NEW, RuntimeLifecycleState.STARTING]
    initialized: list[tuple[str, object | None]] = []
    try:
        config = resolve_foundation_config(environ)
        configure_logging(LoggingSettings(log_level=config.logging.log_level))
        runtime_wall_clock = wall_clock or SystemWallClock()
        runtime_monotonic_clock = monotonic_clock or SystemMonotonicClock()
        runtime_identifiers = identifiers or UuidRuntimeIdentifierGenerator()
        runtime_logger = logger or FoundationLogger()

        persistence_service = persistence or PostgresPersistenceService(config.postgresql)
        persistence_service.initialize()
        initialized.append(("persistence", persistence_service))
        _require_dependency_ready(persistence_service, layer="persistence")

        object_storage_service = object_storage or S3ObjectStorageService(config.object_storage)
        object_storage_service.initialize()
        initialized.append(("object_storage", object_storage_service))
        _require_dependency_ready(object_storage_service, layer="object_storage")

        health = health_report_factory(
            _base_health_layers()
            + [
                persistence_service.health(),
                object_storage_service.health(),
            ]
        )
        if health.status is not ProcessHealth.PASS:
            raise FoundationError(
                category=FoundationErrorCategory.FOUNDATION,
                message="Infrastructure runtime readiness aggregation failed",
                layer="runtime",
                operation="aggregate_health",
                context={"health_status": health.status.value},
            )

        runtime = FoundationRuntime(
            config=config,
            wall_clock=runtime_wall_clock,
            monotonic_clock=runtime_monotonic_clock,
            identifiers=runtime_identifiers,
            logger=runtime_logger,
            health=health,
            persistence=persistence_service,
            object_storage=object_storage_service,
            _state=RuntimeLifecycleState.READY,
            _lifecycle_events=[*lifecycle_events, RuntimeLifecycleState.READY],
        )
        runtime.logger.info("infrastructure_runtime_initialized")
        return runtime
    except Exception as exc:
        cleanup_failures = _cleanup_initialized(reversed(initialized))
        raise _startup_error(exc, cleanup_failures) from exc


def initialize_foundation_runtime_with_postgresql(
    environ: Mapping[str, str] | None = None,
    *,
    wall_clock: WallClock | None = None,
    monotonic_clock: MonotonicClock | None = None,
    identifiers: RuntimeIdentifierGenerator | None = None,
    logger: FoundationLogger | None = None,
    persistence: PersistenceService | None = None,
) -> FoundationRuntime:
    """Initialize focused PostgreSQL runtime for low-level persistence verification."""
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
    """Initialize focused object-storage runtime for low-level storage verification."""
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


def _base_health_layers() -> list[LayerHealth]:
    return [
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


def _require_dependency_ready(
    service: PersistenceService | ObjectStorageService, *, layer: str
) -> None:
    if not service.check():
        raise FoundationError(
            category=(
                FoundationErrorCategory.PERSISTENCE
                if layer == "persistence"
                else FoundationErrorCategory.OBJECT_STORAGE
            ),
            message=f"{layer.replace('_', '-').title()} dependency is not ready",
            layer=layer,
            operation="probe",
        )


def _cleanup_initialized(resources: Iterable[tuple[str, object | None]]) -> list[dict[str, object]]:
    failures: list[dict[str, object]] = []
    for layer, resource in resources:
        if resource is None:
            continue
        close = getattr(resource, "close", None)
        if close is None:
            continue
        try:
            close()
        except FoundationError as exc:
            failures.append(
                {
                    "layer": layer,
                    "category": exc.category.value,
                    "message": exc.safe_message,
                    "operation": exc.operation,
                }
            )
        except Exception:
            failures.append(
                {
                    "layer": layer,
                    "category": FoundationErrorCategory.FOUNDATION.value,
                    "message": "Runtime cleanup failed",
                    "operation": "cleanup",
                }
            )
    return failures


def _startup_error(
    exc: BaseException, cleanup_failures: list[dict[str, object]]
) -> FoundationError:
    context = {
        "lifecycle_state": RuntimeLifecycleState.FAILED.value,
        "cleanup_failures": cleanup_failures,
    }
    if isinstance(exc, FoundationError):
        return FoundationError(
            category=exc.category,
            message=exc.safe_message,
            layer=exc.layer,
            operation=exc.operation,
            context=exc.context | context,
        )
    return FoundationError.wrap(
        exc,
        category=FoundationErrorCategory.FOUNDATION,
        message="Infrastructure runtime startup failed",
        layer="runtime",
        operation="startup",
        context=context,
    )
