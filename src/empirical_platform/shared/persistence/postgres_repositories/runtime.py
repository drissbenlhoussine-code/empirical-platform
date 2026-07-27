"""PostgreSQL repository runtime composition (MILESTONE-025).

Composes the four frozen MILESTONE-023 PostgreSQL repository adapters over one
caller-supplied, caller-owned `PostgresPersistenceService`, per
MILESTONE_025_REPOSITORY_RUNTIME_COMPOSITION_DESIGN.md Sections 5-11.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.campaign_repository import (
    PostgresCampaignRepository,
)
from empirical_platform.shared.persistence.postgres_repositories.evidence_package_repository import (  # noqa: E501
    PostgresEvidencePackageRepository,
)
from empirical_platform.shared.persistence.postgres_repositories.review_repository import (
    PostgresReviewRepository,
)
from empirical_platform.shared.persistence.postgres_repositories.run_repository import (
    PostgresRunRepository,
)


class PostgresRepositoryRuntime:
    """Owns one shared `PostgresPersistenceService` and the four concrete
    PostgreSQL repository adapters constructed over it.

    Construction is eager: all four adapters are built exactly once, here,
    each receiving the exact same `service` instance. Repeated access to any
    property returns the identical object. The caller owns creating and
    initializing `service`; this class performs no readiness probe, no
    `initialize()` call, and no migration -- the existing, unmodified
    `PostgresPersistenceService._ensure_can_work` guard already rejects any
    repository operation attempted against an uninitialized or closed
    service, on first use.
    """

    __slots__ = ("_service", "_campaigns", "_runs", "_evidence_packages", "_reviews")

    def __init__(self, service: PostgresPersistenceService) -> None:
        if not isinstance(service, PostgresPersistenceService):
            raise TypeError(
                "PostgresRepositoryRuntime requires a PostgresPersistenceService instance"
            )
        self._service = service
        self._campaigns = PostgresCampaignRepository(service)
        self._runs = PostgresRunRepository(service)
        self._evidence_packages = PostgresEvidencePackageRepository(service)
        self._reviews = PostgresReviewRepository(service)

    @property
    def campaigns(self) -> PostgresCampaignRepository:
        return self._campaigns

    @property
    def runs(self) -> PostgresRunRepository:
        return self._runs

    @property
    def evidence_packages(self) -> PostgresEvidencePackageRepository:
        return self._evidence_packages

    @property
    def reviews(self) -> PostgresReviewRepository:
        return self._reviews

    def run_composed(self, operations: Sequence[Callable[[], object]]) -> tuple[object, ...]:
        """Delegate directly to the frozen MILESTONE-024 composed-transaction primitive."""
        return self._service.run_composed(operations)

    def close(self) -> None:
        """Delegate to the shared service's own idempotent close."""
        self._service.close()
