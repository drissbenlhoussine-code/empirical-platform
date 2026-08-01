"""Prepare a Campaign for authorization: concrete command and handler (MILESTONE-032)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from empirical_platform.campaign.repository import CampaignRepository
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId
from empirical_platform.shared.contracts.repository import SaveResult
from empirical_platform.shared.domain.versioning import AggregateVersion


@dataclass(frozen=True, slots=True)
class PrepareCampaignForAuthorizationCommand:
    """Request to transition an existing Campaign from DRAFT to READY_FOR_AUTHORIZATION."""

    identity: DomainIdentity[CampaignId]
    expected_persisted_version: AggregateVersion
    actor: str
    occurred_at: datetime
    correlation_id: str | None = None
    reason: str | None = None


class PrepareCampaignForAuthorizationHandler:
    """Loads, transitions, and persists one Campaign for one command."""

    __slots__ = ("_campaign_repository",)

    def __init__(self, *, campaign_repository: CampaignRepository) -> None:
        self._campaign_repository = campaign_repository

    def handle(self, command: PrepareCampaignForAuthorizationCommand) -> SaveResult:
        """Transition the identified Campaign to READY_FOR_AUTHORIZATION and persist it."""
        loaded = self._campaign_repository.get(command.identity)
        campaign = loaded.aggregate
        campaign.prepare_for_authorization(
            actor=command.actor,
            occurred_at=command.occurred_at,
            correlation_id=command.correlation_id,
            reason=command.reason,
        )
        return self._campaign_repository.save(
            campaign, expected_persisted_version=command.expected_persisted_version
        )
