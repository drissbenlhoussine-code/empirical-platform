"""Concrete PostgreSQL repositories for M065 dataset snapshots, corporate
actions, and the corporate-action semantics stress diagnostic."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any, cast

from empirical_platform.decision_candidate.corporate_action_stress import (
    CorporateActionSemanticsStressResult,
    StressComparison,
)
from empirical_platform.decision_candidate.corporate_actions import (
    CorporateActionManifest,
    CorporateActionType,
    SplitAction,
    SymbolChangeAction,
)
from empirical_platform.decision_candidate.dataset_snapshot import (
    CorporateActionSemantics,
    DatasetSnapshotAuthority,
    PriceSemantics,
    SourceFileManifestEntry,
)
from empirical_platform.decision_candidate.instrument_master import InstrumentId
from empirical_platform.decision_candidate.market_data import BarInterval, Instrument
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import BacktestRunId, CorporateActionStressId, DatasetId
from empirical_platform.shared.contracts.repository import AggregateAlreadyExists, AggregateNotFound
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories._errors import (
    unique_violation_constraint_name,
)

_DATASET_SNAPSHOT_KIND = "DatasetSnapshotAuthority"
_CORPORATE_ACTION_MANIFEST_KIND = "CorporateActionManifest"
_STRESS_KIND = "CorporateActionSemanticsStressResult"
_STRESS_UNIQUE_CONSTRAINTS = {
    "pk_corporate_action_semantics_stress",
    "uq_corporate_action_semantics_stress_governance_id",
}


class PostgresDatasetSnapshotRepository:
    """Concrete, storage-aware repository for immutable dataset snapshot
    authorities."""

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def get(self, dataset_id: DatasetId, dataset_version: str) -> DatasetSnapshotAuthority:
        with self._service.unit_of_work() as work:
            rows = work.execute(
                "SELECT * FROM dataset_snapshot "
                "WHERE dataset_id = :dataset_id AND dataset_version = :dataset_version",
                {"dataset_id": str(dataset_id), "dataset_version": dataset_version},
            )
            if not rows:
                raise AggregateNotFound(
                    aggregate_kind=_DATASET_SNAPSHOT_KIND,
                    identity=(str(dataset_id), dataset_version),
                )
            file_rows = work.execute(
                "SELECT * FROM dataset_snapshot_source_file "
                "WHERE dataset_id = :dataset_id AND dataset_version = :dataset_version "
                "ORDER BY file_name",
                {"dataset_id": str(dataset_id), "dataset_version": dataset_version},
            )
        return _row_to_snapshot(rows[0], file_rows)

    def add(self, snapshot: DatasetSnapshotAuthority) -> None:
        insert_sql = (
            "INSERT INTO dataset_snapshot ("
            "dataset_id, dataset_version, source_kind, source_name, source_reference, "
            "license_note, snapshot_created_at, bar_interval, start_timestamp, end_timestamp, "
            "instrument_count, total_row_count, file_count, bundle_sha256, normalized_sha256, "
            "price_semantics, corporate_action_semantics, corporate_action_manifest_hash, "
            "dividend_handling"
            ") VALUES ("
            ":dataset_id, :dataset_version, :source_kind, :source_name, :source_reference, "
            ":license_note, :snapshot_created_at, :bar_interval, :start_timestamp, "
            ":end_timestamp, :instrument_count, :total_row_count, :file_count, :bundle_sha256, "
            ":normalized_sha256, :price_semantics, :corporate_action_semantics, "
            ":corporate_action_manifest_hash, :dividend_handling"
            ")"
        )
        file_insert_sql = (
            "INSERT INTO dataset_snapshot_source_file ("
            "dataset_id, dataset_version, file_name, instrument_symbol, sha256, row_count"
            ") VALUES ("
            ":dataset_id, :dataset_version, :file_name, :instrument_symbol, :sha256, :row_count"
            ")"
        )
        with self._service.unit_of_work() as work:
            try:
                work.execute(
                    insert_sql,
                    {
                        "dataset_id": str(snapshot.dataset_id),
                        "dataset_version": snapshot.dataset_version,
                        "source_kind": snapshot.source_kind,
                        "source_name": snapshot.source_name,
                        "source_reference": snapshot.source_reference,
                        "license_note": snapshot.license_note,
                        "snapshot_created_at": snapshot.snapshot_created_at,
                        "bar_interval": snapshot.interval.value,
                        "start_timestamp": snapshot.start_timestamp,
                        "end_timestamp": snapshot.end_timestamp,
                        "instrument_count": snapshot.instrument_count,
                        "total_row_count": snapshot.total_row_count,
                        "file_count": snapshot.file_count,
                        "bundle_sha256": snapshot.bundle_sha256,
                        "normalized_sha256": snapshot.normalized_sha256,
                        "price_semantics": snapshot.price_semantics.value,
                        "corporate_action_semantics": snapshot.corporate_action_semantics.value,
                        "corporate_action_manifest_hash": snapshot.corporate_action_manifest_hash,
                        "dividend_handling": snapshot.dividend_handling,
                    },
                )
                for entry in snapshot.source_file_manifest:
                    work.execute(
                        file_insert_sql,
                        {
                            "dataset_id": str(snapshot.dataset_id),
                            "dataset_version": snapshot.dataset_version,
                            "file_name": entry.file_name,
                            "instrument_symbol": entry.instrument_symbol,
                            "sha256": entry.sha256,
                            "row_count": entry.row_count,
                        },
                    )
            except FoundationError as exc:
                constraint_name = unique_violation_constraint_name(exc)
                if constraint_name in {"pk_dataset_snapshot"}:
                    raise AggregateAlreadyExists(
                        aggregate_kind=_DATASET_SNAPSHOT_KIND,
                        identity=(str(snapshot.dataset_id), snapshot.dataset_version),
                    ) from exc
                raise


def _row_to_snapshot(
    row: Mapping[str, Any], file_rows: Sequence[Mapping[str, Any]]
) -> DatasetSnapshotAuthority:
    manifest = tuple(
        SourceFileManifestEntry(
            file_name=str(file_row["file_name"]),
            instrument_symbol=str(file_row["instrument_symbol"]),
            sha256=str(file_row["sha256"]),
            row_count=int(file_row["row_count"]),
        )
        for file_row in file_rows
    )
    return DatasetSnapshotAuthority(
        dataset_id=DatasetId(str(row["dataset_id"])),
        dataset_version=str(row["dataset_version"]),
        source_kind=str(row["source_kind"]),
        source_name=str(row["source_name"]),
        source_reference=str(row["source_reference"]),
        license_note=str(row["license_note"]),
        snapshot_created_at=row["snapshot_created_at"],
        interval=BarInterval(str(row["bar_interval"])),
        start_timestamp=row["start_timestamp"],
        end_timestamp=row["end_timestamp"],
        instrument_count=int(row["instrument_count"]),
        total_row_count=int(row["total_row_count"]),
        file_count=int(row["file_count"]),
        source_file_manifest=manifest,
        bundle_sha256=str(row["bundle_sha256"]),
        normalized_sha256=str(row["normalized_sha256"]),
        price_semantics=PriceSemantics(str(row["price_semantics"])),
        corporate_action_semantics=CorporateActionSemantics(str(row["corporate_action_semantics"])),
        corporate_action_manifest_hash=(
            str(row["corporate_action_manifest_hash"])
            if row["corporate_action_manifest_hash"] is not None
            else None
        ),
        dividend_handling=str(row["dividend_handling"]),
    )


class PostgresCorporateActionRepository:
    """Concrete, storage-aware repository for declared corporate actions."""

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def get(self, dataset_id: DatasetId, dataset_version: str) -> CorporateActionManifest:
        with self._service.unit_of_work() as work:
            rows = work.execute(
                "SELECT * FROM corporate_action "
                "WHERE dataset_id = :dataset_id AND dataset_version = :dataset_version "
                "ORDER BY instrument_id, effective_timestamp, action_type",
                {"dataset_id": str(dataset_id), "dataset_version": dataset_version},
            )
            if not rows:
                raise AggregateNotFound(
                    aggregate_kind=_CORPORATE_ACTION_MANIFEST_KIND,
                    identity=(str(dataset_id), dataset_version),
                )
        actions = tuple(_row_to_action(row) for row in rows)
        return CorporateActionManifest(str(dataset_id), dataset_version, actions)

    def add(self, manifest: CorporateActionManifest) -> None:
        insert_sql = (
            "INSERT INTO corporate_action ("
            "dataset_id, dataset_version, instrument_id, effective_timestamp, action_type, "
            "ratio_new_shares, ratio_old_shares, old_symbol, new_symbol, source_kind"
            ") VALUES ("
            ":dataset_id, :dataset_version, :instrument_id, :effective_timestamp, :action_type, "
            ":ratio_new_shares, :ratio_old_shares, :old_symbol, :new_symbol, :source_kind"
            ")"
        )
        with self._service.unit_of_work() as work:
            try:
                for action in manifest.actions:
                    params: dict[str, int | str | None]
                    if isinstance(action, SplitAction):
                        params = {
                            "ratio_new_shares": action.ratio_new_shares,
                            "ratio_old_shares": action.ratio_old_shares,
                            "old_symbol": None,
                            "new_symbol": None,
                        }
                    else:
                        params = {
                            "ratio_new_shares": None,
                            "ratio_old_shares": None,
                            "old_symbol": str(action.old_symbol),
                            "new_symbol": str(action.new_symbol),
                        }
                    work.execute(
                        insert_sql,
                        {
                            "dataset_id": manifest.dataset_id,
                            "dataset_version": manifest.dataset_version,
                            "instrument_id": str(action.instrument_id),
                            "effective_timestamp": action.effective_timestamp,
                            "action_type": action.action_type.value,
                            "source_kind": action.source_kind,
                            **params,
                        },
                    )
            except FoundationError as exc:
                constraint_name = unique_violation_constraint_name(exc)
                if constraint_name in {"pk_corporate_action"}:
                    raise AggregateAlreadyExists(
                        aggregate_kind=_CORPORATE_ACTION_MANIFEST_KIND,
                        identity=(manifest.dataset_id, manifest.dataset_version),
                    ) from exc
                raise


def _row_to_action(row: Mapping[str, Any]) -> SplitAction | SymbolChangeAction:
    action_type = CorporateActionType(str(row["action_type"]))
    instrument_id = InstrumentId(str(row["instrument_id"]))
    if action_type is CorporateActionType.SYMBOL_CHANGE:
        return SymbolChangeAction(
            instrument_id=instrument_id,
            action_type=action_type,
            effective_timestamp=row["effective_timestamp"],
            old_symbol=Instrument(str(row["old_symbol"])),
            new_symbol=Instrument(str(row["new_symbol"])),
            source_kind=str(row["source_kind"]),
        )
    return SplitAction(
        instrument_id=instrument_id,
        action_type=action_type,
        effective_timestamp=row["effective_timestamp"],
        ratio_new_shares=int(row["ratio_new_shares"]),
        ratio_old_shares=int(row["ratio_old_shares"]),
        source_kind=str(row["source_kind"]),
    )


class PostgresCorporateActionSemanticsStressRepository:
    """Concrete, storage-aware repository for immutable corporate-action
    semantics stress diagnostic results."""

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def get(
        self, identity: DomainIdentity[CorporateActionStressId]
    ) -> CorporateActionSemanticsStressResult:
        with self._service.unit_of_work() as work:
            rows = work.execute(
                "SELECT * FROM corporate_action_semantics_stress "
                "WHERE runtime_id = :runtime_id AND governance_id = :governance_id",
                {
                    "runtime_id": str(identity.runtime_id),
                    "governance_id": str(identity.governance_id),
                },
            )
            if not rows:
                raise AggregateNotFound(aggregate_kind=_STRESS_KIND, identity=identity)
        return _row_to_stress(rows[0])

    def add(self, result: CorporateActionSemanticsStressResult) -> None:
        insert_sql = (
            "INSERT INTO corporate_action_semantics_stress ("
            "runtime_id, governance_id, dataset_id, correct_dataset_version, "
            "correct_run_governance_id, naive_dataset_version, naive_run_governance_id, "
            "comparison, correct_executed_trade_count, naive_executed_trade_count, "
            "correct_net_pnl_total, naive_net_pnl_total, correct_total_r_total, "
            "naive_total_r_total"
            ") VALUES ("
            ":runtime_id, :governance_id, :dataset_id, :correct_dataset_version, "
            ":correct_run_governance_id, :naive_dataset_version, :naive_run_governance_id, "
            ":comparison, :correct_executed_trade_count, :naive_executed_trade_count, "
            ":correct_net_pnl_total, :naive_net_pnl_total, :correct_total_r_total, "
            ":naive_total_r_total"
            ")"
        )
        with self._service.unit_of_work() as work:
            try:
                work.execute(
                    insert_sql,
                    {
                        "runtime_id": str(result.identity.runtime_id),
                        "governance_id": str(result.identity.governance_id),
                        "dataset_id": str(result.dataset_id),
                        "correct_dataset_version": result.correct_dataset_version,
                        "correct_run_governance_id": str(result.correct_run_id),
                        "naive_dataset_version": result.naive_dataset_version,
                        "naive_run_governance_id": str(result.naive_run_id),
                        "comparison": result.comparison.value,
                        "correct_executed_trade_count": result.correct_executed_trade_count,
                        "naive_executed_trade_count": result.naive_executed_trade_count,
                        "correct_net_pnl_total": result.correct_net_pnl_total,
                        "naive_net_pnl_total": result.naive_net_pnl_total,
                        "correct_total_r_total": result.correct_total_r_total,
                        "naive_total_r_total": result.naive_total_r_total,
                    },
                )
            except FoundationError as exc:
                constraint_name = unique_violation_constraint_name(exc)
                if constraint_name in _STRESS_UNIQUE_CONSTRAINTS:
                    raise AggregateAlreadyExists(
                        aggregate_kind=_STRESS_KIND, identity=result.identity
                    ) from exc
                raise


def _row_to_stress(row: Mapping[str, Any]) -> CorporateActionSemanticsStressResult:
    return CorporateActionSemanticsStressResult(
        identity=DomainIdentity(
            governance_id=CorporateActionStressId(str(row["governance_id"])),
            runtime_id=RuntimeIdentifier(str(row["runtime_id"])),
        ),
        dataset_id=DatasetId(str(row["dataset_id"])),
        correct_dataset_version=str(row["correct_dataset_version"]),
        correct_run_id=BacktestRunId(str(row["correct_run_governance_id"])),
        naive_dataset_version=str(row["naive_dataset_version"]),
        naive_run_id=BacktestRunId(str(row["naive_run_governance_id"])),
        comparison=StressComparison(str(row["comparison"])),
        correct_executed_trade_count=int(row["correct_executed_trade_count"]),
        naive_executed_trade_count=int(row["naive_executed_trade_count"]),
        correct_net_pnl_total=cast(Decimal, row["correct_net_pnl_total"]),
        naive_net_pnl_total=cast(Decimal, row["naive_net_pnl_total"]),
        correct_total_r_total=cast(Decimal, row["correct_total_r_total"]),
        naive_total_r_total=cast(Decimal, row["naive_total_r_total"]),
    )
