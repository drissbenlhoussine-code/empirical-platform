"""Campaign and Run lifecycle primitives."""

from enum import StrEnum


class CampaignLifecycleState(StrEnum):
    """Frozen Campaign lifecycle states from MILESTONE-012."""

    DRAFT = "DRAFT"
    READY_FOR_AUTHORIZATION = "READY_FOR_AUTHORIZATION"
    AUTHORIZED = "AUTHORIZED"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class RunLifecycleState(StrEnum):
    """Frozen Run execution lifecycle states from MILESTONE-012."""

    CREATED = "CREATED"
    AUTHORIZED = "AUTHORIZED"
    ACQUIRING = "ACQUIRING"
    NORMALIZING = "NORMALIZING"
    VALIDATING = "VALIDATING"
    EXECUTION_COMPLETED = "EXECUTION_COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
