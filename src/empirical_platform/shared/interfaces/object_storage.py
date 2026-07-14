"""Object-storage interfaces without concrete read/write behavior."""

from __future__ import annotations

from typing import Protocol


class ObjectStorageHealth(Protocol):
    """Generic object-storage health interface."""

    def check(self) -> bool:
        """Return whether the object-storage dependency is reachable."""
        ...
