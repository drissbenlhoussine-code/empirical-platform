"""Persistence-neutral aggregate reconstruction helpers."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Any

from empirical_platform.shared.domain.transitions import StateTransitionRecord
from empirical_platform.shared.domain.versioning import AggregateVersion, TransitionSequence


class ReconstructionErrorCategory(StrEnum):
    """Frozen reconstruction error categories."""

    WRONG_RECONSTRUCTION_INPUT = "WrongReconstructionInput"
    INVALID_AGGREGATE_IDENTITY = "InvalidAggregateIdentity"
    INVALID_LIFECYCLE_STATE = "InvalidLifecycleState"
    INVALID_AGGREGATE_VERSION = "InvalidAggregateVersion"
    INVALID_TRANSITION_SEQUENCE = "InvalidTransitionSequence"
    INVALID_TRANSITION_HISTORY = "InvalidTransitionHistory"
    INCONSISTENT_CURRENT_STATE = "InconsistentCurrentState"
    INVALID_COLLECTION_ELEMENT = "InvalidCollectionElement"
    DUPLICATE_OWNED_VALUE = "DuplicateOwnedValue"
    INCONSISTENT_TERMINAL_METADATA = "InconsistentTerminalMetadata"
    UNAUTHORIZED_RECONSTRUCTION_PATH = "UnauthorizedReconstructionPath"


class ReconstructionError(Exception):
    """Domain-level reconstruction failure with a persistence-neutral category."""

    def __init__(
        self,
        category: ReconstructionErrorCategory,
        message: str,
        *,
        field: str | None = None,
        context: str | None = None,
    ) -> None:
        self.category = category
        self.field = field
        self.context = context
        super().__init__(message)


def _materialize_tuple[ElementT](
    values: Iterable[ElementT],
    *,
    element_type: type[Any],
    field: str,
) -> tuple[ElementT, ...]:
    """Materialize an iterable once and verify each element type."""
    materialized = tuple(values)
    for element in materialized:
        if not isinstance(element, element_type):
            raise ReconstructionError(
                ReconstructionErrorCategory.INVALID_COLLECTION_ELEMENT,
                f"{field} contains an invalid element",
                field=field,
            )
    return materialized


def _require_instance(
    value: object,
    expected_type: type[Any],
    *,
    category: ReconstructionErrorCategory,
    field: str,
) -> None:
    """Validate a single runtime type."""
    if not isinstance(value, expected_type):
        raise ReconstructionError(
            category,
            f"{field} must be {expected_type.__name__}",
            field=field,
        )


def _validate_transition_history(
    history: tuple[StateTransitionRecord[Any], ...],
    *,
    identity: object,
    current_state: StrEnum,
    initial_state: StrEnum,
    allowed_edges: set[tuple[str, str]],
    terminal_states: set[str],
    next_transition_sequence: TransitionSequence,
    allow_empty_states: set[str],
) -> AggregateVersion:
    """Validate identical transition-history invariants shared by all aggregates."""
    if not history:
        if current_state.value not in allow_empty_states:
            raise ReconstructionError(
                ReconstructionErrorCategory.INVALID_TRANSITION_HISTORY,
                "empty transition history is not valid for the restored state",
                field="transition_history",
            )
        if next_transition_sequence != TransitionSequence.initial():
            raise ReconstructionError(
                ReconstructionErrorCategory.INVALID_TRANSITION_SEQUENCE,
                "empty transition history requires next sequence 1",
                field="next_transition_sequence",
            )
        return AggregateVersion.initial()

    previous_to_state: str | None = None
    highest_version = AggregateVersion.initial()
    for index, record in enumerate(history, start=1):
        if not isinstance(record, StateTransitionRecord):
            raise ReconstructionError(
                ReconstructionErrorCategory.INVALID_TRANSITION_HISTORY,
                "transition history contains an invalid record",
                field="transition_history",
            )
        if record.identity_reference is not None and record.identity_reference != identity:
            raise ReconstructionError(
                ReconstructionErrorCategory.INVALID_TRANSITION_HISTORY,
                "transition history identity does not match aggregate identity",
                field="transition_history",
            )
        if record.sequence != TransitionSequence(index):
            raise ReconstructionError(
                ReconstructionErrorCategory.INVALID_TRANSITION_SEQUENCE,
                "transition history sequences must be contiguous from 1",
                field="transition_history",
            )
        if index == 1 and record.from_state != initial_state.value:
            raise ReconstructionError(
                ReconstructionErrorCategory.INVALID_TRANSITION_HISTORY,
                "first transition must originate from the canonical initial state",
                field="transition_history",
            )
        if previous_to_state is not None:
            if previous_to_state in terminal_states:
                raise ReconstructionError(
                    ReconstructionErrorCategory.INVALID_TRANSITION_HISTORY,
                    "terminal transition may not be followed by another transition",
                    field="transition_history",
                )
            if record.from_state != previous_to_state:
                raise ReconstructionError(
                    ReconstructionErrorCategory.INVALID_TRANSITION_HISTORY,
                    "transition history is not a connected lifecycle path",
                    field="transition_history",
                )
        if (record.from_state or "", record.to_state) not in allowed_edges:
            raise ReconstructionError(
                ReconstructionErrorCategory.INVALID_TRANSITION_HISTORY,
                "transition history contains an invalid lifecycle edge",
                field="transition_history",
            )
        if record.version > highest_version:
            highest_version = record.version
        previous_to_state = record.to_state

    if previous_to_state != current_state.value:
        raise ReconstructionError(
            ReconstructionErrorCategory.INCONSISTENT_CURRENT_STATE,
            "final transition state does not match restored current state",
            field="state",
        )
    if next_transition_sequence != TransitionSequence(len(history) + 1):
        raise ReconstructionError(
            ReconstructionErrorCategory.INVALID_TRANSITION_SEQUENCE,
            "next transition sequence must follow the final history sequence",
            field="next_transition_sequence",
        )
    return highest_version
