"""Evidence Package lifecycle primitives."""

from enum import StrEnum


class EvidencePackageLifecycleState(StrEnum):
    """Frozen Evidence Package lifecycle states from MILESTONE-012."""

    INITIALIZED = "INITIALIZED"
    COLLECTING = "COLLECTING"
    SEALED = "SEALED"
    INVALIDATED = "INVALIDATED"
