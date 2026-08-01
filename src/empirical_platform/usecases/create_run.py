"""Create a new Run for an existing Campaign: concrete command and handler (MILESTONE-033)."""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId, RunId
from empirical_platform.run.aggregate import Run
from empirical_platform.run.repository import RunRepository
from empirical_platform.shared.identifiers import RuntimeIdentifierGenerator


@dataclass(frozen=True, slots=True)
class CreateRunCommand:
    """Request to create a new Run for an existing Campaign.

    Carries raw, unvalidated data; `CreateRunHandler` translates it into the
    already-frozen `RunId` and `CampaignId` value objects, which perform all
    format validation. Campaign existence is not validated here or in the
    handler -- it is enforced by the database foreign-key constraint on the
    `run.campaign_id` column (see
    MILESTONE_033_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_CREATION_DESIGN_FREEZE.md
    Section 11).
    """

    run_governance_id: str
    campaign_governance_id: str


class CreateRunHandler:
    """Creates and persists a new Run for one `CreateRunCommand`."""

    __slots__ = ("_run_repository", "_runtime_identifier_generator")

    def __init__(
        self,
        *,
        run_repository: RunRepository,
        runtime_identifier_generator: RuntimeIdentifierGenerator,
    ) -> None:
        self._run_repository = run_repository
        self._runtime_identifier_generator = runtime_identifier_generator

    def handle(self, command: CreateRunCommand) -> DomainIdentity[RunId]:
        """Create and persist a new Run; return its identity."""
        identity = DomainIdentity(
            governance_id=RunId(command.run_governance_id),
            runtime_id=self._runtime_identifier_generator.generate(),
        )
        run = Run(
            identity=identity,
            campaign_id=CampaignId(command.campaign_governance_id),
        )
        self._run_repository.add(run)
        return run.identity
