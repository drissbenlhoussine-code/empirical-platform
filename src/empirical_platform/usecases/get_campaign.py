"""Retrieve a Campaign by full identity: concrete query and handler (MILESTONE-031)."""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.campaign.aggregate import CampaignScopeStatement
from empirical_platform.campaign.lifecycle import CampaignLifecycleState
from empirical_platform.campaign.repository import CampaignRepository
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId


@dataclass(frozen=True, slots=True)
class GetCampaignQuery:
    """Request to retrieve a Campaign by its full frozen identity."""

    identity: DomainIdentity[CampaignId]


@dataclass(frozen=True, slots=True)
class CampaignSnapshot:
    """Immutable, milestone-local read value for a retrieved Campaign."""

    identity: DomainIdentity[CampaignId]
    scope_statement: CampaignScopeStatement
    state: CampaignLifecycleState


class GetCampaignHandler:
    """Retrieves a Campaign for one `GetCampaignQuery`."""

    __slots__ = ("_campaign_repository",)

    def __init__(self, *, campaign_repository: CampaignRepository) -> None:
        self._campaign_repository = campaign_repository

    def handle(self, query: GetCampaignQuery) -> CampaignSnapshot:
        """Load a Campaign by identity and return its read-side snapshot."""
        loaded = self._campaign_repository.get(query.identity)
        return CampaignSnapshot(
            identity=loaded.aggregate.identity,
            scope_statement=loaded.aggregate.scope_statement,
            state=loaded.aggregate.state,
        )
