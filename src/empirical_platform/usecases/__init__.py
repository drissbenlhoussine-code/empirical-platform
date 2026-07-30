"""Concrete application command use cases (MILESTONE-030).

Pairs one concrete command with its one handler, wiring the frozen
`CommandHandler` Protocol (MILESTONE-027) to the already-frozen `Campaign`
domain model via the `CampaignRepository` Protocol (MILESTONE-020). This
package depends only on domain-neutral abstractions -- see
`MILESTONE_030_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_DESIGN_FREEZE.md`
Section 10.C for the frozen infrastructure-import prohibition.
"""

from empirical_platform.usecases.create_campaign import (
    CreateCampaignCommand,
    CreateCampaignHandler,
)

__all__ = [
    "CreateCampaignCommand",
    "CreateCampaignHandler",
]
