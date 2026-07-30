"""Create a new Campaign: concrete command and handler (MILESTONE-030)."""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.campaign.aggregate import Campaign, CampaignScopeStatement
from empirical_platform.campaign.repository import CampaignRepository
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId
from empirical_platform.shared.identifiers import RuntimeIdentifierGenerator


@dataclass(frozen=True, slots=True)
class CreateCampaignCommand:
    """Request to create a new Campaign.

    Carries raw, unvalidated data; `CreateCampaignHandler` translates it into
    the already-frozen `CampaignId` and `CampaignScopeStatement` value
    objects, which perform all business-rule validation.
    """

    campaign_governance_id: str
    scope_statement: str


class CreateCampaignHandler:
    """Creates and persists a new Campaign for one `CreateCampaignCommand`."""

    __slots__ = ("_campaign_repository", "_runtime_identifier_generator")

    def __init__(
        self,
        *,
        campaign_repository: CampaignRepository,
        runtime_identifier_generator: RuntimeIdentifierGenerator,
    ) -> None:
        self._campaign_repository = campaign_repository
        self._runtime_identifier_generator = runtime_identifier_generator

    def handle(self, command: CreateCampaignCommand) -> DomainIdentity[CampaignId]:
        """Create and persist a new Campaign; return its identity."""
        identity = DomainIdentity(
            governance_id=CampaignId(command.campaign_governance_id),
            runtime_id=self._runtime_identifier_generator.generate(),
        )
        campaign = Campaign(
            identity=identity,
            scope_statement=CampaignScopeStatement(command.scope_statement),
        )
        self._campaign_repository.add(campaign)
        return campaign.identity
