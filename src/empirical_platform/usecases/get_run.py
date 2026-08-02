"""Retrieve a Run by full identity: concrete query and handler (MILESTONE-034)."""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.campaign.lifecycle import RunLifecycleState
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId, RunId
from empirical_platform.run.repository import RunRepository


@dataclass(frozen=True, slots=True)
class GetRunQuery:
    """Request to retrieve a Run by its full frozen identity."""

    identity: DomainIdentity[RunId]


@dataclass(frozen=True, slots=True)
class RunSnapshot:
    """Immutable, milestone-local, bounded Run header/status read value.

    Deliberately excludes `Run.version` (aggregate domain state) and
    `LoadedAggregate.persisted_version` (repository concurrency metadata),
    and does not expose `manifests` or `transition_history` -- see
    MILESTONE_034_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_RUN_RETRIEVAL_DESIGN_FREEZE.md
    Sections 16-19.
    """

    identity: DomainIdentity[RunId]
    campaign_id: CampaignId
    state: RunLifecycleState


class GetRunHandler:
    """Retrieves a Run for one `GetRunQuery`."""

    __slots__ = ("_run_repository",)

    def __init__(self, *, run_repository: RunRepository) -> None:
        self._run_repository = run_repository

    def handle(self, query: GetRunQuery) -> RunSnapshot:
        """Load a Run by identity and return its bounded read-side snapshot."""
        loaded = self._run_repository.get(query.identity)
        return RunSnapshot(
            identity=loaded.aggregate.identity,
            campaign_id=loaded.aggregate.campaign_id,
            state=loaded.aggregate.state,
        )
