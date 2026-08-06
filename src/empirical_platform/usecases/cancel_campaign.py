"""Cancel an existing Campaign from any allowed non-terminal state.

Concrete command and handler. MILESTONE-047.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from empirical_platform.campaign.repository import CampaignRepository
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId
from empirical_platform.shared.contracts.repository import SaveResult
from empirical_platform.shared.domain.versioning import AggregateVersion


@dataclass(frozen=True, slots=True)
class CancelCampaignCommand:
    """Request to cancel an existing Campaign from an allowed non-terminal state."""

    identity: DomainIdentity[CampaignId]
    expected_persisted_version: AggregateVersion
    actor: str
    occurred_at: datetime
    reason: str | None = None
    correlation_id: str | None = None


class CancelCampaignHandler:
    """Loads, cancels, and persists one Campaign for one command."""

    __slots__ = ("_campaign_repository",)

    def __init__(self, *, campaign_repository: CampaignRepository) -> None:
        self._campaign_repository = campaign_repository

    def handle(self, command: CancelCampaignCommand) -> SaveResult:
        """Cancel the identified Campaign and persist it."""
        loaded = self._campaign_repository.get(command.identity)
        campaign = loaded.aggregate
        campaign.cancel(
            actor=command.actor,
            occurred_at=command.occurred_at,
            reason=command.reason,
            correlation_id=command.correlation_id,
        )
        return self._campaign_repository.save(
            campaign, expected_persisted_version=command.expected_persisted_version
        )
