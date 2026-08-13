"""MILESTONE-074 -- Historical portfolio evidence discovery usecase.

Thin read-only composition over the M074-owned
`HistoricalPortfolioEvidenceQueryRepository`. Loads persisted
historical evidence (M064 survivorship studies + their M067 portfolio
companions) and runs the pure `find_compatible_historical_evidence`
compatibility rule to produce a deterministic, ordered tuple of
`HistoricalPortfolioEvidence` summaries for the daily brief.

Does not write or mutate any persisted row. Does not modify the
M070 ResearchSession. Does not call any broker, scheduler, or LLM.
Does not import `shared.persistence` directly (architecture rule:
`usecases` is forbidden from importing `empirical_platform.shared.persistence`).
The concrete `PostgresHistoricalPortfolioEvidenceQueryRepository` is
wired by the entrypoint composition root, not by this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from empirical_platform.decision_candidate.historical_portfolio_evidence import (
    HistoricalPortfolioEvidence,
    find_compatible_historical_evidence,
)
from empirical_platform.decision_candidate.historical_portfolio_evidence_query_repository import (
    HistoricalPortfolioEvidenceQueryRepository,
)
from empirical_platform.decision_candidate.portfolio_study import PortfolioEvidenceReport
from empirical_platform.decision_candidate.survivorship_study import (
    SurvivorshipAwareRobustnessStudy,
)


@dataclass(frozen=True, slots=True)
class DiscoverHistoricalPortfolioEvidenceQuery:
    """Inputs to the M074 historical-evidence discovery. Mirrors the
    M070 ResearchSession fields the M074 compatibility rule needs
    plus the session identity for downstream logging / tracing."""

    strategy_id: str | None
    strategy_version: str | None
    ranking_model_id: str | None
    ranking_model_version: str | None
    risk_policy_id: str | None
    risk_policy_version: str | None
    sizing_policy_id: str | None
    sizing_policy_version: str | None
    requested_universe: tuple[str, ...]
    as_of: datetime


class DiscoverHistoricalPortfolioEvidenceHandler:
    """Read-only discovery over the M074 query boundary. Loads all
    persisted M064 studies, joins each with its M067 companion report
    (if any), runs the pure compatibility rule, and returns the
    deterministically ordered tuple of HistoricalPortfolioEvidence
    summaries.

    Failures (DB unavailable, malformed rows, etc.) are propagated
    as exceptions -- the M072 brief handler is responsible for
    catching them and rendering an honest "discovery failed" placeholder.
    """

    __slots__ = ("_query_repository",)

    def __init__(self, *, query_repository: HistoricalPortfolioEvidenceQueryRepository) -> None:
        self._query_repository = query_repository

    def handle(
        self, query: DiscoverHistoricalPortfolioEvidenceQuery
    ) -> tuple[HistoricalPortfolioEvidence, ...]:
        survivorship_candidates: tuple[SurvivorshipAwareRobustnessStudy, ...] = (
            self._query_repository.list_survivorship_candidates()
        )
        portfolio_lookup: dict[str, PortfolioEvidenceReport] = {}
        for study in survivorship_candidates:
            report = self._query_repository.find_portfolio_report_for(
                str(study.identity.runtime_id)
            )
            if report is not None:
                portfolio_lookup[str(study.identity.runtime_id)] = report
        instrument_master = self._query_repository.load_instrument_master()
        return find_compatible_historical_evidence(
            m070_strategy_id=query.strategy_id,
            m070_strategy_version=query.strategy_version,
            m070_ranking_model_id=query.ranking_model_id,
            m070_ranking_model_version=query.ranking_model_version,
            m070_risk_policy_id=query.risk_policy_id,
            m070_risk_policy_version=query.risk_policy_version,
            m070_sizing_policy_id=query.sizing_policy_id,
            m070_sizing_policy_version=query.sizing_policy_version,
            m070_requested_universe=query.requested_universe,
            m070_as_of=query.as_of,
            survivorship_candidates=survivorship_candidates,
            portfolio_lookup=portfolio_lookup,
            instrument_master=instrument_master,
        )
