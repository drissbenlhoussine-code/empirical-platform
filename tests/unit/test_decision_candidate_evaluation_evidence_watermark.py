"""MILESTONE-083 -- domain-level unit tests for EvaluationEvidenceWatermark.

Pure functions and dataclasses only: no database. The exactness and
immutability guarantees are DATABASE-enforced (see the M083 migration and
`tests/integration/test_m083_evaluation_evidence_watermark_lifecycle.py`);
these tests cover only what this module itself can be wrong about.
"""

from __future__ import annotations

import pytest

from empirical_platform.decision_candidate.evaluation_evidence_watermark import (
    BLANK_CHARACTERS,
    EvaluationEvidenceWatermark,
)
from empirical_platform.decision_candidate.operator_event_receipt import (
    BLANK_CHARACTERS as M082_BLANK_CHARACTERS,
)


def test_blank_characters_agree_with_m082_character_by_character() -> None:
    """The database CHECK constraints on both tables must classify identically.

    A divergence here would mean a watermark id the Python domain calls blank
    could differ from what the migration's CHECK constraint refuses, or vice
    versa -- exactly the M082 owner findings 12/16 defect class, reproduced
    here as a standing regression test rather than argued about.
    """
    assert BLANK_CHARACTERS == M082_BLANK_CHARACTERS
    assert len(BLANK_CHARACTERS) == 29


@pytest.mark.parametrize("blank_id", ["", "   ", "\t", "\n", " ", " ", "　"])
def test_a_blank_watermark_governance_id_is_refused(blank_id: str) -> None:
    with pytest.raises(ValueError, match="watermark_governance_id must be non-empty"):
        EvaluationEvidenceWatermark(watermark_governance_id=blank_id, receipt_governance_ids=())


def test_a_well_formed_watermark_is_accepted() -> None:
    watermark = EvaluationEvidenceWatermark(
        watermark_governance_id="WM-1",
        receipt_governance_ids=("RC-A", "RC-B", "RC-C"),
    )
    assert watermark.watermark_governance_id == "WM-1"
    assert watermark.receipt_governance_ids == ("RC-A", "RC-B", "RC-C")
    assert watermark.captured_receipt_count == 3


def test_an_empty_receipt_set_is_valid_and_explicit() -> None:
    watermark = EvaluationEvidenceWatermark(
        watermark_governance_id="WM-EMPTY", receipt_governance_ids=()
    )
    assert watermark.receipt_governance_ids == ()
    assert watermark.captured_receipt_count == 0


def test_duplicate_receipt_ids_are_refused() -> None:
    with pytest.raises(ValueError, match="must not contain duplicates"):
        EvaluationEvidenceWatermark(
            watermark_governance_id="WM-DUP", receipt_governance_ids=("RC-A", "RC-A")
        )


def test_out_of_order_receipt_ids_are_refused() -> None:
    with pytest.raises(ValueError, match="canonical ascending order"):
        EvaluationEvidenceWatermark(
            watermark_governance_id="WM-BAD-ORDER", receipt_governance_ids=("RC-B", "RC-A")
        )


def test_the_type_is_frozen() -> None:
    watermark = EvaluationEvidenceWatermark(
        watermark_governance_id="WM-FROZEN", receipt_governance_ids=("RC-A",)
    )
    with pytest.raises(AttributeError):
        watermark.watermark_governance_id = "WM-CHANGED"  # type: ignore[misc]
