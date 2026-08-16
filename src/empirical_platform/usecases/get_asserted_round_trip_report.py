"""MILESTONE-080 query. Read-only: no append path is reachable from here."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from empirical_platform.decision_candidate.operator_asserted_round_trip import (
    AssertedRoundTripReport,
    build_asserted_round_trip_report,
)
from empirical_platform.decision_candidate.operator_position_ledger_repository import (
    OperatorPositionLedgerRepository,
)

__all__ = [
    "GetAssertedRoundTripReportHandler",
    "GetAssertedRoundTripReportQuery",
]


@dataclass(frozen=True, slots=True)
class GetAssertedRoundTripReportQuery:
    """Both cutoffs are required and validated here as well as in the domain.

    M078's R03 lesson: a naive timestamp reaching the domain was reported as a
    LEDGER_INCOHERENT verdict, which told the operator their persisted data was
    corrupt when in fact their REQUEST was malformed. A false diagnosis is worse
    than a crash, so the request is validated at the request boundary.
    """

    effective_as_of: datetime
    knowledge_as_of: datetime

    def __post_init__(self) -> None:
        for label, moment in (
            ("effective_as_of", self.effective_as_of),
            ("knowledge_as_of", self.knowledge_as_of),
        ):
            if moment.tzinfo is None or moment.utcoffset() is None:
                raise ValueError(f"{label} must be timezone-aware; a naive datetime has no instant")


class GetAssertedRoundTripReportHandler:
    """Reads the frozen M076 ledger and returns M080's report."""

    __slots__ = ("_repository",)

    def __init__(
        self,
        *,
        operator_position_ledger_repository: OperatorPositionLedgerRepository | None,
    ) -> None:
        self._repository = operator_position_ledger_repository

    def handle(self, query: GetAssertedRoundTripReportQuery) -> AssertedRoundTripReport:
        if self._repository is None:
            return build_asserted_round_trip_report(
                events=(),
                effective_as_of=query.effective_as_of,
                knowledge_as_of=query.knowledge_as_of,
                ledger_available=False,
            )
        # A database-level failure PROPAGATES: a dead connection is an
        # infrastructure fault, not an absence of evidence, and disguising it as
        # a soft verdict would be the false diagnosis M078's R03 warned about.
        # Matches M079's handler exactly.
        return build_asserted_round_trip_report(
            events=self._repository.list_all(),
            effective_as_of=query.effective_as_of,
            knowledge_as_of=query.knowledge_as_of,
        )
