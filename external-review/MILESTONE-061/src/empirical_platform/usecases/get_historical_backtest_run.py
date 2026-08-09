"""Retrieve one historical backtest run by full identity.

MILESTONE-061.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.decision_candidate.historical_backtest import HistoricalBacktestRun
from empirical_platform.decision_candidate.historical_backtest_repository import (
    HistoricalBacktestRunRepository,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import BacktestRunId


@dataclass(frozen=True, slots=True)
class GetHistoricalBacktestRunQuery:
    """Request to retrieve one historical backtest run by canonical identity."""

    identity: DomainIdentity[BacktestRunId]


class GetHistoricalBacktestRunHandler:
    """Retrieve one persisted historical backtest run."""

    __slots__ = ("_repository",)

    def __init__(self, *, repository: HistoricalBacktestRunRepository) -> None:
        self._repository = repository

    def handle(self, query: GetHistoricalBacktestRunQuery) -> HistoricalBacktestRun:
        return self._repository.get(query.identity)
