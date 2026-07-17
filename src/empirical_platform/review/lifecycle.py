"""Review lifecycle and disposition primitives."""

from enum import StrEnum


class ReviewLifecycleState(StrEnum):
    """Frozen Review lifecycle states from MILESTONE-012."""

    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ReviewDisposition(StrEnum):
    """Review disposition values, separate from lifecycle state."""

    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    INCONCLUSIVE = "INCONCLUSIVE"
