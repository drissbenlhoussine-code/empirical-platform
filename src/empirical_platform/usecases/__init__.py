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

from empirical_platform.usecases.add_review_finding import (
    AddReviewFindingCommand,
    AddReviewFindingHandler,
)
from empirical_platform.usecases.authorize_run import (
    AuthorizeRunCommand,
    AuthorizeRunHandler,
)
from empirical_platform.usecases.complete_review import (
    CompleteReviewCommand,
    CompleteReviewHandler,
)
from empirical_platform.usecases.create_campaign import (
    CreateCampaignCommand,
    CreateCampaignHandler,
)
from empirical_platform.usecases.create_evidence_package import (
    CreateEvidencePackageCommand,
    CreateEvidencePackageHandler,
)
from empirical_platform.usecases.create_review import (
    CreateReviewCommand,
    CreateReviewHandler,
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
from empirical_platform.usecases.get_evidence_package import (
    EvidencePackageSnapshot,
    GetEvidencePackageHandler,
    GetEvidencePackageQuery,
)
from empirical_platform.usecases.get_review import (
    GetReviewHandler,
    GetReviewQuery,
    ReviewSnapshot,
)
from empirical_platform.usecases.get_run import (
    GetRunHandler,
    GetRunQuery,
    RunSnapshot,
)
from empirical_platform.usecases.prepare_campaign_for_authorization import (
    PrepareCampaignForAuthorizationCommand,
    PrepareCampaignForAuthorizationHandler,
)
from empirical_platform.usecases.record_evidence_package_artifact_reference import (
    RecordEvidencePackageArtifactReferenceCommand,
    RecordEvidencePackageArtifactReferenceHandler,
)
from empirical_platform.usecases.record_evidence_package_criterion_result import (
    RecordEvidencePackageCriterionResultCommand,
    RecordEvidencePackageCriterionResultHandler,
)
from empirical_platform.usecases.seal_evidence_package import (
    SealEvidencePackageCommand,
    SealEvidencePackageHandler,
)
from empirical_platform.usecases.start_evidence_package_collection import (
    StartEvidencePackageCollectionCommand,
    StartEvidencePackageCollectionHandler,
)
from empirical_platform.usecases.start_review import (
    StartReviewCommand,
    StartReviewHandler,
)

__all__ = [
    "AddReviewFindingCommand",
    "AddReviewFindingHandler",
    "AuthorizeRunCommand",
    "AuthorizeRunHandler",
    "CampaignSnapshot",
    "CompleteReviewCommand",
    "CompleteReviewHandler",
    "CreateCampaignCommand",
    "CreateCampaignHandler",
    "CreateEvidencePackageCommand",
    "CreateEvidencePackageHandler",
    "CreateReviewCommand",
    "CreateReviewHandler",
    "CreateRunCommand",
    "CreateRunHandler",
    "EvidencePackageSnapshot",
    "GetCampaignHandler",
    "GetCampaignQuery",
    "GetEvidencePackageHandler",
    "GetEvidencePackageQuery",
    "GetReviewHandler",
    "GetReviewQuery",
    "GetRunHandler",
    "GetRunQuery",
    "PrepareCampaignForAuthorizationCommand",
    "PrepareCampaignForAuthorizationHandler",
    "RecordEvidencePackageArtifactReferenceCommand",
    "RecordEvidencePackageArtifactReferenceHandler",
    "RecordEvidencePackageCriterionResultCommand",
    "RecordEvidencePackageCriterionResultHandler",
    "ReviewSnapshot",
    "RunSnapshot",
    "SealEvidencePackageCommand",
    "SealEvidencePackageHandler",
    "StartEvidencePackageCollectionCommand",
    "StartEvidencePackageCollectionHandler",
    "StartReviewCommand",
    "StartReviewHandler",
]
