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
from empirical_platform.shared.persistence.postgres_repositories.decision_candidate_repository import (  # noqa: E501
    PostgresDecisionCandidateRepository,
)
from empirical_platform.shared.persistence.postgres_repositories.evidence_package_repository import (  # noqa: E501
    PostgresEvidencePackageRepository,
)
from empirical_platform.shared.persistence.postgres_repositories.historical_backtest_repository import (  # noqa: E501
    PostgresHistoricalBacktestRunRepository,
)
from empirical_platform.shared.persistence.postgres_repositories.position_plan_repository import (
    PostgresPositionPlanRepository,
)
from empirical_platform.shared.persistence.postgres_repositories.review_repository import (
    PostgresReviewRepository,
)
from empirical_platform.shared.persistence.postgres_repositories.robustness_study_repository import (  # noqa: E501
    PostgresHistoricalRobustnessStudyRepository,
)
from empirical_platform.shared.persistence.postgres_repositories.run_repository import (
    PostgresRunRepository,
)
from empirical_platform.shared.persistence.postgres_repositories.survivorship_study_repository import (  # noqa: E501
    PostgresInstrumentMasterRepository,
    PostgresSurvivorshipAwareRobustnessStudyRepository,
    PostgresUniverseMembershipRepository,
)
from empirical_platform.shared.persistence.postgres_repositories.trade_plan_repository import (
    PostgresTradePlanRepository,
)
from empirical_platform.shared.persistence.postgres_repositories.trading_opportunity_scan_repository import (  # noqa: E501
    PostgresTradingOpportunityScanRepository,
)
from empirical_platform.shared.persistence.postgres_repositories.validation_study_repository import (  # noqa: E501
    PostgresHistoricalValidationStudyRepository,
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

    __slots__ = (
        "_service",
        "_campaigns",
        "_runs",
        "_evidence_packages",
        "_reviews",
        "_decision_candidates",
        "_trading_opportunity_scans",
        "_trade_plans",
        "_position_plans",
        "_historical_backtests",
        "_validation_studies",
        "_robustness_studies",
        "_survivorship_studies",
        "_instrument_masters",
        "_universe_memberships",
    )

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
        self._decision_candidates = PostgresDecisionCandidateRepository(service)
        self._trading_opportunity_scans = PostgresTradingOpportunityScanRepository(service)
        self._trade_plans = PostgresTradePlanRepository(service)
        self._position_plans = PostgresPositionPlanRepository(service)
        self._historical_backtests = PostgresHistoricalBacktestRunRepository(service)
        self._validation_studies = PostgresHistoricalValidationStudyRepository(service)
        self._robustness_studies = PostgresHistoricalRobustnessStudyRepository(service)
        self._survivorship_studies = PostgresSurvivorshipAwareRobustnessStudyRepository(service)
        self._instrument_masters = PostgresInstrumentMasterRepository(service)
        self._universe_memberships = PostgresUniverseMembershipRepository(service)

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

    @property
    def decision_candidates(self) -> PostgresDecisionCandidateRepository:
        return self._decision_candidates

    @property
    def trading_opportunity_scans(self) -> PostgresTradingOpportunityScanRepository:
        return self._trading_opportunity_scans

    @property
    def trade_plans(self) -> PostgresTradePlanRepository:
        return self._trade_plans

    @property
    def position_plans(self) -> PostgresPositionPlanRepository:
        return self._position_plans

    @property
    def historical_backtests(self) -> PostgresHistoricalBacktestRunRepository:
        return self._historical_backtests

    @property
    def validation_studies(self) -> PostgresHistoricalValidationStudyRepository:
        return self._validation_studies

    @property
    def robustness_studies(self) -> PostgresHistoricalRobustnessStudyRepository:
        return self._robustness_studies

    @property
    def survivorship_studies(self) -> PostgresSurvivorshipAwareRobustnessStudyRepository:
        return self._survivorship_studies

    @property
    def instrument_masters(self) -> PostgresInstrumentMasterRepository:
        return self._instrument_masters

    @property
    def universe_memberships(self) -> PostgresUniverseMembershipRepository:
        return self._universe_memberships

    def run_composed(self, operations: Sequence[Callable[[], object]]) -> tuple[object, ...]:
        """Delegate directly to the frozen MILESTONE-024 composed-transaction primitive."""
        return self._service.run_composed(operations)

    def close(self) -> None:
        """Delegate to the shared service's own idempotent close."""
        self._service.close()
