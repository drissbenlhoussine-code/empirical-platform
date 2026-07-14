"""Metadata persistence interfaces without domain schemas."""

from __future__ import annotations

from typing import Protocol


class ConnectivityCheck(Protocol):
    """Generic connectivity check interface."""

    def check(self) -> bool:
        """Return whether the dependency is reachable."""
        ...
