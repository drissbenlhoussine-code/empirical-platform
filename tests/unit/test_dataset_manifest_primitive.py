from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from empirical_platform.datasets import DatasetManifest
from empirical_platform.identifiers import CampaignId, DatasetId, RunId


def test_dataset_manifest_is_immutable_run_owned_and_storage_layout_neutral() -> None:
    manifest = DatasetManifest(
        run_id=RunId("RUN-0001"),
        manifest_id=DatasetId("DATASET-0001"),
        recorded_at=datetime(2026, 7, 17, tzinfo=UTC),
        source="approved empirical input set",
        acquisition_method="documented acquisition procedure",
        normalization_method="documented normalization procedure",
        notes=["bounded note"],
    )

    assert manifest.run_id == RunId("RUN-0001")
    assert manifest.manifest_id == DatasetId("DATASET-0001")
    assert manifest.notes == ("bounded note",)
    assert not hasattr(manifest, "bucket")
    assert not hasattr(manifest, "object_key")
    assert not hasattr(manifest, "vendor")
    with pytest.raises(FrozenInstanceError):
        manifest.source = "changed"  # type: ignore[misc]


def test_dataset_manifest_rejects_wrong_identity_and_blank_fields() -> None:
    with pytest.raises(TypeError):
        DatasetManifest(  # type: ignore[arg-type]
            run_id=CampaignId("CAMP-0001"),
            recorded_at=datetime(2026, 7, 17, tzinfo=UTC),
            source="source",
        )
    with pytest.raises(ValueError, match="source"):
        DatasetManifest(
            run_id=RunId("RUN-0001"),
            recorded_at=datetime(2026, 7, 17, tzinfo=UTC),
            source=" ",
        )
    with pytest.raises(ValueError, match="notes"):
        DatasetManifest(
            run_id=RunId("RUN-0001"),
            recorded_at=datetime(2026, 7, 17, tzinfo=UTC),
            source="source",
            notes=(" ",),
        )
