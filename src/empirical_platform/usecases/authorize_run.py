"""Authorize an existing Run: concrete command and handler (MILESTONE-035)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import RunId
from empirical_platform.run.repository import RunRepository
from empirical_platform.shared.contracts.repository import SaveResult
from empirical_platform.shared.domain.versioning import AggregateVersion


@dataclass(frozen=True, slots=True)
class AuthorizeRunCommand:
    """Request to transition an existing Run from CREATED to AUTHORIZED."""

    identity: DomainIdentity[RunId]
    expected_persisted_version: AggregateVersion
    actor: str
    occurred_at: datetime
    correlation_id: str | None = None
    reason: str | None = None


class AuthorizeRunHandler:
    """Loads, authorizes, and persists one Run for one command."""

    __slots__ = ("_run_repository",)

    def __init__(self, *, run_repository: RunRepository) -> None:
        self._run_repository = run_repository

    def handle(self, command: AuthorizeRunCommand) -> SaveResult:
        """Transition the identified Run to AUTHORIZED and persist it."""
        loaded = self._run_repository.get(command.identity)
        run = loaded.aggregate
        run.authorize(
            actor=command.actor,
            occurred_at=command.occurred_at,
            correlation_id=command.correlation_id,
            reason=command.reason,
        )
        return self._run_repository.save(
            run, expected_persisted_version=command.expected_persisted_version
        )
