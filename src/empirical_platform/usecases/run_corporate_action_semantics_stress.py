"""Run the CORPORATE_ACTION_SEMANTICS_STRESS diagnostic end-to-end.

MILESTONE-065. Loads two already-persisted `DatasetSnapshotAuthority`
records (one `SPLIT_ADJUSTED`, one `RAW_UNADJUSTED`) plus their own
on-disk M061-compatible dataset artifacts, cross-checks each artifact's
own hash against its snapshot's declared `normalized_sha256` (rejecting a
stale or substituted artifact file before any backtest runs), and then
calls the real, unmodified M061 `build_historical_backtest_run()` twice.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from empirical_platform.decision_candidate.corporate_action_stress import (
    CorporateActionSemanticsStressResult,
    build_corporate_action_semantics_stress,
)
from empirical_platform.decision_candidate.dataset_snapshot_repository import (
    CorporateActionSemanticsStressRepository,
    DatasetSnapshotRepository,
)
from empirical_platform.decision_candidate.historical_backtest import HistoricalDataset
from empirical_platform.decision_candidate.historical_backtest_repository import (
    HistoricalBacktestRunRepository,
)
from empirical_platform.decision_candidate.position_plan import PositionSizingContext
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import BacktestRunId, CorporateActionStressId, DatasetId
from empirical_platform.shared.identifiers import RuntimeIdentifierGenerator

__all__ = [
    "CorporateActionSemanticsStressResult",
    "PositionSizingContext",
    "RunCorporateActionSemanticsStressCommand",
    "RunCorporateActionSemanticsStressHandler",
]


@dataclass(frozen=True, slots=True)
class RunCorporateActionSemanticsStressCommand:
    """Request to run one corporate-action semantics stress diagnostic."""

    identity: DomainIdentity[CorporateActionStressId]
    dataset_id: DatasetId
    correct_dataset_version: str
    correct_dataset: HistoricalDataset
    naive_dataset_version: str
    naive_dataset: HistoricalDataset
    correct_run_identity: DomainIdentity[BacktestRunId]
    naive_run_identity: DomainIdentity[BacktestRunId]
    sizing_context: PositionSizingContext
    runtime_identifier_generator: RuntimeIdentifierGenerator
    reference_window_size: int = 5


class RunCorporateActionSemanticsStressHandler:
    """Verify the supplied datasets match their own declared snapshot
    authority, run the frozen M061 engine twice, and persist both runs
    plus the comparison result -- through the unmodified M061
    `HistoricalBacktestRunRepository`, never a second persistence path for
    backtest runs."""

    __slots__ = (
        "_historical_backtest_run_repository",
        "_dataset_snapshot_repository",
        "_stress_repository",
    )

    def __init__(
        self,
        *,
        historical_backtest_run_repository: HistoricalBacktestRunRepository,
        dataset_snapshot_repository: DatasetSnapshotRepository,
        stress_repository: CorporateActionSemanticsStressRepository,
    ) -> None:
        self._historical_backtest_run_repository = historical_backtest_run_repository
        self._dataset_snapshot_repository = dataset_snapshot_repository
        self._stress_repository = stress_repository

    def handle(
        self, command: RunCorporateActionSemanticsStressCommand
    ) -> CorporateActionSemanticsStressResult:
        correct_snapshot = self._dataset_snapshot_repository.get(
            command.dataset_id, command.correct_dataset_version
        )
        naive_snapshot = self._dataset_snapshot_repository.get(
            command.dataset_id, command.naive_dataset_version
        )
        if command.correct_dataset.authority.sha256 != correct_snapshot.normalized_sha256:
            raise ValueError(
                "correct dataset artifact does not match its own declared dataset snapshot "
                f"normalized_sha256 (expected {correct_snapshot.normalized_sha256!r}, got "
                f"{command.correct_dataset.authority.sha256!r})"
            )
        if command.naive_dataset.authority.sha256 != naive_snapshot.normalized_sha256:
            raise ValueError(
                "naive dataset artifact does not match its own declared dataset snapshot "
                f"normalized_sha256 (expected {naive_snapshot.normalized_sha256!r}, got "
                f"{command.naive_dataset.authority.sha256!r})"
            )

        result, correct_run, naive_run = build_corporate_action_semantics_stress(
            identity=command.identity,
            correct_run_identity=command.correct_run_identity,
            naive_run_identity=command.naive_run_identity,
            correct_dataset=command.correct_dataset,
            naive_dataset=command.naive_dataset,
            sizing_context=command.sizing_context,
            runtime_identifier_generator=command.runtime_identifier_generator,
            reference_window_size=command.reference_window_size,
        )
        self._historical_backtest_run_repository.add(correct_run)
        self._historical_backtest_run_repository.add(naive_run)
        self._stress_repository.add(result)
        return result


def build_run_corporate_action_semantics_stress_command(
    *,
    stress_governance_id: str,
    dataset_id: str,
    correct_dataset_version: str,
    correct_dataset: HistoricalDataset,
    naive_dataset_version: str,
    naive_dataset: HistoricalDataset,
    correct_run_governance_id: str,
    naive_run_governance_id: str,
    account_equity: Decimal,
    risk_percent: Decimal,
    runtime_identifier_generator: RuntimeIdentifierGenerator,
    reference_window_size: int = 5,
) -> RunCorporateActionSemanticsStressCommand:
    """Build one real M065 command from plain application-layer inputs."""
    return RunCorporateActionSemanticsStressCommand(
        identity=DomainIdentity(
            governance_id=CorporateActionStressId(stress_governance_id),
            runtime_id=runtime_identifier_generator.generate(),
        ),
        dataset_id=DatasetId(dataset_id),
        correct_dataset_version=correct_dataset_version,
        correct_dataset=correct_dataset,
        naive_dataset_version=naive_dataset_version,
        naive_dataset=naive_dataset,
        correct_run_identity=DomainIdentity(
            governance_id=BacktestRunId(correct_run_governance_id),
            runtime_id=runtime_identifier_generator.generate(),
        ),
        naive_run_identity=DomainIdentity(
            governance_id=BacktestRunId(naive_run_governance_id),
            runtime_id=runtime_identifier_generator.generate(),
        ),
        sizing_context=PositionSizingContext(
            account_equity=account_equity, risk_percent=risk_percent
        ),
        runtime_identifier_generator=runtime_identifier_generator,
        reference_window_size=reference_window_size,
    )
