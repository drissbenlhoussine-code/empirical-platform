"""Revise the scope statement of an existing, DRAFT Campaign.

Concrete command and handler. MILESTONE-056.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.campaign.aggregate import CampaignScopeStatement
from empirical_platform.campaign.repository import CampaignRepository
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId
from empirical_platform.shared.contracts.repository import SaveResult
from empirical_platform.shared.domain.versioning import AggregateVersion


@dataclass(frozen=True, slots=True)
class ReviseCampaignScopeStatementCommand:
    """Request to replace an existing Campaign's scope statement while DRAFT."""

    identity: DomainIdentity[CampaignId]
    expected_persisted_version: AggregateVersion
    scope_statement: str


class ReviseCampaignScopeStatementHandler:
    """Loads, revises the scope statement of, and persists one Campaign for one command."""

    __slots__ = ("_campaign_repository",)

    def __init__(self, *, campaign_repository: CampaignRepository) -> None:
        self._campaign_repository = campaign_repository

    def handle(self, command: ReviseCampaignScopeStatementCommand) -> SaveResult:
        """Replace the identified Campaign's scope statement and persist it."""
        loaded = self._campaign_repository.get(command.identity)
        campaign = loaded.aggregate
        campaign.revise_scope_statement(CampaignScopeStatement(command.scope_statement))
        return self._campaign_repository.save(
            campaign, expected_persisted_version=command.expected_persisted_version
        )
