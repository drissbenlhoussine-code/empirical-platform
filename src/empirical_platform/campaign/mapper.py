"""Domain-facing Campaign persistence mapper contract (MILESTONE-021)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from empirical_platform.campaign._reconstruction import CampaignReconstructionState
from empirical_platform.campaign.aggregate import Campaign
from empirical_platform.shared.contracts.mapping import (
    IdentityDurableRecord,
    TransitionDurableRecord,
)


@dataclass(frozen=True, slots=True)
class CampaignDurableRecord:
    """Persistence-neutral, field-level durable representation of a Campaign."""

    identity: IdentityDurableRecord
    scope_statement: str
    lifecycle_state: str
    version: int
    next_transition_sequence: int
    transition_history: tuple[TransitionDurableRecord, ...]


class CampaignMapper(Protocol):
    """Persistence-neutral mapper contract between Campaign and its durable record."""

    def to_durable_record(self, aggregate: Campaign) -> CampaignDurableRecord:
        """Transform a Campaign into its persistence-neutral durable record.

        Pure data transformation: does not mutate the aggregate, increment its
        version, or append transition history. May raise `MapperError` with
        category `INVALID_AGGREGATE_FOR_MAPPING` if the aggregate is not valid
        for mapping.
        """
        ...

    def from_durable_record(self, record: CampaignDurableRecord) -> CampaignReconstructionState:
        """Transform a durable record into a `CampaignReconstructionState`.

        Does not call the internal `_reconstruct_campaign` factory; that call
        remains a future repository implementation's responsibility. Raises
        `MapperError` with category `INVALID_DURABLE_RECORD` for durable data
        that is structurally malformed before reconstruction can validate it
        (for example, a `lifecycle_state` string matching no known state).
        """
        ...
