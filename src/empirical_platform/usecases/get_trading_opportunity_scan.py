"""Retrieve a TradingOpportunityScan by full identity: concrete query and
handler.

MILESTONE-058.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.decision_candidate.scan import (
    TradingOpportunityScan as TradingOpportunityScan,
)
from empirical_platform.decision_candidate.scan_repository import TradingOpportunityScanRepository
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import TradingOpportunityScanId


@dataclass(frozen=True, slots=True)
class GetTradingOpportunityScanQuery:
    """Request to retrieve a TradingOpportunityScan by its full frozen identity."""

    identity: DomainIdentity[TradingOpportunityScanId]


class GetTradingOpportunityScanHandler:
    """Retrieves a TradingOpportunityScan for one `GetTradingOpportunityScanQuery`."""

    __slots__ = ("_trading_opportunity_scan_repository",)

    def __init__(
        self, *, trading_opportunity_scan_repository: TradingOpportunityScanRepository
    ) -> None:
        self._trading_opportunity_scan_repository = trading_opportunity_scan_repository

    def handle(self, query: GetTradingOpportunityScanQuery) -> TradingOpportunityScan:
        """Load a TradingOpportunityScan by identity and return it.

        No bounded snapshot is needed here (unlike the four lifecycle
        aggregates' own query handlers): `TradingOpportunityScan` is already
        immutable and carries no mutation/version internals to hide.
        """
        return self._trading_opportunity_scan_repository.get(query.identity)
