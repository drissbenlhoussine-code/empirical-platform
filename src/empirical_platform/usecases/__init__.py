"""Concrete application command and query use cases (MILESTONE-030 through MILESTONE-033).

Pairs each concrete command or query with its one handler, wiring the frozen
`CommandHandler` (MILESTONE-027) and `QueryHandler` (MILESTONE-028) Protocols
to the already-frozen `Campaign` and `Run` domain models via the
`CampaignRepository` and `RunRepository` Protocols (MILESTONE-020). This
package depends only on domain-neutral abstractions -- see
`MILESTONE_030_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_DESIGN_FREEZE.md`
Section 10.C,
`MILESTONE_031_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_DESIGN_FREEZE.md`
Section 9,
`MILESTONE_032_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_CAMPAIGN_LIFECYCLE_TRANSITION_DESIGN_FREEZE.md`
Section 23, and
`MILESTONE_033_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_CREATION_DESIGN_FREEZE.md`
Section 25 for the frozen infrastructure-import prohibition.
"""

from empirical_platform.usecases.create_campaign import (
    CreateCampaignCommand,
    CreateCampaignHandler,
)
from empirical_platform.usecases.create_run import (
    CreateRunCommand,
    CreateRunHandler,
)
from empirical_platform.usecases.get_campaign import (
    CampaignSnapshot,
    GetCampaignHandler,
    GetCampaignQuery,
)
from empirical_platform.usecases.prepare_campaign_for_authorization import (
    PrepareCampaignForAuthorizationCommand,
    PrepareCampaignForAuthorizationHandler,
)

__all__ = [
    "CampaignSnapshot",
    "CreateCampaignCommand",
    "CreateCampaignHandler",
    "CreateRunCommand",
    "CreateRunHandler",
    "GetCampaignHandler",
    "GetCampaignQuery",
    "PrepareCampaignForAuthorizationCommand",
    "PrepareCampaignForAuthorizationHandler",
]
