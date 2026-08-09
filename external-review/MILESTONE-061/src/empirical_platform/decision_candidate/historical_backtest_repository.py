"""Persistence-neutral repository contract for M061 historical backtest runs."""

from __future__ import annotations

from typing import Protocol

from empirical_platform.decision_candidate.historical_backtest import HistoricalBacktestRun
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import BacktestRunId


class HistoricalBacktestRunRepository(Protocol):
    """Persistence-neutral repository contract for immutable historical backtest runs."""

    def get(self, identity: DomainIdentity[BacktestRunId]) -> HistoricalBacktestRun:
        """Load a historical backtest run by canonical identity."""
        ...

    def add(self, run: HistoricalBacktestRun) -> None:
        """Persist a new historical backtest run that must not already exist."""
        ...
