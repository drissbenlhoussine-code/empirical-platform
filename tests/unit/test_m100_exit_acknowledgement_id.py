"""M100 -- exit acknowledgement identifiers are unique and fit the identifier limit.

Regression for a defect the end-to-end acceptance matrix found (ACC-17c): the id was built as
`f"XACK-{attempt_id}-{sequence}"[:64]`, which for the 63-character attempt id of a plan-minted
MANDATORY_EXIT cut the sequence off, so a second acknowledgement of one attempt collided with the
first on the primary key.
"""

from __future__ import annotations

import pytest

from empirical_platform.shared.persistence.postgres_repositories.position_exit_repositories import (  # noqa: E501
    _round_id,
)
from empirical_platform.usecases.position_exit import _acknowledgement_id


@pytest.mark.parametrize(
    "attempt_id",
    [
        "XAT-INT-PRP-089-PAPER-20261106T104737Z-1",
        "XAT-plan-PLAN-INT-PRP-089-PAPER-20261106T104737Z-STOP",
        "XAT-plan-PLAN-INT-PRP-089-PAPER-20261106T104737Z-TARGET",
        "XAT-plan-PLAN-INT-PRP-089-PAPER-20261106T104737Z-MANDATORY_EXIT",
        "XAT-pg3-" + "a" * 36,
        "X" * 64,
    ],
)
def test_ids_are_unique_per_sequence_and_within_the_limit(attempt_id: str) -> None:
    ids = [_acknowledgement_id(attempt_id, sequence) for sequence in range(1, 40)]
    assert len(set(ids)) == len(ids)
    assert all(len(i) <= 64 for i in ids)


def test_ids_that_already_fit_keep_their_readable_form() -> None:
    attempt_id = "XAT-plan-PLAN-INT-PRP-089-PAPER-20261106T104737Z-STOP"
    assert _acknowledgement_id(attempt_id, 2) == f"XACK-{attempt_id}-2"


def test_two_long_attempt_ids_never_share_an_acknowledgement_id() -> None:
    first = "XAT-plan-PLAN-INT-PRP-089-PAPER-20261106T104737Z-MANDATORY_EXIT"
    second = "XAT-plan-PLAN-INT-PRP-089-PAPER-20261106T104738Z-MANDATORY_EXIT"
    assert _acknowledgement_id(first, 1) != _acknowledgement_id(second, 1)


@pytest.mark.parametrize(
    "attempt_id",
    [
        "XAT-plan-PLAN-INT-PRP-089-PAPER-20261106T104737Z-STOP",
        "XAT-plan-PLAN-INT-PRP-089-PAPER-20261106T104737Z-MANDATORY_EXIT",
        "X" * 64,
    ],
)
def test_reconciliation_round_ids_are_unique_per_sequence_and_within_the_limit(
    attempt_id: str,
) -> None:
    ids = [_round_id(attempt_id, sequence) for sequence in range(1, 40)]
    assert len(set(ids)) == len(ids) and all(len(i) <= 64 for i in ids)
    if len(f"XRND-{attempt_id}-39") <= 64:
        assert _round_id(attempt_id, 2) == f"XRND-{attempt_id}-2"
