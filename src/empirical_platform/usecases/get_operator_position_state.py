"""MILESTONE-076 -- derive operator-asserted position state at an `as_of`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from empirical_platform.decision_candidate.operator_position_ledger import (
    DerivedPositionState,
    derive_position_state,
)
from empirical_platform.decision_candidate.operator_position_ledger_repository import (
    OperatorPositionLedgerRepository,
)

__all__ = ["GetOperatorPositionStateHandler", "GetOperatorPositionStateQuery"]


@dataclass(frozen=True, slots=True)
class GetOperatorPositionStateQuery:
    """`as_of` is inclusive; events stamped after it are excluded."""

    as_of: datetime


class GetOperatorPositionStateHandler:
    """Read-only. Folds the append-only ledger into derived state."""

    __slots__ = ("_ledger",)

    def __init__(self, *, ledger_repository: OperatorPositionLedgerRepository) -> None:
        self._ledger = ledger_repository

    def handle(self, query: GetOperatorPositionStateQuery) -> DerivedPositionState:
        return derive_position_state(events=self._ledger.list_all(), as_of=query.as_of)
