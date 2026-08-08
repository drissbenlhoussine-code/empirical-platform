"""Resume an existing, SUSPENDED Campaign.

Concrete command and handler. MILESTONE-056.
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
class ResumeCampaignCommand:
    """Request to transition an existing Campaign from SUSPENDED to ACTIVE."""

    identity: DomainIdentity[CampaignId]
    expected_persisted_version: AggregateVersion
    reason: str
    actor: str
    occurred_at: datetime
    correlation_id: str | None = None


class ResumeCampaignHandler:
    """Loads, resumes, and persists one Campaign for one command."""

    __slots__ = ("_campaign_repository",)

    def __init__(self, *, campaign_repository: CampaignRepository) -> None:
        self._campaign_repository = campaign_repository

    def handle(self, command: ResumeCampaignCommand) -> SaveResult:
        """Transition the identified Campaign to ACTIVE and persist it."""
        loaded = self._campaign_repository.get(command.identity)
        campaign = loaded.aggregate
        campaign.resume(
            reason=command.reason,
            actor=command.actor,
            occurred_at=command.occurred_at,
            correlation_id=command.correlation_id,
        )
        return self._campaign_repository.save(
            campaign, expected_persisted_version=command.expected_persisted_version
        )
