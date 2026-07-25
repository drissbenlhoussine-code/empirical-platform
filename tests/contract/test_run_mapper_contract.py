"""MILESTONE-021 contract tests for RunMapper, using an in-memory fake."""

from __future__ import annotations

import uuid
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest
from tests.contract._mapper_fakes import FakeRunMapper

from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId, DatasetId, RunId
from empirical_platform.run._reconstruction import _reconstruct_run
from empirical_platform.run.aggregate import Run
from empirical_platform.shared.contracts.mapping import MapperError, MapperErrorCategory
from empirical_platform.shared.identifiers import RuntimeIdentifier

OCCURRED_AT = datetime(2026, 7, 26, tzinfo=UTC)


def _identity() -> DomainIdentity[RunId]:
    return DomainIdentity(
        governance_id=RunId("RUN-0001"),
        runtime_id=RuntimeIdentifier(str(uuid.uuid4())),
    )


def _run() -> Run:
    return Run(identity=_identity(), campaign_id=CampaignId("CAMP-0001"))


def test_round_trip_preserves_identity_and_initial_state() -> None:
    mapper = FakeRunMapper()
    run = _run()

    record = mapper.to_durable_record(run)
    state = mapper.from_durable_record(record)
    restored = _reconstruct_run(state)

    assert restored.identity == run.identity
    assert restored.campaign_id == run.campaign_id
    assert restored.version == run.version
    assert restored.state == run.state
    assert restored.manifests == run.manifests


def test_round_trip_preserves_manifests_order_and_optional_fields() -> None:
    from empirical_platform.datasets import DatasetManifest

    mapper = FakeRunMapper()
    run = _run()
    run.authorize(actor="tester", occurred_at=OCCURRED_AT)
    run.append_manifest(
        DatasetManifest(
            run_id=RunId("RUN-0001"),
            recorded_at=OCCURRED_AT,
            source="vendor-a",
            manifest_id=DatasetId("DATASET-0001"),
            notes=("first",),
        )
    )
    run.append_manifest(
        DatasetManifest(
            run_id=RunId("RUN-0001"),
            recorded_at=OCCURRED_AT,
            source="vendor-b",
            acquisition_method=None,
            normalization_method=None,
            manifest_id=None,
            notes=(),
        )
    )

    record = mapper.to_durable_record(run)
    state = mapper.from_durable_record(record)
    restored = _reconstruct_run(state)

    assert len(restored.manifests) == 2
    assert restored.manifests[0].source == "vendor-a"
    assert restored.manifests[0].manifest_id == DatasetId("DATASET-0001")
    assert restored.manifests[1].manifest_id is None
    assert restored.manifests[1].notes == ()
    assert restored.version == run.version


def test_durable_record_is_immutable() -> None:
    mapper = FakeRunMapper()
    record = mapper.to_durable_record(_run())

    with pytest.raises(FrozenInstanceError):
        record.lifecycle_state = "changed"  # type: ignore[misc]


def test_malformed_lifecycle_state_raises_mapper_error() -> None:
    mapper = FakeRunMapper()
    record = mapper.to_durable_record(_run())
    corrupted = type(record)(
        identity=record.identity,
        campaign_id=record.campaign_id,
        lifecycle_state="NOT_A_REAL_STATE",
        manifests=record.manifests,
        version=record.version,
        next_transition_sequence=record.next_transition_sequence,
        transition_history=record.transition_history,
    )

    with pytest.raises(MapperError) as excinfo:
        mapper.from_durable_record(corrupted)

    assert excinfo.value.category is MapperErrorCategory.INVALID_DURABLE_RECORD
    assert excinfo.value.aggregate_kind == "Run"
