from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from empirical_platform.evidence import CriterionResult
from empirical_platform.identifiers import EvidencePackageId, RunId


def test_criterion_result_is_immutable_evidence_package_owned_and_neutral() -> None:
    result = CriterionResult(
        evidence_package_id=EvidencePackageId("EVID-0001"),
        criterion_id="B3-L1-QUOTE-COVERAGE",
        recorded_at=datetime(2026, 7, 17, tzinfo=UTC),
        result_label="INCONCLUSIVE",
        summary="Recorded without scoring-engine semantics.",
        evidence_references=["artifact-reference"],
    )

    assert result.evidence_package_id == EvidencePackageId("EVID-0001")
    assert result.evidence_references == ("artifact-reference",)
    assert not hasattr(result, "score")
    assert not hasattr(result, "vendor")
    assert not hasattr(result, "bucket")
    with pytest.raises(FrozenInstanceError):
        result.result_label = "CHANGED"  # type: ignore[misc]


def test_criterion_result_rejects_wrong_identity_and_blank_fields() -> None:
    with pytest.raises(TypeError):
        CriterionResult(  # type: ignore[arg-type]
            evidence_package_id=RunId("RUN-0001"),
            criterion_id="criterion",
            recorded_at=datetime(2026, 7, 17, tzinfo=UTC),
            result_label="result",
        )
    with pytest.raises(ValueError, match="criterion_id"):
        CriterionResult(
            evidence_package_id=EvidencePackageId("EVID-0001"),
            criterion_id=" ",
            recorded_at=datetime(2026, 7, 17, tzinfo=UTC),
            result_label="result",
        )
    with pytest.raises(ValueError, match="evidence_references"):
        CriterionResult(
            evidence_package_id=EvidencePackageId("EVID-0001"),
            criterion_id="criterion",
            recorded_at=datetime(2026, 7, 17, tzinfo=UTC),
            result_label="result",
            evidence_references=(" ",),
        )
