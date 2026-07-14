"""Job ledger and orchestration boundary interfaces."""

from __future__ import annotations

from typing import Protocol


class JobLedgerHealth(Protocol):
    """Generic job-ledger health interface."""

    def check(self) -> bool:
        """Return whether the job-ledger dependency is reachable."""
        ...
