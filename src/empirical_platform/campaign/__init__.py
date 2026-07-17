"""Campaign module boundary. No aggregate behavior is implemented."""

from empirical_platform.campaign.lifecycle import CampaignLifecycleState, RunLifecycleState

__all__ = [
    "CampaignLifecycleState",
    "RunLifecycleState",
]
