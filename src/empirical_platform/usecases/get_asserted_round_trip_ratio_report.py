"""MILESTONE-081 query. Read-only: no append path is reachable from here."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from empirical_platform.decision_candidate.operator_asserted_round_trip_ratio import (
    AssertedRoundTripRatioReport,
    build_asserted_round_trip_ratio_report,
)
from empirical_platform.decision_candidate.operator_position_ledger_repository import (
    OperatorPositionLedgerRepository,
)

__all__ = [
    "GetAssertedRoundTripRatioReportHandler",
    "GetAssertedRoundTripRatioReportQuery",
]


@dataclass(frozen=True, slots=True)
class GetAssertedRoundTripRatioReportQuery:
    """Both cutoffs are required and validated here as well as in the domain.

    Same reasoning as M079 and M080: a naive timestamp reaching the domain would
    be reported as a verdict about the operator's data, when in fact the REQUEST
    was malformed. A false diagnosis is worse than a crash.
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


class GetAssertedRoundTripRatioReportHandler:
    """Reads the frozen M076 ledger and returns M081's ratio report."""

    __slots__ = ("_repository",)

    def __init__(
        self,
        *,
        operator_position_ledger_repository: OperatorPositionLedgerRepository | None,
    ) -> None:
        self._repository = operator_position_ledger_repository

    def handle(self, query: GetAssertedRoundTripRatioReportQuery) -> AssertedRoundTripRatioReport:
        if self._repository is None:
            return build_asserted_round_trip_ratio_report(
                events=(),
                effective_as_of=query.effective_as_of,
                knowledge_as_of=query.knowledge_as_of,
                ledger_available=False,
            )
        # A database-level failure PROPAGATES, exactly as in M079 and M080: a
        # dead connection is an infrastructure fault, not an absence of
        # evidence, and disguising it as a soft verdict would be a false
        # diagnosis about the operator's data.
        return build_asserted_round_trip_ratio_report(
            events=self._repository.list_all(),
            effective_as_of=query.effective_as_of,
            knowledge_as_of=query.knowledge_as_of,
        )
